import copy
import datetime as dt
from pathlib import Path

import pytest
import yaml

from br_elections_mcp.domain import ElectionKind, Office
from br_elections_mcp.elections import ElectionsSchemaError, load_elections, parse_elections

ELECTIONS_FILE = Path(__file__).resolve().parents[1] / "data" / "elections.yaml"


@pytest.fixture(scope="module")
def document() -> dict:
    with ELECTIONS_FILE.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def test_elections_file_loads_and_describes_the_2026_general_election():
    elections = load_elections(ELECTIONS_FILE)
    assert [e.id for e in elections] == ["general-2026"]
    e = elections[0]
    assert e.name == "Eleições Gerais 2026"
    assert e.year == 2026
    assert e.kind is ElectionKind.GENERAL
    assert [(r.number, r.date) for r in e.rounds] == [
        (1, dt.date(2026, 10, 4)),
        (2, dt.date(2026, 10, 25)),
    ]
    assert e.voting_hours.start == dt.time(8, 0)
    assert e.voting_hours.end == dt.time(17, 0)
    assert e.voting_hours.timezone == "America/Sao_Paulo"
    assert set(e.offices) == {
        Office.PRESIDENTE,
        Office.GOVERNADOR,
        Office.SENADOR,
        Office.DEPUTADO_FEDERAL,
        Office.DEPUTADO_ESTADUAL,
        Office.DEPUTADO_DISTRITAL,
    }
    assert e.calendar_source.url == (
        "https://www.tse.jus.br/legislacao/compilada/res/2026/"
        "resolucao-no-23-760-de-2-de-marco-de-2026"
    )
    assert e.calendar_source.verified_at == dt.date(2026, 9, 17)
    assert e.notes, "notes for the voter are expected"


def _mutate(document: dict, path: list, value) -> dict:
    doc = copy.deepcopy(document)
    node = doc
    for key in path[:-1]:
        node = node[key]
    if value is _DELETE:
        del node[path[-1]]
    else:
        node[path[-1]] = value
    return doc


_DELETE = object()


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (["schema_version"], 2, "schema_version"),
        (["elections"], [], "non-empty list"),
        (["elections", 0, "id"], _DELETE, "id must be a non-empty string"),
        (["elections", 0, "year"], "2026", "year must be an integer"),
        (["elections", 0, "kind"], "estadual", "is not one of"),
        (["elections", 0, "rounds", 0, "date"], "2026-10-04", "must be a date"),
        (["elections", 0, "rounds", 1, "number"], 1, r"numbered 1\.\.n"),
        (["elections", 0, "voting_hours", "start"], "8h", "time string"),
        (["elections", 0, "voting_hours", "timezone"], "Brasilia", "timezone"),
        (["elections", 0, "offices", 0], "vereador", "is not one of"),
        (["elections", 0, "offices", 0], "vice_presidente", "non-ballot"),
        (["elections", 0, "calendar_source", "url"], "http://tse.jus.br", "https"),
        (["elections", 0, "calendar_source", "verified_at"], _DELETE, "must be a date"),
        (["elections", 0, "notes"], "texto solto", "list of strings"),
        (["elections", 0, "turnos"], [], "unknown keys"),
    ],
)
def test_schema_violations_are_rejected(document, path, value, message):
    with pytest.raises(ElectionsSchemaError, match=message):
        parse_elections(_mutate(document, path, value))


def test_duplicate_election_ids_are_rejected(document):
    doc = copy.deepcopy(document)
    doc["elections"].append(copy.deepcopy(doc["elections"][0]))
    with pytest.raises(ElectionsSchemaError, match="unique"):
        parse_elections(doc)


def test_two_elections_in_the_same_year_are_rejected(document):
    doc = copy.deepcopy(document)
    second = copy.deepcopy(doc["elections"][0])
    second["id"] = "supplementary-2026"
    doc["elections"].append(second)
    with pytest.raises(ElectionsSchemaError, match="one election per year"):
        parse_elections(doc)


def test_elections_in_different_years_are_accepted(document):
    doc = copy.deepcopy(document)
    second = copy.deepcopy(doc["elections"][0])
    second["id"] = "municipal-2028"
    second["year"] = 2028
    second["kind"] = "municipal"
    second["rounds"] = [
        {"number": 1, "date": dt.date(2028, 10, 1)},
        {"number": 2, "date": dt.date(2028, 10, 29)},
    ]
    doc["elections"].append(second)
    assert [e.year for e in parse_elections(doc)] == [2026, 2028]
