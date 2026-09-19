"""The `Downloader` port of the fetch stage and its two adapters.

`CurlCffiDownloader` is the production adapter: it impersonates a browser's
TLS/HTTP2 fingerprint because the TSE's WAF (Akamai) answers 403 to plain HTTP
clients (ADR 0003). `LocalFilesDownloader` serves files from a directory and is
what every test uses; no test touches the network.

Contract shared by both adapters: `download(url, destination)` writes the body
to `destination` only when the response is 200, so a WAF error page is never
mistaken for a ZIP; any other HTTP status is a result, returned as is, never an
exception. Transport failures (DNS, TLS, timeout) raise `DownloadError`.
"""

from __future__ import annotations

import email.utils
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

HTTP_OK = 200
DEFAULT_IMPERSONATE = "chrome"
# Seconds: connect, then read. The largest ZIP is ~90 MB (docs/domain-model.md).
DEFAULT_TIMEOUT: tuple[float, float] = (30.0, 600.0)
_CHUNK_SIZE = 1 << 20


class DownloadError(RuntimeError):
    """The request never produced an HTTP status (DNS, TLS, timeout, reset)."""


@dataclass(frozen=True, slots=True)
class DownloadResult:
    """What one download returned: the HTTP status and, on 200, what was written."""

    url: str
    status: int
    last_modified: str | None = None
    size: int | None = None

    @property
    def ok(self) -> bool:
        return self.status == HTTP_OK


class Downloader(Protocol):
    """Port: fetch one URL into one file."""

    def download(self, url: str, destination: Path) -> DownloadResult:
        """Write the body of `url` to `destination` when the status is 200.

        Returns the status either way; raises `DownloadError` only when there
        is no status to return.
        """
        ...


class CurlCffiDownloader:
    """Production adapter: `curl_cffi` with browser impersonation (ADR 0003).

    `curl_cffi` is imported lazily so that importing this module never requires
    the `pipeline` dependency group; the service image does not carry it.
    """

    def __init__(
        self,
        *,
        impersonate: str = DEFAULT_IMPERSONATE,
        timeout: tuple[float, float] = DEFAULT_TIMEOUT,
        session: Any | None = None,
    ) -> None:
        self._timeout = timeout
        if session is None:
            from curl_cffi import requests

            session = requests.Session(impersonate=impersonate)
        self._session = session

    def download(self, url: str, destination: Path) -> DownloadResult:
        from curl_cffi import CurlError

        try:
            response = self._session.get(url, stream=True, timeout=self._timeout)
        except CurlError as exc:
            raise DownloadError(f"{url}: {exc}") from exc
        try:
            status = int(response.status_code)
            last_modified = response.headers.get("last-modified")
            if status != HTTP_OK:
                return DownloadResult(url=url, status=status, last_modified=last_modified)
            try:
                size = _write_atomically(response.iter_content(chunk_size=_CHUNK_SIZE), destination)
            except CurlError as exc:
                raise DownloadError(f"{url}: {exc}") from exc
        finally:
            response.close()
        return DownloadResult(url=url, status=status, last_modified=last_modified, size=size)


class LocalFilesDownloader:
    """Test adapter: answers each URL with the file of the same name under `root`.

    A missing file is a 404. `statuses` forces a status for a URL (a 403, for
    instance) so the failure paths of `fetch` can be exercised offline.
    """

    def __init__(self, root: Path, *, statuses: Mapping[str, int] | None = None) -> None:
        self._root = root
        self._statuses = dict(statuses or {})

    def download(self, url: str, destination: Path) -> DownloadResult:
        source = self._root / Path(urlsplit(url).path).name
        if url in self._statuses:
            return DownloadResult(url=url, status=self._statuses[url])
        if not source.is_file():
            return DownloadResult(url=url, status=404)
        stat = source.stat()
        last_modified = email.utils.formatdate(stat.st_mtime, usegmt=True)
        shutil.copyfile(source, destination)
        return DownloadResult(
            url=url, status=HTTP_OK, last_modified=last_modified, size=stat.st_size
        )


def _write_atomically(chunks: Any, destination: Path) -> int:
    """Stream `chunks` into `destination` through a `.part` file; never leave a half file."""
    part = destination.with_name(destination.name + ".part")
    size = 0
    try:
        with part.open("wb") as fh:
            for chunk in chunks:
                fh.write(chunk)
                size += len(chunk)
        part.replace(destination)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    return size
