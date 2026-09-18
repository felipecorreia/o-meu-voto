"""Loader and schema validation for data/elections.yaml.

The YAML is curated by hand once per election; this module is the only way
into the Election entity from the file, so the schema is enforced here and
tested in tests/test_elections_yaml.py.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from br_elections_mcp.domain import (
    CalendarSource,
    Election,
    ElectionKind,
    ElectionRound,
    Office,
    VotingHours,
)

SCHEMA_VERSION = 1

_ELECTION_KEYS = frozenset(
    {"id", "name", "year", "kind", "rounds", "voting_hours", "offices", "calendar_source", "notes"}
)
_ROUND_KEYS = frozenset({"number", "date", "note"})
_HOURS_KEYS = frozenset({"start", "end", "timezone"})
_SOURCE_KEYS = frozenset({"title", "url", "verified_at"})


class ElectionsSchemaError(ValueError):
    """The elections file does not follow the expected schema."""


def load_elections(path: Path) -> tuple[Election, ...]:
    """Read and validate the elections file at `path`."""
    with path.open(encoding="utf-8") as fh:
        document = yaml.safe_load(fh)
    return parse_elections(document)


def parse_elections(document: Any) -> tuple[Election, ...]:
    """Validate an already-parsed YAML document and build the elections."""
    root = _mapping(document, "document")
    _only_keys(root, {"schema_version", "elections"}, "document")
    if root.get("schema_version") != SCHEMA_VERSION:
        raise ElectionsSchemaError(
            f"schema_version must be {SCHEMA_VERSION}, got {root.get('schema_version')!r}"
        )
    raw_elections = root.get("elections")
    if not isinstance(raw_elections, list) or not raw_elections:
        raise ElectionsSchemaError("elections must be a non-empty list")
    elections = tuple(_election(item, index) for index, item in enumerate(raw_elections))
    ids = [e.id for e in elections]
    if len(set(ids)) != len(ids):
        raise ElectionsSchemaError(f"election ids must be unique: {ids}")
    years = [e.year for e in elections]
    if len(set(years)) != len(years):
        raise ElectionsSchemaError(f"at most one election per year: {years}")
    return elections


def _election(raw: Any, index: int) -> Election:
    where = f"elections[{index}]"
    data = _mapping(raw, where)
    _only_keys(data, _ELECTION_KEYS, where)
    try:
        return Election(
            id=_str(data, "id", where),
            name=_str(data, "name", where),
            year=_int(data, "year", where),
            kind=_enum(ElectionKind, _str(data, "kind", where), f"{where}.kind"),
            rounds=tuple(
                _round(item, f"{where}.rounds[{i}]")
                for i, item in enumerate(_list(data, "rounds", where))
            ),
            voting_hours=_hours(data.get("voting_hours"), f"{where}.voting_hours"),
            offices=tuple(
                _enum(Office, item, f"{where}.offices[{i}]")
                for i, item in enumerate(_list(data, "offices", where))
            ),
            calendar_source=_source(data.get("calendar_source"), f"{where}.calendar_source"),
            notes=tuple(_str_items(data.get("notes", []), f"{where}.notes")),
        )
    except ValueError as exc:
        if isinstance(exc, ElectionsSchemaError):
            raise
        raise ElectionsSchemaError(f"{where}: {exc}") from exc


def _round(raw: Any, where: str) -> ElectionRound:
    data = _mapping(raw, where)
    _only_keys(data, _ROUND_KEYS, where)
    note = data.get("note")
    if note is not None and not isinstance(note, str):
        raise ElectionsSchemaError(f"{where}.note must be a string")
    return ElectionRound(
        number=_int(data, "number", where), date=_date(data, "date", where), note=note
    )


def _hours(raw: Any, where: str) -> VotingHours:
    data = _mapping(raw, where)
    _only_keys(data, _HOURS_KEYS, where)
    return VotingHours(
        start=_time(data, "start", where),
        end=_time(data, "end", where),
        timezone=_str(data, "timezone", where),
    )


def _source(raw: Any, where: str) -> CalendarSource:
    data = _mapping(raw, where)
    _only_keys(data, _SOURCE_KEYS, where)
    return CalendarSource(
        title=_str(data, "title", where),
        url=_str(data, "url", where),
        verified_at=_date(data, "verified_at", where),
    )


def _mapping(raw: Any, where: str) -> Mapping[str, Any]:
    if not isinstance(raw, Mapping):
        raise ElectionsSchemaError(f"{where} must be a mapping")
    return raw


def _only_keys(data: Mapping[str, Any], allowed: frozenset[str] | set[str], where: str) -> None:
    unknown = set(data) - allowed
    if unknown:
        raise ElectionsSchemaError(f"{where} has unknown keys: {sorted(unknown)}")


def _list(data: Mapping[str, Any], key: str, where: str) -> list[Any]:
    value = data.get(key)
    if not isinstance(value, list) or not value:
        raise ElectionsSchemaError(f"{where}.{key} must be a non-empty list")
    return value


def _str(data: Mapping[str, Any], key: str, where: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ElectionsSchemaError(f"{where}.{key} must be a non-empty string")
    return value


def _str_items(raw: Any, where: str) -> list[str]:
    if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
        raise ElectionsSchemaError(f"{where} must be a list of strings")
    return raw


def _int(data: Mapping[str, Any], key: str, where: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ElectionsSchemaError(f"{where}.{key} must be an integer")
    return value


def _date(data: Mapping[str, Any], key: str, where: str) -> dt.date:
    value = data.get(key)
    if not isinstance(value, dt.date) or isinstance(value, dt.datetime):
        raise ElectionsSchemaError(f"{where}.{key} must be a date (YYYY-MM-DD)")
    return value


def _time(data: Mapping[str, Any], key: str, where: str) -> dt.time:
    value = data.get(key)
    if not isinstance(value, str):
        raise ElectionsSchemaError(f"{where}.{key} must be a time string (HH:MM)")
    try:
        return dt.time.fromisoformat(value)
    except ValueError as exc:
        raise ElectionsSchemaError(f"{where}.{key} must be a time string (HH:MM)") from exc


def _enum[E](enum_type: type[E], value: Any, where: str) -> E:
    try:
        return enum_type(value)  # type: ignore[call-arg]
    except ValueError as exc:
        allowed = [member.value for member in enum_type]  # type: ignore[attr-defined]
        raise ElectionsSchemaError(f"{where}: {value!r} is not one of {allowed}") from exc
