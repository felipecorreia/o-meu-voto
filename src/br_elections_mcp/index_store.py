"""Adapters of the ``IndexSource`` port.

``LocalDirectoryIndexSource`` reads the index and its manifest from a directory: tests and
local development. ``GcsIndexSource`` is the production adapter and the only service code
that talks to GCS; it keeps a local cache directory with one index file per version.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from br_elections_mcp.core.index_source import IndexSourceUnavailable, IndexVersion
from br_elections_mcp.index_schema import (
    INDEX_FILE_NAME,
    MANIFEST_FILE_NAME,
    Manifest,
    manifest_version,
)

log = logging.getLogger(__name__)

INDEX_SUFFIX = Path(INDEX_FILE_NAME).suffix
_CACHED_INDEX_PREFIX = f"{Path(INDEX_FILE_NAME).stem}-"
_TMP_SUFFIX = ".tmp"


def _cached_index_name(version: str) -> str:
    return f"{_CACHED_INDEX_PREFIX}{version}{INDEX_SUFFIX}"


class LocalDirectoryIndexSource:
    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def current(self) -> IndexVersion:
        manifest_path = self._directory / MANIFEST_FILE_NAME
        index_path = self._directory / INDEX_FILE_NAME
        try:
            raw = manifest_path.read_bytes()
        except OSError as exc:
            raise IndexSourceUnavailable(f"cannot read {manifest_path}: {exc}") from exc
        try:
            manifest = Manifest.model_validate_json(raw)
        except ValidationError as exc:
            raise IndexSourceUnavailable(f"invalid manifest {manifest_path}: {exc}") from exc
        if not index_path.is_file():
            raise IndexSourceUnavailable(f"index file not found: {index_path}")
        return IndexVersion(path=index_path, manifest=manifest, version=manifest_version(raw))


class GcsError(RuntimeError):
    """Raised by a ``GcsBucketClient`` when a blob cannot be read: bucket down, missing
    object, or an authentication/transport failure."""


class GcsBucketClient(Protocol):
    """What ``GcsIndexSource`` needs from a GCS client: read one blob's bytes, stream one
    blob to a file. Narrow by design, so tests inject a fake in-memory implementation
    instead of the real ``google-cloud-storage`` client and its credentials.
    """

    def download_bytes(self, blob_name: str) -> bytes:
        """Raises ``GcsError`` when the blob is missing or the bucket cannot be reached."""
        ...

    def download_to_file(self, blob_name: str, destination: Path) -> None:
        """Raises ``GcsError`` when the blob is missing or the download is interrupted.

        Leaves nothing at ``destination`` on failure.
        """
        ...


class _CloudStorageClient:
    """Production ``GcsBucketClient``: the official ``google-cloud-storage`` client.

    Resolves Application Default Credentials only on the first call, not on construction, so
    building a ``GcsIndexSource`` (composition root, configuration tests) never requires a
    real credential; only an actual ``current()`` call does.
    """

    def __init__(self, bucket_name: str) -> None:
        self._bucket_name = bucket_name
        self._bucket: Any | None = None

    def _bucket_handle(self) -> Any:
        if self._bucket is None:
            from google.cloud import storage

            self._bucket = storage.Client().bucket(self._bucket_name)
        return self._bucket

    def download_bytes(self, blob_name: str) -> bytes:
        from google.api_core.exceptions import GoogleAPIError

        try:
            return self._bucket_handle().blob(blob_name).download_as_bytes()
        except GoogleAPIError as exc:
            raise GcsError(f"{blob_name}: {exc}") from exc

    def download_to_file(self, blob_name: str, destination: Path) -> None:
        from google.api_core.exceptions import GoogleAPIError

        try:
            self._bucket_handle().blob(blob_name).download_to_filename(str(destination))
        except GoogleAPIError as exc:
            raise GcsError(f"{blob_name}: {exc}") from exc


class GcsIndexSource:
    """Downloads ``manifest.json`` from ``gs://bucket/prefix`` on every ``current()``,
    downloading ``index.duckdb`` only when the version is not in the cache yet.

    Each version lives at its own path, ``cache_dir/index-<version>.duckdb``. DuckDB keeps one
    database instance per path, so a new version renamed over the path of the open one would
    be read from the old, unlinked file while the manifest already named the new one: the
    open version must never share a path with the next. The file is written under a
    temporary name and renamed, so a download interrupted partway never leaves a partial
    version under its final name; the cached ``manifest.json`` is only overwritten once that
    rename succeeded, so it only ever names a version whose index is on disk. A version's
    file exists if and only if it is complete, which is what lets ``current()`` skip the
    download. After the download every other copy is deleted: the version still open keeps
    its inode until its last cursor is released, so the cache holds about two copies at the
    peak of a swap and one at rest. Any failure - bucket unreachable, missing blob, invalid
    manifest, interrupted download - raises ``IndexSourceUnavailable`` without touching a
    valid cache, so the caller keeps serving the version it already has open (codebase-design
    3.1).
    """

    def __init__(
        self,
        bucket: str,
        prefix: str,
        cache_dir: Path,
        *,
        client: GcsBucketClient | None = None,
    ) -> None:
        self._prefix = prefix.strip("/")
        self._cache_dir = cache_dir
        self._client = client or _CloudStorageClient(bucket)

    def _blob_name(self, filename: str) -> str:
        return f"{self._prefix}/{filename}" if self._prefix else filename

    def current(self) -> IndexVersion:
        try:
            raw = self._client.download_bytes(self._blob_name(MANIFEST_FILE_NAME))
        except GcsError as exc:
            raise IndexSourceUnavailable(f"cannot download manifest: {exc}") from exc
        try:
            manifest = Manifest.model_validate_json(raw)
        except ValidationError as exc:
            raise IndexSourceUnavailable(f"invalid manifest from bucket: {exc}") from exc

        self._cache_dir.mkdir(parents=True, exist_ok=True)
        version = manifest_version(raw)
        index_path = self._cache_dir / _cached_index_name(version)
        if not index_path.is_file():
            tmp_index_path = index_path.with_name(index_path.name + _TMP_SUFFIX)
            try:
                self._client.download_to_file(self._blob_name(INDEX_FILE_NAME), tmp_index_path)
            except GcsError as exc:
                tmp_index_path.unlink(missing_ok=True)
                raise IndexSourceUnavailable(f"cannot download index: {exc}") from exc
            except BaseException:
                tmp_index_path.unlink(missing_ok=True)
                raise
            tmp_index_path.replace(index_path)
        self._write_cached_manifest(raw)
        self._prune_except(index_path)
        return IndexVersion(path=index_path, manifest=manifest, version=version)

    def _write_cached_manifest(self, raw: bytes) -> None:
        cached = self._cache_dir / MANIFEST_FILE_NAME
        tmp = cached.with_name(cached.name + _TMP_SUFFIX)
        tmp.write_bytes(raw)
        tmp.replace(cached)

    def _prune_except(self, keep: Path) -> None:
        """Delete every other cached index copy, and any leftover temporary file."""
        for stale in (
            *self._cache_dir.glob(f"{_CACHED_INDEX_PREFIX}*{INDEX_SUFFIX}"),
            *self._cache_dir.glob(f"{_CACHED_INDEX_PREFIX}*{INDEX_SUFFIX}{_TMP_SUFFIX}"),
            self._cache_dir / INDEX_FILE_NAME,
            self._cache_dir / (INDEX_FILE_NAME + _TMP_SUFFIX),
        ):
            if stale != keep:
                try:
                    stale.unlink(missing_ok=True)
                except OSError:
                    log.warning("cannot delete the stale cached index %s", stale, exc_info=True)
