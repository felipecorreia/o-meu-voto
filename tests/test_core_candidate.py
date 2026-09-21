"""``Core.get_candidate`` through its interface, over the Acre fixture index."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from br_elections_mcp.core import CandidateAnswer, CandidateProfile, Core, InvalidQuery
from br_elections_mcp.core.divulgacandcontas import REGION_BY_UF, candidate_page_url
from br_elections_mcp.domain import UF
from br_elections_mcp.pipeline.datasets import POLLING_PLACES_CURRENT
from tests.conftest import ACRE_CANDIDATES, build_fixture_index, fixed_clock, open_core
from tests.test_core_candidates import LIST_ITEM_FIELDS, PROFILE_ONLY_FIELDS

GOVERNOR_45 = 10000000001
VICE_45 = 10000000002
GOVERNOR_22_OFF_BALLOT = 10000000005
SENATOR_456 = 10000000006
FIRST_SUBSTITUTE_456 = 10000000007
SECOND_SUBSTITUTE_456 = 10000000008
FEDERAL_DEPUTY_4512 = 10000000009
STATE_DEPUTY_45123 = 10000000011
PRESIDENT_13 = 20000000001
VICE_PRESIDENT_13 = 20000000002


def profile(answer: CandidateAnswer) -> CandidateProfile:
    assert answer.not_found is None
    assert answer.data is not None
    return answer.data.candidate


def test_scenario_8_governor_by_number_carries_the_vice_with_the_same_number(core: Core):
    answer = core.get_candidate(uf="AC", office="governador", number=45)

    assert answer.warnings == []
    candidate = profile(answer)
    assert candidate.model_dump(mode="json") == {
        "sq_candidato": GOVERNOR_45,
        "number": 45,
        "ballot_name": "MARIA DA SILVA",
        "name": "MARIA APARECIDA DA SILVA",
        "office": "governador",
        "party": {
            "number": 45,
            "acronym": "PSDB",
            "name": "PARTIDO DA SOCIAL DEMOCRACIA BRASILEIRA",
        },
        "federation": None,
        "coalition": {"name": "ACRE PARA TODOS", "composition": "PSDB, MDB"},
        "adjudication_status": "DEFERIDO",
        "on_ballot": True,
        "occupation": "ADMINISTRADOR",
        "photo_url": None,
        "round": 1,
        "social_name": None,
        "nomination_kind": "coligacao",
        "gender": "FEMININO",
        "race_color": "PARDA",
        "marital_status": "CASADO(A)",
        "education": "SUPERIOR COMPLETO",
        "running_mates": [
            {
                "sq_candidato": VICE_45,
                "office": "vice_governador",
                "ballot_name": "JOÃO DO ACRE",
                "name": "JOÃO BATISTA PEREIRA",
                "party": {
                    "number": 15,
                    "acronym": "MDB",
                    "name": "MOVIMENTO DEMOCRÁTICO BRASILEIRO",
                },
            }
        ],
        "social_links": [
            "https://www.instagram.com/mariadasilva45",
            "https://www.facebook.com/mariadasilva45",
        ],
        "divulgacandcontas_url": (
            "https://divulgacandcontas.tse.jus.br/divulga/#/candidato/NORTE/AC/20322002026/"
            "10000000001/2026/AC"
        ),
    }


def test_by_sq_candidato_and_by_the_trio_answer_the_same_profile(core: Core):
    by_sq = core.get_candidate(GOVERNOR_45)
    by_trio = core.get_candidate(uf="ac", office="Governador", number="45")

    assert by_sq.model_dump() == by_trio.model_dump()


def test_the_trio_ignores_an_off_ballot_candidacy_that_holds_the_number(core: Core):
    answer = core.get_candidate(uf="AC", office="governador", number=22)

    assert answer.data is None
    assert answer.not_found is not None
    assert answer.not_found.reason == "candidato_nao_encontrado"
    assert "na urna" in answer.not_found.guidance
    assert answer.election is not None
    assert answer.election.round.number == 1


def test_by_sq_candidato_an_off_ballot_candidacy_is_a_profile_without_mates(core: Core):
    candidate = profile(core.get_candidate(GOVERNOR_22_OFF_BALLOT))

    assert candidate.on_ballot is False
    assert candidate.adjudication_status == "RENÚNCIA"
    assert candidate.nomination_kind == "partido_isolado"
    assert candidate.federation is None
    assert candidate.coalition is None
    assert candidate.running_mates == []


def test_unknown_sq_candidato_is_not_found_with_guidance(core: Core):
    answer = core.get_candidate(99999999999)

    assert answer.data is None
    assert answer.not_found is not None
    assert answer.not_found.reason == "candidato_nao_encontrado"
    assert "sq_candidato" in answer.not_found.guidance
    assert answer.election is not None
    assert answer.source.file == "consulta_cand_2026_BRASIL.csv"


def test_federation_and_coalition_carry_their_composition_only_in_the_profile(core: Core):
    candidate = profile(core.get_candidate(PRESIDENT_13))

    assert candidate.federation is not None
    assert candidate.federation.model_dump() == {
        "acronym": "PT/PC do B/PV",
        "name": "BRASIL DA ESPERANÇA",
        "composition": "PT / PC do B / PV",
    }
    assert candidate.coalition is None
    assert candidate.nomination_kind == "federacao"
    listed = core.list_candidates("BR", "presidente", round=1).data
    assert listed is not None
    assert "composition" not in listed.candidates[0].model_dump()["federation"]


def test_senator_profile_lists_both_substitutes_in_order(core: Core):
    candidate = profile(core.get_candidate(uf="AC", office="senador", number=456))

    assert [(m.office.value, m.sq_candidato) for m in candidate.running_mates] == [
        ("primeiro_suplente", FIRST_SUBSTITUTE_456),
        ("segundo_suplente", SECOND_SUBSTITUTE_456),
    ]
    assert candidate.running_mates[0].party.acronym == "PSDB"
    assert candidate.social_links == []


def test_a_running_mate_profile_lists_the_head_first_and_the_other_mates(core: Core):
    vice = profile(core.get_candidate(VICE_45))
    first_substitute = profile(core.get_candidate(FIRST_SUBSTITUTE_456))

    assert vice.office.value == "vice_governador"
    assert [(m.office.value, m.sq_candidato) for m in vice.running_mates] == [
        ("governador", GOVERNOR_45)
    ]
    assert [(m.office.value, m.sq_candidato) for m in first_substitute.running_mates] == [
        ("senador", SENATOR_456),
        ("segundo_suplente", SECOND_SUBSTITUTE_456),
    ]


@pytest.mark.parametrize("sq_candidato", [FEDERAL_DEPUTY_4512, STATE_DEPUTY_45123])
def test_deputies_have_no_ticket(core: Core, sq_candidato: int):
    assert profile(core.get_candidate(sq_candidato)).running_mates == []


def test_president_uses_br_as_uf_and_region_brasil_in_the_link(core: Core):
    candidate = profile(core.get_candidate(uf="BR", office="presidente", number=13))

    assert candidate.sq_candidato == PRESIDENT_13
    assert [m.sq_candidato for m in candidate.running_mates] == [VICE_PRESIDENT_13]
    assert candidate.divulgacandcontas_url == (
        "https://divulgacandcontas.tse.jus.br/divulga/#/candidato/BRASIL/BR/20322002026/"
        "20000000001/2026/BR"
    )


def test_divulgacandcontas_link_is_null_when_the_calendar_has_no_id():
    assert candidate_page_url(None, UF.AC, GOVERNOR_45, 2026) is None
    assert set(REGION_BY_UF) == set(UF) - {UF.ZZ}


def test_divulgacandcontas_link_is_null_for_an_election_outside_the_calendar(tmp_path: Path):
    # The candidate rows carry their election year; when the calendar has no election of that
    # year (a 2022 candidate file served in 2026) there is no id to build the link from.
    original = ACRE_CANDIDATES.read_bytes()
    rewritten = tmp_path / "consulta_cand_2022_BRASIL.csv"
    rewritten.write_bytes(
        original.replace(b'"2026";"2"', b'"2022";"2"')
        .replace(b'"04/10/2026"', b'"02/10/2022"')
        .replace(b'"ELEI\xc7\xd5ES GERAIS 2026"', b'"ELEI\xc7\xd5ES GERAIS 2022"')
    )
    build_fixture_index(tmp_path / "index", candidates=rewritten, dataset=POLLING_PLACES_CURRENT)
    core = open_core(tmp_path / "index")
    try:
        candidate = profile(core.get_candidate(GOVERNOR_45))
    finally:
        core.close()
    assert candidate.divulgacandcontas_url is None
    assert candidate.round == 1


@pytest.mark.parametrize(
    ("args", "kwargs", "message"),
    [
        ((), {}, "trio completo"),
        ((), {"uf": "AC", "office": "governador"}, "trio completo"),
        ((GOVERNOR_45,), {"uf": "AC"}, "não os dois"),
        (("abc",), {}, "sq_candidato inválido"),
        ((0,), {}, "sq_candidato inválido"),
        ((), {"uf": "AC", "office": "governador", "number": "quarenta"}, "número inválido"),
        ((), {"uf": "XX", "office": "governador", "number": 45}, "UF desconhecida"),
        ((), {"uf": "ZZ", "office": "governador", "number": 45}, "UF sem candidatos"),
        ((), {"uf": "AC", "office": "prefeito", "number": 45}, "cargo desconhecido"),
        ((), {"uf": "AC", "office": "vice_governador", "number": 45}, "cargo de chapa"),
        ((), {"uf": "AC", "office": "presidente", "number": 13}, "uf = BR"),
        ((GOVERNOR_45,), {"round": 3}, "turno inválido"),
        ((GOVERNOR_45,), {"round": "x"}, "turno inválido"),
    ],
)
def test_malformed_lookups_are_invalid_query(core: Core, args, kwargs, message):
    with pytest.raises(InvalidQuery, match=message):
        core.get_candidate(*args, **kwargs)


def test_round_absent_or_present_answers_the_candidacy_round(core: Core):
    assert profile(core.get_candidate(GOVERNOR_45)).round == 1
    assert profile(core.get_candidate(GOVERNOR_45, round=1)).round == 1
    # Round 2 is published (presidents) but Acre was decided in round 1: the profile of the
    # highest round of the candidacy, with the F4 warning (tests/test_core_rounds.py has the
    # whole table).
    answer = core.get_candidate(GOVERNOR_45, round=2)
    assert profile(answer).round == 1
    assert answer.warnings == ["Não há 2º turno para governador no AC; esta é a ficha do 1º turno."]
    assert answer.election is not None
    assert answer.election.round.number == 1


def test_every_answer_carries_source_and_election(core: Core):
    found = core.get_candidate(GOVERNOR_45)
    missing = core.get_candidate(uf="AC", office="governador", number=22)
    for answer in (found, missing):
        assert answer.source.dataset == "Candidatos - 2026"
        assert answer.source.license == "CC-BY"
        assert answer.election is not None
        assert answer.election.id == "general-2026"


def test_election_is_null_when_there_is_no_current_election(acre_index_dir: Path):
    core = open_core(acre_index_dir, clock=fixed_clock(dt.datetime(2026, 11, 1, tzinfo=dt.UTC)))
    try:
        answer = core.get_candidate(GOVERNOR_45)
    finally:
        core.close()
    assert answer.election is None
    assert profile(answer).round == 1


# Profile versus list: the contract of codebase-design 8.3 and 8.4.


def test_profile_model_declares_the_list_fields_plus_the_profile_only_ones():
    fields = set(CandidateProfile.model_fields)
    assert fields >= LIST_ITEM_FIELDS
    assert fields >= PROFILE_ONLY_FIELDS
    assert fields >= {
        "round",
        "social_name",
        "nomination_kind",
        "running_mates",
        "social_links",
        "divulgacandcontas_url",
    }
    schema = json.dumps(CandidateAnswer.model_json_schema())
    for field in PROFILE_ONLY_FIELDS:
        assert f'"{field}"' in schema


def test_the_same_candidate_has_the_profile_only_keys_in_the_profile_and_not_in_the_list(
    core: Core,
):
    listed = core.list_candidates("AC", "governador").model_dump(mode="json")
    serialized_list = json.dumps(listed)
    fetched = core.get_candidate(GOVERNOR_45).model_dump(mode="json")
    candidate = fetched["data"]["candidate"]

    assert any(c["sq_candidato"] == GOVERNOR_45 for c in listed["data"]["candidates"])
    for field in PROFILE_ONLY_FIELDS:
        assert f'"{field}"' not in serialized_list
        assert candidate[field] is not None
