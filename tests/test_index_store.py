import ast
from pathlib import Path

import pytest

from br_elections_mcp.core import IndexSourceUnavailable
from br_elections_mcp.index_schema import INDEX_FILE_NAME, MANIFEST_FILE_NAME, manifest_version
from br_elections_mcp.index_store import GcsError, GcsIndexSource, LocalDirectoryIndexSource
from tests.conftest import build_fixture_index

REPO = Path(__file__).resolve().parents[1]
CORE_DIR = REPO / "src" / "br_elections_mcp" / "core"
# Any of these, or a submodule of one, is a network or index-store dependency the core must
# never carry (codebase-design 3.1, ADR 0001).
FORBIDDEN_CORE_IMPORTS = (
    "br_elections_mcp.index_store",
    "httpx",
    "requests",
    "curl_cffi",
    "urllib.request",
    "aiohttp",
    "google.cloud",
    "google.auth",
)


def test_local_directory_source_delivers_path_manifest_and_version(acre_index_dir: Path):
    version = LocalDirectoryIndexSource(acre_index_dir).current()
    assert version.path == acre_index_dir / INDEX_FILE_NAME
    assert version.manifest.counts["polling_sections"] == 20
    assert version.version == manifest_version((acre_index_dir / MANIFEST_FILE_NAME).read_bytes())


def test_missing_directory_is_unavailable(tmp_path: Path):
    with pytest.raises(IndexSourceUnavailable):
        LocalDirectoryIndexSource(tmp_path / "nope").current()


def test_invalid_manifest_is_unavailable(tmp_path: Path):
    (tmp_path / MANIFEST_FILE_NAME).write_text("{}")
    (tmp_path / INDEX_FILE_NAME).write_bytes(b"")
    with pytest.raises(IndexSourceUnavailable, match="invalid manifest"):
        LocalDirectoryIndexSource(tmp_path).current()


# GcsIndexSource (ticket #16), a fake in-memory GCS client: no test touches the network.


class _FakeGcsBucketClient:
    def __init__(self, blobs: dict[str, bytes], *, fail: frozenset[str] = frozenset()) -> None:
        self.blobs = dict(blobs)
        self.fail = fail
        self.download_to_file_calls: list[str] = []

    def download_bytes(self, blob_name: str) -> bytes:
        if blob_name in self.fail:
            raise GcsError(f"{blob_name}: unavailable")
        if blob_name not in self.blobs:
            raise GcsError(f"{blob_name}: not found")
        return self.blobs[blob_name]

    def download_to_file(self, blob_name: str, destination: Path) -> None:
        self.download_to_file_calls.append(blob_name)
        if blob_name in self.fail:
            raise GcsError(f"{blob_name}: interrupted")
        if blob_name not in self.blobs:
            raise GcsError(f"{blob_name}: not found")
        destination.write_bytes(self.blobs[blob_name])


GcsVersions = tuple[dict[str, bytes], dict[str, bytes]]


@pytest.fixture(scope="module")
def gcs_versions(tmp_path_factory: pytest.TempPathFactory) -> GcsVersions:
    """Two genuinely different published versions, built like the pipeline builds them."""
    import datetime as dt

    v1_dir = tmp_path_factory.mktemp("gcs-v1")
    v2_dir = tmp_path_factory.mktemp("gcs-v2")
    build_fixture_index(v1_dir, built_at=dt.datetime(2026, 9, 18, 9, 0, tzinfo=dt.UTC))
    build_fixture_index(v2_dir, built_at=dt.datetime(2026, 9, 19, 9, 0, tzinfo=dt.UTC))

    def blobs_of(directory: Path) -> dict[str, bytes]:
        return {
            MANIFEST_FILE_NAME: (directory / MANIFEST_FILE_NAME).read_bytes(),
            INDEX_FILE_NAME: (directory / INDEX_FILE_NAME).read_bytes(),
        }

    v1 = blobs_of(v1_dir)
    v2 = blobs_of(v2_dir)
    assert v1[MANIFEST_FILE_NAME] != v2[MANIFEST_FILE_NAME]
    return v1, v2


def _prefixed(blobs: dict[str, bytes], prefix: str) -> dict[str, bytes]:
    return {f"{prefix}/{name}": content for name, content in blobs.items()}


def test_same_manifest_no_download(tmp_path: Path, gcs_versions: GcsVersions):
    v1, _ = gcs_versions
    client = _FakeGcsBucketClient(_prefixed(v1, "idx"))
    source = GcsIndexSource("bucket", "idx", tmp_path / "cache", client=client)

    first = source.current()
    assert client.download_to_file_calls == ["idx/index.duckdb"]

    second = source.current()
    assert client.download_to_file_calls == ["idx/index.duckdb"]  # unchanged: no second download
    assert second.version == first.version == manifest_version(v1[MANIFEST_FILE_NAME])


def test_new_manifest_downloads_and_renames(tmp_path: Path, gcs_versions: GcsVersions):
    v1, v2 = gcs_versions
    cache_dir = tmp_path / "cache"
    client = _FakeGcsBucketClient(_prefixed(v1, "idx"))
    source = GcsIndexSource("bucket", "idx", cache_dir, client=client)
    source.current()

    client.blobs = _prefixed(v2, "idx")
    version = source.current()

    assert client.download_to_file_calls == ["idx/index.duckdb", "idx/index.duckdb"]
    assert version.version == manifest_version(v2[MANIFEST_FILE_NAME])
    assert (cache_dir / INDEX_FILE_NAME).read_bytes() == v2[INDEX_FILE_NAME]
    assert (cache_dir / MANIFEST_FILE_NAME).read_bytes() == v2[MANIFEST_FILE_NAME]
    assert not list(cache_dir.glob("*.tmp"))


def test_download_interrupted_previous_version_still_served(
    tmp_path: Path, gcs_versions: GcsVersions
):
    v1, v2 = gcs_versions
    cache_dir = tmp_path / "cache"
    client = _FakeGcsBucketClient(_prefixed(v1, "idx"))
    source = GcsIndexSource("bucket", "idx", cache_dir, client=client)
    source.current()

    client.blobs = _prefixed(v2, "idx")
    client.fail = frozenset({"idx/index.duckdb"})
    with pytest.raises(IndexSourceUnavailable):
        source.current()

    assert not list(cache_dir.glob("*.tmp"))
    previous = LocalDirectoryIndexSource(cache_dir).current()
    assert previous.version == manifest_version(v1[MANIFEST_FILE_NAME])
    assert (cache_dir / INDEX_FILE_NAME).read_bytes() == v1[INDEX_FILE_NAME]


def test_bucket_down_for_manifest_is_unavailable(tmp_path: Path):
    client = _FakeGcsBucketClient({}, fail=frozenset({"idx/manifest.json"}))
    source = GcsIndexSource("bucket", "idx", tmp_path / "cache", client=client)
    with pytest.raises(IndexSourceUnavailable, match="cannot download manifest"):
        source.current()


def test_invalid_manifest_from_bucket_is_unavailable(tmp_path: Path):
    client = _FakeGcsBucketClient({"idx/manifest.json": b"{}"})
    source = GcsIndexSource("bucket", "idx", tmp_path / "cache", client=client)
    with pytest.raises(IndexSourceUnavailable, match="invalid manifest"):
        source.current()


def test_prefix_is_stripped_of_leading_and_trailing_slashes(
    tmp_path: Path, gcs_versions: GcsVersions
):
    v1, _ = gcs_versions
    client = _FakeGcsBucketClient(_prefixed(v1, "idx"))
    source = GcsIndexSource("bucket", "/idx/", tmp_path / "cache", client=client)
    source.current()
    assert client.download_to_file_calls == ["idx/index.duckdb"]


# Import boundary (ticket #16): the core has no network, verifiable by import.


def _imported_module_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return modules


def test_core_package_imports_neither_index_store_nor_any_http_client():
    offenders: dict[str, set[str]] = {}
    for path in CORE_DIR.rglob("*.py"):
        hits = {
            module
            for module in _imported_module_names(path)
            if any(
                module == forbidden or module.startswith(forbidden + ".")
                for forbidden in FORBIDDEN_CORE_IMPORTS
            )
        }
        if hits:
            offenders[str(path.relative_to(REPO))] = hits
    assert not offenders
