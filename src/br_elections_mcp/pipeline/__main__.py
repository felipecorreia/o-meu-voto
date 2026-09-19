"""Command line of the pipeline: `python -m br_elections_mcp.pipeline <stage> ...`.

Only `fetch` exists so far. Each stage reads and writes files, so any one of
them can run alone (docs/codebase-design.md, section 5).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from br_elections_mcp.pipeline.datasets import DATASETS, dataset_by_id
from br_elections_mcp.pipeline.downloader import (
    DEFAULT_IMPERSONATE,
    CurlCffiDownloader,
    Downloader,
    LocalFilesDownloader,
)
from br_elections_mcp.pipeline.fetch import FetchError, FetchRecord, fetch


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m br_elections_mcp.pipeline")
    stages = parser.add_subparsers(dest="stage", required=True)

    fetch_parser = stages.add_parser(
        "fetch", help="download the TSE ZIPs and write fetch.json into --output"
    )
    fetch_parser.add_argument("--output", type=Path, required=True, help="directory for the ZIPs")
    fetch_parser.add_argument(
        "--dataset",
        action="append",
        dest="datasets",
        choices=[dataset.id for dataset in DATASETS],
        help="dataset id to fetch (repeatable; default: all)",
    )
    fetch_parser.add_argument(
        "--from-dir",
        type=Path,
        help="read the ZIPs from this directory instead of the TSE CDN (LocalFilesDownloader)",
    )
    fetch_parser.add_argument(
        "--impersonate",
        default=DEFAULT_IMPERSONATE,
        help=f"curl_cffi browser target (default: {DEFAULT_IMPERSONATE})",
    )
    return parser


def _run_fetch(args: argparse.Namespace) -> int:
    datasets = tuple(dataset_by_id(name) for name in args.datasets) if args.datasets else DATASETS
    downloader: Downloader
    if args.from_dir is not None:
        downloader = LocalFilesDownloader(args.from_dir)
    else:
        downloader = CurlCffiDownloader(impersonate=args.impersonate)
    try:
        record = fetch(datasets, args.output, downloader)
    except FetchError as exc:
        _print_record(exc.record)
        print(f"error: {exc}", file=sys.stderr)
        return 1
    _print_record(record)
    return 0


def _print_record(record: FetchRecord) -> None:
    for item in record.datasets:
        status = item.error if item.status is None else str(item.status)
        size = "" if item.size is None else f" {item.size} bytes"
        print(f"{item.dataset}: {status}{size} {item.url}")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.stage == "fetch":
        return _run_fetch(args)
    raise AssertionError(f"unhandled stage {args.stage!r}")


if __name__ == "__main__":
    sys.exit(main())
