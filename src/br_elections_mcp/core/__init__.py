"""The deep module: the voter's questions over a local index, with no HTTP and no network.

Public surface: ``Core``, the ``IndexSource`` port and the answer models.
"""

from br_elections_mcp.core.answers import (
    CalendarSourceInfo,
    CandidateListItem,
    CandidatesAnswer,
    CandidatesData,
    Coalition,
    CuratedSource,
    ElectionInfo,
    ElectionInfoAnswer,
    ElectionInfoData,
    ElectionInfoRound,
    Federation,
    MunicipalitiesAnswer,
    MunicipalitiesData,
    Municipality,
    MunicipalityMatch,
    NotFound,
    Party,
    PollingPlace,
    PollingPlaceAnswer,
    PollingPlaceData,
    PollingPlaceListItem,
    PollingPlacesAnswer,
    PollingPlacesData,
    PreviousPlace,
    Source,
)
from br_elections_mcp.core.clock import Clock, system_clock
from br_elections_mcp.core.core import Core, Near
from br_elections_mcp.core.errors import IndexUnavailable, InvalidQuery
from br_elections_mcp.core.index_source import IndexSource, IndexSourceUnavailable, IndexVersion

__all__ = [
    "CalendarSourceInfo",
    "CandidateListItem",
    "CandidatesAnswer",
    "CandidatesData",
    "Clock",
    "Coalition",
    "Core",
    "CuratedSource",
    "ElectionInfo",
    "ElectionInfoAnswer",
    "ElectionInfoData",
    "ElectionInfoRound",
    "Federation",
    "IndexSource",
    "IndexSourceUnavailable",
    "IndexUnavailable",
    "IndexVersion",
    "InvalidQuery",
    "MunicipalitiesAnswer",
    "MunicipalitiesData",
    "Municipality",
    "MunicipalityMatch",
    "Near",
    "NotFound",
    "Party",
    "PollingPlace",
    "PollingPlaceAnswer",
    "PollingPlaceData",
    "PollingPlaceListItem",
    "PollingPlacesAnswer",
    "PollingPlacesData",
    "PreviousPlace",
    "Source",
    "system_clock",
]
