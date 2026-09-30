"""Stage 4, mirror_photos: sync candidate JPEGs from the per-UF TSE ZIPs to R2.

`mirror_photos(zips, bucket, public_domain=...)` reads each `PhotoZip` (a per-UF
`foto_cand2026_{UF}_div.zip`, already on disk), and through the `PhotoBucketClient` port
(`pipeline.bucket`) writes only what the TSE currently publishes and removes what
disappeared from the source since the last run (ADR 0004, ADR 0005).

Every object is named after the SHA-256 of its bytes, `F{UF}{SQ}_div-{sha256}.jpg`
(ADR 0013), so a key can only ever hold one content. The run is in phases, and nothing is
written before the checks that can refuse it:

1. Hash every photo in the ZIPs. A key already in the bucket whose checksum (R2's ETag, the
   MD5 of the bytes) differs from the ZIP's photo means the object was replaced or corrupted
   behind our back: the run fails with `PhotoIntegrityError`, having uploaded and deleted
   nothing, and never overwrites it.
2. Upload the keys that are not in the bucket yet (each JPEG is read into memory from the ZIP
   and written once to a temporary directory removed at the end of the run; no image bytes
   are persisted anywhere else).
3. List the bucket again and require every key of this run to be there with the expected
   checksum; only then delete the keys no ZIP of this run explains.

Returns the public URL and the SHA-256 of every candidacy (`sq_candidato`) that ends this run
with a photo in the bucket, for `build.apply_photo_urls` to write into `index.duckdb`
(codebase-design 5, item 4). A photo has no round (docs/domain-model.md, 3.5): the URL
applies to every round of the `sq_candidato`.
"""

from __future__ import annotations

import hashlib
import re
import tempfile
import zipfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from br_elections_mcp.pipeline.bucket import PhotoBucketClient
from br_elections_mcp.pipeline.photo_integrity import (
    photo_key,
    photo_public_domain_problem,
    photo_rows_problems,
)

_PHOTO_NAME_RE = re.compile(r"^F(?P<uf>[A-Za-z]{2})(?P<sq_candidato>\d+)_div\.jpg$")
# The one non-photo entry every real ZIP carries (checked against AC and BR, 2026-09-29).
_README_NAME = "leiame.pdf"


class MirrorError(ValueError):
    """A photo ZIP does not match what `mirror_photos` expects; nothing was uploaded for it."""


class PhotoIntegrityError(MirrorError):
    """The bucket does not hold what the ZIPs say: an object was replaced or is missing."""


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

    photo_sha256s: dict[int, str]
    """``sq_candidato`` -> SHA-256 hex of the photo the URL's key embeds (ADR 0013)."""


def planned_photo_rows(
    zips: Iterable[PhotoZip],
    *,
    public_domain: str,
    candidate_ufs: Mapping[int, str],
) -> list[tuple[int, str, str, str]]:
    """Photo pairs the ZIPs would place in the index, before bucket access."""
    rows = []
    base_url = public_domain.rstrip("/")
    for photo_zip in zips:
        with zipfile.ZipFile(photo_zip.path) as zf:
            for info in zf.infolist():
                if info.is_dir() or Path(info.filename).name.lower() == _README_NAME:
                    continue
                sq_candidato = _parse_entry(photo_zip, info.filename)
                uf = photo_zip.uf.upper()
                index_uf = candidate_ufs.get(sq_candidato, uf)
                if uf != index_uf:
                    raise PhotoIntegrityError(
                        f"sq_candidato {sq_candidato}: ZIP UF {uf} "
                        f"does not match index UF {index_uf}"
                    )
                with zf.open(info) as fh:
                    key, digest = photo_key(uf, sq_candidato, fh.read())
                rows.append((sq_candidato, index_uf, f"{base_url}/{key}", digest))
    return rows


def mirror_photos(
    zips: Iterable[PhotoZip],
    bucket: PhotoBucketClient,
    *,
    public_domain: str,
    candidate_ufs: Mapping[int, str] | None = None,
) -> MirrorResult:
    """Sync `zips` to `bucket` and return what changed plus every current photo URL.

    Raises `MirrorError` on a ZIP entry that is not a `F{UF}{SQ_CANDIDATO}_div.jpg` JPEG
    (the `leiame.pdf` every TSE ZIP carries is ignored), whose UF does not match the
    `PhotoZip.uf` it came from, or when one `sq_candidato` has two different photos: nothing
    is guessed. Raises `PhotoIntegrityError` when an object already in the bucket does not
    hold the bytes its key promises, before anything is written, or when the bucket does not
    hold this run's photos after the upload, before anything is deleted. When ``candidate_ufs``
    is given, a ZIP photo for an indexed candidacy with a different UF also fails before writes.
    """
    domain_problem = photo_public_domain_problem(public_domain)
    if domain_problem:
        raise PhotoIntegrityError(domain_problem)
    remote = bucket.list_objects()
    expected_md5: dict[str, str] = {}
    digest_of_key: dict[str, str] = {}
    uploaded: list[str] = []
    skipped: list[str] = []
    replaced: list[str] = []
    photo_urls: dict[int, str] = {}
    photo_sha256s: dict[int, str] = {}
    planned_rows: list[tuple[int, str, str, str]] = []
    base_url = public_domain.rstrip("/")

    with tempfile.TemporaryDirectory(prefix=".mirror-photos-") as tmp_name:
        tmp_dir = Path(tmp_name)
        for photo_zip in zips:
            with zipfile.ZipFile(photo_zip.path) as zf:
                for info in zf.infolist():
                    if info.is_dir() or Path(info.filename).name.lower() == _README_NAME:
                        continue
                    sq_candidato = _parse_entry(photo_zip, info.filename)
                    if (
                        candidate_ufs is not None
                        and sq_candidato in candidate_ufs
                        and photo_zip.uf.upper() != candidate_ufs[sq_candidato]
                    ):
                        raise PhotoIntegrityError(
                            f"sq_candidato {sq_candidato}: ZIP UF {photo_zip.uf.upper()} "
                            f"does not match index UF {candidate_ufs[sq_candidato]}"
                        )
                    with zf.open(info) as fh:
                        content = fh.read()
                    key, digest = photo_key(photo_zip.uf, sq_candidato, content)
                    planned_rows.append(
                        (
                            sq_candidato,
                            candidate_ufs.get(sq_candidato, photo_zip.uf.upper())
                            if candidate_ufs is not None
                            else photo_zip.uf.upper(),
                            f"{base_url}/{key}",
                            digest,
                        )
                    )
                    if photo_sha256s.setdefault(sq_candidato, digest) != digest:
                        raise MirrorError(
                            f"{photo_zip.path.name}: {info.filename!r} is a second, different "
                            f"photo for sq_candidato {sq_candidato}"
                        )
                    if key in expected_md5:
                        continue
                    expected_md5[key] = hashlib.md5(content).hexdigest()
                    digest_of_key[key] = digest
                    photo_urls[sq_candidato] = f"{base_url}/{key}"
                    if key not in remote:
                        dest = tmp_dir / key
                        dest.write_bytes(content)
                        uploaded.append(key)
                    elif remote[key] == expected_md5[key]:
                        skipped.append(key)
                    else:
                        replaced.append(key)
        if replaced:
            raise PhotoIntegrityError(
                f"{len(replaced)} objects in the bucket do not hold the bytes their key "
                f"promises (replaced or corrupted), e.g. {', '.join(replaced[:3])}; "
                "refusing to overwrite them, nothing was uploaded or deleted"
            )
        problems = photo_rows_problems(planned_rows, public_domain)
        if problems:
            raise PhotoIntegrityError("; ".join(problems))
        for key in uploaded:
            bucket.put(key, tmp_dir / key, digest_of_key[key])

    after = bucket.list_objects()
    missing = [key for key in expected_md5 if key not in after]
    changed = [key for key, md5 in expected_md5.items() if key in after and after[key] != md5]
    if missing or changed:
        raise PhotoIntegrityError(
            f"after the upload the bucket is missing {len(missing)} and holds different bytes "
            f"for {len(changed)} of this run's photos, e.g. "
            f"{', '.join((missing + changed)[:3])}; nothing was deleted"
        )
    removed = [key for key in after if key not in expected_md5]
    for key in removed:
        bucket.delete(key)

    return MirrorResult(
        uploaded=tuple(uploaded),
        skipped=tuple(skipped),
        removed=tuple(removed),
        photo_urls=photo_urls,
        photo_sha256s=photo_sha256s,
    )


def _parse_entry(photo_zip: PhotoZip, filename: str) -> int:
    """The `sq_candidato` of a `F{UF}{SQ_CANDIDATO}_div.jpg` entry of `photo_zip`."""
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
    return int(match.group("sq_candidato"))
