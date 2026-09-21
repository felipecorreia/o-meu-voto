"""``Core.find_polling_place`` through its interface, over the Acre fixture index."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from br_elections_mcp.core import Core, IndexUnavailable, InvalidQuery
from br_elections_mcp.core.core import SECTION_NOT_FOUND_GUIDANCE
from br_elections_mcp.index_store import LocalDirectoryIndexSource
from br_elections_mcp.pipeline.datasets import POLLING_PLACES_2026, POLLING_PLACES_CURRENT
from tests.conftest import (
    ACRE_POLLING_PLACES,
    BUILT_AT,
    ELECTIONS_FILE,
    build_fixture_index,
    fixed_clock,
    open_core,
)

SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def test_scenario_1_title_in_hand(core: Core):
    answer = core.find_polling_place("AC", 9, 422)

    assert answer.not_found is None
    assert answer.warnings == []
    data = answer.data
    assert data is not None
    assert data.municipality.model_dump() == {
        "tse_code": "01392",
        "ibge_code": 1200401,
        "name": "RIO BRANCO",
        "uf": "AC",
    }
    assert (data.round, data.zone, data.section) == (1, 9, 422)
    assert data.section_kind == "principal"
    assert data.votes_at_section == 422
    assert data.voters_in_section == 260
    assert data.accessibility == "com_acessibilidade"
    assert data.previous_place is None
    place = data.place
    assert place.number == 1000
    assert place.name == "IEPTEC - ANTIGO INSTITUTO FEDERAL DO ACRE - IFAC - BAIXADA"
    assert place.kind == "Convencional"
    assert place.address == "RUA RIO GRANDE DO SUL, 2600"
    assert place.neighborhood == "AEROPORTO VELHO"
    assert place.postal_code == "69911030"
    assert place.phone is None
    assert (place.latitude, place.longitude) == (-9.9848126, -67.8225501)
    assert place.status == "ativo"
    assert (place.section_count, place.accessible_section_count) == (3, 2)


def test_scenario_2_aggregated_section_votes_at_the_main_section_same_place(core: Core):
    answer = core.find_polling_place("AC", 9, 424)

    assert answer.data is not None
    assert answer.data.section_kind == "agregada"
    assert answer.data.votes_at_section == 422
    assert answer.data.place.number == 1000
    assert answer.warnings == [
        "Sua seção é agregada: a votação acontece na seção 422, no mesmo local."
    ]


def test_scenario_3_place_changed_carries_the_previous_place_and_the_warning(core: Core):
    answer = core.find_polling_place("AC", 9, 100)

    assert answer.data is not None
    assert answer.data.place.number == 1035
    assert answer.data.previous_place is not None
    assert answer.data.previous_place.model_dump() == {
        "number": 1027,
        "name": "EMEF ANTÔNIO FERREIRA",
        "address": "RUA DO ALTO, 80",
    }
    assert answer.warnings == [
        "O local de votação mudou. Antes era EMEF ANTÔNIO FERREIRA, endereço RUA DO ALTO, 80."
    ]


def test_scenario_6_section_not_found_is_an_answer_with_guidance(core: Core):
    answer = core.find_polling_place("AC", 1, 99999)

    assert answer.data is None
    assert answer.not_found is not None
    assert answer.not_found.reason == "secao_nao_encontrada"
    assert answer.not_found.guidance == SECTION_NOT_FOUND_GUIDANCE
    assert "e-Título" in answer.not_found.guidance
    assert answer.warnings == []
    # not_found still carries the envelope
    assert answer.election is not None
    assert answer.source.file == "eleitorado_local_votacao_2026_AC.csv"


def test_place_without_coordinates_and_blocked_status_is_reported_as_it_comes(core: Core):
    answer = core.find_polling_place("AC", 1, 7)
    assert answer.data is not None
    assert answer.data.place.latitude is None
    assert answer.data.place.longitude is None
    assert answer.data.place.status == "bloqueado"
    assert answer.data.municipality.name == "CRUZEIRO DO SUL"


@pytest.mark.parametrize("zone", ["009", 9, " 9 ", "9"])
@pytest.mark.parametrize("section", ["0422", 422, " 422 "])
@pytest.mark.parametrize("uf", ["ac", "AC", " Ac "])
def test_normalization_of_uf_zone_and_section(core: Core, uf, zone, section):
    answer = core.find_polling_place(uf, zone, section)
    assert answer.data is not None
    assert (answer.data.zone, answer.data.section, answer.data.municipality.uf) == (9, 422, "AC")


@pytest.mark.parametrize(
    ("uf", "zone", "section", "message"),
    [
        ("XX", 9, 422, "UF desconhecida"),
        ("BR", 9, 422, "UF sem seções"),
        ("", 9, 422, "UF desconhecida"),
        ("AC", "nove", 422, "zona inválida"),
        ("AC", 0, 422, "zona inválida"),
        ("AC", 9, "", "seção inválida"),
        ("AC", 9, -1, "seção inválida"),
    ],
)
def test_input_outside_the_domain_is_invalid_query(core: Core, uf, zone, section, message):
    with pytest.raises(InvalidQuery, match=message):
        core.find_polling_place(uf, zone, section)


def test_every_answer_carries_source_and_election(core: Core):
    for args in [("AC", 9, 422), ("AC", 1, 99999)]:
        answer = core.find_polling_place(*args)
        source = answer.source
        assert source.kind == "dataset"
        assert source.dataset == POLLING_PLACES_2026.title
        assert source.dataset_url == POLLING_PLACES_2026.dataset_url
        assert source.file == "eleitorado_local_votacao_2026_AC.csv"
        assert source.generated_at == dt.datetime(2026, 9, 17, 6, 30, 20, tzinfo=SAO_PAULO)
        assert source.index_built_at == BUILT_AT
        assert source.license == "CC-BY"
        assert source.attribution == "Tribunal Superior Eleitoral - Portal de Dados Abertos"

        election = answer.election
        assert election is not None
        assert election.id == "general-2026"
        assert election.name == "Eleições Gerais 2026"
        assert election.round.model_dump() == {"number": 1, "date": dt.date(2026, 10, 4)}
        assert election.voting_hours.model_dump() == {
            "start": "08:00",
            "end": "17:00",
            "timezone": "America/Sao_Paulo",
            "label": "8h às 17h (horário de Brasília)",
        }


# Round handling: the table of codebase-design 3.4 is exercised line by line in
# tests/test_core_rounds.py; these keep the tracer-bullet cases over the shared index.


def test_round_absent_answers_the_next_round_of_the_election(core: Core):
    # Before round 1, the next round is round 1, published: T1.
    answer = core.find_polling_place("AC", 9, 422)
    assert answer.data is not None
    assert answer.data.round == 1
    assert answer.election is not None
    assert answer.election.round.number == 1


def test_round_explicit_and_published_answers_that_round(core: Core):
    for requested, expected in (("1", 1), (2, 2)):
        answer = core.find_polling_place("AC", 9, 422, round=requested)
        assert answer.data is not None
        assert answer.data.round == expected
        assert answer.warnings == []


def test_round_explicit_and_not_published_answers_the_highest_published_round(
    acre_round_1_index_dir: Path,
):
    # Round 2 is a calendar round; this index has only round 1. Never not_found (T4).
    core = open_core(acre_round_1_index_dir)
    try:
        answer = core.find_polling_place("AC", 9, 422, round=2)
    finally:
        core.close()
    assert answer.data is not None
    assert answer.data.round == 1
    assert answer.warnings == [
        "O TSE ainda não publicou os locais do 2º turno; este é o local do 1º turno. "
        "Confira de novo perto da data."
    ]


@pytest.mark.parametrize("round_", [0, 3, "x", "-1"])
def test_round_outside_the_calendar_is_invalid_query(core: Core, round_):
    with pytest.raises(InvalidQuery, match="turno inválido"):
        core.find_polling_place("AC", 9, 422, round=round_)


# The election-coincidence rule (codebase-design 3.4)


def test_election_is_null_when_the_manifest_dates_do_not_coincide_with_the_calendar(
    tmp_path: Path,
):
    shifted = tmp_path / "eleitorado_local_votacao_2026_AC.csv"
    shifted.write_bytes(ACRE_POLLING_PLACES.read_bytes().replace(b"04/10/2026", b"11/10/2026"))
    build_fixture_index(tmp_path / "index", polling_places=shifted)
    core = open_core(tmp_path / "index")
    try:
        answer = core.find_polling_place("AC", 9, 422)
    finally:
        core.close()
    assert answer.data is not None
    # Without a coincident election, the highest published round (T5).
    assert answer.data.round == 2
    assert answer.election is None


def test_election_is_null_when_the_index_comes_from_the_monthly_file(tmp_path: Path):
    build_fixture_index(tmp_path, dataset=POLLING_PLACES_CURRENT)
    core = open_core(tmp_path)
    try:
        answer = core.find_polling_place("AC", 9, 422)
    finally:
        core.close()
    assert answer.data is not None
    assert answer.election is None
    assert answer.source.dataset == POLLING_PLACES_CURRENT.title


def test_election_is_null_when_there_is_no_current_election(acre_index_dir: Path):
    after_last_round = dt.datetime(2026, 10, 26, 12, 0, tzinfo=SAO_PAULO)
    core = open_core(acre_index_dir, clock=fixed_clock(after_last_round))
    try:
        answer = core.find_polling_place("AC", 9, 422)
        assert answer.data is not None
        assert answer.election is None
        # Without a coincident election the calendar cannot bound the round; 1..2 applies.
        with pytest.raises(InvalidQuery):
            core.find_polling_place("AC", 9, 422, round=3)
    finally:
        core.close()


def test_election_uses_the_calendar_date_in_sao_paulo(acre_index_dir: Path):
    # 2026-10-05 01:00 UTC is still 2026-10-04 22:00 in São Paulo: round 1 has not passed.
    core = open_core(acre_index_dir, clock=fixed_clock(dt.datetime(2026, 10, 5, 1, tzinfo=dt.UTC)))
    try:
        assert core.find_polling_place("AC", 9, 422).election is not None
    finally:
        core.close()


# Lifecycle


def test_querying_before_open_is_index_unavailable(acre_index_dir: Path):
    core = Core(LocalDirectoryIndexSource(acre_index_dir), ELECTIONS_FILE)
    with pytest.raises(IndexUnavailable):
        core.find_polling_place("AC", 9, 422)
    core.close()


def test_missing_index_directory_is_index_unavailable(tmp_path: Path):
    core = Core(LocalDirectoryIndexSource(tmp_path / "missing"), ELECTIONS_FILE)
    with pytest.raises(IndexUnavailable):
        core.open_index()


def test_corrupted_index_file_is_index_unavailable(acre_index_dir: Path, tmp_path: Path):
    (tmp_path / "manifest.json").write_bytes((acre_index_dir / "manifest.json").read_bytes())
    (tmp_path / "index.duckdb").write_bytes(b"not a duckdb file")
    core = Core(LocalDirectoryIndexSource(tmp_path), ELECTIONS_FILE)
    with pytest.raises(IndexUnavailable):
        core.open_index()
