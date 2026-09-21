"""Internal seam: the round-resolution table of codebase-design 3.4.

That section is the single owner of the rule; this module is its code. One
function per block of the table (T1-T7 for places and sections, C1-C4 for the
candidate list, F1-F5 for the candidate profile), each taking the sets of
rounds the table names and returning the answered round with its warning.
Round 1 and round 2 are rounds of the same election, never different
elections, so a round never produces ``not_found`` or an empty list: every
line falls back to a round that has data.

"Published" is judged per dataset: a round is published for places when the
index has a section of it, and for candidates when it has a candidate row of
it. The table's invariant that a round never produces ``not_found`` forces
that reading (a round with candidates but no sections yet cannot be the
answered round of ``find_polling_place``), and it keeps the C4 warning
truthful when the TSE publishes the two files days apart.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Literal

from br_elections_mcp.core.errors import InvalidQuery
from br_elections_mcp.domain import Election, Office

ROUNDS_WITHOUT_CALENDAR = 2
"""The bound of ``round`` without a coincident current election (3.4, common rules)."""

OFFICE_LABELS: dict[Office, str] = {
    Office.PRESIDENTE: "presidente",
    Office.VICE_PRESIDENTE: "vice-presidente",
    Office.GOVERNADOR: "governador",
    Office.VICE_GOVERNADOR: "vice-governador",
    Office.SENADOR: "senador",
    Office.PRIMEIRO_SUPLENTE: "1º suplente",
    Office.SEGUNDO_SUPLENTE: "2º suplente",
    Office.DEPUTADO_FEDERAL: "deputado federal",
    Office.DEPUTADO_ESTADUAL: "deputado estadual",
    Office.DEPUTADO_DISTRITAL: "deputado distrital",
}
"""PT-BR label of each office, lowercase, for the voter-facing warnings."""

SECOND_ROUND_OFFICES: frozenset[Office] = frozenset({Office.PRESIDENTE, Office.GOVERNADOR})
"""Offices that can have a second round (the C3 wording tells them apart)."""

AnswerKind = Literal["lista", "ficha"]


@dataclass(frozen=True, slots=True)
class RoundResolution:
    """The round a query answers and the warning that explains it, if any."""

    round: int
    warning: str | None = None


# Warnings (voter-facing, PT-BR; the texts of the table for rounds 2 and 1).


def _ordinal(round_number: int) -> str:
    return f"{round_number}º turno"


def places_not_yet_published_warning(requested: int, answered: int) -> str:
    """T2 and T4."""
    return (
        f"O TSE ainda não publicou os locais do {_ordinal(requested)}; este é o local do "
        f"{_ordinal(answered)}. Confira de novo perto da data."
    )


def places_no_data_warning(requested: int, answered: int) -> str:
    """T7."""
    return f"Não há dados do {_ordinal(requested)}; este é o local do {_ordinal(answered)}."


def office_without_round_warning(
    office: Office, uf: str, requested: int, answered: int, kind: AnswerKind
) -> str:
    """C3 and F4: the round is published, but not for this office in this UF."""
    if office in SECOND_ROUND_OFFICES:
        where = "" if office is Office.PRESIDENTE else f" no {uf}"
        head = f"Não há {_ordinal(requested)} para {OFFICE_LABELS[office]}{where}"
    else:
        label = OFFICE_LABELS[office]
        head = f"{label[0].upper()}{label[1:]} não tem {_ordinal(requested)}"
    return f"{head}; esta é a {kind} do {_ordinal(answered)}."


def candidates_not_yet_published_warning(requested: int, answered: int, kind: AnswerKind) -> str:
    """C4 and F5."""
    return (
        f"O TSE ainda não publicou os candidatos do {_ordinal(requested)}; esta é a {kind} do "
        f"{_ordinal(answered)}."
    )


def candidate_not_in_round_warning(requested: int, answered: int) -> str:
    """F3."""
    return (
        f"Este candidato não disputa o {_ordinal(requested)}; esta é a ficha do "
        f"{_ordinal(answered)}."
    )


# Common rules.


def check_round_bound(requested: int | None, election: Election | None) -> None:
    """``round`` outside 1..n of the calendar's rounds (1..2 without a coincident
    current election) is ``InvalidQuery``. ``requested`` is already a positive integer."""
    if requested is None:
        return
    last = len(election.rounds) if election is not None else ROUNDS_WITHOUT_CALENDAR
    if requested > last:
        raise InvalidQuery(f"turno inválido: {requested}; os turnos possíveis vão de 1 a {last}")


def highest_or_requested(present: tuple[int, ...], requested: int | None) -> int:
    """The requested round when present, else the highest present. ``present`` is
    never empty. What every line answers once its warning is decided; also the round
    a ``not_found`` answer refers to."""
    if requested is not None and requested in present:
        return requested
    return present[-1]


# T1-T7: places and sections.


def resolve_place_round(
    *,
    published: tuple[int, ...],
    requested: int | None,
    election: Election | None,
    today: dt.date,
) -> RoundResolution:
    """Lines T1 to T7. ``published`` is the ascending, non-empty tuple of rounds with a
    section in the index; ``election`` the coincident current election, or null."""
    check_round_bound(requested, election)
    highest = published[-1]
    if election is not None:
        if requested is None:
            # The election is current, so a round on or after today exists.
            next_round = election.next_round_on(today)
            target = next_round.number if next_round is not None else highest
            if target in published:
                return RoundResolution(target)  # T1
            return RoundResolution(highest, places_not_yet_published_warning(target, highest))  # T2
        if requested in published:
            return RoundResolution(requested)  # T3
        return RoundResolution(highest, places_not_yet_published_warning(requested, highest))  # T4
    if requested is None:
        return RoundResolution(highest)  # T5
    if requested in published:
        return RoundResolution(requested)  # T6
    return RoundResolution(highest, places_no_data_warning(requested, highest))  # T7


# C1-C4: the candidate list.


def resolve_list_round(
    *,
    office_rounds: tuple[int, ...],
    published: tuple[int, ...],
    requested: int | None,
    office: Office,
    uf: str,
) -> RoundResolution:
    """Lines C1 to C4. ``office_rounds`` is the ascending, non-empty tuple of rounds in
    which (``uf``, ``office``) has a row; ``published`` the rounds with any candidate row."""
    highest = office_rounds[-1]
    if requested is None:
        return RoundResolution(highest)  # C1
    if requested in office_rounds:
        return RoundResolution(requested)  # C2
    if requested in published:
        return RoundResolution(
            highest, office_without_round_warning(office, uf, requested, highest, "lista")
        )  # C3
    return RoundResolution(
        highest, candidates_not_yet_published_warning(requested, highest, "lista")
    )  # C4


# F1-F5: the candidate profile.


def resolve_profile_round(
    *,
    candidacy_rounds: tuple[int, ...],
    office_rounds: tuple[int, ...],
    published: tuple[int, ...],
    requested: int | None,
    office: Office,
    uf: str,
) -> RoundResolution:
    """Lines F1 to F5. ``candidacy_rounds`` is the ascending, non-empty tuple of rounds
    of the candidacy itself (by ``sq_candidato``, the rounds it appears in; by the trio,
    the rounds with an on-ballot candidacy of that number); ``office_rounds`` the rounds
    of its office in its UF; ``published`` the rounds with any candidate row."""
    highest = candidacy_rounds[-1]
    if requested is None:
        return RoundResolution(highest)  # F1
    if requested in candidacy_rounds:
        return RoundResolution(requested)  # F2
    if requested in office_rounds:
        return RoundResolution(highest, candidate_not_in_round_warning(requested, highest))  # F3
    if requested in published:
        return RoundResolution(
            highest, office_without_round_warning(office, uf, requested, highest, "ficha")
        )  # F4
    return RoundResolution(
        highest, candidates_not_yet_published_warning(requested, highest, "ficha")
    )  # F5
