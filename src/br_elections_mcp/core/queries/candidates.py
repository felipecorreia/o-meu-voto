"""The candidate list: one office in one UF and round, filtered, paginated, with the total."""

from __future__ import annotations

from dataclasses import dataclass

import duckdb


@dataclass(frozen=True, slots=True)
class CandidateRow:
    sq_candidato: int
    number: int
    ballot_name: str
    name: str
    office: str
    party_number: int
    party_acronym: str
    party_name: str
    federation_acronym: str | None
    federation_name: str | None
    coalition_name: str | None
    adjudication_status: str
    on_ballot: bool
    occupation: str | None


@dataclass(frozen=True, slots=True)
class CandidateFilter:
    """The filters of ``list_candidates`` already normalized by the core.

    ``party_number`` or ``party_acronym`` (search form) is set when the voter
    filtered by party; ``name`` is the search form of the text typed.
    """

    uf: str
    office: str
    round: int
    on_ballot_only: bool
    party_number: int | None = None
    party_acronym: str | None = None
    name: str | None = None


_COLUMNS = """
    sq_candidato, number, ballot_name, name, office,
    party_number, party_acronym, party_name,
    federation_acronym, federation_name, coalition_name,
    adjudication_status, on_ballot, occupation
"""


def office_rounds(cursor: duckdb.DuckDBPyConnection, uf: str, office: str) -> tuple[int, ...]:
    """Rounds in which (``uf``, ``office``) has candidates, ascending."""
    rows = cursor.execute(
        "SELECT DISTINCT round FROM candidates WHERE uf = ? AND office = ? ORDER BY round",
        [uf, office],
    ).fetchall()
    return tuple(int(row[0]) for row in rows)


def candidate_rounds(cursor: duckdb.DuckDBPyConnection) -> tuple[int, ...]:
    """Rounds with at least one candidate of any office, ascending."""
    rows = cursor.execute("SELECT DISTINCT round FROM candidates ORDER BY round").fetchall()
    return tuple(int(row[0]) for row in rows)


def list_candidates(
    cursor: duckdb.DuckDBPyConnection, filters: CandidateFilter, limit: int, offset: int
) -> tuple[list[CandidateRow], int]:
    """The page of candidates matching ``filters``, in ballot-number order, and the total."""
    where, params = _where(filters)
    total = cursor.execute(f"SELECT count(*) FROM candidates WHERE {where}", params).fetchone()
    rows = cursor.execute(
        f"""
        SELECT {_COLUMNS} FROM candidates
        WHERE {where}
        ORDER BY number, sq_candidato
        LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    ).fetchall()
    return [CandidateRow(*row) for row in rows], int(total[0]) if total else 0


def _where(filters: CandidateFilter) -> tuple[str, list[object]]:
    clauses = ["uf = ?", "office = ?", "round = ?"]
    params: list[object] = [filters.uf, filters.office, filters.round]
    if filters.on_ballot_only:
        clauses.append("on_ballot")
    if filters.party_number is not None:
        clauses.append("party_number = ?")
        params.append(filters.party_number)
    if filters.party_acronym is not None:
        clauses.append("search_party_acronym = ?")
        params.append(filters.party_acronym)
    if filters.name is not None:
        pattern = "%" + _escape_like(filters.name) + "%"
        clauses.append(r"(search_ballot_name LIKE ? ESCAPE '\' OR search_name LIKE ? ESCAPE '\')")
        params.extend([pattern, pattern])
    return " AND ".join(clauses), params


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
