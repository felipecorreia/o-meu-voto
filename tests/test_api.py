"""REST adapter through an ASGI test client over a real ``Core``."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from br_elections_mcp.api import create_api
from br_elections_mcp.app import ENV_INDEX_DIR, ENV_PORT, Settings, build_app, create_app
from br_elections_mcp.core import (
    CandidatesAnswer,
    Core,
    ElectionInfoAnswer,
    IndexUnavailable,
    MunicipalitiesAnswer,
    PollingPlaceAnswer,
    PollingPlacesAnswer,
)
from br_elections_mcp.index_store import LocalDirectoryIndexSource
from tests.conftest import ELECTIONS_FILE, fixed_clock


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
        "/polling-places",
        "/municipalities",
    } <= set(document["paths"])
    assert document["servers"] == [{"url": "/api/v1"}]
    schemas = document["components"]["schemas"]
    for model in (
        PollingPlaceAnswer,
        ElectionInfoAnswer,
        CandidatesAnswer,
        PollingPlacesAnswer,
        MunicipalitiesAnswer,
    ):
        assert set(model.model_json_schema()["properties"]) == set(
            schemas[model.__name__]["properties"]
        )
    assert not {"gender", "race_color", "marital_status", "education"} & set(
        schemas["CandidateListItem"]["properties"]
    )


def test_settings_from_env_reads_the_index_dir_and_defaults(
    monkeypatch: pytest.MonkeyPatch, acre_index_dir: Path
):
    monkeypatch.delenv(ENV_INDEX_DIR, raising=False)
    with pytest.raises(RuntimeError, match=ENV_INDEX_DIR):
        Settings.from_env()

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
    assert body["data"]["total"] == 2
    assert [c["number"] for c in body["data"]["candidates"]] == [13, 45]
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


def test_polling_places_ambiguous_municipality_is_200_with_options(client: TestClient):
    response = client.get("/api/v1/polling-places", params={"uf": "AC", "municipality": "porto"})
    assert response.status_code == 200
    body = response.json()
    assert body["data"] is None
    assert body["not_found"]["reason"] == "municipio_ambiguo"
    assert [o["name"] for o in body["not_found"]["options"]] == ["PORTO ACRE", "PORTO WALTER"]


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
    assert [m["name"] for m in response.json()["data"]["municipalities"]] == ["PORTO ACRE"]

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


def test_healthz_is_503_when_the_index_was_never_opened(acre_index_dir: Path):
    # No lifespan here (no ``with``), so core.start() never runs and the index stays closed.
    core = Core(LocalDirectoryIndexSource(acre_index_dir), ELECTIONS_FILE)
    unstarted_client = TestClient(build_app(core), base_url="http://localhost")
    response = unstarted_client.get("/healthz")
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
