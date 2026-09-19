"""Internal seam: the elections of the YAML and "which election is current".

This is the only calendar logic in the system (codebase-design 3.2). The
current election is the first of the file whose last round has not passed;
the coincidence rule of 3.4 decides whether the index was built for it.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from br_elections_mcp.domain import Election
from br_elections_mcp.elections import load_elections
from br_elections_mcp.index_schema import Manifest


class Calendar:
    def __init__(self, elections: tuple[Election, ...]) -> None:
        self._elections = elections

    @classmethod
    def from_file(cls, path: Path) -> Calendar:
        return cls(load_elections(path))

    def current_election(self, today: dt.date) -> Election | None:
        """The first election of the file whose last round is on or after ``today``."""
        return next((e for e in self._elections if e.last_round.date >= today), None)

    def current_or_last_election(self, today: dt.date) -> Election:
        """``current_election``, or the last election of the file once every one is over.

        The file is never empty (``elections.py`` rejects it), so this always
        returns an election: ``election_info`` describes a past election
        instead of answering ``not_found``.
        """
        return self.current_election(today) or self._elections[-1]

    def divulgacandcontas_election_id(self, year: int) -> str | None:
        """The curated DivulgaCandContas id of the election of ``year`` (at most one per
        year), or null when the file has no such election or no id for it."""
        election = next((e for e in self._elections if e.year == year), None)
        return election.divulgacandcontas_election_id if election is not None else None

    def coincident_election(self, today: dt.date, manifest: Manifest) -> Election | None:
        """The current election, when the index was built for it (codebase-design 3.4).

        Same year as the manifest and, for every round the manifest carries, the
        same date as the round of that number in the calendar. A round the
        manifest does not carry yet does not count against. Null election in the
        manifest (monthly ``ATUAL`` file) never coincides.
        """
        election = self.current_election(today)
        if election is None or manifest.election_year != election.year:
            return None
        if not manifest.election_dates:
            return None
        calendar_dates = {r.number: r.date for r in election.rounds}
        for number, date in manifest.election_dates.items():
            if calendar_dates.get(number) != date:
                return None
        return election
