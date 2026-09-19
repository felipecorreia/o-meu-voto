"""Stage 1, fetch: download the TSE ZIPs and leave a record for the next stage.

`fetch(datasets, output_dir, downloader)` downloads every dataset through the
`Downloader` port into a temporary directory, moves each finished ZIP into
`output_dir`, and writes `fetch.json` there: URL, HTTP status, `Last-Modified`
and size per dataset. The temporary directory is removed at the end of the run,
even on failure. `build` runs alone from `output_dir`.

A non-200 status is recorded, never worked around: the record is written first
and `FetchError` is raised afterwards, so a workflow can still report the
status per dataset (ADR 0003, the datacenter access test).
"""

from __future__ import annotations

import datetime as dt
import json
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from br_elections_mcp.pipeline.datasets import Dataset
from br_elections_mcp.pipeline.downloader import Downloader, DownloadError

FETCH_RECORD_FILE = "fetch.json"
FETCH_RECORD_VERSION = 1


@dataclass(frozen=True, slots=True)
class FetchedDataset:
    """One line of the fetch record."""

    dataset: str
    ckan_dataset: str
    title: str
    url: str
    file: str
    status: int | None
    last_modified: str | None
    size: int | None
    error: str | None

    @property
    def ok(self) -> bool:
        return self.status == 200


@dataclass(frozen=True, slots=True)
class FetchRecord:
    """What one run of `fetch` did, as written to `fetch.json`."""

    fetched_at: str
    datasets: tuple[FetchedDataset, ...]

    @property
    def ok(self) -> bool:
        return all(item.ok for item in self.datasets)

    @property
    def failed(self) -> tuple[FetchedDataset, ...]:
        return tuple(item for item in self.datasets if not item.ok)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": FETCH_RECORD_VERSION,
            "fetched_at": self.fetched_at,
            "datasets": [asdict(item) for item in self.datasets],
        }

    def write(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n")

    @classmethod
    def read(cls, path: Path) -> FetchRecord:
        raw = json.loads(path.read_text())
        if raw.get("version") != FETCH_RECORD_VERSION:
            raise ValueError(f"{path}: unsupported fetch record version {raw.get('version')!r}")
        return cls(
            fetched_at=raw["fetched_at"],
            datasets=tuple(FetchedDataset(**item) for item in raw["datasets"]),
        )


class FetchError(RuntimeError):
    """At least one dataset did not come back with 200; `record` has the statuses."""

    def __init__(self, record: FetchRecord) -> None:
        failed = ", ".join(
            f"{item.dataset}: {item.error if item.status is None else item.status}"
            for item in record.failed
        )
        super().__init__(f"fetch failed for {failed}")
        self.record = record


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def fetch(
    datasets: Iterable[Dataset],
    output_dir: Path,
    downloader: Downloader,
    *,
    now: Callable[[], dt.datetime] = _utcnow,
) -> FetchRecord:
    """Download `datasets` into `output_dir` and write `fetch.json` next to them.

    Raises `FetchError` after writing the record when any download is not 200.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    fetched: list[FetchedDataset] = []
    # Inside output_dir so the final move is an atomic rename on one filesystem.
    with tempfile.TemporaryDirectory(prefix=".fetch-", dir=output_dir) as tmp_name:
        tmp_dir = Path(tmp_name)
        for dataset in datasets:
            fetched.append(_fetch_one(dataset, tmp_dir, output_dir, downloader))
    record = FetchRecord(fetched_at=now().isoformat(), datasets=tuple(fetched))
    record.write(output_dir / FETCH_RECORD_FILE)
    if not record.ok:
        raise FetchError(record)
    return record


def _fetch_one(
    dataset: Dataset, tmp_dir: Path, output_dir: Path, downloader: Downloader
) -> FetchedDataset:
    common = {
        "dataset": dataset.id,
        "ckan_dataset": dataset.ckan_dataset,
        "title": dataset.title,
        "url": dataset.url,
        "file": dataset.file_name,
    }
    try:
        result = downloader.download(dataset.url, tmp_dir / dataset.file_name)
    except DownloadError as exc:
        return FetchedDataset(**common, status=None, last_modified=None, size=None, error=str(exc))
    if result.ok:
        (tmp_dir / dataset.file_name).replace(output_dir / dataset.file_name)
    return FetchedDataset(
        **common,
        status=result.status,
        last_modified=result.last_modified,
        size=result.size,
        error=None,
    )
