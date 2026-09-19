"""Composition root: chooses the IndexSource, builds the Core, mounts /mcp and /api/v1.

Composition only, never logic. The ASGI lifespan opens the index through
``Core.start()`` and closes it through ``Core.close()``; the MCP session
manager runs inside the same lifespan because Starlette does not propagate
lifespans to mounted apps.

Run locally with ``python -m br_elections_mcp.app --index-dir <dir>`` or with
``uvicorn --factory br_elections_mcp.app:create_app`` and the environment
variables read by ``Settings.from_env``.
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
from starlette.routing import Mount

from br_elections_mcp.api import create_api
from br_elections_mcp.core import Core
from br_elections_mcp.index_store import LocalDirectoryIndexSource
from br_elections_mcp.mcp_server import create_mcp_server
from br_elections_mcp.rate_limit import Clock, RateLimitConfig, RateLimitMiddleware

DEFAULT_ELECTIONS_FILE = Path(__file__).resolve().parents[2] / "data" / "elections.yaml"

ENV_INDEX_DIR = "BR_ELECTIONS_INDEX_DIR"
ENV_ELECTIONS_FILE = "BR_ELECTIONS_ELECTIONS_FILE"
ENV_HOST = "BR_ELECTIONS_HOST"
ENV_PORT = "BR_ELECTIONS_PORT"
ENV_RATE_LIMIT_MAX_REQUESTS = "BR_ELECTIONS_RATE_LIMIT_MAX_REQUESTS"
ENV_RATE_LIMIT_WINDOW_SECONDS = "BR_ELECTIONS_RATE_LIMIT_WINDOW_SECONDS"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_RATE_LIMIT_WINDOW_SECONDS = 60.0


@dataclass(frozen=True, slots=True)
class Settings:
    index_dir: Path
    elections_file: Path = DEFAULT_ELECTIONS_FILE
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    rate_limit: RateLimitConfig | None = None

    @classmethod
    def from_env(cls) -> Settings:
        index_dir = os.environ.get(ENV_INDEX_DIR)
        if not index_dir:
            raise RuntimeError(f"{ENV_INDEX_DIR} must point at a directory with index.duckdb")
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
        return cls(
            index_dir=Path(index_dir),
            elections_file=Path(os.environ.get(ENV_ELECTIONS_FILE, DEFAULT_ELECTIONS_FILE)),
            host=os.environ.get(ENV_HOST, DEFAULT_HOST),
            port=int(os.environ.get(ENV_PORT, DEFAULT_PORT)),
            rate_limit=rate_limit,
        )


def build_app(
    core: Core,
    *,
    host: str = DEFAULT_HOST,
    rate_limit: RateLimitConfig | None = None,
    rate_limit_clock: Clock = time.monotonic,
) -> Starlette:
    """Mount the two adapters over an already-constructed ``Core``; tests use this directly.

    The per-IP rate limit (codebase-design 4, ticket #10) wraps both mounts as ASGI
    middleware, the only cross-cutting concern of this composition root; ``rate_limit=None``
    (the default, and the default in tests) disables it entirely.
    """
    mcp_server = create_mcp_server(core)
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

    middleware = [Middleware(RateLimitMiddleware, config=rate_limit, clock=rate_limit_clock)]
    return Starlette(
        routes=[Mount("/api/v1", app=create_api(core)), Mount("/", app=mcp_app)],
        middleware=middleware,
        lifespan=lifespan,
    )


def create_app(settings: Settings | None = None) -> Starlette:
    settings = settings or Settings.from_env()
    core = Core(LocalDirectoryIndexSource(settings.index_dir), settings.elections_file)
    return build_app(core, host=settings.host, rate_limit=settings.rate_limit)


def main(argv: list[str] | None = None) -> None:
    import uvicorn

    parser = argparse.ArgumentParser(prog="python -m br_elections_mcp.app")
    parser.add_argument("--index-dir", type=Path, required=True)
    parser.add_argument("--elections-file", type=Path, default=DEFAULT_ELECTIONS_FILE)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    settings = Settings(
        index_dir=args.index_dir, elections_file=args.elections_file, host=args.host, port=args.port
    )
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
