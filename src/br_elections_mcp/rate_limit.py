"""Per-IP rate limiting for the composition root (codebase-design 4, ADR 0005).

A pure ASGI middleware: an in-memory token bucket per client IP, ``429`` with
``Retry-After`` over the configured rate, and log lines carrying the truncated IP
only, never the full address (ADR 0004). The client IP is the ASGI ``client``
address: behind the edge, ``edge.py`` has already replaced it with
``CF-Connecting-IP`` for requests that carried a valid edge secret (ADR 0010), so
this module never reads a forgeable header. Used by ``app.py`` alone: neither
adapter (``mcp_server.py``, ``api.py``) imports this module or knows limits or IPs
exist.
"""

from __future__ import annotations

import ipaddress
import logging
import math
import time
from collections.abc import Callable, Iterable, MutableMapping
from dataclasses import dataclass

logger = logging.getLogger(__name__)

Clock = Callable[[], float]
"""Returns a monotonically increasing instant, in seconds."""

EXEMPT_PATHS = frozenset({"/healthz", "/health"})
MCP_PATH = "/mcp"


def truncate_ip(host: str) -> str:
    """``host`` with the last octet (IPv4) or last 80 bits (IPv6) zeroed, for logging."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return "unknown"
    prefix = 24 if address.version == 4 else 48
    return str(ipaddress.ip_network(f"{address}/{prefix}", strict=False).network_address)


def client_ip(scope: dict) -> str:
    """The client IP to rate-limit by: the ASGI client address (see the module docstring)."""
    client = scope.get("client")
    return client[0] if client else ""


@dataclass(frozen=True, slots=True)
class RateLimitConfig:
    """``max_requests`` per ``window_seconds`` per IP. Absent (``None``) disables the limit."""

    max_requests: int
    window_seconds: float = 60.0

    def __post_init__(self) -> None:
        if self.max_requests <= 0:
            raise ValueError(f"max_requests must be positive, got {self.max_requests}")
        if self.window_seconds <= 0:
            raise ValueError(f"window_seconds must be positive, got {self.window_seconds}")


@dataclass(slots=True)
class _Bucket:
    tokens: float
    updated_at: float


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: float


class TokenBucketLimiter:
    """One token bucket per key, refilled continuously at ``max_requests / window_seconds``."""

    def __init__(self, config: RateLimitConfig, clock: Clock = time.monotonic) -> None:
        self._capacity = config.max_requests
        self._refill_rate = config.max_requests / config.window_seconds
        self._clock = clock
        self._buckets: MutableMapping[str, _Bucket] = {}

    def check(self, key: str) -> RateLimitDecision:
        now = self._clock()
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = _Bucket(tokens=float(self._capacity), updated_at=now)
            self._buckets[key] = bucket
        else:
            elapsed = max(0.0, now - bucket.updated_at)
            bucket.tokens = min(self._capacity, bucket.tokens + elapsed * self._refill_rate)
            bucket.updated_at = now
        if bucket.tokens >= 1:
            bucket.tokens -= 1
            return RateLimitDecision(allowed=True, retry_after_seconds=0.0)
        missing = 1 - bucket.tokens
        return RateLimitDecision(allowed=False, retry_after_seconds=missing / self._refill_rate)


class RateLimitMiddleware:
    """ASGI middleware wrapping the whole composition root, above both mounts.

    ``config=None`` disables the general limit entirely, the default in tests (ticket #10).
    ``mcp_config`` (ticket #64) gives ``/mcp`` its own bucket, independent of the general one,
    so REST traffic and ``/mcp`` traffic from the same IP do not drain each other; unset, ``/mcp``
    falls back to the general limiter and bucket, today's behavior. ``mcp_config`` can be set
    even when ``config`` is ``None``, limiting only ``/mcp``.
    """

    def __init__(
        self,
        app,
        *,
        config: RateLimitConfig | None,
        mcp_config: RateLimitConfig | None = None,
        clock: Clock = time.monotonic,
        exempt_paths: Iterable[str] = EXEMPT_PATHS,
    ) -> None:
        self._app = app
        self._exempt_paths = frozenset(exempt_paths)
        self._limiter = TokenBucketLimiter(config, clock) if config is not None else None
        self._mcp_limiter = (
            TokenBucketLimiter(mcp_config, clock) if mcp_config is not None else None
        )

    def _limiter_for(self, path: str) -> TokenBucketLimiter | None:
        if path == MCP_PATH and self._mcp_limiter is not None:
            return self._mcp_limiter
        return self._limiter

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or scope["path"] in self._exempt_paths:
            await self._app(scope, receive, send)
            return

        limiter = self._limiter_for(scope["path"])
        if limiter is None:
            await self._app(scope, receive, send)
            return

        ip = client_ip(scope)
        decision = limiter.check(ip)
        if decision.allowed:
            await self._app(scope, receive, send)
            return

        retry_after = max(1, math.ceil(decision.retry_after_seconds))
        logger.warning("rate limit exceeded for ip=%s", truncate_ip(ip))
        await send(
            {
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    (b"retry-after", str(retry_after).encode("ascii")),
                    (b"content-type", b"application/json"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": b'{"detail":"too many requests"}'})
