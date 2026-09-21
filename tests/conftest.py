"""Shared fixtures: the Acre index built by the pipeline's own ``build`` stage.

The ``acre/`` fixtures are the minimal index of codebase-design 3.3: sections in rounds 1
and 2, presidents 45 and 22 in both rounds, president 13 eliminated in round 1 (row in
round 1 only), every other office in round 1 only. ``acre_round_1_index_dir`` is the
variant without round 2 at all, derived here by dropping the ``NR_TURNO = 2`` rows.
"""

from __future__ import annotations

import csv
import datetime as dt
from collections.abc import Iterator
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from br_elections_mcp.core import Core
from br_elections_mcp.index_schema import Manifest
from br_elections_mcp.index_store import LocalDirectoryIndexSource
from br_elections_mcp.pipeline.build import build_index
from br_elections_mcp.pipeline.datasets import (
    CANDIDATE_SOCIAL_LINKS_2026,
    CANDIDATES_2026,
    CANDIDATES_COMPLEMENTARY_2026,
    MUNICIPALITIES_TSE_IBGE,
    POLLING_PLACES_2026,
    Dataset,
    SourceFile,
)

REPO = Path(__file__).resolve().parents[1]
ELECTIONS_FILE = REPO / "data" / "elections.yaml"
FIXTURES = Path(__file__).parent / "fixtures"
ACRE_POLLING_PLACES = FIXTURES / "acre" / "eleitorado_local_votacao_2026_AC.csv"
ACRE_MUNICIPALITIES = FIXTURES / "acre" / "municipio_tse_ibge.csv"
ACRE_LGPD_POLLING_PLACES = FIXTURES / "acre_lgpd" / "eleitorado_local_votacao_2026_AC.csv"
ACRE_CANDIDATES = FIXTURES / "acre" / "consulta_cand_2026_BRASIL.csv"
ACRE_CANDIDATES_COMPLEMENTARY = FIXTURES / "acre" / "consulta_cand_complementar_2026_BRASIL.csv"
ACRE_SOCIAL_LINKS = FIXTURES / "acre" / "rede_social_candidato_2026_BRASIL.csv"

BUILT_AT = dt.datetime(2026, 9, 18, 9, 5, 11, tzinfo=ZoneInfo("America/Sao_Paulo"))
# A day inside the 2026 campaign, before the first round: general-2026 is the current election.
NOW = dt.datetime(2026, 9, 18, 15, 0, tzinfo=dt.UTC)
# The three moments the round table distinguishes (codebase-design 3.4): before round 1
# (next round 1), between the rounds (next round 2) and after round 2 (no current election).
BEFORE_ROUND_1 = NOW
BETWEEN_ROUNDS = dt.datetime(2026, 10, 10, 15, 0, tzinfo=dt.UTC)
AFTER_ROUND_2 = dt.datetime(2026, 10, 26, 15, 0, tzinfo=dt.UTC)


def fixed_clock(instant: dt.datetime = NOW):
    return lambda: instant


CLOCK = fixed_clock()


def build_fixture_index(
    output_dir: Path,
    *,
    polling_places: Path = ACRE_POLLING_PLACES,
    municipalities: Path = ACRE_MUNICIPALITIES,
    candidates: Path = ACRE_CANDIDATES,
    candidates_complementary: Path = ACRE_CANDIDATES_COMPLEMENTARY,
    social_links: Path = ACRE_SOCIAL_LINKS,
    dataset: Dataset = POLLING_PLACES_2026,
    built_at: dt.datetime = BUILT_AT,
) -> Manifest:
    return build_index(
        SourceFile(dataset, polling_places),
        SourceFile(MUNICIPALITIES_TSE_IBGE, municipalities),
        SourceFile(CANDIDATES_2026, candidates),
        SourceFile(CANDIDATES_COMPLEMENTARY_2026, candidates_complementary),
        SourceFile(CANDIDATE_SOCIAL_LINKS_2026, social_links),
        output_dir,
        built_at=built_at,
    )


def without_round_2(source: Path, directory: Path) -> Path:
    """A copy of a TSE CSV fixture without its ``NR_TURNO = 2`` rows, same name and format."""
    with source.open(encoding="latin-1", newline="") as f:
        rows = list(csv.reader(f, delimiter=";", quotechar='"'))
    header, body = rows[0], rows[1:]
    round_column = header.index("NR_TURNO")
    target = directory / source.name
    with target.open("w", encoding="latin-1", newline="") as f:
        writer = csv.writer(
            f, delimiter=";", quotechar='"', quoting=csv.QUOTE_ALL, lineterminator="\n"
        )
        writer.writerow(header)
        writer.writerows(row for row in body if row[round_column] != "2")
    return target


def build_round_1_index(output_dir: Path, *, dataset: Dataset = POLLING_PLACES_2026) -> Manifest:
    """The variant of the fixture index without round 2 at all (codebase-design 3.3)."""
    sources = output_dir / "round-1-sources"
    sources.mkdir(parents=True, exist_ok=True)
    return build_fixture_index(
        output_dir,
        polling_places=without_round_2(ACRE_POLLING_PLACES, sources),
        candidates=without_round_2(ACRE_CANDIDATES, sources),
        dataset=dataset,
    )


def open_core(index_dir: Path, clock=CLOCK) -> Core:
    core = Core(LocalDirectoryIndexSource(index_dir), ELECTIONS_FILE, clock=clock)
    core.open_index()
    return core


@pytest.fixture(scope="session")
def acre_index_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("acre-index")
    build_fixture_index(directory)
    return directory


@pytest.fixture(scope="session")
def acre_round_1_index_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("acre-round-1-index")
    build_round_1_index(directory)
    return directory


@pytest.fixture
def core(acre_index_dir: Path) -> Iterator[Core]:
    core = open_core(acre_index_dir)
    yield core
    core.close()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
