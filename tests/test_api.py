"""REST adapter through an ASGI test client over a real ``Core``."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from br_elections_mcp.api import create_api
from br_elections_mcp.app import ENV_INDEX_DIR, ENV_PORT, Settings, build_app, create_app
from br_elections_mcp.core import Core, PollingPlaceAnswer
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


def test_openapi_is_served_under_the_prefix_and_generated_from_the_answer_model(
    client: TestClient,
):
    response = client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    document = response.json()
    assert "/polling-place" in document["paths"]
    assert document["servers"] == [{"url": "/api/v1"}]
    schemas = document["components"]["schemas"]
    assert set(PollingPlaceAnswer.model_json_schema()["properties"]) == set(
        schemas["PollingPlaceAnswer"]["properties"]
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
