"""The "where do I vote" lookup: one section in one round, with its place and municipality.

The place is the one of the section the voter votes at: the section itself, or its main
section when it is aggregated. The TSE registers some aggregated sections at a place with
no main section, hence no ballot box (1,807 of 17,931 in the 2026 file), so the aggregated
row's own place is not where its voters go.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import duckdb


@dataclass(frozen=True, slots=True)
class SectionRow:
    uf: str
    zone: int
    section: int
    round: int
    section_kind: str
    main_section: int | None
    voters: int
    accessibility: str
    election_date: dt.date | None
    previous_place_number: int | None
    previous_place_name: str | None
    previous_place_address: str | None
    municipality_tse_code: str
    municipality_ibge_code: int | None
    municipality_name: str
    place_number: int
    place_name: str
    place_kind: str
    place_address: str
    place_neighborhood: str
    place_postal_code: str
    place_phone: str | None
    place_latitude: float | None
    place_longitude: float | None
    place_status: str
    place_section_count: int
    place_accessible_section_count: int
    votes_elsewhere: bool
    """True when the voting place is not the place the aggregated section is registered at."""


_SQL = """
    SELECT
        s.uf, s.zone, s.section, s.round, s.section_kind, s.main_section, s.voters,
        s.accessibility, s.election_date,
        s.previous_place_number, s.previous_place_name, s.previous_place_address,
        m.tse_code, m.ibge_code, m.name,
        p.number, p.name, p.kind, p.address, p.neighborhood, p.postal_code, p.phone,
        p.latitude, p.longitude, p.status, p.section_count, p.accessible_section_count,
        v.municipality_tse_code <> s.municipality_tse_code OR v.place_number <> s.place_number
    FROM polling_sections AS s
    JOIN polling_sections AS v
      ON v.uf = s.uf AND v.zone = s.zone AND v.round = s.round
      AND v.section = coalesce(s.main_section, s.section)
    JOIN polling_places AS p
      ON p.uf = v.uf AND p.zone = v.zone AND p.municipality_tse_code = v.municipality_tse_code
      AND p.number = v.place_number AND p.round = v.round
    JOIN municipalities AS m ON m.tse_code = v.municipality_tse_code
    WHERE s.uf = ? AND s.zone = ? AND s.section = ? AND s.round = ?
"""


def find_section(
    cursor: duckdb.DuckDBPyConnection, uf: str, zone: int, section: int, round: int
) -> SectionRow | None:
    row = cursor.execute(_SQL, [uf, zone, section, round]).fetchone()
    return SectionRow(*row) if row is not None else None
