"""Stage 4, mirror_photos: sync candidate JPEGs from the per-UF TSE ZIPs to R2.

`mirror_photos(zips, bucket, public_domain=...)` reads each `PhotoZip` (a per-UF
`foto_cand2026_{UF}_div.zip`, already on disk), and through the `PhotoBucketClient` port
(`pipeline.bucket`) writes only what the TSE currently publishes and removes what
disappeared from the source since the last run (ADR 0004, ADR 0005): a photo is unchanged
when its content's MD5 matches the checksum `bucket.list_objects()` reports for that key
(R2's ETag) and is skipped; new or changed ones are uploaded, and keys that were in the
bucket but not seen in this run's ZIPs are deleted. Every JPEG is read
into memory from the ZIP and, only when it needs uploading, written once to a
temporary directory removed at the end of the run; no image bytes are persisted
anywhere else.

Returns the public URL of every candidacy (`sq_candidato`) that ends this run with a
photo in the bucket, for `build.apply_photo_urls` to write into `index.duckdb`
(codebase-design 5, item 4). A photo has no round (docs/domain-model.md, 3.5): the URL
applies to every round of the `sq_candidato`.
"""

from __future__ import annotations

import hashlib
import re
import tempfile
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from br_elections_mcp.pipeline.bucket import PhotoBucketClient

_PHOTO_NAME_RE = re.compile(r"^F(?P<uf>[A-Za-z]{2})(?P<sq_candidato>\d+)_div\.jpg$")


class MirrorError(ValueError):
    """A photo ZIP does not match what `mirror_photos` expects; nothing was uploaded for it."""


@dataclass(frozen=True, slots=True)
class PhotoZip:
    """One per-UF photo ZIP, already on disk (docs/domain-model.md, section 2)."""

    uf: str
    path: Path


@dataclass(frozen=True, slots=True)
class MirrorResult:
    """What one run of `mirror_photos` did."""

    uploaded: tuple[str, ...]
    """Keys written this run: new or changed since the previous run."""

    skipped: tuple[str, ...]
    """Keys already in the bucket with the same content: left untouched."""

    removed: tuple[str, ...]
    """Keys that were in the bucket but not in any ZIP this run: deleted."""

    photo_urls: dict[int, str]
    """``sq_candidato`` -> public URL, for every candidacy with a photo in the bucket now."""


def mirror_photos(
    zips: Iterable[PhotoZip], bucket: PhotoBucketClient, *, public_domain: str
) -> MirrorResult:
    """Sync `zips` to `bucket` and return what changed plus every current photo URL.

    Raises `MirrorError` on a ZIP entry that is not a `F{UF}{SQ_CANDIDATO}_div.jpg` JPEG
    or whose UF does not match the `PhotoZip.uf` it came from: nothing is guessed.
    """
    remote = bucket.list_objects()
    seen: dict[str, str] = {}
    uploaded: list[str] = []
    skipped: list[str] = []
    photo_urls: dict[int, str] = {}
    base_url = public_domain.rstrip("/")

    with tempfile.TemporaryDirectory(prefix=".mirror-photos-") as tmp_name:
        tmp_dir = Path(tmp_name)
        for photo_zip in zips:
            with zipfile.ZipFile(photo_zip.path) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    key, sq_candidato = _parse_entry(photo_zip, info.filename)
                    with zf.open(info) as fh:
                        content = fh.read()
                    checksum = hashlib.sha256(content).hexdigest()
                    etag = hashlib.md5(content).hexdigest()
                    seen[key] = checksum
                    photo_urls[sq_candidato] = f"{base_url}/{key}"
                    if remote.get(key) == etag:
                        skipped.append(key)
                        continue
                    dest = tmp_dir / key
                    dest.write_bytes(content)
                    bucket.put(key, dest, checksum)
                    uploaded.append(key)

    removed = [key for key in remote if key not in seen]
    for key in removed:
        bucket.delete(key)

    return MirrorResult(
        uploaded=tuple(uploaded),
        skipped=tuple(skipped),
        removed=tuple(removed),
        photo_urls=photo_urls,
    )


def _parse_entry(photo_zip: PhotoZip, filename: str) -> tuple[str, int]:
    name = Path(filename).name
    if not name.lower().endswith(".jpg"):
        raise MirrorError(f"{photo_zip.path.name}: unexpected entry {filename!r}")
    match = _PHOTO_NAME_RE.match(name)
    if match is None:
        raise MirrorError(f"{photo_zip.path.name}: unexpected entry {filename!r}")
    uf = match.group("uf").upper()
    if uf != photo_zip.uf.upper():
        raise MirrorError(
            f"{photo_zip.path.name}: entry {filename!r} does not match UF {photo_zip.uf!r}"
        )
    return name, int(match.group("sq_candidato"))
