"""Per-IP rate limiting for the composition root (codebase-design 4, ADR 0005).

A pure ASGI middleware: an in-memory token bucket per client IP, ``429`` with
``Retry-After`` over the configured rate, ``CF-Connecting-IP`` honored only
when the peer socket address is inside Cloudflare's published ranges (the
header is forgeable otherwise), and log lines carrying the truncated IP only,
never the full address (ADR 0004). Used by ``app.py`` alone: neither adapter
(``mcp_server.py``, ``api.py``) imports this module or knows limits or IPs
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

# Cloudflare's published edge ranges (https://www.cloudflare.com/ips/). Refresh with:
#   curl -s https://www.cloudflare.com/ips-v4 https://www.cloudflare.com/ips-v6
CLOUDFLARE_IP_RANGES: tuple[str, ...] = (
    "173.245.48.0/20",
    "103.21.244.0/22",
    "103.22.200.0/22",
    "103.31.4.0/22",
    "141.101.64.0/18",
    "108.162.192.0/18",
    "190.93.240.0/20",
    "188.114.96.0/20",
    "197.234.240.0/22",
    "198.41.128.0/17",
    "162.158.0.0/15",
    "104.16.0.0/13",
    "104.24.0.0/14",
    "172.64.0.0/13",
    "131.0.72.0/22",
    "2400:cb00::/32",
    "2606:4700::/32",
    "2803:f800::/32",
    "2405:b500::/32",
    "2405:8100::/32",
    "2a06:98c0::/29",
    "2c0f:f248::/32",
)

_CLOUDFLARE_NETWORKS = tuple(ipaddress.ip_network(cidr) for cidr in CLOUDFLARE_IP_RANGES)

EXEMPT_PATHS = frozenset({"/healthz"})


def is_cloudflare_ip(host: str) -> bool:
    """Whether ``host``, a socket peer address, is inside a Cloudflare range."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(address in network for network in _CLOUDFLARE_NETWORKS)


def truncate_ip(host: str) -> str:
    """``host`` with the last octet (IPv4) or last 80 bits (IPv6) zeroed, for logging."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return "unknown"
    prefix = 24 if address.version == 4 else 48
    return str(ipaddress.ip_network(f"{address}/{prefix}", strict=False).network_address)


def client_ip(scope: dict) -> str:
    """The client IP to rate-limit by: ``CF-Connecting-IP`` only from a Cloudflare peer."""
    client = scope.get("client")
    peer = client[0] if client else ""
    if is_cloudflare_ip(peer):
        header = _header(scope, b"cf-connecting-ip")
        if header:
            return header
    return peer


def _header(scope: dict, name: bytes) -> str | None:
    for key, value in scope.get("headers", ()):
        if key.lower() == name:
            return value.decode("latin-1")
    return None


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

    ``config=None`` disables the limit entirely, the default in tests (ticket #10).
    """

    def __init__(
        self,
        app,
        *,
        config: RateLimitConfig | None,
        clock: Clock = time.monotonic,
        exempt_paths: Iterable[str] = EXEMPT_PATHS,
    ) -> None:
        self._app = app
        self._exempt_paths = frozenset(exempt_paths)
        self._limiter = TokenBucketLimiter(config, clock) if config is not None else None

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or self._limiter is None or scope["path"] in self._exempt_paths:
            await self._app(scope, receive, send)
            return

        ip = client_ip(scope)
        decision = self._limiter.check(ip)
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
