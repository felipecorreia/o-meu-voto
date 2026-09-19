"""MCP adapter: one read-only tool per core method, over Streamable HTTP (ADR 0002).

Thin by construction: receives the call, delegates to the core, serializes
the answer. ``structuredContent`` is the envelope, ``content`` a short PT-BR
text for clients that ignore structured output. ``InvalidQuery`` becomes a
result with ``isError``; ``IndexUnavailable`` becomes a server error.
"""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.shared.exceptions import MCPError
from mcp.types import INTERNAL_ERROR, CallToolResult, TextContent, ToolAnnotations
from pydantic import Field

from br_elections_mcp import __version__
from br_elections_mcp.core import Core, IndexUnavailable, InvalidQuery, PollingPlaceAnswer

SERVER_NAME = "br-elections-mcp"

SERVER_INSTRUCTIONS = (
    "Responde às perguntas do eleitor brasileiro a partir dos dados abertos do TSE: onde votar, "
    "a partir da UF, zona e seção do título. Nunca consulta o cadastro eleitoral: para descobrir "
    "a própria zona e seção pelo nome ou CPF, o eleitor usa o e-Título. Toda resposta cita a "
    "fonte (dataset, arquivo e data de geração) e a licença CC-BY do TSE."
)

FIND_POLLING_PLACE_TITLE = "Onde voto"
FIND_POLLING_PLACE_DESCRIPTION = (
    "Encontra o local de votação a partir da UF, da zona e da seção impressas no título de "
    "eleitor ou no e-Título. Não aceita nome, CPF ou número do título: para descobrir a própria "
    "zona e seção, o eleitor usa o e-Título."
)

READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)


def create_mcp_server(core: Core) -> MCPServer:
    server = MCPServer(
        name=SERVER_NAME,
        title="Eleições brasileiras (TSE)",
        version=__version__,
        instructions=SERVER_INSTRUCTIONS,
    )

    @server.tool(
        name="find_polling_place",
        title=FIND_POLLING_PLACE_TITLE,
        description=FIND_POLLING_PLACE_DESCRIPTION,
        annotations=READ_ONLY,
    )
    def find_polling_place(
        uf: Annotated[
            str, Field(description="Sigla da UF, 2 letras: estados, DF ou ZZ para o exterior")
        ],
        zone: Annotated[
            int | str, Field(description="Zona eleitoral do título; aceita zeros à esquerda")
        ],
        section: Annotated[
            int | str, Field(description="Seção eleitoral do título; aceita zeros à esquerda")
        ],
        round: Annotated[
            int | None, Field(description="Turno, opcional; sem ele, o turno mais recente")
        ] = None,
    ) -> Annotated[CallToolResult, PollingPlaceAnswer]:
        try:
            answer = core.find_polling_place(uf, zone, section, round)
        except InvalidQuery as exc:
            return CallToolResult(content=[TextContent(type="text", text=str(exc))], is_error=True)
        except IndexUnavailable as exc:
            raise MCPError(code=INTERNAL_ERROR, message=f"índice indisponível: {exc}") from exc
        return CallToolResult(
            content=[TextContent(type="text", text=polling_place_text(answer))],
            structured_content=answer.model_dump(mode="json"),
        )

    return server


def polling_place_text(answer: PollingPlaceAnswer) -> str:
    """The short PT-BR text of a polling-place answer, for clients without structured output."""
    if answer.data is None:
        assert answer.not_found is not None
        lines = [f"Seção não encontrada. {answer.not_found.guidance}"]
    else:
        d = answer.data
        p = d.place
        lines = [
            f"Zona {d.zone}, seção {d.section} ({d.municipality.name} - {d.municipality.uf}), "
            f"turno {d.round}: {p.name}, {p.address}, {p.neighborhood}, CEP {p.postal_code}."
        ]
        accessibility = (
            "com acessibilidade"
            if d.accessibility == "com_acessibilidade"
            else "sem acessibilidade"
        )
        lines.append(
            f"Seção {d.section_kind}, {accessibility}; o local tem {p.section_count} seções, "
            f"{p.accessible_section_count} com acessibilidade."
        )
    lines.extend(answer.warnings)
    lines.append(
        f"Fonte: {answer.source.dataset} ({answer.source.file}), gerado pelo TSE em "
        f"{answer.source.generated_at.strftime('%d/%m/%Y %H:%M')}. Licença {answer.source.license}."
    )
    return " ".join(lines)
