"""Anonymous product telemetry for the composition root (ticket #17).

One ``query`` event per MCP tool call or REST request, carrying only the route, the latency,
``stale`` and the answered round when the query produced an answer, and ``not_found.reason``
when it didn't find one. Never the IP, never a request input (UF, zone, section, municipality,
name, number), never a session or device identifier; ``distinct_id`` is a constant per
deployment, set once in ``TelemetryConfig``.

``telemetry=None`` (the default, and the default in tests) disables telemetry entirely: no
client is constructed and ``Telemetry.call`` runs the query without recording anything.
Capture never touches the request path: the PostHog SDK queues on its own background thread,
and ``Telemetry.call`` itself swallows whatever a capture raises, so a PostHog outage can never
delay or fail a query.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, TypeVar

logger = logging.getLogger(__name__)

Clock = Callable[[], float]
T = TypeVar("T")

EVENT_NAME = "query"


class TelemetryClient(Protocol):
    def capture(self, event: str, *, distinct_id: str, properties: dict[str, object]) -> object: ...


@dataclass(frozen=True, slots=True)
class TelemetryConfig:
    """PostHog project credentials. Absent (``None``) disables telemetry."""

    api_key: str
    host: str
    distinct_id: str

    def __post_init__(self) -> None:
        if not self.api_key:
            raise ValueError("api_key must not be empty")
        if not self.distinct_id:
            raise ValueError("distinct_id must not be empty")


def build_client(config: TelemetryConfig) -> TelemetryClient:
    from posthog import Posthog

    # disable_geoip: PostHog otherwise derives a location from the caller's IP server-side,
    # which this project never collects (ADR 0004).
    return Posthog(project_api_key=config.api_key, host=config.host, disable_geoip=True)


class Telemetry:
    """Wraps a ``TelemetryClient``. ``client=None`` makes every call a no-op."""

    def __init__(
        self,
        client: TelemetryClient | None = None,
        *,
        distinct_id: str = "",
        clock: Clock = time.monotonic,
    ) -> None:
        self._client = client
        self._distinct_id = distinct_id
        self._clock = clock

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def call(self, route: str, fn: Callable[[], T]) -> T:
        """Run ``fn``, record exactly one event for ``route``, and return or re-raise as-is.

        The event carries ``stale``, ``round`` and ``not_found.reason`` only when ``fn``
        returns an answer envelope exposing them; a raised exception still produces an event,
        with the route and the latency alone.
        """
        if self._client is None:
            return fn()
        started = self._clock()
        try:
            result = fn()
        except Exception:
            self._capture(route, self._clock() - started, None)
            raise
        self._capture(route, self._clock() - started, result)
        return result

    def _capture(self, route: str, elapsed_seconds: float, answer: object | None) -> None:
        assert self._client is not None
        properties: dict[str, object] = {
            "route": route,
            "latency_ms": elapsed_seconds * 1000,
        }
        if answer is not None:
            stale = _stale_of(answer)
            if stale is not None:
                properties["stale"] = stale
            round_ = _round_of(answer)
            if round_ is not None:
                properties["round"] = round_
            reason = _not_found_reason_of(answer)
            if reason is not None:
                properties["not_found.reason"] = reason
        try:
            self._client.capture(EVENT_NAME, distinct_id=self._distinct_id, properties=properties)
        except Exception:
            logger.warning("telemetry capture failed", exc_info=True)


def build_telemetry(config: TelemetryConfig | None) -> Telemetry:
    if config is None:
        return Telemetry()
    return Telemetry(build_client(config), distinct_id=config.distinct_id)


def _stale_of(answer: object) -> bool | None:
    source = getattr(answer, "source", None)
    return getattr(source, "stale", None) if source is not None else None


def _round_of(answer: object) -> int | None:
    """The round the answer refers to: ``data.round``, or ``data.candidate.round`` for
    ``CandidateAnswer``, whose round lives on the nested profile instead."""
    data = getattr(answer, "data", None)
    if data is None:
        return None
    round_ = getattr(data, "round", None)
    if round_ is not None:
        return round_
    candidate = getattr(data, "candidate", None)
    return getattr(candidate, "round", None) if candidate is not None else None


def _not_found_reason_of(answer: object) -> str | None:
    not_found = getattr(answer, "not_found", None)
    return not_found.reason if not_found is not None else None
