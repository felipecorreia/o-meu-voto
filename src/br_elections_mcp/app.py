"""Composition root: chooses the IndexSource, builds the Core, mounts /mcp, /api/v1, /healthz
and /health.

Composition only, never logic. The ASGI lifespan opens the index through
``Core.start()`` and closes it through ``Core.close()``; the MCP session
manager runs inside the same lifespan because Starlette does not propagate
lifespans to mounted apps.

Run locally with ``python -m br_elections_mcp.app --index-dir <dir>`` or with
``uvicorn --factory br_elections_mcp.app:create_app`` and the environment
variables read by ``Settings.from_env``. The page is published on Cloudflare
Pages (ADR 0005), never by the service.

In production the service sits behind the Pages Function of ``web-next/`` (ADR 0005, ADR 0010):
``BR_ELECTIONS_EDGE_SECRET`` makes it refuse traffic that did not come through that edge,
and ``GET /mcp`` answers ``405`` so no idle event stream holds an instance.
"""

from __future__ import annotations

import argparse
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route

from br_elections_mcp.api import create_api
from br_elections_mcp.core import Core, IndexSource, IndexUnavailable
from br_elections_mcp.edge import EdgeSecretMiddleware
from br_elections_mcp.index_store import GcsIndexSource, LocalDirectoryIndexSource
from br_elections_mcp.mcp_server import create_mcp_server
from br_elections_mcp.rate_limit import Clock, RateLimitConfig, RateLimitMiddleware
from br_elections_mcp.telemetry import Telemetry, TelemetryConfig, build_telemetry

DEFAULT_ELECTIONS_FILE = Path(__file__).resolve().parents[2] / "data" / "elections.yaml"

ENV_INDEX_DIR = "BR_ELECTIONS_INDEX_DIR"
ENV_INDEX_BUCKET = "BR_ELECTIONS_INDEX_BUCKET"
ENV_INDEX_BUCKET_PREFIX = "BR_ELECTIONS_INDEX_BUCKET_PREFIX"
ENV_INDEX_CACHE_DIR = "BR_ELECTIONS_INDEX_CACHE_DIR"
ENV_ELECTIONS_FILE = "BR_ELECTIONS_ELECTIONS_FILE"
ENV_HOST = "BR_ELECTIONS_HOST"
ENV_PORT = "BR_ELECTIONS_PORT"
ENV_RATE_LIMIT_MAX_REQUESTS = "BR_ELECTIONS_RATE_LIMIT_MAX_REQUESTS"
ENV_RATE_LIMIT_WINDOW_SECONDS = "BR_ELECTIONS_RATE_LIMIT_WINDOW_SECONDS"
ENV_RATE_LIMIT_MCP_MAX_REQUESTS = "BR_ELECTIONS_RATE_LIMIT_MCP_MAX_REQUESTS"
ENV_RATE_LIMIT_MCP_WINDOW_SECONDS = "BR_ELECTIONS_RATE_LIMIT_MCP_WINDOW_SECONDS"
ENV_EDGE_SECRET = "BR_ELECTIONS_EDGE_SECRET"
ENV_POSTHOG_API_KEY = "BR_ELECTIONS_POSTHOG_API_KEY"
ENV_POSTHOG_HOST = "BR_ELECTIONS_POSTHOG_HOST"
ENV_POSTHOG_DISTINCT_ID = "BR_ELECTIONS_POSTHOG_DISTINCT_ID"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_RATE_LIMIT_WINDOW_SECONDS = 60.0
DEFAULT_INDEX_BUCKET_PREFIX = ""
DEFAULT_POSTHOG_HOST = "https://us.i.posthog.com"
DEFAULT_POSTHOG_DISTINCT_ID = "br-elections-mcp"


@dataclass(frozen=True, slots=True)
class Settings:
    """Either ``index_dir`` (``LocalDirectoryIndexSource``) or ``index_bucket`` (``GcsIndexSource``,
    which also needs ``index_cache_dir``) must be set, never both; ``build_index_source()``
    is where that is enforced.
    """

    index_dir: Path | None = None
    index_bucket: str | None = None
    index_bucket_prefix: str = DEFAULT_INDEX_BUCKET_PREFIX
    index_cache_dir: Path | None = None
    elections_file: Path = DEFAULT_ELECTIONS_FILE
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    rate_limit: RateLimitConfig | None = None
    rate_limit_mcp: RateLimitConfig | None = None
    edge_secret: str | None = None
    telemetry: TelemetryConfig | None = None

    def build_index_source(self) -> IndexSource:
        if self.index_dir and self.index_bucket:
            raise RuntimeError(f"set only one of {ENV_INDEX_DIR} or {ENV_INDEX_BUCKET}, not both")
        if self.index_dir:
            return LocalDirectoryIndexSource(self.index_dir)
        if self.index_bucket:
            if not self.index_cache_dir:
                raise RuntimeError(
                    f"{ENV_INDEX_CACHE_DIR} must point at a local cache directory when "
                    f"{ENV_INDEX_BUCKET} is set"
                )
            return GcsIndexSource(self.index_bucket, self.index_bucket_prefix, self.index_cache_dir)
        raise RuntimeError(f"set {ENV_INDEX_DIR} or {ENV_INDEX_BUCKET} to choose the index source")

    @classmethod
    def from_env(cls) -> Settings:
        index_dir = os.environ.get(ENV_INDEX_DIR)
        index_bucket = os.environ.get(ENV_INDEX_BUCKET)
        index_cache_dir = os.environ.get(ENV_INDEX_CACHE_DIR)
        max_requests = os.environ.get(ENV_RATE_LIMIT_MAX_REQUESTS)
        rate_limit = (
            RateLimitConfig(
                max_requests=int(max_requests),
                window_seconds=float(
                    os.environ.get(ENV_RATE_LIMIT_WINDOW_SECONDS, DEFAULT_RATE_LIMIT_WINDOW_SECONDS)
                ),
            )
            if max_requests
            else None
        )
        mcp_max_requests = os.environ.get(ENV_RATE_LIMIT_MCP_MAX_REQUESTS)
        rate_limit_mcp = (
            RateLimitConfig(
                max_requests=int(mcp_max_requests),
                window_seconds=float(
                    os.environ.get(
                        ENV_RATE_LIMIT_MCP_WINDOW_SECONDS, DEFAULT_RATE_LIMIT_WINDOW_SECONDS
                    )
                ),
            )
            if mcp_max_requests
            else None
        )
        posthog_api_key = os.environ.get(ENV_POSTHOG_API_KEY)
        telemetry = (
            TelemetryConfig(
                api_key=posthog_api_key,
                host=os.environ.get(ENV_POSTHOG_HOST, DEFAULT_POSTHOG_HOST),
                distinct_id=os.environ.get(ENV_POSTHOG_DISTINCT_ID, DEFAULT_POSTHOG_DISTINCT_ID),
            )
            if posthog_api_key
            else None
        )
        return cls(
            index_dir=Path(index_dir) if index_dir else None,
            index_bucket=index_bucket or None,
            index_bucket_prefix=os.environ.get(
                ENV_INDEX_BUCKET_PREFIX, DEFAULT_INDEX_BUCKET_PREFIX
            ),
            index_cache_dir=Path(index_cache_dir) if index_cache_dir else None,
            elections_file=Path(os.environ.get(ENV_ELECTIONS_FILE, DEFAULT_ELECTIONS_FILE)),
            host=os.environ.get(ENV_HOST, DEFAULT_HOST),
            port=int(os.environ.get(ENV_PORT, DEFAULT_PORT)),
            rate_limit=rate_limit,
            rate_limit_mcp=rate_limit_mcp,
            edge_secret=os.environ.get(ENV_EDGE_SECRET) or None,
            telemetry=telemetry,
        )


def build_app(
    core: Core,
    *,
    host: str = DEFAULT_HOST,
    rate_limit: RateLimitConfig | None = None,
    rate_limit_mcp: RateLimitConfig | None = None,
    rate_limit_clock: Clock = time.monotonic,
    edge_secret: str | None = None,
    telemetry: Telemetry | None = None,
) -> Starlette:
    """Mount the two adapters over an already-constructed ``Core``; tests use this directly.

    Two ASGI middlewares wrap both mounts, the only cross-cutting concerns of this
    composition root (codebase-design 4): outermost the edge-secret check (ADR 0010), which
    also makes ``CF-Connecting-IP`` the client address of a request that passed it, then the
    per-IP rate limit (ticket #10), which counts by that address. ``edge_secret=None`` and
    ``rate_limit=None`` (the defaults, and the defaults in tests) disable each entirely.
    ``rate_limit_mcp`` (ticket #64) gives ``/mcp`` its own, independent bucket; unset, ``/mcp``
    falls back to ``rate_limit``'s bucket, shared with REST, today's behavior.
    ``telemetry=None`` (the default, and the default in tests) likewise disables product
    telemetry (ticket #17).
    """
    telemetry = telemetry if telemetry is not None else Telemetry()
    mcp_server = create_mcp_server(core, telemetry=telemetry)
    # `host` only drives the SDK's DNS-rebinding protection: on localhost it allows
    # localhost origins; elsewhere the protection is off and the edge is the guard (ADR 0005).
    mcp_app = mcp_server.streamable_http_app(
        streamable_http_path="/mcp", stateless_http=True, json_response=True, host=host
    )

    @asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        core.start()
        try:
            async with mcp_server.session_manager.run():
                yield
        finally:
            core.close()

    async def healthz(_: Request) -> JSONResponse:
        try:
            health = core.health()
        except IndexUnavailable as exc:
            return JSONResponse({"detail": str(exc)}, status_code=503)
        return JSONResponse(health.model_dump(mode="json"))

    # Cloud Run reserves some paths ending in "z" on the default run.app domain and answers
    # them with its own 404 for external requests (a documented known issue), so /healthz is
    # unreachable from outside even though the internal startup and liveness probes on it work.
    # /health serves the same payload for external checks (scripts/smoke.sh).

    async def mcp_stream_not_allowed(_: Request) -> Response:
        # The server is stateless and never sends server-initiated messages, so it declines
        # the optional GET event stream, as the Streamable HTTP spec allows, instead of
        # holding an idle request open that keeps a Cloud Run instance billed.
        return Response(status_code=405, headers={"allow": "POST"})

    middleware = [
        Middleware(EdgeSecretMiddleware, secret=edge_secret),
        Middleware(
            RateLimitMiddleware,
            config=rate_limit,
            mcp_config=rate_limit_mcp,
            clock=rate_limit_clock,
        ),
    ]
    routes = [
        Route("/healthz", healthz),
        Route("/health", healthz),
        Mount("/api/v1", app=create_api(core, telemetry=telemetry)),
        # Before the MCP mount, which would otherwise take GET /mcp; POST and DELETE only
        # match partially here and fall through to it.
        Route("/mcp", mcp_stream_not_allowed, methods=["GET"]),
        Mount("/", app=mcp_app),
    ]
    return Starlette(
        routes=routes,
        middleware=middleware,
        lifespan=lifespan,
    )


def create_app(settings: Settings | None = None) -> Starlette:
    settings = settings or Settings.from_env()
    core = Core(settings.build_index_source(), settings.elections_file)
    return build_app(
        core,
        host=settings.host,
        rate_limit=settings.rate_limit,
        rate_limit_mcp=settings.rate_limit_mcp,
        edge_secret=settings.edge_secret,
        telemetry=build_telemetry(settings.telemetry),
    )


def main(argv: list[str] | None = None) -> None:
    import uvicorn

    parser = argparse.ArgumentParser(prog="python -m br_elections_mcp.app")
    parser.add_argument("--index-dir", type=Path, required=True)
    parser.add_argument("--elections-file", type=Path, default=DEFAULT_ELECTIONS_FILE)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    settings = Settings(
        index_dir=args.index_dir,
        elections_file=args.elections_file,
        host=args.host,
        port=args.port,
    )
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
