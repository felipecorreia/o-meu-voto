"""Pipeline stage ``validate``: the gate between ``build`` and ``publish``.

Reads the raw CSVs ``build`` reads, the index ``build`` already wrote (``index.duckdb`` and
``manifest.json``), the curated calendar and, when there is one, the previously published
index pair for per-round counts; writes a validation report and raises loudly when any gate
fails, so a bad index is never published (docs/codebase-design.md, section 5;
docs/domain-model.md, section 7).

Every gate re-derives its invariant directly from the raw CSVs or the built index, independent of
whatever ``build`` already happens to enforce internally (a primary key, a hard-coded mapping):
this stage is the single, final, independently testable safety net.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
from collections import defaultdict
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import duckdb

from br_elections_mcp.domain import Office
from br_elections_mcp.elections import load_elections
from br_elections_mcp.index_schema import (
    CANDIDATE_ASSETS_CSV_COLUMNS,
    CANDIDATE_SOCIAL_LINKS_CSV_COLUMNS,
    CANDIDATES_COMPLEMENTARY_CSV_COLUMNS,
    CANDIDATES_CSV_COLUMNS,
    CSV_READ_OPTIONS,
    FORBIDDEN_COLUMNS,
    INDEX_FILE_NAME,
    MANIFEST_FILE_NAME,
    MUNICIPALITIES_CSV_COLUMNS,
    POLLING_PLACES_CSV_COLUMNS,
    Manifest,
    read_manifest,
)
from br_elections_mcp.pipeline.build import OFFICE_BY_DS_CARGO, office_key
from br_elections_mcp.pipeline.datasets import SourceFile
from br_elections_mcp.pipeline.photo_integrity import photo_problems

VALIDATION_REPORT_FILE = "validation_report.json"
VALIDATION_REPORT_VERSION = 1

COUNT_TOLERANCE = 0.05
"""A count more than this fraction away from the previous manifest fails ``count_stability``."""

COUNT_STABILITY_EXCLUDED_TABLES: dict[str, str] = {
    "candidate_social_links": (
        "count moves with our own normalize/cap/dedupe filtering (build.py), so it is not "
        "stability-checked; a truncated raw social-links source file alone would therefore not "
        "be caught here, an accepted risk because the candidates table still is and missing "
        "links are the least critical data"
    ),
}
"""Tables ``count_stability`` skips, each with a one-line reason; every other table still
enforces ``COUNT_TOLERANCE``."""

ROUND_2_OFFICES: frozenset[Office] = frozenset(
    {Office.PRESIDENTE, Office.VICE_PRESIDENTE, Office.GOVERNADOR, Office.VICE_GOVERNADOR}
)
_ROUND_2_TICKETS: tuple[tuple[Office, Office], ...] = (
    (Office.PRESIDENTE, Office.VICE_PRESIDENTE),
    (Office.GOVERNADOR, Office.VICE_GOVERNADOR),
)

GateStatus = Literal["pass", "fail", "skip"]


@dataclass(frozen=True, slots=True)
class GateResult:
    """The outcome of one gate: its name, status and a human-readable message."""

    name: str
    status: GateStatus
    message: str


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """What one run of ``validate`` did, as written to ``validation_report.json``."""

    validated_at: str
    gates: tuple[GateResult, ...]

    @property
    def ok(self) -> bool:
        return all(gate.status != "fail" for gate in self.gates)

    @property
    def failed(self) -> tuple[GateResult, ...]:
        return tuple(gate for gate in self.gates if gate.status == "fail")

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": VALIDATION_REPORT_VERSION,
            "validated_at": self.validated_at,
            "gates": [asdict(gate) for gate in self.gates],
        }

    def write(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n")

    @classmethod
    def read(cls, path: Path) -> ValidationReport:
        raw = json.loads(path.read_text())
        if raw.get("version") != VALIDATION_REPORT_VERSION:
            raise ValueError(
                f"{path}: unsupported validation report version {raw.get('version')!r}"
            )
        return cls(
            validated_at=raw["validated_at"],
            gates=tuple(GateResult(**item) for item in raw["gates"]),
        )


class ValidationError(RuntimeError):
    """At least one gate failed; ``report`` has every gate's outcome."""

    def __init__(self, report: ValidationReport) -> None:
        failed = "; ".join(f"{gate.name}: {gate.message}" for gate in report.failed)
        super().__init__(f"validation failed: {failed}")
        self.report = report


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def validate(
    polling_places: SourceFile,
    municipalities: SourceFile,
    candidates: SourceFile,
    candidates_complementary: SourceFile,
    social_links: SourceFile,
    candidate_assets: SourceFile,
    index_dir: Path,
    elections_path: Path,
    output_dir: Path,
    *,
    previous_manifest: Manifest | None = None,
    previous_index_dir: Path | None = None,
    photo_public_domain: str | None = None,
    now: Callable[[], dt.datetime] = _utcnow,
) -> ValidationReport:
    """Run every gate and write ``validation_report.json`` under ``output_dir``.

    Raises ``ValidationError`` after writing the report when any gate's status is
    ``"fail"``. Reads the built index at ``index_dir`` (``index.duckdb`` and
    ``manifest.json``, from ``build``) and the same raw CSVs ``build`` read.
    """
    manifest = read_manifest(index_dir / MANIFEST_FILE_NAME)
    conn = duckdb.connect(":memory:")
    try:
        headers = {
            "polling_places": _csv_header(conn, "raw_polling_places", polling_places.path),
            "municipalities": _csv_header(conn, "raw_municipalities", municipalities.path),
            "candidates": _csv_header(conn, "raw_candidates", candidates.path),
            "candidates_complementary": _csv_header(
                conn, "raw_candidates_complementary", candidates_complementary.path
            ),
            "candidate_social_links": _csv_header(conn, "raw_social_links", social_links.path),
            "candidate_assets": _csv_header(conn, "raw_candidate_assets", candidate_assets.path),
        }
        with_round = "NR_TURNO" in headers["candidates_complementary"]
        with contextlib.suppress(duckdb.Error):
            # A broken complementary file fails its own gates below by referencing this view.
            _create_complementary_view(conn, with_round=with_round)
        is_election_batch = (
            polling_places.dataset.election_file and candidates.dataset.election_file
        )
        gates = (
            _gate_csv_header(headers),
            _run("key_uniqueness", lambda: _gate_key_uniqueness(conn)),
            _run(
                "forbidden_columns_absent",
                lambda: _gate_forbidden_columns_absent(index_dir / INDEX_FILE_NAME),
            ),
            _run(
                "count_stability",
                lambda: _gate_count_stability(
                    manifest,
                    previous_manifest,
                    index_dir / INDEX_FILE_NAME,
                    previous_index_dir / INDEX_FILE_NAME if previous_index_dir else None,
                ),
            ),
            _run(
                "election_date_matches_calendar",
                lambda: _gate_election_date_matches_calendar(
                    manifest, elections_path, is_election_batch
                ),
            ),
            _run("polling_place_identity", lambda: _gate_polling_place_identity(conn)),
            _run(
                "aggregated_section_main_is_principal",
                lambda: _gate_aggregated_section_main_is_principal(index_dir / INDEX_FILE_NAME),
            ),
            _run("blocked_status_inspection", lambda: _gate_blocked_status_inspection(conn)),
            _run("office_text_known", lambda: _gate_office_text_known(conn)),
            _run(
                "ticket_single_head",
                lambda: _gate_ticket_single_head(conn, with_round=with_round),
            ),
            _run(
                "complementary_join_consistent",
                lambda: _gate_complementary_join_consistent(conn, with_round=with_round),
            ),
            _run("round_2_scope", lambda: _gate_round_2_scope(conn, with_round=with_round)),
            _run("municipality_crosswalk_scope", lambda: _gate_municipality_crosswalk_scope(conn)),
            _run(
                "photo_chain",
                lambda: _gate_photo_chain(index_dir / INDEX_FILE_NAME, photo_public_domain),
            ),
        )
    finally:
        conn.close()
    report = ValidationReport(validated_at=now().isoformat(), gates=gates)
    output_dir.mkdir(parents=True, exist_ok=True)
    report.write(output_dir / VALIDATION_REPORT_FILE)
    if not report.ok:
        raise ValidationError(report)
    return report


def _run(name: str, fn: Callable[[], GateResult]) -> GateResult:
    """Run one gate, turning a broken input (an unreadable column, a missing view) into a
    failed result named after the gate instead of crashing the whole run."""
    try:
        return fn()
    except duckdb.Error as exc:
        return GateResult(name, "fail", f"gate could not run: {exc}")


def _csv_header(conn: duckdb.DuckDBPyConnection, view: str, path: Path) -> list[str]:
    source = f"read_csv('{_sql_literal(str(path))}', {CSV_READ_OPTIONS})"
    conn.execute(f"CREATE OR REPLACE TEMP VIEW {view} AS SELECT * FROM {source}")
    return [column[0] for column in conn.execute(f"SELECT * FROM {view} LIMIT 0").description]


def _sql_literal(text: str) -> str:
    return text.replace("'", "''")


# Gate 1: every CSV carries at least the columns the build stage reads.


def _gate_csv_header(headers: dict[str, list[str]]) -> GateResult:
    expected: dict[str, tuple[str, ...]] = {
        "polling_places": POLLING_PLACES_CSV_COLUMNS,
        "municipalities": MUNICIPALITIES_CSV_COLUMNS,
        "candidates": CANDIDATES_CSV_COLUMNS,
        "candidates_complementary": CANDIDATES_COMPLEMENTARY_CSV_COLUMNS,
        "candidate_social_links": CANDIDATE_SOCIAL_LINKS_CSV_COLUMNS,
        "candidate_assets": CANDIDATE_ASSETS_CSV_COLUMNS,
    }
    problems = []
    for key, columns in expected.items():
        missing = [column for column in columns if column not in headers[key]]
        if missing:
            problems.append(f"{key} lacks expected columns: {missing}")
    if problems:
        return GateResult("csv_header", "fail", "; ".join(problems))
    return GateResult("csv_header", "pass", "every CSV has the expected columns")


# Gate 2: the identity keys of sections and candidates are unique.


def _gate_key_uniqueness(conn: duckdb.DuckDBPyConnection) -> GateResult:
    section_dupes = conn.execute(
        """
        SELECT upper(trim(SG_UF)), CAST(NR_ZONA AS INTEGER), CAST(NR_SECAO AS INTEGER),
               CAST(NR_TURNO AS INTEGER)
        FROM raw_polling_places
        GROUP BY 1, 2, 3, 4 HAVING count(*) > 1
        """
    ).fetchall()
    candidate_dupes = conn.execute(
        """
        SELECT CAST(SQ_CANDIDATO AS BIGINT), CAST(NR_TURNO AS INTEGER)
        FROM raw_candidates
        GROUP BY 1, 2 HAVING count(*) > 1
        """
    ).fetchall()
    problems = []
    if section_dupes:
        problems.append(
            f"polling section key (uf, zone, section, round) duplicated: {section_dupes}"
        )
    if candidate_dupes:
        problems.append(f"candidate key (sq_candidato, round) duplicated: {candidate_dupes}")
    if problems:
        return GateResult("key_uniqueness", "fail", "; ".join(problems))
    return GateResult("key_uniqueness", "pass", "every identity key is unique")


# Gate 3: none of the forbidden (personal-data) columns reached the built index.


def _gate_forbidden_columns_absent(index_path: Path) -> GateResult:
    conn = duckdb.connect(str(index_path), read_only=True)
    try:
        columns = {
            row[0]
            for row in conn.execute("SELECT column_name FROM information_schema.columns").fetchall()
        }
    finally:
        conn.close()
    present = sorted(FORBIDDEN_COLUMNS & columns)
    if present:
        return GateResult(
            "forbidden_columns_absent", "fail", f"forbidden columns present in the index: {present}"
        )
    return GateResult("forbidden_columns_absent", "pass", "no forbidden column reached the index")


# Gate 4: table counts stay within COUNT_TOLERANCE; compare place and section rounds
# individually when the previous index belongs to the same election.


def _gate_count_stability(
    manifest: Manifest,
    previous: Manifest | None,
    index_path: Path | None = None,
    previous_index_path: Path | None = None,
) -> GateResult:
    if previous is None:
        return GateResult("count_stability", "pass", "no previous manifest; first run")
    if (
        index_path is not None
        and previous_index_path is None
        and previous.election_year == manifest.election_year
        and previous.election_year is not None
        and any(table in previous.counts for table in ("polling_places", "polling_sections"))
    ):
        return GateResult(
            "count_stability", "fail", "previous index required for per-round count comparison"
        )
    problems = []
    for table, count in manifest.counts.items():
        if table in COUNT_STABILITY_EXCLUDED_TABLES:
            continue
        old = previous.counts.get(table)
        if old is None:
            continue
        if (
            table in {"polling_places", "polling_sections"}
            and index_path is not None
            and previous_index_path is not None
            and previous.election_year == manifest.election_year
            and previous.election_year is not None
        ):
            round_counts = _round_counts(index_path, table)
            previous_round_counts = _round_counts(previous_index_path, table)
            new_round_baseline = old / len(previous_round_counts) if previous_round_counts else 0
            for round_number in sorted(previous_round_counts.keys() | round_counts.keys()):
                round_count = round_counts.get(round_number, 0)
                baseline = previous_round_counts.get(round_number, new_round_baseline)
                change = _count_change(baseline, round_count)
                if change > COUNT_TOLERANCE:
                    problems.append(
                        f"{table} round {round_number}: {baseline:g} -> {round_count} "
                        f"({change:.1%})"
                    )
        else:
            change = _count_change(old, count)
            if change > COUNT_TOLERANCE:
                problems.append(f"{table}: {old} -> {count} ({change:.1%})")
    skipped_note = (
        f"; skipped {sorted(COUNT_STABILITY_EXCLUDED_TABLES)}"
        if COUNT_STABILITY_EXCLUDED_TABLES
        else ""
    )
    if problems:
        return GateResult(
            "count_stability",
            "fail",
            f"counts moved more than {COUNT_TOLERANCE:.0%} from the previous manifest: "
            + "; ".join(problems)
            + skipped_note,
        )
    return GateResult("count_stability", "pass", "every count is within tolerance" + skipped_note)


def _count_change(old: float, current: int) -> float:
    return 0.0 if old == current == 0 else (float("inf") if old == 0 else abs(current - old) / old)


def _round_counts(index_path: Path, table: str) -> dict[int, int]:
    conn = duckdb.connect(str(index_path), read_only=True)
    try:
        return dict(conn.execute(f"SELECT round, count(*) FROM {table} GROUP BY round").fetchall())
    finally:
        conn.close()


# Gate 5: DT_ELEICAO of the index matches the curated calendar (election files only).


def _gate_election_date_matches_calendar(
    manifest: Manifest, elections_path: Path, is_election_batch: bool
) -> GateResult:
    if not is_election_batch:
        return GateResult(
            "election_date_matches_calendar",
            "skip",
            "the monthly ATUAL file does not belong to a YAML election",
        )
    if manifest.election_year is None or manifest.election_dates is None:
        return GateResult(
            "election_date_matches_calendar",
            "fail",
            "the index datasets disagree with each other on the election",
        )
    elections = load_elections(elections_path)
    matching = [election for election in elections if election.year == manifest.election_year]
    if not matching:
        return GateResult(
            "election_date_matches_calendar",
            "fail",
            f"no election for year {manifest.election_year} in {elections_path}",
        )
    election = matching[0]
    problems = []
    for round_number, date in manifest.election_dates.items():
        try:
            expected = election.round(round_number).date
        except KeyError:
            problems.append(f"round {round_number} has no entry in {election.id}")
            continue
        if date != expected:
            problems.append(f"round {round_number}: index has {date}, calendar has {expected}")
    if problems:
        return GateResult("election_date_matches_calendar", "fail", "; ".join(problems))
    return GateResult(
        "election_date_matches_calendar", "pass", f"every round date matches {election.id}"
    )


# Gate 6: a polling place's identity (uf, zone, municipality, number, round) carries one name and
# address. The number alone is unique per municipality within a zone, not per zone: the real
# 2026 file has 12,212 (uf, zone, number) keys spanning more than one municipality.


def _gate_polling_place_identity(conn: duckdb.DuckDBPyConnection) -> GateResult:
    rows = conn.execute(
        """
        SELECT upper(trim(SG_UF)), CAST(NR_ZONA AS INTEGER), lpad(trim(CD_MUNICIPIO), 5, '0'),
               CAST(NR_LOCAL_VOTACAO AS INTEGER), CAST(NR_TURNO AS INTEGER)
        FROM raw_polling_places
        GROUP BY 1, 2, 3, 4, 5
        HAVING count(DISTINCT trim(NM_LOCAL_VOTACAO)) > 1 OR count(DISTINCT trim(DS_ENDERECO)) > 1
        """
    ).fetchall()
    if rows:
        return GateResult(
            "polling_place_identity",
            "fail",
            "place (uf, zone, municipality, number, round) with more than one name or "
            f"address: {rows}",
        )
    return GateResult(
        "polling_place_identity", "pass", "every polling place has one name and address"
    )


# Gate 7: an aggregated section's main section exists in the same zone and round and is a
# main section itself, so "where do I vote" can answer the main section's place. The main
# section is not always at the aggregated section's place: the real 2026 file has 1,996
# aggregated sections registered elsewhere, 1,807 of them at a place with no main section.


def _gate_aggregated_section_main_is_principal(index_path: Path) -> GateResult:
    conn = duckdb.connect(str(index_path), read_only=True)
    try:
        rows = conn.execute(
            """
            SELECT a.uf, a.zone, a.section, a.round, a.main_section, m.section_kind
            FROM polling_sections AS a
            LEFT JOIN polling_sections AS m
              ON a.uf = m.uf AND a.zone = m.zone AND a.round = m.round
              AND a.main_section = m.section
            WHERE a.main_section IS NOT NULL
              AND (m.section IS NULL OR m.section_kind != 'principal')
            ORDER BY 1, 2, 3, 4
            """
        ).fetchall()
    finally:
        conn.close()
    if rows:
        problems = [
            f"{uf} {zone}/{section} round {round_}: main section {main} "
            + ("missing" if kind is None else "is not a main section")
            for uf, zone, section, round_, main, kind in rows
        ]
        return GateResult("aggregated_section_main_is_principal", "fail", "; ".join(problems))
    return GateResult(
        "aggregated_section_main_is_principal",
        "pass",
        "every aggregated section points at a main section of its zone and round",
    )


# Gate 8: BLOQUEADO versus *_ORIGINAL is an assumption to inspect, never a hard rule.

_PLACE_STATUS_SQL = "lower(strip_accents(trim(DS_SITU_LOCAL_VOTACAO)))"
_NO_PLACE_CHANGE_SQL = """
    (try_cast(NR_LOCAL_VOTACAO_ORIGINAL AS INTEGER) IS NULL
        OR try_cast(NR_LOCAL_VOTACAO_ORIGINAL AS INTEGER)
            IN (-1, CAST(NR_LOCAL_VOTACAO AS INTEGER)))
"""


def _gate_blocked_status_inspection(conn: duckdb.DuckDBPyConnection) -> GateResult:
    blocked_without_change, changed_without_block = conn.execute(
        f"""
        SELECT
            count(*) FILTER (WHERE {_PLACE_STATUS_SQL} = 'bloqueado'
                AND {_NO_PLACE_CHANGE_SQL}),
            count(*) FILTER (WHERE {_PLACE_STATUS_SQL} != 'bloqueado'
                AND NOT {_NO_PLACE_CHANGE_SQL})
        FROM raw_polling_places
        """
    ).fetchone()
    message = (
        f"{blocked_without_change} row(s) BLOQUEADO without a place change, "
        f"{changed_without_block} row(s) with a place change but not BLOQUEADO "
        "(assumption under investigation, docs/domain-model.md section 7)"
    )
    return GateResult("blocked_status_inspection", "pass", message)


# Gate 9: every DS_CARGO text maps to a known office.


def _gate_office_text_known(conn: duckdb.DuckDBPyConnection) -> GateResult:
    texts = [
        row[0] for row in conn.execute("SELECT DISTINCT DS_CARGO FROM raw_candidates").fetchall()
    ]
    unknown = sorted({text for text in texts if office_key(text or "") not in OFFICE_BY_DS_CARGO})
    if unknown:
        return GateResult("office_text_known", "fail", f"unknown DS_CARGO texts: {unknown}")
    return GateResult("office_text_known", "pass", "every DS_CARGO text maps to a known office")


# Gate 10: an on-ballot ticket, derived by (round, uf, number) within a ticket-head office,
# has one head. Off-ballot rows never count: a rejected candidate replaced by a substitute
# with the same number is one on-ballot ticket (domain-model 3.5, codebase-design 3.4).


def _gate_ticket_single_head(conn: duckdb.DuckDBPyConnection, *, with_round: bool) -> GateResult:
    rows = conn.execute(
        f"""
        SELECT CAST(c.NR_TURNO AS INTEGER), upper(trim(c.SG_UF)),
               CAST(c.NR_CANDIDATO AS INTEGER), c.DS_CARGO
        FROM raw_candidates AS c
        JOIN validate_complementary AS x ON {_complementary_join_condition(with_round)}
        WHERE x.on_ballot
        """
    ).fetchall()
    groups: dict[tuple[int, str, int, Office], list[Office]] = defaultdict(list)
    for round_number, uf, number, ds_cargo in rows:
        office = OFFICE_BY_DS_CARGO.get(office_key(ds_cargo or ""))
        if office is None:
            continue  # reported by office_text_known
        groups[(round_number, uf, number, office.ticket_head)].append(office)
    bad = sorted(
        key
        for key, offices in groups.items()
        if sum(1 for office in offices if office == key[3]) != 1
    )
    if bad:
        return GateResult("ticket_single_head", "fail", f"tickets without exactly one head: {bad}")
    return GateResult("ticket_single_head", "pass", "every ticket has exactly one head")


# Gate 11: the complementary file joins cleanly, by (sq_candidato, round) or by sq_candidato alone.


def _create_complementary_view(conn: duckdb.DuckDBPyConnection, *, with_round: bool) -> None:
    round_column = ", CAST(NR_TURNO AS INTEGER) AS round" if with_round else ""
    conn.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW validate_complementary AS
        SELECT DISTINCT
            CAST(SQ_CANDIDATO AS BIGINT) AS sq_candidato{round_column},
            trim(DS_SITUACAO_JULGAMENTO) AS adjudication_status,
            CASE upper(strip_accents(trim(ST_CANDIDATO_INSERIDO_URNA)))
                WHEN 'S' THEN TRUE WHEN 'SIM' THEN TRUE
                WHEN 'N' THEN FALSE WHEN 'NAO' THEN FALSE
            END
            -- A substituted candidacy is off the ballot even when the TSE still flags it on.
            AND NOT EXISTS (
                SELECT 1 FROM raw_candidates_complementary AS s
                WHERE try_cast(s.SQ_SUBSTITUIDO AS BIGINT) = CAST(c.SQ_CANDIDATO AS BIGINT)
            ) AS on_ballot
        FROM raw_candidates_complementary AS c
        """
    )


def _complementary_join_condition(with_round: bool) -> str:
    condition = "x.sq_candidato = CAST(c.SQ_CANDIDATO AS BIGINT)"
    if with_round:
        condition += " AND x.round = CAST(c.NR_TURNO AS INTEGER)"
    return condition


def _gate_complementary_join_consistent(
    conn: duckdb.DuckDBPyConnection, *, with_round: bool
) -> GateResult:
    key = "sq_candidato, round" if with_round else "sq_candidato"
    conflicting = [
        row[0]
        for row in conn.execute(
            f"SELECT {key} FROM validate_complementary GROUP BY {key} HAVING count(*) > 1"
        ).fetchall()
    ]
    missing = [
        row[0]
        for row in conn.execute(
            f"""
            SELECT DISTINCT CAST(c.SQ_CANDIDATO AS BIGINT)
            FROM raw_candidates AS c
            LEFT JOIN validate_complementary AS x ON {_complementary_join_condition(with_round)}
            WHERE x.sq_candidato IS NULL
            """
        ).fetchall()
    ]
    problems = []
    if conflicting:
        problems.append(f"conflicting rows for the same key: {sorted(conflicting)}")
    if missing:
        problems.append(f"candidates without a complementary row: {sorted(missing)}")
    if problems:
        return GateResult("complementary_join_consistent", "fail", "; ".join(problems))
    return GateResult(
        "complementary_join_consistent", "pass", "the complementary file joins cleanly"
    )


# Gate 12: round-2 lines are restricted to the four offices, with complete tickets and two heads.


def _gate_round_2_scope(conn: duckdb.DuckDBPyConnection, *, with_round: bool) -> GateResult:
    rows = conn.execute(
        f"""
        SELECT upper(trim(c.SG_UF)), c.DS_CARGO, x.on_ballot
        FROM raw_candidates AS c
        LEFT JOIN validate_complementary AS x ON {_complementary_join_condition(with_round)}
        WHERE CAST(c.NR_TURNO AS INTEGER) = 2
        """
    ).fetchall()
    if not rows:
        return GateResult("round_2_scope", "pass", "no round-2 rows yet")

    offices_seen: set[tuple[str, Office]] = set()
    unknown: set[tuple[str, str]] = set()
    on_ballot_heads: dict[tuple[str, Office], int] = defaultdict(int)
    for uf, ds_cargo, on_ballot in rows:
        office = OFFICE_BY_DS_CARGO.get(office_key(ds_cargo or ""))
        if office is None:
            continue  # reported by office_text_known
        if office not in ROUND_2_OFFICES:
            unknown.add((uf, office.value))
            continue
        offices_seen.add((uf, office))
        if office == office.ticket_head and on_ballot:
            on_ballot_heads[(uf, office)] += 1

    problems = []
    if unknown:
        problems.append(f"round-2 rows outside the allowed offices: {sorted(unknown)}")
    ufs = {uf for uf, _ in offices_seen}
    for uf in ufs:
        for head, mate in _ROUND_2_TICKETS:
            has_head = (uf, head) in offices_seen
            has_mate = (uf, mate) in offices_seen
            if has_head != has_mate:
                problems.append(f"incomplete round-2 ticket in {uf}: {head.value} vs {mate.value}")
    for (uf, office), count in sorted(
        on_ballot_heads.items(), key=lambda item: (item[0][0], item[0][1])
    ):
        if count != 2:
            problems.append(
                f"{uf}/{office.value} round 2 has {count} on-ballot head(s), expected 2"
            )

    if problems:
        return GateResult("round_2_scope", "fail", "; ".join(problems))
    return GateResult(
        "round_2_scope", "pass", "round-2 rows are within scope with complete tickets"
    )


# Gate 13: a municipality missing from the crosswalk is abroad (uf = ZZ).


def _gate_municipality_crosswalk_scope(conn: duckdb.DuckDBPyConnection) -> GateResult:
    rows = conn.execute(
        """
        SELECT DISTINCT upper(trim(p.SG_UF)), lpad(trim(p.CD_MUNICIPIO), 5, '0')
        FROM raw_polling_places AS p
        LEFT JOIN raw_municipalities AS m
          ON lpad(trim(p.CD_MUNICIPIO), 5, '0') = lpad(trim(m.CD_MUNICIPIO_TSE), 5, '0')
        WHERE m.CD_MUNICIPIO_TSE IS NULL AND upper(trim(p.SG_UF)) != 'ZZ'
        """
    ).fetchall()
    if rows:
        return GateResult(
            "municipality_crosswalk_scope",
            "fail",
            f"municipalities outside the crosswalk with uf != ZZ: {rows}",
        )
    return GateResult(
        "municipality_crosswalk_scope",
        "pass",
        "every municipality missing from the crosswalk is abroad",
    )


def _gate_photo_chain(index_path: Path, public_domain: str | None = None) -> GateResult:
    """Every mirrored photo's URL carries the SHA-256 the index records for it (ADR 0013)."""
    problems = photo_problems(index_path, public_domain)
    if problems:
        return GateResult("photo_chain", "fail", "; ".join(problems))
    return GateResult(
        "photo_chain", "pass", "every photo_url carries its recorded photo_sha256 (or none is set)"
    )
