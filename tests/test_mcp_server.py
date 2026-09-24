"""MCP adapter through the SDK's in-memory client over a real ``Core``."""

from __future__ import annotations

import pytest
from mcp import Client
from mcp.shared.exceptions import MCPError

from br_elections_mcp.core import (
    CandidateAnswer,
    CandidatesAnswer,
    Core,
    ElectionInfoAnswer,
    MunicipalitiesAnswer,
    PollingPlaceAnswer,
    PollingPlacesAnswer,
)
from br_elections_mcp.index_store import LocalDirectoryIndexSource
from br_elections_mcp.mcp_server import create_mcp_server
from tests.conftest import ELECTIONS_FILE

pytestmark = pytest.mark.anyio


async def test_tools_are_listed_with_pt_br_texts_annotations_and_generated_schemas(core: Core):
    async with Client(create_mcp_server(core)) as client:
        tools = (await client.list_tools()).tools

    assert [tool.name for tool in tools] == [
        "find_polling_place",
        "election_info",
        "list_candidates",
        "get_candidate",
        "search_polling_places",
        "resolve_municipality",
    ]
    tool = next(tool for tool in tools if tool.name == "find_polling_place")
    assert tool.title == "Onde voto"
    assert tool.description is not None
    assert "Não aceita nome, CPF ou número do título" in tool.description
    assert "e-Título" in tool.description
    assert tool.annotations is not None
    assert tool.annotations.read_only_hint is True
    assert tool.annotations.idempotent_hint is True
    assert tool.annotations.open_world_hint is False

    assert set(tool.input_schema["properties"]) == {"uf", "zone", "section", "round"}
    assert tool.input_schema["required"] == ["uf", "zone", "section"]
    assert tool.output_schema is not None
    assert set(tool.output_schema["properties"]) == set(
        PollingPlaceAnswer.model_json_schema()["properties"]
    )


async def test_call_returns_the_envelope_as_structured_content_and_a_pt_br_text(core: Core):
    async with Client(create_mcp_server(core)) as client:
        result = await client.call_tool(
            "find_polling_place", {"uf": "ac", "zone": "009", "section": "0422"}
        )

    assert result.is_error is False
    expected = core.find_polling_place("ac", "009", "0422").model_dump(mode="json")
    assert result.structured_content == expected
    assert len(result.content) == 1
    text = result.content[0]
    assert text.type == "text"
    assert "Zona 9, seção 422" in text.text
    assert "IEPTEC" in text.text
    assert "Fonte:" in text.text


async def test_warnings_reach_the_text_content(core: Core):
    async with Client(create_mcp_server(core)) as client:
        result = await client.call_tool(
            "find_polling_place", {"uf": "AC", "zone": 9, "section": 424}
        )
    assert "a votação acontece na seção 422" in result.content[0].text
    assert result.structured_content is not None
    assert result.structured_content["warnings"] == [
        "Sua seção é agregada: a votação acontece na seção 422, no mesmo local."
    ]


async def test_not_found_is_a_normal_result_with_guidance(core: Core):
    async with Client(create_mcp_server(core)) as client:
        result = await client.call_tool(
            "find_polling_place", {"uf": "AC", "zone": 1, "section": 99999}
        )
    assert result.is_error is False
    assert result.structured_content is not None
    assert result.structured_content["data"] is None
    assert result.structured_content["not_found"]["reason"] == "secao_nao_encontrada"
    assert "e-Título" in result.content[0].text


async def test_invalid_query_is_a_result_with_is_error(core: Core):
    async with Client(create_mcp_server(core)) as client:
        result = await client.call_tool(
            "find_polling_place", {"uf": "XX", "zone": 9, "section": 422}
        )
    assert result.is_error is True
    assert result.content[0].text == "UF desconhecida: 'XX'"
    assert result.structured_content is None


async def test_index_unavailable_is_a_server_error(acre_index_dir):
    unopened = Core(LocalDirectoryIndexSource(acre_index_dir), ELECTIONS_FILE)
    async with Client(create_mcp_server(unopened)) as client:
        with pytest.raises(MCPError, match="índice indisponível"):
            await client.call_tool("find_polling_place", {"uf": "AC", "zone": 9, "section": 422})


async def test_election_info_tool_schema_and_annotations(core: Core):
    async with Client(create_mcp_server(core)) as client:
        tools = (await client.list_tools()).tools

    tool = next(tool for tool in tools if tool.name == "election_info")
    assert tool.title == "Quando é a eleição"
    assert tool.description is not None
    assert "quando é a eleição" in tool.description
    assert tool.annotations is not None
    assert tool.annotations.read_only_hint is True
    assert set(tool.input_schema["properties"]) == {"on"}
    assert tool.input_schema.get("required", []) == []
    assert tool.output_schema is not None
    assert set(tool.output_schema["properties"]) == set(
        ElectionInfoAnswer.model_json_schema()["properties"]
    )


async def test_election_info_call_returns_the_envelope_and_a_pt_br_text(core: Core):
    async with Client(create_mcp_server(core)) as client:
        result = await client.call_tool("election_info", {"on": "2026-09-18"})

    assert result.is_error is False
    expected = core.election_info("2026-09-18").model_dump(mode="json")
    assert result.structured_content == expected
    assert result.structured_content["source"]["kind"] == "curated"
    assert result.structured_content["not_found"] is None
    assert result.structured_content["warnings"] == []
    text = result.content[0].text
    assert text.startswith("Eleições Gerais 2026")
    assert "turno" in text
    assert "Fonte:" in text


async def test_election_info_invalid_on_is_a_result_with_is_error(core: Core):
    async with Client(create_mcp_server(core)) as client:
        result = await client.call_tool("election_info", {"on": "not-a-date"})

    assert result.is_error is True
    assert "data inválida" in result.content[0].text
    assert result.structured_content is None


# list_candidates (ticket #8)


async def test_list_candidates_tool_is_listed_with_the_lgpd_promise_and_schemas(core: Core):
    async with Client(create_mcp_server(core)) as client:
        tools = (await client.list_tools()).tools
    tool = next(tool for tool in tools if tool.name == "list_candidates")

    assert tool.title == "Candidatos"
    assert tool.description is not None
    assert "BR para presidente" in tool.description
    assert "Nunca inclui CPF, título de eleitor, data de nascimento ou e-mail" in tool.description
    assert tool.annotations is not None
    assert tool.annotations.read_only_hint is True
    assert tool.annotations.open_world_hint is False

    assert set(tool.input_schema["properties"]) == {
        "uf",
        "office",
        "party",
        "name",
        "on_ballot_only",
        "limit",
        "offset",
        "round",
    }
    assert tool.input_schema["required"] == ["uf", "office"]
    assert tool.input_schema["properties"]["office"]["enum"] == [
        "presidente",
        "governador",
        "senador",
        "deputado_federal",
        "deputado_estadual",
        "deputado_distrital",
    ]
    assert tool.output_schema is not None
    assert set(tool.output_schema["properties"]) == set(
        CandidatesAnswer.model_json_schema()["properties"]
    )
    serialized = str(tool.output_schema)
    for field in ("gender", "race_color", "marital_status", "education"):
        assert f"'{field}'" not in serialized


async def test_list_candidates_returns_the_envelope_and_a_pt_br_text(core: Core):
    async with Client(create_mcp_server(core)) as client:
        result = await client.call_tool("list_candidates", {"uf": "ac", "office": "governador"})

    assert result.is_error is False
    expected = core.list_candidates("ac", "governador").model_dump(mode="json")
    assert result.structured_content == expected
    assert result.structured_content["data"]["total"] == 2
    text = result.content[0].text
    assert "2 candidatos a governador no AC" in text
    assert "13 ZÉ ANTÔNIO (PT)" in text
    assert "INDEFERIDO EM PRAZO RECURSAL OU COM RECURSO" in text
    assert "45 MARIA DA SILVA (PSDB)" in text
    assert "Fonte:" in text


async def test_list_candidates_passes_every_filter_through(core: Core):
    async with Client(create_mcp_server(core)) as client:
        result = await client.call_tool(
            "list_candidates",
            {
                "uf": "AC",
                "office": "governador",
                "party": "pl",
                "on_ballot_only": False,
                "limit": 1,
                "offset": 0,
                "round": 1,
            },
        )
    data = result.structured_content["data"]
    assert data["total"] == 1
    assert data["candidates"][0]["number"] == 22
    assert data["candidates"][0]["on_ballot"] is False
    assert (data["limit"], data["offset"], data["round"]) == (1, 0, 1)


async def test_list_candidates_empty_list_text_says_so(core: Core):
    async with Client(create_mcp_server(core)) as client:
        result = await client.call_tool(
            "list_candidates", {"uf": "AC", "office": "senador", "name": "ninguém"}
        )
    assert result.is_error is False
    assert result.structured_content["data"]["total"] == 0
    assert "Nenhum candidato" in result.content[0].text


async def test_list_candidates_invalid_query_is_a_result_with_is_error(core: Core):
    async with Client(create_mcp_server(core)) as client:
        result = await client.call_tool("list_candidates", {"uf": "AC", "office": "presidente"})
    assert result.is_error is True
    assert "presidente só existe com uf = BR" in result.content[0].text


async def test_get_candidate_tool_is_listed_with_the_lgpd_promise_and_schemas(core: Core):
    async with Client(create_mcp_server(core)) as client:
        tools = (await client.list_tools()).tools
    tool = next(tool for tool in tools if tool.name == "get_candidate")

    assert tool.title == "Ficha do candidato"
    assert tool.description is not None
    assert "DivulgaCandContas" in tool.description
    assert "Nunca inclui CPF, título de eleitor, data de nascimento ou e-mail" in tool.description
    assert tool.annotations is not None
    assert tool.annotations.read_only_hint is True
    assert tool.annotations.open_world_hint is False

    assert set(tool.input_schema["properties"]) == {
        "sq_candidato",
        "uf",
        "office",
        "number",
        "round",
    }
    assert "required" not in tool.input_schema or tool.input_schema["required"] == []
    assert tool.output_schema is not None
    assert set(tool.output_schema["properties"]) == set(
        CandidateAnswer.model_json_schema()["properties"]
    )
    profile_schema = tool.output_schema["$defs"]["CandidateProfile"]["properties"]
    assert {"gender", "race_color", "marital_status", "education"} <= set(profile_schema)


async def test_get_candidate_by_sq_candidato_returns_the_envelope_and_a_pt_br_text(core: Core):
    async with Client(create_mcp_server(core)) as client:
        result = await client.call_tool("get_candidate", {"sq_candidato": 10000000001})

    assert result.is_error is False
    assert result.structured_content == core.get_candidate(10000000001).model_dump(mode="json")
    text = result.content[0].text
    assert "45 MARIA DA SILVA (Maria Aparecida da Silva), governador, turno 1" in text
    assert "coligação ACRE PARA TODOS" in text
    assert "Chapa: vice governador JOÃO DO ACRE (MDB)." in text
    assert "https://www.instagram.com/mariadasilva45" in text
    assert "Página oficial: https://divulgacandcontas.tse.jus.br/" in text
    assert "Fonte:" in text


async def test_get_candidate_by_the_trio_passes_every_argument_through(core: Core):
    async with Client(create_mcp_server(core)) as client:
        result = await client.call_tool(
            "get_candidate", {"uf": "br", "office": "presidente", "number": "13", "round": 1}
        )

    assert result.is_error is False
    expected = core.get_candidate(uf="br", office="presidente", number="13", round=1)
    assert result.structured_content == expected.model_dump(mode="json")
    assert result.structured_content["data"]["candidate"]["sq_candidato"] == 20000000001


async def test_get_candidate_not_found_is_a_normal_result_with_guidance(core: Core):
    async with Client(create_mcp_server(core)) as client:
        result = await client.call_tool(
            "get_candidate", {"uf": "AC", "office": "governador", "number": 22}
        )

    assert result.is_error is False
    assert result.structured_content["data"] is None
    assert result.structured_content["not_found"]["reason"] == "candidato_nao_encontrado"
    assert result.content[0].text.startswith("Candidato não encontrado.")


async def test_get_candidate_invalid_query_is_a_result_with_is_error(core: Core):
    async with Client(create_mcp_server(core)) as client:
        both = await client.call_tool("get_candidate", {"sq_candidato": 10000000001, "uf": "AC"})
        neither = await client.call_tool("get_candidate", {})

    assert both.is_error is True
    assert "não os dois" in both.content[0].text
    assert neither.is_error is True
    assert "trio completo" in neither.content[0].text


async def test_search_and_resolve_tools_are_listed_with_pt_br_texts_and_schemas(core: Core):
    async with Client(create_mcp_server(core)) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    search = tools["search_polling_places"]
    assert search.title == "Locais de votação da cidade"
    assert search.description is not None
    assert "Para quem não sabe a zona e a seção" in search.description
    assert search.annotations is not None and search.annotations.read_only_hint is True
    assert set(search.input_schema["properties"]) == {
        "uf",
        "municipality",
        "neighborhood",
        "query",
        "near",
        "limit",
        "round",
    }
    assert search.input_schema["required"] == ["uf", "municipality"]
    assert search.output_schema is not None
    assert set(search.output_schema["properties"]) == set(
        PollingPlacesAnswer.model_json_schema()["properties"]
    )

    resolve = tools["resolve_municipality"]
    assert resolve.title == "Código do município"
    assert resolve.description is not None
    assert "com ou sem acento" in resolve.description
    assert set(resolve.input_schema["properties"]) == {"name", "uf", "limit"}
    assert resolve.input_schema["required"] == ["name"]
    assert resolve.output_schema is not None
    assert set(resolve.output_schema["properties"]) == set(
        MunicipalitiesAnswer.model_json_schema()["properties"]
    )


async def test_search_polling_places_returns_the_envelope_and_a_pt_br_text(core: Core):
    async with Client(create_mcp_server(core)) as client:
        result = await client.call_tool(
            "search_polling_places",
            {"uf": "ac", "municipality": "Rio Branco", "neighborhood": "centro"},
        )

    assert result.is_error is False
    expected = core.search_polling_places("ac", "Rio Branco", neighborhood="centro")
    assert result.structured_content == expected.model_dump(mode="json")
    assert "distance_km" not in result.structured_content["data"]["places"][0]
    text = result.content[0].text
    assert "2 locais" in text
    assert "Colégio Acreano" in text
    assert "Para saber a sua seção, consulte o e-Título." in text
    assert "Fonte:" in text


async def test_search_polling_places_with_near_carries_the_distance(core: Core):
    async with Client(create_mcp_server(core)) as client:
        result = await client.call_tool(
            "search_polling_places",
            {
                "uf": "AC",
                "municipality": "Cruzeiro do Sul",
                "near": {"latitude": -7.6, "longitude": -72.7},
                "limit": 5,
            },
        )

    assert result.is_error is False
    places = result.structured_content["data"]["places"]
    assert [p["number"] for p in places] == [1020, 1015]
    assert places[0]["distance_km"] > 0
    assert places[1]["distance_km"] is None
    assert "km" in result.content[0].text


async def test_search_polling_places_ambiguous_municipality_lists_options(core: Core):
    async with Client(create_mcp_server(core)) as client:
        result = await client.call_tool(
            "search_polling_places", {"uf": "AC", "municipality": "porto"}
        )

    assert result.is_error is False
    not_found = result.structured_content["not_found"]
    assert not_found["reason"] == "municipio_ambiguo"
    assert [o["name"] for o in not_found["options"]] == ["Porto Acre", "Porto Walter"]
    assert "Porto Acre" in result.content[0].text


async def test_search_polling_places_invalid_limit_is_a_result_with_is_error(core: Core):
    async with Client(create_mcp_server(core)) as client:
        result = await client.call_tool(
            "search_polling_places", {"uf": "AC", "municipality": "Rio Branco", "limit": 51}
        )
    assert result.is_error is True
    assert "limite inválido" in result.content[0].text


async def test_resolve_municipality_returns_the_envelope_and_a_pt_br_text(core: Core):
    async with Client(create_mcp_server(core)) as client:
        result = await client.call_tool("resolve_municipality", {"name": "colonia"})

    assert result.is_error is False
    expected = core.resolve_municipality("colonia")
    assert result.structured_content == expected.model_dump(mode="json")
    assert result.structured_content["data"]["municipalities"][0]["ibge_code"] is None
    text = result.content[0].text
    assert "Colônia" in text and "ZZ" in text and "30015" in text
    assert "Fonte:" in text


async def test_resolve_municipality_not_found_is_a_normal_result_with_guidance(core: Core):
    async with Client(create_mcp_server(core)) as client:
        result = await client.call_tool("resolve_municipality", {"name": "Xanadu", "uf": "AC"})

    assert result.is_error is False
    assert result.structured_content["data"] is None
    assert result.structured_content["not_found"]["reason"] == "municipio_nao_encontrado"
    assert "Nenhum município" in result.content[0].text
