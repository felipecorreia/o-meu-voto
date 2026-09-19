"""Internal seam: the open, read-only DuckDB index and the reload without restart.

``open_index()`` is the only place the core touches the file system. A query
takes a cursor from ``Index.cursor()`` (DuckDB connections are not shared
across threads; a cursor is a private duplicate), and an ``Index`` closed
while cursors are out only releases its connection when the last one returns,
so a query in flight finishes on the version it started with.

``IndexManager`` owns the open version, the ``refresh()`` that swaps it and the
check task of codebase-design 3.2: a thread created in ``start()``, woken by
the signal of each finished query, that ignores signals until
``INDEX_CHECK_INTERVAL_SECONDS`` have passed since the last check and
otherwise runs ``refresh()``. It has no timer of its own: without queries
there is no check (ADR 0001). The only synchronous call to
``IndexSource.current()`` is ``open()``.
"""

from __future__ import annotations

import datetime as dt
import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import duckdb

from br_elections_mcp.core.clock import Clock
from br_elections_mcp.core.errors import IndexUnavailable
from br_elections_mcp.core.index_source import IndexSource, IndexSourceUnavailable, IndexVersion
from br_elections_mcp.index_schema import TABLES, Manifest

INDEX_CHECK_INTERVAL_SECONDS = 60
"""Minimum seconds between two checks of the ``IndexSource`` by the task."""

QUERY_ATTEMPTS = 3
"""How many swaps a query tolerates under it before giving up (never in practice)."""

log = logging.getLogger(__name__)


class IndexClosed(IndexUnavailable):
    """Raised on ``Index.cursor()`` entry once the index was closed; ``IndexManager.query()``
    retries on the version that replaced it."""


class Index:
    def __init__(
        self, conn: duckdb.DuckDBPyConnection, version: IndexVersion, rounds: tuple[int, ...]
    ) -> None:
        self._conn = conn
        self._version = version
        self._rounds = rounds
        self._lock = threading.Lock()
        self._cursors = 0
        self._closing = False

    @property
    def manifest(self) -> Manifest:
        return self._version.manifest

    @property
    def version(self) -> str:
        return self._version.version

    @property
    def published_rounds(self) -> tuple[int, ...]:
        """Rounds with at least one section in the index, ascending."""
        return self._rounds

    @contextmanager
    def cursor(self) -> Iterator[duckdb.DuckDBPyConnection]:
        cursor = self.acquire()
        try:
            yield cursor
        finally:
            self.release(cursor)

    def acquire(self) -> duckdb.DuckDBPyConnection:
        """A cursor the caller must ``release()``; ``IndexClosed`` once closed."""
        with self._lock:
            if self._closing:
                raise IndexClosed("index is closed")
            self._cursors += 1
        try:
            return self._conn.cursor()
        except BaseException:
            self._release_slot()
            raise

    def release(self, cursor: duckdb.DuckDBPyConnection) -> None:
        try:
            cursor.close()
        finally:
            self._release_slot()

    def _release_slot(self) -> None:
        with self._lock:
            self._cursors -= 1
            if self._closing and self._cursors == 0:
                self._conn.close()

    def close(self) -> None:
        """Refuse new cursors; the connection closes once the last cursor out is released."""
        with self._lock:
            self._closing = True
            if self._cursors == 0:
                self._conn.close()


def open_index(version: IndexVersion) -> Index:
    """Open ``version`` read-only; ``IndexUnavailable`` when the file is missing or malformed."""
    try:
        conn = duckdb.connect(str(version.path), read_only=True)
    except duckdb.Error as exc:
        raise IndexUnavailable(f"cannot open index {version.path}: {exc}") from exc
    try:
        present = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
        missing = sorted(set(TABLES) - present)
        if missing:
            raise IndexUnavailable(f"index {version.path} lacks tables: {missing}")
        rows = conn.execute("SELECT DISTINCT round FROM polling_sections ORDER BY round").fetchall()
    except duckdb.Error as exc:
        conn.close()
        raise IndexUnavailable(f"index {version.path} is not readable: {exc}") from exc
    except IndexUnavailable:
        conn.close()
        raise
    return Index(conn, version, tuple(int(row[0]) for row in rows))


@dataclass(frozen=True, slots=True)
class IndexCheckFailure:
    """The last failed check of the ``IndexSource``, kept for ``health()``."""

    at: dt.datetime
    message: str


class IndexManager:
    """The open index, ``refresh()`` and the check task; see the module docstring."""

    def __init__(self, source: IndexSource, clock: Clock) -> None:
        self._source = source
        self._clock = clock
        self._index: Index | None = None
        self._closed = False
        self._refresh_lock = threading.Lock()
        self.last_check_at: dt.datetime | None = None
        """Instant of the last successful check, or ``None`` before the first."""
        self.last_check_error: IndexCheckFailure | None = None
        """The last failed check, or ``None``; a later success does not clear it."""
        self._gate: dt.datetime | None = None
        """Instant the last check was accepted or finished; signals are ignored until
        ``INDEX_CHECK_INTERVAL_SECONDS`` after it."""
        self._condition = threading.Condition()
        self._pending = False
        self._stopping = False
        self._thread: threading.Thread | None = None

    # The open version

    def current(self) -> Index:
        index = self._index
        if index is None:
            raise IndexUnavailable("index is not open; call open_index() or start() first")
        return index

    @contextmanager
    def query(self) -> Iterator[tuple[Index, duckdb.DuckDBPyConnection]]:
        """The open version and a cursor on it, for one query.

        A swap between reading the version and taking the cursor closes that
        version under the query; it then starts over on the new one instead of
        failing. Raises ``IndexUnavailable`` when nothing is open.
        """
        for _ in range(QUERY_ATTEMPTS):
            index = self.current()
            try:
                cursor = index.acquire()
            except IndexClosed:
                continue
            try:
                yield index, cursor
            finally:
                index.release(cursor)
            return
        raise IndexUnavailable("index kept being swapped under the query")

    def open(self) -> None:
        """The initial, synchronous open: raises ``IndexUnavailable`` on any failure."""
        with self._refresh_lock:
            try:
                version = self._source.current()
            except IndexSourceUnavailable as exc:
                raise IndexUnavailable(str(exc)) from exc
            self._swap(open_index(version))

    def refresh(self) -> None:
        """Check the source and swap when its version differs from the open one.

        Serialized by a lock. A failing check is logged and kept in
        ``last_check_error``; the open version keeps being served.
        """
        with self._refresh_lock:
            if self._closed:
                return
            try:
                version = self._source.current()
                current = self._index
                if current is None or current.version != version.version:
                    self._swap(open_index(version))
                    log.info("index swapped to version %s", version.version)
            except (IndexSourceUnavailable, IndexUnavailable) as exc:
                self.last_check_error = IndexCheckFailure(at=self._clock(), message=str(exc))
                log.warning("index check failed, keeping the open version: %s", exc)
            else:
                self.last_check_at = self._clock()
            finally:
                self._gate = self._clock()

    def _swap(self, new_index: Index) -> None:
        previous, self._index = self._index, new_index
        if previous is not None:
            previous.close()

    # The check task

    def start(self) -> None:
        """The initial open, then the task; a failing open starts nothing."""
        self.open()
        self._thread = threading.Thread(target=self._run, name="index-check", daemon=True)
        self._thread.start()

    def signal(self) -> bool:
        """A query finished: schedule a check unless one ran less than
        ``INDEX_CHECK_INTERVAL_SECONDS`` ago. Returns whether a check was scheduled;
        always ``False`` without a running task. Never blocks on the check itself."""
        if self._thread is None:
            return False
        with self._condition:
            now = self._clock()
            if self._gate is not None and (now - self._gate).total_seconds() < (
                INDEX_CHECK_INTERVAL_SECONDS
            ):
                return False
            self._gate = now
            self._pending = True
            self._condition.notify()
            return True

    def close(self) -> None:
        """Stop the task, wait for a check in flight, then close the index."""
        if self._thread is not None:
            with self._condition:
                self._stopping = True
                self._condition.notify()
            self._thread.join()
            self._thread = None
        with self._refresh_lock:
            self._closed = True
            previous, self._index = self._index, None
            if previous is not None:
                previous.close()

    def _run(self) -> None:
        while True:
            with self._condition:
                while not self._pending and not self._stopping:
                    self._condition.wait()
                if self._stopping:
                    return
                self._pending = False
            self.refresh()
