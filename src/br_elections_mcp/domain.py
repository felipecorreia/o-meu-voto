"""Domain model: entities, value objects and their invariants.

Identifiers are in English; domain values (enum members, notes shown to the
voter) are in PT-BR. See CONTEXT.md for the glossary and docs/domain-model.md
for the full model, including which TSE CSV columns feed each entity and which
are discarded.

This module holds the part of the model that already has a data source in the
repository (data/elections.yaml). PollingSection, PollingPlace, Municipality
and Candidate are specified in docs/domain-model.md and arrive with the index.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class UF(StrEnum):
    """Unidade da federação, the two-letter code that partitions every TSE dataset.

    ZZ is the electorate abroad; BR appears only on national candidacies
    (president and vice) and never on a polling section.
    """

    AC = "AC"
    AL = "AL"
    AM = "AM"
    AP = "AP"
    BA = "BA"
    CE = "CE"
    DF = "DF"
    ES = "ES"
    GO = "GO"
    MA = "MA"
    MG = "MG"
    MS = "MS"
    MT = "MT"
    PA = "PA"
    PB = "PB"
    PE = "PE"
    PI = "PI"
    PR = "PR"
    RJ = "RJ"
    RN = "RN"
    RO = "RO"
    RR = "RR"
    RS = "RS"
    SC = "SC"
    SE = "SE"
    SP = "SP"
    TO = "TO"
    ZZ = "ZZ"
    BR = "BR"


POLLING_UFS: frozenset[UF] = frozenset(UF) - {UF.BR}
"""The UFs that have polling sections: the 26 states, DF and ZZ (abroad)."""


class ElectionKind(StrEnum):
    """Tipo de eleição, que determina quais cargos estão em disputa."""

    GENERAL = "geral"
    MUNICIPAL = "municipal"


class Office(StrEnum):
    """Cargo de uma candidatura, como registrado no TSE.

    Ballot offices are the ones the voter chooses directly. The others belong
    to a ticket headed by a ballot office (vice and suplentes share the head's
    ballot number). Municipal offices are added when a municipal election
    enters the scope.
    """

    PRESIDENTE = "presidente"
    VICE_PRESIDENTE = "vice_presidente"
    GOVERNADOR = "governador"
    VICE_GOVERNADOR = "vice_governador"
    SENADOR = "senador"
    PRIMEIRO_SUPLENTE = "primeiro_suplente"
    SEGUNDO_SUPLENTE = "segundo_suplente"
    DEPUTADO_FEDERAL = "deputado_federal"
    DEPUTADO_ESTADUAL = "deputado_estadual"
    DEPUTADO_DISTRITAL = "deputado_distrital"

    @property
    def is_ballot_office(self) -> bool:
        """True when the voter picks this office directly on the ballot."""
        return self in BALLOT_OFFICES

    @property
    def ticket_head(self) -> Office:
        """The office whose candidate heads the ticket this office belongs to."""
        return _TICKET_HEAD.get(self, self)


BALLOT_OFFICES: frozenset[Office] = frozenset(
    {
        Office.PRESIDENTE,
        Office.GOVERNADOR,
        Office.SENADOR,
        Office.DEPUTADO_FEDERAL,
        Office.DEPUTADO_ESTADUAL,
        Office.DEPUTADO_DISTRITAL,
    }
)

_TICKET_HEAD: dict[Office, Office] = {
    Office.VICE_PRESIDENTE: Office.PRESIDENTE,
    Office.VICE_GOVERNADOR: Office.GOVERNADOR,
    Office.PRIMEIRO_SUPLENTE: Office.SENADOR,
    Office.SEGUNDO_SUPLENTE: Office.SENADOR,
}


@dataclass(frozen=True, slots=True)
class VotingHours:
    """Voting window, identical for the whole country, in one IANA timezone."""

    start: dt.time
    end: dt.time
    timezone: str

    def __post_init__(self) -> None:
        if self.start >= self.end:
            raise ValueError(f"voting hours must start before they end: {self.start}-{self.end}")
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown IANA timezone: {self.timezone!r}") from exc

    @property
    def label(self) -> str:
        """Texto para o eleitor, ex.: '8h às 17h (horário de Brasília)'."""
        tz = " (horário de Brasília)" if self.timezone == "America/Sao_Paulo" else ""
        return f"{_hour_label(self.start)} às {_hour_label(self.end)}{tz}"


def _hour_label(value: dt.time) -> str:
    return f"{value.hour}h" if value.minute == 0 else f"{value.hour}h{value.minute:02d}"


@dataclass(frozen=True, slots=True)
class ElectionRound:
    """One voting day of an election (turno)."""

    number: int
    date: dt.date
    note: str | None = None

    def __post_init__(self) -> None:
        if self.number < 1:
            raise ValueError(f"round number must be positive: {self.number}")


@dataclass(frozen=True, slots=True)
class CalendarSource:
    """The normative act the calendar was curated from, and when it was checked."""

    title: str
    url: str
    verified_at: dt.date

    def __post_init__(self) -> None:
        if not self.title:
            raise ValueError("calendar source needs a title")
        if not self.url.startswith("https://"):
            raise ValueError(f"calendar source url must be https: {self.url!r}")


@dataclass(frozen=True, slots=True)
class Election:
    """An election as curated by hand in data/elections.yaml.

    Invariants: rounds are numbered 1..n in strictly increasing date order and
    all fall in `year`; every office in dispute is a ballot office.
    """

    id: str
    name: str
    year: int
    kind: ElectionKind
    rounds: tuple[ElectionRound, ...]
    voting_hours: VotingHours
    offices: tuple[Office, ...]
    calendar_source: CalendarSource
    notes: tuple[str, ...] = ()
    divulgacandcontas_election_id: str | None = None
    """The election id in the DivulgaCandContas URLs, curated by hand: it is not the
    ``CD_ELEICAO`` of the TSE files. Null while unknown; the candidate page link is then null."""

    def __post_init__(self) -> None:
        if not self.id or not self.name:
            raise ValueError("election needs an id and a name")
        if self.divulgacandcontas_election_id is not None and (
            not self.divulgacandcontas_election_id.isdigit()
        ):
            raise ValueError(
                f"election {self.id!r} divulgacandcontas_election_id must be digits: "
                f"{self.divulgacandcontas_election_id!r}"
            )
        if not self.rounds:
            raise ValueError(f"election {self.id!r} needs at least one round")
        numbers = [r.number for r in self.rounds]
        if numbers != list(range(1, len(self.rounds) + 1)):
            raise ValueError(f"election {self.id!r} rounds must be numbered 1..n: {numbers}")
        dates = [r.date for r in self.rounds]
        if any(later <= earlier for earlier, later in pairwise(dates)):
            raise ValueError(f"election {self.id!r} rounds must be in increasing date order")
        if any(d.year != self.year for d in dates):
            raise ValueError(f"election {self.id!r} has a round outside year {self.year}")
        if not self.offices:
            raise ValueError(f"election {self.id!r} needs at least one office in dispute")
        if len(set(self.offices)) != len(self.offices):
            raise ValueError(f"election {self.id!r} lists an office twice")
        not_ballot = [o for o in self.offices if not o.is_ballot_office]
        if not_ballot:
            raise ValueError(f"election {self.id!r} lists non-ballot offices: {not_ballot}")

    def round(self, number: int) -> ElectionRound:
        for r in self.rounds:
            if r.number == number:
                return r
        raise KeyError(f"election {self.id!r} has no round {number}")

    def next_round_on(self, day: dt.date) -> ElectionRound | None:
        """The first round on or after `day`, or None when the election is over."""
        return next((r for r in self.rounds if r.date >= day), None)

    @property
    def last_round(self) -> ElectionRound:
        return self.rounds[-1]
