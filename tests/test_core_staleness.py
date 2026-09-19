"""Stale data (ticket #13, domain-model scenario 11): ``source.age_hours``, ``source.stale``
and the 48-hour warning, over the Acre fixture index with the injected clock.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from br_elections_mcp.core import STALE_AFTER_HOURS, Core
from tests.conftest import NOW, fixed_clock, open_core

SAO_PAULO = ZoneInfo("America/Sao_Paulo")

POLLING_PLACES_GENERATED_AT = dt.datetime(2026, 9, 17, 6, 30, 20, tzinfo=SAO_PAULO)
CANDIDATES_GENERATED_AT = dt.datetime(2026, 9, 18, 22, 30, 5, tzinfo=SAO_PAULO)
MUNICIPALITIES_GENERATED_AT = dt.datetime(2026, 9, 18, 3, 12, 47, tzinfo=SAO_PAULO)

STALE_AFTER = dt.timedelta(hours=60)

POLLING_PLACES_STALE_WARNING = (
    "Os dados do TSE usados nesta resposta foram gerados em 17/09/2026 às 06:30 (há 60 horas). "
    "Confira no e-Título se algo mudou."
)
CANDIDATES_STALE_WARNING = (
    "Os dados do TSE usados nesta resposta foram gerados em 18/09/2026 às 22:30 (há 60 horas). "
    "Confira no e-Título se algo mudou."
)
MUNICIPALITIES_STALE_WARNING = (
    "Os dados do TSE usados nesta resposta foram gerados em 18/09/2026 às 03:12 (há 60 horas). "
    "Confira no e-Título se algo mudou."
)


def stale_core(acre_index_dir: Path, generated_at: dt.datetime) -> Core:
    return open_core(acre_index_dir, clock=fixed_clock(generated_at + STALE_AFTER))


def test_stale_after_hours_constant_is_48() -> None:
    assert STALE_AFTER_HOURS == 48


def test_under_the_threshold_is_not_stale(core: Core):
    answer = core.find_polling_place("AC", 9, 422)

    expected_age = (NOW - POLLING_PLACES_GENERATED_AT).total_seconds() / 3600
    assert answer.source.age_hours == pytest.approx(expected_age)
    assert answer.source.stale is False
    assert answer.warnings == []


def test_find_polling_place_is_stale_60_hours_after_generated_at(acre_index_dir: Path):
    core = stale_core(acre_index_dir, POLLING_PLACES_GENERATED_AT)
    try:
        answer = core.find_polling_place("AC", 9, 422)
        assert answer.data is not None
        assert answer.source.age_hours == pytest.approx(60.0)
        assert answer.source.stale is True
        assert answer.warnings == [POLLING_PLACES_STALE_WARNING]
    finally:
        core.close()


def test_find_polling_place_not_found_still_carries_the_stale_warning(acre_index_dir: Path):
    core = stale_core(acre_index_dir, POLLING_PLACES_GENERATED_AT)
    try:
        answer = core.find_polling_place("AC", 1, 99999)
        assert answer.data is None
        assert answer.not_found is not None
        assert answer.source.stale is True
        assert answer.warnings == [POLLING_PLACES_STALE_WARNING]
    finally:
        core.close()


def test_search_polling_places_is_stale_60_hours_after_generated_at(acre_index_dir: Path):
    core = stale_core(acre_index_dir, POLLING_PLACES_GENERATED_AT)
    try:
        answer = core.search_polling_places("AC", "Rio Branco", neighborhood="centro")
        assert answer.data is not None
        assert answer.source.age_hours == pytest.approx(60.0)
        assert answer.source.stale is True
        assert answer.warnings == [POLLING_PLACES_STALE_WARNING]
    finally:
        core.close()


def test_list_candidates_is_stale_60_hours_after_generated_at(acre_index_dir: Path):
    core = stale_core(acre_index_dir, CANDIDATES_GENERATED_AT)
    try:
        answer = core.list_candidates("br", "presidente")
        assert answer.data is not None
        assert answer.source.age_hours == pytest.approx(60.0)
        assert answer.source.stale is True
        assert answer.warnings == [CANDIDATES_STALE_WARNING]
    finally:
        core.close()


def test_resolve_municipality_is_stale_60_hours_after_generated_at(acre_index_dir: Path):
    core = stale_core(acre_index_dir, MUNICIPALITIES_GENERATED_AT)
    try:
        answer = core.resolve_municipality("Rio Branco")
        assert answer.data is not None
        assert answer.source.age_hours == pytest.approx(60.0)
        assert answer.source.stale is True
        assert answer.warnings == [MUNICIPALITIES_STALE_WARNING]
    finally:
        core.close()


def test_resolve_municipality_not_found_still_carries_the_stale_warning(acre_index_dir: Path):
    core = stale_core(acre_index_dir, MUNICIPALITIES_GENERATED_AT)
    try:
        answer = core.resolve_municipality("Xanadu")
        assert answer.data is None
        assert answer.not_found is not None
        assert answer.source.stale is True
        assert answer.warnings == [MUNICIPALITIES_STALE_WARNING]
    finally:
        core.close()


def test_election_info_never_carries_age_hours_stale_or_warning(acre_index_dir: Path):
    core = stale_core(acre_index_dir, POLLING_PLACES_GENERATED_AT)
    try:
        answer = core.election_info(dt.date(2026, 9, 18))
        assert answer.warnings == []
        assert not hasattr(answer.source, "stale")
        assert not hasattr(answer.source, "age_hours")
    finally:
        core.close()
