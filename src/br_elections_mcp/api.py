"""REST adapter: the same envelope as the MCP tools, as JSON under ``/api/v1``, GET only.

Thin by construction: it does not normalize input, format warnings or touch
the index. ``InvalidQuery`` is 400 with the core's message;
``IndexUnavailable`` is 503. OpenAPI is served at ``/api/v1/openapi.json``
once the app is mounted there.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

from br_elections_mcp import __version__
from br_elections_mcp.core import (
    CandidatesAnswer,
    Core,
    ElectionInfoAnswer,
    IndexUnavailable,
    InvalidQuery,
    PollingPlaceAnswer,
)


def create_api(core: Core) -> FastAPI:
    api = FastAPI(
        title="br-elections-mcp REST API",
        version=__version__,
        description=(
            "As perguntas do eleitor sobre os dados abertos do TSE, sem dado pessoal. "
            "Mesmo envelope das tools MCP: data, not_found, warnings, election, source."
        ),
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url=None,
    )

    @api.exception_handler(InvalidQuery)
    async def invalid_query(_: Request, exc: InvalidQuery) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @api.exception_handler(IndexUnavailable)
    async def index_unavailable(_: Request, exc: IndexUnavailable) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @api.get(
        "/polling-place",
        response_model=PollingPlaceAnswer,
        summary="Onde voto",
        description=(
            "Local de votação a partir da UF, zona e seção do título de eleitor. Não aceita nome, "
            "CPF ou número do título."
        ),
        responses={
            400: {"description": "Entrada fora do domínio"},
            503: {"description": "Índice indisponível"},
        },
    )
    def polling_place(
        uf: Annotated[str, Query(description="Sigla da UF: estados, DF ou ZZ")],
        zone: Annotated[str, Query(description="Zona eleitoral; aceita zeros à esquerda")],
        section: Annotated[str, Query(description="Seção eleitoral; aceita zeros à esquerda")],
        round: Annotated[str | None, Query(description="Turno, opcional")] = None,
    ) -> PollingPlaceAnswer:
        return core.find_polling_place(uf, zone, section, round)

    @api.get(
        "/election",
        response_model=ElectionInfoAnswer,
        summary="Quando é a eleição",
        description=(
            "Data e horário da votação, turnos, cargos em disputa e a fonte oficial. Responde "
            "'quando é a eleição' e 'até que horas posso votar'."
        ),
        responses={400: {"description": "Entrada fora do domínio"}},
    )
    def election(
        on: Annotated[
            str | None, Query(description="Data no formato AAAA-MM-DD; padrão: hoje")
        ] = None,
    ) -> ElectionInfoAnswer:
        return core.election_info(on)

    @api.get(
        "/candidates",
        response_model=CandidatesAnswer,
        summary="Candidatos",
        description=(
            "Candidatos de um cargo numa UF (BR para presidente), com filtro por partido ou por "
            "nome de urna ou nome civil. Nunca inclui CPF, título de eleitor, data de nascimento "
            "ou e-mail."
        ),
        responses={
            400: {"description": "Entrada fora do domínio"},
            503: {"description": "Índice indisponível"},
        },
    )
    def candidates(
        uf: Annotated[str, Query(description="Sigla da UF: estados, DF ou BR para presidente")],
        office: Annotated[
            str,
            Query(
                description=(
                    "Cargo de urna: presidente, governador, senador, deputado_federal, "
                    "deputado_estadual ou deputado_distrital"
                )
            ),
        ],
        party: Annotated[str | None, Query(description="Partido, sigla ou número")] = None,
        name: Annotated[
            str | None, Query(description="Trecho do nome de urna ou do nome civil")
        ] = None,
        on_ballot_only: Annotated[
            bool, Query(description="Só candidatos carregados na urna (padrão)")
        ] = True,
        limit: Annotated[str, Query(description="Tamanho da página, 1 a 50")] = "50",
        offset: Annotated[str, Query(description="Início da página")] = "0",
        round: Annotated[str | None, Query(description="Turno, opcional")] = None,
    ) -> CandidatesAnswer:
        return core.list_candidates(
            uf,
            office,
            party=party,
            name=name,
            on_ballot_only=on_ballot_only,
            limit=limit,
            offset=offset,
            round=round,
        )

    return api
