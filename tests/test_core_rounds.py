"""The round-resolution table of codebase-design 3.4, one test per line (ticket #14).

Three indexes: the shared Acre index (rounds 1 and 2: sections in both, presidents 45 and
22 in both, president 13 in round 1 only, every other office in round 1 only), the variant
without round 2 at all (``acre_round_1_index_dir``) and, where the line needs it, an index
whose manifest carries no election (the monthly ``ATUAL`` file) or an election the calendar
no longer has as current. Three clocks: before round 1, between the rounds, after round 2.
"""

from __future__ import annotations

import copy
import datetime as dt
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from mcp import Client
from starlette.testclient import TestClient

from br_elections_mcp.app import build_app
from br_elections_mcp.core import Core, InvalidQuery
from br_elections_mcp.core.core import CANDIDATE_NOT_FOUND_BY_NUMBER_GUIDANCE
from br_elections_mcp.core.rounds import (
    candidate_not_in_round_warning,
    candidates_not_yet_published_warning,
    office_without_round_warning,
    places_no_data_warning,
    places_not_yet_published_warning,
)
from br_elections_mcp.domain import Office
from br_elections_mcp.index_store import LocalDirectoryIndexSource
from br_elections_mcp.mcp_server import create_mcp_server
from br_elections_mcp.pipeline.datasets import POLLING_PLACES_CURRENT
from tests.conftest import (
    AFTER_ROUND_2,
    BEFORE_ROUND_1,
    BETWEEN_ROUNDS,
    ELECTIONS_FILE,
    build_fixture_index,
    fixed_clock,
    open_core,
)

ROUND_1_DATE = dt.date(2026, 10, 4)
ROUND_2_DATE = dt.date(2026, 10, 25)

PRESIDENT_13 = 20000000001  # eliminated in round 1: row in round 1 only
PRESIDENT_45 = 20000000003  # in both rounds
GOVERNOR_45 = 10000000001  # Acre decided in round 1: governor rows in round 1 only
STATE_DEPUTY_22222_ON_BALLOT = 10000000012  # the substitute of the rejected 22222
STATE_DEPUTY_22222_REJECTED = 10000000013  # off the ballot, same number

# The exact PT-BR texts of the table, for rounds 2 and 1.
T2_WARNING = (
    "O TSE ainda não publicou os locais do 2º turno; este é o local do 1º turno. "
    "Confira de novo perto da data."
)
T7_WARNING = "Não há dados do 2º turno; este é o local do 1º turno."
C3_GOVERNOR_AC_WARNING = "Não há 2º turno para governador no AC; esta é a lista do 1º turno."
C3_FEDERAL_DEPUTY_WARNING = "Deputado federal não tem 2º turno; esta é a lista do 1º turno."
C4_WARNING = "O TSE ainda não publicou os candidatos do 2º turno; esta é a lista do 1º turno."
F3_WARNING = "Este candidato não disputa o 2º turno; esta é a ficha do 1º turno."
F4_GOVERNOR_AC_WARNING = "Não há 2º turno para governador no AC; esta é a ficha do 1º turno."
F5_WARNING = "O TSE ainda não publicou os candidatos do 2º turno; esta é a ficha do 1º turno."


def test_the_table_texts_are_the_ones_of_the_design_document():
    assert places_not_yet_published_warning(2, 1) == T2_WARNING
    assert places_no_data_warning(2, 1) == T7_WARNING
    assert office_without_round_warning(Office.GOVERNADOR, "AC", 2, 1, "lista") == (
        C3_GOVERNOR_AC_WARNING
    )
    assert office_without_round_warning(Office.DEPUTADO_FEDERAL, "AC", 2, 1, "lista") == (
        C3_FEDERAL_DEPUTY_WARNING
    )
    assert office_without_round_warning(Office.PRESIDENTE, "BR", 2, 1, "lista") == (
        "Não há 2º turno para presidente; esta é a lista do 1º turno."
    )
    assert office_without_round_warning(Office.SENADOR, "AC", 2, 1, "ficha") == (
        "Senador não tem 2º turno; esta é a ficha do 1º turno."
    )
    assert candidates_not_yet_published_warning(2, 1, "lista") == C4_WARNING
    assert candidate_not_in_round_warning(2, 1) == F3_WARNING


# Fixtures: the three indexes and a core factory with the clock.


@pytest.fixture(scope="module")
def atual_index_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Both rounds, but the polling places come from the monthly ``ATUAL`` file: the
    manifest has no election, so no election ever coincides."""
    directory = tmp_path_factory.mktemp("acre-atual-index")
    build_fixture_index(directory, dataset=POLLING_PLACES_CURRENT)
    return directory


@pytest.fixture(scope="module")
def elections_with_2028(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The calendar with ``municipal-2028`` after ``general-2026``."""
    document = yaml.safe_load(ELECTIONS_FILE.read_text(encoding="utf-8"))
    following = copy.deepcopy(document["elections"][0])
    following.update(
        id="municipal-2028",
        name="Eleições Municipais 2028",
        year=2028,
        kind="municipal",
        rounds=[
            {"number": 1, "date": dt.date(2028, 10, 1)},
            {"number": 2, "date": dt.date(2028, 10, 29)},
        ],
    )
    following.pop("divulgacandcontas_election_id", None)
    document["elections"].append(following)
    path = tmp_path_factory.mktemp("calendar") / "elections.yaml"
    path.write_text(yaml.safe_dump(document, allow_unicode=True), encoding="utf-8")
    return path


class CoreFactory:
    def __init__(self) -> None:
        self._open: list[Core] = []

    def __call__(
        self, index_dir: Path, at: dt.datetime, elections_file: Path = ELECTIONS_FILE
    ) -> Core:
        core = Core(LocalDirectoryIndexSource(index_dir), elections_file, clock=fixed_clock(at))
        core.open_index()
        self._open.append(core)
        return core

    def close(self) -> None:
        for core in self._open:
            core.close()


@pytest.fixture
def core_at() -> Iterator[CoreFactory]:
    factory = CoreFactory()
    yield factory
    factory.close()


def round_warnings(answer) -> list[str]:
    """The warnings of the round table: the staleness warning of codebase-design 9 is a
    separate concern (the fixture data is weeks old at the later clocks)."""
    return [w for w in answer.warnings if not w.startswith("Os dados do TSE")]


def assert_election(answer, round_number: int | None) -> None:
    """``election`` is the coincident current election with the answered round, or null."""
    if round_number is None:
        assert answer.election is None
        return
    assert answer.election is not None
    assert answer.election.id == "general-2026"
    assert answer.election.round.number == round_number
    assert answer.election.round.date == {1: ROUND_1_DATE, 2: ROUND_2_DATE}[round_number]


# T1-T7: find_polling_place and search_polling_places.


def place_answers(core: Core, **kwargs):
    """The two place queries of the table, with ``total > 0`` checked for the list."""
    section = core.find_polling_place("AC", 9, 422, **kwargs)
    assert section.data is not None
    places = core.search_polling_places("AC", "Rio Branco", **kwargs)
    assert places.data is not None
    assert places.data.total > 0
    return section, places


def test_t1_round_absent_and_the_next_round_published_answers_the_next_round(
    acre_index_dir: Path, core_at: CoreFactory
):
    for at, expected in ((BEFORE_ROUND_1, 1), (BETWEEN_ROUNDS, 2)):
        for answer in place_answers(core_at(acre_index_dir, at)):
            assert answer.data.round == expected
            assert round_warnings(answer) == []
            assert_election(answer, expected)


def test_t2_round_absent_and_the_next_round_not_yet_published_answers_the_highest_with_warning(
    acre_round_1_index_dir: Path, core_at: CoreFactory
):
    # Between the rounds the next round is round 2, and the TSE has not published it yet.
    for answer in place_answers(core_at(acre_round_1_index_dir, BETWEEN_ROUNDS)):
        assert answer.data.round == 1
        assert round_warnings(answer) == [T2_WARNING]
        assert_election(answer, 1)


def test_t3_round_explicit_and_published_answers_that_round(
    acre_index_dir: Path, core_at: CoreFactory
):
    for at in (BEFORE_ROUND_1, BETWEEN_ROUNDS):
        for requested in (1, 2):
            for answer in place_answers(core_at(acre_index_dir, at), round=requested):
                assert answer.data.round == requested
                assert round_warnings(answer) == []
                assert_election(answer, requested)


def test_t4_round_explicit_and_not_yet_published_answers_the_highest_with_warning(
    acre_round_1_index_dir: Path, core_at: CoreFactory
):
    for at in (BEFORE_ROUND_1, BETWEEN_ROUNDS):
        for answer in place_answers(core_at(acre_round_1_index_dir, at), round=2):
            assert answer.data.round == 1
            assert round_warnings(answer) == [T2_WARNING]
            assert_election(answer, 1)


def test_t5_round_absent_without_a_coincident_election_answers_the_highest_published(
    acre_index_dir: Path, acre_round_1_index_dir: Path, core_at: CoreFactory
):
    # After the last round there is no current election: the highest published round,
    # round 2 while the index carries both rounds, with election null and no warning.
    for index_dir, expected in ((acre_index_dir, 2), (acre_round_1_index_dir, 1)):
        for answer in place_answers(core_at(index_dir, AFTER_ROUND_2)):
            assert answer.data.round == expected
            assert round_warnings(answer) == []
            assert_election(answer, None)


def test_t5_election_is_null_with_the_monthly_atual_manifest_and_a_future_election(
    atual_index_dir: Path, core_at: CoreFactory
):
    # general-2026 is current before round 1, but the index has no election to coincide.
    for answer in place_answers(core_at(atual_index_dir, BEFORE_ROUND_1)):
        assert answer.data.round == 2
        assert round_warnings(answer) == []
        assert_election(answer, None)
        assert answer.source.dataset == POLLING_PLACES_CURRENT.title


def test_t5_election_is_null_with_a_finished_election_while_the_calendar_has_the_next_one(
    acre_index_dir: Path, elections_with_2028: Path, core_at: CoreFactory
):
    # In 2027-06 the current election is municipal-2028; the index is still the 2026 one
    # with both rounds: 2026 does not coincide with 2028, so T5 answers round 2, never T1.
    at = dt.datetime(2027, 6, 1, 15, 0, tzinfo=dt.UTC)
    for answer in place_answers(core_at(acre_index_dir, at, elections_with_2028)):
        assert answer.data.round == 2
        assert round_warnings(answer) == []
        assert_election(answer, None)


def test_t6_round_explicit_and_published_without_a_coincident_election_answers_it(
    acre_index_dir: Path, core_at: CoreFactory
):
    for requested in (1, 2):
        for answer in place_answers(core_at(acre_index_dir, AFTER_ROUND_2), round=requested):
            assert answer.data.round == requested
            assert round_warnings(answer) == []
            assert_election(answer, None)


def test_t7_round_explicit_and_not_published_without_a_coincident_election_warns_no_data(
    acre_round_1_index_dir: Path, core_at: CoreFactory
):
    for answer in place_answers(core_at(acre_round_1_index_dir, AFTER_ROUND_2), round=2):
        assert answer.data.round == 1
        assert round_warnings(answer) == [T7_WARNING]
        assert_election(answer, None)


def test_the_round_is_never_a_not_found_for_a_section_that_exists(
    acre_round_1_index_dir: Path, core_at: CoreFactory
):
    core = core_at(acre_round_1_index_dir, AFTER_ROUND_2)
    assert core.find_polling_place("AC", 9, 422, round=2).not_found is None
    # not_found only when the key exists in no round.
    assert core.find_polling_place("AC", 9, 99999, round=2).not_found is not None


# C1-C4: list_candidates.


def candidates(core: Core, uf: str, office: str, **kwargs):
    answer = core.list_candidates(uf, office, **kwargs)
    assert answer.data is not None
    assert answer.data.total > 0
    return answer


def test_c1_round_absent_answers_the_highest_round_of_the_office(
    acre_index_dir: Path, core_at: CoreFactory
):
    for at, election_filled in ((BEFORE_ROUND_1, True), (BETWEEN_ROUNDS, True)):
        core = core_at(acre_index_dir, at)
        president = candidates(core, "BR", "presidente")
        assert president.data.round == 2
        assert [c.number for c in president.data.candidates] == [22, 45]
        assert round_warnings(president) == []
        assert_election(president, 2 if election_filled else None)

        deputies = candidates(core, "AC", "deputado_federal")
        assert deputies.data.round == 1
        assert round_warnings(deputies) == []
        assert_election(deputies, 1)


def test_c1_after_the_election_the_list_answers_with_election_null(
    acre_index_dir: Path, core_at: CoreFactory
):
    answer = candidates(core_at(acre_index_dir, AFTER_ROUND_2), "BR", "presidente")
    assert answer.data.round == 2
    assert round_warnings(answer) == []
    assert_election(answer, None)


def test_c2_round_explicit_and_a_round_of_the_office_answers_it(
    acre_index_dir: Path, core_at: CoreFactory
):
    core = core_at(acre_index_dir, BETWEEN_ROUNDS)
    for requested, numbers in ((1, [13, 22, 45]), (2, [22, 45])):
        answer = candidates(core, "BR", "presidente", round=requested)
        assert answer.data.round == requested
        assert [c.number for c in answer.data.candidates] == numbers
        assert round_warnings(answer) == []
        assert_election(answer, requested)


def test_c3_round_explicit_and_published_but_not_of_the_office_warns_and_answers_the_highest(
    acre_index_dir: Path, core_at: CoreFactory
):
    for at, election_round in ((BEFORE_ROUND_1, 1), (BETWEEN_ROUNDS, 1), (AFTER_ROUND_2, None)):
        core = core_at(acre_index_dir, at)
        governor = candidates(core, "AC", "governador", round=2)
        assert governor.data.round == 1
        assert round_warnings(governor) == [C3_GOVERNOR_AC_WARNING]
        assert_election(governor, election_round)

        deputies = candidates(core, "AC", "deputado_federal", round=2)
        assert deputies.data.round == 1
        assert round_warnings(deputies) == [C3_FEDERAL_DEPUTY_WARNING]
        assert_election(deputies, election_round)


def test_c4_round_explicit_and_not_yet_published_warns_and_answers_the_highest(
    acre_round_1_index_dir: Path, core_at: CoreFactory
):
    for at, election_round in ((BEFORE_ROUND_1, 1), (BETWEEN_ROUNDS, 1), (AFTER_ROUND_2, None)):
        core = core_at(acre_round_1_index_dir, at)
        for uf, office in (("BR", "presidente"), ("AC", "governador")):
            answer = candidates(core, uf, office, round=2)
            assert answer.data.round == 1
            assert round_warnings(answer) == [C4_WARNING]
            assert_election(answer, election_round)


# F1-F5: get_candidate.


def profile(core: Core, *args, **kwargs):
    answer = core.get_candidate(*args, **kwargs)
    assert answer.not_found is None
    assert answer.data is not None
    return answer


def test_f1_round_absent_answers_the_highest_round_of_the_candidacy(
    acre_index_dir: Path, core_at: CoreFactory
):
    for at, election_filled in ((BEFORE_ROUND_1, True), (BETWEEN_ROUNDS, True)):
        core = core_at(acre_index_dir, at)
        eliminated = profile(core, PRESIDENT_13)
        assert eliminated.data.candidate.round == 1
        assert round_warnings(eliminated) == []
        assert_election(eliminated, 1 if election_filled else None)

        by_trio = profile(core, uf="BR", office="presidente", number=13)
        assert by_trio.model_dump() == eliminated.model_dump()

        in_round_2 = profile(core, PRESIDENT_45)
        assert in_round_2.data.candidate.round == 2
        assert round_warnings(in_round_2) == []
        assert_election(in_round_2, 2)


def test_f2_round_explicit_and_a_round_of_the_candidacy_answers_it(
    acre_index_dir: Path, core_at: CoreFactory
):
    core = core_at(acre_index_dir, BETWEEN_ROUNDS)
    for requested in (1, 2):
        answer = profile(core, PRESIDENT_45, round=requested)
        assert answer.data.candidate.round == requested
        assert round_warnings(answer) == []
        assert_election(answer, requested)
    answer = profile(core, uf="BR", office="presidente", number=45, round=1)
    assert answer.data.candidate.round == 1
    assert round_warnings(answer) == []


def test_f3_round_of_the_office_but_not_of_the_candidacy_warns_and_answers_the_candidacy_round(
    acre_index_dir: Path, core_at: CoreFactory
):
    for at, election_round in ((BEFORE_ROUND_1, 1), (BETWEEN_ROUNDS, 1), (AFTER_ROUND_2, None)):
        core = core_at(acre_index_dir, at)
        by_sq = profile(core, PRESIDENT_13, round=2)
        assert by_sq.data.candidate.round == 1
        assert by_sq.data.candidate.sq_candidato == PRESIDENT_13
        assert round_warnings(by_sq) == [F3_WARNING]
        assert_election(by_sq, election_round)

        by_trio = profile(core, uf="BR", office="presidente", number=13, round=2)
        assert by_trio.model_dump() == by_sq.model_dump()


def test_f3_the_same_profile_is_answered_with_and_without_round(
    acre_index_dir: Path, core_at: CoreFactory
):
    core = core_at(acre_index_dir, BETWEEN_ROUNDS)
    without = profile(core, PRESIDENT_13)
    with_round_2 = profile(core, PRESIDENT_13, round=2)
    assert with_round_2.data == without.data
    assert with_round_2.election == without.election


def test_f4_round_published_but_not_of_the_office_warns_and_answers_the_candidacy_round(
    acre_index_dir: Path, core_at: CoreFactory
):
    for at, election_round in ((BEFORE_ROUND_1, 1), (BETWEEN_ROUNDS, 1), (AFTER_ROUND_2, None)):
        core = core_at(acre_index_dir, at)
        by_sq = profile(core, GOVERNOR_45, round=2)
        assert by_sq.data.candidate.round == 1
        assert round_warnings(by_sq) == [F4_GOVERNOR_AC_WARNING]
        assert_election(by_sq, election_round)

        by_trio = profile(core, uf="AC", office="governador", number=45, round=2)
        assert by_trio.model_dump() == by_sq.model_dump()

        deputy = profile(core, uf="AC", office="deputado_federal", number=4512, round=2)
        assert round_warnings(deputy) == [
            "Deputado federal não tem 2º turno; esta é a ficha do 1º turno."
        ]


def test_f5_round_not_yet_published_warns_and_answers_the_candidacy_round(
    acre_round_1_index_dir: Path, core_at: CoreFactory
):
    for at, election_round in ((BEFORE_ROUND_1, 1), (BETWEEN_ROUNDS, 1), (AFTER_ROUND_2, None)):
        core = core_at(acre_round_1_index_dir, at)
        for lookup in ((PRESIDENT_45,), (GOVERNOR_45,)):
            answer = profile(core, *lookup, round=2)
            assert answer.data.candidate.round == 1
            assert round_warnings(answer) == [F5_WARNING]
            assert_election(answer, election_round)
        by_trio = profile(core, uf="BR", office="presidente", number=45, round=2)
        assert round_warnings(by_trio) == [F5_WARNING]


# The trio: on-ballot candidacies only.


def test_the_trio_resolves_a_shared_number_to_the_on_ballot_substitute(core: Core):
    answer = profile(core, uf="AC", office="deputado_estadual", number=22222)
    assert answer.data.candidate.sq_candidato == STATE_DEPUTY_22222_ON_BALLOT
    assert answer.data.candidate.ballot_name == "MARCOS ROCHA"
    assert round_warnings(answer) == []
    rejected = profile(core, STATE_DEPUTY_22222_REJECTED)
    assert rejected.data.candidate.on_ballot is False
    assert rejected.data.candidate.adjudication_status == "INDEFERIDO"


def test_the_trio_is_not_found_when_nobody_with_the_number_is_on_the_ballot(core: Core):
    # Governor 22 renounced and nobody took the number: the set of candidacy rounds is empty.
    for requested in (None, 1, 2):
        answer = core.get_candidate(uf="AC", office="governador", number=22, round=requested)
        assert answer.data is None
        assert answer.not_found is not None
        assert answer.not_found.reason == "candidato_nao_encontrado"
        assert answer.not_found.guidance == CANDIDATE_NOT_FOUND_BY_NUMBER_GUIDANCE
        assert_election(answer, 1)


# The bound of `round`, in the core and through both adapters.


@pytest.mark.parametrize("requested", [0, 3, "-1", "x"])
def test_round_outside_the_calendar_rounds_is_invalid_query(core: Core, requested):
    with pytest.raises(InvalidQuery, match="turno inválido"):
        core.find_polling_place("AC", 9, 422, round=requested)
    with pytest.raises(InvalidQuery, match="turno inválido"):
        core.search_polling_places("AC", "Rio Branco", round=requested)
    with pytest.raises(InvalidQuery, match="turno inválido"):
        core.list_candidates("BR", "presidente", round=requested)
    with pytest.raises(InvalidQuery, match="turno inválido"):
        core.get_candidate(PRESIDENT_45, round=requested)


def test_round_outside_1_to_2_without_a_coincident_election_is_invalid_query(
    acre_index_dir: Path, atual_index_dir: Path, core_at: CoreFactory
):
    for core in (core_at(acre_index_dir, AFTER_ROUND_2), core_at(atual_index_dir, BEFORE_ROUND_1)):
        assert core.find_polling_place("AC", 9, 422, round=2).data is not None
        with pytest.raises(InvalidQuery, match="turno inválido"):
            core.find_polling_place("AC", 9, 422, round=3)
        with pytest.raises(InvalidQuery, match="turno inválido"):
            core.list_candidates("BR", "presidente", round=3)
        with pytest.raises(InvalidQuery, match="turno inválido"):
            core.get_candidate(PRESIDENT_45, round=3)


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/api/v1/polling-place", {"uf": "AC", "zone": "9", "section": "422", "round": "3"}),
        ("/api/v1/polling-places", {"uf": "AC", "municipality": "Rio Branco", "round": "3"}),
        ("/api/v1/candidates", {"uf": "BR", "office": "presidente", "round": "3"}),
        (f"/api/v1/candidates/{PRESIDENT_45}", {"round": "3"}),
        (
            "/api/v1/candidates/by-number",
            {"uf": "BR", "office": "presidente", "number": "45", "round": "3"},
        ),
    ],
)
def test_rest_answers_400_for_a_round_outside_the_calendar(
    acre_index_dir: Path, path: str, params: dict[str, str]
):
    core = Core(LocalDirectoryIndexSource(acre_index_dir), ELECTIONS_FILE, clock=fixed_clock())
    with TestClient(build_app(core), base_url="http://localhost") as client:
        response = client.get(path, params=params)
    assert response.status_code == 400
    assert "turno inválido" in response.json()["detail"]


def test_rest_passes_the_round_warning_through(acre_round_1_index_dir: Path):
    core = Core(
        LocalDirectoryIndexSource(acre_round_1_index_dir), ELECTIONS_FILE, clock=fixed_clock()
    )
    with TestClient(build_app(core), base_url="http://localhost") as client:
        response = client.get(
            "/api/v1/polling-place",
            params={"uf": "AC", "zone": "9", "section": "422", "round": "2"},
        )
    assert response.status_code == 200
    body = response.json()
    assert (body["data"]["round"], body["election"]["round"]["number"]) == (1, 1)
    assert body["warnings"] == [T2_WARNING]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("find_polling_place", {"uf": "AC", "zone": 9, "section": 422, "round": 3}),
        ("search_polling_places", {"uf": "AC", "municipality": "Rio Branco", "round": 3}),
        ("list_candidates", {"uf": "BR", "office": "presidente", "round": 3}),
        ("get_candidate", {"sq_candidato": PRESIDENT_45, "round": 3}),
    ],
)
async def test_mcp_answers_is_error_for_a_round_outside_the_calendar(
    core: Core, tool: str, arguments: dict
):
    async with Client(create_mcp_server(core)) as client:
        result = await client.call_tool(tool, arguments)
    assert result.is_error is True
    assert "turno inválido" in result.content[0].text
    assert result.structured_content is None


@pytest.mark.anyio
async def test_mcp_passes_the_round_warning_through_in_structured_content_and_text(
    acre_index_dir: Path,
):
    core = open_core(acre_index_dir, clock=fixed_clock(BETWEEN_ROUNDS))
    try:
        async with Client(create_mcp_server(core)) as client:
            result = await client.call_tool(
                "get_candidate", {"sq_candidato": PRESIDENT_13, "round": 2}
            )
    finally:
        core.close()
    assert result.is_error is False
    assert result.structured_content["data"]["candidate"]["round"] == 1
    assert result.structured_content["warnings"] == [F3_WARNING]
    assert F3_WARNING in result.content[0].text
