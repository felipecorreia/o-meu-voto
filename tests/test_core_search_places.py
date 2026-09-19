"""``Core.resolve_municipality`` and ``Core.search_polling_places`` over the Acre fixture index."""

from __future__ import annotations

import pytest

from br_elections_mcp.core import Core, InvalidQuery
from br_elections_mcp.core.core import (
    MUNICIPALITY_AMBIGUOUS_GUIDANCE,
    MUNICIPALITY_NOT_FOUND_GUIDANCE,
    SEARCH_PLACES_GUIDANCE,
)
from br_elections_mcp.pipeline.datasets import MUNICIPALITIES_TSE_IBGE, POLLING_PLACES_2026

# Scenario 4: abroad


def test_scenario_4_abroad_section_resolves_to_a_place_in_cologne_with_the_same_schema(
    core: Core,
):
    answer = core.find_polling_place("zz", "001", "0001")

    assert answer.not_found is None
    data = answer.data
    assert data is not None
    assert data.municipality.model_dump() == {
        "tse_code": "30015",
        "ibge_code": None,
        "name": "COLÔNIA",
        "uf": "ZZ",
    }
    assert data.place.name == "CONSULADO-GERAL DO BRASIL EM COLÔNIA"
    assert data.place.address == "BENRATHER STRASSE 8"
    assert (data.place.section_count, data.place.accessible_section_count) == (2, 1)
    assert answer.election is not None


# resolve_municipality


@pytest.mark.parametrize("name", ["Rio Branco", "rio branco", "RIO BRANCO", "  rio   branco "])
def test_resolve_municipality_is_case_and_whitespace_insensitive(core: Core, name: str):
    answer = core.resolve_municipality(name)

    assert answer.not_found is None
    assert answer.data is not None
    assert [m.model_dump() for m in answer.data.municipalities] == [
        {"tse_code": "01392", "ibge_code": 1200401, "name": "RIO BRANCO", "uf": "AC", "score": 1.0}
    ]


def test_resolve_municipality_is_accent_insensitive_and_abroad_has_no_ibge_code(core: Core):
    answer = core.resolve_municipality("colonia")

    assert answer.data is not None
    assert [m.model_dump() for m in answer.data.municipalities] == [
        {"tse_code": "30015", "ibge_code": None, "name": "COLÔNIA", "uf": "ZZ", "score": 1.0}
    ]


def test_resolve_municipality_lists_partial_matches_by_score(core: Core):
    answer = core.resolve_municipality("porto")

    assert answer.data is not None
    matches = answer.data.municipalities
    assert [(m.name, m.uf) for m in matches] == [("PORTO ACRE", "AC"), ("PORTO WALTER", "AC")]
    assert all(0 < m.score < 1 for m in matches)


def test_resolve_municipality_tolerates_a_typo_with_a_lower_score(core: Core):
    answer = core.resolve_municipality("Rio Branca", uf="ac")

    assert answer.data is not None
    assert [m.name for m in answer.data.municipalities] == ["RIO BRANCO"]
    assert 0.9 < answer.data.municipalities[0].score < 1.0


def test_resolve_municipality_filters_by_uf(core: Core):
    assert core.resolve_municipality("colonia", uf="AC").not_found is not None
    zz = core.resolve_municipality("colonia", uf="ZZ")
    assert zz.data is not None
    assert [m.uf for m in zz.data.municipalities] == ["ZZ"]


def test_resolve_municipality_honors_limit(core: Core):
    answer = core.resolve_municipality("porto", limit=1)
    assert answer.data is not None
    assert [m.name for m in answer.data.municipalities] == ["PORTO ACRE"]


def test_resolve_municipality_not_found_carries_guidance(core: Core):
    answer = core.resolve_municipality("Xanadu")

    assert answer.data is None
    assert answer.not_found is not None
    assert answer.not_found.reason == "municipio_nao_encontrado"
    assert answer.not_found.guidance == MUNICIPALITY_NOT_FOUND_GUIDANCE
    assert answer.not_found.options is None


def test_resolve_municipality_source_is_the_crosswalk_and_election_is_null(core: Core):
    answer = core.resolve_municipality("Rio Branco")

    assert answer.source.dataset == MUNICIPALITIES_TSE_IBGE.title
    assert answer.source.dataset_url == MUNICIPALITIES_TSE_IBGE.dataset_url
    assert answer.source.file == "municipio_tse_ibge.csv"
    assert answer.source.license == "CC-BY"
    assert answer.election is None
    assert answer.warnings == []


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"name": ""}, "nome inválido"),
        ({"name": "   "}, "nome inválido"),
        ({"name": "Rio Branco", "uf": "XX"}, "UF desconhecida"),
        ({"name": "Rio Branco", "limit": 0}, "limite inválido"),
        ({"name": "Rio Branco", "limit": 51}, "limite inválido"),
        ({"name": "Rio Branco", "limit": "dez"}, "limite inválido"),
    ],
)
def test_resolve_municipality_invalid_input_is_invalid_query(core: Core, kwargs, message):
    with pytest.raises(InvalidQuery, match=message):
        core.resolve_municipality(**kwargs)


# search_polling_places


def test_scenario_7_places_of_a_municipality_filtered_by_neighborhood(core: Core):
    answer = core.search_polling_places("AC", "Rio Branco", neighborhood="centro")

    assert answer.not_found is None
    assert answer.warnings == []
    data = answer.data
    assert data is not None
    assert data.round == 1
    assert data.municipality.model_dump() == {
        "tse_code": "01392",
        "ibge_code": 1200401,
        "name": "RIO BRANCO",
        "uf": "AC",
    }
    assert data.total == 2
    assert data.guidance == SEARCH_PLACES_GUIDANCE
    assert [p.model_dump() for p in data.places] == [
        {
            "number": 1050,
            "zone": 9,
            "name": "COLÉGIO ACREANO",
            "kind": "Convencional",
            "address": "RUA RUI BARBOSA, 200",
            "neighborhood": "CENTRO",
            "postal_code": "69900120",
            "phone": None,
            "latitude": -9.9738,
            "longitude": -67.8109,
            "status": "ativo",
            "section_count": 1,
            "accessible_section_count": 1,
            "voters": 287,
        },
        {
            "number": 1035,
            "zone": 9,
            "name": "ESCOLA ESTADUAL JOSÉ RODRIGUES LEITE",
            "kind": "Convencional",
            "address": "AVENIDA CEARÁ, 1500",
            "neighborhood": "CENTRO",
            "postal_code": "69900460",
            "phone": "(68) 3223-1234",
            "latitude": -9.9754,
            "longitude": -67.812,
            "status": "ativo",
            "section_count": 1,
            "accessible_section_count": 1,
            "voters": 312,
        },
    ]


def test_search_without_filters_lists_every_place_of_the_municipality_by_name(core: Core):
    answer = core.search_polling_places("ac", "rio branco")

    assert answer.data is not None
    assert answer.data.total == 3
    assert [p.number for p in answer.data.places] == [1050, 1035, 1000]
    assert answer.data.places[2].model_dump()["section_count"] == 3
    assert answer.data.places[2].model_dump()["accessible_section_count"] == 2
    assert answer.data.places[2].model_dump()["voters"] == 260 + 251 + 38


def test_search_accepts_the_municipality_by_tse_code(core: Core):
    by_code = core.search_polling_places("AC", "01392")
    by_short_code = core.search_polling_places("AC", "1392")
    by_name = core.search_polling_places("AC", "Rio Branco")

    assert by_code.data is not None
    assert by_code.data.municipality.tse_code == "01392"
    assert by_code.model_dump() == by_name.model_dump() == by_short_code.model_dump()


def test_search_query_matches_the_place_name_or_the_address_without_accents(core: Core):
    by_name = core.search_polling_places("AC", "Rio Branco", query="colegio")
    assert by_name.data is not None
    assert [p.number for p in by_name.data.places] == [1050]

    by_address = core.search_polling_places("AC", "Rio Branco", query="avenida ceara")
    assert by_address.data is not None
    assert [p.number for p in by_address.data.places] == [1035]


def test_search_with_no_match_is_an_empty_list_not_not_found(core: Core):
    answer = core.search_polling_places("AC", "Rio Branco", neighborhood="Nenhum")

    assert answer.not_found is None
    assert answer.data is not None
    assert answer.data.places == []
    assert answer.data.total == 0
    assert answer.data.guidance == SEARCH_PLACES_GUIDANCE


def test_search_of_a_municipality_without_places_is_an_empty_list(core: Core):
    answer = core.search_polling_places("AC", "Porto Acre")

    assert answer.not_found is None
    assert answer.data is not None
    assert answer.data.municipality.name == "PORTO ACRE"
    assert answer.data.total == 0


def test_search_honors_limit_and_total_counts_before_the_limit(core: Core):
    answer = core.search_polling_places("AC", "Rio Branco", limit=2)

    assert answer.data is not None
    assert len(answer.data.places) == 2
    assert answer.data.total == 3


def test_search_without_near_has_no_distance(core: Core):
    answer = core.search_polling_places("AC", "Rio Branco")

    assert answer.data is not None
    for place in answer.data.places:
        assert "distance_km" not in place.model_dump()
        assert "distance_km" not in place.model_dump(mode="json")


def test_search_with_near_orders_by_distance_and_puts_places_without_coordinates_last(
    core: Core,
):
    # Cruzeiro do Sul: 1020 has coordinates, 1015 does not. From the far side of 1020.
    answer = core.search_polling_places(
        "AC", "Cruzeiro do Sul", near={"latitude": -7.6, "longitude": -72.7}
    )

    assert answer.data is not None
    assert [p.number for p in answer.data.places] == [1020, 1015]
    with_coords, without = answer.data.places
    assert with_coords.distance_km is not None
    assert 4 < with_coords.distance_km < 5.5
    assert without.distance_km is None
    assert "distance_km" in with_coords.model_dump()


def test_search_with_near_orders_ascending_from_a_point_near_the_airport(core: Core):
    # Next to place 1000 (Aeroporto Velho); the two places in Centro are ~1.3 km away.
    answer = core.search_polling_places(
        "AC", "Rio Branco", near={"latitude": -9.9848, "longitude": -67.8225}
    )

    assert answer.data is not None
    numbers = [p.number for p in answer.data.places]
    assert numbers[0] == 1000
    assert set(numbers[1:]) == {1035, 1050}
    distances = [p.distance_km for p in answer.data.places]
    assert distances == sorted(distances)  # type: ignore[type-var]
    assert distances[0] is not None and distances[0] < 0.1


def test_search_abroad_lists_the_place_in_cologne(core: Core):
    answer = core.search_polling_places("ZZ", "Colônia")

    assert answer.data is not None
    assert answer.data.municipality.ibge_code is None
    assert [p.name for p in answer.data.places] == ["CONSULADO-GERAL DO BRASIL EM COLÔNIA"]
    assert answer.data.places[0].voters == 412 + 398


def test_search_unknown_municipality_is_not_found(core: Core):
    answer = core.search_polling_places("AC", "Xanadu")

    assert answer.data is None
    assert answer.not_found is not None
    assert answer.not_found.reason == "municipio_nao_encontrado"
    assert answer.not_found.guidance == MUNICIPALITY_NOT_FOUND_GUIDANCE
    assert answer.not_found.options is None


def test_search_ambiguous_municipality_lists_the_options_in_the_resolve_shape(core: Core):
    answer = core.search_polling_places("AC", "porto")

    assert answer.data is None
    assert answer.not_found is not None
    assert answer.not_found.reason == "municipio_ambiguo"
    assert answer.not_found.guidance == MUNICIPALITY_AMBIGUOUS_GUIDANCE
    resolved = core.resolve_municipality("porto", uf="AC")
    assert resolved.data is not None
    assert answer.not_found.options == resolved.data.municipalities


def test_search_a_municipality_of_another_uf_is_not_found(core: Core):
    answer = core.search_polling_places("ZZ", "Rio Branco")
    assert answer.not_found is not None
    assert answer.not_found.reason == "municipio_nao_encontrado"


def test_search_source_and_election_follow_the_polling_places_dataset(core: Core):
    answer = core.search_polling_places("AC", "Rio Branco")

    assert answer.source.dataset == POLLING_PLACES_2026.title
    assert answer.source.file == "eleitorado_local_votacao_2026_AC.csv"
    assert answer.election is not None
    assert answer.election.id == "general-2026"
    assert answer.election.round.number == 1


def test_search_round_explicit_and_not_published_answers_the_highest_published_round(
    core: Core,
):
    answer = core.search_polling_places("AC", "Rio Branco", round=2)
    assert answer.data is not None
    assert answer.data.round == 1


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"uf": "XX", "municipality": "Rio Branco"}, "UF desconhecida"),
        ({"uf": "BR", "municipality": "Rio Branco"}, "UF sem seções"),
        ({"uf": "AC", "municipality": ""}, "município inválido"),
        ({"uf": "AC", "municipality": "Rio Branco", "limit": 0}, "limite inválido"),
        ({"uf": "AC", "municipality": "Rio Branco", "limit": 51}, "limite inválido"),
        ({"uf": "AC", "municipality": "Rio Branco", "round": 3}, "turno inválido"),
        ({"uf": "AC", "municipality": "Rio Branco", "near": {"latitude": -9.9}}, "coordenadas"),
        (
            {"uf": "AC", "municipality": "Rio Branco", "near": {"latitude": 91, "longitude": 0}},
            "coordenadas",
        ),
        (
            {"uf": "AC", "municipality": "Rio Branco", "near": {"latitude": "x", "longitude": 0}},
            "coordenadas",
        ),
    ],
)
def test_search_invalid_input_is_invalid_query(core: Core, kwargs, message):
    with pytest.raises(InvalidQuery, match=message):
        core.search_polling_places(**kwargs)
