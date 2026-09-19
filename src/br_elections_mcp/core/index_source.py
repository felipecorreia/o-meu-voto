"""The ``IndexSource`` port: which index version is current and where it is on disk.

The core only knows this port. Its adapters (a local directory, a GCS bucket)
live in ``index_store.py``, outside the core, so "the core has no network"
stays verifiable by import.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from br_elections_mcp.index_schema import Manifest


class IndexSourceUnavailable(RuntimeError):
    """The adapter could not determine the current version; no partial version is returned."""


@dataclass(frozen=True, slots=True)
class IndexVersion:
    path: Path
    """Local path of ``index.duckdb``."""
    manifest: Manifest
    version: str
    """Identifier of the version: the SHA-256 of the manifest bytes."""


class IndexSource(Protocol):
    def current(self) -> IndexVersion:
        """Return the current version. May be slow and may touch the network.

        Raises ``IndexSourceUnavailable`` when the version cannot be determined.
        """
        ...
