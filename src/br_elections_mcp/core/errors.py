"""The only two errors that escape the core (codebase-design 3.1)."""


class InvalidQuery(ValueError):
    """The input is outside the domain: unknown UF, non-numeric zone, round out of range."""


class IndexUnavailable(RuntimeError):
    """The index is missing, corrupted or not open."""
