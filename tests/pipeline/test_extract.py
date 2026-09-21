"""``extract``: the one CSV ``build`` reads, taken out of a TSE ZIP."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from br_elections_mcp.pipeline.extract import ExtractError, extract_csv


def _zip(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return path


def test_extract_prefers_the_brasil_file_over_the_per_uf_files(tmp_path: Path):
    archive = _zip(
        tmp_path / "consulta_cand_2026.zip",
        {
            "consulta_cand_2026_AC.csv": b"ac",
            "consulta_cand_2026_BRASIL.csv": b"brasil",
            "consulta_cand_2026_SP.csv": b"sp",
            "leiame.pdf": b"pdf",
        },
    )
    extracted = extract_csv(archive, tmp_path / "csv")
    assert extracted == tmp_path / "csv" / "consulta_cand_2026_BRASIL.csv"
    assert extracted.read_bytes() == b"brasil"
    assert sorted(p.name for p in (tmp_path / "csv").iterdir()) == ["consulta_cand_2026_BRASIL.csv"]


def test_extract_takes_the_only_csv_when_there_is_no_brasil_file(tmp_path: Path):
    archive = _zip(
        tmp_path / "municipio_tse_ibge.zip",
        {"municipio_tse_ibge.csv": b"crosswalk", "leiame.pdf": b"pdf"},
    )
    extracted = extract_csv(archive, tmp_path / "csv")
    assert extracted.name == "municipio_tse_ibge.csv"
    assert extracted.read_bytes() == b"crosswalk"


def test_extract_fails_when_several_csvs_and_no_brasil_file(tmp_path: Path):
    archive = _zip(
        tmp_path / "x.zip", {"x_2026_AC.csv": b"ac", "x_2026_SP.csv": b"sp", "leiame.pdf": b""}
    )
    with pytest.raises(ExtractError, match=r"x_2026_AC\.csv"):
        extract_csv(archive, tmp_path / "csv")


def test_extract_fails_when_the_zip_has_no_csv(tmp_path: Path):
    archive = _zip(tmp_path / "x.zip", {"leiame.pdf": b""})
    with pytest.raises(ExtractError, match="no CSV"):
        extract_csv(archive, tmp_path / "csv")


def test_extract_fails_on_a_missing_or_invalid_zip(tmp_path: Path):
    with pytest.raises(ExtractError, match="not found"):
        extract_csv(tmp_path / "missing.zip", tmp_path / "csv")
    broken = tmp_path / "broken.zip"
    broken.write_bytes(b"not a zip")
    with pytest.raises(ExtractError, match="not a ZIP"):
        extract_csv(broken, tmp_path / "csv")


def test_extract_writes_the_member_under_its_base_name_only(tmp_path: Path):
    """A member path inside the archive never escapes the output directory."""
    archive = _zip(tmp_path / "x.zip", {"nested/dir/x_2026_BRASIL.csv": b"brasil"})
    extracted = extract_csv(archive, tmp_path / "csv")
    assert extracted == tmp_path / "csv" / "x_2026_BRASIL.csv"
    assert extracted.read_bytes() == b"brasil"
