"""Stage ``clean-photos``: remove from R2 the photos no served index references (ADR 0015).

ADR 0004 keeps a candidate photo in R2 only while the TSE publishes it. ``mirror-photos`` in
production retains every old object (ADR 0014), because deleting before ``publish`` could
break the index Cloud Run is still serving. This stage runs after a successful ``publish``
instead, and deletes an object only when no index a running instance may still hold
references it.

How long an instance may hold a superseded index follows from ``core/index.py``: the service
has no timer. A finished query signals the check task, which asks the ``IndexSource`` at most
once every 60 seconds and swaps in the background, so the query that triggers the check (and
every query while the download runs) is still answered from the old version. A warm instance
with no traffic (``--min-instances=1`` in election week) therefore keeps its version until the
first query after it wakes, however many refreshes published in between, and a failed check
keeps the open version for as long as the index bucket stays unreachable. The immediately
previous pair is not enough.

The grace rule: an object is deleted only after it has gone unreferenced by every index that
was current for ``CLEANUP_GRACE`` (48 hours). The stage records, in a ledger in the index
bucket, when each photo object was first seen unreferenced by both the pair this run
published and the pair it superseded. The ledger names the pair it evaluated last; when this
run's previous pair is not that one (a run that published without cleaning up, a run
refused before it wrote the ledger, a manual publish or rollback), no evaluation covered
the pairs current in between and every clock restarts. So an object past the grace was
absent from every pair that was current at any moment in the last 48 hours. An instance
still serving an older pair has not completed an index check for 48 hours; its answers
already carry the staleness warning (``core.STALE_AFTER_HOURS``, also 48), since
that pair's data is at least as old.

Rolling back to a version superseded more than 48 hours ago can therefore point to deleted
photos. The next refresh repairs it: carry-forward drops a URL R2 no longer holds and the
mirror uploads every photo the TSE still publishes.

Refusals (``PhotoCleanupError``), all before any deletion: a pair that does not match its
manifest or breaks the photo chain, a live manifest that is not the pair this run published,
an R2 listing that lacks an object the published index references, and more due deletions
than ``max_delete_fraction`` of the photo objects in the bucket. Only the last one writes the
ledger first, so the clocks keep running and the chain stays intact while the operator
decides; the others write nothing. Objects whose key is not a content-addressed photo key,
and the full-load marker, are never deleted.
"""

from __future__ import annotations

import datetime as dt
import json
import tempfile
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from br_elections_mcp.index_schema import INDEX_FILE_NAME, MANIFEST_FILE_NAME
from br_elections_mcp.pipeline.bucket import BucketClient, PhotoBucketClient
from br_elections_mcp.pipeline.mirror_photos import FULL_LOAD_MARKER_KEY
from br_elections_mcp.pipeline.photo_integrity import is_photo_key, photo_problems
from br_elections_mcp.pipeline.publish import (
    download_current_manifest,
    normalize_prefix,
    verify_index_pair,
)

CLEANUP_GRACE = dt.timedelta(hours=48)
"""How long an object must stay unreferenced by every current pair before it is deleted."""

MAX_DELETE_FRACTION = 0.1
"""Default bound: refuse when more than this fraction of the photo objects would go."""

LEDGER_OBJECT = "photo-cleanup/unreferenced.json"
"""The ledger's object name in the index bucket, under the publish prefix."""

LEDGER_VERSION = 1
_MAX_SHOWN = 3


class PhotoCleanupError(RuntimeError):
    """The cleanup is refused; nothing was deleted."""


@dataclass(frozen=True, slots=True)
class CleanupLedger:
    """When each photo object was first seen unreferenced, and by which evaluation."""

    evaluated_index_sha256: str
    """``index_sha256`` of the pair published by the run that wrote this ledger."""

    unreferenced_since: Mapping[str, dt.datetime]
    """Photo key -> first evaluation that found it in neither the published nor previous pair."""

    def to_json(self) -> str:
        return (
            json.dumps(
                {
                    "version": LEDGER_VERSION,
                    "evaluated_index_sha256": self.evaluated_index_sha256,
                    "unreferenced_since": {
                        key: since.astimezone(dt.UTC).isoformat()
                        for key, since in sorted(self.unreferenced_since.items())
                    },
                },
                indent=2,
            )
            + "\n"
        )

    @classmethod
    def from_json(cls, text: str) -> CleanupLedger:
        raw: Any = json.loads(text)
        if not isinstance(raw, dict) or raw.get("version") != LEDGER_VERSION:
            raise ValueError("unsupported photo cleanup ledger version")
        since: dict[str, dt.datetime] = {}
        for key, value in raw["unreferenced_since"].items():
            parsed = dt.datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                raise ValueError(f"ledger time without a timezone: {value!r}")
            since[str(key)] = parsed
        return cls(
            evaluated_index_sha256=str(raw["evaluated_index_sha256"]), unreferenced_since=since
        )


@dataclass(frozen=True, slots=True)
class CleanupPlan:
    """What one evaluation decided, before anything is written or deleted."""

    photo_objects: int
    """Objects in the bucket with a content-addressed photo key."""

    other_objects: int
    """Objects with any other key (the full-load marker excluded): never deleted."""

    chain_intact: bool
    """Whether the previous ledger evaluated this run's previous pair (clocks carried)."""

    ledger: CleanupLedger
    """The ledger to write: every photo object neither pair references, with its clock."""

    due: tuple[str, ...]
    """Keys unreferenced for at least the grace: what the stage deletes."""

    refusal: str | None = None
    """Why the stage must delete nothing although the ledger is worth keeping (the bound)."""


@dataclass(frozen=True, slots=True)
class CleanupResult:
    plan: CleanupPlan
    deleted: tuple[str, ...]
    """Keys deleted this run; empty on a dry run."""


def referenced_photo_keys(index_path: Path, public_domain: str) -> set[str]:
    """The R2 keys the ``photo_url`` values of an index point to, after the chain check."""
    problems = photo_problems(index_path, public_domain)
    if problems:
        raise PhotoCleanupError(f"{index_path}: photo chain: {'; '.join(problems)}")
    conn = duckdb.connect(str(index_path), read_only=True)
    try:
        rows = conn.execute(
            "SELECT DISTINCT photo_url FROM candidates WHERE photo_url IS NOT NULL"
        ).fetchall()
    finally:
        conn.close()
    base = public_domain.rstrip("/") + "/"
    # photo_problems with the public domain guarantees every URL is base + key.
    return {url.removeprefix(base) for (url,) in rows}


def plan_photo_cleanup(
    remote_keys: Iterable[str],
    *,
    published: set[str],
    published_sha256: str,
    previous: set[str],
    previous_sha256: str | None,
    ledger: CleanupLedger | None,
    now: dt.datetime,
    grace: dt.timedelta = CLEANUP_GRACE,
    max_delete_fraction: float = MAX_DELETE_FRACTION,
) -> CleanupPlan:
    """Decide which objects are due for deletion; see the module docstring for the rules.

    ``previous_sha256`` is None when no pair was published before this run's; the clocks
    then restart. Raises ``PhotoCleanupError`` when the listing lacks a key the published
    index references; the plan carries a ``refusal`` when the due deletions exceed
    ``max_delete_fraction`` of the photo objects.
    """
    remote = set(remote_keys)
    missing = sorted(published - remote)
    if missing:
        raise PhotoCleanupError(
            f"the R2 listing lacks {len(missing)} objects the published index references, "
            f"e.g. {', '.join(missing[:_MAX_SHOWN])}; wrong bucket or partial listing, "
            "nothing deleted"
        )
    photo_keys = {key for key in remote if is_photo_key(key)}
    others = remote - photo_keys - {FULL_LOAD_MARKER_KEY}
    chain_intact = (
        ledger is not None
        and previous_sha256 is not None
        and ledger.evaluated_index_sha256 == previous_sha256
    )
    carried = ledger.unreferenced_since if chain_intact and ledger is not None else {}
    # A clock in the future (a skewed writer) restarts at now: it can only delay a deletion.
    since = {
        key: min(carried.get(key, now), now) for key in sorted(photo_keys - published - previous)
    }
    due = tuple(key for key, first in since.items() if now - first >= grace)
    refusal = None
    if len(due) > max_delete_fraction * len(photo_keys):
        refusal = (
            f"{len(due)} of {len(photo_keys)} photo objects would be deleted, above the bound "
            f"of {max_delete_fraction:.0%}; nothing deleted, the ledger is kept so the clocks "
            "keep running"
        )
    return CleanupPlan(
        photo_objects=len(photo_keys),
        other_objects=len(others),
        chain_intact=chain_intact,
        ledger=CleanupLedger(evaluated_index_sha256=published_sha256, unreferenced_since=since),
        due=due,
        refusal=refusal,
    )


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def read_ledger(
    index_bucket: BucketClient, *, prefix: str = "", warn: Callable[[str], None] | None = None
) -> CleanupLedger | None:
    """The ledger in the index bucket; None when absent or unreadable (the clocks restart)."""
    with tempfile.TemporaryDirectory(prefix=".photo-cleanup-") as tmp_name:
        path = Path(tmp_name) / "ledger.json"
        if not index_bucket.download(f"{normalize_prefix(prefix)}{LEDGER_OBJECT}", path):
            return None
        try:
            return CleanupLedger.from_json(path.read_text())
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            if warn is not None:
                warn(f"photo cleanup ledger unreadable ({exc}); every clock restarts")
            return None


def write_ledger(index_bucket: BucketClient, ledger: CleanupLedger, *, prefix: str = "") -> None:
    with tempfile.TemporaryDirectory(prefix=".photo-cleanup-") as tmp_name:
        path = Path(tmp_name) / "ledger.json"
        path.write_text(ledger.to_json())
        index_bucket.upload(path, f"{normalize_prefix(prefix)}{LEDGER_OBJECT}")


def clean_photos(
    published_dir: Path,
    previous_dir: Path,
    photo_bucket: PhotoBucketClient,
    index_bucket: BucketClient,
    *,
    public_domain: str,
    prefix: str = "",
    dry_run: bool = False,
    max_delete_fraction: float = MAX_DELETE_FRACTION,
    now: Callable[[], dt.datetime] = _utcnow,
    progress: Callable[[str], None] | None = None,
) -> CleanupResult:
    """Evaluate the pair just published against the one it superseded, then delete what is due.

    ``published_dir`` holds the pair this run published; ``previous_dir`` the pair that was
    current before it, as ``current-index`` downloaded it (no index there means nothing was
    published before). The ledger is written on a dry run too, so the grace clock runs; a
    dry run never touches R2 beyond listing it. Raises ``PhotoCleanupError`` or
    ``PublishError`` before any deletion when a check fails.
    """
    published_manifest = verify_index_pair(published_dir)
    with tempfile.TemporaryDirectory(prefix=".photo-cleanup-") as tmp_name:
        live = download_current_manifest(
            index_bucket, Path(tmp_name) / MANIFEST_FILE_NAME, prefix=prefix
        )
    if live is None or live.index_sha256 != published_manifest.index_sha256:
        raise PhotoCleanupError(
            "the live manifest is not the pair this run published; nothing deleted"
        )
    published = referenced_photo_keys(published_dir / INDEX_FILE_NAME, public_domain)
    previous: set[str] = set()
    previous_sha256: str | None = None
    if (previous_dir / INDEX_FILE_NAME).is_file():
        previous_sha256 = verify_index_pair(previous_dir).index_sha256
        previous = referenced_photo_keys(previous_dir / INDEX_FILE_NAME, public_domain)

    ledger = read_ledger(index_bucket, prefix=prefix, warn=progress)
    plan = plan_photo_cleanup(
        photo_bucket.list_objects(),
        published=published,
        published_sha256=published_manifest.index_sha256,
        previous=previous,
        previous_sha256=previous_sha256,
        ledger=ledger,
        now=now(),
        max_delete_fraction=max_delete_fraction,
    )
    # The ledger that justifies a deletion is durable before the deletion happens.
    write_ledger(index_bucket, plan.ledger, prefix=prefix)
    if plan.refusal is not None:
        raise PhotoCleanupError(plan.refusal)
    if dry_run:
        return CleanupResult(plan=plan, deleted=())

    for key in plan.due:
        photo_bucket.delete(key)
    after = photo_bucket.list_objects()
    lost = sorted(published - set(after))
    if lost:
        raise PhotoCleanupError(
            f"after the cleanup R2 lacks {len(lost)} objects the published index references, "
            f"e.g. {', '.join(lost[:_MAX_SHOWN])}"
        )
    return CleanupResult(plan=plan, deleted=plan.due)
