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

from pydantic import BaseModel, ConfigDict, Field

LICENSE = "CC-BY"
ATTRIBUTION = "Tribunal Superior Eleitoral - Portal de Dados Abertos"


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True)


class NotFound(_Model):
    reason: Literal["secao_nao_encontrada"] = Field(description="Motivo, em PT-BR")
    guidance: str = Field(description="Orientação ao eleitor, em PT-BR")


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


class Municipality(_Model):
    tse_code: str = Field(description="Código TSE, 5 dígitos")
    ibge_code: int | None = Field(description="Código IBGE de 7 dígitos; nulo no exterior")
    name: str
    uf: str


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
