"""The pipeline command line: ``build`` with every input file, file in, file out."""

from __future__ import annotations

from pathlib import Path

import pytest

from br_elections_mcp.index_schema import INDEX_FILE_NAME, MANIFEST_FILE_NAME, read_manifest
from br_elections_mcp.pipeline.__main__ import main
from tests.conftest import (
    ACRE_CANDIDATES,
    ACRE_CANDIDATES_COMPLEMENTARY,
    ACRE_MUNICIPALITIES,
    ACRE_POLLING_PLACES,
    ACRE_SOCIAL_LINKS,
    ELECTIONS_FILE,
)


def _build_args(output: Path) -> list[str]:
    return [
        "build",
        "--polling-places",
        str(ACRE_POLLING_PLACES),
        "--municipalities",
        str(ACRE_MUNICIPALITIES),
        "--candidates",
        str(ACRE_CANDIDATES),
        "--candidates-complementary",
        str(ACRE_CANDIDATES_COMPLEMENTARY),
        "--social-links",
        str(ACRE_SOCIAL_LINKS),
        "--output-dir",
        str(output),
    ]


def test_build_command_writes_the_index_with_candidates(tmp_path: Path, capsys):
    assert main(_build_args(tmp_path)) == 0
    assert (tmp_path / INDEX_FILE_NAME).is_file()
    manifest = read_manifest(tmp_path / MANIFEST_FILE_NAME)
    assert manifest.counts["candidates"] == 23
    assert set(manifest.datasets) == {
        "polling_places",
        "municipalities",
        "candidates",
        "candidates_complementary",
        "candidate_social_links",
    }
    assert "'candidates': 23" in capsys.readouterr().out


def test_build_command_requires_the_candidate_files(tmp_path: Path):
    args = _build_args(tmp_path)
    del args[args.index("--candidates") : args.index("--candidates") + 2]
    with pytest.raises(SystemExit):
        main(args)


def test_build_command_reports_a_build_error_and_returns_1(tmp_path: Path, capsys):
    broken = tmp_path / "consulta_cand_2026_BRASIL.csv"
    broken.write_bytes(ACRE_CANDIDATES.read_bytes().replace(b'"SENADOR"', b'"SENADORA"', 1))
    args = _build_args(tmp_path / "out")
    args[args.index("--candidates") + 1] = str(broken)
    assert main(args) == 1
    assert "SENADORA" in capsys.readouterr().err


def _validate_args(index_dir: Path, output: Path) -> list[str]:
    return [
        "validate",
        "--polling-places",
        str(ACRE_POLLING_PLACES),
        "--municipalities",
        str(ACRE_MUNICIPALITIES),
        "--candidates",
        str(ACRE_CANDIDATES),
        "--candidates-complementary",
        str(ACRE_CANDIDATES_COMPLEMENTARY),
        "--social-links",
        str(ACRE_SOCIAL_LINKS),
        "--index-dir",
        str(index_dir),
        "--elections",
        str(ELECTIONS_FILE),
        "--output-dir",
        str(output),
    ]


def test_validate_command_passes_every_gate_over_a_clean_index(tmp_path: Path, capsys):
    assert main(_build_args(tmp_path / "out")) == 0
    assert main(_validate_args(tmp_path / "out", tmp_path / "out")) == 0
    assert (tmp_path / "out" / "validation_report.json").is_file()
    assert "every gate passed" in capsys.readouterr().out


def test_validate_command_reports_a_failed_gate_and_returns_1(tmp_path: Path, capsys):
    assert main(_build_args(tmp_path / "out")) == 0
    broken = tmp_path / "consulta_cand_2026_BRASIL.csv"
    broken.write_bytes(ACRE_CANDIDATES.read_bytes().replace(b'"SENADOR"', b'"SENADORA"', 1))
    args = _validate_args(tmp_path / "out", tmp_path / "out")
    args[args.index("--candidates") + 1] = str(broken)
    assert main(args) == 1
    assert "office_text_known" in capsys.readouterr().err


def test_extract_command_prints_the_extracted_csv_path(tmp_path: Path, capsys):
    import zipfile

    archive = tmp_path / "consulta_cand_2026.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("consulta_cand_2026_AC.csv", "ac")
        zf.writestr("consulta_cand_2026_BRASIL.csv", "brasil")
    assert main(["extract", "--zip", str(archive), "--output-dir", str(tmp_path / "csv")]) == 0
    assert capsys.readouterr().out.strip() == str(
        tmp_path / "csv" / "consulta_cand_2026_BRASIL.csv"
    )


def test_extract_command_reports_an_extract_error_and_returns_1(tmp_path: Path, capsys):
    assert main(["extract", "--zip", str(tmp_path / "x.zip"), "--output-dir", str(tmp_path)]) == 1
    assert "not found" in capsys.readouterr().err


def _publish_args(index_dir: Path, bucket_dir: Path, prefix: str | None = None) -> list[str]:
    args = ["publish", "--index-dir", str(index_dir), "--local-bucket", str(bucket_dir)]
    if prefix is not None:
        args += ["--prefix", prefix]
    return args


def test_publish_command_writes_the_current_pair_and_the_versioned_pair(tmp_path: Path, capsys):
    assert main(_build_args(tmp_path / "out")) == 0
    bucket = tmp_path / "bucket"
    assert main(_publish_args(tmp_path / "out", bucket, prefix="index")) == 0
    manifest = read_manifest(tmp_path / "out" / MANIFEST_FILE_NAME)
    assert (bucket / "index" / MANIFEST_FILE_NAME).read_bytes() == (
        tmp_path / "out" / MANIFEST_FILE_NAME
    ).read_bytes()
    assert (bucket / "index" / INDEX_FILE_NAME).is_file()
    versions = sorted(p.name for p in (bucket / "index" / "versions").iterdir())
    assert len(versions) == 1
    assert versions[0].endswith(manifest.index_sha256[:12])
    out = capsys.readouterr().out
    assert versions[0] in out
    assert manifest.index_sha256 in out
    assert (tmp_path / "out" / "publish.json").is_file()


def test_publish_command_requires_exactly_one_bucket(tmp_path: Path, capsys):
    assert main(_build_args(tmp_path / "out")) == 0
    with pytest.raises(SystemExit):
        main(["publish", "--index-dir", str(tmp_path / "out")])
    with pytest.raises(SystemExit):
        main(
            [
                "publish",
                "--index-dir",
                str(tmp_path / "out"),
                "--local-bucket",
                str(tmp_path / "b"),
                "--bucket",
                "gs-bucket",
            ]
        )


def test_publish_command_reports_a_publish_error_and_returns_1(tmp_path: Path, capsys):
    assert main(_build_args(tmp_path / "out")) == 0
    (tmp_path / "out" / INDEX_FILE_NAME).unlink()
    assert main(_publish_args(tmp_path / "out", tmp_path / "bucket")) == 1
    assert "not found" in capsys.readouterr().err
    assert not (tmp_path / "bucket").exists() or not any((tmp_path / "bucket").iterdir())


def test_current_manifest_command_downloads_the_published_manifest(tmp_path: Path, capsys):
    assert main(_build_args(tmp_path / "out")) == 0
    bucket = tmp_path / "bucket"
    assert main(_publish_args(tmp_path / "out", bucket)) == 0
    target = tmp_path / "previous" / "manifest.json"
    assert main(["current-manifest", "--local-bucket", str(bucket), "--output", str(target)]) == 0
    assert read_manifest(target) == read_manifest(tmp_path / "out" / MANIFEST_FILE_NAME)
    assert str(target) in capsys.readouterr().out


def test_current_manifest_command_succeeds_without_a_file_when_nothing_is_published(
    tmp_path: Path, capsys
):
    target = tmp_path / "previous" / "manifest.json"
    assert (
        main(
            ["current-manifest", "--local-bucket", str(tmp_path / "empty"), "--output", str(target)]
        )
        == 0
    )
    assert not target.exists()
    assert "no manifest" in capsys.readouterr().out
