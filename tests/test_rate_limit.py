"""Per-IP rate limiting through the ASGI test client only (ticket #10)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from br_elections_mcp.app import (
    ENV_INDEX_DIR,
    ENV_RATE_LIMIT_MAX_REQUESTS,
    ENV_RATE_LIMIT_MCP_MAX_REQUESTS,
    ENV_RATE_LIMIT_MCP_WINDOW_SECONDS,
    ENV_RATE_LIMIT_WINDOW_SECONDS,
    Settings,
    build_app,
)
from br_elections_mcp.core import Core
from br_elections_mcp.index_store import LocalDirectoryIndexSource
from br_elections_mcp.rate_limit import RateLimitConfig
from tests.conftest import ELECTIONS_FILE, fixed_clock


class ManualClock:
    """A monotonic clock a test can advance by hand."""

    def __init__(self) -> None:
        self._value = 0.0

    def __call__(self) -> float:
        return self._value

    def advance(self, seconds: float) -> None:
        self._value += seconds


def make_client(
    acre_index_dir: Path,
    *,
    rate_limit: RateLimitConfig | None,
    clock: ManualClock,
    rate_limit_mcp: RateLimitConfig | None = None,
    peer: tuple[str, int] = ("198.51.100.7", 12345),
    edge_secret: str | None = None,
) -> TestClient:
    core = Core(LocalDirectoryIndexSource(acre_index_dir), ELECTIONS_FILE, clock=fixed_clock())
    app = build_app(
        core,
        rate_limit=rate_limit,
        rate_limit_mcp=rate_limit_mcp,
        rate_limit_clock=clock,
        edge_secret=edge_secret,
    )
    # With a port: the SDK's DNS-rebinding guard on a localhost bind accepts only
    # "localhost:<port>" as the Host of an MCP request that reaches the app (test_edge.py).
    return TestClient(app, base_url="http://localhost:8000", client=peer)


POLLING_PLACE_PARAMS = {"uf": "AC", "zone": 9, "section": 422}


def test_requests_under_the_limit_are_unaffected(acre_index_dir: Path):
    clock = ManualClock()
    with make_client(
        acre_index_dir, rate_limit=RateLimitConfig(max_requests=5, window_seconds=60), clock=clock
    ) as client:
        for _ in range(3):
            response = client.get("/api/v1/polling-place", params=POLLING_PLACE_PARAMS)
            assert response.status_code == 200


def test_requests_over_the_limit_get_429_with_retry_after_on_rest(acre_index_dir: Path):
    clock = ManualClock()
    with make_client(
        acre_index_dir, rate_limit=RateLimitConfig(max_requests=2, window_seconds=60), clock=clock
    ) as client:
        for _ in range(2):
            assert (
                client.get("/api/v1/polling-place", params=POLLING_PLACE_PARAMS).status_code == 200
            )
        response = client.get("/api/v1/polling-place", params=POLLING_PLACE_PARAMS)
        assert response.status_code == 429
        assert int(response.headers["retry-after"]) >= 1


def mcp_ping(client: TestClient) -> int:
    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        headers={"accept": "application/json, text/event-stream"},
    )
    return response.status_code


def test_requests_over_the_limit_get_429_with_retry_after_on_mcp(acre_index_dir: Path):
    clock = ManualClock()
    with make_client(
        acre_index_dir, rate_limit=RateLimitConfig(max_requests=1, window_seconds=60), clock=clock
    ) as client:
        # No BR_ELECTIONS_RATE_LIMIT_MCP_MAX_REQUESTS (rate_limit_mcp=None): /mcp falls back to
        # the general bucket, shared across both mounts, today's behavior. The first request, on
        # the REST surface, consumes the only token.
        assert client.get("/api/v1/polling-place", params=POLLING_PLACE_PARAMS).status_code == 200
        assert mcp_ping(client) == 429


def test_mcp_has_its_own_higher_limit_independent_of_rest(acre_index_dir: Path):
    clock = ManualClock()
    with make_client(
        acre_index_dir,
        rate_limit=RateLimitConfig(max_requests=1, window_seconds=60),
        rate_limit_mcp=RateLimitConfig(max_requests=3, window_seconds=60),
        clock=clock,
    ) as client:
        # The general bucket (REST) is exhausted after one request...
        assert client.get("/api/v1/polling-place", params=POLLING_PLACE_PARAMS).status_code == 200
        assert client.get("/api/v1/polling-place", params=POLLING_PLACE_PARAMS).status_code == 429
        # ...but /mcp draws from its own, larger bucket, unaffected by the spent REST one.
        assert mcp_ping(client) == 200
        assert mcp_ping(client) == 200
        assert mcp_ping(client) == 200
        assert mcp_ping(client) == 429


def test_rest_is_unaffected_when_the_mcp_bucket_is_exhausted(acre_index_dir: Path):
    clock = ManualClock()
    with make_client(
        acre_index_dir,
        rate_limit=RateLimitConfig(max_requests=1, window_seconds=60),
        rate_limit_mcp=RateLimitConfig(max_requests=3, window_seconds=60),
        clock=clock,
    ) as client:
        # Exhaust the /mcp bucket first...
        assert mcp_ping(client) == 200
        assert mcp_ping(client) == 200
        assert mcp_ping(client) == 200
        assert mcp_ping(client) == 429
        # ...the general (REST) bucket is untouched, since the two are independent.
        assert client.get("/api/v1/polling-place", params=POLLING_PLACE_PARAMS).status_code == 200


def test_bucket_refills_after_the_window(acre_index_dir: Path):
    clock = ManualClock()
    with make_client(
        acre_index_dir, rate_limit=RateLimitConfig(max_requests=1, window_seconds=60), clock=clock
    ) as client:
        assert client.get("/api/v1/polling-place", params=POLLING_PLACE_PARAMS).status_code == 200
        assert client.get("/api/v1/polling-place", params=POLLING_PLACE_PARAMS).status_code == 429
        clock.advance(60)
        assert client.get("/api/v1/polling-place", params=POLLING_PLACE_PARAMS).status_code == 200


def test_healthz_is_exempt_from_the_limit(acre_index_dir: Path):
    clock = ManualClock()
    with make_client(
        acre_index_dir, rate_limit=RateLimitConfig(max_requests=1, window_seconds=60), clock=clock
    ) as client:
        for _ in range(5):
            assert client.get("/healthz").status_code == 200


def test_health_is_exempt_from_the_limit(acre_index_dir: Path):
    clock = ManualClock()
    with make_client(
        acre_index_dir, rate_limit=RateLimitConfig(max_requests=1, window_seconds=60), clock=clock
    ) as client:
        for _ in range(5):
            assert client.get("/health").status_code == 200


def test_default_is_disabled(acre_index_dir: Path):
    clock = ManualClock()
    with make_client(acre_index_dir, rate_limit=None, clock=clock) as client:
        for _ in range(50):
            response = client.get("/api/v1/polling-place", params=POLLING_PLACE_PARAMS)
            assert response.status_code == 200


# On Cloud Run the socket peer is Google's front end for every client, so the limit can
# only tell voters apart through CF-Connecting-IP, and only once the edge secret proves the
# request came through Cloudflare (ADR 0010).
EDGE_SECRET = "s3cret"
# A Google front-end address: the same peer for every client, as on Cloud Run.
CLOUD_RUN_PEER = ("169.254.169.126", 443)


def test_cf_connecting_ip_is_honored_when_the_edge_secret_matched(acre_index_dir: Path):
    clock = ManualClock()
    with make_client(
        acre_index_dir,
        rate_limit=RateLimitConfig(max_requests=1, window_seconds=60),
        clock=clock,
        peer=CLOUD_RUN_PEER,
        edge_secret=EDGE_SECRET,
    ) as client:

        def get(client_ip: str) -> int:
            headers = {"x-edge-secret": EDGE_SECRET, "CF-Connecting-IP": client_ip}
            return client.get(
                "/api/v1/polling-place", params=POLLING_PLACE_PARAMS, headers=headers
            ).status_code

        assert get("203.0.113.10") == 200
        # Same peer, a different client behind the edge: its own, unspent bucket.
        assert get("203.0.113.20") == 200
        assert get("2001:db8::1") == 200
        # The first client again: its bucket is already spent.
        assert get("203.0.113.10") == 429


def test_cf_connecting_ip_is_ignored_without_a_configured_edge_secret(acre_index_dir: Path):
    clock = ManualClock()
    with make_client(
        acre_index_dir,
        rate_limit=RateLimitConfig(max_requests=1, window_seconds=60),
        clock=clock,
        peer=CLOUD_RUN_PEER,
    ) as client:
        first = client.get(
            "/api/v1/polling-place",
            params=POLLING_PLACE_PARAMS,
            headers={"CF-Connecting-IP": "203.0.113.10", "x-edge-secret": EDGE_SECRET},
        )
        assert first.status_code == 200
        # A different (forged) declared client: the header is ignored, so the socket
        # address's bucket, already spent, applies.
        second = client.get(
            "/api/v1/polling-place",
            params=POLLING_PLACE_PARAMS,
            headers={"CF-Connecting-IP": "203.0.113.20", "x-edge-secret": EDGE_SECRET},
        )
        assert second.status_code == 429


def test_an_unparseable_cf_connecting_ip_falls_back_to_the_peer(acre_index_dir: Path):
    clock = ManualClock()
    with make_client(
        acre_index_dir,
        rate_limit=RateLimitConfig(max_requests=1, window_seconds=60),
        clock=clock,
        peer=CLOUD_RUN_PEER,
        edge_secret=EDGE_SECRET,
    ) as client:
        for expected in (200, 429):
            response = client.get(
                "/api/v1/polling-place",
                params=POLLING_PLACE_PARAMS,
                headers={"x-edge-secret": EDGE_SECRET, "CF-Connecting-IP": "not-an-ip"},
            )
            assert response.status_code == expected


def test_log_lines_carry_only_the_truncated_ip(
    acre_index_dir: Path, caplog: pytest.LogCaptureFixture
):
    clock = ManualClock()
    with (
        caplog.at_level(logging.WARNING, logger="br_elections_mcp.rate_limit"),
        make_client(
            acre_index_dir,
            rate_limit=RateLimitConfig(max_requests=1, window_seconds=60),
            clock=clock,
            peer=("203.0.113.42", 443),
        ) as client,
    ):
        assert client.get("/api/v1/polling-place", params=POLLING_PLACE_PARAMS).status_code == 200
        assert client.get("/api/v1/polling-place", params=POLLING_PLACE_PARAMS).status_code == 429

    assert caplog.records, "expected a log line for the rejected request"
    for record in caplog.records:
        assert "203.0.113.42" not in record.getMessage()
    assert any("203.0.113.0" in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize(
    "max_requests, window_seconds", [(0, 60.0), (-1, 60.0), (5, 0.0), (5, -1.0)]
)
def test_rate_limit_config_rejects_non_positive_values(max_requests: int, window_seconds: float):
    with pytest.raises(ValueError):
        RateLimitConfig(max_requests=max_requests, window_seconds=window_seconds)


def test_settings_from_env_rejects_a_zero_max_requests(
    monkeypatch: pytest.MonkeyPatch, acre_index_dir: Path
):
    monkeypatch.setenv(ENV_INDEX_DIR, str(acre_index_dir))
    monkeypatch.setenv(ENV_RATE_LIMIT_MAX_REQUESTS, "0")
    with pytest.raises(ValueError):
        Settings.from_env()


def test_settings_from_env_reads_the_rate_limit(
    monkeypatch: pytest.MonkeyPatch, acre_index_dir: Path
):
    monkeypatch.setenv(ENV_INDEX_DIR, str(acre_index_dir))
    monkeypatch.delenv(ENV_RATE_LIMIT_MAX_REQUESTS, raising=False)
    monkeypatch.delenv(ENV_RATE_LIMIT_WINDOW_SECONDS, raising=False)
    assert Settings.from_env().rate_limit is None

    monkeypatch.setenv(ENV_RATE_LIMIT_MAX_REQUESTS, "120")
    monkeypatch.setenv(ENV_RATE_LIMIT_WINDOW_SECONDS, "30")
    assert Settings.from_env().rate_limit == RateLimitConfig(max_requests=120, window_seconds=30.0)


def test_settings_from_env_rejects_a_zero_mcp_max_requests(
    monkeypatch: pytest.MonkeyPatch, acre_index_dir: Path
):
    monkeypatch.setenv(ENV_INDEX_DIR, str(acre_index_dir))
    monkeypatch.setenv(ENV_RATE_LIMIT_MCP_MAX_REQUESTS, "0")
    with pytest.raises(ValueError):
        Settings.from_env()


def test_settings_from_env_reads_the_mcp_rate_limit(
    monkeypatch: pytest.MonkeyPatch, acre_index_dir: Path
):
    monkeypatch.setenv(ENV_INDEX_DIR, str(acre_index_dir))
    monkeypatch.delenv(ENV_RATE_LIMIT_MCP_MAX_REQUESTS, raising=False)
    monkeypatch.delenv(ENV_RATE_LIMIT_MCP_WINDOW_SECONDS, raising=False)
    # Unset: rate_limit_mcp is None, so /mcp falls back to the general limit (build_app's
    # default behavior when mcp_config is not passed).
    assert Settings.from_env().rate_limit_mcp is None

    monkeypatch.setenv(ENV_RATE_LIMIT_MCP_MAX_REQUESTS, "600")
    monkeypatch.setenv(ENV_RATE_LIMIT_MCP_WINDOW_SECONDS, "60")
    assert Settings.from_env().rate_limit_mcp == RateLimitConfig(
        max_requests=600, window_seconds=60.0
    )
