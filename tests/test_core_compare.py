"""``compare_candidates`` (codebase-design 8.7, ADR 0008) over the Acre fixture index."""

from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path

import pytest

from br_elections_mcp.core import (
    STALE_AFTER_HOURS,
    CandidatesComparisonAnswer,
    ComparedCandidate,
    Core,
    InvalidQuery,
)
from br_elections_mcp.core.core import ASSETS_NOTE, VOTE_DESTINATION_NOTES
from br_elections_mcp.pipeline.build import apply_photo_urls
from tests.conftest import fixed_clock, open_core

GOVERNOR_45 = 10000000001
GOVERNOR_13 = 10000000003
GOVERNOR_22_OFF_BALLOT = 10000000005
SENATOR_456 = 10000000006
PROFILE_ONLY_FIELDS = {"gender", "race_color", "marital_status", "education"}


def data(answer: CandidatesComparisonAnswer):
    assert answer.not_found is None
    assert answer.data is not None
    return answer.data


def numbers(answer: CandidatesComparisonAnswer) -> list[int]:
    return [candidate.number for candidate in data(answer).candidates]


def test_without_a_selector_compares_every_on_ballot_candidacy_of_the_round(core: Core):
    answer = core.compare_candidates("ac", "Governador")

    d = data(answer)
    assert (d.round, d.uf, d.office) == (1, "AC", "governador")
    # 22 renounced and is off the ballot; the other two come in ballot-number order.
    assert numbers(answer) == [13, 45]
    assert d.missing == []
    assert answer.source.file == "consulta_cand_2026_BRASIL.csv"
    assert d.assets_source.file == "bem_candidato_2026_BRASIL.csv"
    assert d.assets_source.dataset == "Bens de candidatos - 2026"
    assert d.assets_note == ASSETS_NOTE
    assert answer.election is not None
    assert answer.election.round.number == 1
    assert answer.warnings == []


def test_an_entry_carries_the_alliance_ticket_links_vote_destination_and_assets(core: Core):
    thirteen, forty_five = data(core.compare_candidates("AC", "governador")).candidates

    assert forty_five.model_dump(mode="json") == {
        "sq_candidato": GOVERNOR_45,
        "number": 45,
        "ballot_name": "MARIA DA SILVA",
        "name": "Maria Aparecida da Silva",
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
        "vote_destination": "Válido",
        "social_name": None,
        "nomination_kind": "coligacao",
        "vote_destination_note": VOTE_DESTINATION_NOTES["Válido"],
        "running_mates": [
            {
                "sq_candidato": 10000000002,
                "office": "vice_governador",
                "ballot_name": "JOÃO DO ACRE",
                "name": forty_five.running_mates[0].name,
                "party": {
                    "number": 15,
                    "acronym": "MDB",
                    "name": forty_five.running_mates[0].party.name,
                },
            }
        ],
        "social_links": [
            "https://www.instagram.com/mariadasilva45",
            "https://www.facebook.com/mariadasilva45",
        ],
        "divulgacandcontas_url": forty_five.divulgacandcontas_url,
        "assets": {"state": "declarados", "total": 1216500.0},
    }
    assert forty_five.divulgacandcontas_url is not None
    assert forty_five.divulgacandcontas_url.startswith("https://divulgacandcontas.tse.jus.br/")
    assert str(GOVERNOR_45) in forty_five.divulgacandcontas_url

    # Rejected with an appeal and still on the ballot: votes annulled sub judice, verbatim.
    assert thirteen.adjudication_status == "INDEFERIDO EM PRAZO RECURSAL OU COM RECURSO"
    assert thirteen.vote_destination == "Anulado sub judice"
    assert thirteen.vote_destination_note == VOTE_DESTINATION_NOTES["Anulado sub judice"]
    assert thirteen.federation is not None
    assert thirteen.federation.composition == "PT / PC do B / PV"
    # A negative item is summed as declared, never corrected.
    assert thirteen.assets.model_dump() == {"state": "declarados", "total": 115000.0}


def test_the_three_asset_states_and_deputies_without_a_ticket(core: Core):
    by_number = {
        c.number: c
        for c in data(
            core.compare_candidates("AC", "deputado_federal", numbers=[1313, 4512])
        ).candidates
    }
    assert by_number[4512].assets.model_dump() == {"state": "declarados", "total": 12000.5}
    # ST_DECLARAR_BENS = N: declared having no assets.
    assert by_number[1313].assets.model_dump() == {"state": "declarou_nao_possuir", "total": None}
    assert by_number[4512].running_mates == []

    presidents = data(core.compare_candidates("BR", "presidente", numbers=[22, 45], round=1))
    twenty_two = presidents.candidates[0]
    # "Não divulgável" in ST_DECLARAR_BENS and no published item: no information.
    assert twenty_two.number == 22
    assert twenty_two.assets.model_dump() == {"state": "sem_informacao", "total": None}


def test_entries_follow_the_ballot_number_whatever_the_request_order(core: Core):
    answer = core.compare_candidates("BR", "presidente", numbers=["45", 22, "013"], round=1)
    assert numbers(answer) == [13, 22, 45]
    # President 45 declares the largest total and still comes last: never ordered by value.
    totals = [c.assets.total for c in data(answer).candidates]
    assert totals == [4775651.0, None, 8186556.0]


def test_the_round_follows_the_list_rules_and_leaves_out_who_is_not_in_it(core: Core):
    # C1: without round, the highest round of the office (2 for president); 13 was
    # eliminated in round 1.
    answer = core.compare_candidates("BR", "presidente", numbers=[13, 45, 22])
    d = data(answer)
    assert d.round == 2
    assert numbers(answer) == [22, 45]
    assert [m.model_dump() for m in d.missing] == [{"requested": 13, "reason": "fora_do_turno"}]
    assert answer.election is not None
    assert answer.election.round.number == 2

    # C3: governor of AC has no round 2; the comparison is of round 1, with the warning.
    governors = core.compare_candidates("AC", "governador", round=2)
    assert data(governors).round == 1
    assert governors.warnings == [
        "Não há 2º turno para governador no AC; esta é a lista do 1º turno."
    ]


def test_a_number_held_off_the_ballot_resolves_to_the_on_ballot_substitute(core: Core):
    answer = core.compare_candidates("AC", "deputado_estadual", numbers=[22222, 45123])
    assert [c.sq_candidato for c in data(answer).candidates] == [10000000012, 10000000011]


def test_by_sq_candidato_the_off_ballot_and_the_unknown_are_named_in_missing(core: Core):
    answer = core.compare_candidates(
        "AC",
        "governador",
        sq_candidatos=[GOVERNOR_45, GOVERNOR_22_OFF_BALLOT, "10000000003", 99999999999],
    )
    assert numbers(answer) == [13, 45]
    assert [m.model_dump() for m in data(answer).missing] == [
        {"requested": GOVERNOR_22_OFF_BALLOT, "reason": "fora_da_urna"},
        {"requested": 99999999999, "reason": "nao_encontrado"},
    ]


def test_by_number_the_off_ballot_and_the_unknown_are_named_in_missing(core: Core):
    answer = core.compare_candidates("AC", "governador", numbers=[45, 22, 13, 77])
    assert numbers(answer) == [13, 45]
    assert [m.model_dump() for m in data(answer).missing] == [
        {"requested": 22, "reason": "fora_da_urna"},
        {"requested": 77, "reason": "nao_encontrado"},
    ]


def test_fewer_than_two_left_is_not_found_with_guidance(core: Core):
    answer = core.compare_candidates("AC", "governador", numbers=[45, 22])
    assert answer.data is None
    assert answer.not_found is not None
    assert answer.not_found.reason == "candidaturas_insuficientes"
    assert "list_candidates" in answer.not_found.guidance
    assert answer.election is not None
    assert answer.source.file == "consulta_cand_2026_BRASIL.csv"


def test_the_photo_url_of_each_entry_comes_from_the_mirror(tmp_path: Path, acre_index_dir: Path):
    index_dir = tmp_path / "index"
    shutil.copytree(acre_index_dir, index_dir)
    photo = "https://fotos.example.org/AC/FAC10000000001_div.jpg"
    apply_photo_urls(index_dir, {GOVERNOR_45: photo})
    core = open_core(index_dir)
    try:
        thirteen, forty_five = data(core.compare_candidates("AC", "governador")).candidates
    finally:
        core.close()
    assert forty_five.photo_url == photo
    assert thirteen.photo_url is None


def test_both_sources_age_and_warn(acre_index_dir: Path):
    later = dt.datetime(2026, 9, 18, 22, 31, 7, tzinfo=dt.UTC) + dt.timedelta(
        hours=STALE_AFTER_HOURS + 12
    )
    core = open_core(acre_index_dir, clock=fixed_clock(later))
    try:
        answer = core.compare_candidates("AC", "governador")
    finally:
        core.close()
    d = data(answer)
    assert answer.source.stale is True
    assert d.assets_source.stale is True
    # The candidates file was generated at 22:30, the asset file at 22:31: one warning each.
    assert len(answer.warnings) == 2
    assert "22:30" in answer.warnings[0]
    assert "22:31" in answer.warnings[1]


def test_the_default_needs_two_to_four_on_ballot_candidacies(core: Core):
    # One senator on the ballot in AC.
    with pytest.raises(InvalidQuery, match="1 candidatura"):
        core.compare_candidates("AC", "senador")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"numbers": [45]}, "escolha de 2 a 4"),
        ({"numbers": [1, 2, 3, 4, 5]}, "escolha de 2 a 4"),
        ({"numbers": []}, "escolha de 2 a 4"),
        ({"numbers": [45, "045"]}, "repetida"),
        ({"numbers": "45,13"}, "lista"),
        ({"numbers": [45, "x"]}, "número inválido"),
        ({"numbers": [45, 13], "sq_candidatos": [GOVERNOR_45, GOVERNOR_13]}, "não os dois"),
        ({"sq_candidatos": [GOVERNOR_45, SENATOR_456]}, "é de senador no AC"),
        ({"numbers": [45, 13], "round": 9}, "turno inválido"),
    ],
)
def test_malformed_requests_are_invalid_query(core: Core, kwargs: dict, message: str):
    with pytest.raises(InvalidQuery, match=message):
        core.compare_candidates("AC", "governador", **kwargs)


@pytest.mark.parametrize(
    ("uf", "office", "message"),
    [
        ("AC", "vice_governador", "cargo de chapa"),
        ("AC", "presidente", "presidente só existe com uf = BR"),
        ("ZZ", "governador", "UF sem candidatos"),
    ],
)
def test_ticket_offices_and_impossible_pairs_are_invalid_query(core: Core, uf, office, message):
    with pytest.raises(InvalidQuery, match=message):
        core.compare_candidates(uf, office, numbers=[45, 13])


def test_a_comparison_never_carries_a_profile_only_field(core: Core):
    schema = json.dumps(CandidatesComparisonAnswer.model_json_schema())
    assert not set(ComparedCandidate.model_json_schema()["properties"]) & PROFILE_ONLY_FIELDS
    for field in PROFILE_ONLY_FIELDS:
        assert f'"{field}"' not in schema
    serialized = json.dumps(
        core.compare_candidates("AC", "governador").model_dump(mode="json"), ensure_ascii=False
    )
    for field in PROFILE_ONLY_FIELDS:
        assert f'"{field}"' not in serialized
    # The values the TSE publishes in those columns never leak through another key either.
    assert "FEMININO" not in serialized
    assert "SUPERIOR COMPLETO" not in serialized


def test_every_vote_destination_the_tse_publishes_has_one_line():
    assert set(VOTE_DESTINATION_NOTES) == {"Válido", "Anulado sub judice", "Nulo técnico"}
    for note in VOTE_DESTINATION_NOTES.values():
        assert "\n" not in note
        assert note.endswith(".")
