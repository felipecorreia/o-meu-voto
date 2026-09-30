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
from br_elections_mcp.index_schema import manifest_version
from br_elections_mcp.index_store import GcsIndexSource, LocalDirectoryIndexSource
from br_elections_mcp.pipeline.build import apply_photo_urls
from tests.conftest import (
    ACRE_POLLING_PLACES,
    BUILT_AT,
    CLOCK,
    ELECTIONS_FILE,
    NOW,
    FakeGcsBucketClient,
    build_fixture_index,
    fixed_clock,
    open_core,
    published_blobs,
    without_round_2,
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


# A refresh must change what the queries read, not only the manifest-derived fields. DuckDB
# keeps one database instance per path, so a new version stored at the path of the open one
# is silently read from the old, unlinked file while ``health()`` and every answer's
# ``source`` already name the new version. ``GcsIndexSource`` (production) gives each version
# its own path; these tests change DATA between versions and assert on a queried value.

PHOTO_SHA256 = "ab" * 32
PHOTO_URL = f"https://fotos.example.org/FAC10000000001_div-{PHOTO_SHA256}.jpg"
PHOTO_SQ = 10000000001


@pytest.fixture(scope="module")
def bare_and_photo(tmp_path_factory: pytest.TempPathFactory) -> tuple[dict, dict]:
    """The same build twice, published like the pipeline does; the second has a photo URL
    written into it (what ``mirror-photos`` does), so the two differ in data only."""
    bare_dir = tmp_path_factory.mktemp("reload-bare")
    photo_dir = tmp_path_factory.mktemp("reload-photo")
    build_fixture_index(bare_dir)
    build_fixture_index(photo_dir)
    apply_photo_urls(photo_dir, {PHOTO_SQ: PHOTO_URL}, {PHOTO_SQ: PHOTO_SHA256})
    bare, photo = published_blobs(bare_dir), published_blobs(photo_dir)
    assert bare["manifest.json"] != photo["manifest.json"]
    return bare, photo


def _prefixed(blobs: dict[str, bytes]) -> dict[str, bytes]:
    return {f"idx/{name}": content for name, content in blobs.items()}


def _photo_url(core: Core) -> str | None:
    return core.get_candidate(PHOTO_SQ).data.candidate.photo_url


def _gcs_core(tmp_path: Path, blobs: dict[str, bytes]) -> tuple[Core, FakeGcsBucketClient]:
    client = FakeGcsBucketClient(_prefixed(blobs))
    source = GcsIndexSource("bucket", "idx", tmp_path / "cache", client=client)
    core = Core(source, ELECTIONS_FILE, clock=CLOCK)
    core.open_index()
    return core, client


def test_new_index_is_served_only_after_refresh(tmp_path: Path, bare_and_photo: tuple[dict, dict]):
    bare, photo = bare_and_photo
    core, client = _gcs_core(tmp_path, bare)
    try:
        client.blobs = _prefixed(photo)

        assert core.health().index_version == manifest_version(bare["manifest.json"])
        assert _photo_url(core) is None

        core.refresh()

        assert core.health().index_version == manifest_version(photo["manifest.json"])
        assert core.find_polling_place("AC", 9, 422).data is not None
        assert _photo_url(core) == PHOTO_URL
    finally:
        core.close()


def test_successive_refreshes_through_the_gcs_source_each_serve_their_own_data(
    tmp_path: Path, bare_and_photo: tuple[dict, dict]
):
    bare, photo = bare_and_photo
    core, client = _gcs_core(tmp_path, bare)
    try:
        for blobs, expected in ((photo, PHOTO_URL), (bare, None), (photo, PHOTO_URL)):
            client.blobs = _prefixed(blobs)
            core.refresh()
            assert _photo_url(core) == expected
    finally:
        core.close()


def test_a_query_in_flight_finishes_on_the_version_it_started_with(
    tmp_path: Path, bare_and_photo: tuple[dict, dict]
):
    """The source deletes the previous copy on the swap; the open connection keeps its inode."""
    bare, photo = bare_and_photo
    core, client = _gcs_core(tmp_path, bare)
    try:
        with core._index_manager.query() as (_, cursor):
            client.blobs = _prefixed(photo)
            core.refresh()
            assert cursor.execute("SELECT count(photo_url) FROM candidates").fetchone() == (0,)
        assert _photo_url(core) == PHOTO_URL
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


class ManifestCountsOffIndexSource:
    """Delivers the real index under a manifest whose counts say something else."""

    def __init__(self, directory: Path, table: str) -> None:
        self._inner = LocalDirectoryIndexSource(directory)
        self._table = table

    def current(self) -> IndexVersion:
        version = self._inner.current()
        counts = {**version.manifest.counts, self._table: version.manifest.counts[self._table] + 1}
        manifest = version.manifest.model_copy(update={"counts": counts})
        return IndexVersion(path=version.path, manifest=manifest, version=version.version)


def test_an_index_that_does_not_match_its_manifest_is_refused_on_open(index_dir: Path):
    core = Core(ManifestCountsOffIndexSource(index_dir, "candidates"), ELECTIONS_FILE)
    with pytest.raises(IndexUnavailable, match="does not match its manifest"):
        core.open_index()


def test_a_file_that_is_not_the_one_the_manifest_names_is_refused_and_the_open_version_serves(
    index_dir: Path, tmp_path: Path
):
    # Rebuilding in place under an open connection: DuckDB keeps serving the old file at
    # that path, so the new manifest's counts do not match what the connection reads.
    core = open_core(index_dir)
    try:
        opened = core.health().index_version
        fewer_places = without_round_2(ACRE_POLLING_PLACES, tmp_path)
        build_fixture_index(index_dir, polling_places=fewer_places, built_at=REBUILT_AT)

        core.refresh()

        health = core.health()
        assert health.index_version == opened
        assert health.last_index_check_error is not None
        assert "does not match its manifest" in health.last_index_check_error.message
        assert core.find_polling_place("AC", 9, 422).data is not None
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
