"""``Core.election_info`` through its interface, over ``data/elections.yaml`` (issue #7).

Never touches the index: these tests never call ``open_index()``, matching the
promise that this answer is curated and never goes stale.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from br_elections_mcp.core import Core, InvalidQuery
from br_elections_mcp.domain import Office
from br_elections_mcp.index_store import LocalDirectoryIndexSource
from tests.conftest import ELECTIONS_FILE, fixed_clock

ROUND_1 = dt.date(2026, 10, 4)
ROUND_2 = dt.date(2026, 10, 25)

BALLOT_OFFICES = [
    Office.PRESIDENTE,
    Office.GOVERNADOR,
    Office.SENADOR,
    Office.DEPUTADO_FEDERAL,
    Office.DEPUTADO_ESTADUAL,
    Office.DEPUTADO_DISTRITAL,
]


def unopened_core(tmp_path: Path, *, on: dt.datetime | None = None) -> Core:
    clock = fixed_clock(on) if on is not None else fixed_clock()
    return Core(LocalDirectoryIndexSource(tmp_path / "unused"), ELECTIONS_FILE, clock=clock)


def test_before_round_1_next_round_is_round_1(tmp_path: Path):
    core = unopened_core(tmp_path)
    answer = core.election_info(dt.date(2026, 9, 18))

    assert answer.not_found is None
    assert answer.warnings == []
    assert answer.election is None
    data = answer.data
    assert data is not None
    assert [(r.number, r.date) for r in data.rounds] == [(1, ROUND_1), (2, ROUND_2)]
    assert data.rounds[1].note is not None and "segundo turno" in data.rounds[1].note
    assert data.next_round is not None
    assert (data.next_round.number, data.next_round.date) == (1, ROUND_1)
    assert data.days_until_next_round == 16
    assert data.offices == BALLOT_OFFICES
    assert data.notes, "curated notes for the voter are expected"
    assert data.calendar_source.title == (
        "Resolução TSE nº 23.760, de 2 de março de 2026 (Calendário Eleitoral)"
    )
    assert data.calendar_source.url.startswith("https://")
    assert data.calendar_source.verified_at == dt.date(2026, 9, 17)


def test_between_the_rounds_next_round_is_round_2(tmp_path: Path):
    core = unopened_core(tmp_path)
    answer = core.election_info(dt.date(2026, 10, 10))

    data = answer.data
    assert data is not None
    assert (data.next_round.number, data.next_round.date) == (2, ROUND_2)
    assert data.days_until_next_round == 15


def test_on_round_1_itself_next_round_is_still_round_1(tmp_path: Path):
    core = unopened_core(tmp_path)
    answer = core.election_info(ROUND_1)

    data = answer.data
    assert data is not None
    assert data.next_round.number == 1
    assert data.days_until_next_round == 0


def test_after_round_2_the_last_election_in_the_file_data_has_no_next_round(tmp_path: Path):
    core = unopened_core(tmp_path)
    answer = core.election_info(dt.date(2026, 10, 26))

    assert answer.not_found is None
    data = answer.data
    assert data is not None
    assert data.next_round is None
    assert data.days_until_next_round is None
    # The rest of the calendar still describes general-2026, never not_found.
    assert [(r.number, r.date) for r in data.rounds] == [(1, ROUND_1), (2, ROUND_2)]
    assert data.offices == BALLOT_OFFICES


def test_default_on_is_today_in_sao_paulo(tmp_path: Path):
    # tests/conftest.py's default clock is 2026-09-18 15:00 UTC, before round 1.
    core = unopened_core(tmp_path)
    answer = core.election_info()

    assert answer.data is not None
    assert answer.data.next_round is not None
    assert answer.data.next_round.number == 1


@pytest.mark.parametrize("on", ["not-a-date", "2026-13-40", 123, ""])
def test_invalid_on_is_invalid_query(tmp_path: Path, on):
    core = unopened_core(tmp_path)
    with pytest.raises(InvalidQuery, match="data inválida"):
        core.election_info(on)


def test_source_is_curated_and_never_stale(tmp_path: Path):
    core = unopened_core(tmp_path)
    answer = core.election_info(dt.date(2026, 9, 18))

    source = answer.source
    assert source.kind == "curated"
    assert source.calendar_source == (
        "Resolução TSE nº 23.760, de 2 de março de 2026 (Calendário Eleitoral)"
    )
    assert source.verified_at == dt.date(2026, 9, 17)
    assert source.license == "CC-BY"
    assert source.attribution == "Tribunal Superior Eleitoral - Portal de Dados Abertos"
    assert not hasattr(source, "stale")


def test_voting_hours_label(tmp_path: Path):
    core = unopened_core(tmp_path)
    answer = core.election_info(dt.date(2026, 9, 18))

    assert answer.data is not None
    assert answer.data.voting_hours.model_dump() == {
        "start": "08:00",
        "end": "17:00",
        "timezone": "America/Sao_Paulo",
        "label": "8h às 17h (horário de Brasília)",
    }
