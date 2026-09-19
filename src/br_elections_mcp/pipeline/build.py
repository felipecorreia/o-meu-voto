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
from collections.abc import Iterable
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

from br_elections_mcp.index_schema import (
    FORBIDDEN_COLUMNS,
    INDEX_FILE_NAME,
    MANIFEST_FILE_NAME,
    MUNICIPALITIES_CSV_COLUMNS,
    POLLING_PLACES_CSV_COLUMNS,
    TABLES,
    TSE_TIMEZONE,
    DatasetSource,
    Manifest,
    write_manifest,
)
from br_elections_mcp.pipeline.datasets import SourceFile

# The TSE distributes every CSV with ';' as separator, every field quoted and ISO-8859-1.
_CSV_OPTIONS = "delim=';', header=true, quote='\"', encoding='latin-1', all_varchar=true"

# Values the TSE uses for "no value" in otherwise textual or numeric fields.
_NULL_MARKERS = ("", "-1", "#NULO", "#NULO#", "#NE")


class BuildError(ValueError):
    """The input files cannot be turned into an index; nothing was written."""


def build_index(
    polling_places: SourceFile,
    municipalities: SourceFile,
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

    conn = duckdb.connect(str(tmp_path))
    try:
        _load_source(conn, "raw_polling_places", polling_places.path, POLLING_PLACES_CSV_COLUMNS)
        _load_source(conn, "raw_municipalities", municipalities.path, MUNICIPALITIES_CSV_COLUMNS)
        _check_domain_values(conn)
        for ddl in TABLES.values():
            conn.execute(ddl)
        conn.execute(_INSERT_MUNICIPALITIES)
        conn.execute(_INSERT_POLLING_SECTIONS)
        conn.execute(_INSERT_POLLING_PLACES)
        counts = {
            table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]  # type: ignore[index]
            for table in TABLES
        }
        election_year, election_dates = _election_of_index(conn, polling_places)
        generated = {
            "polling_places": _generated_at(conn, "raw_polling_places"),
            "municipalities": _generated_at(conn, "raw_municipalities"),
        }
        for view in ("raw_polling_places", "raw_municipalities"):
            conn.execute(f"DROP VIEW {view}")
    finally:
        conn.close()

    tmp_path.replace(index_path)
    manifest = Manifest(
        index_built_at=built_at or dt.datetime.now(dt.UTC),
        datasets={
            "polling_places": DatasetSource(
                dataset=polling_places.dataset.title,
                dataset_url=polling_places.dataset.dataset_url,
                file=polling_places.path.name,
                generated_at=generated["polling_places"],
            ),
            "municipalities": DatasetSource(
                dataset=municipalities.dataset.title,
                dataset_url=municipalities.dataset.dataset_url,
                file=municipalities.path.name,
                generated_at=generated["municipalities"],
            ),
        },
        election_year=election_year,
        election_dates=election_dates,
        counts=counts,
        index_sha256=_sha256(index_path),
    )
    write_manifest(manifest, output_dir / MANIFEST_FILE_NAME)
    return manifest


def _load_source(
    conn: duckdb.DuckDBPyConnection, view: str, path: Path, expected: Iterable[str]
) -> None:
    """Expose ``path`` as a temporary view holding only the allowed columns.

    The forbidden columns are dropped here, at the first read, so no later
    statement can even name them. A column the build needs and the file lacks
    is a hard error: the TSE renames columns between elections and the
    ingestion must fail loudly, not guess.
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


def _election_of_index(
    conn: duckdb.DuckDBPyConnection, polling_places: SourceFile
) -> tuple[int | None, dict[int, dt.date] | None]:
    """The election recorded in the manifest (codebase-design 3.4 and 5).

    Read from ``AA_ELEICAO`` and ``DT_ELEICAO`` per round when the file is an
    election file; null for the monthly ``ATUAL`` snapshot.
    """
    if not polling_places.dataset.election_file:
        return None, None
    rows = conn.execute(
        """
        SELECT DISTINCT
            CAST(AA_ELEICAO AS INTEGER),
            CAST(NR_TURNO AS INTEGER),
            CAST(strptime(DT_ELEICAO, '%d/%m/%Y') AS DATE)
        FROM raw_polling_places
        ORDER BY 1, 2
        """
    ).fetchall()
    years = {row[0] for row in rows}
    if len(years) != 1:
        raise BuildError(f"an election file must carry exactly one AA_ELEICAO, got {sorted(years)}")
    dates: dict[int, dt.date] = {}
    for _, round_number, date in rows:
        if dates.setdefault(round_number, date) != date:
            raise BuildError(f"round {round_number} has more than one DT_ELEICAO")
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
    return str(path).replace("'", "''")


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
