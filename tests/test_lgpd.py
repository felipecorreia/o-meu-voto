"""LGPD contract (ADR 0004): no forbidden column in the index, no forbidden key in any answer."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from br_elections_mcp.index_schema import FORBIDDEN_COLUMNS, INDEX_FILE_NAME, TABLES
from tests.conftest import (
    ACRE_CANDIDATE_ASSETS,
    ACRE_CANDIDATES,
    ACRE_LGPD_POLLING_PLACES,
    build_fixture_index,
    open_core,
)

# Placeholder values of the forbidden columns in the fixtures; none may reach an answer. The
# last ones are fragments of the free-text asset descriptions of bem_candidato (ADR 0009).
PLACEHOLDERS = (
    "00000000000",
    "000000000000",
    "01/01/1970",
    "NÃO DIVULGÁVEL",
    "1970-01-01",
    "RUA DAS FLORES",
    "PLACA",
    "AGÊNCIA",
    "CNPJ",
)

EXPECTED_FORBIDDEN = {
    "NR_CPF_CANDIDATO",
    "NR_TITULO_ELEITORAL_CANDIDATO",
    "DT_NASCIMENTO",
    "SG_UF_NASCIMENTO",
    "DS_EMAIL",
    "DS_BEM_CANDIDATO",
}


def test_the_forbidden_list_is_exactly_the_one_decided_in_adr_0004_and_0009():
    assert FORBIDDEN_COLUMNS == EXPECTED_FORBIDDEN


@pytest.fixture(scope="module")
def lgpd_index_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("lgpd-index")
    headers = [
        fixture.read_bytes().split(b"\n", 1)[0].decode("latin-1")
        for fixture in (ACRE_LGPD_POLLING_PLACES, ACRE_CANDIDATES, ACRE_CANDIDATE_ASSETS)
    ]
    for column in FORBIDDEN_COLUMNS:
        assert any(f'"{column}"' in header for header in headers), f"no fixture carries {column}"
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
            core.list_candidates("BR", "presidente"),
            core.list_candidates("AC", "governador", on_ballot_only=False),
            core.list_candidates("AC", "senador"),
            core.list_candidates("AC", "deputado_federal"),
            core.list_candidates("AC", "deputado_estadual"),
            core.get_candidate(10000000001),
            core.get_candidate(10000000005),
            core.get_candidate(uf="AC", office="senador", number=456),
            core.get_candidate(uf="BR", office="presidente", number=45),
            core.get_candidate(uf="AC", office="governador", number=22),
            core.search_polling_places("AC", "Rio Branco"),
            core.search_polling_places(
                "AC", "Cruzeiro do Sul", near={"latitude": -7.6, "longitude": -72.7}
            ),
            core.search_polling_places("AC", "Xanadu"),
            core.resolve_municipality("rio"),
            core.compare_candidates("AC", "governador"),
            core.compare_candidates("BR", "presidente", numbers=[13, 45, 22], round=1),
            core.compare_candidates("AC", "deputado_federal", numbers=[4512, 1313]),
        ]
    finally:
        core.close()
    assert any(a.data is not None and getattr(a.data, "total", 0) > 0 for a in answers)
    assert any(a.data is not None and hasattr(a.data, "candidate") for a in answers)
    for answer in answers:
        serialized = json.dumps(answer.model_dump(mode="json"), ensure_ascii=False)
        for column in FORBIDDEN_COLUMNS:
            assert column not in serialized.upper()
        for placeholder in PLACEHOLDERS:
            assert placeholder not in serialized
