"""The ``BucketClient`` port of the ``publish`` stage and its adapters.

The stage needs two things from an object store: put a local file under an
object name and get an object back into a local file. ``GcsBucketClient`` is
the production adapter (the index bucket of ADR 0005); ``LocalDirectoryBucketClient``
writes the same object layout under a directory, for local runs and the CLI
tests. The tests of the stage itself use an in-memory fake that records the
order of writes. Nothing here is imported by the service.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


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
