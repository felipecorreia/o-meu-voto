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
    CANDIDATE_ASSETS_2026,
    CANDIDATE_SOCIAL_LINKS_2026,
    CANDIDATES_2026,
    CANDIDATES_COMPLEMENTARY_2026,
    POLLING_PLACES_2026,
    POLLING_PLACES_CURRENT,
)
from tests.conftest import (
    ACRE_CANDIDATE_ASSETS,
    ACRE_CANDIDATES,
    ACRE_CANDIDATES_COMPLEMENTARY,
    ACRE_POLLING_PLACES,
    AGGREGATED_ELSEWHERE,
    BUILT_AT,
    SHARED_PLACE_NUMBER,
    SUBSTITUTED_STILL_ON_BALLOT,
    build_fixture_index,
    open_core,
    with_fields,
    with_section_fields,
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
        # Five candidacies declared assets; the sixth SQ_CANDIDATO of the file is not a
        # candidacy of the candidates file and is dropped.
        "candidate_assets": 5,
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


def test_a_place_with_no_main_section_in_its_round_is_not_a_polling_place(tmp_path: Path):
    # Real TSE data (2026-09-24): 1,233 of 95,601 places carry only aggregated sections.
    # Section 9/424 (aggregated, main 422) moved to place 1099 leaves place 1099 with no ballot
    # box: its section stays in polling_sections, but the place is not in polling_places.
    polling_places = with_section_fields(ACRE_POLLING_PLACES, tmp_path, AGGREGATED_ELSEWHERE)
    manifest = build_fixture_index(tmp_path / "index", polling_places=polling_places)

    conn = duckdb.connect(str(tmp_path / "index" / INDEX_FILE_NAME), read_only=True)
    try:
        places = conn.execute("SELECT count(*) FROM polling_places WHERE number = 1099").fetchone()
        sections = conn.execute(
            "SELECT round, section_kind, main_section, place_number FROM polling_sections "
            "WHERE zone = 9 AND section = 424 ORDER BY round"
        ).fetchall()
        without_main = conn.execute(
            """
            SELECT count(*) FROM polling_places AS p
            WHERE NOT EXISTS (
                SELECT 1 FROM polling_sections AS s
                WHERE s.uf = p.uf AND s.zone = p.zone AND s.round = p.round
                  AND s.municipality_tse_code = p.municipality_tse_code
                  AND s.place_number = p.number AND s.section_kind = 'principal'
            )
            """
        ).fetchone()
    finally:
        conn.close()
    assert places == (0,)
    assert sections == [(1, "agregada", 422, 1099), (2, "agregada", 422, 1099)]
    assert without_main == (0,)
    assert manifest.counts["polling_places"] == 12
    assert manifest.counts["polling_sections"] == 20


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
        ("01120", 1200203, "Cruzeiro do Sul", "AC", "CRUZEIRO DO SUL"),
        ("01392", 1200401, "Rio Branco", "AC", "RIO BRANCO"),
        ("01481", 1200807, "Porto Acre", "AC", "PORTO ACRE"),
        ("01503", 1200609, "Porto Walter", "AC", "PORTO WALTER"),
        # Abroad: missing from the crosswalk, so the name the TSE prints and no IBGE code.
        ("30015", None, "Colônia", "ZZ", "COLONIA"),
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


def test_a_place_number_shared_by_two_municipalities_of_a_zone_is_two_places(tmp_path: Path):
    polling_places = with_section_fields(ACRE_POLLING_PLACES, tmp_path, SHARED_PLACE_NUMBER)
    build_fixture_index(tmp_path / "out", polling_places=polling_places)
    conn = duckdb.connect(str(tmp_path / "out" / INDEX_FILE_NAME), read_only=True)
    try:
        rows = conn.execute(
            """
            SELECT municipality_tse_code, name, section_count FROM polling_places
            WHERE uf = 'AC' AND zone = 9 AND number = 1000 AND round = 1
            ORDER BY municipality_tse_code
            """
        ).fetchall()
    finally:
        conn.close()
    assert rows == [
        ("01120", "Escola Estadual Flodoardo Cabral", 1),
        ("01392", "IEPTEC - Antigo Instituto Federal do Acre - IFAC - Baixada", 3),
    ]


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
    assert governor["name"] == "José Antônio dos Santos"
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


def test_vote_destination_and_the_asset_declaration_flag_come_from_the_complementary_file(
    acre_index_dir: Path,
):
    rejected_on_ballot = _candidate(acre_index_dir, 10000000003)
    assert rejected_on_ballot["vote_destination"] == "Anulado sub judice"
    assert rejected_on_ballot["declares_assets"] is True
    assert _candidate(acre_index_dir, 10000000001)["vote_destination"] == "Válido"
    assert _candidate(acre_index_dir, 10000000005)["vote_destination"] is None  # #NULO
    assert _candidate(acre_index_dir, 10000000010)["declares_assets"] is False  # N
    assert _candidate(acre_index_dir, 20000000005)["declares_assets"] is None  # Não divulgável


def test_declared_assets_are_one_total_per_candidacy_without_any_item_text(acre_index_dir):
    conn = duckdb.connect(str(acre_index_dir / INDEX_FILE_NAME), read_only=True)
    try:
        rows = conn.execute(
            "SELECT sq_candidato, total, item_count FROM candidate_assets ORDER BY 1"
        ).fetchall()
        columns = {row[0] for row in conn.execute("DESCRIBE candidate_assets").fetchall()}
    finally:
        conn.close()
    assert [(sq, float(total), count) for sq, total, count in rows] == [
        (10000000001, 1216500.0, 3),
        # A negative item (a loan to a third party) is summed as declared.
        (10000000003, 115000.0, 2),
        (10000000009, 12000.5, 1),
        (20000000001, 4775651.0, 1),
        (20000000003, 8186556.0, 1),
    ]
    assert columns == {"sq_candidato", "total", "item_count"}


def test_manifest_cites_the_asset_file(acre_index_dir: Path):
    assets = read_manifest(acre_index_dir / MANIFEST_FILE_NAME).datasets["candidate_assets"]
    assert assets.dataset == CANDIDATE_ASSETS_2026.title
    assert assets.dataset_url == CANDIDATE_ASSETS_2026.dataset_url
    assert assets.file == "bem_candidato_2026_BRASIL.csv"
    assert assets.generated_at == dt.datetime(2026, 9, 18, 22, 31, 7, tzinfo=SAO_PAULO)


def test_unparseable_asset_value_fails_loudly(tmp_path: Path):
    broken = tmp_path / "bem_candidato_2026_BRASIL.csv"
    broken.write_bytes(ACRE_CANDIDATE_ASSETS.read_bytes().replace(b'"450000,00"', b'"450.000,00"'))
    with pytest.raises(BuildError, match=r"450\.000,00"):
        build_fixture_index(tmp_path / "out", candidate_assets=broken)
    assert not (tmp_path / "out" / INDEX_FILE_NAME).exists()


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


def test_a_substituted_candidacy_is_off_the_ballot_even_when_the_tse_flags_it_on(
    tmp_path: Path,
):
    # Real TSE data (2026-09-24): of 282 substituted candidacies, 280 come with
    # ST_CANDIDATO_INSERIDO_URNA = NÃO and 2 still with SIM, one of them next to its
    # substitute with the same number (SP deputado federal 3660), which broke the ticket check.
    complementary = with_fields(
        ACRE_CANDIDATES_COMPLEMENTARY, tmp_path, ("SQ_CANDIDATO",), SUBSTITUTED_STILL_ON_BALLOT
    )
    index_dir = tmp_path / "out"
    build_fixture_index(index_dir, candidates_complementary=complementary)

    assert _candidate(index_dir, 10000000013)["on_ballot"] is False
    assert _candidate(index_dir, 10000000012)["on_ballot"] is True
    core = open_core(index_dir)
    try:
        answer = core.get_candidate(uf="AC", office="deputado_estadual", number=22222)
    finally:
        core.close()
    assert answer.data is not None
    assert answer.data.candidate.sq_candidato == 10000000012


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
