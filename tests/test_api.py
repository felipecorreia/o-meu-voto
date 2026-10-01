"""REST adapter through an ASGI test client over a real ``Core``."""

from __future__ import annotations

import csv
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from br_elections_mcp.api import create_api
from br_elections_mcp.app import (
    ENV_INDEX_BUCKET,
    ENV_INDEX_CACHE_DIR,
    ENV_INDEX_DIR,
    ENV_PORT,
    Settings,
    build_app,
    create_app,
)
from br_elections_mcp.core import (
    CandidateAnswer,
    CandidatesAnswer,
    Core,
    ElectionInfoAnswer,
    IndexUnavailable,
    MunicipalitiesAnswer,
    PollingPlaceAnswer,
    PollingPlacesAnswer,
)
from br_elections_mcp.index_store import GcsIndexSource, LocalDirectoryIndexSource
from tests.conftest import ACRE_POLLING_PLACES, ELECTIONS_FILE, build_fixture_index, fixed_clock


@pytest.fixture
def client(acre_index_dir: Path) -> Iterator[TestClient]:
    # The lifespan calls start()/close(); the Core is not opened here.
    core = Core(LocalDirectoryIndexSource(acre_index_dir), ELECTIONS_FILE, clock=fixed_clock())
    with TestClient(build_app(core), base_url="http://localhost") as client:
        yield client


def test_polling_place_returns_the_core_envelope(client: TestClient, core: Core):
    response = client.get(
        "/api/v1/polling-place", params={"uf": "ac", "zone": "009", "section": "0422"}
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"data", "not_found", "warnings", "election", "source"}
    assert body == core.find_polling_place("ac", "009", "0422").model_dump(mode="json")
    assert body["data"]["zone"] == 9
    assert body["data"]["section"] == 422
    assert body["election"]["id"] == "general-2026"
    assert body["source"]["file"] == "eleitorado_local_votacao_2026_AC.csv"


def test_not_found_is_200_with_the_envelope(client: TestClient):
    response = client.get("/api/v1/polling-place", params={"uf": "AC", "zone": 1, "section": 99999})
    assert response.status_code == 200
    body = response.json()
    assert body["data"] is None
    assert body["not_found"]["reason"] == "secao_nao_encontrada"
    assert body["source"]["license"] == "CC-BY"


def test_round_query_parameter_is_passed_through(client: TestClient):
    response = client.get(
        "/api/v1/polling-place", params={"uf": "AC", "zone": 9, "section": 422, "round": "1"}
    )
    assert response.status_code == 200
    assert response.json()["data"]["round"] == 1


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"uf": "XX", "zone": 9, "section": 422}, "UF desconhecida: 'XX'"),
        ({"uf": "AC", "zone": "nove", "section": 422}, "zona inválida: 'nove'"),
        ({"uf": "AC", "zone": 9, "section": 422, "round": 3}, "turno inválido"),
    ],
)
def test_invalid_query_is_400_with_the_core_message(client: TestClient, params, message):
    response = client.get("/api/v1/polling-place", params=params)
    assert response.status_code == 400
    assert message in response.json()["detail"]


def test_election_returns_the_core_envelope(client: TestClient, core: Core):
    response = client.get("/api/v1/election", params={"on": "2026-09-18"})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"data", "not_found", "warnings", "election", "source"}
    assert body == core.election_info("2026-09-18").model_dump(mode="json")
    assert body["data"]["id"] == "general-2026"
    assert body["data"]["name"] == "Eleições Gerais 2026"
    assert body["data"]["next_round"]["number"] == 1
    assert body["source"]["kind"] == "curated"
    assert body["not_found"] is None
    assert "stale" not in body["source"]


def test_election_default_on_is_today(client: TestClient):
    response = client.get("/api/v1/election")
    assert response.status_code == 200
    assert response.json()["data"] is not None


def test_election_invalid_on_is_400(client: TestClient):
    response = client.get("/api/v1/election", params={"on": "not-a-date"})
    assert response.status_code == 400
    assert "data inválida" in response.json()["detail"]


def test_openapi_is_served_under_the_prefix_and_generated_from_the_answer_model(
    client: TestClient,
):
    response = client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    document = response.json()
    assert {
        "/polling-place",
        "/election",
        "/candidates",
        "/candidates/by-number",
        "/candidates/{sq_candidato}",
        "/polling-places",
        "/municipalities",
    } <= set(document["paths"])
    assert document["servers"] == [{"url": "/api/v1"}]
    schemas = document["components"]["schemas"]
    for model in (
        PollingPlaceAnswer,
        ElectionInfoAnswer,
        CandidatesAnswer,
        CandidateAnswer,
        PollingPlacesAnswer,
        MunicipalitiesAnswer,
    ):
        assert set(model.model_json_schema()["properties"]) == set(
            schemas[model.__name__]["properties"]
        )
    assert not {"race_color", "marital_status", "education"} & set(
        schemas["CandidateListItem"]["properties"]
    )
    assert schemas["CandidateListItem"]["properties"]["gender"]["anyOf"] == [
        {"type": "string"},
        {"type": "null"},
    ]
    assert "gender" not in schemas["ComparedCandidate"]["properties"]
    assert {"gender", "race_color", "marital_status", "education"} <= set(
        schemas["CandidateProfile"]["properties"]
    )


def test_settings_from_env_reads_the_index_dir_and_defaults(
    monkeypatch: pytest.MonkeyPatch, acre_index_dir: Path
):
    monkeypatch.delenv(ENV_INDEX_DIR, raising=False)
    monkeypatch.delenv(ENV_INDEX_BUCKET, raising=False)
    with pytest.raises(RuntimeError, match=ENV_INDEX_DIR):
        Settings.from_env().build_index_source()

    monkeypatch.setenv(ENV_INDEX_DIR, str(acre_index_dir))
    monkeypatch.setenv(ENV_PORT, "8765")
    settings = Settings.from_env()
    assert settings.index_dir == acre_index_dir
    assert settings.elections_file == ELECTIONS_FILE
    assert (settings.host, settings.port) == ("127.0.0.1", 8765)
    assert settings.rate_limit is None

    with TestClient(create_app(), base_url="http://localhost") as client:
        response = client.get(
            "/api/v1/polling-place", params={"uf": "AC", "zone": 9, "section": 422}
        )
        assert response.status_code == 200
        assert client.get("/api/v1/docs").status_code == 200


def test_settings_selects_the_index_source_from_configuration(
    monkeypatch: pytest.MonkeyPatch, acre_index_dir: Path, tmp_path: Path
):
    monkeypatch.delenv(ENV_INDEX_DIR, raising=False)
    monkeypatch.delenv(ENV_INDEX_BUCKET, raising=False)
    monkeypatch.delenv(ENV_INDEX_CACHE_DIR, raising=False)

    assert isinstance(
        Settings(index_dir=acre_index_dir).build_index_source(), LocalDirectoryIndexSource
    )

    with pytest.raises(RuntimeError, match=ENV_INDEX_CACHE_DIR):
        Settings(index_bucket="my-bucket").build_index_source()

    assert isinstance(
        Settings(index_bucket="my-bucket", index_cache_dir=tmp_path).build_index_source(),
        GcsIndexSource,
    )

    with pytest.raises(RuntimeError, match=f"{ENV_INDEX_DIR} or {ENV_INDEX_BUCKET}"):
        Settings(index_dir=acre_index_dir, index_bucket="my-bucket").build_index_source()


def test_index_unavailable_is_503(acre_index_dir: Path):
    # A Core whose index was never opened: the adapter passes the failure through as 503.
    core = Core(LocalDirectoryIndexSource(acre_index_dir), ELECTIONS_FILE)
    with TestClient(create_api(core)) as client:
        response = client.get("/polling-place", params={"uf": "AC", "zone": 9, "section": 422})
    assert response.status_code == 503
    assert "index is not open" in response.json()["detail"]


# GET /api/v1/candidates (ticket #8)


def test_candidates_returns_the_core_envelope(client: TestClient, core: Core):
    response = client.get("/api/v1/candidates", params={"uf": "br", "office": "presidente"})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"data", "not_found", "warnings", "election", "source"}
    assert body == core.list_candidates("br", "presidente").model_dump(mode="json")
    # Without `round`, the president list is the highest round of the office (round 2).
    assert (body["data"]["round"], body["data"]["total"]) == (2, 2)
    assert [c["number"] for c in body["data"]["candidates"]] == [22, 45]
    assert body["source"]["file"] == "consulta_cand_2026_BRASIL.csv"
    assert body["election"]["id"] == "general-2026"


def test_candidates_query_parameters_are_passed_through(client: TestClient):
    response = client.get(
        "/api/v1/candidates",
        params={
            "uf": "AC",
            "office": "governador",
            "party": "22",
            "on_ballot_only": "false",
            "limit": "1",
            "offset": "0",
            "round": "1",
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 1
    assert data["candidates"][0]["ballot_name"] == "ANA LÚCIA"
    assert data["candidates"][0]["on_ballot"] is False
    assert (data["limit"], data["offset"], data["round"]) == (1, 0, 1)

    by_name = client.get(
        "/api/v1/candidates", params={"uf": "AC", "office": "deputado_estadual", "name": "d'arc"}
    )
    assert [c["number"] for c in by_name.json()["data"]["candidates"]] == [45123]


# GET /api/v1/candidates/by-number and /api/v1/candidates/{sq_candidato} (ticket #12)


def test_candidate_by_sq_candidato_returns_the_core_envelope(client: TestClient, core: Core):
    response = client.get("/api/v1/candidates/10000000001")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"data", "not_found", "warnings", "election", "source"}
    assert body == core.get_candidate(10000000001).model_dump(mode="json")
    candidate = body["data"]["candidate"]
    assert candidate["ballot_name"] == "MARIA DA SILVA"
    assert candidate["running_mates"][0]["office"] == "vice_governador"
    assert candidate["gender"] == "FEMININO"
    assert candidate["divulgacandcontas_url"].startswith("https://divulgacandcontas.tse.jus.br/")


def test_candidate_by_number_is_matched_before_the_sq_candidato_route(client: TestClient):
    # Called explicitly, so a regression that lets `{sq_candidato}` swallow the literal
    # segment shows up as a 422 ("by-number" is not an integer) instead of the profile.
    response = client.get(
        "/api/v1/candidates/by-number",
        params={"uf": "ac", "office": "governador", "number": "45", "round": "1"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["not_found"] is None
    assert body["data"]["candidate"]["sq_candidato"] == 10000000001
    assert body["data"]["candidate"]["round"] == 1

    off_ballot = client.get(
        "/api/v1/candidates/by-number", params={"uf": "AC", "office": "governador", "number": 22}
    )
    assert off_ballot.status_code == 200
    assert off_ballot.json()["not_found"]["reason"] == "candidato_nao_encontrado"


def test_candidate_with_a_non_numeric_sq_candidato_is_422(client: TestClient):
    response = client.get("/api/v1/candidates/abc")
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail[0]["loc"] == ["path", "sq_candidato"]


@pytest.mark.parametrize(
    ("path", "params", "message"),
    [
        ("/api/v1/candidates/by-number", {"uf": "AC", "office": "governador"}, None),
        (
            "/api/v1/candidates/by-number",
            {"uf": "AC", "office": "governador", "number": "x"},
            "número inválido",
        ),
        (
            "/api/v1/candidates/by-number",
            {"uf": "AC", "office": "vice_governador", "number": "45"},
            "cargo de chapa",
        ),
        ("/api/v1/candidates/10000000001", {"round": "9"}, "turno inválido"),
    ],
)
def test_candidate_invalid_query_is_400_and_missing_parameter_is_422(client, path, params, message):
    response = client.get(path, params=params)
    if message is None:
        assert response.status_code == 422
        return
    assert response.status_code == 400
    assert message in response.json()["detail"]


def test_polling_places_returns_the_core_envelope(client: TestClient, core: Core):
    response = client.get(
        "/api/v1/polling-places",
        params={"uf": "ac", "municipality": "Rio Branco", "neighborhood": "centro"},
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"data", "not_found", "warnings", "election", "source"}
    expected = core.search_polling_places("ac", "Rio Branco", neighborhood="centro")
    assert body == expected.model_dump(mode="json")
    assert [p["number"] for p in body["data"]["places"]] == [1050, 1035]
    assert "distance_km" not in body["data"]["places"][0]
    assert body["data"]["guidance"] == "Para saber a sua seção, consulte o e-Título."
    assert body["election"]["id"] == "general-2026"


def test_polling_places_pages_cover_the_full_ordered_list(tmp_path: Path):
    # Expand Rio Branco to 233 places. Clones share a name to exercise the sort tie-breaker.
    with ACRE_POLLING_PLACES.open(encoding="latin-1", newline="") as source:
        reader = csv.DictReader(source, delimiter=";")
        rows = list(reader)
        fieldnames = reader.fieldnames
    assert fieldnames is not None
    original = next(
        row for row in rows if row["CD_MUNICIPIO"] == "01392" and row["NR_TURNO"] == "1"
    )
    for number in range(2000, 2230):
        clone = original.copy()
        clone["NR_SECAO"] = str(number)
        clone["NR_LOCAL_VOTACAO"] = str(number)
        clone["NR_LOCAL_VOTACAO_ORIGINAL"] = str(number)
        clone["NM_LOCAL_VOTACAO"] = "ESCOLA MODELO"
        clone["NM_LOCAL_VOTACAO_ORIGINAL"] = "ESCOLA MODELO"
        if number == 2229:
            clone["NR_ZONA"] = "10"
            clone["NR_LOCAL_VOTACAO"] = "2228"
            clone["NR_LOCAL_VOTACAO_ORIGINAL"] = "2228"
        rows.append(clone)
    source_path = tmp_path / ACRE_POLLING_PLACES.name
    with source_path.open("w", encoding="latin-1", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames, delimiter=";", quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)
    index_dir = tmp_path / "index"
    build_fixture_index(index_dir, polling_places=source_path)
    core = Core(LocalDirectoryIndexSource(index_dir), ELECTIONS_FILE, clock=fixed_clock())
    with TestClient(build_app(core), base_url="http://localhost") as client:

        def page(offset: int, limit: int = 20) -> dict:
            response = client.get(
                "/api/v1/polling-places",
                params={
                    "uf": "AC",
                    "municipality": "01392",
                    "limit": str(limit),
                    "offset": str(offset),
                },
            )
            assert response.status_code == 200
            return response.json()["data"]

        pages = [page(offset) for offset in range(0, 233, 20)]
        beyond = page(240)

    assert [(p["limit"], p["offset"], p["total"], len(p["places"])) for p in pages] == [
        (20, offset, 233, min(20, 233 - offset)) for offset in range(0, 233, 20)
    ]
    numbers = [[(place["zone"], place["number"]) for place in p["places"]] for p in pages]
    assert len(set().union(*(set(page_numbers) for page_numbers in numbers))) == 233
    places = [place for page in pages for place in page["places"]]
    assert places == sorted(
        places, key=lambda place: (place["name"], place["number"], place["zone"])
    )
    assert (beyond["limit"], beyond["offset"], beyond["total"], beyond["places"]) == (
        20,
        240,
        233,
        [],
    )


def test_polling_places_lat_lon_become_near_and_order_by_distance(client: TestClient):
    response = client.get(
        "/api/v1/polling-places",
        params={
            "uf": "AC",
            "municipality": "Cruzeiro do Sul",
            "lat": "-7.6",
            "lon": "-72.7",
            "limit": "5",
            "round": "1",
        },
    )
    assert response.status_code == 200
    places = response.json()["data"]["places"]
    assert [p["number"] for p in places] == [1020, 1015]
    assert places[0]["distance_km"] > 0
    assert places[1]["distance_km"] is None


def test_polling_places_with_only_one_coordinate_is_400(client: TestClient):
    response = client.get(
        "/api/v1/polling-places", params={"uf": "AC", "municipality": "Rio Branco", "lat": "-9.9"}
    )
    assert response.status_code == 400
    assert "coordenadas" in response.json()["detail"]


def test_polling_places_bad_offset_has_the_candidates_error_shape(client: TestClient):
    places = client.get(
        "/api/v1/polling-places",
        params={"uf": "AC", "municipality": "Rio Branco", "offset": "x"},
    )
    candidates = client.get(
        "/api/v1/candidates", params={"uf": "AC", "office": "governador", "offset": "x"}
    )
    assert places.status_code == candidates.status_code == 400
    assert places.json() == candidates.json()


def test_polling_places_ambiguous_municipality_is_200_with_options(client: TestClient):
    response = client.get("/api/v1/polling-places", params={"uf": "AC", "municipality": "porto"})
    assert response.status_code == 200
    body = response.json()
    assert body["data"] is None
    assert body["not_found"]["reason"] == "municipio_ambiguo"
    assert [o["name"] for o in body["not_found"]["options"]] == ["Porto Acre", "Porto Walter"]


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"uf": "AC", "office": "prefeito"}, "cargo desconhecido"),
        ({"uf": "AC", "office": "presidente"}, "presidente só existe com uf = BR"),
        ({"uf": "AC", "office": "governador", "limit": "51"}, "limite inválido"),
        ({"uf": "AC", "office": "governador", "round": "3"}, "turno inválido"),
    ],
)
def test_candidates_invalid_query_is_400_with_the_core_message(client, params, message):
    response = client.get("/api/v1/candidates", params=params)
    assert response.status_code == 400
    assert message in response.json()["detail"]


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"uf": "AC", "municipality": "Rio Branco", "limit": "51"}, "limite inválido"),
        ({"uf": "AC", "municipality": "Rio Branco", "limit": "x"}, "limite inválido"),
        ({"uf": "AC", "municipality": "Rio Branco", "offset": "x"}, "deslocamento inválido"),
        ({"uf": "AC", "municipality": "Rio Branco", "round": "3"}, "turno inválido"),
        ({"uf": "XX", "municipality": "Rio Branco"}, "UF desconhecida"),
    ],
)
def test_polling_places_invalid_query_is_400(client: TestClient, params, message):
    response = client.get("/api/v1/polling-places", params=params)
    assert response.status_code == 400
    assert message in response.json()["detail"]


def test_municipalities_returns_the_core_envelope(client: TestClient, core: Core):
    response = client.get("/api/v1/municipalities", params={"name": "colonia"})
    assert response.status_code == 200
    body = response.json()
    assert body == core.resolve_municipality("colonia").model_dump(mode="json")
    assert body["data"]["municipalities"][0]["tse_code"] == "30015"
    assert body["data"]["municipalities"][0]["ibge_code"] is None
    assert body["election"] is None
    assert body["source"]["file"] == "municipio_tse_ibge.csv"


def test_municipalities_uf_and_limit_are_passed_through(client: TestClient):
    response = client.get(
        "/api/v1/municipalities", params={"name": "porto", "uf": "ac", "limit": "1"}
    )
    assert response.status_code == 200
    assert [m["name"] for m in response.json()["data"]["municipalities"]] == ["Porto Acre"]

    response = client.get("/api/v1/municipalities", params={"name": "porto", "limit": "0"})
    assert response.status_code == 400
    assert "limite inválido" in response.json()["detail"]


def test_municipalities_not_found_is_200_with_the_envelope(client: TestClient):
    response = client.get("/api/v1/municipalities", params={"name": "Xanadu"})
    assert response.status_code == 200
    body = response.json()
    assert body["data"] is None
    assert body["not_found"]["reason"] == "municipio_nao_encontrado"


# GET /healthz (ticket #13): not an MCP tool and not under /api/v1


def test_healthz_returns_the_health_envelope(client: TestClient, core: Core):
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body == core.health().model_dump(mode="json")
    assert set(body) == {
        "datasets",
        "index_built_at",
        "stale",
        "index_version",
        "last_index_check_at",
        "last_index_check_error",
    }
    assert body["datasets"]["polling_places"]["generated_at"] is not None
    assert body["stale"] is False


def test_healthz_is_not_under_api_v1(client: TestClient):
    assert client.get("/api/v1/healthz").status_code == 404


def test_health_serves_the_same_envelope_as_healthz(client: TestClient):
    # Cloud Run reserves paths ending in "z" on run.app for external requests (a documented
    # known issue), so /health exists for checks made from outside the service.
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == client.get("/healthz").json()


def test_healthz_is_503_when_the_index_was_never_opened(acre_index_dir: Path):
    # No lifespan here (no ``with``), so core.start() never runs and the index stays closed.
    core = Core(LocalDirectoryIndexSource(acre_index_dir), ELECTIONS_FILE)
    unstarted_client = TestClient(build_app(core), base_url="http://localhost")
    response = unstarted_client.get("/healthz")
    assert response.status_code == 503
    assert "index is not open" in response.json()["detail"]


def test_health_is_also_503_when_the_index_was_never_opened(acre_index_dir: Path):
    core = Core(LocalDirectoryIndexSource(acre_index_dir), ELECTIONS_FILE)
    unstarted_client = TestClient(build_app(core), base_url="http://localhost")
    response = unstarted_client.get("/health")
    assert response.status_code == 503
    assert "index is not open" in response.json()["detail"]


def test_lifespan_starts_the_check_task_and_shutdown_stops_it(acre_index_dir: Path):
    def check_task_alive() -> bool:
        return any(thread.name == "index-check" for thread in threading.enumerate())

    core = Core(LocalDirectoryIndexSource(acre_index_dir), ELECTIONS_FILE, clock=fixed_clock())
    assert check_task_alive() is False
    with TestClient(build_app(core), base_url="http://localhost") as client:
        assert check_task_alive() is True
        response = client.get(
            "/api/v1/polling-place", params={"uf": "AC", "zone": 9, "section": 422}
        )
        assert response.status_code == 200
        assert response.json()["data"]["section"] == 422
    assert check_task_alive() is False
    with pytest.raises(IndexUnavailable):
        core.find_polling_place("AC", 9, 422)


# GET /api/v1/candidates/compare (codebase-design 8.7, ADR 0008)


def test_compare_is_matched_before_the_sq_candidato_route(client: TestClient, core: Core):
    # A regression that lets `{sq_candidato}` swallow the literal segment shows up as a 422.
    response = client.get("/api/v1/candidates/compare", params={"uf": "ac", "office": "governador"})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"data", "not_found", "warnings", "election", "source"}
    assert body == core.compare_candidates("ac", "governador").model_dump(mode="json")
    assert [c["number"] for c in body["data"]["candidates"]] == [13, 45]
    assert body["data"]["candidates"][1]["assets"] == {"state": "declarados", "total": 1216500.0}


def test_compare_takes_repeated_number_or_sq_parameters(client: TestClient, core: Core):
    by_number = client.get(
        "/api/v1/candidates/compare",
        params=[
            ("uf", "BR"),
            ("office", "presidente"),
            ("number", "45"),
            ("number", "13"),
            ("number", "22"),
            ("round", "1"),
        ],
    )
    assert by_number.status_code == 200
    expected = core.compare_candidates("BR", "presidente", numbers=["45", "13", "22"], round="1")
    assert by_number.json() == expected.model_dump(mode="json")
    assert [c["number"] for c in by_number.json()["data"]["candidates"]] == [13, 22, 45]

    by_sq = client.get(
        "/api/v1/candidates/compare",
        params=[
            ("uf", "AC"),
            ("office", "governador"),
            ("sq", "10000000001"),
            ("sq", "10000000005"),
        ],
    )
    assert by_sq.status_code == 200
    assert by_sq.json()["not_found"]["reason"] == "candidaturas_insuficientes"


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ([("uf", "AC"), ("office", "governador"), ("number", "45")], "escolha de 2 a 4"),
        (
            [("uf", "AC"), ("office", "governador"), ("number", "45"), ("sq", "10000000003")],
            "não os dois",
        ),
        ([("uf", "AC"), ("office", "senador")], "candidatura(s) na urna"),
        (
            [("uf", "AC"), ("office", "vice_governador"), ("number", "45"), ("number", "13")],
            "cargo de chapa",
        ),
    ],
)
def test_compare_invalid_query_is_400(client: TestClient, params, message):
    response = client.get("/api/v1/candidates/compare", params=params)
    assert response.status_code == 400
    assert message in response.json()["detail"]


def test_candidate_list_returns_tse_gender_without_other_profile_only_fields(client: TestClient):
    response = client.get("/api/v1/candidates?uf=AC&office=governador&round=1")
    assert response.status_code == 200
    candidates = response.json()["data"]["candidates"]
    assert [(candidate["number"], candidate["gender"]) for candidate in candidates] == [
        (13, "MASCULINO"),
        (45, "FEMININO"),
    ]
    for candidate in candidates:
        assert not {"race_color", "marital_status", "education"} & candidate.keys()


@pytest.mark.parametrize("round_query", ["", "&round=1"])
def test_sp_senator_request_is_valid_even_without_sp_fixture_candidates(client, round_query):
    response = client.get(f"/api/v1/candidates?uf=SP&office=senador{round_query}")
    assert response.status_code == 200
    assert response.json()["data"]["candidates"] == []


@pytest.mark.parametrize(
    "query",
    [
        "uf=AC&amp;office=governador&amp;round=1",
        "uf=AC&amp;office=governador&round=1",
        "uf=AC&AMP;office=governador&amp;round=1",
    ],
)
def test_html_escaped_query_separators_reach_the_endpoint_as_parameters(client, query):
    # Assistants that copy a URL out of rendered HTML send `&amp;` literally, which would
    # otherwise drop `office` and answer 422 (issue #115).
    response = client.get(f"/api/v1/candidates?{query}")
    assert response.status_code == 200
    expected = client.get("/api/v1/candidates?uf=AC&office=governador&round=1").json()
    assert response.json() == expected


def test_a_query_value_containing_amp_is_left_as_sent(client: TestClient):
    response = client.get("/api/v1/candidates", params={"uf": "AC", "office": "amp;governador"})
    assert response.status_code == 400
    assert "amp;governador" in response.json()["detail"]


def test_compare_also_takes_one_comma_separated_selector(client: TestClient):
    # Some assistants' URL readers keep one value per parameter name (issue #115).
    repeated = client.get(
        "/api/v1/candidates/compare?uf=BR&office=presidente&number=45&number=13&number=22&round=1"
    )
    for query in ("number=45,13,22", "number=45%2C13%2C22", "number=45,13&number=22"):
        response = client.get(f"/api/v1/candidates/compare?uf=BR&office=presidente&{query}&round=1")
        assert response.status_code == 200
        assert response.json() == repeated.json()
    by_sq = client.get(
        "/api/v1/candidates/compare?uf=AC&office=governador&sq=10000000001,10000000005"
    )
    assert by_sq.json()["not_found"]["reason"] == "candidaturas_insuficientes"
    one = client.get("/api/v1/candidates/compare?uf=AC&office=governador&number=45,")
    assert one.status_code == 400
