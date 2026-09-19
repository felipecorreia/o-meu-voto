"""Municipality lookup: by name with a score, or by TSE code."""

from __future__ import annotations

from dataclasses import dataclass

import duckdb

MIN_SCORE = 0.85
"""Below this a name is not offered as a candidate; exact and substring matches always are."""

# The same normalization the build applied to ``search_name``, applied to the voter's text.
_NORMALIZED_PARAM = "upper(strip_accents(?))"

# Exact name first, then the name that contains the text, then a similar spelling.
_SCORE_SQL = f"""
    CASE
        WHEN search_name = {_NORMALIZED_PARAM} THEN 1.0
        WHEN contains(search_name, {_NORMALIZED_PARAM}) THEN 0.9
        ELSE jaro_winkler_similarity(search_name, {_NORMALIZED_PARAM})
    END
"""


@dataclass(frozen=True, slots=True)
class MunicipalityRow:
    tse_code: str
    ibge_code: int | None
    name: str
    uf: str
    score: float


def search_municipalities(
    cursor: duckdb.DuckDBPyConnection, name: str, uf: str | None, limit: int
) -> list[MunicipalityRow]:
    """Municipalities matching ``name``, best score first, then by name; ``uf`` narrows."""
    sql = f"""
        WITH scored AS (
            SELECT tse_code, ibge_code, name, uf, {_SCORE_SQL} AS score
            FROM municipalities
            WHERE ? IS NULL OR uf = ?
        )
        SELECT tse_code, ibge_code, name, uf, score FROM scored
        WHERE score >= ?
        ORDER BY score DESC, name, uf
        LIMIT ?
    """
    rows = cursor.execute(sql, [name, name, name, uf, uf, MIN_SCORE, limit]).fetchall()
    return [MunicipalityRow(*row) for row in rows]


def get_municipality(
    cursor: duckdb.DuckDBPyConnection, tse_code: str, uf: str
) -> MunicipalityRow | None:
    row = cursor.execute(
        "SELECT tse_code, ibge_code, name, uf, 1.0 FROM municipalities "
        "WHERE tse_code = ? AND uf = ?",
        [tse_code, uf],
    ).fetchone()
    return MunicipalityRow(*row) if row is not None else None
