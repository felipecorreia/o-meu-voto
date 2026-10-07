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
    CANDIDATE_ASSETS_2026,
    CANDIDATE_SOCIAL_LINKS_2026,
    CANDIDATES_2026,
    CANDIDATES_COMPLEMENTARY_2026,
    MUNICIPALITIES_TSE_IBGE,
    POLLING_PLACES_2026,
    POLLING_PLACES_CURRENT,
    Dataset,
    SourceFile,
)
from br_elections_mcp.pipeline.validate import (
    ValidationError,
    ValidationReport,
    _gate_count_stability,
    validate,
)
from tests.conftest import (
    ACRE_CANDIDATE_ASSETS,
    ACRE_CANDIDATES,
    ACRE_CANDIDATES_COMPLEMENTARY,
    ACRE_MUNICIPALITIES,
    ACRE_POLLING_PLACES,
    ACRE_SOCIAL_LINKS,
    AGGREGATED_ELSEWHERE,
    BUILT_AT,
    ELECTIONS_FILE,
    SHARED_PLACE_NUMBER,
    SUBSTITUTED_STILL_ON_BALLOT,
    build_fixture_index,
    with_fields,
    with_section_fields,
    without_round_2,
)


def run_validate(
    index_dir: Path,
    *,
    polling_places: Path = ACRE_POLLING_PLACES,
    municipalities: Path = ACRE_MUNICIPALITIES,
    candidates: Path = ACRE_CANDIDATES,
    candidates_complementary: Path = ACRE_CANDIDATES_COMPLEMENTARY,
    social_links: Path = ACRE_SOCIAL_LINKS,
    candidate_assets: Path = ACRE_CANDIDATE_ASSETS,
    dataset: Dataset = POLLING_PLACES_2026,
    output_dir: Path | None = None,
    elections_path: Path = ELECTIONS_FILE,
    previous_manifest: Manifest | None = None,
    previous_index_dir: Path | None = None,
    photo_public_domain: str | None = None,
) -> ValidationReport:
    return validate(
        SourceFile(dataset, polling_places),
        SourceFile(MUNICIPALITIES_TSE_IBGE, municipalities),
        SourceFile(CANDIDATES_2026, candidates),
        SourceFile(CANDIDATES_COMPLEMENTARY_2026, candidates_complementary),
        SourceFile(CANDIDATE_SOCIAL_LINKS_2026, social_links),
        SourceFile(CANDIDATE_ASSETS_2026, candidate_assets),
        index_dir,
        elections_path,
        output_dir or index_dir,
        previous_manifest=previous_manifest,
        previous_index_dir=previous_index_dir,
        photo_public_domain=photo_public_domain,
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
        "aggregated_section_main_is_principal",
        "blocked_status_inspection",
        "office_text_known",
        "ticket_single_head",
        "complementary_join_consistent",
        "round_2_scope",
        "municipality_crosswalk_scope",
        "photo_chain",
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


def test_csv_header_gate_covers_the_asset_file(acre_index_dir: Path, tmp_path: Path):
    broken = tmp_path / "bem_candidato_2026_BRASIL.csv"
    broken.write_bytes(
        ACRE_CANDIDATE_ASSETS.read_bytes().replace(b'"VR_BEM_CANDIDATO"', b'"VR_BEM"', 1)
    )
    with pytest.raises(ValidationError) as excinfo:
        run_validate(acre_index_dir, candidate_assets=broken, output_dir=tmp_path)
    gate = _gate(excinfo.value, "csv_header")
    assert gate.status == "fail"
    assert "candidate_assets lacks expected columns: ['VR_BEM_CANDIDATO']" in gate.message


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
        run_validate(
            acre_index_dir,
            output_dir=tmp_path,
            previous_manifest=previous,
            previous_index_dir=acre_index_dir,
        )
    assert "count_stability" in str(excinfo.value)


def test_count_stability_gate_accepts_new_round_with_stable_counts(
    acre_round_1_index_dir: Path, tmp_path: Path
):
    candidates = acre_round_1_index_dir / "round-1-sources" / ACRE_CANDIDATES.name
    index_dir = tmp_path / "index"
    build_fixture_index(index_dir, candidates=candidates)
    previous = read_manifest(acre_round_1_index_dir / MANIFEST_FILE_NAME)
    report = run_validate(
        index_dir,
        candidates=candidates,
        output_dir=tmp_path,
        previous_manifest=previous,
        previous_index_dir=acre_round_1_index_dir,
    )
    assert _gate(report, "count_stability").status == "pass"


def test_count_stability_uses_place_rounds_when_previous_candidates_have_two_rounds(
    acre_index_dir: Path, tmp_path: Path
):
    previous_dir = tmp_path / "previous"
    previous_dir.mkdir()
    places = without_round_2(ACRE_POLLING_PLACES, previous_dir)
    previous = build_fixture_index(previous_dir, polling_places=places)
    assert set(previous.election_dates) == {1, 2}
    report = run_validate(
        acre_index_dir,
        output_dir=tmp_path,
        previous_manifest=previous,
        previous_index_dir=previous_dir,
    )
    assert _gate(report, "count_stability").status == "pass"


def test_count_stability_gate_rejects_a_round_change_hidden_by_stable_total(
    acre_index_dir: Path, tmp_path: Path
):
    lines = ACRE_POLLING_PLACES.read_bytes().splitlines()
    rows = [line.split(b";") for line in lines]
    round_1_section = (b'"1"', b'"150"')
    round_2_section = (b'"2"', b'"150"')
    assert sum((row[5], row[10]) == round_1_section for row in rows[1:]) == 1
    moved = [row for row in rows[1:] if (row[5], row[10]) != round_1_section]
    extra = next(row.copy() for row in moved if (row[5], row[10]) == round_2_section)
    extra[10] = b'"999"'
    changed = tmp_path / "eleitorado_local_votacao_2026_AC.csv"
    changed.write_bytes(
        b"\n".join([lines[0], *(b";".join(row) for row in moved), b";".join(extra)]) + b"\n"
    )
    index_dir = tmp_path / "index"
    build_fixture_index(index_dir, polling_places=changed)
    previous = read_manifest(acre_index_dir / MANIFEST_FILE_NAME)
    with pytest.raises(ValidationError) as excinfo:
        run_validate(
            index_dir,
            polling_places=changed,
            output_dir=tmp_path,
            previous_manifest=previous,
            previous_index_dir=acre_index_dir,
        )
    assert "polling_sections" in _gate(excinfo.value, "count_stability").message


def test_count_stability_gate_skips_candidate_social_links():
    counts = {"candidates": 1_000, "candidate_social_links": 53218}
    previous = Manifest(
        index_built_at=BUILT_AT,
        datasets={},
        election_year=None,
        election_dates=None,
        counts={**counts, "candidate_social_links": 62901},
        index_sha256="0" * 64,
    )
    current = Manifest(
        index_built_at=BUILT_AT,
        datasets={},
        election_year=None,
        election_dates=None,
        counts=counts,
        index_sha256="0" * 64,
    )
    gate = _gate_count_stability(current, previous)
    assert gate.status == "pass"
    assert "candidate_social_links" in gate.message


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


def test_polling_place_identity_gate_accepts_a_name_change_across_rounds(
    acre_index_dir: Path, tmp_path: Path
):
    changed = with_fields(
        ACRE_POLLING_PLACES,
        tmp_path,
        ("NR_TURNO", "NR_ZONA", "NR_LOCAL_VOTACAO"),
        {("2", "9", "1000"): {"NM_LOCAL_VOTACAO": "OUTRO NOME"}},
    )
    report = run_validate(acre_index_dir, polling_places=changed, output_dir=tmp_path)
    assert _gate(report, "polling_place_identity").status == "pass"


@pytest.mark.parametrize(
    "patches",
    [SHARED_PLACE_NUMBER, AGGREGATED_ELSEWHERE],
    ids=["place-number-shared-across-municipalities", "aggregated-section-elsewhere"],
)
def test_real_tse_shapes_pass_every_gate(tmp_path: Path, patches):
    # Both shapes are in the real 2026 file (first real ingestion, 2026-09-24).
    polling_places = with_section_fields(ACRE_POLLING_PLACES, tmp_path, patches)
    index_dir = tmp_path / "index"
    build_fixture_index(index_dir, polling_places=polling_places)
    report = run_validate(index_dir, polling_places=polling_places, output_dir=tmp_path)
    assert report.ok, report.failed


def test_ticket_single_head_gate_passes_with_a_substituted_candidacy_still_flagged_on(
    tmp_path: Path,
):
    complementary = with_fields(
        ACRE_CANDIDATES_COMPLEMENTARY, tmp_path, ("SQ_CANDIDATO",), SUBSTITUTED_STILL_ON_BALLOT
    )
    index_dir = tmp_path / "index"
    build_fixture_index(index_dir, candidates_complementary=complementary)
    report = run_validate(index_dir, candidates_complementary=complementary, output_dir=tmp_path)
    assert _gate(report, "ticket_single_head").status == "pass"


def test_polling_place_identity_gate_fails_on_two_names_within_one_municipality(
    acre_index_dir: Path, tmp_path: Path
):
    # Section 9/150 (place 1050, COLÉGIO ACREANO) moved to place 1000 of the same municipality
    # without taking its name: two names for (AC, 9, 01392, 1000).
    broken = with_section_fields(
        ACRE_POLLING_PLACES, tmp_path, {("9", "150"): {"NR_LOCAL_VOTACAO": "1000"}}
    )
    with pytest.raises(ValidationError) as excinfo:
        run_validate(acre_index_dir, polling_places=broken, output_dir=tmp_path)
    assert "polling_place_identity" in str(excinfo.value)


@pytest.mark.parametrize(
    ("main_section", "problem"),
    [("999", "main section 999 missing"), ("424", "main section 424 is not a main section")],
    ids=["missing", "aggregated"],
)
def test_aggregated_section_main_is_principal_gate_fails(
    tmp_path: Path, main_section: str, problem: str
):
    # 9/424 aggregated to 999 (no such section) or to itself-aggregated 424 via 9/423.
    patched_section = "424" if main_section == "999" else "423"
    broken = with_section_fields(
        ACRE_POLLING_PLACES,
        tmp_path,
        {
            ("9", patched_section): {
                "DS_TIPO_SECAO_AGREGADA": "Agregada",
                "NR_SECAO_PRINCIPAL": main_section,
            }
        },
    )
    index_dir = tmp_path / "out"
    build_fixture_index(index_dir, polling_places=broken)
    with pytest.raises(ValidationError) as excinfo:
        run_validate(index_dir, polling_places=broken, output_dir=tmp_path)
    gate = _gate(excinfo.value, "aggregated_section_main_is_principal")
    assert gate.status == "fail"
    assert problem in gate.message


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
