"""The chain that ties a candidate's photo to the bytes the TSE published (ADR 0013).

The mirror names every object after the SHA-256 of its bytes, ``F<UF><SQ>_div-<sha256>.jpg``,
and the index records the same digest next to ``photo_url``. ``photo_problems`` re-derives the
chain from the index alone: it is what the ``validate`` gate and ``mirror-photos`` (after it
writes the index) both run, so a URL that does not carry its own recorded digest never leaves
the pipeline.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import SplitResult, urlsplit

import duckdb

_KEY_RE = re.compile(r"^F(?P<uf>[A-Z]{2})(?P<sq_candidato>\d+)_div-(?P<sha256>[0-9a-f]{64})\.jpg$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_LISTED = 5


def photo_key(uf: str, sq_candidato: int, content: bytes) -> tuple[str, str]:
    """The object key of a photo and the SHA-256 hex digest it embeds."""
    digest = hashlib.sha256(content).hexdigest()
    return f"F{uf.upper()}{sq_candidato}_div-{digest}.jpg", digest


def photo_problems(index_path: Path, public_domain: str | None = None) -> list[str]:
    """Every way the ``photo_url``/``photo_sha256`` pairs of the index break the chain.

    Empty when every round of each candidacy has the same pair, both columns are null
    (no photo mirrored) or both are set, the digest is 64 lowercase hex, and the URL
    points to the key of that ``sq_candidato``, UF and digest. A configured public
    domain also fixes the exact base URL.
    """
    conn = duckdb.connect(str(index_path), read_only=True)
    try:
        rows = conn.execute(
            "SELECT DISTINCT sq_candidato, uf, photo_url, photo_sha256 FROM candidates "
            "ORDER BY sq_candidato"
        ).fetchall()
    finally:
        conn.close()
    return photo_rows_problems(rows, public_domain)


def _http_url(url: str) -> SplitResult | None:
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        _ = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme not in {"https", "http"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or "?" in url
        or "#" in url
        or url != url.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in url)
    ):
        return None
    return parsed


def photo_public_domain_problem(public_domain: str) -> str | None:
    """Reject a public base URL that could not form a valid photo URL."""
    if _http_url(public_domain) is None:
        return "public domain must be an http(s) URL without userinfo, query or fragment"
    return None


def photo_rows_problems(
    rows: Iterable[tuple[int, str, str | None, str | None]],
    public_domain: str | None = None,
) -> list[str]:
    """Validate the photo pair of each candidacy, including consistency across rounds."""
    unpaired: list[int] = []
    malformed: list[int] = []
    mismatched: list[int] = []
    wrong_uf: list[int] = []
    invalid_url: list[int] = []
    wrong_domain: list[int] = []
    inconsistent: set[int] = set()
    pairs: dict[int, tuple[str | None, str | None]] = {}
    origins: set[tuple[str, str]] = set()
    for sq_candidato, uf, url, digest in rows:
        pair = (url, digest)
        if sq_candidato in pairs and pairs[sq_candidato] != pair:
            inconsistent.add(sq_candidato)
        else:
            pairs[sq_candidato] = pair
        if url is None and digest is None:
            continue
        if url is None or digest is None:
            unpaired.append(sq_candidato)
            continue
        parsed = _http_url(url)
        if parsed is None:
            invalid_url.append(sq_candidato)
            continue
        origins.add((parsed.scheme, parsed.netloc))
        match = _KEY_RE.fullmatch(parsed.path.rsplit("/", 1)[-1])
        if match is None or _SHA256_RE.match(digest) is None:
            malformed.append(sq_candidato)
        elif match["sq_candidato"] != str(sq_candidato) or match["sha256"] != digest:
            mismatched.append(sq_candidato)
        elif match["uf"] != uf:
            wrong_uf.append(sq_candidato)
        elif public_domain is not None and url != f"{public_domain.rstrip('/')}/{match.group(0)}":
            wrong_domain.append(sq_candidato)
    problems = []
    for label, sqs in (
        ("photo_url and photo_sha256 differ across rounds of one candidacy", sorted(inconsistent)),
        ("photo_url and photo_sha256 not set together", unpaired),
        ("photo_url must be an http(s) URL without userinfo, query or fragment", invalid_url),
        ("photo_url is not a content-addressed key or the digest is malformed", malformed),
        ("photo_url does not carry the recorded photo_sha256 of its candidacy", mismatched),
        ("photo_url key UF does not match the candidacy UF", wrong_uf),
        ("photo_url does not match the configured public domain and key", wrong_domain),
    ):
        if sqs:
            shown = ", ".join(str(sq) for sq in sqs[:_MAX_LISTED])
            more = f" (+{len(sqs) - _MAX_LISTED} more)" if len(sqs) > _MAX_LISTED else ""
            problems.append(f"{label}: {len(sqs)} candidacies, e.g. {shown}{more}")
    if len(origins) > 1:
        problems.append("photo_url values do not share one scheme and host")
    return problems
