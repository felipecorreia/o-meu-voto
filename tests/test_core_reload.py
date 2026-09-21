"""Index reload without restart: ``refresh()``, the check task and ``start()``/``close()``."""

from __future__ import annotations

import datetime as dt
import threading
import time
from pathlib import Path

import pytest

from br_elections_mcp.core import Core, IndexSourceUnavailable, IndexUnavailable, IndexVersion
from br_elections_mcp.core import index as index_module
from br_elections_mcp.core.index import INDEX_CHECK_INTERVAL_SECONDS, IndexManager
from br_elections_mcp.index_store import LocalDirectoryIndexSource
from tests.conftest import (
    BUILT_AT,
    ELECTIONS_FILE,
    NOW,
    build_fixture_index,
    fixed_clock,
    open_core,
)

REBUILT_AT = BUILT_AT + dt.timedelta(hours=6)
WAIT_SECONDS = 5.0


class MutableClock:
    """An injected clock the test moves by hand."""

    def __init__(self, now: dt.datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> dt.datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += dt.timedelta(seconds=seconds)


class CountingIndexSource:
    """A real ``LocalDirectoryIndexSource`` that counts ``current()`` calls."""

    def __init__(self, directory: Path) -> None:
        self._inner = LocalDirectoryIndexSource(directory)
        self.calls = 0

    def current(self) -> IndexVersion:
        self.calls += 1
        return self._inner.current()


class OverlapDetectingIndexSource:
    """Slow ``current()`` that records whether two calls ever ran at the same time."""

    def __init__(self, directory: Path) -> None:
        self._inner = LocalDirectoryIndexSource(directory)
        self._lock = threading.Lock()
        self._in_flight = 0
        self.calls = 0
        self.overlapped = False

    def current(self) -> IndexVersion:
        with self._lock:
            self._in_flight += 1
            self.calls += 1
            if self._in_flight > 1:
                self.overlapped = True
        try:
            time.sleep(0.05)
            return self._inner.current()
        finally:
            with self._lock:
                self._in_flight -= 1


class FailingIndexSource:
    def current(self) -> IndexVersion:
        raise IndexSourceUnavailable("bucket is down")


class SwappableIndexSource:
    """Delegates to ``inner``, which the test replaces to simulate the bucket going away."""

    def __init__(self, inner) -> None:
        self.inner = inner

    def current(self) -> IndexVersion:
        return self.inner.current()


def wait_until(predicate, timeout: float = WAIT_SECONDS) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        time.sleep(0.001)


@pytest.fixture
def index_dir(tmp_path: Path) -> Path:
    build_fixture_index(tmp_path)
    return tmp_path


def test_core_opens_nothing_and_starts_no_thread(index_dir: Path):
    source = CountingIndexSource(index_dir)
    threads_before = threading.active_count()

    core = Core(source, ELECTIONS_FILE)

    assert source.calls == 0
    assert threading.active_count() == threads_before
    core.close()


def test_open_index_is_the_initial_open_without_a_thread(index_dir: Path):
    source = CountingIndexSource(index_dir)
    threads_before = threading.active_count()
    core = Core(source, ELECTIONS_FILE)

    core.open_index()

    assert source.calls == 1
    assert threading.active_count() == threads_before
    assert core.find_polling_place("AC", 9, 422).data is not None
    core.close()


def test_new_index_is_served_only_after_refresh(index_dir: Path):
    core = open_core(index_dir)
    try:
        build_fixture_index(index_dir, built_at=REBUILT_AT)

        before = core.find_polling_place("AC", 9, 422)
        assert before.source.index_built_at == BUILT_AT

        core.refresh()

        after = core.find_polling_place("AC", 9, 422)
        assert after.source.index_built_at == REBUILT_AT
        assert after.data is not None
    finally:
        core.close()


def test_refresh_with_the_same_version_does_not_reopen(
    index_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    core = open_core(index_dir)
    try:
        opens: list[IndexVersion] = []
        real_open = index_module.open_index

        def spying_open(version: IndexVersion):
            opens.append(version)
            return real_open(version)

        monkeypatch.setattr(index_module, "open_index", spying_open)

        core.refresh()

        assert opens == []
    finally:
        core.close()


def test_concurrent_refreshes_are_serialized_and_open_the_new_file_once(
    index_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    source = OverlapDetectingIndexSource(index_dir)
    core = Core(source, ELECTIONS_FILE)
    core.open_index()
    try:
        build_fixture_index(index_dir, built_at=REBUILT_AT)
        opens: list[IndexVersion] = []
        real_open = index_module.open_index

        def spying_open(version: IndexVersion):
            opens.append(version)
            return real_open(version)

        monkeypatch.setattr(index_module, "open_index", spying_open)

        threads = [threading.Thread(target=core.refresh) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert source.overlapped is False
        assert source.calls == 1 + 4
        assert len(opens) == 1
        assert core.find_polling_place("AC", 9, 422).source.index_built_at == REBUILT_AT
    finally:
        core.close()


def test_failing_current_keeps_the_open_version_serving(index_dir: Path):
    source = SwappableIndexSource(LocalDirectoryIndexSource(index_dir))
    core = Core(source, ELECTIONS_FILE, clock=fixed_clock())
    core.open_index()
    try:
        source.inner = FailingIndexSource()

        core.refresh()

        answer = core.find_polling_place("AC", 9, 422)
        assert answer.data is not None
        assert answer.source.index_built_at == BUILT_AT
    finally:
        core.close()


def test_closing_an_index_waits_for_its_last_cursor(index_dir: Path):
    # A query in flight keeps its cursor on the old index while refresh() swaps and closes it.
    index = index_module.open_index(LocalDirectoryIndexSource(index_dir).current())
    with index.cursor() as cursor:
        index.close()
        assert cursor.execute("SELECT count(*) FROM polling_sections").fetchone() == (20,)
    with pytest.raises(IndexUnavailable), index.cursor():
        pass


def test_query_that_caught_a_version_closed_by_the_swap_retries_on_the_new_one(
    index_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    manager = IndexManager(LocalDirectoryIndexSource(index_dir), fixed_clock())
    manager.open()
    try:
        stale = manager.current()
        build_fixture_index(index_dir, built_at=REBUILT_AT)
        manager.refresh()  # closes ``stale``: no cursor was out
        fresh = manager.current()
        # A query that read the open version just before the swap sees it closed on entry.
        served = iter([stale, fresh])
        monkeypatch.setattr(manager, "current", lambda: next(served))

        with manager.query() as (index, cursor):
            assert index is fresh
            assert cursor.execute("SELECT count(*) FROM polling_sections").fetchone() == (20,)
    finally:
        manager.close()


# The check task, from start() to close()


def test_signal_schedules_one_check_per_interval(index_dir: Path):
    source = CountingIndexSource(index_dir)
    clock = MutableClock()
    manager = IndexManager(source, clock)
    assert manager.signal() is False  # no task yet: nothing to wake

    manager.start()
    try:
        assert source.calls == 1  # the initial open, synchronous
        assert manager.signal() is True
        wait_until(lambda: source.calls == 2)
        assert manager.signal() is False  # within the interval: ignored
        clock.advance(INDEX_CHECK_INTERVAL_SECONDS - 1)
        assert manager.signal() is False
        clock.advance(1)
        assert manager.signal() is True
        wait_until(lambda: source.calls == 3)
        # The interval counts from the end of the last check, a direct refresh() included.
        clock.advance(INDEX_CHECK_INTERVAL_SECONDS)
        manager.refresh()
        assert source.calls == 4
        assert manager.signal() is False
        clock.advance(INDEX_CHECK_INTERVAL_SECONDS)
        assert manager.signal() is True
        wait_until(lambda: source.calls == 5)
    finally:
        manager.close()
    assert source.calls == 5
    assert manager.signal() is False  # after close(): nothing to wake


def test_lifecycle_two_signals_in_a_row_refresh_once_and_a_late_signal_refreshes_again(
    index_dir: Path,
):
    source = CountingIndexSource(index_dir)
    clock = MutableClock()
    threads_before = threading.active_count()
    core = Core(source, ELECTIONS_FILE, clock=clock)

    core.start()
    assert source.calls == 1  # the initial open, synchronous
    assert threading.active_count() == threads_before + 1

    core.find_polling_place("AC", 9, 422)  # first query: signals the task
    wait_until(lambda: source.calls == 2)

    core.find_polling_place("AC", 9, 422)  # second query within the interval: ignored
    clock.advance(INDEX_CHECK_INTERVAL_SECONDS + 1)
    core.find_polling_place("AC", 9, 422)  # after the interval: a second refresh
    wait_until(lambda: source.calls == 3)

    core.close()
    assert threading.active_count() == threads_before
    assert source.calls == 3


def test_start_then_close_swaps_the_index_through_the_task(index_dir: Path):
    clock = MutableClock()
    core = Core(LocalDirectoryIndexSource(index_dir), ELECTIONS_FILE, clock=clock)
    core.start()
    try:
        build_fixture_index(index_dir, built_at=REBUILT_AT)
        # The query that signals still serves the open version; the swap happens in the task.
        assert core.find_polling_place("AC", 9, 422).source.index_built_at == BUILT_AT
        wait_until(
            lambda: core.find_polling_place("AC", 9, 422).source.index_built_at == REBUILT_AT
        )
    finally:
        core.close()


def test_failing_check_in_the_task_keeps_serving_and_is_logged(
    index_dir: Path, caplog: pytest.LogCaptureFixture
):
    source = SwappableIndexSource(LocalDirectoryIndexSource(index_dir))
    core = Core(source, ELECTIONS_FILE, clock=fixed_clock())
    core.start()
    try:
        source.inner = FailingIndexSource()
        core.find_polling_place("AC", 9, 422)
        wait_until(lambda: "bucket is down" in caplog.text)
        assert core.find_polling_place("AC", 9, 422).data is not None
    finally:
        core.close()
