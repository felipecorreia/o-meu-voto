import datetime as dt

import pytest

from br_elections_mcp.domain import (
    BALLOT_OFFICES,
    CalendarSource,
    Election,
    ElectionKind,
    ElectionRound,
    Office,
    VotingHours,
)

SOURCE = CalendarSource(
    title="Resolução", url="https://www.tse.jus.br/x", verified_at=dt.date(2026, 9, 17)
)
HOURS = VotingHours(start=dt.time(8), end=dt.time(17), timezone="America/Sao_Paulo")


def election(**overrides):
    fields = {
        "id": "general-2026",
        "name": "Eleições Gerais 2026",
        "year": 2026,
        "kind": ElectionKind.GENERAL,
        "rounds": (
            ElectionRound(1, dt.date(2026, 10, 4)),
            ElectionRound(2, dt.date(2026, 10, 25)),
        ),
        "voting_hours": HOURS,
        "offices": (Office.PRESIDENTE, Office.GOVERNADOR),
        "calendar_source": SOURCE,
    }
    fields.update(overrides)
    return Election(**fields)


def test_ballot_offices_are_the_ones_the_voter_chooses_directly():
    expected = {
        Office.PRESIDENTE,
        Office.GOVERNADOR,
        Office.SENADOR,
        Office.DEPUTADO_FEDERAL,
        Office.DEPUTADO_ESTADUAL,
        Office.DEPUTADO_DISTRITAL,
    }
    assert expected == BALLOT_OFFICES
    assert all(office.is_ballot_office for office in BALLOT_OFFICES)
    assert not Office.VICE_GOVERNADOR.is_ballot_office


def test_running_mates_point_to_the_head_of_their_ticket():
    assert Office.VICE_PRESIDENTE.ticket_head is Office.PRESIDENTE
    assert Office.VICE_GOVERNADOR.ticket_head is Office.GOVERNADOR
    assert Office.PRIMEIRO_SUPLENTE.ticket_head is Office.SENADOR
    assert Office.SEGUNDO_SUPLENTE.ticket_head is Office.SENADOR
    assert Office.SENADOR.ticket_head is Office.SENADOR


def test_voting_hours_label_is_in_voter_language():
    assert HOURS.label == "8h às 17h (horário de Brasília)"


@pytest.mark.parametrize(
    ("start", "end", "timezone"),
    [
        (dt.time(17), dt.time(8), "America/Sao_Paulo"),
        (dt.time(8), dt.time(8), "America/Sao_Paulo"),
        (dt.time(8), dt.time(17), "Brasilia/Nowhere"),
    ],
)
def test_voting_hours_reject_inverted_window_and_unknown_timezone(start, end, timezone):
    with pytest.raises(ValueError):
        VotingHours(start=start, end=end, timezone=timezone)


def test_rounds_must_be_numbered_from_one_in_date_order():
    with pytest.raises(ValueError, match=r"numbered 1\.\.n"):
        election(rounds=(ElectionRound(2, dt.date(2026, 10, 4)),))
    with pytest.raises(ValueError, match="increasing date order"):
        election(
            rounds=(
                ElectionRound(1, dt.date(2026, 10, 25)),
                ElectionRound(2, dt.date(2026, 10, 4)),
            )
        )
    with pytest.raises(ValueError, match="outside year"):
        election(year=2027)


def test_offices_in_dispute_must_be_ballot_offices_without_repeats():
    with pytest.raises(ValueError, match="non-ballot"):
        election(offices=(Office.PRESIDENTE, Office.VICE_PRESIDENTE))
    with pytest.raises(ValueError, match="twice"):
        election(offices=(Office.PRESIDENTE, Office.PRESIDENTE))
    with pytest.raises(ValueError, match="at least one office"):
        election(offices=())


def test_next_round_on_walks_the_calendar():
    e = election()
    assert e.next_round_on(dt.date(2026, 9, 17)) == e.round(1)
    assert e.next_round_on(dt.date(2026, 10, 4)) == e.round(1)
    assert e.next_round_on(dt.date(2026, 10, 5)) == e.round(2)
    assert e.next_round_on(dt.date(2026, 10, 26)) is None
    assert e.last_round == e.round(2)
    with pytest.raises(KeyError):
        e.round(3)
