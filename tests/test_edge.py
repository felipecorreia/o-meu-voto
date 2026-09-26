"""The edge check and the declined MCP event stream of the composition root (ADR 0010)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from br_elections_mcp.app import ENV_EDGE_SECRET, ENV_INDEX_DIR, Settings, build_app
from br_elections_mcp.core import Core
from br_elections_mcp.index_store import LocalDirectoryIndexSource
from tests.conftest import ELECTIONS_FILE, fixed_clock

EDGE_SECRET = "s3cret"
MCP_HEADERS = {"accept": "application/json, text/event-stream"}
TOOLS_LIST = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}


def make_client(acre_index_dir: Path, *, edge_secret: str | None) -> TestClient:
    core = Core(LocalDirectoryIndexSource(acre_index_dir), ELECTIONS_FILE, clock=fixed_clock())
    # With a port: the SDK's DNS-rebinding guard on a localhost bind accepts only
    # "localhost:<port>" as the Host of an MCP request.
    app = build_app(core, edge_secret=edge_secret)
    return TestClient(app, base_url="http://localhost:8000")


@pytest.fixture
def open_client(acre_index_dir: Path) -> Iterator[TestClient]:
    with make_client(acre_index_dir, edge_secret=None) as client:
        yield client


@pytest.fixture
def guarded_client(acre_index_dir: Path) -> Iterator[TestClient]:
    with make_client(acre_index_dir, edge_secret=EDGE_SECRET) as client:
        yield client


def test_get_mcp_declines_the_event_stream_with_405(open_client: TestClient):
    # Without the route the SDK answers 200 text/event-stream and never closes the stream.
    response = open_client.get("/mcp", headers={"accept": "text/event-stream"})
    assert response.status_code == 405
    assert response.headers["allow"] == "POST"
    assert "text/event-stream" not in response.headers.get("content-type", "")


def test_post_mcp_still_reaches_the_mcp_server(open_client: TestClient):
    response = open_client.post("/mcp", json=TOOLS_LIST, headers=MCP_HEADERS)
    assert response.status_code == 200
    tools = {tool["name"] for tool in response.json()["result"]["tools"]}
    assert "find_polling_place" in tools


def test_without_a_configured_secret_nothing_is_checked(open_client: TestClient):
    assert open_client.get("/api/v1/election").status_code == 200
    assert open_client.post("/mcp", json=TOOLS_LIST, headers=MCP_HEADERS).status_code == 200


@pytest.mark.parametrize("headers", [{}, {"x-edge-secret": "wrong"}, {"x-edge-secret": ""}])
def test_requests_without_the_edge_secret_are_refused(guarded_client: TestClient, headers):
    rest = guarded_client.get("/api/v1/election", headers=headers)
    assert rest.status_code == 403
    assert rest.json() == {"detail": "forbidden"}
    mcp = guarded_client.post("/mcp", json=TOOLS_LIST, headers=MCP_HEADERS | headers)
    assert mcp.status_code == 403
    assert guarded_client.get("/mcp", headers=headers).status_code == 403


def test_requests_with_the_edge_secret_are_served(guarded_client: TestClient):
    edge = {"x-edge-secret": EDGE_SECRET}
    assert guarded_client.get("/api/v1/election", headers=edge).status_code == 200
    mcp = guarded_client.post("/mcp", json=TOOLS_LIST, headers=MCP_HEADERS | edge)
    assert mcp.status_code == 200
    assert guarded_client.get("/mcp", headers=edge).status_code == 405


def test_healthz_needs_no_edge_secret_so_the_platform_probes_keep_working(
    guarded_client: TestClient,
):
    assert guarded_client.get("/healthz").status_code == 200


def test_health_needs_no_edge_secret_so_external_checks_keep_working(
    guarded_client: TestClient,
):
    assert guarded_client.get("/health").status_code == 200


def test_settings_read_the_edge_secret_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, acre_index_dir: Path
):
    monkeypatch.setenv(ENV_INDEX_DIR, str(acre_index_dir))
    monkeypatch.delenv(ENV_EDGE_SECRET, raising=False)
    assert Settings.from_env().edge_secret is None
    # An empty value is no secret at all, never a secret that an empty header would match.
    monkeypatch.setenv(ENV_EDGE_SECRET, "")
    assert Settings.from_env().edge_secret is None
    monkeypatch.setenv(ENV_EDGE_SECRET, EDGE_SECRET)
    assert Settings.from_env().edge_secret == EDGE_SECRET
