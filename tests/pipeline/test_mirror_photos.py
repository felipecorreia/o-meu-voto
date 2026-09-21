"""The mirror_photos stage over a FakePhotoBucketClient. No test here touches the network."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from br_elections_mcp.pipeline.bucket import FakePhotoBucketClient
from br_elections_mcp.pipeline.mirror_photos import MirrorError, PhotoZip, mirror_photos


def _make_zip(path: Path, entries: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)


def _checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def test_new_photo_is_uploaded(tmp_path: Path):
    zip_path = tmp_path / "foto_cand2026_AC_div.zip"
    _make_zip(zip_path, {"FAC10000000001_div.jpg": b"photo-bytes"})
    bucket = FakePhotoBucketClient()

    result = mirror_photos(
        [PhotoZip(uf="AC", path=zip_path)], bucket, public_domain="https://fotos.example.org"
    )

    assert result.uploaded == ("FAC10000000001_div.jpg",)
    assert result.skipped == ()
    assert result.removed == ()
    assert result.photo_urls == {10000000001: "https://fotos.example.org/FAC10000000001_div.jpg"}
    stored_bytes, stored_checksum = bucket.objects["FAC10000000001_div.jpg"]
    assert stored_bytes == b"photo-bytes"
    assert stored_checksum == _checksum(b"photo-bytes")


def test_unchanged_photo_is_skipped(tmp_path: Path):
    zip_path = tmp_path / "foto_cand2026_AC_div.zip"
    content = b"same-bytes"
    _make_zip(zip_path, {"FAC10000000001_div.jpg": content})
    bucket = FakePhotoBucketClient({"FAC10000000001_div.jpg": (content, _checksum(content))})

    result = mirror_photos(
        [PhotoZip(uf="AC", path=zip_path)], bucket, public_domain="https://fotos.example.org"
    )

    assert result.uploaded == ()
    assert result.skipped == ("FAC10000000001_div.jpg",)
    assert result.removed == ()
    assert result.photo_urls == {10000000001: "https://fotos.example.org/FAC10000000001_div.jpg"}


def test_changed_photo_is_reuploaded(tmp_path: Path):
    zip_path = tmp_path / "foto_cand2026_AC_div.zip"
    _make_zip(zip_path, {"FAC10000000001_div.jpg": b"new-bytes"})
    bucket = FakePhotoBucketClient(
        {"FAC10000000001_div.jpg": (b"old-bytes", _checksum(b"old-bytes"))}
    )

    result = mirror_photos(
        [PhotoZip(uf="AC", path=zip_path)], bucket, public_domain="https://fotos.example.org"
    )

    assert result.uploaded == ("FAC10000000001_div.jpg",)
    assert result.skipped == ()
    assert bucket.objects["FAC10000000001_div.jpg"][0] == b"new-bytes"


def test_photo_gone_from_source_is_removed_from_the_bucket(tmp_path: Path):
    zip_path = tmp_path / "foto_cand2026_AC_div.zip"
    _make_zip(zip_path, {"FAC10000000001_div.jpg": b"still-here"})
    bucket = FakePhotoBucketClient(
        {
            "FAC10000000001_div.jpg": (b"still-here", _checksum(b"still-here")),
            "FAC10000000002_div.jpg": (b"gone-now", _checksum(b"gone-now")),
        }
    )

    result = mirror_photos(
        [PhotoZip(uf="AC", path=zip_path)], bucket, public_domain="https://fotos.example.org"
    )

    assert result.removed == ("FAC10000000002_div.jpg",)
    assert "FAC10000000002_div.jpg" not in bucket.objects
    assert 10000000002 not in result.photo_urls


def test_photo_urls_cover_every_uf_processed(tmp_path: Path):
    ac_zip = tmp_path / "foto_cand2026_AC_div.zip"
    sp_zip = tmp_path / "foto_cand2026_SP_div.zip"
    _make_zip(ac_zip, {"FAC10000000001_div.jpg": b"ac-photo"})
    _make_zip(sp_zip, {"FSP20000000009_div.jpg": b"sp-photo"})
    bucket = FakePhotoBucketClient()

    result = mirror_photos(
        [PhotoZip(uf="AC", path=ac_zip), PhotoZip(uf="SP", path=sp_zip)],
        bucket,
        public_domain="https://fotos.example.org/",
    )

    assert result.photo_urls == {
        10000000001: "https://fotos.example.org/FAC10000000001_div.jpg",
        20000000009: "https://fotos.example.org/FSP20000000009_div.jpg",
    }


def test_unexpected_entry_fails_loudly(tmp_path: Path):
    zip_path = tmp_path / "foto_cand2026_AC_div.zip"
    _make_zip(zip_path, {"leiame.pdf": b"readme"})

    with pytest.raises(MirrorError, match=r"leiame\.pdf"):
        mirror_photos(
            [PhotoZip(uf="AC", path=zip_path)],
            FakePhotoBucketClient(),
            public_domain="https://fotos.example.org",
        )


def test_entry_uf_mismatch_fails_loudly(tmp_path: Path):
    zip_path = tmp_path / "foto_cand2026_AC_div.zip"
    _make_zip(zip_path, {"FSP10000000001_div.jpg": b"wrong-uf"})

    with pytest.raises(MirrorError, match="does not match UF 'AC'"):
        mirror_photos(
            [PhotoZip(uf="AC", path=zip_path)],
            FakePhotoBucketClient(),
            public_domain="https://fotos.example.org",
        )


class _MultipartEtagBucketClient:
    """A PhotoBucketClient stub whose list_objects() reports a multipart-style ETag,
    to prove mirror_photos never treats such a value as a match."""

    def __init__(self, key: str, etag: str) -> None:
        self._key = key
        self._etag = etag
        self.put_calls: list[str] = []

    def list_objects(self) -> dict[str, str]:
        return {self._key: self._etag}

    def put(self, key: str, path: Path, checksum: str) -> None:
        self.put_calls.append(key)

    def delete(self, key: str) -> None:
        raise AssertionError("not expected to be called")


def test_multipart_etag_is_never_treated_as_a_match(tmp_path: Path):
    zip_path = tmp_path / "foto_cand2026_AC_div.zip"
    content = b"photo-bytes"
    _make_zip(zip_path, {"FAC10000000001_div.jpg": content})
    multipart_etag = hashlib.md5(content).hexdigest() + "-2"
    bucket = _MultipartEtagBucketClient("FAC10000000001_div.jpg", multipart_etag)

    result = mirror_photos(
        [PhotoZip(uf="AC", path=zip_path)], bucket, public_domain="https://fotos.example.org"
    )

    assert result.uploaded == ("FAC10000000001_div.jpg",)
    assert result.skipped == ()
    assert bucket.put_calls == ["FAC10000000001_div.jpg"]


def test_no_image_bytes_are_left_behind_after_the_run(tmp_path: Path):
    zip_path = tmp_path / "foto_cand2026_AC_div.zip"
    _make_zip(zip_path, {"FAC10000000001_div.jpg": b"photo-bytes"})

    mirror_photos(
        [PhotoZip(uf="AC", path=zip_path)],
        FakePhotoBucketClient(),
        public_domain="https://fotos.example.org",
    )

    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".mirror-photos-")]
    assert leftovers == []
