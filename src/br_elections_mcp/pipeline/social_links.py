"""Turn candidacy-declared free text into bounded HTTP(S) links at ingestion."""

import ipaddress
import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit

MAX_SOCIAL_LINKS = 10
MAX_SOCIAL_URL_LENGTH = 256
_HOST_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")


def normalize_social_url(raw: str) -> str | None:
    """Reject prose and unsafe URL forms without interpreting or fetching their content.

    Scheme and host are case-insensitive; path, query and fragment retain their case.
    Bare domain names gain HTTPS. Credentials, whitespace, controls and literal markup
    delimiters are not part of the accepted social-link format.
    """
    if not raw or len(raw) > MAX_SOCIAL_URL_LENGTH:
        return None
    if any(
        ch.isspace() or unicodedata.category(ch).startswith("C") or ch in "\"'<>\\`" for ch in raw
    ):
        return None
    explicit_scheme = raw.lower().startswith(("http://", "https://"))
    try:
        url = urlsplit(raw if explicit_scheme else "https://" + raw)
        if url.scheme not in ("http", "https") or not url.hostname:
            return None
        if url.username is not None or url.password is not None:
            return None
        host = url.hostname.encode("idna").decode("ascii").lower()
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if len(host) > 253 or not all(
                _HOST_LABEL.fullmatch(label) for label in host.split(".")
            ):
                return None
            if not explicit_scheme and ("." not in host or not host.split(".")[-1].isalpha()):
                return None
        port = url.port  # Also rejects invalid and out-of-range ports.
        if ":" in host:
            host = f"[{host}]"
        if port is not None:
            host += f":{port}"
        normalized = urlunsplit((url.scheme, host, url.path, url.query, url.fragment))
    except (ValueError, UnicodeError):
        return None
    return normalized if len(normalized) <= MAX_SOCIAL_URL_LENGTH else None
