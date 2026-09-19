"""LGPD contract (ADR 0004): no forbidden column in the index, no forbidden key in any answer."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from br_elections_mcp.index_schema import FORBIDDEN_COLUMNS, INDEX_FILE_NAME, TABLES
from tests.conftest import ACRE_LGPD_POLLING_PLACES, build_fixture_index, open_core

EXPECTED_FORBIDDEN = {
    "NR_CPF_CANDIDATO",
    "NR_TITULO_ELEITORAL_CANDIDATO",
    "DT_NASCIMENTO",
    "SG_UF_NASCIMENTO",
    "DS_EMAIL",
}


def test_the_forbidden_list_is_exactly_the_one_decided_in_adr_0004():
    assert FORBIDDEN_COLUMNS == EXPECTED_FORBIDDEN


@pytest.fixture(scope="module")
def lgpd_index_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("lgpd-index")
    header = ACRE_LGPD_POLLING_PLACES.read_bytes().split(b"\n", 1)[0].decode("latin-1")
    assert all(column in header for column in FORBIDDEN_COLUMNS), "fixture must carry them"
    build_fixture_index(directory, polling_places=ACRE_LGPD_POLLING_PLACES)
    return directory


def test_no_forbidden_column_exists_in_the_built_index(lgpd_index_dir: Path):
    conn = duckdb.connect(str(lgpd_index_dir / INDEX_FILE_NAME), read_only=True)
    try:
        for table in TABLES:
            columns = {row[0] for row in conn.execute(f"DESCRIBE {table}").fetchall()}
            assert not {c.upper() for c in columns} & FORBIDDEN_COLUMNS, table
        # Neither the tables nor any leftover view or column anywhere in the file.
        all_columns = {
            row[0].upper()
            for row in conn.execute("SELECT column_name FROM information_schema.columns").fetchall()
        }
        assert not all_columns & FORBIDDEN_COLUMNS
    finally:
        conn.close()


def test_no_forbidden_key_appears_in_any_serialized_answer(lgpd_index_dir: Path):
    core = open_core(lgpd_index_dir)
    try:
        answers = [
            core.find_polling_place("AC", 9, 422),
            core.find_polling_place("AC", 9, 424),
            core.find_polling_place("AC", 9, 100),
            core.find_polling_place("AC", 1, 99999),
        ]
    finally:
        core.close()
    for answer in answers:
        serialized = json.dumps(answer.model_dump(mode="json"), ensure_ascii=False)
        for column in FORBIDDEN_COLUMNS:
            assert column not in serialized.upper()
        assert "00000000000" not in serialized  # the placeholder CPF of the fixture
