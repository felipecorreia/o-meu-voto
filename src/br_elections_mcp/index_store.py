"""Adapters of the ``IndexSource`` port.

``LocalDirectoryIndexSource`` reads the index and its manifest from a directory:
tests and local development. The GCS adapter, the only service code that talks
to the bucket, is added in its own change and lives here too.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from br_elections_mcp.core.index_source import IndexSourceUnavailable, IndexVersion
from br_elections_mcp.index_schema import (
    INDEX_FILE_NAME,
    MANIFEST_FILE_NAME,
    Manifest,
    manifest_version,
)


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
