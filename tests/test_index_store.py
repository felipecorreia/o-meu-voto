from pathlib import Path

import pytest

from br_elections_mcp.core import IndexSourceUnavailable
from br_elections_mcp.index_schema import INDEX_FILE_NAME, MANIFEST_FILE_NAME, manifest_version
from br_elections_mcp.index_store import LocalDirectoryIndexSource


def test_local_directory_source_delivers_path_manifest_and_version(acre_index_dir: Path):
    version = LocalDirectoryIndexSource(acre_index_dir).current()
    assert version.path == acre_index_dir / INDEX_FILE_NAME
    assert version.manifest.counts["polling_sections"] == 6
    assert version.version == manifest_version((acre_index_dir / MANIFEST_FILE_NAME).read_bytes())


def test_missing_directory_is_unavailable(tmp_path: Path):
    with pytest.raises(IndexSourceUnavailable):
        LocalDirectoryIndexSource(tmp_path / "nope").current()


def test_invalid_manifest_is_unavailable(tmp_path: Path):
    (tmp_path / MANIFEST_FILE_NAME).write_text("{}")
    (tmp_path / INDEX_FILE_NAME).write_bytes(b"")
    with pytest.raises(IndexSourceUnavailable, match="invalid manifest"):
        LocalDirectoryIndexSource(tmp_path).current()
