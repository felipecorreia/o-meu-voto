"""Pipeline stage ``build``: TSE CSV files in, ``index.duckdb`` + ``manifest.json`` out.

The stage reads the CSVs with DuckDB, discards the forbidden columns before
anything is written (ADR 0004), derives the fields the domain model marks as
derived and writes the tables of ``index_schema.TABLES``. It never opens a
server and never touches the network; the same function builds the fixture
indexes the tests run on (codebase-design 5).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import unicodedata
from collections.abc import Iterable, Mapping
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

from br_elections_mcp.domain import Office
from br_elections_mcp.index_schema import (
    CANDIDATE_SOCIAL_LINKS_CSV_COLUMNS,
    CANDIDATES_COMPLEMENTARY_CSV_COLUMNS,
    CANDIDATES_CSV_COLUMNS,
    CSV_READ_OPTIONS,
    FORBIDDEN_COLUMNS,
    INDEX_FILE_NAME,
    MANIFEST_FILE_NAME,
    MUNICIPALITIES_CSV_COLUMNS,
    POLLING_PLACES_CSV_COLUMNS,
    TABLES,
    TSE_TIMEZONE,
    DatasetKey,
    DatasetSource,
    Manifest,
    write_manifest,
)
from br_elections_mcp.pipeline.datasets import SourceFile

_CSV_OPTIONS = CSV_READ_OPTIONS

# Values the TSE uses for "no value" in otherwise textual or numeric fields.
_NULL_MARKERS = ("", "-1", "#NULO", "#NULO#", "#NE")


class BuildError(ValueError):
    """The input files cannot be turned into an index; nothing was written."""


OFFICE_BY_DS_CARGO: dict[str, Office] = {
    "PRESIDENTE": Office.PRESIDENTE,
    "VICE-PRESIDENTE": Office.VICE_PRESIDENTE,
    "GOVERNADOR": Office.GOVERNADOR,
    "VICE-GOVERNADOR": Office.VICE_GOVERNADOR,
    "SENADOR": Office.SENADOR,
    "1O SUPLENTE": Office.PRIMEIRO_SUPLENTE,
    "2O SUPLENTE": Office.SEGUNDO_SUPLENTE,
    "PRIMEIRO SUPLENTE": Office.PRIMEIRO_SUPLENTE,
    "SEGUNDO SUPLENTE": Office.SEGUNDO_SUPLENTE,
    "DEPUTADO FEDERAL": Office.DEPUTADO_FEDERAL,
    "DEPUTADO ESTADUAL": Office.DEPUTADO_ESTADUAL,
    "DEPUTADO DISTRITAL": Office.DEPUTADO_DISTRITAL,
}
"""``DS_CARGO`` texts, normalized by ``office_key``, mapped to the domain enum.

The scout verified only ``"DEPUTADO FEDERAL"`` verbatim (docs/domain-model.md, 3.5);
the build fails loudly on a text outside this table, so the first real
ingestion fixes the remaining spellings here.
"""


def office_key(text: str) -> str:
    """The lookup key of a ``DS_CARGO`` text: accents stripped (``º`` becomes ``O``),
    upper case, single spaces."""
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_only = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(ascii_only.upper().split())


def build_index(
    polling_places: SourceFile,
    municipalities: SourceFile,
    candidates: SourceFile,
    candidates_complementary: SourceFile,
    social_links: SourceFile,
    output_dir: Path,
    *,
    built_at: dt.datetime | None = None,
) -> Manifest:
    """Build ``index.duckdb`` and ``manifest.json`` under ``output_dir``.

    The index file is written under a temporary name and renamed at the end,
    so a reader never sees a half-written file. Returns the manifest written.
    Raises ``BuildError`` when a required column is missing or a domain value
    cannot be mapped; nothing is guessed.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    index_path = output_dir / INDEX_FILE_NAME
    tmp_path = output_dir / f"{INDEX_FILE_NAME}.tmp"
    tmp_path.unlink(missing_ok=True)

    sources: dict[DatasetKey, SourceFile] = {
        "polling_places": polling_places,
        "municipalities": municipalities,
        "candidates": candidates,
        "candidates_complementary": candidates_complementary,
        "candidate_social_links": social_links,
    }
    expected_columns: dict[DatasetKey, tuple[str, ...]] = {
        "polling_places": POLLING_PLACES_CSV_COLUMNS,
        "municipalities": MUNICIPALITIES_CSV_COLUMNS,
        "candidates": CANDIDATES_CSV_COLUMNS,
        "candidates_complementary": CANDIDATES_COMPLEMENTARY_CSV_COLUMNS,
        "candidate_social_links": CANDIDATE_SOCIAL_LINKS_CSV_COLUMNS,
    }
    conn = duckdb.connect(str(tmp_path))
    try:
        headers = {
            key: _load_source(conn, f"raw_{key}", source.path, expected_columns[key])
            for key, source in sources.items()
        }
        _check_domain_values(conn)
        office_sql = _office_case_sql(conn)
        _check_candidate_values(conn)
        complementary_has_round = "NR_TURNO" in headers["candidates_complementary"]
        _prepare_complementary(conn, with_round=complementary_has_round)
        for ddl in TABLES.values():
            conn.execute(ddl)
        conn.execute(_INSERT_MUNICIPALITIES)
        conn.execute(_INSERT_POLLING_SECTIONS)
        conn.execute(_INSERT_POLLING_PLACES)
        conn.execute(_insert_candidates_sql(office_sql, with_round=complementary_has_round))
        _check_tickets(conn)
        conn.execute(_INSERT_SOCIAL_LINKS)
        counts = {
            table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]  # type: ignore[index]
            for table in TABLES
        }
        election_year, election_dates = _election_of_index(
            conn, {"polling_places": polling_places, "candidates": candidates}
        )
        generated = {key: _generated_at(conn, f"raw_{key}") for key in sources}
        conn.execute("DROP VIEW complementary")
        for key in sources:
            conn.execute(f"DROP VIEW raw_{key}")
    except duckdb.Error as exc:
        conn.close()
        tmp_path.unlink(missing_ok=True)
        raise BuildError(f"the input files cannot be loaded: {exc}") from exc
    except BuildError:
        conn.close()
        tmp_path.unlink(missing_ok=True)
        raise
    else:
        conn.close()

    tmp_path.replace(index_path)
    manifest = Manifest(
        index_built_at=built_at or dt.datetime.now(dt.UTC),
        datasets={
            key: DatasetSource(
                dataset=source.dataset.title,
                dataset_url=source.dataset.dataset_url,
                file=source.path.name,
                generated_at=generated[key],
            )
            for key, source in sources.items()
        },
        election_year=election_year,
        election_dates=election_dates,
        counts=counts,
        index_sha256=_sha256(index_path),
    )
    write_manifest(manifest, output_dir / MANIFEST_FILE_NAME)
    return manifest


def apply_photo_urls(index_dir: Path, photo_urls: Mapping[int, str]) -> None:
    """Set ``photo_url`` on an already-built index for the candidacies of ``photo_urls``.

    Called by the ``mirror_photos`` stage after it has synced the JPEGs to R2, with one
    URL per ``sq_candidato`` currently mirrored. A photo has no round (docs/domain-model.md,
    3.5): every round of a mirrored ``sq_candidato`` gets the same URL. Everything else keeps
    the ``NULL`` that ``build_index`` wrote.
    """
    conn = duckdb.connect(str(index_dir / INDEX_FILE_NAME))
    try:
        conn.executemany(
            "UPDATE candidates SET photo_url = ? WHERE sq_candidato = ?",
            [(url, sq_candidato) for sq_candidato, url in photo_urls.items()],
        )
    finally:
        conn.close()


def _load_source(
    conn: duckdb.DuckDBPyConnection, view: str, path: Path, expected: Iterable[str]
) -> list[str]:
    """Expose ``path`` as a temporary view holding only the allowed columns.

    The forbidden columns are dropped here, at the first read, so no later
    statement can even name them. A column the build needs and the file lacks
    is a hard error: the TSE renames columns between elections and the
    ingestion must fail loudly, not guess. Returns the columns the view kept.
    """
    if not path.is_file():
        raise BuildError(f"input file not found: {path}")
    source = f"read_csv('{_sql_string(path)}', {_CSV_OPTIONS})"
    header = [column[0] for column in conn.execute(f"SELECT * FROM {source} LIMIT 0").description]
    missing = [column for column in expected if column not in header]
    if missing:
        raise BuildError(f"{path.name} lacks expected columns: {missing}")
    kept = [column for column in header if column not in FORBIDDEN_COLUMNS]
    projection = ", ".join(f'"{column}"' for column in kept)
    conn.execute(f"CREATE TEMP VIEW {view} AS SELECT {projection} FROM {source}")
    return kept


def _check_domain_values(conn: duckdb.DuckDBPyConnection) -> None:
    """Fail loudly on any value the domain mapping does not know."""
    unknown_accessibility = [
        row[0]
        for row in conn.execute(
            f"""
            SELECT DISTINCT DS_SITU_SECAO_ACESSIBILIDADE FROM raw_polling_places
            WHERE {_ACCESSIBILITY_SQL} IS NULL
            """
        ).fetchall()
    ]
    if unknown_accessibility:
        raise BuildError(f"unknown DS_SITU_SECAO_ACESSIBILIDADE values: {unknown_accessibility}")
    unknown_status = [
        row[0]
        for row in conn.execute(
            f"""
            SELECT DISTINCT DS_SITU_LOCAL_VOTACAO FROM raw_polling_places
            WHERE {_PLACE_STATUS_SQL} NOT IN ('ativo', 'bloqueado')
            """
        ).fetchall()
    ]
    if unknown_status:
        raise BuildError(f"unknown DS_SITU_LOCAL_VOTACAO values: {unknown_status}")


def _office_case_sql(conn: duckdb.DuckDBPyConnection) -> str:
    """The ``CASE`` mapping every ``DS_CARGO`` text of the file to the ``Office`` value.

    Built from the distinct texts actually present, so an unknown one fails
    here, before any table is written.
    """
    texts = [
        row[0] for row in conn.execute("SELECT DISTINCT DS_CARGO FROM raw_candidates").fetchall()
    ]
    unknown = [text for text in texts if office_key(text or "") not in OFFICE_BY_DS_CARGO]
    if unknown:
        raise BuildError(f"unknown DS_CARGO values: {unknown}")
    branches = " ".join(
        f"WHEN '{_sql_literal(text)}' THEN '{OFFICE_BY_DS_CARGO[office_key(text)].value}'"
        for text in texts
    )
    return f"CASE DS_CARGO {branches} END"


def _check_candidate_values(conn: duckdb.DuckDBPyConnection) -> None:
    """Fail loudly on any candidate value the domain mapping does not know."""
    unknown_nomination = [
        row[0]
        for row in conn.execute(
            f"""
            SELECT DISTINCT TP_AGREMIACAO FROM raw_candidates
            WHERE {_NOMINATION_KIND_SQL} IS NULL
            """
        ).fetchall()
    ]
    if unknown_nomination:
        raise BuildError(f"unknown TP_AGREMIACAO values: {unknown_nomination}")
    unknown_on_ballot = [
        row[0]
        for row in conn.execute(
            f"""
            SELECT DISTINCT ST_CANDIDATO_INSERIDO_URNA FROM raw_candidates_complementary
            WHERE {_ON_BALLOT_SQL} IS NULL
            """
        ).fetchall()
    ]
    if unknown_on_ballot:
        raise BuildError(f"unknown ST_CANDIDATO_INSERIDO_URNA values: {unknown_on_ballot}")
    nameless_federations = [
        row[0]
        for row in conn.execute(
            f"""
            SELECT DISTINCT SG_FEDERACAO FROM raw_candidates
            WHERE {_nullif_markers("SG_FEDERACAO")} IS NOT NULL
              AND {_nullif_markers("NM_FEDERACAO")} IS NULL
            """
        ).fetchall()
    ]
    if nameless_federations:
        raise BuildError(f"SG_FEDERACAO without NM_FEDERACAO: {nameless_federations}")


def _check_tickets(conn: duckdb.DuckDBPyConnection) -> None:
    """Every on-ballot ticket has exactly one head (docs/domain-model.md, 3.5 and 7).

    A ticket is the on-ballot candidacies with the same round, UF and number
    whose offices share a ``ticket_head``; ``get_candidate`` derives the running
    mates from it, so two heads with one number or a vice without a head fail
    the build instead of producing a wrong profile.
    """
    head_sql = " ".join(
        f"WHEN '{office.value}' THEN '{office.ticket_head.value}'" for office in Office
    )
    broken = conn.execute(
        f"""
        SELECT round, uf, head_office, number, count(*) FILTER (WHERE office = head_office)
        FROM (
            SELECT round, uf, number, office, CASE office {head_sql} END AS head_office
            FROM candidates
            WHERE on_ballot
        )
        GROUP BY round, uf, number, head_office
        HAVING count(*) FILTER (WHERE office = head_office) <> 1
        ORDER BY round, uf, head_office, number
        """
    ).fetchall()
    if broken:
        described = [f"round {row[0]} {row[1]} {row[2]} {row[3]}: {row[4]} heads" for row in broken]
        raise BuildError(f"on-ballot tickets without exactly one head: {described}")


def _prepare_complementary(conn: duckdb.DuckDBPyConnection, *, with_round: bool) -> None:
    """Expose the complementary file as the view ``complementary``, one row per candidate.

    With ``NR_TURNO`` the key is (``sq_candidato``, ``round``); without it the
    file is deduplicated by ``sq_candidato`` and two rows that still differ are
    a hard error, as is a candidate of the main file without a row here
    (docs/domain-model.md, 3.5 and 7).
    """
    round_column = ", CAST(NR_TURNO AS INTEGER) AS round" if with_round else ""
    conn.execute(
        f"""
        CREATE TEMP VIEW complementary AS
        SELECT DISTINCT
            CAST(SQ_CANDIDATO AS BIGINT) AS sq_candidato{round_column},
            trim(DS_SITUACAO_JULGAMENTO) AS adjudication_status,
            {_ON_BALLOT_SQL} AS on_ballot
        FROM raw_candidates_complementary
        """
    )
    key = "sq_candidato, round" if with_round else "sq_candidato"
    conflicting = [
        row[0]
        for row in conn.execute(
            f"SELECT {key} FROM complementary GROUP BY {key} HAVING count(*) > 1 ORDER BY 1"
        ).fetchall()
    ]
    if conflicting:
        raise BuildError(
            f"the complementary file has conflicting rows for the same SQ_CANDIDATO: {conflicting}"
        )
    missing = [
        row[0]
        for row in conn.execute(
            f"""
            SELECT DISTINCT CAST(c.SQ_CANDIDATO AS BIGINT)
            FROM raw_candidates AS c
            LEFT JOIN complementary AS x ON {_complementary_join(with_round)}
            WHERE x.sq_candidato IS NULL
            ORDER BY 1
            """
        ).fetchall()
    ]
    if missing:
        raise BuildError(f"candidates without a row in the complementary file: {missing}")


def _complementary_join(with_round: bool) -> str:
    condition = "x.sq_candidato = CAST(c.SQ_CANDIDATO AS BIGINT)"
    if with_round:
        condition += " AND x.round = CAST(c.NR_TURNO AS INTEGER)"
    return condition


def _election_of_index(
    conn: duckdb.DuckDBPyConnection, sources: dict[str, SourceFile]
) -> tuple[int | None, dict[int, dt.date] | None]:
    """The election recorded in the manifest (codebase-design 3.4 and 5).

    Read from the election year and ``DT_ELEICAO`` per round of every
    election-bearing file. Null when any of them is the monthly ``ATUAL``
    snapshot, or when the files do not agree on one election (year or the
    date of a round).
    """
    if not all(source.dataset.election_file for source in sources.values()):
        return None, None
    year: int | None = None
    dates: dict[int, dt.date] = {}
    for key in sources:
        file_year, file_dates = _election_of_file(conn, f"raw_{key}")
        if year is None:
            year = file_year
        elif file_year != year:
            return None, None
        for round_number, date in file_dates.items():
            if dates.setdefault(round_number, date) != date:
                return None, None
    return year, dates


def _election_of_file(conn: duckdb.DuckDBPyConnection, view: str) -> tuple[int, dict[int, dt.date]]:
    """Year and date per round of one election file; the polling-places file
    names the year ``AA_ELEICAO``, the candidates file ``ANO_ELEICAO``."""
    columns = {column[0] for column in conn.execute(f"SELECT * FROM {view} LIMIT 0").description}
    year_column = "AA_ELEICAO" if "AA_ELEICAO" in columns else "ANO_ELEICAO"
    rows = conn.execute(
        f"""
        SELECT DISTINCT
            CAST({year_column} AS INTEGER),
            CAST(NR_TURNO AS INTEGER),
            CAST(strptime(DT_ELEICAO, '%d/%m/%Y') AS DATE)
        FROM {view}
        ORDER BY 1, 2
        """
    ).fetchall()
    years = {row[0] for row in rows}
    if len(years) != 1:
        raise BuildError(
            f"{view}: an election file must carry exactly one election year, got {sorted(years)}"
        )
    dates: dict[int, dt.date] = {}
    for _, round_number, date in rows:
        if dates.setdefault(round_number, date) != date:
            raise BuildError(f"{view}: round {round_number} has more than one DT_ELEICAO")
    return years.pop(), dates


def _generated_at(conn: duckdb.DuckDBPyConnection, view: str) -> dt.datetime:
    """``DT_GERACAO`` + ``HH_GERACAO`` of the file, interpreted in America/Sao_Paulo."""
    row = conn.execute(
        f"""
        SELECT strptime(DT_GERACAO || ' ' || HH_GERACAO, '%d/%m/%Y %H:%M:%S')
        FROM {view} LIMIT 1
        """
    ).fetchone()
    if row is None:
        raise BuildError(f"{view}: the file has no rows")
    naive: dt.datetime = row[0]
    return naive.replace(tzinfo=ZoneInfo(TSE_TIMEZONE))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sql_string(path: Path) -> str:
    return _sql_literal(str(path))


def _sql_literal(text: str) -> str:
    return text.replace("'", "''")


def _nullif_markers(column: str) -> str:
    markers = ", ".join(f"'{marker}'" for marker in _NULL_MARKERS)
    return f"CASE WHEN trim({column}) IN ({markers}) THEN NULL ELSE trim({column}) END"


# Accessibility of a section, mapped from the TSE description to the domain enum.
_ACCESSIBILITY_SQL = """
    CASE
        WHEN upper(strip_accents(trim(DS_SITU_SECAO_ACESSIBILIDADE))) LIKE 'COM%'
            THEN 'com_acessibilidade'
        WHEN upper(strip_accents(trim(DS_SITU_SECAO_ACESSIBILIDADE))) LIKE 'SEM%'
            THEN 'sem_acessibilidade'
    END
"""

_PLACE_STATUS_SQL = "lower(strip_accents(trim(DS_SITU_LOCAL_VOTACAO)))"

# A coordinate the TSE does not have comes as -1 (docs/domain-model.md, 3.3).
_LATITUDE_SQL = "nullif(try_cast(replace(NR_LATITUDE, ',', '.') AS DOUBLE), -1)"
_LONGITUDE_SQL = "nullif(try_cast(replace(NR_LONGITUDE, ',', '.') AS DOUBLE), -1)"

_MAIN_SECTION_SQL = """
    CASE
        WHEN try_cast(NR_SECAO_PRINCIPAL AS INTEGER) IN (-1, CAST(NR_SECAO AS INTEGER)) THEN NULL
        ELSE try_cast(NR_SECAO_PRINCIPAL AS INTEGER)
    END
"""

# The previous place exists only when the original number differs from the current one.
_PREVIOUS_NUMBER_SQL = """
    CASE
        WHEN try_cast(NR_LOCAL_VOTACAO_ORIGINAL AS INTEGER) IS NULL
            OR try_cast(NR_LOCAL_VOTACAO_ORIGINAL AS INTEGER)
                IN (-1, CAST(NR_LOCAL_VOTACAO AS INTEGER))
            THEN NULL
        ELSE CAST(NR_LOCAL_VOTACAO_ORIGINAL AS INTEGER)
    END
"""

_INSERT_MUNICIPALITIES = f"""
    INSERT INTO municipalities (tse_code, ibge_code, name, uf, search_name)
    WITH crosswalk AS (
        SELECT
            lpad(trim(CD_MUNICIPIO_TSE), 5, '0') AS tse_code,
            try_cast({_nullif_markers("CD_MUNICIPIO_IBGE")} AS INTEGER) AS ibge_code,
            trim(NM_MUNICIPIO_TSE) AS name,
            upper(trim(SG_UF)) AS uf
        FROM raw_municipalities
    ),
    -- Municipalities missing from the crosswalk (abroad) keep the name the TSE prints.
    from_places AS (
        SELECT DISTINCT
            lpad(trim(CD_MUNICIPIO), 5, '0') AS tse_code,
            NULL::INTEGER AS ibge_code,
            trim(NM_MUNICIPIO) AS name,
            upper(trim(SG_UF)) AS uf
        FROM raw_polling_places
        WHERE lpad(trim(CD_MUNICIPIO), 5, '0') NOT IN (SELECT tse_code FROM crosswalk)
    ),
    merged AS (SELECT * FROM crosswalk UNION ALL SELECT * FROM from_places)
    SELECT tse_code, ibge_code, name, uf, upper(strip_accents(name)) FROM merged
"""

_INSERT_POLLING_SECTIONS = f"""
    INSERT INTO polling_sections (
        uf, zone, section, round, municipality_tse_code, place_number, section_kind,
        main_section, voters, accessibility, status, election_date,
        previous_place_number, previous_place_name, previous_place_address
    )
    WITH rows AS (
        SELECT
            upper(trim(SG_UF)) AS uf,
            CAST(NR_ZONA AS INTEGER) AS zone,
            CAST(NR_SECAO AS INTEGER) AS section,
            CAST(NR_TURNO AS INTEGER) AS round,
            lpad(trim(CD_MUNICIPIO), 5, '0') AS municipality_tse_code,
            CAST(NR_LOCAL_VOTACAO AS INTEGER) AS place_number,
            {_MAIN_SECTION_SQL} AS main_section,
            CAST(QT_ELEITOR_SECAO AS INTEGER) AS voters,
            {_ACCESSIBILITY_SQL} AS accessibility,
            trim(DS_SITU_SECAO) AS status,
            CAST(strptime(DT_ELEICAO, '%d/%m/%Y') AS DATE) AS election_date,
            {_PREVIOUS_NUMBER_SQL} AS previous_place_number,
            {_nullif_markers("NM_LOCAL_VOTACAO_ORIGINAL")} AS previous_place_name,
            {_nullif_markers("DS_ENDERECO_LOCVT_ORIGINAL")} AS previous_place_address
        FROM raw_polling_places
    )
    SELECT
        uf, zone, section, round, municipality_tse_code, place_number,
        CASE WHEN main_section IS NULL THEN 'principal' ELSE 'agregada' END,
        main_section, voters, accessibility, status, election_date,
        previous_place_number,
        CASE WHEN previous_place_number IS NULL THEN NULL ELSE previous_place_name END,
        CASE WHEN previous_place_number IS NULL THEN NULL ELSE previous_place_address END
    FROM rows
"""

_INSERT_POLLING_PLACES = f"""
    INSERT INTO polling_places (
        uf, zone, number, round, municipality_tse_code, name, kind, address, neighborhood,
        postal_code, phone, latitude, longitude, status,
        section_count, accessible_section_count, voters
    )
    SELECT
        upper(trim(SG_UF)),
        CAST(NR_ZONA AS INTEGER),
        CAST(NR_LOCAL_VOTACAO AS INTEGER),
        CAST(NR_TURNO AS INTEGER),
        lpad(trim(CD_MUNICIPIO), 5, '0'),
        any_value(trim(NM_LOCAL_VOTACAO)),
        any_value(trim(DS_TIPO_LOCAL)),
        any_value(trim(DS_ENDERECO)),
        any_value(trim(NM_BAIRRO)),
        any_value(trim(NR_CEP)),
        any_value({_nullif_markers("NR_TELEFONE_LOCAL")}),
        any_value({_LATITUDE_SQL}),
        any_value({_LONGITUDE_SQL}),
        any_value({_PLACE_STATUS_SQL}),
        count(*),
        count(*) FILTER (WHERE {_ACCESSIBILITY_SQL} = 'com_acessibilidade'),
        sum(CAST(QT_ELEITOR_SECAO AS INTEGER))
    FROM raw_polling_places
    GROUP BY 1, 2, 3, 4, 5
"""

_NOMINATION_KIND_SQL = """
    CASE upper(strip_accents(trim(TP_AGREMIACAO)))
        WHEN 'COLIGACAO' THEN 'coligacao'
        WHEN 'FEDERACAO' THEN 'federacao'
        WHEN 'PARTIDO ISOLADO' THEN 'partido_isolado'
    END
"""

# The leiame documents S/N; the domain model records SIM/NÃO. Both are accepted.
_ON_BALLOT_SQL = """
    CASE upper(strip_accents(trim(ST_CANDIDATO_INSERIDO_URNA)))
        WHEN 'S' THEN TRUE
        WHEN 'SIM' THEN TRUE
        WHEN 'N' THEN FALSE
        WHEN 'NAO' THEN FALSE
    END
"""

_SEARCH_TEXT = "upper(strip_accents(trim({column})))"

# "PARTIDO ISOLADO" in NM_COLIGACAO means no coalition (docs/domain-model.md, 3.5).
_COALITION_NAME_SQL = f"""
    CASE
        WHEN upper(strip_accents(trim(NM_COLIGACAO))) = 'PARTIDO ISOLADO' THEN NULL
        ELSE {_nullif_markers("NM_COLIGACAO")}
    END
"""


def _insert_candidates_sql(office_sql: str, *, with_round: bool) -> str:
    return f"""
        INSERT INTO candidates (
            sq_candidato, round, uf, office, number, ballot_name, name, social_name,
            search_ballot_name, search_name,
            party_number, party_acronym, party_name, search_party_acronym, nomination_kind,
            federation_acronym, federation_name, federation_composition,
            coalition_name, coalition_composition,
            adjudication_status, on_ballot, occupation,
            gender, race_color, marital_status, education,
            election_year, election_date
        )
        WITH rows AS (
            SELECT
                CAST(c.SQ_CANDIDATO AS BIGINT) AS sq_candidato,
                CAST(c.NR_TURNO AS INTEGER) AS round,
                upper(trim(c.SG_UF)) AS uf,
                {office_sql} AS office,
                CAST(c.NR_CANDIDATO AS INTEGER) AS number,
                trim(c.NM_URNA_CANDIDATO) AS ballot_name,
                trim(c.NM_CANDIDATO) AS name,
                {_nullif_markers("c.NM_SOCIAL_CANDIDATO")} AS social_name,
                {_SEARCH_TEXT.format(column="c.NM_URNA_CANDIDATO")} AS search_ballot_name,
                {_SEARCH_TEXT.format(column="c.NM_CANDIDATO")} AS search_name,
                CAST(c.NR_PARTIDO AS INTEGER) AS party_number,
                trim(c.SG_PARTIDO) AS party_acronym,
                trim(c.NM_PARTIDO) AS party_name,
                {_SEARCH_TEXT.format(column="c.SG_PARTIDO")} AS search_party_acronym,
                {_NOMINATION_KIND_SQL} AS nomination_kind,
                {_nullif_markers("c.SG_FEDERACAO")} AS federation_acronym,
                {_nullif_markers("c.NM_FEDERACAO")} AS federation_name,
                {_nullif_markers("c.DS_COMPOSICAO_FEDERACAO")} AS federation_composition,
                {_COALITION_NAME_SQL} AS coalition_name,
                {_nullif_markers("c.DS_COMPOSICAO_COLIGACAO")} AS coalition_composition,
                x.adjudication_status,
                x.on_ballot,
                {_nullif_markers("c.DS_OCUPACAO")} AS occupation,
                {_nullif_markers("c.DS_GENERO")} AS gender,
                {_nullif_markers("c.DS_COR_RACA")} AS race_color,
                {_nullif_markers("c.DS_ESTADO_CIVIL")} AS marital_status,
                {_nullif_markers("c.DS_GRAU_INSTRUCAO")} AS education,
                CAST(c.ANO_ELEICAO AS INTEGER) AS election_year,
                CAST(strptime(c.DT_ELEICAO, '%d/%m/%Y') AS DATE) AS election_date
            FROM raw_candidates AS c
            JOIN complementary AS x ON {_complementary_join(with_round)}
        )
        SELECT
            sq_candidato, round, uf, office, number, ballot_name, name, social_name,
            search_ballot_name, search_name,
            party_number, party_acronym, party_name, search_party_acronym, nomination_kind,
            federation_acronym,
            CASE WHEN federation_acronym IS NULL THEN NULL ELSE federation_name END,
            CASE WHEN federation_acronym IS NULL THEN NULL ELSE federation_composition END,
            coalition_name,
            CASE WHEN coalition_name IS NULL THEN NULL ELSE coalition_composition END,
            adjudication_status, on_ballot, occupation,
            gender, race_color, marital_status, education,
            election_year, election_date
        FROM rows
    """


_INSERT_SOCIAL_LINKS = f"""
    INSERT INTO candidate_social_links (sq_candidato, position, url)
    SELECT DISTINCT
        CAST(SQ_CANDIDATO AS BIGINT),
        CAST(NR_ORDEM_REDE_SOCIAL AS INTEGER),
        trim(DS_URL)
    FROM raw_candidate_social_links
    WHERE {_nullif_markers("DS_URL")} IS NOT NULL
      AND CAST(SQ_CANDIDATO AS BIGINT) IN (SELECT sq_candidato FROM candidates)
"""
