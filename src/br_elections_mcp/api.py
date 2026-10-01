"""REST adapter: the same envelope as the MCP tools, as JSON under ``/api/v1``, GET only.

Thin by construction: it does not normalize input, format warnings or touch
the index. The one transport repair is ``&amp;`` read as a query separator (issue #115).
``InvalidQuery`` is 400 with the core's message;
``IndexUnavailable`` is 503. OpenAPI is served at ``/api/v1/openapi.json``
once the app is mounted there.
"""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import FastAPI, Path, Query, Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from br_elections_mcp import __version__
from br_elections_mcp.core import (
    CandidateAnswer,
    CandidatesAnswer,
    CandidatesComparisonAnswer,
    Core,
    ElectionInfoAnswer,
    IndexUnavailable,
    InvalidQuery,
    MunicipalitiesAnswer,
    PollingPlaceAnswer,
    PollingPlacesAnswer,
)
from br_elections_mcp.telemetry import Telemetry

_HTML_ESCAPED_SEPARATOR = re.compile(rb"&amp;", re.IGNORECASE)


class HtmlEscapedQueryMiddleware:
    """Read a literal ``&amp;`` in the raw query string as the ``&`` separator.

    Assistants that copy a URL out of rendered HTML send ``uf=SP&amp;office=senador``, which
    parses as ``amp;office`` and answers 422 for a missing ``office`` (issue #115). A value
    that really contains ``&amp;`` arrives percent-encoded, so only the separator changes.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            query = _HTML_ESCAPED_SEPARATOR.sub(b"&", scope["query_string"])
            if query != scope["query_string"]:
                scope = {**scope, "query_string": query}
        await self.app(scope, receive, send)


def _split_commas(values: list[str] | None) -> list[str] | None:
    """``number=45,13`` is ``number=45&number=13``: some URL readers keep one value per name."""
    return None if values is None else [part for value in values for part in value.split(",")]


def create_api(core: Core, *, telemetry: Telemetry | None = None) -> FastAPI:
    telemetry = telemetry if telemetry is not None else Telemetry()
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
    api.add_middleware(HtmlEscapedQueryMiddleware)

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
        return telemetry.call(
            "GET /api/v1/polling-place", lambda: core.find_polling_place(uf, zone, section, round)
        )

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
        return telemetry.call("GET /api/v1/election", lambda: core.election_info(on))

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
        return telemetry.call(
            "GET /api/v1/candidates",
            lambda: core.list_candidates(
                uf,
                office,
                party=party,
                name=name,
                on_ballot_only=on_ballot_only,
                limit=limit,
                offset=offset,
                round=round,
            ),
        )

    # Declaration order is part of the contract (codebase-design 4): `by-number` and `compare`
    # come before `{sq_candidato}`, because the first matching route wins and the `int`
    # annotation only turns a non-numeric segment into a clear 422, it never keeps the path
    # from matching.
    @api.get(
        "/candidates/by-number",
        response_model=CandidateAnswer,
        summary="Ficha do candidato por número",
        description=(
            "Ficha de um candidato por UF, cargo e número de urna, só entre os candidatos na "
            "urna. Inclui vice ou suplentes da chapa, redes sociais declaradas ao TSE e o link "
            "da página oficial no DivulgaCandContas. Nunca inclui CPF, título de eleitor, data "
            "de nascimento ou e-mail."
        ),
        responses={
            400: {"description": "Entrada fora do domínio"},
            503: {"description": "Índice indisponível"},
        },
    )
    def candidate_by_number(
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
        number: Annotated[str, Query(description="Número que o eleitor digita na urna")],
        round: Annotated[str | None, Query(description="Turno, opcional")] = None,
    ) -> CandidateAnswer:
        return telemetry.call(
            "GET /api/v1/candidates/by-number",
            lambda: core.get_candidate(uf=uf, office=office, number=number, round=round),
        )

    @api.get(
        "/candidates/compare",
        response_model=CandidatesComparisonAnswer,
        summary="Comparar candidatos",
        description=(
            "Compara lado a lado de 2 a 4 candidaturas do mesmo cargo, UF e turno, por sq "
            "ou por number, repetido ou separado por vírgula (number=45,13): partido, aliança, "
            "situação do registro, destino dos votos, ocupação, chapa, foto, total de bens "
            "declarados e links oficiais. Sempre em ordem de número de urna: não ordena por "
            "valor, não pontua e não recomenda voto. "
            "Sem sq nem number, compara todas as candidaturas na urna quando são de 2 a 4. Nunca "
            "inclui CPF, título de eleitor, data de nascimento, idade, gênero, cor/raça, estado "
            "civil ou escolaridade."
        ),
        responses={
            400: {"description": "Entrada fora do domínio"},
            503: {"description": "Índice indisponível"},
        },
    )
    def compare_candidates(
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
        sq: Annotated[
            list[str] | None,
            Query(
                description="sq_candidato, de 2 a 4, repetido ou separado por vírgula; ou number"
            ),
        ] = None,
        number: Annotated[
            list[str] | None,
            Query(description="Número de urna, de 2 a 4, repetido ou separado por vírgula; ou sq"),
        ] = None,
        round: Annotated[str | None, Query(description="Turno, opcional")] = None,
    ) -> CandidatesComparisonAnswer:
        return telemetry.call(
            "GET /api/v1/candidates/compare",
            lambda: core.compare_candidates(
                uf,
                office,
                sq_candidatos=_split_commas(sq),
                numbers=_split_commas(number),
                round=round,
            ),
        )

    @api.get(
        "/candidates/{sq_candidato}",
        response_model=CandidateAnswer,
        summary="Ficha do candidato",
        description=(
            "Ficha de um candidato pelo sq_candidato. Inclui vice ou suplentes da chapa, redes "
            "sociais declaradas ao TSE e o link da página oficial no DivulgaCandContas. Nunca "
            "inclui CPF, título de eleitor, data de nascimento ou e-mail."
        ),
        responses={
            400: {"description": "Entrada fora do domínio"},
            422: {"description": "sq_candidato não numérico"},
            503: {"description": "Índice indisponível"},
        },
    )
    def candidate(
        sq_candidato: Annotated[int, Path(description="Número sequencial da candidatura no TSE")],
        round: Annotated[str | None, Query(description="Turno, opcional")] = None,
    ) -> CandidateAnswer:
        return telemetry.call(
            "GET /api/v1/candidates/{sq_candidato}",
            lambda: core.get_candidate(sq_candidato, round=round),
        )

    @api.get(
        "/polling-places",
        response_model=PollingPlacesAnswer,
        summary="Locais de votação da cidade",
        description=(
            "Locais de votação de um município, com filtro por bairro, nome do local ou endereço, "
            "e ordenados pela distância a (lat, lon) quando informados. Para quem não sabe a zona "
            "e a seção."
        ),
        responses={
            400: {"description": "Entrada fora do domínio"},
            503: {"description": "Índice indisponível"},
        },
    )
    def polling_places(
        uf: Annotated[str, Query(description="Sigla da UF: estados, DF ou ZZ")],
        municipality: Annotated[str, Query(description="Nome do município ou código TSE")],
        neighborhood: Annotated[str | None, Query(description="Bairro, opcional")] = None,
        query: Annotated[
            str | None, Query(description="Texto que casa com o nome do local ou o endereço")
        ] = None,
        lat: Annotated[str | None, Query(description="Latitude do eleitor, com lon")] = None,
        lon: Annotated[str | None, Query(description="Longitude do eleitor, com lat")] = None,
        limit: Annotated[str | None, Query(description="1 a 50; padrão 20")] = None,
        offset: Annotated[str, Query(description="Início da página")] = "0",
        round: Annotated[str | None, Query(description="Turno, opcional")] = None,
    ) -> PollingPlacesAnswer:
        # lat/lon are the REST spelling of `near`; the core validates the pair.
        near = None if lat is None and lon is None else {"latitude": lat, "longitude": lon}
        return telemetry.call(
            "GET /api/v1/polling-places",
            lambda: core.search_polling_places(
                uf, municipality, neighborhood, query, near, limit, round, offset=offset
            ),
        )

    @api.get(
        "/municipalities",
        response_model=MunicipalitiesAnswer,
        summary="Código do município",
        description=(
            "Código TSE de um município a partir do nome, com ou sem acento, para usar nas "
            "outras rotas."
        ),
        responses={
            400: {"description": "Entrada fora do domínio"},
            503: {"description": "Índice indisponível"},
        },
    )
    def municipalities(
        name: Annotated[str, Query(description="Nome do município, com ou sem acento")],
        uf: Annotated[str | None, Query(description="Sigla da UF, opcional")] = None,
        limit: Annotated[str | None, Query(description="1 a 50; padrão 10")] = None,
    ) -> MunicipalitiesAnswer:
        return telemetry.call(
            "GET /api/v1/municipalities", lambda: core.resolve_municipality(name, uf, limit)
        )

    return api
