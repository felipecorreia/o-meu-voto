"""Stage ``publish``: index and manifest in, objects in the bucket out, through the port.

Every test runs against ``FakeBucketClient``, an in-memory bucket that records the order of
its writes; no test touches the network or a real cloud credential.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path

import pytest

from br_elections_mcp.index_schema import (
    INDEX_FILE_NAME,
    MANIFEST_FILE_NAME,
    Manifest,
    read_manifest,
    write_manifest,
)
from br_elections_mcp.pipeline.bucket import LocalDirectoryBucketClient
from br_elections_mcp.pipeline.build import apply_photo_urls
from br_elections_mcp.pipeline.datasets import POLLING_PLACES_CURRENT
from br_elections_mcp.pipeline.publish import (
    PUBLISH_RECORD_FILE,
    PublishError,
    PublishRecord,
    download_current_index,
    download_current_manifest,
    publish,
    version_id,
)
from tests.conftest import BUILT_AT, build_fixture_index


class FakeBucketClient:
    """In-memory bucket: object name -> bytes, plus the order every object was written in."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.writes: list[str] = []

    def upload(self, local_path: Path, object_name: str) -> None:
        self.objects[object_name] = local_path.read_bytes()
        self.writes.append(object_name)

    def download(self, object_name: str, local_path: Path) -> bool:
        if object_name not in self.objects:
            return False
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(self.objects[object_name])
        return True


@pytest.fixture
def index_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "index"
    build_fixture_index(directory)
    return directory


def _publish(index_dir: Path, client: FakeBucketClient, prefix: str = "") -> PublishRecord:
    return publish(
        index_dir / INDEX_FILE_NAME, index_dir / MANIFEST_FILE_NAME, client, prefix=prefix
    )


def test_publish_writes_the_versioned_pair_then_the_current_pair_manifest_last(index_dir: Path):
    client = FakeBucketClient()
    record = _publish(index_dir, client)
    manifest = read_manifest(index_dir / MANIFEST_FILE_NAME)
    version = version_id(manifest)
    assert client.writes == [
        f"versions/{version}/{INDEX_FILE_NAME}",
        f"versions/{version}/{MANIFEST_FILE_NAME}",
        INDEX_FILE_NAME,
        MANIFEST_FILE_NAME,
    ]
    assert client.writes[-1] == MANIFEST_FILE_NAME
    assert client.objects[INDEX_FILE_NAME] == (index_dir / INDEX_FILE_NAME).read_bytes()
    assert client.objects[MANIFEST_FILE_NAME] == (index_dir / MANIFEST_FILE_NAME).read_bytes()
    assert record.index_version == version
    assert record.index_sha256 == manifest.index_sha256
    assert record.objects == tuple(client.writes)


def test_publish_uploads_only_the_index_and_the_manifest(index_dir: Path):
    """Raw ZIPs and CSVs never reach the bucket: the stage only knows two files (ADR 0004)."""
    (index_dir / "eleitorado_local_votacao_2026.zip").write_bytes(b"not for the bucket")
    client = FakeBucketClient()
    _publish(index_dir, client)
    assert {Path(name).name for name in client.objects} == {INDEX_FILE_NAME, MANIFEST_FILE_NAME}


def test_publish_keeps_the_previous_version_when_a_new_index_is_published(
    index_dir: Path, tmp_path: Path
):
    client = FakeBucketClient()
    first = _publish(index_dir, client)
    later_dir = tmp_path / "later"
    build_fixture_index(later_dir, built_at=BUILT_AT + dt.timedelta(hours=6))
    second = _publish(later_dir, client)
    assert first.index_version != second.index_version
    assert (
        client.objects[f"versions/{first.index_version}/{MANIFEST_FILE_NAME}"]
        == (index_dir / MANIFEST_FILE_NAME).read_bytes()
    )
    assert (
        client.objects[f"versions/{second.index_version}/{MANIFEST_FILE_NAME}"]
        == (later_dir / MANIFEST_FILE_NAME).read_bytes()
    )
    # The current pair now points at the second version; the first is intact for rollback.
    assert client.objects[MANIFEST_FILE_NAME] == (later_dir / MANIFEST_FILE_NAME).read_bytes()
    assert client.writes[-1] == MANIFEST_FILE_NAME


def test_publish_prefixes_every_object_name(index_dir: Path):
    client = FakeBucketClient()
    record = _publish(index_dir, client, prefix="index/")
    assert all(name.startswith("index/") for name in client.writes)
    assert client.writes[-1] == f"index/{MANIFEST_FILE_NAME}"
    assert record.objects[-1] == f"index/{MANIFEST_FILE_NAME}"


def test_publish_normalizes_a_prefix_without_trailing_slash(index_dir: Path):
    client = FakeBucketClient()
    _publish(index_dir, client, prefix="index")
    assert client.writes[-1] == f"index/{MANIFEST_FILE_NAME}"


def test_download_current_index_uses_versioned_object_and_verifies_hash(
    index_dir: Path, tmp_path: Path
):
    client = FakeBucketClient()
    record = _publish(index_dir, client)
    client.objects[INDEX_FILE_NAME] = b"an in-progress mutable upload"
    target = tmp_path / "downloaded"

    assert download_current_index(client, target)
    assert (target / INDEX_FILE_NAME).read_bytes() == (index_dir / INDEX_FILE_NAME).read_bytes()

    client.objects[f"versions/{record.index_version}/{INDEX_FILE_NAME}"] = b"tampered"
    with pytest.raises(PublishError, match="does not match manifest"):
        download_current_index(client, tmp_path / "corrupt")


def test_publish_refuses_a_manifest_whose_sha256_does_not_match_the_index(index_dir: Path):
    manifest = read_manifest(index_dir / MANIFEST_FILE_NAME)
    tampered = manifest.model_copy(update={"index_sha256": "0" * 64})
    write_manifest(tampered, index_dir / MANIFEST_FILE_NAME)
    client = FakeBucketClient()
    with pytest.raises(PublishError, match="SHA-256"):
        _publish(index_dir, client)
    assert client.writes == []


def test_publish_accepts_the_manifest_apply_photo_urls_rewrote(index_dir: Path):
    """apply_photo_urls mutates index.duckdb in place; its manifest rewrite must keep the
    two in sync, or publish would refuse the pair the next time mirror-photos runs."""
    digest = hashlib.sha256(b"photo").hexdigest()
    url = f"https://fotos.example.org/FAC10000000001_div-{digest}.jpg"
    apply_photo_urls(index_dir, {10000000001: url}, {10000000001: digest})
    manifest = read_manifest(index_dir / MANIFEST_FILE_NAME)
    assert (
        manifest.index_sha256
        == hashlib.sha256((index_dir / INDEX_FILE_NAME).read_bytes()).hexdigest()
    )
    client = FakeBucketClient()
    record = _publish(index_dir, client)
    assert record.index_sha256 == manifest.index_sha256


def test_publish_refuses_a_missing_index_file(index_dir: Path):
    (index_dir / INDEX_FILE_NAME).unlink()
    client = FakeBucketClient()
    with pytest.raises(PublishError, match="not found"):
        _publish(index_dir, client)
    assert client.writes == []


def test_publish_record_is_written_next_to_the_index(index_dir: Path):
    client = FakeBucketClient()
    record = _publish(index_dir, client)
    read_back = PublishRecord.read(index_dir / PUBLISH_RECORD_FILE)
    assert read_back == record
    assert read_back.published_at


def test_published_manifest_carries_the_election_of_an_all_election_files_index(
    index_dir: Path,
):
    client = FakeBucketClient()
    _publish(index_dir, client)
    published = Manifest.model_validate_json(client.objects[MANIFEST_FILE_NAME])
    assert published.election_year == 2026
    assert published.election_dates == {1: dt.date(2026, 10, 4), 2: dt.date(2026, 10, 25)}
    assert set(published.datasets) == {
        "polling_places",
        "municipalities",
        "candidates",
        "candidates_complementary",
        "candidate_social_links",
        "candidate_assets",
    }
    assert all(source.generated_at for source in published.datasets.values())
    assert published.index_built_at == BUILT_AT
    assert published.counts["candidates"] == 23
    assert published.index_sha256 == hashlib.sha256(client.objects[INDEX_FILE_NAME]).hexdigest()


def test_published_manifest_has_a_null_election_when_a_dataset_is_the_monthly_atual_file(
    tmp_path: Path,
):
    monthly_dir = tmp_path / "monthly"
    build_fixture_index(monthly_dir, dataset=POLLING_PLACES_CURRENT)
    client = FakeBucketClient()
    publish(monthly_dir / INDEX_FILE_NAME, monthly_dir / MANIFEST_FILE_NAME, client)
    published = Manifest.model_validate_json(client.objects[MANIFEST_FILE_NAME])
    assert published.election_year is None
    assert published.election_dates is None
    # Candidates still come from consulta_cand_2026; the election is null all the same.
    assert published.datasets["candidates"].file == "consulta_cand_2026_BRASIL.csv"
    assert published.datasets["polling_places"].dataset == POLLING_PLACES_CURRENT.title


def test_version_id_is_sortable_by_build_time_and_names_the_index(index_dir: Path):
    manifest = read_manifest(index_dir / MANIFEST_FILE_NAME)
    version = version_id(manifest)
    # BUILT_AT is 09:05:11 in America/Sao_Paulo, 12:05:11 UTC.
    assert version == f"20260918T120511Z-{manifest.index_sha256[:12]}"


def test_download_current_manifest_returns_none_when_nothing_was_published(tmp_path: Path):
    client = FakeBucketClient()
    assert download_current_manifest(client, tmp_path / "previous.json") is None
    assert not (tmp_path / "previous.json").exists()


def test_download_current_manifest_returns_the_published_manifest(index_dir: Path, tmp_path: Path):
    client = FakeBucketClient()
    _publish(index_dir, client, prefix="index")
    target = tmp_path / "previous" / "manifest.json"
    manifest = download_current_manifest(client, target, prefix="index")
    assert manifest == read_manifest(index_dir / MANIFEST_FILE_NAME)
    assert target.is_file()


def test_local_directory_bucket_client_round_trips_objects(tmp_path: Path):
    client = LocalDirectoryBucketClient(tmp_path / "bucket")
    source = tmp_path / "file.bin"
    source.write_bytes(b"payload")
    client.upload(source, "index/versions/v1/file.bin")
    assert (tmp_path / "bucket" / "index" / "versions" / "v1" / "file.bin").read_bytes() == (
        b"payload"
    )
    target = tmp_path / "out" / "file.bin"
    assert client.download("index/versions/v1/file.bin", target) is True
    assert target.read_bytes() == b"payload"
    assert client.download("index/missing", tmp_path / "out" / "missing") is False
    assert not (tmp_path / "out" / "missing").exists()


def test_local_directory_bucket_client_rejects_object_names_outside_the_root(tmp_path: Path):
    client = LocalDirectoryBucketClient(tmp_path / "bucket")
    source = tmp_path / "file.bin"
    source.write_bytes(b"payload")
    with pytest.raises(ValueError):
        client.upload(source, "../escape.bin")
    with pytest.raises(ValueError):
        client.download("/etc/passwd", tmp_path / "out")
