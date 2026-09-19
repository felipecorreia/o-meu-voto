"""Normalization of voter input: leading zeros, whitespace, UF case, office names, accents,
free text.

Normalization belongs to the core; adapters pass input through untouched.
"""

from __future__ import annotations

import datetime as dt
import unicodedata

from br_elections_mcp.core.errors import InvalidQuery
from br_elections_mcp.domain import POLLING_UFS, UF, Office

CANDIDATE_UFS: frozenset[UF] = frozenset(UF) - {UF.ZZ}
"""The UFs a candidacy can have: the 26 states, DF and BR (docs/domain-model.md, 3.5)."""


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


def normalize_candidate_uf(value: object) -> UF:
    """``"ac"`` and ``"AC"`` are the same UF; ``BR`` is the UF of president; ZZ has no
    candidates."""
    text = str(value).strip().upper() if value is not None else ""
    try:
        uf = UF(text)
    except ValueError:
        raise InvalidQuery(f"UF desconhecida: {value!r}") from None
    if uf not in CANDIDATE_UFS:
        raise InvalidQuery(f"UF sem candidatos: {text}")
    return uf


def normalize_ballot_office(value: object) -> Office:
    """``"deputado_federal"``, ``"Deputado Federal"`` and ``"DEPUTADO-FEDERAL"`` are the same
    office; a ticket office (vice, suplente) and anything else are ``InvalidQuery``."""
    text = strip_accents(str(value)).strip().lower() if value is not None else ""
    key = "_".join(text.replace("-", " ").split())
    try:
        office = Office(key)
    except ValueError:
        raise InvalidQuery(f"cargo desconhecido: {value!r}") from None
    if not office.is_ballot_office:
        raise InvalidQuery(
            f"cargo de chapa, não de urna: {office.value}; use {office.ticket_head.value}"
        )
    return office


def check_office_for_uf(office: Office, uf: UF) -> None:
    """The UF/office pairs that exist (docs/domain-model.md, 3.5)."""
    if office is Office.PRESIDENTE and uf is not UF.BR:
        raise InvalidQuery("presidente só existe com uf = BR")
    if office is not Office.PRESIDENTE and uf is UF.BR:
        raise InvalidQuery(f"BR é a UF apenas de presidente, não de {office.value}")
    if office is Office.DEPUTADO_DISTRITAL and uf is not UF.DF:
        raise InvalidQuery("deputado_distrital só existe no DF")
    if office is Office.DEPUTADO_ESTADUAL and uf is UF.DF:
        raise InvalidQuery("no DF o cargo é deputado_distrital, não deputado_estadual")


def normalize_offset(value: object) -> int:
    """``offset`` is a non-negative integer, also accepted as text."""
    if isinstance(value, bool):
        raise InvalidQuery(f"deslocamento inválido: {value!r}")
    if isinstance(value, int):
        number = value
    else:
        text = str(value).strip() if value is not None else ""
        if not text.isdigit():
            raise InvalidQuery(f"deslocamento inválido: {value!r}")
        number = int(text)
    if number < 0:
        raise InvalidQuery(f"deslocamento inválido: {value!r}")
    return number


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def search_text(value: object) -> str:
    """The form the index stores names in: accents stripped, upper case, single spaces."""
    return " ".join(strip_accents(str(value)).upper().split())


def normalize_text(value: object, label: str) -> str:
    """Free text for a search: trimmed, inner whitespace collapsed; empty is InvalidQuery.

    Accents and case are removed by the query itself, with the same DuckDB expression
    that built ``search_name``, so both sides normalize identically.
    """
    text = " ".join(str(value).split()) if value is not None else ""
    if not text:
        raise InvalidQuery(f"{label}: {value!r}")
    return text


def normalize_limit(value: object, maximum: int, default: int) -> int:
    """``limit`` within 1..``maximum``; absent is ``default``; anything else is InvalidQuery."""
    if value is None:
        return default
    limit = normalize_number(value, "limite inválido")
    if limit > maximum:
        raise InvalidQuery(f"limite inválido: {value!r}; o máximo é {maximum}")
    return limit
