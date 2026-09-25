"""``Core.health()`` (ticket #13): freshness per dataset, index version and the last
``IndexSource`` check, for an operator to alert before a voter sees the 48-hour warning.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from br_elections_mcp.core import Core, IndexSourceUnavailable, IndexUnavailable, IndexVersion
from br_elections_mcp.index_schema import MANIFEST_FILE_NAME, manifest_version
from br_elections_mcp.index_store import LocalDirectoryIndexSource
from tests.conftest import (
    BUILT_AT,
    ELECTIONS_FILE,
    NOW,
    build_fixture_index,
    fixed_clock,
    open_core,
)

SAO_PAULO = ZoneInfo("America/Sao_Paulo")
POLLING_PLACES_GENERATED_AT = dt.datetime(2026, 9, 17, 6, 30, 20, tzinfo=SAO_PAULO)


class MutableClock:
    """An injected clock a test advances by hand, matching tests/test_core_reload.py."""

    def __init__(self, now: dt.datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> dt.datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += dt.timedelta(seconds=seconds)


class FailingIndexSource:
    def current(self) -> IndexVersion:
        raise IndexSourceUnavailable("bucket is down")


class SwappableIndexSource:
    """Delegates to ``inner``, which the test replaces to simulate the bucket going away."""

    def __init__(self, inner) -> None:
        self.inner = inner

    def current(self) -> IndexVersion:
        return self.inner.current()


@pytest.fixture
def index_dir(tmp_path: Path) -> Path:
    build_fixture_index(tmp_path)
    return tmp_path


def test_health_exposes_generated_at_per_dataset_index_built_at_and_version(
    core: Core, acre_index_dir: Path
):
    health = core.health()

    assert health.datasets["polling_places"].generated_at == POLLING_PLACES_GENERATED_AT
    expected_age = (NOW - POLLING_PLACES_GENERATED_AT).total_seconds() / 3600
    assert health.datasets["polling_places"].age_hours == pytest.approx(expected_age)
    assert health.datasets["polling_places"].stale is False
    assert set(health.datasets) == {
        "polling_places",
        "municipalities",
        "candidates",
        "candidates_complementary",
        "candidate_social_links",
        "candidate_assets",
    }
    assert health.index_built_at == BUILT_AT
    assert health.stale is False
    manifest_bytes = (acre_index_dir / MANIFEST_FILE_NAME).read_bytes()
    assert health.index_version == manifest_version(manifest_bytes)
    assert health.last_index_check_at is None
    assert health.last_index_check_error is None


def test_health_is_stale_when_any_dataset_crosses_the_threshold(acre_index_dir: Path):
    stale_clock = fixed_clock(POLLING_PLACES_GENERATED_AT + dt.timedelta(hours=60))
    core = open_core(acre_index_dir, clock=stale_clock)
    try:
        health = core.health()
        assert health.datasets["polling_places"].stale is True
        assert health.stale is True
    finally:
        core.close()


def test_health_before_any_open_is_index_unavailable(acre_index_dir: Path):
    core = Core(LocalDirectoryIndexSource(acre_index_dir), ELECTIONS_FILE)
    with pytest.raises(IndexUnavailable):
        core.health()
    core.close()


def test_failing_refresh_sets_last_check_error_and_keeps_previous_last_check_at(index_dir: Path):
    source = SwappableIndexSource(LocalDirectoryIndexSource(index_dir))
    clock = MutableClock()
    core = Core(source, ELECTIONS_FILE, clock=clock)
    core.open_index()
    try:
        core.refresh()
        first_success = core.health().last_index_check_at
        assert first_success == NOW
        assert core.health().last_index_check_error is None

        clock.advance(3600)
        source.inner = FailingIndexSource()
        core.refresh()

        health = core.health()
        assert health.last_index_check_at == first_success
        assert health.last_index_check_error is not None
        assert health.last_index_check_error.message == "bucket is down"
        assert health.last_index_check_error.at == NOW + dt.timedelta(seconds=3600)
        # The open version keeps being served: health() still answers over it.
        assert health.index_built_at == BUILT_AT
    finally:
        core.close()
