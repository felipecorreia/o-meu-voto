"""The ``build`` stage by file in, file out."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
import pytest

from br_elections_mcp.index_schema import (
    INDEX_FILE_NAME,
    MANIFEST_FILE_NAME,
    TABLES,
    read_manifest,
)
from br_elections_mcp.pipeline.build import BuildError, apply_photo_urls
from br_elections_mcp.pipeline.datasets import (
    CANDIDATE_SOCIAL_LINKS_2026,
    CANDIDATES_2026,
    CANDIDATES_COMPLEMENTARY_2026,
    POLLING_PLACES_2026,
    POLLING_PLACES_CURRENT,
)
from tests.conftest import (
    ACRE_CANDIDATES,
    ACRE_CANDIDATES_COMPLEMENTARY,
    ACRE_POLLING_PLACES,
    BUILT_AT,
    build_fixture_index,
    open_core,
)

SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def test_build_writes_index_and_manifest_from_the_acre_fixtures(acre_index_dir: Path):
    assert (acre_index_dir / INDEX_FILE_NAME).is_file()
    assert not (acre_index_dir / f"{INDEX_FILE_NAME}.tmp").exists()
    manifest = read_manifest(acre_index_dir / MANIFEST_FILE_NAME)

    assert manifest.index_built_at == BUILT_AT
    # Sections and places count once per round (rounds 1 and 2); the candidates are the 16
    # round-1 candidacies plus president 22 with vice, the rejected state deputy 22222 and
    # the round-2 rows of presidents 45 and 22 with their vices (tests/fixtures/README.md).
    assert manifest.counts == {
        "municipalities": 5,
        "polling_places": 12,
        "polling_sections": 20,
        "candidates": 23,
        "candidate_social_links": 4,
    }
    assert manifest.election_year == 2026
    assert manifest.election_dates == {1: dt.date(2026, 10, 4), 2: dt.date(2026, 10, 25)}
    assert len(manifest.index_sha256) == 64

    places = manifest.datasets["polling_places"]
    assert places.dataset == POLLING_PLACES_2026.title
    assert places.dataset_url == POLLING_PLACES_2026.dataset_url
    assert places.file == "eleitorado_local_votacao_2026_AC.csv"
    # DT_GERACAO + HH_GERACAO of the file, in America/Sao_Paulo
    assert places.generated_at == dt.datetime(2026, 9, 17, 6, 30, 20, tzinfo=SAO_PAULO)
    assert manifest.datasets["municipalities"].file == "municipio_tse_ibge.csv"


def test_index_has_exactly_the_shared_schema_tables(acre_index_dir: Path):
    conn = duckdb.connect(str(acre_index_dir / INDEX_FILE_NAME), read_only=True)
    try:
        tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
        assert tables == set(TABLES)
        counts = conn.execute(
            "SELECT number, section_count, accessible_section_count, voters "
            "FROM polling_places WHERE uf = 'AC' AND zone = 9 AND number = 1000"
        ).fetchone()
        assert counts == (1000, 3, 2, 260 + 251 + 38)
        no_coordinates = conn.execute(
            "SELECT latitude, longitude, phone, status FROM polling_places WHERE number = 1015"
        ).fetchone()
        assert no_coordinates == (None, None, None, "bloqueado")
    finally:
        conn.close()


def test_municipalities_come_from_the_crosswalk_with_the_abroad_fallback(acre_index_dir: Path):
    conn = duckdb.connect(str(acre_index_dir / INDEX_FILE_NAME), read_only=True)
    try:
        rows = conn.execute(
            "SELECT tse_code, ibge_code, name, uf, search_name FROM municipalities "
            "ORDER BY tse_code"
        ).fetchall()
    finally:
        conn.close()
    assert rows == [
        ("01120", 1200203, "CRUZEIRO DO SUL", "AC", "CRUZEIRO DO SUL"),
        ("01392", 1200401, "RIO BRANCO", "AC", "RIO BRANCO"),
        ("01481", 1200807, "PORTO ACRE", "AC", "PORTO ACRE"),
        ("01503", 1200609, "PORTO WALTER", "AC", "PORTO WALTER"),
        # Abroad: missing from the crosswalk, so the name the TSE prints and no IBGE code.
        ("30015", None, "COLÔNIA", "ZZ", "COLONIA"),
    ]


def test_monthly_snapshot_has_no_election_in_the_manifest(tmp_path: Path):
    manifest = build_fixture_index(tmp_path, dataset=POLLING_PLACES_CURRENT)
    assert manifest.election_year is None
    assert manifest.election_dates is None
    assert manifest.datasets["polling_places"].dataset == POLLING_PLACES_CURRENT.title


def test_missing_expected_column_fails_loudly(tmp_path: Path):
    broken = tmp_path / "eleitorado_local_votacao_2026_AC.csv"
    broken.write_bytes(ACRE_POLLING_PLACES.read_bytes().replace(b'"NR_SECAO"', b'"NR_SECAO_X"', 1))
    with pytest.raises(BuildError, match="NR_SECAO"):
        build_fixture_index(tmp_path / "out", polling_places=broken)
    assert not (tmp_path / "out" / INDEX_FILE_NAME).exists()


def test_unknown_accessibility_text_fails_loudly(tmp_path: Path):
    broken = tmp_path / "eleitorado_local_votacao_2026_AC.csv"
    broken.write_bytes(
        ACRE_POLLING_PLACES.read_bytes().replace(b'"COM ACESSIBILIDADE"', b'"TALVEZ"', 1)
    )
    with pytest.raises(BuildError, match="TALVEZ"):
        build_fixture_index(tmp_path / "out", polling_places=broken)


# Candidates (ticket #8): three files in, two tables out, nothing personal written.


def test_manifest_cites_the_three_candidate_files(acre_index_dir: Path):
    manifest = read_manifest(acre_index_dir / MANIFEST_FILE_NAME)

    candidates = manifest.datasets["candidates"]
    assert candidates.dataset == CANDIDATES_2026.title
    assert candidates.dataset_url == CANDIDATES_2026.dataset_url
    assert candidates.file == "consulta_cand_2026_BRASIL.csv"
    assert candidates.generated_at == dt.datetime(2026, 9, 18, 22, 30, 5, tzinfo=SAO_PAULO)
    complementary = manifest.datasets["candidates_complementary"]
    assert complementary.dataset == CANDIDATES_COMPLEMENTARY_2026.title
    assert complementary.file == "consulta_cand_complementar_2026_BRASIL.csv"
    assert complementary.generated_at == dt.datetime(2026, 9, 18, 22, 30, 11, tzinfo=SAO_PAULO)
    social = manifest.datasets["candidate_social_links"]
    assert social.dataset == CANDIDATE_SOCIAL_LINKS_2026.title
    assert social.file == "rede_social_candidato_2026_BRASIL.csv"
    # The candidate file carries the same election as the polling places: still one election.
    assert manifest.election_year == 2026
    assert manifest.election_dates == {1: dt.date(2026, 10, 4), 2: dt.date(2026, 10, 25)}


def _candidate(index_dir: Path, sq_candidato: int) -> dict:
    conn = duckdb.connect(str(index_dir / INDEX_FILE_NAME), read_only=True)
    try:
        cursor = conn.execute(
            "SELECT * FROM candidates WHERE sq_candidato = ? AND round = 1", [sq_candidato]
        )
        columns = [column[0] for column in cursor.description]
        row = cursor.fetchone()
    finally:
        conn.close()
    assert row is not None
    return dict(zip(columns, row, strict=True))


def test_candidate_row_maps_office_by_text_and_joins_the_complementary_file(acre_index_dir):
    governor = _candidate(acre_index_dir, 10000000003)
    assert governor["uf"] == "AC"
    assert governor["office"] == "governador"
    assert governor["number"] == 13
    assert governor["ballot_name"] == "ZÉ ANTÔNIO"
    assert governor["name"] == "JOSÉ ANTÔNIO DOS SANTOS"
    assert governor["social_name"] is None  # #NULO
    assert (governor["party_number"], governor["party_acronym"]) == (13, "PT")
    assert governor["party_name"] == "PARTIDO DOS TRABALHADORES"
    assert governor["nomination_kind"] == "federacao"
    assert governor["federation_acronym"] == "PT/PC do B/PV"
    assert governor["federation_name"] == "BRASIL DA ESPERANÇA"
    assert governor["federation_composition"] == "PT / PC do B / PV"
    assert governor["coalition_name"] is None  # #NULO
    assert governor["adjudication_status"] == "INDEFERIDO EM PRAZO RECURSAL OU COM RECURSO"
    assert governor["on_ballot"] is True
    assert governor["occupation"] == "PROFESSOR DE ENSINO SUPERIOR"
    assert governor["gender"] == "MASCULINO"
    assert governor["education"] == "SUPERIOR COMPLETO"
    assert governor["marital_status"] == "DIVORCIADO(A)"
    assert governor["race_color"] == "PRETA"
    assert governor["election_year"] == 2026
    assert governor["election_date"] == dt.date(2026, 10, 4)

    isolated = _candidate(acre_index_dir, 10000000005)
    assert isolated["nomination_kind"] == "partido_isolado"
    assert isolated["federation_acronym"] is None  # NR_FEDERACAO = -1, SG_FEDERACAO = #NULO
    assert isolated["coalition_name"] is None  # "PARTIDO ISOLADO"
    assert isolated["coalition_composition"] is None
    assert isolated["adjudication_status"] == "RENÚNCIA"
    assert isolated["on_ballot"] is False

    coalition = _candidate(acre_index_dir, 10000000001)
    assert coalition["nomination_kind"] == "coligacao"
    assert coalition["coalition_name"] == "ACRE PARA TODOS"
    assert coalition["coalition_composition"] == "PSDB, MDB"
    assert coalition["federation_acronym"] is None

    offices = {
        10000000002: "vice_governador",
        10000000006: "senador",
        10000000007: "primeiro_suplente",
        10000000008: "segundo_suplente",
        10000000009: "deputado_federal",
        10000000011: "deputado_estadual",
        20000000001: "presidente",
        20000000002: "vice_presidente",
    }
    for sq_candidato, office in offices.items():
        assert _candidate(acre_index_dir, sq_candidato)["office"] == office
    assert _candidate(acre_index_dir, 20000000001)["uf"] == "BR"


def test_social_links_are_loaded_by_candidate_and_order(acre_index_dir: Path):
    conn = duckdb.connect(str(acre_index_dir / INDEX_FILE_NAME), read_only=True)
    try:
        rows = conn.execute(
            "SELECT sq_candidato, position, url FROM candidate_social_links ORDER BY 1, 2"
        ).fetchall()
    finally:
        conn.close()
    assert rows == [
        (10000000001, 1, "https://www.instagram.com/mariadasilva45"),
        (10000000001, 2, "https://www.facebook.com/mariadasilva45"),
        (10000000003, 1, "https://www.instagram.com/zeantonio13"),
        (20000000001, 1, "https://www.instagram.com/fernando13"),
    ]


def test_unknown_ds_cargo_text_fails_loudly(tmp_path: Path):
    broken = tmp_path / "consulta_cand_2026_BRASIL.csv"
    broken.write_bytes(ACRE_CANDIDATES.read_bytes().replace(b'"SENADOR"', b'"SENADORA"', 1))
    with pytest.raises(BuildError, match=r"DS_CARGO.*SENADORA"):
        build_fixture_index(tmp_path / "out", candidates=broken)
    assert not (tmp_path / "out" / INDEX_FILE_NAME).exists()


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (b'"Partido Isolado"', b'"Chapa Avulsa"', "TP_AGREMIACAO"),
        (b'"MDB, PL"', b'"MDB, PL"', None),  # control: the file builds
    ],
)
def test_unknown_nomination_kind_fails_loudly(tmp_path: Path, old, new, message):
    broken = tmp_path / "consulta_cand_2026_BRASIL.csv"
    broken.write_bytes(ACRE_CANDIDATES.read_bytes().replace(old, new, 1))
    if message is None:
        build_fixture_index(tmp_path / "out", candidates=broken)
        return
    with pytest.raises(BuildError, match=message):
        build_fixture_index(tmp_path / "out", candidates=broken)


def test_unknown_on_ballot_flag_fails_loudly(tmp_path: Path):
    broken = tmp_path / "consulta_cand_complementar_2026_BRASIL.csv"
    original = ACRE_CANDIDATES_COMPLEMENTARY.read_bytes()
    header, body = original.split(b"\n", 1)
    columns = header.decode("latin-1").split(";")
    position = columns.index('"ST_CANDIDATO_INSERIDO_URNA"')
    first, rest = body.split(b"\n", 1)
    fields = first.decode("latin-1").split(";")
    fields[position] = '"TALVEZ"'
    broken.write_bytes(header + b"\n" + ";".join(fields).encode("latin-1") + b"\n" + rest)
    with pytest.raises(BuildError, match=r"ST_CANDIDATO_INSERIDO_URNA.*TALVEZ"):
        build_fixture_index(tmp_path / "out", candidates_complementary=broken)


def test_candidate_without_a_complementary_row_fails_loudly(tmp_path: Path):
    header, body = ACRE_CANDIDATES_COMPLEMENTARY.read_bytes().split(b"\n", 1)
    lines = body.split(b"\n")
    lines = [line for line in lines if b'"10000000011"' not in line]
    incomplete = tmp_path / "consulta_cand_complementar_2026_BRASIL.csv"
    incomplete.write_bytes(header + b"\n" + b"\n".join(lines))
    with pytest.raises(BuildError, match="10000000011"):
        build_fixture_index(tmp_path / "out", candidates_complementary=incomplete)


def _duplicate_row(original: bytes, sq_candidato: bytes, new_sq_candidato: bytes) -> bytes:
    """Append a copy of the row of ``sq_candidato`` under ``new_sq_candidato``."""
    header, body = original.split(b"\n", 1)
    row = next(line for line in body.split(b"\n") if b'"' + sq_candidato + b'"' in line)
    copy = row.replace(b'"' + sq_candidato + b'"', b'"' + new_sq_candidato + b'"')
    return header + b"\n" + body.rstrip(b"\n") + b"\n" + copy + b"\n"


def test_two_on_ballot_heads_with_the_same_number_fail_the_ticket_check(tmp_path: Path):
    # A second on-ballot governor 45 in AC: the number would no longer identify the ticket.
    candidates = tmp_path / "consulta_cand_2026_BRASIL.csv"
    candidates.write_bytes(
        _duplicate_row(ACRE_CANDIDATES.read_bytes(), b"10000000001", b"10000000099")
    )
    complementary = tmp_path / "consulta_cand_complementar_2026_BRASIL.csv"
    complementary.write_bytes(
        _duplicate_row(ACRE_CANDIDATES_COMPLEMENTARY.read_bytes(), b"10000000001", b"10000000099")
    )
    with pytest.raises(BuildError, match=r"exactly one head.*round 1 AC governador 45: 2 heads"):
        build_fixture_index(
            tmp_path / "out", candidates=candidates, candidates_complementary=complementary
        )
    assert not (tmp_path / "out" / INDEX_FILE_NAME).exists()


def test_an_on_ballot_vice_without_a_head_fails_the_ticket_check(tmp_path: Path):
    # Governor 45 leaves the ballot while the vice 45 stays on it.
    header, body = ACRE_CANDIDATES_COMPLEMENTARY.read_bytes().split(b"\n", 1)
    columns = header.decode("latin-1").split(";")
    position = columns.index('"ST_CANDIDATO_INSERIDO_URNA"')
    lines = []
    for line in body.split(b"\n"):
        if b'"10000000001"' in line:
            fields = line.decode("latin-1").split(";")
            fields[position] = '"N"'
            line = ";".join(fields).encode("latin-1")
        lines.append(line)
    complementary = tmp_path / "consulta_cand_complementar_2026_BRASIL.csv"
    complementary.write_bytes(header + b"\n" + b"\n".join(lines))
    with pytest.raises(BuildError, match=r"round 1 AC governador 45: 0 heads"):
        build_fixture_index(tmp_path / "out", candidates_complementary=complementary)


def test_an_off_ballot_head_never_counts_for_the_ticket_check(acre_index_dir: Path):
    # Governor 22 is off the ballot in the fixture and has no vice: the build accepts it.
    conn = duckdb.connect(str(acre_index_dir / INDEX_FILE_NAME), read_only=True)
    try:
        row = conn.execute(
            "SELECT on_ballot FROM candidates WHERE sq_candidato = 10000000005"
        ).fetchone()
    finally:
        conn.close()
    assert row == (False,)


def _with_round_column(original: bytes, rounds: dict[bytes, list[tuple[bytes, bytes]]]) -> bytes:
    """Append NR_TURNO to the complementary file; ``rounds`` adds extra rows per sq_candidato
    as (round, DS_SITUACAO_JULGAMENTO) pairs, the original rows get round 1."""
    header, body = original.split(b"\n", 1)
    out = [header + b';"NR_TURNO"']
    for line in body.split(b"\n"):
        if not line:
            continue
        out.append(line + b';"1"')
        sq = line.split(b";")[4]
        for round_number, status in rounds.get(sq, []):
            extra = line.replace(b'"DEFERIDO"', b'"' + status + b'"')
            out.append(extra + b';"' + round_number + b'"')
    return b"\n".join(out) + b"\n"


def test_complementary_with_nr_turno_is_joined_by_candidate_and_round(tmp_path: Path):
    # A round-2 row for the president must not leak into the round-1 candidate.
    with_rounds = tmp_path / "consulta_cand_complementar_2026_BRASIL.csv"
    with_rounds.write_bytes(
        _with_round_column(
            ACRE_CANDIDATES_COMPLEMENTARY.read_bytes(),
            {
                b'"20000000001"': [(b"2", b"CASSADO")],
                # The candidacies with a round-2 row in the fixture need their round-2 join.
                b'"20000000003"': [(b"2", b"DEFERIDO")],
                b'"20000000004"': [(b"2", b"DEFERIDO")],
                b'"20000000005"': [(b"2", b"DEFERIDO")],
                b'"20000000006"': [(b"2", b"DEFERIDO")],
            },
        )
    )
    build_fixture_index(tmp_path / "out", candidates_complementary=with_rounds)
    assert _candidate(tmp_path / "out", 20000000001)["adjudication_status"] == "DEFERIDO"


def test_complementary_without_nr_turno_with_conflicting_duplicates_fails_loudly(tmp_path: Path):
    original = ACRE_CANDIDATES_COMPLEMENTARY.read_bytes()
    header, body = original.split(b"\n", 1)
    first = body.split(b"\n", 1)[0]
    conflicting = first.replace(b'"DEFERIDO"', b'"CASSADO"')
    assert conflicting != first
    duplicated = tmp_path / "consulta_cand_complementar_2026_BRASIL.csv"
    duplicated.write_bytes(header + b"\n" + body + conflicting + b"\n")
    with pytest.raises(BuildError, match="SQ_CANDIDATO"):
        build_fixture_index(tmp_path / "out", candidates_complementary=duplicated)


def test_complementary_without_nr_turno_with_exact_duplicates_is_deduplicated(tmp_path: Path):
    original = ACRE_CANDIDATES_COMPLEMENTARY.read_bytes()
    header, body = original.split(b"\n", 1)
    first = body.split(b"\n", 1)[0]
    duplicated = tmp_path / "consulta_cand_complementar_2026_BRASIL.csv"
    duplicated.write_bytes(header + b"\n" + body + first + b"\n")
    manifest = build_fixture_index(tmp_path / "out", candidates_complementary=duplicated)
    assert manifest.counts["candidates"] == 23


def test_election_is_null_when_the_candidate_file_disagrees_with_the_polling_places(tmp_path):
    shifted = tmp_path / "consulta_cand_2026_BRASIL.csv"
    shifted.write_bytes(ACRE_CANDIDATES.read_bytes().replace(b"04/10/2026", b"11/10/2026"))
    manifest = build_fixture_index(tmp_path / "out", candidates=shifted)
    assert manifest.election_year is None
    assert manifest.election_dates is None


def test_missing_candidate_column_fails_loudly(tmp_path: Path):
    broken = tmp_path / "consulta_cand_2026_BRASIL.csv"
    broken.write_bytes(ACRE_CANDIDATES.read_bytes().replace(b'"DS_CARGO"', b'"DS_CARGO_X"', 1))
    with pytest.raises(BuildError, match="DS_CARGO"):
        build_fixture_index(tmp_path / "out", candidates=broken)


def test_a_freshly_built_index_has_no_photo_url(tmp_path: Path):
    build_fixture_index(tmp_path / "out")
    conn = duckdb.connect(str(tmp_path / "out" / INDEX_FILE_NAME), read_only=True)
    try:
        rows = conn.execute("SELECT DISTINCT photo_url FROM candidates").fetchall()
    finally:
        conn.close()
    assert rows == [(None,)]


def test_apply_photo_urls_sets_the_column_for_the_matching_candidacy_only(tmp_path: Path):
    build_fixture_index(tmp_path / "out")

    apply_photo_urls(
        tmp_path / "out", {10000000001: "https://fotos.example.org/FAC10000000001_div.jpg"}
    )

    conn = duckdb.connect(str(tmp_path / "out" / INDEX_FILE_NAME), read_only=True)
    try:
        rows = dict(conn.execute("SELECT sq_candidato, photo_url FROM candidates").fetchall())
    finally:
        conn.close()
    assert rows[10000000001] == "https://fotos.example.org/FAC10000000001_div.jpg"
    assert rows[10000000002] is None


def test_photo_url_reaches_list_candidates_and_get_candidate_through_a_real_core(tmp_path: Path):
    build_fixture_index(tmp_path / "out")
    apply_photo_urls(
        tmp_path / "out", {10000000001: "https://fotos.example.org/FAC10000000001_div.jpg"}
    )
    core = open_core(tmp_path / "out")
    try:
        list_answer = core.list_candidates("AC", "governador")
        by_number = {c.number: c for c in list_answer.data.candidates}
        assert by_number[45].photo_url == "https://fotos.example.org/FAC10000000001_div.jpg"
        assert by_number[13].photo_url is None

        profile_answer = core.get_candidate(sq_candidato=10000000001)
        assert (
            profile_answer.data.candidate.photo_url
            == "https://fotos.example.org/FAC10000000001_div.jpg"
        )
    finally:
        core.close()
