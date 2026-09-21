"""``Core.list_candidates`` through its interface, over the Acre fixture index."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from br_elections_mcp.core import CandidateListItem, CandidatesAnswer, Core, InvalidQuery
from br_elections_mcp.pipeline.datasets import CANDIDATES_2026, POLLING_PLACES_CURRENT
from tests.conftest import BUILT_AT, build_fixture_index, fixed_clock, open_core

SAO_PAULO = ZoneInfo("America/Sao_Paulo")

LIST_ITEM_FIELDS = {
    "sq_candidato",
    "number",
    "ballot_name",
    "name",
    "office",
    "party",
    "federation",
    "coalition",
    "adjudication_status",
    "on_ballot",
    "occupation",
    "photo_url",
}
PROFILE_ONLY_FIELDS = {"gender", "race_color", "marital_status", "education"}


def numbers(answer: CandidatesAnswer) -> list[int]:
    assert answer.data is not None
    return [candidate.number for candidate in answer.data.candidates]


def test_scenario_9_president_is_asked_with_uf_br_and_lists_only_the_heads(core: Core):
    # Round 1 explicitly: the fixture also carries round 2 (presidents 22 and 45), which is
    # what the list answers without `round` (codebase-design 3.4, C1; tests/test_core_rounds.py).
    answer = core.list_candidates("BR", "presidente", round=1)

    assert answer.not_found is None
    assert answer.warnings == []
    data = answer.data
    assert data is not None
    assert (data.round, data.total, data.limit, data.offset) == (1, 3, 50, 0)
    assert numbers(answer) == [13, 22, 45]
    assert {candidate.office for candidate in data.candidates} == {"presidente"}

    thirteen = data.candidates[0]
    assert thirteen.model_dump() == {
        "sq_candidato": 20000000001,
        "number": 13,
        "ballot_name": "FERNANDO",
        "name": "FERNANDO AUGUSTO PEREIRA",
        "office": "presidente",
        "party": {"number": 13, "acronym": "PT", "name": "PARTIDO DOS TRABALHADORES"},
        "federation": {"acronym": "PT/PC do B/PV", "name": "BRASIL DA ESPERANÇA"},
        "coalition": None,
        "adjudication_status": "DEFERIDO",
        "on_ballot": True,
        "occupation": "ECONOMISTA",
        "photo_url": None,
    }
    forty_five = data.candidates[2]
    assert forty_five.federation is None
    assert forty_five.coalition is not None
    assert forty_five.coalition.name == "BRASIL EM FRENTE"
    assert forty_five.party.acronym == "PSDB"


def test_scenario_10_denied_candidate_on_the_ballot_is_listed_with_the_status_visible(core: Core):
    answer = core.list_candidates("AC", "governador")

    assert answer.data is not None
    assert answer.data.total == 2
    assert numbers(answer) == [13, 45]
    denied = answer.data.candidates[0]
    assert denied.ballot_name == "ZÉ ANTÔNIO"
    assert denied.adjudication_status == "INDEFERIDO EM PRAZO RECURSAL OU COM RECURSO"
    assert denied.on_ballot is True
    # The vice-governors share the numbers but are ticket offices, never listed here.
    assert all(candidate.office == "governador" for candidate in answer.data.candidates)


def test_on_ballot_only_false_includes_the_off_ballot_candidate(core: Core):
    answer = core.list_candidates("AC", "governador", on_ballot_only=False)

    assert answer.data is not None
    assert answer.data.total == 3
    assert numbers(answer) == [13, 22, 45]
    renounced = answer.data.candidates[1]
    assert renounced.on_ballot is False
    assert renounced.adjudication_status == "RENÚNCIA"
    assert renounced.federation is None
    assert renounced.coalition is None


@pytest.mark.parametrize("party", ["PSDB", "psdb", " Psdb ", "45", 45])
def test_party_filter_accepts_acronym_or_number(core: Core, party):
    answer = core.list_candidates("AC", "deputado_federal", party=party)
    assert answer.data is not None
    assert answer.data.total == 1
    assert numbers(answer) == [4512]


def test_party_filter_with_accented_acronym_is_accent_insensitive(core: Core):
    # "PC do B" is stored as the TSE prints it; the filter compares without accents or case.
    answer = core.list_candidates("AC", "governador", party="pc do b", on_ballot_only=False)
    assert answer.data is not None
    assert answer.data.total == 0
    assert answer.data.candidates == []


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("antonio", [13]),  # ballot name "ZÉ ANTÔNIO", accent and case insensitive
        ("ANTÔNIO", [13]),
        ("santos", [13]),  # civil name "JOSÉ ANTÔNIO DOS SANTOS"
        ("maria da", [45]),
        ("silva", [45]),
        ("xyz", []),
    ],
)
def test_name_filter_matches_ballot_or_civil_name_without_accents_or_case(core, name, expected):
    answer = core.list_candidates("AC", "governador", name=name)
    assert numbers(answer) == expected


def test_name_filter_with_apostrophe_and_like_metacharacters(core: Core):
    assert numbers(core.list_candidates("AC", "deputado_estadual", name="d'arc")) == [45123]
    assert numbers(core.list_candidates("AC", "deputado_estadual", name="%")) == []
    assert numbers(core.list_candidates("AC", "deputado_estadual", name="_")) == []


def test_pagination_returns_total_and_the_requested_page_in_number_order(core: Core):
    page = core.list_candidates("AC", "governador", on_ballot_only=False, limit=1, offset=1)

    assert page.data is not None
    assert (page.data.total, page.data.limit, page.data.offset) == (3, 1, 1)
    assert numbers(page) == [22]

    beyond = core.list_candidates("AC", "governador", limit=10, offset=10)
    assert beyond.data is not None
    assert (beyond.data.total, beyond.data.candidates) == (2, [])


@pytest.mark.parametrize("limit", ["50", " 50 ", 50])
def test_limit_accepts_strings_with_spaces(core: Core, limit):
    answer = core.list_candidates("AC", "governador", limit=limit, offset="0")
    assert answer.data is not None
    assert answer.data.limit == 50


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"limit": 51}, "limite inválido"),
        ({"limit": 0}, "limite inválido"),
        ({"limit": "dez"}, "limite inválido"),
        ({"offset": -1}, "deslocamento inválido"),
        ({"offset": "x"}, "deslocamento inválido"),
        ({"party": True}, "partido inválido"),
    ],
)
def test_limit_outside_1_50_and_negative_offset_are_invalid_query(core: Core, kwargs, message):
    with pytest.raises(InvalidQuery, match=message):
        core.list_candidates("AC", "governador", **kwargs)


@pytest.mark.parametrize(
    ("uf", "office", "message"),
    [
        ("AC", "prefeito", "cargo desconhecido"),
        ("AC", "", "cargo desconhecido"),
        ("AC", None, "cargo desconhecido"),
        ("AC", "vice_governador", "cargo de chapa"),
        ("AC", "presidente", "presidente"),
        ("BR", "governador", "BR"),
        ("AC", "deputado_distrital", "DF"),
        ("DF", "deputado_estadual", "DF"),
        ("ZZ", "senador", "UF"),
        ("XX", "senador", "UF desconhecida"),
    ],
)
def test_unknown_office_or_office_impossible_for_the_uf_is_invalid_query(core, uf, office, message):
    with pytest.raises(InvalidQuery, match=message):
        core.list_candidates(uf, office)


@pytest.mark.parametrize("office", ["deputado_federal", "Deputado Federal", " DEPUTADO-FEDERAL "])
@pytest.mark.parametrize("uf", ["ac", "AC", " Ac "])
def test_office_and_uf_are_normalized(core: Core, uf, office):
    answer = core.list_candidates(uf, office)
    assert numbers(answer) == [1313, 4512]


def test_empty_list_is_an_answer_not_a_not_found(core: Core):
    answer = core.list_candidates("AC", "senador", party="PT")
    assert answer.not_found is None
    assert answer.data is not None
    assert (answer.data.total, answer.data.candidates, answer.data.round) == (0, [], 1)
    assert answer.election is not None


def test_every_answer_carries_source_and_election(core: Core):
    for args in [("BR", "presidente", 1), ("AC", "senador", None)]:
        answer = core.list_candidates(*args[:2], round=args[2])
        source = answer.source
        assert source.kind == "dataset"
        assert source.dataset == CANDIDATES_2026.title
        assert source.dataset_url == CANDIDATES_2026.dataset_url
        assert source.file == "consulta_cand_2026_BRASIL.csv"
        assert source.generated_at == dt.datetime(2026, 9, 18, 22, 30, 5, tzinfo=SAO_PAULO)
        assert source.index_built_at == BUILT_AT
        assert source.license == "CC-BY"

        election = answer.election
        assert election is not None
        assert election.id == "general-2026"
        assert election.round.model_dump() == {"number": 1, "date": dt.date(2026, 10, 4)}


# Round handling: the table of codebase-design 3.4 is exercised line by line in
# tests/test_core_rounds.py; these keep the tracer-bullet cases over the shared index.


def test_round_absent_answers_the_highest_round_of_the_office(core: Core):
    answer = core.list_candidates("BR", "presidente")
    assert answer.data is not None
    assert answer.data.round == 2
    assert numbers(answer) == [22, 45]
    assert answer.election is not None
    assert answer.election.round.number == 2


def test_round_explicit_and_present_answers_that_round(core: Core):
    answer = core.list_candidates("BR", "presidente", round="1")
    assert answer.data is not None
    assert answer.data.round == 1


def test_round_explicit_and_absent_answers_the_highest_round_of_the_office(core: Core):
    answer = core.list_candidates("AC", "deputado_federal", round=2)
    assert answer.data is not None
    assert answer.data.round == 1
    assert answer.data.total == 2
    assert answer.warnings == ["Deputado federal não tem 2º turno; esta é a lista do 1º turno."]


@pytest.mark.parametrize("round_", [0, 3, "x", "-1"])
def test_round_outside_the_calendar_is_invalid_query(core: Core, round_):
    with pytest.raises(InvalidQuery, match="turno inválido"):
        core.list_candidates("AC", "governador", round=round_)


def test_election_is_null_when_the_index_comes_from_the_monthly_file(tmp_path: Path):
    build_fixture_index(tmp_path, dataset=POLLING_PLACES_CURRENT)
    core = open_core(tmp_path)
    try:
        answer = core.list_candidates("AC", "governador")
    finally:
        core.close()
    assert answer.data is not None
    assert answer.data.total == 2
    assert answer.election is None


def test_election_is_null_when_there_is_no_current_election(acre_index_dir: Path):
    after_last_round = dt.datetime(2026, 10, 26, 12, 0, tzinfo=SAO_PAULO)
    core = open_core(acre_index_dir, clock=fixed_clock(after_last_round))
    try:
        answer = core.list_candidates("AC", "governador")
        assert answer.data is not None
        assert answer.election is None
        with pytest.raises(InvalidQuery):
            core.list_candidates("AC", "governador", round=3)
    finally:
        core.close()


# Profile-versus-list contract (codebase-design 8.3 and 10)


def test_list_item_model_declares_no_profile_only_field():
    schema = CandidateListItem.model_json_schema()
    assert set(schema["properties"]) == LIST_ITEM_FIELDS
    assert not set(schema["properties"]) & PROFILE_ONLY_FIELDS
    answer_schema = json.dumps(CandidatesAnswer.model_json_schema())
    for field in PROFILE_ONLY_FIELDS:
        assert f'"{field}"' not in answer_schema


def test_no_serialized_list_answer_contains_a_profile_only_key(core: Core):
    answers = [
        core.list_candidates("BR", "presidente"),
        core.list_candidates("AC", "governador", on_ballot_only=False),
        core.list_candidates("AC", "deputado_estadual"),
        core.list_candidates("AC", "senador", party="PT"),
    ]
    for answer in answers:
        serialized = json.dumps(answer.model_dump(mode="json"), ensure_ascii=False)
        for field in PROFILE_ONLY_FIELDS:
            assert f'"{field}"' not in serialized
        # The values the TSE publishes in those columns never leak through another key either.
        assert "MASCULINO" not in serialized
        assert "SUPERIOR COMPLETO" not in serialized
