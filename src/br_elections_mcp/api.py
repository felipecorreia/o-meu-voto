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
from br_elections_mcp.core import Core, IndexUnavailable, InvalidQuery, PollingPlaceAnswer


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

    return api
