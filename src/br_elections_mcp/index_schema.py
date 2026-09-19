"""Index schema shared by the pipeline (writer) and the core (reader).

Three things live here because both sides must agree on them and nothing else
may redefine them: the columns the TSE files are expected to carry, the
columns that are discarded before anything is written (LGPD, ADR 0004), and
the tables of ``index.duckdb`` plus the ``manifest.json`` that travels with it.
The pipeline never imports the core and the core never imports the pipeline;
this module is their only shared vocabulary.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = 2

INDEX_FILE_NAME = "index.duckdb"
MANIFEST_FILE_NAME = "manifest.json"

TSE_TIMEZONE = "America/Sao_Paulo"
"""Timezone in which the TSE writes ``DT_GERACAO`` and ``HH_GERACAO``."""

CSV_READ_OPTIONS = "delim=';', header=true, quote='\"', encoding='latin-1', all_varchar=true"
"""``read_csv`` options matching how the TSE distributes every CSV; shared by build and validate."""

FORBIDDEN_COLUMNS: frozenset[str] = frozenset(
    {
        "NR_CPF_CANDIDATO",
        "NR_TITULO_ELEITORAL_CANDIDATO",
        "DT_NASCIMENTO",
        "SG_UF_NASCIMENTO",
        "DS_EMAIL",
    }
)
"""Personal-data columns dropped before any write. The exact list of ADR 0004."""

POLLING_PLACES_CSV_COLUMNS: tuple[str, ...] = (
    "DT_GERACAO",
    "HH_GERACAO",
    "AA_ELEICAO",
    "DT_ELEICAO",
    "DS_ELEICAO",
    "NR_TURNO",
    "SG_UF",
    "CD_MUNICIPIO",
    "NM_MUNICIPIO",
    "NR_ZONA",
    "NR_SECAO",
    "CD_TIPO_SECAO_AGREGADA",
    "DS_TIPO_SECAO_AGREGADA",
    "NR_SECAO_PRINCIPAL",
    "NR_LOCAL_VOTACAO",
    "NM_LOCAL_VOTACAO",
    "CD_TIPO_LOCAL",
    "DS_TIPO_LOCAL",
    "DS_ENDERECO",
    "NM_BAIRRO",
    "NR_CEP",
    "NR_TELEFONE_LOCAL",
    "NR_LATITUDE",
    "NR_LONGITUDE",
    "CD_SITU_LOCAL_VOTACAO",
    "DS_SITU_LOCAL_VOTACAO",
    "CD_SITU_ZONA",
    "DS_SITU_ZONA",
    "CD_SITU_SECAO",
    "DS_SITU_SECAO",
    "CD_SITU_LOCALIDADE",
    "DS_SITU_LOCALIDADE",
    "CD_SITU_SECAO_ACESSIBILIDADE",
    "DS_SITU_SECAO_ACESSIBILIDADE",
    "QT_ELEITOR_SECAO",
    "QT_ELEITOR_ELEICAO_FEDERAL",
    "QT_ELEITOR_ELEICAO_ESTADUAL",
    "QT_ELEITOR_ELEICAO_MUNICIPAL",
    "NR_LOCAL_VOTACAO_ORIGINAL",
    "NM_LOCAL_VOTACAO_ORIGINAL",
    "DS_ENDERECO_LOCVT_ORIGINAL",
)
"""Header of ``eleitorado_local_votacao_*.csv`` (docs/domain-model.md, 3.3 and 3.4)."""

MUNICIPALITIES_CSV_COLUMNS: tuple[str, ...] = (
    "DT_GERACAO",
    "HH_GERACAO",
    "SG_UF",
    "CD_UF_TSE",
    "CD_UF_IBGE",
    "NM_UF",
    "CD_MUNICIPIO_TSE",
    "CD_MUNICIPIO_IBGE",
    "NM_MUNICIPIO_TSE",
    "NM_MUNICIPIO_IBGE",
)
"""Header of the TSE/IBGE crosswalk ``municipio_tse_ibge.csv`` (docs/domain-model.md, 3.2)."""

CANDIDATES_CSV_COLUMNS: tuple[str, ...] = (
    "DT_GERACAO",
    "HH_GERACAO",
    "ANO_ELEICAO",
    "NR_TURNO",
    "DT_ELEICAO",
    "SG_UF",
    "DS_CARGO",
    "SQ_CANDIDATO",
    "NR_CANDIDATO",
    "NM_CANDIDATO",
    "NM_URNA_CANDIDATO",
    "NM_SOCIAL_CANDIDATO",
    "TP_AGREMIACAO",
    "NR_PARTIDO",
    "SG_PARTIDO",
    "NM_PARTIDO",
    "NR_FEDERACAO",
    "NM_FEDERACAO",
    "SG_FEDERACAO",
    "DS_COMPOSICAO_FEDERACAO",
    "NM_COLIGACAO",
    "DS_COMPOSICAO_COLIGACAO",
    "DS_GENERO",
    "DS_GRAU_INSTRUCAO",
    "DS_ESTADO_CIVIL",
    "DS_COR_RACA",
    "DS_OCUPACAO",
)
"""Columns of ``consulta_cand_*.csv`` the build reads (docs/domain-model.md, 3.5).

The file carries more (codes redundant with descriptions, totalization, and the
five forbidden columns); everything not listed here is ignored, and the
forbidden ones are dropped at the first read.
"""

CANDIDATES_COMPLEMENTARY_CSV_COLUMNS: tuple[str, ...] = (
    "DT_GERACAO",
    "HH_GERACAO",
    "SQ_CANDIDATO",
    "ST_CANDIDATO_INSERIDO_URNA",
    "DS_SITUACAO_JULGAMENTO",
)
"""Columns of ``consulta_cand_complementar_*.csv`` the build reads.

``NR_TURNO`` is optional: when present the join is by (``SQ_CANDIDATO``,
``NR_TURNO``); when absent the file is deduplicated by ``SQ_CANDIDATO`` and
applied to every round (docs/domain-model.md, 3.5 and 7).
"""

CANDIDATE_SOCIAL_LINKS_CSV_COLUMNS: tuple[str, ...] = (
    "DT_GERACAO",
    "HH_GERACAO",
    "SQ_CANDIDATO",
    "NR_ORDEM_REDE_SOCIAL",
    "DS_URL",
)
"""Columns of ``rede_social_candidato_*.csv`` the build reads."""

TABLES: dict[str, str] = {
    "municipalities": """
        CREATE TABLE municipalities (
            tse_code    VARCHAR NOT NULL PRIMARY KEY,
            ibge_code   INTEGER,
            name        VARCHAR NOT NULL,
            uf          VARCHAR NOT NULL,
            search_name VARCHAR NOT NULL
        )
    """,
    "polling_places": """
        CREATE TABLE polling_places (
            uf                       VARCHAR NOT NULL,
            zone                     INTEGER NOT NULL,
            number                   INTEGER NOT NULL,
            round                    INTEGER NOT NULL,
            municipality_tse_code    VARCHAR NOT NULL,
            name                     VARCHAR NOT NULL,
            kind                     VARCHAR NOT NULL,
            address                  VARCHAR NOT NULL,
            neighborhood             VARCHAR NOT NULL,
            postal_code              VARCHAR NOT NULL,
            phone                    VARCHAR,
            latitude                 DOUBLE,
            longitude                DOUBLE,
            status                   VARCHAR NOT NULL,
            section_count            INTEGER NOT NULL,
            accessible_section_count INTEGER NOT NULL,
            voters                   INTEGER NOT NULL,
            PRIMARY KEY (uf, zone, number, round)
        )
    """,
    "polling_sections": """
        CREATE TABLE polling_sections (
            uf                     VARCHAR NOT NULL,
            zone                   INTEGER NOT NULL,
            section                INTEGER NOT NULL,
            round                  INTEGER NOT NULL,
            municipality_tse_code  VARCHAR NOT NULL,
            place_number           INTEGER NOT NULL,
            section_kind           VARCHAR NOT NULL,
            main_section           INTEGER,
            voters                 INTEGER NOT NULL,
            accessibility          VARCHAR NOT NULL,
            status                 VARCHAR NOT NULL,
            election_date          DATE,
            previous_place_number  INTEGER,
            previous_place_name    VARCHAR,
            previous_place_address VARCHAR,
            PRIMARY KEY (uf, zone, section, round)
        )
    """,
    "candidates": """
        CREATE TABLE candidates (
            sq_candidato           BIGINT NOT NULL,
            round                  INTEGER NOT NULL,
            uf                     VARCHAR NOT NULL,
            office                 VARCHAR NOT NULL,
            number                 INTEGER NOT NULL,
            ballot_name            VARCHAR NOT NULL,
            name                   VARCHAR NOT NULL,
            social_name            VARCHAR,
            search_ballot_name     VARCHAR NOT NULL,
            search_name            VARCHAR NOT NULL,
            party_number           INTEGER NOT NULL,
            party_acronym          VARCHAR NOT NULL,
            party_name             VARCHAR NOT NULL,
            search_party_acronym   VARCHAR NOT NULL,
            nomination_kind        VARCHAR NOT NULL,
            federation_acronym     VARCHAR,
            federation_name        VARCHAR,
            federation_composition VARCHAR,
            coalition_name         VARCHAR,
            coalition_composition  VARCHAR,
            adjudication_status    VARCHAR NOT NULL,
            on_ballot              BOOLEAN NOT NULL,
            occupation             VARCHAR,
            gender                 VARCHAR,
            race_color             VARCHAR,
            marital_status         VARCHAR,
            education              VARCHAR,
            election_year          INTEGER NOT NULL,
            election_date          DATE NOT NULL,
            PRIMARY KEY (sq_candidato, round)
        )
    """,
    "candidate_social_links": """
        CREATE TABLE candidate_social_links (
            sq_candidato BIGINT NOT NULL,
            position     INTEGER NOT NULL,
            url          VARCHAR NOT NULL,
            PRIMARY KEY (sq_candidato, position)
        )
    """,
}
"""DDL of every table in ``index.duckdb``, keyed by table name."""

DatasetKey = Literal[
    "polling_places",
    "municipalities",
    "candidates",
    "candidates_complementary",
    "candidate_social_links",
]


class DatasetSource(BaseModel):
    """Where one table of the index came from, as the answer's ``source`` cites it."""

    model_config = ConfigDict(frozen=True)

    dataset: str
    dataset_url: str
    file: str
    generated_at: dt.datetime = Field(description="DT_GERACAO + HH_GERACAO in America/Sao_Paulo")


class Manifest(BaseModel):
    """The ``manifest.json`` written next to ``index.duckdb``.

    ``election_year`` and ``election_dates`` (keyed by round number) are the
    "election of the index" of codebase-design 3.4: filled only when every
    election-bearing dataset is an election file of the same year, null when
    any of them is the monthly ``ATUAL`` file.
    """

    model_config = ConfigDict(frozen=True)

    schema_version: int = SCHEMA_VERSION
    index_built_at: dt.datetime
    datasets: dict[DatasetKey, DatasetSource]
    election_year: int | None
    election_dates: dict[int, dt.date] | None
    counts: dict[str, int]
    index_sha256: str


def write_manifest(manifest: Manifest, path: Path) -> None:
    path.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")


def read_manifest(path: Path) -> Manifest:
    return Manifest.model_validate_json(path.read_text(encoding="utf-8"))


def manifest_version(raw: bytes) -> str:
    """The version identifier of an index: the SHA-256 of its manifest bytes."""
    return hashlib.sha256(raw).hexdigest()
