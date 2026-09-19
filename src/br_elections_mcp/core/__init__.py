"""The deep module: the voter's questions over a local index, with no HTTP and no network.

Public surface: ``Core``, the ``IndexSource`` port and the answer models.
"""

from br_elections_mcp.core.answers import (
    ElectionInfo,
    Municipality,
    NotFound,
    PollingPlace,
    PollingPlaceAnswer,
    PollingPlaceData,
    PreviousPlace,
    Source,
)
from br_elections_mcp.core.core import Clock, Core, system_clock
from br_elections_mcp.core.errors import IndexUnavailable, InvalidQuery
from br_elections_mcp.core.index_source import IndexSource, IndexSourceUnavailable, IndexVersion

__all__ = [
    "Clock",
    "Core",
    "ElectionInfo",
    "IndexSource",
    "IndexSourceUnavailable",
    "IndexUnavailable",
    "IndexVersion",
    "InvalidQuery",
    "Municipality",
    "NotFound",
    "PollingPlace",
    "PollingPlaceAnswer",
    "PollingPlaceData",
    "PreviousPlace",
    "Source",
    "system_clock",
]
