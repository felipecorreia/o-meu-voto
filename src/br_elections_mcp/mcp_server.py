"""MCP adapter: one read-only tool per core method, over Streamable HTTP (ADR 0002).

Thin by construction: receives the call, delegates to the core, serializes
the answer. ``structuredContent`` is the envelope, ``content`` a short PT-BR
text for clients that ignore structured output. ``InvalidQuery`` becomes a
result with ``isError``; ``IndexUnavailable`` becomes a server error.
"""

from __future__ import annotations

from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.shared.exceptions import MCPError
from mcp.types import INTERNAL_ERROR, CallToolResult, TextContent, ToolAnnotations
from pydantic import Field

from br_elections_mcp import __version__
from br_elections_mcp.core import (
    CandidatesAnswer,
    Core,
    ElectionInfoAnswer,
    IndexUnavailable,
    InvalidQuery,
    PollingPlaceAnswer,
    Source,
)

SERVER_NAME = "br-elections-mcp"

SERVER_INSTRUCTIONS = (
    "Responde às perguntas do eleitor brasileiro a partir dos dados abertos do TSE: onde votar, "
    "a partir da UF, zona e seção do título, e quem são os candidatos de um cargo numa UF. "
    "Nunca consulta o cadastro eleitoral: para descobrir a própria zona e seção pelo nome ou "
    "CPF, o eleitor usa o e-Título. Nenhuma resposta traz CPF, título de eleitor, data de "
    "nascimento ou e-mail de candidato. Toda resposta cita a fonte (dataset, arquivo e data de "
    "geração) e a licença CC-BY do TSE."
)

FIND_POLLING_PLACE_TITLE = "Onde voto"
FIND_POLLING_PLACE_DESCRIPTION = (
    "Encontra o local de votação a partir da UF, da zona e da seção impressas no título de "
    "eleitor ou no e-Título. Não aceita nome, CPF ou número do título: para descobrir a própria "
    "zona e seção, o eleitor usa o e-Título."
)

ELECTION_INFO_TITLE = "Quando é a eleição"
ELECTION_INFO_DESCRIPTION = (
    "Data e horário da votação, turnos, cargos em disputa e a fonte oficial. Responde 'quando é "
    "a eleição' e 'até que horas posso votar'."
)

LIST_CANDIDATES_TITLE = "Candidatos"
LIST_CANDIDATES_DESCRIPTION = (
    "Lista os candidatos de um cargo numa UF (BR para presidente), com filtro por partido ou por "
    "nome de urna ou nome civil. Nunca inclui CPF, título de eleitor, data de nascimento ou "
    "e-mail."
)

BallotOffice = Literal[
    "presidente",
    "governador",
    "senador",
    "deputado_federal",
    "deputado_estadual",
    "deputado_distrital",
]

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

    @server.tool(
        name="election_info",
        title=ELECTION_INFO_TITLE,
        description=ELECTION_INFO_DESCRIPTION,
        annotations=READ_ONLY,
    )
    def election_info(
        on: Annotated[
            str | None,
            Field(description="Data no formato AAAA-MM-DD; padrão: hoje, horário de Brasília"),
        ] = None,
    ) -> Annotated[CallToolResult, ElectionInfoAnswer]:
        try:
            answer = core.election_info(on)
        except InvalidQuery as exc:
            return CallToolResult(content=[TextContent(type="text", text=str(exc))], is_error=True)
        return CallToolResult(
            content=[TextContent(type="text", text=election_info_text(answer))],
            structured_content=answer.model_dump(mode="json"),
        )

    @server.tool(
        name="list_candidates",
        title=LIST_CANDIDATES_TITLE,
        description=LIST_CANDIDATES_DESCRIPTION,
        annotations=READ_ONLY,
    )
    def list_candidates(
        uf: Annotated[
            str, Field(description="Sigla da UF, 2 letras: estados, DF ou BR para presidente")
        ],
        office: Annotated[BallotOffice, Field(description="Cargo de urna")],
        party: Annotated[
            str | int | None, Field(description="Partido, sigla ou número; opcional")
        ] = None,
        name: Annotated[
            str | None,
            Field(description="Trecho do nome de urna ou do nome civil, sem acento; opcional"),
        ] = None,
        on_ballot_only: Annotated[
            bool, Field(description="Só candidatos carregados na urna (padrão)")
        ] = True,
        limit: Annotated[int, Field(description="Tamanho da página, 1 a 50", ge=1, le=50)] = 50,
        offset: Annotated[int, Field(description="Início da página", ge=0)] = 0,
        round: Annotated[
            int | None, Field(description="Turno, opcional; sem ele, o turno mais recente do cargo")
        ] = None,
    ) -> Annotated[CallToolResult, CandidatesAnswer]:
        try:
            answer = core.list_candidates(
                uf,
                office,
                party=party,
                name=name,
                on_ballot_only=on_ballot_only,
                limit=limit,
                offset=offset,
                round=round,
            )
        except InvalidQuery as exc:
            return CallToolResult(content=[TextContent(type="text", text=str(exc))], is_error=True)
        except IndexUnavailable as exc:
            raise MCPError(code=INTERNAL_ERROR, message=f"índice indisponível: {exc}") from exc
        return CallToolResult(
            content=[TextContent(type="text", text=candidates_text(answer, uf, office))],
            structured_content=answer.model_dump(mode="json"),
        )

    return server


def candidates_text(answer: CandidatesAnswer, uf: str, office: str) -> str:
    """The short PT-BR text of a candidate list, for clients without structured output."""
    assert answer.data is not None
    d = answer.data
    office_label = office.replace("_", " ")
    uf_label = uf.strip().upper()
    if d.total == 0:
        lines = [
            f"Nenhum candidato a {office_label} no {uf_label} (turno {d.round}) com esse filtro."
        ]
    else:
        first, last = d.offset + 1, d.offset + len(d.candidates)
        lines = [
            f"{d.total} candidatos a {office_label} no {uf_label} (turno {d.round}), "
            f"mostrando {first} a {last}:"
        ]
        for c in d.candidates:
            notes = []
            if c.adjudication_status != "DEFERIDO":
                notes.append(c.adjudication_status)
            if not c.on_ballot:
                notes.append("fora da urna")
            suffix = f" - {', '.join(notes)}" if notes else ""
            lines.append(f"{c.number} {c.ballot_name} ({c.party.acronym}){suffix};")
    lines.extend(answer.warnings)
    lines.append(_source_text(answer.source))
    return " ".join(lines)


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
    lines.append(_source_text(answer.source))
    return " ".join(lines)


def election_info_text(answer: ElectionInfoAnswer) -> str:
    """The short PT-BR text of an election-info answer, for clients without structured output."""
    assert answer.data is not None
    d = answer.data
    rounds = "; ".join(f"{r.number}º turno em {r.date.strftime('%d/%m/%Y')}" for r in d.rounds)
    lines = [f"Eleição com {len(d.rounds)} turno(s): {rounds}. Votação {d.voting_hours.label}."]
    if d.next_round is not None:
        lines.append(
            f"Próximo turno: {d.next_round.number}º em "
            f"{d.next_round.date.strftime('%d/%m/%Y')} (faltam {d.days_until_next_round} dia(s))."
        )
    lines.extend(d.notes)
    lines.append(f"Fonte: {d.calendar_source.title}.")
    return " ".join(lines)


def _source_text(source: Source) -> str:
    return (
        f"Fonte: {source.dataset} ({source.file}), gerado pelo TSE em "
        f"{source.generated_at.strftime('%d/%m/%Y %H:%M')}. Licença {source.license}."
    )
