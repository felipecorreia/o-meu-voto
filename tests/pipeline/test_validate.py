"""The ``validate`` stage: one fixture and one test per gate, plus the clean fixtures."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from br_elections_mcp.index_schema import (
    MANIFEST_FILE_NAME,
    Manifest,
    read_manifest,
    write_manifest,
)
from br_elections_mcp.pipeline.datasets import (
    CANDIDATE_SOCIAL_LINKS_2026,
    CANDIDATES_2026,
    CANDIDATES_COMPLEMENTARY_2026,
    MUNICIPALITIES_TSE_IBGE,
    POLLING_PLACES_2026,
    POLLING_PLACES_CURRENT,
    Dataset,
    SourceFile,
)
from br_elections_mcp.pipeline.validate import ValidationError, ValidationReport, validate
from tests.conftest import (
    ACRE_CANDIDATES,
    ACRE_CANDIDATES_COMPLEMENTARY,
    ACRE_MUNICIPALITIES,
    ACRE_POLLING_PLACES,
    ACRE_SOCIAL_LINKS,
    BUILT_AT,
    ELECTIONS_FILE,
    build_fixture_index,
)


def run_validate(
    index_dir: Path,
    *,
    polling_places: Path = ACRE_POLLING_PLACES,
    municipalities: Path = ACRE_MUNICIPALITIES,
    candidates: Path = ACRE_CANDIDATES,
    candidates_complementary: Path = ACRE_CANDIDATES_COMPLEMENTARY,
    social_links: Path = ACRE_SOCIAL_LINKS,
    dataset: Dataset = POLLING_PLACES_2026,
    output_dir: Path | None = None,
    elections_path: Path = ELECTIONS_FILE,
    previous_manifest: Manifest | None = None,
) -> ValidationReport:
    return validate(
        SourceFile(dataset, polling_places),
        SourceFile(MUNICIPALITIES_TSE_IBGE, municipalities),
        SourceFile(CANDIDATES_2026, candidates),
        SourceFile(CANDIDATES_COMPLEMENTARY_2026, candidates_complementary),
        SourceFile(CANDIDATE_SOCIAL_LINKS_2026, social_links),
        index_dir,
        elections_path,
        output_dir or index_dir,
        previous_manifest=previous_manifest,
    )


def _gate(report_or_error, name: str):
    report = (
        report_or_error.report if isinstance(report_or_error, ValidationError) else report_or_error
    )
    return next(gate for gate in report.gates if gate.name == name)


ROUND_1 = (5, b'"1"')
"""``NR_TURNO`` of the polling-places and candidates fixtures: the sections repeat in
round 2, so a patch of one section names the round too."""


def _patch_field(
    data: bytes,
    match_index: int,
    match_value: bytes,
    set_index: int,
    new_value: bytes,
    also_match: tuple[int, bytes] | None = None,
) -> bytes:
    """Replace field ``set_index`` in the exactly one data line whose field ``match_index``
    equals ``match_value`` (both 0-based, ``;``-separated, header excluded), and whose
    ``also_match`` field equals its value when given."""
    lines = data.split(b"\n")
    changed = 0
    out = []
    for i, line in enumerate(lines):
        if i > 0 and line:
            fields = line.split(b";")
            matches = len(fields) > match_index and fields[match_index] == match_value
            if matches and also_match is not None:
                matches = fields[also_match[0]] == also_match[1]
            if matches:
                fields[set_index] = new_value
                line = b";".join(fields)
                changed += 1
        out.append(line)
    assert changed == 1, f"expected exactly one match for {match_value!r}, got {changed}"
    return b"\n".join(out)


def _append_line_with_field(
    data: bytes, match_index: int, match_value: bytes, set_index: int, new_value: bytes
) -> bytes:
    """Append a copy of the one data line matching ``match_index``==``match_value``, with
    ``set_index`` changed to ``new_value``."""
    lines = [line for line in data.rstrip(b"\n").split(b"\n") if line]
    for line in lines:
        fields = line.split(b";")
        if fields[match_index] == match_value:
            fields[set_index] = new_value
            return b"\n".join([*lines, b";".join(fields)]) + b"\n"
    raise AssertionError(f"no line found with field {match_index} == {match_value!r}")


def test_clean_fixtures_pass_every_gate(acre_index_dir: Path, tmp_path: Path):
    report = run_validate(acre_index_dir, output_dir=tmp_path)
    assert report.ok
    assert (tmp_path / "validation_report.json").is_file()
    by_name = {gate.name for gate in report.gates}
    assert by_name == {
        "csv_header",
        "key_uniqueness",
        "forbidden_columns_absent",
        "count_stability",
        "election_date_matches_calendar",
        "polling_place_identity",
        "aggregated_section_same_place",
        "blocked_status_inspection",
        "office_text_known",
        "ticket_single_head",
        "complementary_join_consistent",
        "round_2_scope",
        "municipality_crosswalk_scope",
    }
    assert _gate(report, "count_stability").message == "no previous manifest; first run"
    assert (
        _gate(report, "round_2_scope").message
        == "round-2 rows are within scope with complete tickets"
    )
    assert _gate(report, "ticket_single_head").status == "pass"
    blocked = _gate(report, "blocked_status_inspection")
    assert blocked.status == "pass"
    assert "4 row(s) BLOQUEADO without a place change" in blocked.message
    assert "2 row(s) with a place change but not BLOQUEADO" in blocked.message


def test_validation_report_round_trips(acre_index_dir: Path, tmp_path: Path):
    report = run_validate(acre_index_dir, output_dir=tmp_path)
    reread = ValidationReport.read(tmp_path / "validation_report.json")
    assert reread == report


def test_csv_header_gate_fails_on_a_missing_expected_column(acre_index_dir: Path, tmp_path: Path):
    broken = tmp_path / "eleitorado_local_votacao_2026_AC.csv"
    broken.write_bytes(ACRE_POLLING_PLACES.read_bytes().replace(b'"NR_SECAO"', b'"NR_SECAO_X"', 1))
    with pytest.raises(ValidationError) as excinfo:
        run_validate(acre_index_dir, polling_places=broken, output_dir=tmp_path)
    assert "csv_header" in str(excinfo.value)
    assert _gate(excinfo.value, "csv_header").status == "fail"


def test_key_uniqueness_gate_fails_on_a_duplicated_section_key(
    acre_index_dir: Path, tmp_path: Path
):
    duplicated = tmp_path / "eleitorado_local_votacao_2026_AC.csv"
    original = ACRE_POLLING_PLACES.read_bytes()
    lines = [line for line in original.rstrip(b"\n").split(b"\n") if line]
    duplicated.write_bytes(b"\n".join([*lines, lines[1]]) + b"\n")
    with pytest.raises(ValidationError) as excinfo:
        run_validate(acre_index_dir, polling_places=duplicated, output_dir=tmp_path)
    assert "key_uniqueness" in str(excinfo.value)


def test_key_uniqueness_gate_fails_on_a_duplicated_candidate_key(
    acre_index_dir: Path, tmp_path: Path
):
    duplicated = tmp_path / "consulta_cand_2026_BRASIL.csv"
    original = ACRE_CANDIDATES.read_bytes()
    lines = [line for line in original.rstrip(b"\n").split(b"\n") if line]
    duplicated.write_bytes(b"\n".join([*lines, lines[1]]) + b"\n")
    with pytest.raises(ValidationError) as excinfo:
        run_validate(acre_index_dir, candidates=duplicated, output_dir=tmp_path)
    assert "key_uniqueness" in str(excinfo.value)


def test_forbidden_columns_absent_gate_fails_on_a_leaked_column(tmp_path: Path):
    index_dir = tmp_path / "broken-index"
    index_dir.mkdir()
    conn = duckdb.connect(str(index_dir / "index.duckdb"))
    conn.execute("CREATE TABLE candidates (sq_candidato BIGINT, NR_CPF_CANDIDATO VARCHAR)")
    conn.close()
    write_manifest(
        Manifest(
            index_built_at=BUILT_AT,
            datasets={},
            election_year=None,
            election_dates=None,
            counts={},
            index_sha256="0" * 64,
        ),
        index_dir / MANIFEST_FILE_NAME,
    )
    with pytest.raises(ValidationError) as excinfo:
        run_validate(index_dir)
    assert "forbidden_columns_absent" in str(excinfo.value)
    assert "NR_CPF_CANDIDATO" in _gate(excinfo.value, "forbidden_columns_absent").message


def test_count_stability_gate_fails_when_a_count_moves_more_than_five_percent(
    acre_index_dir: Path, tmp_path: Path
):
    current = read_manifest(acre_index_dir / MANIFEST_FILE_NAME)
    previous = current.model_copy(update={"counts": {**current.counts, "candidates": 1}})
    with pytest.raises(ValidationError) as excinfo:
        run_validate(acre_index_dir, output_dir=tmp_path, previous_manifest=previous)
    assert "count_stability" in str(excinfo.value)


def test_election_date_matches_calendar_gate_fails_on_a_date_mismatch(tmp_path: Path):
    shifted_places = tmp_path / "eleitorado_local_votacao_2026_AC.csv"
    shifted_places.write_bytes(
        ACRE_POLLING_PLACES.read_bytes().replace(b"04/10/2026", b"05/10/2026")
    )
    shifted_candidates = tmp_path / "consulta_cand_2026_BRASIL.csv"
    shifted_candidates.write_bytes(
        ACRE_CANDIDATES.read_bytes().replace(b"04/10/2026", b"05/10/2026")
    )
    index_dir = tmp_path / "out"
    build_fixture_index(index_dir, polling_places=shifted_places, candidates=shifted_candidates)
    with pytest.raises(ValidationError) as excinfo:
        run_validate(
            index_dir,
            polling_places=shifted_places,
            candidates=shifted_candidates,
            output_dir=tmp_path,
        )
    assert "election_date_matches_calendar" in str(excinfo.value)


def test_election_date_gate_is_skipped_for_the_monthly_atual_file(tmp_path: Path):
    index_dir = tmp_path / "out"
    build_fixture_index(index_dir, dataset=POLLING_PLACES_CURRENT)
    report = run_validate(index_dir, dataset=POLLING_PLACES_CURRENT, output_dir=tmp_path)
    gate = _gate(report, "election_date_matches_calendar")
    assert gate.status == "skip"


def test_polling_place_identity_gate_fails_on_an_inconsistent_name(
    acre_index_dir: Path, tmp_path: Path
):
    broken = tmp_path / "eleitorado_local_votacao_2026_AC.csv"
    broken.write_bytes(
        _patch_field(
            ACRE_POLLING_PLACES.read_bytes(),
            match_index=10,
            match_value=b'"423"',
            set_index=15,
            new_value=b'"OUTRO NOME"',
            also_match=ROUND_1,
        )
    )
    with pytest.raises(ValidationError) as excinfo:
        run_validate(acre_index_dir, polling_places=broken, output_dir=tmp_path)
    assert "polling_place_identity" in str(excinfo.value)


def test_polling_place_identity_gate_fails_on_an_inconsistency_across_rounds(
    acre_index_dir: Path, tmp_path: Path
):
    # Identity is (uf, zone, number), not (uf, zone, number, round): a name that changes
    # between round 1 and round 2 at the same place must still be caught.
    data = _patch_field(
        ACRE_POLLING_PLACES.read_bytes(),
        match_index=10,
        match_value=b'"422"',
        set_index=15,
        new_value=b'"OUTRO NOME"',
        also_match=(5, b'"2"'),
    )
    broken = tmp_path / "eleitorado_local_votacao_2026_AC.csv"
    broken.write_bytes(data)
    with pytest.raises(ValidationError) as excinfo:
        run_validate(acre_index_dir, polling_places=broken, output_dir=tmp_path)
    assert "polling_place_identity" in str(excinfo.value)


def test_aggregated_section_same_place_gate_fails_when_moved(tmp_path: Path):
    broken = tmp_path / "eleitorado_local_votacao_2026_AC.csv"
    broken.write_bytes(
        _patch_field(
            ACRE_POLLING_PLACES.read_bytes(),
            match_index=10,
            match_value=b'"424"',
            set_index=14,
            new_value=b'"9999"',
            also_match=ROUND_1,
        )
    )
    index_dir = tmp_path / "out"
    build_fixture_index(index_dir, polling_places=broken)
    with pytest.raises(ValidationError) as excinfo:
        run_validate(index_dir, polling_places=broken, output_dir=tmp_path)
    assert "aggregated_section_same_place" in str(excinfo.value)


def test_office_text_known_gate_fails_on_an_unmapped_ds_cargo(acre_index_dir: Path, tmp_path: Path):
    broken = tmp_path / "consulta_cand_2026_BRASIL.csv"
    broken.write_bytes(ACRE_CANDIDATES.read_bytes().replace(b'"SENADOR"', b'"SENADORA"', 1))
    with pytest.raises(ValidationError) as excinfo:
        run_validate(acre_index_dir, candidates=broken, output_dir=tmp_path)
    assert "office_text_known" in str(excinfo.value)


def test_ticket_single_head_gate_fails_with_two_heads_in_one_ticket(
    acre_index_dir: Path, tmp_path: Path
):
    broken = tmp_path / "consulta_cand_2026_BRASIL.csv"
    broken.write_bytes(
        _patch_field(
            ACRE_CANDIDATES.read_bytes(),
            match_index=15,
            match_value=b'"10000000004"',
            set_index=14,
            new_value=b'"GOVERNADOR"',
        )
    )
    with pytest.raises(ValidationError) as excinfo:
        run_validate(acre_index_dir, candidates=broken, output_dir=tmp_path)
    assert "ticket_single_head" in str(excinfo.value)


def test_complementary_join_consistent_gate_fails_on_a_missing_row(
    acre_index_dir: Path, tmp_path: Path
):
    header, body = ACRE_CANDIDATES_COMPLEMENTARY.read_bytes().split(b"\n", 1)
    lines = [line for line in body.split(b"\n") if b'"10000000011"' not in line]
    incomplete = tmp_path / "consulta_cand_complementar_2026_BRASIL.csv"
    incomplete.write_bytes(header + b"\n" + b"\n".join(lines))
    with pytest.raises(ValidationError) as excinfo:
        run_validate(acre_index_dir, candidates_complementary=incomplete, output_dir=tmp_path)
    assert "complementary_join_consistent" in str(excinfo.value)
    assert "10000000011" in _gate(excinfo.value, "complementary_join_consistent").message


def test_round_2_scope_gate_fails_on_an_office_outside_the_allowed_set(
    acre_index_dir: Path, tmp_path: Path
):
    broken = tmp_path / "consulta_cand_2026_BRASIL.csv"
    broken.write_bytes(
        _append_line_with_field(
            ACRE_CANDIDATES.read_bytes(),
            match_index=15,
            match_value=b'"10000000006"',  # senator, not a round-2 office
            set_index=5,
            new_value=b'"2"',
        )
    )
    with pytest.raises(ValidationError) as excinfo:
        run_validate(acre_index_dir, candidates=broken, output_dir=tmp_path)
    assert "round_2_scope" in str(excinfo.value)


def test_round_2_scope_gate_fails_on_an_incomplete_ticket(acre_index_dir: Path, tmp_path: Path):
    # Governor 13 goes to round 2 without its vice: the ticket is incomplete.
    broken = tmp_path / "consulta_cand_2026_BRASIL.csv"
    broken.write_bytes(
        _append_line_with_field(
            ACRE_CANDIDATES.read_bytes(),
            match_index=15,
            match_value=b'"10000000003"',  # governor 13, on_ballot
            set_index=5,
            new_value=b'"2"',
        )
    )
    with pytest.raises(ValidationError) as excinfo:
        run_validate(acre_index_dir, candidates=broken, output_dir=tmp_path)
    assert "round_2_scope" in str(excinfo.value)
    assert "incomplete round-2 ticket" in _gate(excinfo.value, "round_2_scope").message


def test_round_2_scope_gate_passes_with_two_complete_tickets(acre_index_dir: Path, tmp_path: Path):
    # Governors 45 and 13 both go to round 2, each with its vice: two complete tickets.
    complete = tmp_path / "consulta_cand_2026_BRASIL.csv"
    data = ACRE_CANDIDATES.read_bytes()
    for sq in (b'"10000000001"', b'"10000000002"', b'"10000000003"', b'"10000000004"'):
        data = _append_line_with_field(
            data, match_index=15, match_value=sq, set_index=5, new_value=b'"2"'
        )
    complete.write_bytes(data)
    report = run_validate(acre_index_dir, candidates=complete, output_dir=tmp_path)
    assert report.ok
    assert _gate(report, "round_2_scope").status == "pass"


def test_municipality_crosswalk_scope_gate_fails_on_a_non_zz_gap(
    acre_index_dir: Path, tmp_path: Path
):
    broken = tmp_path / "eleitorado_local_votacao_2026_AC.csv"
    broken.write_bytes(
        _patch_field(
            ACRE_POLLING_PLACES.read_bytes(),
            match_index=10,
            match_value=b'"20"',
            set_index=7,
            new_value=b'"09999"',
            also_match=ROUND_1,
        )
    )
    with pytest.raises(ValidationError) as excinfo:
        run_validate(acre_index_dir, polling_places=broken, output_dir=tmp_path)
    assert "municipality_crosswalk_scope" in str(excinfo.value)
