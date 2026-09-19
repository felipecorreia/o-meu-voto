"""Internal seam: the open, read-only DuckDB index and the version it came from.

Opening is the only place the core touches the file system. A query takes a
cursor from ``Index.cursor()`` (DuckDB connections are not shared across
threads; a cursor is a private duplicate).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import duckdb

from br_elections_mcp.core.errors import IndexUnavailable
from br_elections_mcp.core.index_source import IndexVersion
from br_elections_mcp.index_schema import TABLES, Manifest


class Index:
    def __init__(
        self, conn: duckdb.DuckDBPyConnection, version: IndexVersion, rounds: tuple[int, ...]
    ) -> None:
        self._conn = conn
        self._version = version
        self._rounds = rounds

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
        cursor = self._conn.cursor()
        try:
            yield cursor
        finally:
            cursor.close()

    def close(self) -> None:
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
