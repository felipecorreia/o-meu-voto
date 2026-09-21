"""The bucket ports of the ``publish`` and ``mirror_photos`` stages and their adapters.

``BucketClient`` is what ``publish`` asks of the index bucket: put a local file under an
object name and get an object back into a local file. ``GcsBucketClient`` is the
production adapter (the index bucket of ADR 0005); ``LocalDirectoryBucketClient`` writes
the same object layout under a directory, for local runs and the CLI tests. The tests of
the stage itself use an in-memory fake that records the order of writes.

``PhotoBucketClient`` is what `mirror_photos` asks of the photo bucket. `R2BucketClient`
is the production adapter: R2 is Cloudflare's S3-compatible object storage (ADR 0005),
reached with `boto3`'s S3 client pointed at the account's R2 endpoint. `boto3` is
imported lazily so importing this module never requires the `pipeline` dependency group;
the service image does not carry it. `FakePhotoBucketClient` is an in-memory stand-in and
what every test uses; no test touches the network.

Contract shared by both photo adapters: `list_objects()` returns every key currently in
the bucket mapped to a content checksum from the store itself (R2's ETag, no extra
round trip per key), so `mirror_photos` can tell an unchanged photo from a changed one
by comparing it against a freshly computed local MD5 hex digest, without downloading it
back. A multipart upload's ETag contains a `-` and a local MD5 digest never does, so it
never matches and the photo is always re-uploaded rather than assumed unchanged.
`put(key, path, checksum)` uploads `path`'s bytes to `key` and stores `checksum` (a
SHA-256, for future auditability) as metadata; `delete(key)` removes one object.

Nothing here is imported by the service.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Protocol

_CHECKSUM_METADATA_KEY = "sha256"


class BucketClient(Protocol):
    """What ``publish`` asks of the index bucket."""

    def upload(self, local_path: Path, object_name: str) -> None:
        """Write ``local_path`` as ``object_name``, replacing any previous object."""
        ...

    def download(self, object_name: str, local_path: Path) -> bool:
        """Write ``object_name`` into ``local_path``; False (and no file) when it does not exist."""
        ...


class LocalDirectoryBucketClient:
    """A bucket on the local filesystem: ``object_name`` becomes a path under ``root``.

    A directory published this way is exactly what ``LocalDirectoryIndexSource``
    serves, so a local pipeline run can feed a local service.
    """

    def __init__(self, root: Path) -> None:
        self._root = root

    def _resolve(self, object_name: str) -> Path:
        if object_name.startswith("/"):
            raise ValueError(f"object name must be relative: {object_name!r}")
        root = self._root.resolve()
        target = (root / object_name).resolve()
        if root != target and root not in target.parents:
            raise ValueError(f"object name escapes the bucket root: {object_name!r}")
        return target

    def upload(self, local_path: Path, object_name: str) -> None:
        target = self._resolve(object_name)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f".{target.name}.tmp")
        tmp.write_bytes(local_path.read_bytes())
        tmp.replace(target)

    def download(self, object_name: str, local_path: Path) -> bool:
        source = self._resolve(object_name)
        if not source.is_file():
            return False
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(source.read_bytes())
        return True


class GcsBucketClient:
    """The index bucket on Google Cloud Storage.

    Credentials come from the environment (``GOOGLE_APPLICATION_CREDENTIALS``
    or the runner's authenticated account); the library is imported lazily so
    the service and the tests never need it installed.
    """

    def __init__(self, bucket_name: str) -> None:
        from google.cloud import storage

        self._bucket = storage.Client().bucket(bucket_name)

    def upload(self, local_path: Path, object_name: str) -> None:
        self._bucket.blob(object_name).upload_from_filename(str(local_path))

    def download(self, object_name: str, local_path: Path) -> bool:
        from google.api_core.exceptions import NotFound

        blob = self._bucket.blob(object_name)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = local_path.with_name(f".{local_path.name}.tmp")
        try:
            blob.download_to_filename(str(tmp))
        except NotFound:
            tmp.unlink(missing_ok=True)
            return False
        tmp.replace(local_path)
        return True


class PhotoBucketClient(Protocol):
    """Port: an object store keyed by name, with a checksum attached to each object."""

    def list_objects(self) -> dict[str, str]:
        """Every key currently in the bucket, mapped to a checksum comparable against a
        freshly computed local MD5 hex digest (equal means unchanged). A value that can
        never equal such a digest, such as a multipart ETag containing `-`, means the
        object must always be treated as changed."""
        ...

    def put(self, key: str, path: Path, checksum: str) -> None:
        """Upload `path`'s bytes to `key`, storing `checksum` as the object's metadata."""
        ...

    def delete(self, key: str) -> None:
        """Remove `key`. A missing key is not an error."""
        ...


class R2BucketClient:
    """Production adapter: an S3-compatible bucket on Cloudflare R2.

    `client` is injectable for tests that stub `boto3`'s S3 client without touching the
    network; production code leaves it unset and gets a real one.
    """

    def __init__(
        self,
        *,
        endpoint_url: str,
        bucket: str,
        access_key_id: str,
        secret_access_key: str,
        prefix: str = "",
        client: Any | None = None,
    ) -> None:
        self._bucket = bucket
        self._prefix = prefix
        if client is None:
            import boto3

            client = boto3.client(
                "s3",
                endpoint_url=endpoint_url,
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
            )
        self._client = client

    def list_objects(self) -> dict[str, str]:
        objects: dict[str, str] = {}
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=self._prefix):
            for entry in page.get("Contents", ()):
                key = entry["Key"]
                etag = entry["ETag"].strip('"')
                objects[key.removeprefix(self._prefix)] = etag
        return objects

    def put(self, key: str, path: Path, checksum: str) -> None:
        self._client.upload_file(
            str(path),
            self._bucket,
            self._prefix + key,
            ExtraArgs={
                "ContentType": "image/jpeg",
                "Metadata": {_CHECKSUM_METADATA_KEY: checksum},
            },
        )

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=self._prefix + key)


class FakePhotoBucketClient:
    """Test adapter: an in-memory bucket. `objects` exposes the stored bytes for assertions."""

    def __init__(self, initial: dict[str, tuple[bytes, str]] | None = None) -> None:
        self.objects: dict[str, tuple[bytes, str]] = dict(initial or {})

    def list_objects(self) -> dict[str, str]:
        return {key: hashlib.md5(content).hexdigest() for key, (content, _) in self.objects.items()}

    def put(self, key: str, path: Path, checksum: str) -> None:
        self.objects[key] = (path.read_bytes(), checksum)

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)
