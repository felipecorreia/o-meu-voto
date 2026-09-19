"""CurlCffiDownloader over a fake session: the mapping from response to result.

No network: the session is a stub. The real TSE access is the manual workflow
in .github/workflows/tse-access-test.yml, not a test.
"""

from pathlib import Path

import pytest

from br_elections_mcp.pipeline.downloader import CurlCffiDownloader, DownloadError

pytest.importorskip("curl_cffi", reason="the pipeline dependency group is not installed")


class _FakeResponse:
    def __init__(self, status: int, chunks: list[bytes], headers: dict[str, str]) -> None:
        self.status_code = status
        self.headers = headers
        self._chunks = chunks
        self.closed = False

    def iter_content(self, chunk_size: int):
        yield from self._chunks

    def close(self) -> None:
        self.closed = True


class _FakeSession:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, dict]] = []

    def get(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def test_200_streams_the_body_to_destination_and_reports_size(tmp_path: Path):
    response = _FakeResponse(
        200, [b"ab", b"cd"], {"last-modified": "Thu, 18 Sep 2026 06:25:00 GMT"}
    )
    session = _FakeSession(response)

    result = CurlCffiDownloader(session=session).download("https://h/x.zip", tmp_path / "x.zip")

    assert result.ok
    assert result.size == 4
    assert result.last_modified == "Thu, 18 Sep 2026 06:25:00 GMT"
    assert (tmp_path / "x.zip").read_bytes() == b"abcd"
    assert not (tmp_path / "x.zip.part").exists()
    assert response.closed
    (url, kwargs) = session.calls[0]
    assert url == "https://h/x.zip"
    assert kwargs["stream"] is True


def test_403_is_returned_as_a_result_and_writes_nothing(tmp_path: Path):
    response = _FakeResponse(403, [b"<html>Access Denied</html>"], {})

    result = CurlCffiDownloader(session=_FakeSession(response)).download(
        "https://h/x.zip", tmp_path / "x.zip"
    )

    assert result.status == 403
    assert not result.ok
    assert result.size is None
    assert list(tmp_path.iterdir()) == []
    assert response.closed


def test_transport_error_becomes_download_error(tmp_path: Path):
    from curl_cffi import CurlError

    class _Session:
        def get(self, url: str, **kwargs):
            raise CurlError("Failed to connect")

    with pytest.raises(DownloadError, match=r"https://h/x\.zip: .*Failed to connect"):
        CurlCffiDownloader(session=_Session()).download("https://h/x.zip", tmp_path / "x.zip")
    assert list(tmp_path.iterdir()) == []
