"""The fetch stage over LocalFilesDownloader. No test here touches the network."""

import datetime as dt
import json
import zipfile
from pathlib import Path

import pytest

from br_elections_mcp.domain import UF
from br_elections_mcp.pipeline.datasets import (
    CANDIDATE_PHOTOS_2026,
    CANDIDATES_2026,
    DATASETS,
    MUNICIPALITIES_TSE_IBGE,
    POLLING_PLACES_2026,
    Dataset,
    dataset_by_id,
)
from br_elections_mcp.pipeline.downloader import (
    DownloadError,
    DownloadResult,
    LocalFilesDownloader,
)
from br_elections_mcp.pipeline.fetch import (
    FETCH_RECORD_FILE,
    FetchError,
    FetchRecord,
    fetch,
)

FIXED_NOW = dt.datetime(2026, 9, 18, 3, 0, tzinfo=dt.UTC)


def _now() -> dt.datetime:
    return FIXED_NOW


def _make_zip(path: Path, member: str, content: bytes) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(member, content)


@pytest.fixture
def source_dir(tmp_path: Path) -> Path:
    """A directory with a ZIP for every dataset, as the TSE CDN would serve."""
    source = tmp_path / "source"
    source.mkdir()
    for dataset in DATASETS:
        _make_zip(source / dataset.file_name, "leiame.pdf", dataset.id.encode())
    return source


def test_fetch_writes_zips_and_record_and_removes_temporary_files(source_dir, tmp_path):
    output = tmp_path / "out"

    record = fetch(DATASETS, output, LocalFilesDownloader(source_dir), now=_now)

    assert record.ok
    assert record.fetched_at == "2026-09-18T03:00:00+00:00"
    assert sorted(p.name for p in output.iterdir()) == sorted(
        [FETCH_RECORD_FILE, *(d.file_name for d in DATASETS)]
    )
    for dataset in DATASETS:
        with zipfile.ZipFile(output / dataset.file_name) as zf:
            assert zf.read("leiame.pdf") == dataset.id.encode()


def test_fetch_record_has_url_status_last_modified_and_size_per_dataset(source_dir, tmp_path):
    output = tmp_path / "out"

    fetch(DATASETS, output, LocalFilesDownloader(source_dir), now=_now)

    raw = json.loads((output / FETCH_RECORD_FILE).read_text())
    assert raw["version"] == 1
    assert raw["fetched_at"] == "2026-09-18T03:00:00+00:00"
    by_id = {item["dataset"]: item for item in raw["datasets"]}
    assert list(by_id) == [d.id for d in DATASETS]
    item = by_id[POLLING_PLACES_2026.id]
    assert item["ckan_dataset"] == "eleitorado-2026"
    assert item["url"] == POLLING_PLACES_2026.url
    assert item["file"] == "eleitorado_local_votacao_2026.zip"
    assert item["status"] == 200
    assert item["size"] == (source_dir / POLLING_PLACES_2026.file_name).stat().st_size
    assert item["last_modified"].endswith(" GMT")
    assert item["error"] is None


def test_fetch_record_round_trips_through_read(source_dir, tmp_path):
    output = tmp_path / "out"
    record = fetch(DATASETS, output, LocalFilesDownloader(source_dir), now=_now)

    assert FetchRecord.read(output / FETCH_RECORD_FILE) == record


def test_fetch_records_a_403_and_fails_after_writing_the_record(source_dir, tmp_path):
    output = tmp_path / "out"
    downloader = LocalFilesDownloader(source_dir, statuses={CANDIDATES_2026.url: 403})

    with pytest.raises(FetchError) as excinfo:
        fetch(DATASETS, output, downloader, now=_now)

    assert "candidates_2026: 403" in str(excinfo.value)
    record = excinfo.value.record
    assert not record.ok
    assert [item.dataset for item in record.failed] == [CANDIDATES_2026.id]
    assert FetchRecord.read(output / FETCH_RECORD_FILE) == record
    assert not (output / CANDIDATES_2026.file_name).exists()
    assert (output / POLLING_PLACES_2026.file_name).exists()
    assert [p.name for p in output.iterdir() if p.name.startswith(".fetch-")] == []


def test_fetch_records_a_missing_file_as_404(source_dir, tmp_path):
    (source_dir / MUNICIPALITIES_TSE_IBGE.file_name).unlink()

    with pytest.raises(FetchError) as excinfo:
        fetch(DATASETS, tmp_path / "out", LocalFilesDownloader(source_dir), now=_now)

    failed = excinfo.value.record.failed
    assert [(item.dataset, item.status) for item in failed] == [(MUNICIPALITIES_TSE_IBGE.id, 404)]


class _BrokenDownloader:
    def download(self, url: str, destination: Path) -> DownloadResult:
        raise DownloadError(f"{url}: connection reset")


def test_fetch_records_a_transport_failure_with_null_status(tmp_path):
    output = tmp_path / "out"

    with pytest.raises(FetchError) as excinfo:
        fetch([POLLING_PLACES_2026], output, _BrokenDownloader(), now=_now)

    (item,) = excinfo.value.record.datasets
    assert item.status is None
    assert item.error == f"{POLLING_PLACES_2026.url}: connection reset"
    assert "connection reset" in str(excinfo.value)
    assert list(p.name for p in output.iterdir()) == [FETCH_RECORD_FILE]


def test_fetch_accepts_a_subset_of_datasets(source_dir, tmp_path):
    output = tmp_path / "out"

    record = fetch([MUNICIPALITIES_TSE_IBGE], output, LocalFilesDownloader(source_dir), now=_now)

    assert [item.dataset for item in record.datasets] == [MUNICIPALITIES_TSE_IBGE.id]
    assert sorted(p.name for p in output.iterdir()) == sorted(
        [FETCH_RECORD_FILE, MUNICIPALITIES_TSE_IBGE.file_name]
    )


def test_registry_covers_the_three_ckan_datasets_with_unique_ids_and_files():
    assert {d.ckan_dataset for d in DATASETS} == {
        "eleitorado-2026",
        "candidatos-2026",
        "codigos-oficiais-de-uf-e-municipios-segundo-o-tse-e-o-ibge",
    }
    assert len({d.id for d in DATASETS}) == len(DATASETS)
    assert len({d.file_name for d in DATASETS}) == len(DATASETS)
    for dataset in DATASETS:
        assert dataset.url.startswith("https://cdn.tse.jus.br/")
        assert dataset.url.endswith("/" + dataset.file_name)
        assert (
            dataset.dataset_url == f"https://dadosabertos.tse.jus.br/dataset/{dataset.ckan_dataset}"
        )
    assert dataset_by_id("candidates_2026") is CANDIDATES_2026


def test_dataset_by_id_names_the_known_ids_on_miss():
    with pytest.raises(KeyError, match=r"unknown dataset 'nope'.*candidates_2026"):
        dataset_by_id("nope")


def test_local_files_downloader_matches_the_file_by_url_basename(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "x.zip").write_bytes(b"zip")
    dataset = Dataset(
        id="x", ckan_dataset="d", title="t", file_name="x.zip", url="https://h/p/x.zip"
    )

    result = LocalFilesDownloader(root).download(dataset.url, tmp_path / "dest.zip")

    assert result.ok
    assert result.size == 3
    assert (tmp_path / "dest.zip").read_bytes() == b"zip"


@pytest.fixture
def photos_source_dir(tmp_path: Path) -> Path:
    """A directory with a photo ZIP for every UF, as the TSE CDN would serve."""
    source = tmp_path / "photos-source"
    source.mkdir()
    for dataset in CANDIDATE_PHOTOS_2026:
        _make_zip(source / dataset.file_name, "leiame.pdf", dataset.id.encode())
    return source


def test_photo_registry_has_one_zip_per_uf_with_candidacies_and_none_for_abroad():
    ufs = {dataset.id.removeprefix("candidate_photos_2026_") for dataset in CANDIDATE_PHOTOS_2026}

    assert len(CANDIDATE_PHOTOS_2026) == 28
    assert ufs == {uf.value for uf in UF} - {"ZZ"}
    assert {"BR", "DF", "SP"} <= ufs
    assert len({d.file_name for d in CANDIDATE_PHOTOS_2026}) == 28
    for dataset in CANDIDATE_PHOTOS_2026:
        assert dataset.ckan_dataset == "candidatos-2026"
        assert dataset.url == (
            "https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/fotos/"
            f"foto_cand2026_{dataset.id[-2:]}_div.zip"
        )
        assert dataset.file_name == dataset.url.rsplit("/", 1)[1]


def test_photo_zips_are_not_part_of_the_default_datasets():
    assert not {d.id for d in CANDIDATE_PHOTOS_2026} & {d.id for d in DATASETS}


def test_fetch_downloads_every_photo_zip_and_records_status_last_modified_and_size(
    photos_source_dir, tmp_path
):
    output = tmp_path / "photos"

    record = fetch(CANDIDATE_PHOTOS_2026, output, LocalFilesDownloader(photos_source_dir), now=_now)

    assert record.ok
    assert sorted(p.name for p in output.iterdir()) == sorted(
        [FETCH_RECORD_FILE, *(d.file_name for d in CANDIDATE_PHOTOS_2026)]
    )
    assert len(record.datasets) == 28
    ac = next(item for item in record.datasets if item.dataset == "candidate_photos_2026_AC")
    assert ac.status == 200
    assert ac.size == (photos_source_dir / "foto_cand2026_AC_div.zip").stat().st_size
    assert ac.last_modified is not None
    assert FetchRecord.read(output / FETCH_RECORD_FILE) == record


def test_fetch_fails_on_a_missing_photo_zip_and_records_which(photos_source_dir, tmp_path):
    (photos_source_dir / "foto_cand2026_BR_div.zip").unlink()
    output = tmp_path / "photos"

    with pytest.raises(FetchError) as excinfo:
        fetch(CANDIDATE_PHOTOS_2026, output, LocalFilesDownloader(photos_source_dir), now=_now)

    failed = excinfo.value.record.failed
    assert [(item.dataset, item.status) for item in failed] == [("candidate_photos_2026_BR", 404)]
    assert not (output / "foto_cand2026_BR_div.zip").exists()
