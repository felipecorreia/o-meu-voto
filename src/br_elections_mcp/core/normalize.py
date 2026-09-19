"""Normalization of voter input: leading zeros, whitespace, UF case.

Normalization belongs to the core; adapters pass input through untouched.
"""

from __future__ import annotations

import datetime as dt

from br_elections_mcp.core.errors import InvalidQuery
from br_elections_mcp.domain import POLLING_UFS, UF


def normalize_polling_uf(value: object) -> UF:
    """``"ac"``, ``" AC "`` and ``"AC"`` are the same UF; BR has no polling sections."""
    text = str(value).strip().upper() if value is not None else ""
    try:
        uf = UF(text)
    except ValueError:
        raise InvalidQuery(f"UF desconhecida: {value!r}") from None
    if uf not in POLLING_UFS:
        raise InvalidQuery(f"UF sem seções eleitorais: {text}")
    return uf


def normalize_number(value: object, label: str) -> int:
    """``"009"``, ``9`` and ``" 9 "`` are the same number; anything else is InvalidQuery.

    ``label`` is the PT-BR error prefix, e.g. ``"zona inválida"``.
    """
    if isinstance(value, bool):
        raise InvalidQuery(f"{label}: {value!r}")
    if isinstance(value, int):
        number = value
    else:
        text = str(value).strip() if value is not None else ""
        if not text.isdigit():
            raise InvalidQuery(f"{label}: {value!r}")
        number = int(text)
    if number < 1:
        raise InvalidQuery(f"{label}: {value!r}")
    return number


def normalize_date(value: object, label: str) -> dt.date:
    """``dt.date`` is passed through; a string is parsed as ISO ``AAAA-MM-DD``.

    ``label`` is the PT-BR error prefix, e.g. ``"data inválida"``.
    """
    if isinstance(value, dt.datetime) or not isinstance(value, dt.date | str):
        raise InvalidQuery(f"{label}: {value!r}")
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(value.strip())
    except ValueError:
        raise InvalidQuery(f"{label}: {value!r}") from None
