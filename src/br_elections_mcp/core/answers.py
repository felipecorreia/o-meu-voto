"""Answer models: the interface of the core and the output schema of both adapters.

Every answer carries the envelope of codebase-design section 8: ``data``,
``not_found``, ``warnings``, ``election`` and ``source``. Field names are in
English; enum values, warnings and guidance are PT-BR texts ready for the
voter. The MCP ``outputSchema`` and the REST OpenAPI are generated from these
models, so a contract change happens in this file only.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SerializerFunctionWrapHandler, model_serializer

from br_elections_mcp.domain import Office

LICENSE = "CC-BY"
ATTRIBUTION = "Tribunal Superior Eleitoral - Portal de Dados Abertos"


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True)


class Municipality(_Model):
    tse_code: str = Field(description="Código TSE, 5 dígitos")
    ibge_code: int | None = Field(description="Código IBGE de 7 dígitos; nulo no exterior")
    name: str
    uf: str


class MunicipalityMatch(Municipality):
    """One candidate of ``resolve_municipality``: a municipality with how well it matched."""

    score: float = Field(
        description="1.0 para o nome exato (sem acento e sem diferenciar maiúsculas), menor "
        "para nome parcial ou parecido"
    )


NotFoundReason = Literal["secao_nao_encontrada", "municipio_nao_encontrado", "municipio_ambiguo"]


class NotFound(_Model):
    reason: NotFoundReason = Field(description="Motivo, em PT-BR")
    guidance: str = Field(description="Orientação ao eleitor, em PT-BR")
    options: list[MunicipalityMatch] | None = Field(
        default=None,
        description="Os municípios que casaram, quando o motivo é municipio_ambiguo",
    )


class ElectionRoundInfo(_Model):
    number: int
    date: dt.date


class VotingHoursInfo(_Model):
    start: str = Field(description="HH:MM")
    end: str = Field(description="HH:MM")
    timezone: str = Field(description="Nome IANA, ex.: America/Sao_Paulo")
    label: str = Field(description="Texto para o eleitor, ex.: '8h às 17h (horário de Brasília)'")


class ElectionInfo(_Model):
    """The current election of the calendar, with the round the answer refers to."""

    id: str
    name: str
    round: ElectionRoundInfo
    voting_hours: VotingHoursInfo


class Source(_Model):
    """Where the data came from, required by the CC-BY license (domain-model 3.6)."""

    kind: Literal["dataset"] = "dataset"
    dataset: str
    dataset_url: str
    file: str
    generated_at: dt.datetime = Field(
        description="Instante em que o TSE gerou o arquivo (DT_GERACAO + HH_GERACAO)"
    )
    index_built_at: dt.datetime
    license: str = LICENSE
    attribution: str = ATTRIBUTION


class PollingPlace(_Model):
    number: int
    name: str
    kind: str = Field(description="Tipo do local, como o TSE publica, ex.: 'Convencional'")
    address: str
    neighborhood: str
    postal_code: str = Field(description="CEP, 8 dígitos")
    phone: str | None
    latitude: float | None
    longitude: float | None
    status: Literal["ativo", "bloqueado"]
    section_count: int = Field(description="Seções que funcionam neste local, no turno")
    accessible_section_count: int = Field(description="Dessas, quantas têm acessibilidade")


class PreviousPlace(_Model):
    number: int
    name: str
    address: str


class PollingPlaceData(_Model):
    municipality: Municipality
    round: int = Field(description="Turno a que a resposta se refere")
    zone: int
    section: int
    section_kind: Literal["principal", "agregada"]
    votes_at_section: int = Field(
        description="Seção em que o eleitor efetivamente vota: a principal, se a dele é agregada"
    )
    voters_in_section: int
    accessibility: Literal["com_acessibilidade", "sem_acessibilidade"]
    place: PollingPlace
    previous_place: PreviousPlace | None = Field(
        description="Local anterior, quando a seção foi transferida"
    )


class PollingPlaceAnswer(_Model):
    """Answer of ``find_polling_place`` (codebase-design 8.1)."""

    data: PollingPlaceData | None
    not_found: NotFound | None
    warnings: list[str] = Field(description="Avisos ao eleitor, em PT-BR; pode ser vazia")
    election: ElectionInfo | None
    source: Source


class ElectionInfoRound(_Model):
    number: int
    date: dt.date
    note: str | None = None


class CalendarSourceInfo(_Model):
    """The normative act the calendar was curated from (domain-model 3.1)."""

    title: str
    url: str
    verified_at: dt.date


class CuratedSource(_Model):
    """Source for answers curated from ``data/elections.yaml`` (domain-model 3.6):
    ``calendar_source`` replaces ``dataset`` and ``verified_at`` replaces ``generated_at``.
    Never ages, so ``stale`` and ``age_hours`` are absent.
    """

    kind: Literal["curated"] = "curated"
    calendar_source: str = Field(description="Título da fonte curada, ex.: a resolução do TSE")
    verified_at: dt.date
    license: str = LICENSE
    attribution: str = ATTRIBUTION


class ElectionInfoData(_Model):
    rounds: list[ElectionInfoRound]
    voting_hours: VotingHoursInfo
    next_round: ElectionInfoRound | None = Field(
        description="Próximo turno a partir da data consultada, ou nulo após o último turno"
    )
    days_until_next_round: int | None = Field(
        description="Dias até next_round, ou nulo quando não há próximo turno"
    )
    offices: list[Office]
    notes: list[str] = Field(description="Avisos curados ao eleitor, em PT-BR; pode ser vazia")
    calendar_source: CalendarSourceInfo


class ElectionInfoAnswer(_Model):
    """Answer of ``election_info`` (codebase-design 8.5). Never ``not_found`` and never stale."""

    data: ElectionInfoData | None
    not_found: NotFound | None
    warnings: list[str] = Field(description="Avisos ao eleitor, em PT-BR; sempre vazia aqui")
    election: ElectionInfo | None
    source: CuratedSource


class Party(_Model):
    number: int
    acronym: str
    name: str


class Federation(_Model):
    acronym: str
    name: str


class Coalition(_Model):
    name: str


class CandidateListItem(_Model):
    """One candidate as ``list_candidates`` shows it (codebase-design 8.3).

    Deliberately without ``gender``, ``race_color``, ``marital_status`` and
    ``education``: those exist only in the individual profile of ``get_candidate``.
    """

    sq_candidato: int = Field(description="Número sequencial da candidatura no TSE")
    number: int = Field(description="Número que o eleitor digita na urna")
    ballot_name: str = Field(description="Nome de urna")
    name: str = Field(description="Nome civil")
    office: Office
    party: Party
    federation: Federation | None
    coalition: Coalition | None
    adjudication_status: str = Field(
        description="Situação de julgamento do registro, como o TSE publica"
    )
    on_ballot: bool = Field(description="Se o candidato está carregado na urna eletrônica")
    occupation: str | None
    photo_url: str | None = Field(
        description="Foto oficial espelhada; nula enquanto não há espelho"
    )


class CandidatesData(_Model):
    round: int = Field(description="Turno a que a resposta se refere")
    candidates: list[CandidateListItem]
    total: int = Field(description="Total de candidatos que casam com o filtro, sem paginação")
    limit: int
    offset: int


class CandidatesAnswer(_Model):
    """Answer of ``list_candidates`` (codebase-design 8.3). An empty list is data, never
    ``not_found``."""

    data: CandidatesData | None
    not_found: NotFound | None
    warnings: list[str] = Field(description="Avisos ao eleitor, em PT-BR; pode ser vazia")
    election: ElectionInfo | None
    source: Source


class PollingPlaceListItem(PollingPlace):
    """One place of ``search_polling_places``: the place, its zone, its voters and, only when
    the client sent ``near``, its distance. ``distance_km`` is absent (not null) otherwise."""

    zone: int
    voters: int = Field(description="Soma dos eleitores das seções do local, no turno")
    distance_km: float | None = Field(
        default=None,
        description="Distância em km ao ponto informado em `near`; nula para local sem "
        "coordenadas; ausente sem `near`",
    )

    @model_serializer(mode="wrap")
    def _omit_distance_without_near(self, handler: SerializerFunctionWrapHandler) -> dict:
        serialized = handler(self)
        if "distance_km" in self.model_fields_set:
            return serialized
        serialized.pop("distance_km", None)
        return serialized


class PollingPlacesData(_Model):
    round: int = Field(description="Turno a que a resposta se refere")
    municipality: Municipality
    places: list[PollingPlaceListItem]
    total: int = Field(description="Total de locais que casam com o filtro, antes do limite")
    guidance: str = Field(description="Orientação ao eleitor, em PT-BR")


class PollingPlacesAnswer(_Model):
    """Answer of ``search_polling_places`` (codebase-design 8.2)."""

    data: PollingPlacesData | None
    not_found: NotFound | None
    warnings: list[str] = Field(description="Avisos ao eleitor, em PT-BR; pode ser vazia")
    election: ElectionInfo | None
    source: Source


class MunicipalitiesData(_Model):
    municipalities: list[MunicipalityMatch] = Field(
        description="Do melhor para o pior `score`; nunca vazia (sem candidato é not_found)"
    )


class MunicipalitiesAnswer(_Model):
    """Answer of ``resolve_municipality`` (codebase-design 8.6).

    ``election`` is always null: the municipality list refers to no round.
    """

    data: MunicipalitiesData | None
    not_found: NotFound | None
    warnings: list[str] = Field(description="Avisos ao eleitor, em PT-BR; pode ser vazia")
    election: ElectionInfo | None
    source: Source
