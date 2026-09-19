"""Command line of the pipeline: `python -m br_elections_mcp.pipeline <stage> ...`.

Fetch and build exist so far. Each stage reads and writes files, so any one of
them can run alone (docs/codebase-design.md, section 5).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from br_elections_mcp.index_schema import read_manifest
from br_elections_mcp.pipeline.build import BuildError, build_index
from br_elections_mcp.pipeline.datasets import (
    CANDIDATE_SOCIAL_LINKS_2026,
    CANDIDATES_2026,
    CANDIDATES_COMPLEMENTARY_2026,
    DATASETS,
    MUNICIPALITIES_TSE_IBGE,
    POLLING_PLACES_2026,
    POLLING_PLACES_CURRENT,
    SourceFile,
    dataset_by_id,
)
from br_elections_mcp.pipeline.downloader import (
    DEFAULT_IMPERSONATE,
    CurlCffiDownloader,
    Downloader,
    LocalFilesDownloader,
)
from br_elections_mcp.pipeline.fetch import FetchError, FetchRecord, fetch
from br_elections_mcp.pipeline.validate import ValidationError, validate


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

    build_parser = stages.add_parser(
        "build", help="build index.duckdb and manifest.json from CSV files"
    )
    build_parser.add_argument(
        "--polling-places", type=Path, required=True, help="eleitorado_local_votacao CSV"
    )
    build_parser.add_argument(
        "--municipalities", type=Path, required=True, help="municipio_tse_ibge CSV"
    )
    build_parser.add_argument(
        "--candidates", type=Path, required=True, help="consulta_cand CSV (main file)"
    )
    build_parser.add_argument(
        "--candidates-complementary",
        type=Path,
        required=True,
        help="consulta_cand_complementar CSV (adjudication status and on-ballot flag)",
    )
    build_parser.add_argument(
        "--social-links", type=Path, required=True, help="rede_social_candidato CSV"
    )
    build_parser.add_argument("--output-dir", type=Path, required=True)
    build_parser.add_argument(
        "--monthly",
        action="store_true",
        help="the polling-places file is the monthly ATUAL snapshot, not an election file",
    )

    validate_parser = stages.add_parser(
        "validate", help="run every gate over a built index and write validation_report.json"
    )
    validate_parser.add_argument(
        "--polling-places", type=Path, required=True, help="eleitorado_local_votacao CSV"
    )
    validate_parser.add_argument(
        "--municipalities", type=Path, required=True, help="municipio_tse_ibge CSV"
    )
    validate_parser.add_argument(
        "--candidates", type=Path, required=True, help="consulta_cand CSV (main file)"
    )
    validate_parser.add_argument(
        "--candidates-complementary",
        type=Path,
        required=True,
        help="consulta_cand_complementar CSV (adjudication status and on-ballot flag)",
    )
    validate_parser.add_argument(
        "--social-links", type=Path, required=True, help="rede_social_candidato CSV"
    )
    validate_parser.add_argument(
        "--index-dir",
        type=Path,
        required=True,
        help="directory with index.duckdb and manifest.json",
    )
    validate_parser.add_argument(
        "--elections", type=Path, required=True, help="data/elections.yaml"
    )
    validate_parser.add_argument("--output-dir", type=Path, required=True)
    validate_parser.add_argument(
        "--monthly",
        action="store_true",
        help="the polling-places file is the monthly ATUAL snapshot, not an election file",
    )
    validate_parser.add_argument(
        "--previous-manifest", type=Path, help="manifest.json of the previously published index"
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


def _run_build(args: argparse.Namespace) -> int:
    polling_dataset = POLLING_PLACES_CURRENT if args.monthly else POLLING_PLACES_2026
    try:
        manifest = build_index(
            SourceFile(polling_dataset, args.polling_places),
            SourceFile(MUNICIPALITIES_TSE_IBGE, args.municipalities),
            SourceFile(CANDIDATES_2026, args.candidates),
            SourceFile(CANDIDATES_COMPLEMENTARY_2026, args.candidates_complementary),
            SourceFile(CANDIDATE_SOCIAL_LINKS_2026, args.social_links),
            args.output_dir,
        )
    except BuildError as exc:
        print(f"build failed: {exc}", file=sys.stderr)
        return 1
    print(f"index written to {args.output_dir}: {manifest.counts}")
    return 0


def _run_validate(args: argparse.Namespace) -> int:
    polling_dataset = POLLING_PLACES_CURRENT if args.monthly else POLLING_PLACES_2026
    previous_manifest = read_manifest(args.previous_manifest) if args.previous_manifest else None
    try:
        report = validate(
            SourceFile(polling_dataset, args.polling_places),
            SourceFile(MUNICIPALITIES_TSE_IBGE, args.municipalities),
            SourceFile(CANDIDATES_2026, args.candidates),
            SourceFile(CANDIDATES_COMPLEMENTARY_2026, args.candidates_complementary),
            SourceFile(CANDIDATE_SOCIAL_LINKS_2026, args.social_links),
            args.index_dir,
            args.elections,
            args.output_dir,
            previous_manifest=previous_manifest,
        )
    except ValidationError as exc:
        for gate in exc.report.failed:
            print(f"{gate.name}: {gate.message}", file=sys.stderr)
        return 1
    gate_names = [gate.name for gate in report.gates]
    print(f"every gate passed, report written to {args.output_dir}: {gate_names}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.stage == "fetch":
        return _run_fetch(args)
    if args.stage == "build":
        return _run_build(args)
    if args.stage == "validate":
        return _run_validate(args)
    raise AssertionError(f"unhandled stage {args.stage!r}")


if __name__ == "__main__":
    sys.exit(main())
