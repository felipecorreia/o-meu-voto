"""The edge check of the composition root (ADR 0010, amending ADR 0005; codebase-design 4).

Cloud Run cannot restrict its ingress to Cloudflare, so the service checks a shared secret
instead: the Pages Function (``web/functions/[[path]].js``) sends it as ``x-edge-secret``, and
when a secret is configured every request except ``/healthz`` (the platform's probes) must
carry it or gets ``403``. A request that carries it provably crossed the edge, so its
``CF-Connecting-IP``, which Cloudflare sets and a client cannot alter, becomes the client
address everything downstream sees, the per-IP rate limit included. Without a configured
secret (a local run, the tests) nothing is checked and the header is ignored, because any
client could forge it. Used by ``app.py`` alone: neither adapter knows the edge exists.
"""

from __future__ import annotations

import hmac
import ipaddress
from collections.abc import Iterable

EDGE_SECRET_HEADER = b"x-edge-secret"
CLIENT_IP_HEADER = b"cf-connecting-ip"
EXEMPT_PATHS = frozenset({"/healthz"})


class EdgeSecretMiddleware:
    """ASGI middleware wrapping the whole composition root, outside the rate limit.

    ``secret=None`` disables the check and the header trust entirely, the default in tests.
    """

    def __init__(
        self, app, *, secret: str | None, exempt_paths: Iterable[str] = EXEMPT_PATHS
    ) -> None:
        self._app = app
        self._secret = secret.encode() if secret else None
        self._exempt_paths = frozenset(exempt_paths)

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or self._secret is None or scope["path"] in self._exempt_paths:
            await self._app(scope, receive, send)
            return

        provided = _header(scope, EDGE_SECRET_HEADER)
        if provided is None or not hmac.compare_digest(provided, self._secret):
            await send(
                {
                    "type": "http.response.start",
                    "status": 403,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": b'{"detail":"forbidden"}'})
            return

        client_ip = _edge_client_ip(scope)
        if client_ip is not None:
            scope = {**scope, "client": (client_ip, 0)}
        await self._app(scope, receive, send)


def _edge_client_ip(scope: dict) -> str | None:
    value = _header(scope, CLIENT_IP_HEADER)
    if value is None:
        return None
    try:
        return str(ipaddress.ip_address(value.decode("latin-1").strip()))
    except ValueError:
        return None


def _header(scope: dict, name: bytes) -> bytes | None:
    for key, value in scope.get("headers", ()):
        if key.lower() == name:
            return value
    return None
