import ast
from pathlib import Path

import pytest

from br_elections_mcp.core import IndexSourceUnavailable
from br_elections_mcp.index_schema import INDEX_FILE_NAME, MANIFEST_FILE_NAME, manifest_version
from br_elections_mcp.index_store import GcsIndexSource, LocalDirectoryIndexSource
from tests.conftest import FakeGcsBucketClient, build_fixture_index, published_blobs

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


GcsVersions = tuple[dict[str, bytes], dict[str, bytes]]


@pytest.fixture(scope="module")
def gcs_versions(tmp_path_factory: pytest.TempPathFactory) -> GcsVersions:
    """Two genuinely different published versions, built like the pipeline builds them."""
    import datetime as dt

    v1_dir = tmp_path_factory.mktemp("gcs-v1")
    v2_dir = tmp_path_factory.mktemp("gcs-v2")
    build_fixture_index(v1_dir, built_at=dt.datetime(2026, 9, 18, 9, 0, tzinfo=dt.UTC))
    build_fixture_index(v2_dir, built_at=dt.datetime(2026, 9, 19, 9, 0, tzinfo=dt.UTC))

    v1 = published_blobs(v1_dir)
    v2 = published_blobs(v2_dir)
    assert v1[MANIFEST_FILE_NAME] != v2[MANIFEST_FILE_NAME]
    return v1, v2


def _cached_index(cache_dir: Path, blobs: dict[str, bytes]) -> Path:
    """Where the source must keep the index of the version ``blobs`` publishes."""
    return cache_dir / f"index-{manifest_version(blobs[MANIFEST_FILE_NAME])}.duckdb"


def _prefixed(blobs: dict[str, bytes], prefix: str) -> dict[str, bytes]:
    return {f"{prefix}/{name}": content for name, content in blobs.items()}


def test_same_manifest_no_download(tmp_path: Path, gcs_versions: GcsVersions):
    v1, _ = gcs_versions
    client = FakeGcsBucketClient(_prefixed(v1, "idx"))
    source = GcsIndexSource("bucket", "idx", tmp_path / "cache", client=client)

    first = source.current()
    assert client.download_to_file_calls == ["idx/index.duckdb"]

    second = source.current()
    assert client.download_to_file_calls == ["idx/index.duckdb"]  # unchanged: no second download
    assert second.version == first.version == manifest_version(v1[MANIFEST_FILE_NAME])


def test_new_manifest_downloads_to_its_own_path_and_prunes_the_old_copy(
    tmp_path: Path, gcs_versions: GcsVersions
):
    v1, v2 = gcs_versions
    cache_dir = tmp_path / "cache"
    client = FakeGcsBucketClient(_prefixed(v1, "idx"))
    source = GcsIndexSource("bucket", "idx", cache_dir, client=client)
    first = source.current()

    client.blobs = _prefixed(v2, "idx")
    version = source.current()

    assert client.download_to_file_calls == ["idx/index.duckdb", "idx/index.duckdb"]
    assert version.version == manifest_version(v2[MANIFEST_FILE_NAME])
    assert version.path == _cached_index(cache_dir, v2)
    assert version.path != first.path
    assert version.path.read_bytes() == v2[INDEX_FILE_NAME]
    assert (cache_dir / MANIFEST_FILE_NAME).read_bytes() == v2[MANIFEST_FILE_NAME]
    assert sorted(path.name for path in cache_dir.iterdir()) == sorted(
        [MANIFEST_FILE_NAME, version.path.name]
    )


def test_download_interrupted_previous_version_still_served(
    tmp_path: Path, gcs_versions: GcsVersions
):
    v1, v2 = gcs_versions
    cache_dir = tmp_path / "cache"
    client = FakeGcsBucketClient(_prefixed(v1, "idx"))
    source = GcsIndexSource("bucket", "idx", cache_dir, client=client)
    source.current()

    client.blobs = _prefixed(v2, "idx")
    client.fail = frozenset({"idx/index.duckdb"})
    with pytest.raises(IndexSourceUnavailable):
        source.current()

    assert not list(cache_dir.glob("*.tmp"))
    assert _cached_index(cache_dir, v1).read_bytes() == v1[INDEX_FILE_NAME]
    assert not _cached_index(cache_dir, v2).exists()
    assert (cache_dir / MANIFEST_FILE_NAME).read_bytes() == v1[MANIFEST_FILE_NAME]

    client.fail = frozenset()
    assert source.current().version == manifest_version(v2[MANIFEST_FILE_NAME])


def test_a_crash_between_the_rename_and_the_manifest_does_not_download_again(
    tmp_path: Path, gcs_versions: GcsVersions
):
    v1, v2 = gcs_versions
    cache_dir = tmp_path / "cache"
    client = FakeGcsBucketClient(_prefixed(v1, "idx"))
    GcsIndexSource("bucket", "idx", cache_dir, client=client).current()
    # The process died after renaming v2's index into place, before writing its manifest.
    _cached_index(cache_dir, v2).write_bytes(v2[INDEX_FILE_NAME])

    client.blobs = _prefixed(v2, "idx")
    client.download_to_file_calls.clear()
    version = GcsIndexSource("bucket", "idx", cache_dir, client=client).current()

    assert client.download_to_file_calls == []
    assert version.path == _cached_index(cache_dir, v2)
    assert (cache_dir / MANIFEST_FILE_NAME).read_bytes() == v2[MANIFEST_FILE_NAME]
    assert not _cached_index(cache_dir, v1).exists()


def test_leftovers_of_an_earlier_layout_or_crash_are_pruned(
    tmp_path: Path, gcs_versions: GcsVersions
):
    v1, _ = gcs_versions
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    for leftover in ("index.duckdb", "index.duckdb.tmp", "index-deadbeef.duckdb.tmp"):
        (cache_dir / leftover).write_bytes(b"stale")
    client = FakeGcsBucketClient(_prefixed(v1, "idx"))

    version = GcsIndexSource("bucket", "idx", cache_dir, client=client).current()

    assert sorted(path.name for path in cache_dir.iterdir()) == sorted(
        [MANIFEST_FILE_NAME, version.path.name]
    )


def test_an_unprunable_copy_does_not_fail_the_check(
    tmp_path: Path, gcs_versions: GcsVersions, monkeypatch: pytest.MonkeyPatch
):
    v1, v2 = gcs_versions
    cache_dir = tmp_path / "cache"
    client = FakeGcsBucketClient(_prefixed(v1, "idx"))
    source = GcsIndexSource("bucket", "idx", cache_dir, client=client)
    source.current()
    client.blobs = _prefixed(v2, "idx")
    real_unlink = Path.unlink

    def refusing_unlink(self: Path, missing_ok: bool = False) -> None:
        if self == _cached_index(cache_dir, v1):
            raise PermissionError("busy")
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", refusing_unlink)

    assert source.current().version == manifest_version(v2[MANIFEST_FILE_NAME])


def test_the_open_version_and_the_next_never_share_a_path(
    tmp_path: Path, gcs_versions: GcsVersions
):
    v1, v2 = gcs_versions
    client = FakeGcsBucketClient(_prefixed(v1, "idx"))
    source = GcsIndexSource("bucket", "idx", tmp_path / "cache", client=client)
    first = source.current()
    client.blobs = _prefixed(v2, "idx")
    second = source.current()
    client.blobs = _prefixed(v1, "idx")
    third = source.current()

    assert len({first.path, second.path}) == 2
    assert third.path == first.path  # same version, same name: a path identifies its content
    assert third.path.read_bytes() == v1[INDEX_FILE_NAME]


def test_bucket_down_for_manifest_is_unavailable(tmp_path: Path):
    client = FakeGcsBucketClient({}, fail=frozenset({"idx/manifest.json"}))
    source = GcsIndexSource("bucket", "idx", tmp_path / "cache", client=client)
    with pytest.raises(IndexSourceUnavailable, match="cannot download manifest"):
        source.current()


def test_invalid_manifest_from_bucket_is_unavailable(tmp_path: Path):
    client = FakeGcsBucketClient({"idx/manifest.json": b"{}"})
    source = GcsIndexSource("bucket", "idx", tmp_path / "cache", client=client)
    with pytest.raises(IndexSourceUnavailable, match="invalid manifest"):
        source.current()


def test_prefix_is_stripped_of_leading_and_trailing_slashes(
    tmp_path: Path, gcs_versions: GcsVersions
):
    v1, _ = gcs_versions
    client = FakeGcsBucketClient(_prefixed(v1, "idx"))
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
