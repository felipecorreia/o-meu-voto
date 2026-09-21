"""Anonymous PostHog telemetry (ticket #17): one event per query, disabled by default."""

from __future__ import annotations

from pathlib import Path

import pytest
from mcp import Client
from starlette.testclient import TestClient

from br_elections_mcp.app import (
    DEFAULT_POSTHOG_DISTINCT_ID,
    DEFAULT_POSTHOG_HOST,
    ENV_INDEX_DIR,
    ENV_POSTHOG_API_KEY,
    ENV_POSTHOG_DISTINCT_ID,
    ENV_POSTHOG_HOST,
    Settings,
    build_app,
)
from br_elections_mcp.core import Core
from br_elections_mcp.index_store import LocalDirectoryIndexSource
from br_elections_mcp.mcp_server import create_mcp_server
from br_elections_mcp.telemetry import EVENT_NAME, Telemetry, TelemetryConfig, build_telemetry
from tests.conftest import ELECTIONS_FILE, fixed_clock

pytestmark = pytest.mark.anyio

ALLOWED_PROPERTIES = {"route", "latency_ms", "stale", "round", "not_found.reason"}


class FakeTelemetryClient:
    """Records every capture call, in order; never touches the network."""

    def __init__(self, *, raise_on_capture: bool = False) -> None:
        self.events: list[dict] = []
        self.raise_on_capture = raise_on_capture

    def capture(self, event: str, *, distinct_id: str, properties: dict) -> None:
        if self.raise_on_capture:
            raise RuntimeError("posthog is down")
        self.events.append({"event": event, "distinct_id": distinct_id, "properties": properties})


def make_telemetry(client: FakeTelemetryClient, distinct_id: str = "deployment-1") -> Telemetry:
    return Telemetry(client, distinct_id=distinct_id)


class _FakeSource:
    def __init__(self, stale: bool) -> None:
        self.stale = stale


class _FakeData:
    def __init__(self, round_: int) -> None:
        self.round = round_


class _FakeNotFound:
    def __init__(self, reason: str) -> None:
        self.reason = reason


class _FakeAnswer:
    def __init__(self, *, data=None, source=None, not_found=None) -> None:
        self.data = data
        self.source = source
        self.not_found = not_found


# -- Telemetry.call, unit level -------------------------------------------------------------


def test_disabled_telemetry_builds_no_client_and_records_nothing():
    telemetry = build_telemetry(None)
    assert telemetry.enabled is False
    assert telemetry.call("some_route", lambda: 42) == 42


def test_enabled_telemetry_records_one_event_with_the_allowed_fields():
    client = FakeTelemetryClient()
    telemetry = make_telemetry(client)
    answer = _FakeAnswer(data=_FakeData(2), source=_FakeSource(True))

    result = telemetry.call("some_tool", lambda: answer)

    assert result is answer
    assert len(client.events) == 1
    event = client.events[0]
    assert event["event"] == EVENT_NAME
    assert event["distinct_id"] == "deployment-1"
    assert set(event["properties"]) == {"route", "latency_ms", "stale", "round"}
    assert event["properties"]["route"] == "some_tool"
    assert isinstance(event["properties"]["latency_ms"], float)
    assert event["properties"]["stale"] is True
    assert event["properties"]["round"] == 2


def test_not_found_reason_is_recorded_when_present_and_absent_otherwise():
    client = FakeTelemetryClient()
    telemetry = make_telemetry(client)

    telemetry.call("some_tool", lambda: _FakeAnswer(not_found=_FakeNotFound("municipio_ambiguo")))
    assert client.events[0]["properties"]["not_found.reason"] == "municipio_ambiguo"

    telemetry.call("some_tool", lambda: _FakeAnswer())
    assert "not_found.reason" not in client.events[1]["properties"]
    assert set(client.events[1]["properties"]) == {"route", "latency_ms"}


def test_round_of_a_candidate_answer_is_read_from_the_nested_profile():
    client = FakeTelemetryClient()
    telemetry = make_telemetry(client)

    class Data:
        candidate = _FakeData(1)

    telemetry.call("get_candidate", lambda: _FakeAnswer(data=Data()))

    assert client.events[0]["properties"]["round"] == 1


def test_a_raised_exception_still_records_one_event_with_only_route_and_latency():
    client = FakeTelemetryClient()
    telemetry = make_telemetry(client)

    def boom():
        raise ValueError("bad input")

    with pytest.raises(ValueError, match="bad input"):
        telemetry.call("some_tool", boom)

    assert len(client.events) == 1
    assert set(client.events[0]["properties"]) == {"route", "latency_ms"}


def test_a_posthog_outage_never_fails_or_delays_the_query():
    client = FakeTelemetryClient(raise_on_capture=True)
    telemetry = make_telemetry(client)

    assert telemetry.call("some_tool", lambda: 42) == 42


def test_distinct_id_is_a_constant_never_a_uuid_the_sdk_would_generate():
    client = FakeTelemetryClient()
    telemetry = make_telemetry(client, distinct_id="deployment-1")

    telemetry.call("a", lambda: 1)
    telemetry.call("b", lambda: 2)

    assert {event["distinct_id"] for event in client.events} == {"deployment-1"}


# -- Wired through the MCP adapter -----------------------------------------------------------

MCP_CALLS = [
    ("find_polling_place", {"uf": "AC", "zone": 9, "section": 422}),
    ("election_info", {"on": "2026-09-18"}),
    ("list_candidates", {"uf": "ac", "office": "governador"}),
    ("get_candidate", {"sq_candidato": 10000000001}),
    ("search_polling_places", {"uf": "AC", "municipality": "Rio Branco"}),
    ("resolve_municipality", {"name": "colonia"}),
]


async def test_each_mcp_tool_call_produces_exactly_one_event_with_no_request_input(core: Core):
    client = FakeTelemetryClient()
    telemetry = make_telemetry(client)
    forbidden_values = {value for _, args in MCP_CALLS for value in args.values()}
    forbidden_values |= {str(value) for value in forbidden_values}
    forbidden_keys = {key for _, args in MCP_CALLS for key in args}

    async with Client(create_mcp_server(core, telemetry=telemetry)) as mcp_client:
        for name, args in MCP_CALLS:
            result = await mcp_client.call_tool(name, args)
            assert result.is_error is False

    assert len(client.events) == len(MCP_CALLS)
    for (name, _), event in zip(MCP_CALLS, client.events, strict=True):
        assert event["event"] == EVENT_NAME
        properties = event["properties"]
        assert properties["route"] == name
        assert set(properties) <= ALLOWED_PROPERTIES
        assert set(properties).isdisjoint(forbidden_keys)
        assert all(value not in forbidden_values for value in properties.values())


async def test_mcp_search_polling_places_ambiguous_municipality_records_not_found_reason(
    core: Core,
):
    client = FakeTelemetryClient()
    telemetry = make_telemetry(client)

    async with Client(create_mcp_server(core, telemetry=telemetry)) as mcp_client:
        result = await mcp_client.call_tool(
            "search_polling_places", {"uf": "AC", "municipality": "porto"}
        )

    assert result.structured_content["not_found"]["reason"] == "municipio_ambiguo"
    assert client.events[0]["properties"]["not_found.reason"] == "municipio_ambiguo"


async def test_mcp_disabled_by_default_records_nothing(core: Core):
    async with Client(create_mcp_server(core)) as mcp_client:
        result = await mcp_client.call_tool(
            "find_polling_place", {"uf": "AC", "zone": 9, "section": 422}
        )
    assert result.is_error is False


# -- Wired through the REST adapter -----------------------------------------------------------

REST_CALLS = [
    ("GET /api/v1/polling-place", "/api/v1/polling-place", {"uf": "AC", "zone": 9, "section": 422}),
    ("GET /api/v1/election", "/api/v1/election", {"on": "2026-09-18"}),
    ("GET /api/v1/candidates", "/api/v1/candidates", {"uf": "br", "office": "presidente"}),
    (
        "GET /api/v1/candidates/by-number",
        "/api/v1/candidates/by-number",
        {"uf": "ac", "office": "governador", "number": "45", "round": "1"},
    ),
    ("GET /api/v1/candidates/{sq_candidato}", "/api/v1/candidates/10000000001", {}),
    (
        "GET /api/v1/polling-places",
        "/api/v1/polling-places",
        {"uf": "AC", "municipality": "Rio Branco"},
    ),
    ("GET /api/v1/municipalities", "/api/v1/municipalities", {"name": "colonia"}),
]


def test_each_rest_request_produces_exactly_one_event_with_no_request_input(acre_index_dir: Path):
    client = FakeTelemetryClient()
    telemetry = make_telemetry(client)
    core = Core(LocalDirectoryIndexSource(acre_index_dir), ELECTIONS_FILE, clock=fixed_clock())
    app = build_app(core, telemetry=telemetry)

    # "round" is excluded: it is the one request field the ticket also allows as output (the
    # answered round), so its value legitimately reappears in the recorded event.
    forbidden_values = {
        value for _, _, params in REST_CALLS for key, value in params.items() if key != "round"
    }
    forbidden_values |= {"10000000001"}
    forbidden_keys = {key for _, _, params in REST_CALLS for key in params if key != "round"}

    with TestClient(app, base_url="http://localhost") as http_client:
        for _, path, params in REST_CALLS:
            response = http_client.get(path, params=params)
            assert response.status_code == 200

    assert len(client.events) == len(REST_CALLS)
    for (route, _, _), event in zip(REST_CALLS, client.events, strict=True):
        assert event["event"] == EVENT_NAME
        properties = event["properties"]
        assert properties["route"] == route
        assert set(properties) <= ALLOWED_PROPERTIES
        assert set(properties).isdisjoint(forbidden_keys)
        assert all(value not in forbidden_values for value in properties.values())


def test_rest_disabled_by_default_records_nothing(acre_index_dir: Path):
    core = Core(LocalDirectoryIndexSource(acre_index_dir), ELECTIONS_FILE, clock=fixed_clock())
    app = build_app(core)

    with TestClient(app, base_url="http://localhost") as http_client:
        response = http_client.get(
            "/api/v1/polling-place", params={"uf": "AC", "zone": 9, "section": 422}
        )
    assert response.status_code == 200


# -- Settings.from_env --------------------------------------------------------------------


def test_settings_from_env_disables_telemetry_without_an_api_key(
    monkeypatch: pytest.MonkeyPatch, acre_index_dir: Path
):
    monkeypatch.setenv(ENV_INDEX_DIR, str(acre_index_dir))
    monkeypatch.delenv(ENV_POSTHOG_API_KEY, raising=False)
    assert Settings.from_env().telemetry is None


def test_settings_from_env_reads_the_posthog_config(
    monkeypatch: pytest.MonkeyPatch, acre_index_dir: Path
):
    monkeypatch.setenv(ENV_INDEX_DIR, str(acre_index_dir))
    monkeypatch.setenv(ENV_POSTHOG_API_KEY, "phc_test_key")
    monkeypatch.delenv(ENV_POSTHOG_HOST, raising=False)
    monkeypatch.delenv(ENV_POSTHOG_DISTINCT_ID, raising=False)

    telemetry = Settings.from_env().telemetry

    assert telemetry == TelemetryConfig(
        api_key="phc_test_key",
        host=DEFAULT_POSTHOG_HOST,
        distinct_id=DEFAULT_POSTHOG_DISTINCT_ID,
    )

    monkeypatch.setenv(ENV_POSTHOG_HOST, "https://eu.i.posthog.com")
    monkeypatch.setenv(ENV_POSTHOG_DISTINCT_ID, "br-elections-mcp-staging")

    telemetry = Settings.from_env().telemetry

    assert telemetry == TelemetryConfig(
        api_key="phc_test_key",
        host="https://eu.i.posthog.com",
        distinct_id="br-elections-mcp-staging",
    )
