"""Candidate queries: the list of one office in one UF and round, and the individual profile."""

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


# The candidate profile (codebase-design 8.4): one candidacy in one round, its ticket and links.


@dataclass(frozen=True, slots=True)
class CandidateProfileRow(CandidateRow):
    round: int
    uf: str
    social_name: str | None
    nomination_kind: str
    federation_composition: str | None
    coalition_composition: str | None
    gender: str | None
    race_color: str | None
    marital_status: str | None
    education: str | None
    election_year: int


@dataclass(frozen=True, slots=True)
class RunningMateRow:
    sq_candidato: int
    office: str
    ballot_name: str
    name: str
    party_number: int
    party_acronym: str
    party_name: str


_PROFILE_COLUMNS = f"""
    {_COLUMNS},
    round, uf, social_name, nomination_kind,
    federation_composition, coalition_composition,
    gender, race_color, marital_status, education, election_year
"""


def candidacy_rounds(cursor: duckdb.DuckDBPyConnection, sq_candidato: int) -> tuple[int, ...]:
    """Rounds in which the candidacy ``sq_candidato`` has a row, ascending."""
    rows = cursor.execute(
        "SELECT round FROM candidates WHERE sq_candidato = ? ORDER BY round", [sq_candidato]
    ).fetchall()
    return tuple(int(row[0]) for row in rows)


def on_ballot_rounds_by_number(
    cursor: duckdb.DuckDBPyConnection, uf: str, office: str, number: int
) -> tuple[int, ...]:
    """Rounds in which an on-ballot candidacy has (``uf``, ``office``, ``number``), ascending.

    Off-ballot candidacies never count: a number held only off the ballot resolves to
    nothing (codebase-design 3.4 and 8.4).
    """
    rows = cursor.execute(
        """
        SELECT DISTINCT round FROM candidates
        WHERE uf = ? AND office = ? AND number = ? AND on_ballot
        ORDER BY round
        """,
        [uf, office, number],
    ).fetchall()
    return tuple(int(row[0]) for row in rows)


def get_candidate(
    cursor: duckdb.DuckDBPyConnection, sq_candidato: int, round: int
) -> CandidateProfileRow | None:
    row = cursor.execute(
        f"SELECT {_PROFILE_COLUMNS} FROM candidates WHERE sq_candidato = ? AND round = ?",
        [sq_candidato, round],
    ).fetchone()
    return CandidateProfileRow(*row) if row is not None else None


def get_candidate_by_number(
    cursor: duckdb.DuckDBPyConnection, uf: str, office: str, number: int, round: int
) -> CandidateProfileRow | None:
    """The on-ballot candidacy with (``uf``, ``office``, ``number``) in ``round``: at most
    one, because the number is unique among on-ballot candidates of an office."""
    row = cursor.execute(
        f"""
        SELECT {_PROFILE_COLUMNS} FROM candidates
        WHERE uf = ? AND office = ? AND number = ? AND round = ? AND on_ballot
        ORDER BY sq_candidato
        LIMIT 1
        """,
        [uf, office, number, round],
    ).fetchone()
    return CandidateProfileRow(*row) if row is not None else None


def running_mates(
    cursor: duckdb.DuckDBPyConnection,
    profile: CandidateProfileRow,
    ticket_offices: tuple[str, ...],
) -> list[RunningMateRow]:
    """The other candidacies of the same ticket, head first, then in office order.

    The ticket is the candidacies of ``ticket_offices`` (the head office and the
    offices whose ``ticket_head`` it is) with the same round, UF and number, and
    the same ballot status as ``profile``: an on-ballot head lists its on-ballot
    vice or substitutes, never the mates of an off-ballot candidacy that held the
    number before it (domain-model 3.5).
    """
    if not ticket_offices:
        return []
    placeholders = ", ".join("?" for _ in ticket_offices)
    order = " ".join(f"WHEN ? THEN {position}" for position in range(len(ticket_offices)))
    rows = cursor.execute(
        f"""
        SELECT sq_candidato, office, ballot_name, name, party_number, party_acronym, party_name
        FROM candidates
        WHERE round = ? AND uf = ? AND number = ? AND on_ballot = ?
          AND office IN ({placeholders}) AND sq_candidato <> ?
        ORDER BY CASE office {order} END, sq_candidato
        """,
        [
            profile.round,
            profile.uf,
            profile.number,
            profile.on_ballot,
            *ticket_offices,
            profile.sq_candidato,
            *ticket_offices,
        ],
    ).fetchall()
    return [RunningMateRow(*row) for row in rows]


def social_links(cursor: duckdb.DuckDBPyConnection, sq_candidato: int) -> list[str]:
    """The URLs declared to the TSE, in the order the dataset gives them."""
    rows = cursor.execute(
        "SELECT url FROM candidate_social_links WHERE sq_candidato = ? ORDER BY position",
        [sq_candidato],
    ).fetchall()
    return [str(row[0]) for row in rows]
