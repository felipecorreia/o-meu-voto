"""Command line of the pipeline: `python -m br_elections_mcp.pipeline <stage> ...`.

Stages `fetch`, `build`, `validate`, `publish` and `mirror-photos`, plus two helpers the
refresh workflow chains them with: `extract` (the CSV out of a fetched ZIP)
and `current-manifest` (the published manifest, for the count-stability gate
of `validate`). Each stage reads and writes files, so any one of them can run
alone (docs/codebase-design.md, section 5).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from br_elections_mcp.index_schema import INDEX_FILE_NAME, MANIFEST_FILE_NAME, read_manifest
from br_elections_mcp.pipeline.bucket import (
    BucketClient,
    GcsBucketClient,
    LocalDirectoryBucketClient,
    R2BucketClient,
)
from br_elections_mcp.pipeline.build import BuildError, apply_photo_urls, build_index
from br_elections_mcp.pipeline.datasets import (
    CANDIDATE_ASSETS_2026,
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
from br_elections_mcp.pipeline.extract import ExtractError, extract_csv
from br_elections_mcp.pipeline.fetch import FetchError, FetchRecord, fetch
from br_elections_mcp.pipeline.mirror_photos import MirrorError, PhotoZip, mirror_photos
from br_elections_mcp.pipeline.publish import PublishError, download_current_manifest, publish
from br_elections_mcp.pipeline.validate import ValidationError, validate

_PHOTO_ZIP_NAME_RE = re.compile(r"^foto_cand\d+_(?P<uf>[A-Za-z]{2})_div\.zip$")


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
    build_parser.add_argument(
        "--candidate-assets", type=Path, required=True, help="bem_candidato CSV"
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
        "--candidate-assets", type=Path, required=True, help="bem_candidato CSV"
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

    extract_parser = stages.add_parser(
        "extract", help="extract the _BRASIL (or only) CSV of a TSE ZIP and print its path"
    )
    extract_parser.add_argument("--zip", type=Path, required=True, help="a ZIP fetch downloaded")
    extract_parser.add_argument("--output-dir", type=Path, required=True)

    current_parser = stages.add_parser(
        "current-manifest",
        help="download the manifest currently published in the bucket, if any, into --output",
    )
    _add_bucket_arguments(current_parser)
    current_parser.add_argument("--output", type=Path, required=True, help="where to write it")

    publish_parser = stages.add_parser(
        "publish", help="send index.duckdb and manifest.json to the bucket, manifest last"
    )
    publish_parser.add_argument(
        "--index-dir",
        type=Path,
        required=True,
        help="directory with index.duckdb and manifest.json (build output, validated)",
    )
    _add_bucket_arguments(publish_parser)

    mirror_parser = stages.add_parser(
        "mirror-photos",
        help="sync candidate photo ZIPs to R2 and write photo_url into the index",
    )
    mirror_parser.add_argument(
        "--zips-dir",
        type=Path,
        required=True,
        help="directory of already-downloaded foto_cand<year>_<UF>_div.zip files",
    )
    mirror_parser.add_argument(
        "--index-dir",
        type=Path,
        required=True,
        help="directory with the already-built index.duckdb to write photo_url into",
    )
    mirror_parser.add_argument(
        "--public-domain",
        required=True,
        help="public base URL of the R2 bucket, e.g. https://fotos.example.org",
    )
    mirror_parser.add_argument("--r2-endpoint", required=True, help="R2 account S3 endpoint URL")
    mirror_parser.add_argument("--r2-bucket", required=True, help="R2 bucket name")
    mirror_parser.add_argument("--r2-access-key-id", required=True)
    mirror_parser.add_argument("--r2-secret-access-key", required=True)
    mirror_parser.add_argument("--r2-prefix", default="", help="key prefix inside the bucket")
    return parser


def _add_bucket_arguments(parser: argparse.ArgumentParser) -> None:
    bucket = parser.add_mutually_exclusive_group(required=True)
    bucket.add_argument("--bucket", help="name of the GCS index bucket (GcsBucketClient)")
    bucket.add_argument(
        "--local-bucket",
        type=Path,
        help="a directory standing in for the bucket (LocalDirectoryBucketClient)",
    )
    parser.add_argument(
        "--prefix", default="", help="object name prefix inside the bucket (default: none)"
    )


def _bucket_client(args: argparse.Namespace) -> BucketClient:
    if args.local_bucket is not None:
        return LocalDirectoryBucketClient(args.local_bucket)
    return GcsBucketClient(args.bucket)


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
            SourceFile(CANDIDATE_ASSETS_2026, args.candidate_assets),
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
            SourceFile(CANDIDATE_ASSETS_2026, args.candidate_assets),
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


def _run_extract(args: argparse.Namespace) -> int:
    try:
        extracted = extract_csv(args.zip, args.output_dir)
    except ExtractError as exc:
        print(f"extract failed: {exc}", file=sys.stderr)
        return 1
    print(extracted)
    return 0


def _run_current_manifest(args: argparse.Namespace) -> int:
    manifest = download_current_manifest(_bucket_client(args), args.output, prefix=args.prefix)
    if manifest is None:
        print("no manifest is published yet; nothing written")
    else:
        print(f"current manifest written to {args.output}: {manifest.index_sha256}")
    return 0


def _run_publish(args: argparse.Namespace) -> int:
    try:
        record = publish(
            args.index_dir / INDEX_FILE_NAME,
            args.index_dir / MANIFEST_FILE_NAME,
            _bucket_client(args),
            prefix=args.prefix,
        )
    except PublishError as exc:
        print(f"publish failed: {exc}", file=sys.stderr)
        return 1
    print(
        f"published version {record.index_version} (index sha256 {record.index_sha256}): "
        f"{list(record.objects)}"
    )
    return 0


def _iter_photo_zips(zips_dir: Path) -> list[PhotoZip]:
    """Every `foto_cand<year>_<UF>_div.zip` under `zips_dir`, UF taken from the file name."""
    zips = []
    for path in sorted(zips_dir.iterdir()):
        match = _PHOTO_ZIP_NAME_RE.match(path.name)
        if match is not None:
            zips.append(PhotoZip(uf=match.group("uf").upper(), path=path))
    return zips


def _run_mirror_photos(args: argparse.Namespace) -> int:
    zips = _iter_photo_zips(args.zips_dir)
    bucket = R2BucketClient(
        endpoint_url=args.r2_endpoint,
        bucket=args.r2_bucket,
        access_key_id=args.r2_access_key_id,
        secret_access_key=args.r2_secret_access_key,
        prefix=args.r2_prefix,
    )
    try:
        result = mirror_photos(zips, bucket, public_domain=args.public_domain)
    except MirrorError as exc:
        print(f"mirror-photos failed: {exc}", file=sys.stderr)
        return 1
    apply_photo_urls(args.index_dir, result.photo_urls)
    print(
        f"uploaded {len(result.uploaded)}, skipped {len(result.skipped)}, "
        f"removed {len(result.removed)}, photo_url set for {len(result.photo_urls)} candidacies"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.stage == "fetch":
        return _run_fetch(args)
    if args.stage == "build":
        return _run_build(args)
    if args.stage == "validate":
        return _run_validate(args)
    if args.stage == "extract":
        return _run_extract(args)
    if args.stage == "current-manifest":
        return _run_current_manifest(args)
    if args.stage == "publish":
        return _run_publish(args)
    if args.stage == "mirror-photos":
        return _run_mirror_photos(args)
    raise AssertionError(f"unhandled stage {args.stage!r}")


if __name__ == "__main__":
    sys.exit(main())
