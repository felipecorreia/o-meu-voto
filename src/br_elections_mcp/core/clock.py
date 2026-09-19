"""The injected clock: tests move in time, the service uses UTC now."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable

Clock = Callable[[], dt.datetime]
"""Returns the current instant, timezone-aware."""


def system_clock() -> dt.datetime:
    return dt.datetime.now(dt.UTC)
