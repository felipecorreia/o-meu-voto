"""Command line of the pipeline: `python -m br_elections_mcp.pipeline <stage> ...`.

Stages `fetch` (the datasets, or the candidate photo ZIPs with `--photos`), `build`, `validate`,
`publish`, `mirror-photos` and `clean-photos`, plus two helpers the refresh workflow chains
them with: `extract` (the CSV out of a fetched ZIP) and `current-manifest` (the published
manifest, for the count-stability gate of `validate`). Each stage reads and writes files, so
any one of them can run alone (docs/codebase-design.md, section 5).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import duckdb

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
    CANDIDATE_PHOTOS_2026,
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
from br_elections_mcp.pipeline.mirror_photos import (
    MirrorError,
    PhotoZip,
    full_photo_load_complete,
    mark_full_photo_load_complete,
    mirror_photos,
    planned_photo_rows,
    verified_previous_photos,
)
from br_elections_mcp.pipeline.photo_cleanup import (
    CLEANUP_GRACE,
    MAX_DELETE_FRACTION,
    PhotoCleanupError,
    clean_photos,
)
from br_elections_mcp.pipeline.photo_integrity import (
    photo_problems,
    photo_public_domain_problem,
    photo_rows_problems,
)
from br_elections_mcp.pipeline.publish import (
    PublishError,
    download_current_index,
    download_current_manifest,
    publish,
    verify_index_pair,
)
from br_elections_mcp.pipeline.validate import ValidationError, validate

_PHOTO_ZIP_NAME_RE = re.compile(r"^foto_cand\d+_(?P<uf>[A-Za-z]{2})_div\.zip$")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m br_elections_mcp.pipeline")
    stages = parser.add_subparsers(dest="stage", required=True)

    fetch_parser = stages.add_parser(
        "fetch", help="download the TSE ZIPs and write fetch.json into --output"
    )
    fetch_parser.add_argument("--output", type=Path, required=True, help="directory for the ZIPs")
    fetch_selection = fetch_parser.add_mutually_exclusive_group()
    fetch_selection.add_argument(
        "--dataset",
        action="append",
        dest="datasets",
        choices=[dataset.id for dataset in DATASETS],
        help="dataset id to fetch (repeatable; default: all)",
    )
    fetch_selection.add_argument(
        "--photos",
        action="store_true",
        help="fetch the per-UF candidate photo ZIPs (for mirror-photos) instead of the datasets",
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
    validate_parser.add_argument(
        "--previous-index-dir", type=Path, help="previously published index for per-round counts"
    )
    validate_parser.add_argument(
        "--photo-public-domain",
        help="require photo_url to use this exact public base URL and its content-addressed key",
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

    current_index_parser = stages.add_parser(
        "current-index", help="download and verify the currently published immutable index pair"
    )
    _add_bucket_arguments(current_index_parser)
    current_index_parser.add_argument("--output-dir", type=Path, required=True)

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
        help="directory of the foto_cand<year>_<UF>_div.zip files (`fetch --photos`), all of them",
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
    mirror_parser.add_argument(
        "--retain-old-photos",
        action="store_true",
        help="do not prune objects before index publication",
    )
    mirror_parser.add_argument(
        "--mark-full-load-complete",
        action="store_true",
        help="write the verified R2 completion marker after the one-time full load",
    )

    load_status_parser = stages.add_parser(
        "photo-load-status", help="succeed only after the full photo load completed in R2"
    )
    load_status_parser.add_argument("--r2-endpoint", required=True)
    load_status_parser.add_argument("--r2-bucket", required=True)
    load_status_parser.add_argument("--r2-access-key-id", required=True)
    load_status_parser.add_argument("--r2-secret-access-key", required=True)
    load_status_parser.add_argument("--r2-prefix", default="")
    load_status_parser.add_argument("--require-incomplete", action="store_true")

    retain_parser = stages.add_parser(
        "retain-photos", help="copy previously published URLs verified against TSE and R2"
    )
    retain_parser.add_argument("--zips-dir", type=Path, required=True)
    retain_parser.add_argument("--index-dir", type=Path, required=True)
    retain_parser.add_argument("--previous-index-dir", type=Path, required=True)
    retain_parser.add_argument("--public-domain", required=True)
    retain_parser.add_argument("--r2-endpoint", required=True)
    retain_parser.add_argument("--r2-bucket", required=True)
    retain_parser.add_argument("--r2-access-key-id", required=True)
    retain_parser.add_argument("--r2-secret-access-key", required=True)
    retain_parser.add_argument("--r2-prefix", default="")

    clean_parser = stages.add_parser(
        "clean-photos",
        help="after publish, delete R2 photos no index current in the grace window references",
    )
    clean_parser.add_argument(
        "--index-dir", type=Path, required=True, help="the pair this run just published"
    )
    clean_parser.add_argument(
        "--previous-index-dir",
        type=Path,
        required=True,
        help="the pair current before this run's publish, as current-index downloaded it",
    )
    clean_parser.add_argument("--public-domain", required=True)
    clean_parser.add_argument("--r2-endpoint", required=True)
    clean_parser.add_argument("--r2-bucket", required=True)
    clean_parser.add_argument("--r2-access-key-id", required=True)
    clean_parser.add_argument("--r2-secret-access-key", required=True)
    clean_parser.add_argument("--r2-prefix", default="")
    _add_bucket_arguments(clean_parser)
    clean_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what is due and update the ledger, but delete nothing",
    )
    clean_parser.add_argument(
        "--max-delete-fraction",
        type=_fraction,
        default=MAX_DELETE_FRACTION,
        help=f"refuse above this fraction of the photo objects (default: {MAX_DELETE_FRACTION})",
    )

    verify_parser = stages.add_parser("verify-photos", help="check the index photo URL chain")
    verify_parser.add_argument("--index-dir", type=Path, required=True)
    verify_parser.add_argument("--public-domain", required=True)
    return parser


def _fraction(value: str) -> float:
    fraction = float(value)
    if not 0 <= fraction <= 1:
        raise argparse.ArgumentTypeError(f"must be between 0 and 1, got {value}")
    return fraction


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
    if args.photos:
        datasets = CANDIDATE_PHOTOS_2026
    elif args.datasets:
        datasets = tuple(dataset_by_id(name) for name in args.datasets)
    else:
        datasets = DATASETS
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
    previous_manifest_path = args.previous_manifest or (
        args.previous_index_dir / MANIFEST_FILE_NAME if args.previous_index_dir else None
    )
    previous_manifest = read_manifest(previous_manifest_path) if previous_manifest_path else None
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
            previous_index_dir=args.previous_index_dir,
            photo_public_domain=args.photo_public_domain,
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


def _run_current_index(args: argparse.Namespace) -> int:
    try:
        present = download_current_index(_bucket_client(args), args.output_dir, prefix=args.prefix)
    except PublishError as exc:
        print(f"current-index failed: {exc}", file=sys.stderr)
        return 1
    print("current index verified" if present else "no index is published yet")
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


def _candidate_ufs(index_dir: Path) -> dict[int, str]:
    conn = duckdb.connect(str(index_dir / INDEX_FILE_NAME), read_only=True)
    try:
        rows = conn.execute("SELECT DISTINCT sq_candidato, uf FROM candidates").fetchall()
    finally:
        conn.close()
    candidate_ufs: dict[int, str] = {}
    for sq_candidato, uf in rows:
        previous_uf = candidate_ufs.get(sq_candidato)
        if previous_uf is not None and previous_uf != uf:
            raise MirrorError(
                f"sq_candidato {sq_candidato} has conflicting index UFs {previous_uf} and {uf}"
            )
        candidate_ufs[sq_candidato] = uf
    return candidate_ufs


def _photo_bucket(args: argparse.Namespace) -> R2BucketClient:
    return R2BucketClient(
        endpoint_url=args.r2_endpoint,
        bucket=args.r2_bucket,
        access_key_id=args.r2_access_key_id,
        secret_access_key=args.r2_secret_access_key,
        prefix=args.r2_prefix,
    )


def _complete_photo_zips(zips_dir: Path) -> list[PhotoZip]:
    zips = _iter_photo_zips(zips_dir)
    missing = sorted(
        {dataset.file_name for dataset in CANDIDATE_PHOTOS_2026} - {zip_.path.name for zip_ in zips}
    )
    if missing:
        raise MirrorError(
            f"{len(missing)} of {len(CANDIDATE_PHOTOS_2026)} photo ZIPs missing from "
            f"{zips_dir} ({', '.join(missing)}); refusing a partial set"
        )
    return zips


def _run_retain_photos(args: argparse.Namespace) -> int:
    previous_path = args.previous_index_dir / INDEX_FILE_NAME
    if not previous_path.is_file():
        print("no previous index; no photo URLs to retain")
        return 0
    try:
        verify_index_pair(args.previous_index_dir)
        zips = _complete_photo_zips(args.zips_dir)
        problems = photo_problems(previous_path, args.public_domain)
        if problems:
            raise MirrorError("previous index photo chain: " + "; ".join(problems))
        problems = photo_problems(args.index_dir / INDEX_FILE_NAME, "")
        if problems:
            raise MirrorError("new index photo chain: " + "; ".join(problems))
        conn = duckdb.connect(str(previous_path), read_only=True)
        try:
            rows = conn.execute(
                "SELECT DISTINCT sq_candidato, photo_url, photo_sha256 FROM candidates "
                "WHERE photo_url IS NOT NULL"
            ).fetchall()
        finally:
            conn.close()
        previous = {sq: (url, digest) for sq, url, digest in rows}
        urls, digests = verified_previous_photos(
            zips,
            _photo_bucket(args),
            public_domain=args.public_domain,
            candidate_ufs=_candidate_ufs(args.index_dir),
            previous=previous,
        )
        if urls:
            apply_photo_urls(args.index_dir, urls, digests)
        problems = photo_problems(args.index_dir / INDEX_FILE_NAME, args.public_domain)
        if problems:
            raise MirrorError("retained index photo chain: " + "; ".join(problems))
    except (MirrorError, OSError, PublishError) as exc:
        print(f"retain-photos failed: {exc}", file=sys.stderr)
        return 1
    print(f"retained {len(urls)} verified photo URLs from {len(previous)} previously published")
    return 0


def _run_verify_photos(args: argparse.Namespace) -> int:
    problems = photo_problems(args.index_dir / INDEX_FILE_NAME, args.public_domain)
    if problems:
        print(f"verify-photos failed: {'; '.join(problems)}", file=sys.stderr)
        return 1
    print("photo chain verified")
    return 0


def _run_clean_photos(args: argparse.Namespace) -> int:
    domain_problem = photo_public_domain_problem(args.public_domain)
    if domain_problem:
        print(f"clean-photos failed: {domain_problem}", file=sys.stderr)
        return 1
    mode = "dry run" if args.dry_run else "delete"
    try:
        result = clean_photos(
            args.index_dir,
            args.previous_index_dir,
            _photo_bucket(args),
            _bucket_client(args),
            public_domain=args.public_domain,
            prefix=args.prefix,
            dry_run=args.dry_run,
            max_delete_fraction=args.max_delete_fraction,
            progress=lambda message: print(message, flush=True),
        )
    except (PhotoCleanupError, PublishError, OSError) as exc:
        print(f"clean-photos ({mode}) refused: {exc}", file=sys.stderr)
        return 1
    plan = result.plan
    grace_hours = int(CLEANUP_GRACE.total_seconds() // 3600)
    print(
        f"clean-photos ({mode}): {plan.photo_objects} photo objects, "
        f"{len(plan.ledger.unreferenced_since)} referenced by neither the published nor the "
        f"previous pair, {len(plan.due)} unreferenced for {grace_hours} h or more; "
        f"ledger {'carried' if plan.chain_intact else 'restarted'}; "
        f"{plan.other_objects} objects outside the photo key format left untouched"
    )
    if args.dry_run:
        sample = f", e.g. {', '.join(plan.due[:3])}" if plan.due else ""
        print(f"clean-photos (dry run): would delete {len(plan.due)}{sample}; deleted 0")
    else:
        print(f"clean-photos (delete): deleted {len(result.deleted)}")
    return 0


def _run_photo_load_status(args: argparse.Namespace) -> int:
    try:
        complete = full_photo_load_complete(_photo_bucket(args))
    except MirrorError as exc:
        print(f"photo-load-status failed: {exc}", file=sys.stderr)
        return 2
    print("full photo load complete" if complete else "full photo load has not completed")
    if args.require_incomplete:
        return 1 if complete else 0
    return 0 if complete else 3


def _run_mirror_photos(args: argparse.Namespace) -> int:
    try:
        zips = _complete_photo_zips(args.zips_dir)
    except MirrorError as exc:
        print(f"mirror-photos refused: {exc}", file=sys.stderr)
        return 1
    domain_problem = photo_public_domain_problem(args.public_domain)
    if domain_problem:
        print(f"mirror-photos failed: {domain_problem}", file=sys.stderr)
        return 1
    problems = photo_problems(args.index_dir / INDEX_FILE_NAME, args.public_domain)
    if problems:
        print(f"mirror-photos failed: {'; '.join(problems)}", file=sys.stderr)
        return 1
    try:
        candidate_ufs = _candidate_ufs(args.index_dir)
        planned_rows = planned_photo_rows(
            zips, public_domain=args.public_domain, candidate_ufs=candidate_ufs
        )
    except MirrorError as exc:
        print(f"mirror-photos failed: {exc}", file=sys.stderr)
        return 1
    problems = photo_rows_problems(planned_rows, args.public_domain)
    if problems:
        print(f"mirror-photos failed: {'; '.join(problems)}", file=sys.stderr)
        return 1
    bucket = _photo_bucket(args)
    try:
        result = mirror_photos(
            zips,
            bucket,
            public_domain=args.public_domain,
            candidate_ufs=candidate_ufs,
            prune=not args.retain_old_photos,
            progress=lambda message: print(message, flush=True),
        )
    except MirrorError as exc:
        print(f"mirror-photos failed: {exc}", file=sys.stderr)
        return 1
    apply_photo_urls(args.index_dir, result.photo_urls, result.photo_sha256s)
    problems = photo_problems(args.index_dir / INDEX_FILE_NAME, args.public_domain)
    if problems:
        print(f"mirror-photos failed: {'; '.join(problems)}", file=sys.stderr)
        return 1
    if args.mark_full_load_complete:
        try:
            mark_full_photo_load_complete(bucket)
        except MirrorError as exc:
            print(f"mirror-photos failed: {exc}", file=sys.stderr)
            return 1
        print("full photo load marked complete in R2", flush=True)
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
    if args.stage == "current-index":
        return _run_current_index(args)
    if args.stage == "publish":
        return _run_publish(args)
    if args.stage == "mirror-photos":
        return _run_mirror_photos(args)
    if args.stage == "retain-photos":
        return _run_retain_photos(args)
    if args.stage == "clean-photos":
        return _run_clean_photos(args)
    if args.stage == "verify-photos":
        return _run_verify_photos(args)
    if args.stage == "photo-load-status":
        return _run_photo_load_status(args)
    raise AssertionError(f"unhandled stage {args.stage!r}")


if __name__ == "__main__":
    sys.exit(main())
