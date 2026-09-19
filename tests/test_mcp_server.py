"""MCP adapter through the SDK's in-memory client over a real ``Core``."""

from __future__ import annotations

import pytest
from mcp import Client
from mcp.shared.exceptions import MCPError

from br_elections_mcp.core import CandidatesAnswer, Core, ElectionInfoAnswer, PollingPlaceAnswer
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
