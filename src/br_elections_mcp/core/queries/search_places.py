"""The polling places of one municipality in one round, filtered and optionally by distance."""

from __future__ import annotations

from dataclasses import dataclass

import duckdb

EARTH_RADIUS_KM = 6371.0


@dataclass(frozen=True, slots=True)
class PlaceRow:
    number: int
    zone: int
    name: str
    kind: str
    address: str
    neighborhood: str
    postal_code: str
    phone: str | None
    latitude: float | None
    longitude: float | None
    status: str
    section_count: int
    accessible_section_count: int
    voters: int
    distance_km: float | None


# The same normalization the build applied to ``search_name``, for the free-text filters.
_NORMALIZED_PARAM = "upper(strip_accents(?))"

# Great-circle distance (haversine) in km; NULL when the place has no coordinates.
_DISTANCE_SQL = f"""
    CASE WHEN latitude IS NULL THEN NULL ELSE
        2 * {EARTH_RADIUS_KM} * asin(sqrt(
            pow(sin(radians(latitude - ?) / 2), 2)
            + cos(radians(?)) * cos(radians(latitude)) * pow(sin(radians(longitude - ?) / 2), 2)
        ))
    END
"""


def search_places(
    cursor: duckdb.DuckDBPyConnection,
    uf: str,
    municipality_tse_code: str,
    round: int,
    *,
    neighborhood: str | None,
    query: str | None,
    near: tuple[float, float] | None,
    limit: int,
) -> tuple[list[PlaceRow], int]:
    """The places that match, in order, up to ``limit``, and the total before the limit.

    With ``near`` (latitude, longitude) the order is by distance, places without
    coordinates last; without it, by name and number.
    """
    filters = ["uf = ?", "municipality_tse_code = ?", "round = ?"]
    params: list[object] = [uf, municipality_tse_code, round]
    if neighborhood is not None:
        filters.append(f"contains(upper(strip_accents(neighborhood)), {_NORMALIZED_PARAM})")
        params.append(neighborhood)
    if query is not None:
        filters.append(
            f"(contains(upper(strip_accents(name)), {_NORMALIZED_PARAM})"
            f" OR contains(upper(strip_accents(address)), {_NORMALIZED_PARAM}))"
        )
        params.extend([query, query])
    where = " AND ".join(filters)

    if near is None:
        distance, order, distance_params = "NULL", "name, number", []
    else:
        latitude, longitude = near
        distance = _DISTANCE_SQL
        order = "distance_km ASC NULLS LAST, name, number"
        distance_params = [latitude, latitude, longitude]

    total = cursor.execute(f"SELECT count(*) FROM polling_places WHERE {where}", params).fetchone()
    assert total is not None
    rows = cursor.execute(
        f"""
        SELECT number, zone, name, kind, address, neighborhood, postal_code, phone,
               latitude, longitude, status, section_count, accessible_section_count, voters,
               {distance} AS distance_km
        FROM polling_places
        WHERE {where}
        ORDER BY {order}
        LIMIT ?
        """,
        [*distance_params, *params, limit],
    ).fetchall()
    return [PlaceRow(*row) for row in rows], int(total[0])
