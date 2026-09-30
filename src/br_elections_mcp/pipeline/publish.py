"""Pipeline stage ``publish``: ``index.duckdb`` and ``manifest.json`` in, the bucket out.

The stage takes exactly two files, the pair ``build`` wrote and ``validate``
approved, and sends them to the index bucket through the ``BucketClient``
port. Nothing else ever reaches the bucket: the raw ZIPs and CSVs stay in the
runner's temporary directory (ADR 0004). Layout under ``prefix``::

    versions/{version}/index.duckdb    kept forever, one directory per published index
    versions/{version}/manifest.json
    index.duckdb                       the current pair, what GcsIndexSource reads
    manifest.json                      written last: the pointer that makes a version current

``version`` is the UTC build time plus the first twelve hex digits of the
index SHA-256, so the directory listing sorts by build and names its index.
Rolling back is copying an older ``versions/{version}/`` pair over the current
pair, index first and manifest last, the same order this stage writes in: a
reader that only re-downloads the index when the manifest changes never sees a
manifest without its index.

The manifest is published as ``build`` wrote it. Its ``election_year`` and
``election_dates`` are the "election of the index" of codebase-design 3.4 and
5: filled only when every election-bearing dataset is an election file of the
same year, null when any of them is the monthly ``ATUAL`` snapshot. ``build``
derives them from the ``DT_ELEICAO`` lines that ``validate`` checks against
``data/elections.yaml`` before this stage runs, so this stage only refuses to
publish a manifest whose ``index_sha256`` does not match the index next to it.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from br_elections_mcp.index_schema import (
    INDEX_FILE_NAME,
    MANIFEST_FILE_NAME,
    Manifest,
    read_manifest,
)
from br_elections_mcp.pipeline.bucket import BucketClient

PUBLISH_RECORD_FILE = "publish.json"
PUBLISH_RECORD_VERSION = 1
VERSIONS_DIR = "versions"


class PublishError(RuntimeError):
    """The pair cannot be published; nothing was written to the bucket."""


@dataclass(frozen=True, slots=True)
class PublishRecord:
    """What one run of ``publish`` did, as written to ``publish.json`` next to the index."""

    published_at: str
    index_version: str
    index_sha256: str
    objects: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"version": PUBLISH_RECORD_VERSION, **asdict(self)}

    def write(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n")

    @classmethod
    def read(cls, path: Path) -> PublishRecord:
        raw = json.loads(path.read_text())
        if raw.get("version") != PUBLISH_RECORD_VERSION:
            raise ValueError(f"{path}: unsupported publish record version {raw.get('version')!r}")
        return cls(
            published_at=raw["published_at"],
            index_version=raw["index_version"],
            index_sha256=raw["index_sha256"],
            objects=tuple(raw["objects"]),
        )


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def version_id(manifest: Manifest) -> str:
    """``{build time, UTC}-{index SHA-256 prefix}``: sortable by build, names its index."""
    built_at = manifest.index_built_at.astimezone(dt.UTC)
    return f"{built_at:%Y%m%dT%H%M%SZ}-{manifest.index_sha256[:12]}"


def _normalize_prefix(prefix: str) -> str:
    prefix = prefix.strip("/")
    return f"{prefix}/" if prefix else ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def publish(
    index_path: Path,
    manifest_path: Path,
    client: BucketClient,
    *,
    prefix: str = "",
    now: Callable[[], dt.datetime] = _utcnow,
) -> PublishRecord:
    """Send the pair to the bucket, previous versions kept, current manifest last.

    Raises ``PublishError`` before any write when a file is missing, the
    manifest is invalid or its ``index_sha256`` is not the SHA-256 of
    ``index_path``. Writes ``publish.json`` next to the index and returns it.
    """
    for path in (index_path, manifest_path):
        if not path.is_file():
            raise PublishError(f"file not found: {path}")
    try:
        manifest = read_manifest(manifest_path)
    except ValueError as exc:
        raise PublishError(f"invalid manifest {manifest_path}: {exc}") from exc
    actual = _sha256(index_path)
    if actual != manifest.index_sha256:
        raise PublishError(
            f"the manifest's index SHA-256 ({manifest.index_sha256}) does not match "
            f"{index_path.name} ({actual}); refusing to publish a mismatched pair"
        )

    base = _normalize_prefix(prefix)
    version = version_id(manifest)
    versioned = f"{base}{VERSIONS_DIR}/{version}/"
    # Order matters: the versioned pair first, then the current index, and the current
    # manifest last, so a reader keyed on the manifest never points at a missing index.
    steps: tuple[tuple[Path, str], ...] = (
        (index_path, f"{versioned}{INDEX_FILE_NAME}"),
        (manifest_path, f"{versioned}{MANIFEST_FILE_NAME}"),
        (index_path, f"{base}{INDEX_FILE_NAME}"),
        (manifest_path, f"{base}{MANIFEST_FILE_NAME}"),
    )
    for local_path, object_name in steps:
        client.upload(local_path, object_name)

    record = PublishRecord(
        published_at=now().isoformat(),
        index_version=version,
        index_sha256=manifest.index_sha256,
        objects=tuple(object_name for _, object_name in steps),
    )
    record.write(index_path.parent / PUBLISH_RECORD_FILE)
    return record


def download_current_manifest(
    client: BucketClient, target: Path, *, prefix: str = ""
) -> Manifest | None:
    """The manifest currently published, saved to ``target``; None when nothing is published.

    ``validate`` takes it as the previous manifest of its count-stability gate.
    """
    if not client.download(f"{_normalize_prefix(prefix)}{MANIFEST_FILE_NAME}", target):
        return None
    return read_manifest(target)


def download_current_index(client: BucketClient, target_dir: Path, *, prefix: str = "") -> bool:
    """Download the immutable current version and verify it against its manifest.

    A refresh may publish concurrently with a manual photo load, so download from the
    version named by the manifest rather than the mutable current index object.
    """
    manifest_path = target_dir / MANIFEST_FILE_NAME
    manifest = download_current_manifest(client, manifest_path, prefix=prefix)
    if manifest is None:
        return False
    versioned = f"{_normalize_prefix(prefix)}{VERSIONS_DIR}/{version_id(manifest)}/"
    index_path = target_dir / INDEX_FILE_NAME
    if not client.download(f"{versioned}{INDEX_FILE_NAME}", index_path):
        raise PublishError(f"published index missing: {versioned}{INDEX_FILE_NAME}")
    verify_index_pair(target_dir)
    return True


def verify_index_pair(index_dir: Path) -> Manifest:
    """Require an index and manifest pair with matching SHA-256 before reuse."""
    manifest_path = index_dir / MANIFEST_FILE_NAME
    index_path = index_dir / INDEX_FILE_NAME
    try:
        manifest = read_manifest(manifest_path)
    except ValueError as exc:
        raise PublishError(f"invalid manifest {manifest_path}: {exc}") from exc
    if not index_path.is_file():
        raise PublishError(f"index not found: {index_path}")
    actual = _sha256(index_path)
    if actual != manifest.index_sha256:
        raise PublishError(
            f"published index SHA-256 {actual} does not match manifest {manifest.index_sha256}"
        )
    return manifest
