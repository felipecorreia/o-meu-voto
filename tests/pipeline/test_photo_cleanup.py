"""Stage clean-photos: the grace rule, the bound and the refresh wiring (ADR 0015).

No test touches the network: R2 is a FakePhotoBucketClient and the index bucket a
LocalDirectoryBucketClient.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import shlex
import subprocess
from pathlib import Path

import pytest
import yaml

from br_elections_mcp.core.core import STALE_AFTER_HOURS
from br_elections_mcp.index_schema import INDEX_FILE_NAME, MANIFEST_FILE_NAME
from br_elections_mcp.pipeline import __main__ as cli
from br_elections_mcp.pipeline.bucket import FakePhotoBucketClient, LocalDirectoryBucketClient
from br_elections_mcp.pipeline.build import apply_photo_urls
from br_elections_mcp.pipeline.mirror_photos import FULL_LOAD_MARKER_KEY
from br_elections_mcp.pipeline.photo_cleanup import (
    CLEANUP_GRACE,
    LEDGER_OBJECT,
    CleanupLedger,
    PhotoCleanupError,
    clean_photos,
    plan_photo_cleanup,
    read_ledger,
)
from br_elections_mcp.pipeline.photo_integrity import photo_key
from br_elections_mcp.pipeline.publish import PublishError, publish, verify_index_pair
from tests.conftest import build_fixture_index

DOMAIN = "https://fotos.example.org"
T0 = dt.datetime(2026, 10, 1, 10, 10, tzinfo=dt.UTC)
SQ1, SQ2, SQ3, SQ4, SQ5 = (10000000001 + n for n in range(5))


def _key(sq: int, content: bytes) -> str:
    return photo_key("AC", sq, content)[0]


def _keys(count: int) -> list[str]:
    return [_key(SQ1, f"photo-{n}".encode()) for n in range(count)]


# The grace rule, over plan_photo_cleanup


def _plan(remote, *, published=(), previous=(), ledger=None, now=T0, previous_sha="prev", **kw):
    return plan_photo_cleanup(
        remote,
        published=set(published),
        published_sha256="new",
        previous=set(previous),
        previous_sha256=previous_sha,
        ledger=ledger,
        now=now,
        max_delete_fraction=kw.pop("max_delete_fraction", 1.0),
        **kw,
    )


def _ledger(since: dict[str, dt.datetime], evaluated: str = "prev") -> CleanupLedger:
    return CleanupLedger(evaluated_index_sha256=evaluated, unreferenced_since=since)


def test_a_newly_unreferenced_object_starts_its_clock_and_is_not_deleted():
    old, current = _keys(2)

    plan = _plan([old, current], published=[current])

    assert plan.due == ()
    assert plan.ledger.unreferenced_since == {old: T0}
    assert plan.ledger.evaluated_index_sha256 == "new"


@pytest.mark.parametrize(
    ("age", "due"),
    [(CLEANUP_GRACE - dt.timedelta(seconds=1), False), (CLEANUP_GRACE, True)],
)
def test_an_object_is_due_once_unreferenced_for_the_whole_grace(age: dt.timedelta, due: bool):
    old, current = _keys(2)

    plan = _plan([old, current], published=[current], ledger=_ledger({old: T0 - age}))

    assert plan.due == ((old,) if due else ())
    assert plan.ledger.unreferenced_since == {old: T0 - age}


def test_objects_the_published_or_previous_pair_reference_are_never_due():
    in_published, in_previous = _keys(2)
    long_ago = T0 - 10 * CLEANUP_GRACE

    plan = _plan(
        [in_published, in_previous],
        published=[in_published],
        previous=[in_previous],
        ledger=_ledger({in_published: long_ago, in_previous: long_ago}),
    )

    assert plan.due == ()
    assert plan.ledger.unreferenced_since == {}


def test_a_ledger_that_did_not_evaluate_the_previous_pair_restarts_every_clock():
    # A run published without cleaning up: the pair it published was never evaluated.
    old, current = _keys(2)
    long_ago = T0 - 10 * CLEANUP_GRACE

    plan = _plan([old, current], published=[current], ledger=_ledger({old: long_ago}, "other"))

    assert not plan.chain_intact
    assert plan.due == ()
    assert plan.ledger.unreferenced_since == {old: T0}


def test_no_previous_pair_restarts_every_clock():
    old, current = _keys(2)

    plan = _plan(
        [old, current],
        published=[current],
        previous_sha=None,
        ledger=_ledger({old: T0 - 10 * CLEANUP_GRACE}),
    )

    assert plan.due == ()


def test_a_clock_in_the_future_restarts_at_now():
    old, current = _keys(2)

    plan = _plan([old, current], published=[current], ledger=_ledger({old: T0 + CLEANUP_GRACE}))

    assert plan.ledger.unreferenced_since == {old: T0}


def test_keys_outside_the_photo_format_and_the_marker_are_never_touched():
    current = _key(SQ1, b"current")
    stray = ["FAC10000000001_div.jpg", "notes.txt", FULL_LOAD_MARKER_KEY]

    plan = _plan([current, *stray], published=[current], ledger=_ledger({}))

    assert plan.due == ()
    assert plan.ledger.unreferenced_since == {}
    assert plan.other_objects == 2


def test_a_listing_without_a_published_key_is_refused():
    current, other = _keys(2)

    with pytest.raises(PhotoCleanupError, match="lacks 1 objects"):
        _plan([other], published=[current])


def test_due_deletions_above_the_bound_carry_a_refusal_and_keep_the_clocks():
    keys = _keys(10)
    long_ago = T0 - 2 * CLEANUP_GRACE
    ledger = _ledger(dict.fromkeys(keys[:2], long_ago))

    within = _plan(keys, ledger=_ledger({keys[0]: long_ago}), max_delete_fraction=0.1)
    over = _plan(keys, ledger=ledger, max_delete_fraction=0.1)

    assert within.refusal is None
    assert len(within.due) == 1
    assert over.refusal is not None
    assert "2 of 10 photo objects" in over.refusal
    assert over.ledger.unreferenced_since[keys[0]] == long_ago


def test_an_empty_index_can_never_wipe_the_bucket():
    # A bad build with no photo URLs, published twice in a row: the first run only starts
    # the clocks, and once they run out the bound refuses.
    keys = _keys(20)

    first = _plan(keys, published=[], previous=[], ledger=None)
    assert first.due == ()
    second = _plan(
        keys,
        ledger=_ledger(first.ledger.unreferenced_since, "prev"),
        now=T0 + CLEANUP_GRACE,
        max_delete_fraction=0.1,
    )
    assert second.refusal is not None
    assert "20 of 20" in second.refusal


def test_the_grace_matches_the_service_staleness_threshold():
    # An instance serving a pair superseded before the grace already warns that its data is
    # stale (ADR 0015); change both together.
    assert dt.timedelta(hours=STALE_AFTER_HOURS) == CLEANUP_GRACE


def test_the_ledger_round_trips_through_json():
    ledger = _ledger({_key(SQ1, b"a"): T0, _key(SQ2, b"b"): T0 - CLEANUP_GRACE}, "abc")

    assert CleanupLedger.from_json(ledger.to_json()) == ledger


# clean_photos over the index bucket and R2, across refreshes


class _Refreshes:
    """Publishes pairs to a local index bucket the way refresh.yml does, then cleans up."""

    def __init__(self, tmp_path: Path, r2: FakePhotoBucketClient) -> None:
        self.tmp_path = tmp_path
        self.gcs = LocalDirectoryBucketClient(tmp_path / "gcs")
        self.r2 = r2
        self.live: Path | None = None
        self._count = 0

    def pair(self, photos: dict[int, bytes]) -> Path:
        self._count += 1
        directory = self.tmp_path / f"pair{self._count}"
        build_fixture_index(directory, built_at=T0 + dt.timedelta(minutes=self._count))
        urls, digests = {}, {}
        for sq, content in photos.items():
            key, digest = photo_key("AC", sq, content)
            urls[sq], digests[sq] = f"{DOMAIN}/{key}", digest
        if urls:
            apply_photo_urls(directory, urls, digests)
        return directory

    def publish(self, directory: Path) -> Path:
        previous = self.live if self.live is not None else self.tmp_path / "nothing"
        publish(directory / INDEX_FILE_NAME, directory / MANIFEST_FILE_NAME, self.gcs)
        self.live = directory
        return previous

    def refresh(self, directory: Path, at: dt.datetime, **kw):
        previous = self.publish(directory)
        return clean_photos(
            directory,
            previous,
            self.r2,
            self.gcs,
            public_domain=DOMAIN,
            now=lambda: at,
            max_delete_fraction=kw.pop("max_delete_fraction", 1.0),
            **kw,
        )


def _r2(*photos: tuple[int, bytes]) -> FakePhotoBucketClient:
    return FakePhotoBucketClient(
        {photo_key("AC", sq, content)[0]: (content, "") for sq, content in photos}
    )


def test_a_superseded_photo_outlives_the_previous_pair_by_the_whole_grace(tmp_path: Path):
    # stray is a partial upload no index ever referenced; the mirror uploads each new photo
    # in the run that publishes it.
    r2 = _r2((SQ1, b"old"), (SQ1, b"new"), (SQ2, b"b"), (SQ5, b"x"))
    old, stray = _key(SQ1, b"old"), _key(SQ5, b"x")
    runs = _Refreshes(tmp_path, r2)
    runs.publish(runs.pair({SQ1: b"old"}))

    # The TSE changed SQ1's photo: the previous pair still references the old one.
    first = runs.refresh(runs.pair({SQ1: b"new", SQ2: b"b"}), T0)
    assert first.deleted == ()
    assert first.plan.ledger.unreferenced_since == {stray: T0}
    r2.objects[_key(SQ3, b"c")] = (b"c", "")
    second = runs.refresh(runs.pair({SQ1: b"new", SQ2: b"b", SQ3: b"c"}), T0 + dt.timedelta(1))
    assert second.plan.chain_intact
    assert second.deleted == ()
    assert second.plan.ledger.unreferenced_since == {old: T0 + dt.timedelta(1), stray: T0}
    r2.objects[_key(SQ4, b"d")] = (b"d", "")
    third = runs.refresh(
        runs.pair({SQ1: b"new", SQ2: b"b", SQ3: b"c", SQ4: b"d"}),
        T0 + CLEANUP_GRACE + dt.timedelta(hours=1),
    )

    assert third.deleted == (stray,)
    assert stray not in r2.objects
    assert old in r2.objects
    assert read_ledger(runs.gcs) == third.plan.ledger


def test_a_refresh_that_published_without_cleaning_up_restarts_the_clocks(tmp_path: Path):
    r2 = _r2((SQ1, b"new"), (SQ2, b"b"), (SQ3, b"c"), (SQ4, b"d"), (SQ5, b"x"))
    runs = _Refreshes(tmp_path, r2)
    # Each pair references a different set of photos, so the four indexes never share a
    # SHA-256 (the build alone is not guaranteed to produce different bytes for the same
    # content, and the ledger tells pairs apart by that digest).
    runs.publish(runs.pair({SQ1: b"new"}))
    runs.refresh(runs.pair({SQ1: b"new", SQ2: b"b"}), T0)
    runs.publish(runs.pair({SQ1: b"new", SQ2: b"b", SQ3: b"c"}))  # a photo stage failed

    result = runs.refresh(
        runs.pair({SQ1: b"new", SQ2: b"b", SQ3: b"c", SQ4: b"d"}), T0 + 2 * CLEANUP_GRACE
    )

    assert not result.plan.chain_intact
    assert result.deleted == ()
    assert _key(SQ5, b"x") in r2.objects


def test_a_dry_run_deletes_nothing_but_keeps_the_clock_running(tmp_path: Path):
    r2 = _r2((SQ1, b"new"), (SQ5, b"x"))
    runs = _Refreshes(tmp_path, r2)
    runs.publish(runs.pair({SQ1: b"new"}))
    runs.refresh(runs.pair({SQ1: b"new"}), T0, dry_run=True)

    dry = runs.refresh(runs.pair({SQ1: b"new"}), T0 + CLEANUP_GRACE, dry_run=True)
    assert dry.plan.due == (_key(SQ5, b"x"),)
    assert dry.deleted == ()
    assert _key(SQ5, b"x") in r2.objects

    live = runs.refresh(runs.pair({SQ1: b"new"}), T0 + CLEANUP_GRACE + dt.timedelta(hours=4))
    assert live.deleted == (_key(SQ5, b"x"),)


def test_a_refused_bound_keeps_the_ledger_and_deletes_nothing(tmp_path: Path):
    r2 = _r2((SQ1, b"new"), (SQ5, b"x"))
    stray = _key(SQ5, b"x")
    runs = _Refreshes(tmp_path, r2)
    runs.publish(runs.pair({SQ1: b"new"}))
    runs.refresh(runs.pair({SQ1: b"new"}), T0)
    refused_at = T0 + CLEANUP_GRACE

    with pytest.raises(PhotoCleanupError, match="above the bound"):
        runs.refresh(runs.pair({SQ1: b"new"}), refused_at, max_delete_fraction=0.1)
    kept = read_ledger(runs.gcs)
    assert kept is not None
    assert kept.unreferenced_since == {stray: T0}
    assert set(r2.objects) == {_key(SQ1, b"new"), stray}

    next_run = runs.refresh(runs.pair({SQ1: b"new"}), refused_at + dt.timedelta(hours=4))
    assert next_run.plan.chain_intact
    assert next_run.deleted == (stray,)


def test_a_dry_run_over_the_bound_is_refused_too(tmp_path: Path):
    r2 = _r2((SQ1, b"new"), (SQ5, b"x"))
    runs = _Refreshes(tmp_path, r2)
    runs.publish(runs.pair({SQ1: b"new"}))
    runs.refresh(runs.pair({SQ1: b"new"}), T0, dry_run=True)

    with pytest.raises(PhotoCleanupError, match="above the bound"):
        runs.refresh(
            runs.pair({SQ1: b"new"}), T0 + CLEANUP_GRACE, dry_run=True, max_delete_fraction=0.1
        )


def test_a_live_manifest_other_than_the_published_pair_is_refused(tmp_path: Path):
    r2 = _r2((SQ1, b"new"), (SQ5, b"x"))
    runs = _Refreshes(tmp_path, r2)
    previous = runs.pair({SQ1: b"new"})
    # Different photo URLs, so the two indexes never share a SHA-256 (the build alone is not
    # guaranteed to produce different bytes for the same content).
    published = runs.pair({SQ1: b"new", SQ2: b"b"})
    runs.publish(previous)

    with pytest.raises(PhotoCleanupError, match="live manifest"):
        clean_photos(published, previous, r2, runs.gcs, public_domain=DOMAIN, now=lambda: T0)
    assert not (tmp_path / "gcs" / LEDGER_OBJECT).exists()


def test_a_previous_pair_that_fails_verification_is_refused(tmp_path: Path):
    r2 = _r2((SQ1, b"new"))
    runs = _Refreshes(tmp_path, r2)
    previous = runs.pair({SQ1: b"new"})
    runs.publish(previous)
    published = runs.pair({SQ1: b"new"})
    runs.publish(published)
    (previous / INDEX_FILE_NAME).write_bytes(b"tampered")

    with pytest.raises(PublishError, match="does not match manifest"):
        clean_photos(published, previous, r2, runs.gcs, public_domain=DOMAIN, now=lambda: T0)
    assert not (tmp_path / "gcs" / LEDGER_OBJECT).exists()


def test_a_published_pair_on_another_public_domain_is_refused(tmp_path: Path):
    r2 = _r2((SQ1, b"new"))
    runs = _Refreshes(tmp_path, r2)
    runs.publish(runs.pair({SQ1: b"new"}))
    published = runs.pair({SQ1: b"new"})
    previous = runs.publish(published)

    with pytest.raises(PhotoCleanupError, match="photo chain"):
        clean_photos(published, previous, r2, runs.gcs, public_domain="https://other.example.org")


# The CLI stage


def _clean_args(tmp_path: Path, published: Path, previous: Path, *extra: str) -> list[str]:
    return [
        "clean-photos",
        "--index-dir",
        str(published),
        "--previous-index-dir",
        str(previous),
        "--public-domain",
        DOMAIN,
        "--r2-endpoint",
        "https://example.invalid",
        "--r2-bucket",
        "bucket",
        "--r2-access-key-id",
        "id",
        "--r2-secret-access-key",
        "secret",
        "--local-bucket",
        str(tmp_path / "gcs"),
        *extra,
    ]


def test_cli_dry_run_reports_the_counts_and_deletes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    r2 = _r2((SQ1, b"old"), (SQ1, b"new"), (SQ5, b"x"))
    monkeypatch.setattr(cli, "R2BucketClient", lambda **_: r2)
    runs = _Refreshes(tmp_path, r2)
    runs.publish(runs.pair({SQ1: b"old"}))
    published = runs.pair({SQ1: b"new"})
    previous = runs.publish(published)

    assert cli.main(_clean_args(tmp_path, published, previous, "--dry-run")) == 0
    out = capsys.readouterr().out
    assert "clean-photos (dry run): 3 photo objects, 1 referenced by neither" in out
    assert "would delete 0; deleted 0" in out
    assert len(r2.objects) == 3
    assert verify_index_pair(published)


def test_cli_refusal_exits_non_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    r2 = _r2((SQ5, b"x"))
    monkeypatch.setattr(cli, "R2BucketClient", lambda **_: r2)
    runs = _Refreshes(tmp_path, r2)
    runs.publish(runs.pair({}))
    published = runs.pair({SQ1: b"new"})
    previous = runs.publish(published)

    assert cli.main(_clean_args(tmp_path, published, previous)) == 1
    assert "clean-photos (delete) refused" in capsys.readouterr().err


def test_cli_reports_the_counts_of_a_bound_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    r2 = _r2((SQ1, b"new"), (SQ5, b"x"))
    monkeypatch.setattr(cli, "R2BucketClient", lambda **_: r2)
    runs = _Refreshes(tmp_path, r2)
    runs.publish(runs.pair({SQ1: b"new"}))
    runs.refresh(runs.pair({SQ1: b"new"}), T0 - 10 * CLEANUP_GRACE)
    published = runs.pair({SQ1: b"new"})
    previous = runs.publish(published)

    code = cli.main(_clean_args(tmp_path, published, previous, "--max-delete-fraction", "0.1"))

    assert code == 1
    assert "1 of 2 photo objects would be deleted, above the bound of 10%" in (
        capsys.readouterr().err
    )


def test_cli_rejects_a_bound_outside_zero_and_one(tmp_path: Path):
    with pytest.raises(SystemExit):
        cli.main(_clean_args(tmp_path, tmp_path, tmp_path, "--max-delete-fraction", "1.5"))


# The refresh wiring


def _steps(workflow: str, job: str) -> list[dict]:
    return yaml.safe_load(Path(f".github/workflows/{workflow}").read_text())["jobs"][job]["steps"]


def _cleanup_step() -> dict:
    return next(
        step for step in _steps("refresh.yml", "refresh") if step.get("id") == "clean_photos"
    )


_TERM = re.compile(r"^(env|steps)\.(\w+)(?:\.outcome)? (==|!=) '([^']*)'$")


def _condition_holds(condition: str, env: dict[str, str], outcomes: dict[str, str]) -> bool:
    """Evaluate the `&&`/`==`/`!=` subset of a step `if`; anything else is unsupported.

    A condition without a status function is gated by an implicit ``success()``, which the
    caller models by only evaluating it when no earlier step failed.
    """
    holds = True
    for term in condition.split(" && "):
        match = _TERM.match(term.strip())
        assert match, f"unsupported term in the step condition: {term!r}"
        scope, name, operator, literal = match.groups()
        actual = env.get(name, "") if scope == "env" else outcomes[name]
        holds = holds and ((actual == literal) == (operator == "=="))
    return holds


_ALL_GOOD_ENV = {"MIRROR_PHOTOS": "true", "PHOTO_STATUS_FAILED": "false"}
_PHOTO_STEPS = ("fetch_photos", "current_index", "retain_photos", "mirror_photos")


def _cleanup_runs(env: dict[str, str], outcomes: dict[str, str]) -> bool:
    return _condition_holds(_cleanup_step()["if"], env, outcomes)


def test_refresh_cleans_up_right_after_publish_with_no_failure_tolerance():
    steps = _steps("refresh.yml", "refresh")
    ids = [step.get("id") for step in steps]

    assert ids.index("clean_photos") == ids.index("publish") + 1
    assert "continue-on-error" not in _cleanup_step()


def test_refresh_cleans_up_only_when_every_photo_stage_succeeded():
    every_success = dict.fromkeys(_PHOTO_STEPS, "success")

    assert _cleanup_runs(_ALL_GOOD_ENV, every_success)
    for name in _PHOTO_STEPS:
        for outcome in ("failure", "skipped", "cancelled"):
            assert not _cleanup_runs(_ALL_GOOD_ENV, every_success | {name: outcome})
    assert not _cleanup_runs(_ALL_GOOD_ENV | {"MIRROR_PHOTOS": "false"}, every_success)
    assert not _cleanup_runs(_ALL_GOOD_ENV | {"MIRROR_PHOTOS": ""}, every_success)
    assert not _cleanup_runs(_ALL_GOOD_ENV | {"PHOTO_STATUS_FAILED": "true"}, every_success)


def _pipeline_invocations(run: str) -> list[tuple[str, list[str]]]:
    tokens = shlex.split(run.replace("\\\n", " "), comments=True)
    starts = [i for i, token in enumerate(tokens) if token == "br_elections_mcp.pipeline"]
    return [
        (tokens[i + 1], tokens[i + 2 : end])
        for i, end in zip(starts, [*starts[1:], len(tokens)], strict=False)
    ]


def test_the_full_photo_load_mirrors_with_retention_and_never_cleans_up():
    invocations = [
        invocation
        for step in _steps("photo-full-load.yml", "load")
        for invocation in _pipeline_invocations(step.get("run", ""))
    ]
    stages = [stage for stage, _ in invocations]

    assert "mirror-photos" in stages
    assert "clean-photos" not in stages
    for stage, args in invocations:
        if stage == "mirror-photos":
            assert "--retain-old-photos" in args


def _run_cleanup_step(
    tmp_path: Path, mode: str, *, stub: str
) -> tuple[subprocess.CompletedProcess, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    timeout = bin_dir / "timeout"
    timeout.write_text('#!/bin/bash\nwhile [ "$1" != uv ]; do shift; done\nshift\n"$@"\n')
    timeout.chmod(0o755)
    run = bin_dir / "run"
    run.write_text(f'#!/bin/bash\nprintf "%s\\n" "$@" > "$ARGS_FILE"\n{stub}\n')
    run.chmod(0o755)
    args_file = tmp_path / "args"
    env = os.environ | {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "ARGS_FILE": str(args_file),
        "WORK": str(tmp_path),
        "PHOTO_INDEX_DIR": str(tmp_path / "mirrored"),
        "PHOTO_CLEANUP_MODE": mode,
        "INDEX_BUCKET": "index-bucket",
        "INDEX_BUCKET_PREFIX": "",
        "R2_ENDPOINT": "https://example.invalid",
        "R2_BUCKET": "bucket",
        "R2_ACCESS_KEY_ID": "id",
        "R2_SECRET_ACCESS_KEY": "secret",
        "R2_PUBLIC_DOMAIN": DOMAIN,
    }
    result = subprocess.run(
        ["bash", "-e", "-c", _cleanup_step()["run"]], env=env, capture_output=True, text=True
    )
    return result, args_file


@pytest.mark.parametrize(("mode", "dry_run"), [("", True), ("dry-run", True), ("delete", False)])
def test_refresh_cleanup_is_a_dry_run_unless_the_variable_says_delete(
    tmp_path: Path, mode: str, dry_run: bool
):
    result, args_file = _run_cleanup_step(tmp_path, mode, stub="echo report")

    assert result.returncode == 0, result.stderr
    args = args_file.read_text().splitlines()
    assert args[:4] == ["python", "-m", "br_elections_mcp.pipeline", "clean-photos"]
    assert ("--dry-run" in args) is dry_run
    assert args[args.index("--previous-index-dir") + 1] == str(tmp_path / "previous")
    assert args[args.index("--index-dir") + 1] == str(tmp_path / "mirrored")
    assert (tmp_path / "clean-photos.log").read_text() == "report\n"


def test_a_refused_cleanup_fails_the_step_and_leaves_its_message_for_the_summary(tmp_path: Path):
    message = "clean-photos (delete) refused: 3 of 10 photo objects would be deleted"

    result, _ = _run_cleanup_step(tmp_path, "delete", stub=f'echo "{message}" >&2; exit 1')

    assert result.returncode != 0
    assert (tmp_path / "clean-photos.log").read_text() == f"{message}\n"
