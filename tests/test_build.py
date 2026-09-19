"""The ``build`` stage by file in, file out."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
import pytest

from br_elections_mcp.index_schema import (
    INDEX_FILE_NAME,
    MANIFEST_FILE_NAME,
    TABLES,
    read_manifest,
)
from br_elections_mcp.pipeline.build import BuildError
from br_elections_mcp.pipeline.datasets import POLLING_PLACES_2026, POLLING_PLACES_CURRENT
from tests.conftest import ACRE_POLLING_PLACES, BUILT_AT, build_fixture_index

SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def test_build_writes_index_and_manifest_from_the_acre_fixtures(acre_index_dir: Path):
    assert (acre_index_dir / INDEX_FILE_NAME).is_file()
    assert not (acre_index_dir / f"{INDEX_FILE_NAME}.tmp").exists()
    manifest = read_manifest(acre_index_dir / MANIFEST_FILE_NAME)

    assert manifest.index_built_at == BUILT_AT
    assert manifest.counts == {"municipalities": 2, "polling_places": 3, "polling_sections": 6}
    assert manifest.election_year == 2026
    assert manifest.election_dates == {1: dt.date(2026, 10, 4)}
    assert len(manifest.index_sha256) == 64

    places = manifest.datasets["polling_places"]
    assert places.dataset == POLLING_PLACES_2026.title
    assert places.dataset_url == POLLING_PLACES_2026.dataset_url
    assert places.file == "eleitorado_local_votacao_2026_AC.csv"
    # DT_GERACAO + HH_GERACAO of the file, in America/Sao_Paulo
    assert places.generated_at == dt.datetime(2026, 9, 17, 6, 30, 20, tzinfo=SAO_PAULO)
    assert manifest.datasets["municipalities"].file == "municipio_tse_ibge.csv"


def test_index_has_exactly_the_shared_schema_tables(acre_index_dir: Path):
    conn = duckdb.connect(str(acre_index_dir / INDEX_FILE_NAME), read_only=True)
    try:
        tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
        assert tables == set(TABLES)
        counts = conn.execute(
            "SELECT number, section_count, accessible_section_count, voters "
            "FROM polling_places WHERE uf = 'AC' AND zone = 9 AND number = 1000"
        ).fetchone()
        assert counts == (1000, 3, 2, 260 + 251 + 38)
        no_coordinates = conn.execute(
            "SELECT latitude, longitude, phone, status FROM polling_places WHERE number = 1015"
        ).fetchone()
        assert no_coordinates == (None, None, None, "bloqueado")
    finally:
        conn.close()


def test_monthly_snapshot_has_no_election_in_the_manifest(tmp_path: Path):
    manifest = build_fixture_index(tmp_path, dataset=POLLING_PLACES_CURRENT)
    assert manifest.election_year is None
    assert manifest.election_dates is None
    assert manifest.datasets["polling_places"].dataset == POLLING_PLACES_CURRENT.title


def test_missing_expected_column_fails_loudly(tmp_path: Path):
    broken = tmp_path / "eleitorado_local_votacao_2026_AC.csv"
    broken.write_bytes(ACRE_POLLING_PLACES.read_bytes().replace(b'"NR_SECAO"', b'"NR_SECAO_X"', 1))
    with pytest.raises(BuildError, match="NR_SECAO"):
        build_fixture_index(tmp_path / "out", polling_places=broken)
    assert not (tmp_path / "out" / INDEX_FILE_NAME).exists()


def test_unknown_accessibility_text_fails_loudly(tmp_path: Path):
    broken = tmp_path / "eleitorado_local_votacao_2026_AC.csv"
    broken.write_bytes(
        ACRE_POLLING_PLACES.read_bytes().replace(b'"COM ACESSIBILIDADE"', b'"TALVEZ"', 1)
    )
    with pytest.raises(BuildError, match="TALVEZ"):
        build_fixture_index(tmp_path / "out", polling_places=broken)
