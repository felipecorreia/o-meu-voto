"""R2BucketClient over a stub S3 client: the mapping from calls to results.

No network: the client is a stub, injected the same way CurlCffiDownloader takes a
stub session (test_downloader.py). Real R2 access has no automated test; it needs a
live bucket and credentials, which is a follow-up for whoever runs this stage for real.
"""

from __future__ import annotations

from pathlib import Path

from br_elections_mcp.pipeline.bucket import R2BucketClient


class _FakePaginator:
    def __init__(self, pages: list[dict]) -> None:
        self._pages = pages

    def paginate(self, **kwargs):
        return self._pages


class _FakeS3Client:
    def __init__(self, pages: list[dict]) -> None:
        self._pages = pages
        self.uploaded: list[tuple[str, str, str, dict]] = []
        self.deleted: list[tuple[str, str]] = []

    def get_paginator(self, name: str):
        assert name == "list_objects_v2"
        return _FakePaginator(self._pages)

    def upload_file(self, path: str, bucket: str, key: str, ExtraArgs: dict):
        self.uploaded.append((path, bucket, key, ExtraArgs))

    def delete_object(self, *, Bucket: str, Key: str):
        self.deleted.append((Bucket, Key))


def _client(pages, *, prefix: str = "") -> tuple[R2BucketClient, _FakeS3Client]:
    fake = _FakeS3Client(pages)
    bucket = R2BucketClient(
        endpoint_url="https://account.r2.cloudflarestorage.com",
        bucket="photos",
        access_key_id="id",
        secret_access_key="secret",
        prefix=prefix,
        client=fake,
    )
    return bucket, fake


def test_list_objects_maps_keys_to_their_etag_with_quotes_stripped():
    pages = [
        {
            "Contents": [
                {"Key": "a.jpg", "ETag": '"aaa"'},
                {"Key": "b.jpg", "ETag": '"bbb"'},
            ]
        }
    ]
    bucket, _ = _client(pages)

    assert bucket.list_objects() == {"a.jpg": "aaa", "b.jpg": "bbb"}


def test_list_objects_keeps_a_multipart_etag_intact():
    pages = [{"Contents": [{"Key": "a.jpg", "ETag": '"aaa-3"'}]}]
    bucket, _ = _client(pages)

    assert bucket.list_objects() == {"a.jpg": "aaa-3"}


def test_list_objects_is_empty_when_the_bucket_has_no_contents():
    bucket, _ = _client([{}])

    assert bucket.list_objects() == {}


def test_put_uploads_with_content_type_and_checksum_metadata(tmp_path: Path):
    path = tmp_path / "a.jpg"
    path.write_bytes(b"x")
    bucket, fake = _client([])

    bucket.put("a.jpg", path, "aaa")

    (call,) = fake.uploaded
    assert call == (
        str(path),
        "photos",
        "a.jpg",
        {"ContentType": "image/jpeg", "Metadata": {"sha256": "aaa"}},
    )


def test_delete_removes_the_key():
    bucket, fake = _client([])

    bucket.delete("a.jpg")

    assert fake.deleted == [("photos", "a.jpg")]


def test_list_objects_strips_the_prefix_from_returned_keys():
    pages = [{"Contents": [{"Key": "2026/a.jpg", "ETag": '"aaa"'}]}]
    bucket, _ = _client(pages, prefix="2026/")

    assert bucket.list_objects() == {"a.jpg": "aaa"}


def test_put_uploads_to_the_bare_key_joined_with_the_prefix(tmp_path: Path):
    path = tmp_path / "a.jpg"
    path.write_bytes(b"x")
    bucket, fake = _client([], prefix="2026/")

    bucket.put("a.jpg", path, "aaa")

    (call,) = fake.uploaded
    assert call == (
        str(path),
        "photos",
        "2026/a.jpg",
        {"ContentType": "image/jpeg", "Metadata": {"sha256": "aaa"}},
    )


def test_delete_removes_the_key_joined_with_the_prefix():
    bucket, fake = _client([], prefix="2026/")

    bucket.delete("a.jpg")

    assert fake.deleted == [("photos", "2026/a.jpg")]
