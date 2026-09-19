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
    assert manifest.counts["candidates"] == 16
    assert set(manifest.datasets) == {
        "polling_places",
        "municipalities",
        "candidates",
        "candidates_complementary",
        "candidate_social_links",
    }
    assert "'candidates': 16" in capsys.readouterr().out


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
