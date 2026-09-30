"""The mirror_photos stage over a FakePhotoBucketClient. No test here touches the network."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from br_elections_mcp.pipeline.bucket import FakePhotoBucketClient
from br_elections_mcp.pipeline.mirror_photos import (
    MirrorError,
    PhotoIntegrityError,
    PhotoZip,
    mirror_photos,
)
from br_elections_mcp.pipeline.photo_integrity import photo_key

DOMAIN = "https://fotos.example.org"


def _make_zip(path: Path, entries: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)


def _checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _key(uf: str, sq: int, content: bytes) -> str:
    return photo_key(uf, sq, content)[0]


def _ac_zip(tmp_path: Path, entries: dict[str, bytes]) -> PhotoZip:
    path = tmp_path / "foto_cand2026_AC_div.zip"
    _make_zip(path, entries)
    return PhotoZip(uf="AC", path=path)


class _SpyBucket(FakePhotoBucketClient):
    def __init__(self, initial: dict[str, tuple[bytes, str]] | None = None) -> None:
        super().__init__(initial)
        self.puts: list[str] = []
        self.deletes: list[str] = []

    def put(self, key: str, path: Path, checksum: str) -> None:
        self.puts.append(key)
        super().put(key, path, checksum)

    def delete(self, key: str) -> None:
        self.deletes.append(key)
        super().delete(key)


def test_new_photo_is_uploaded_under_a_key_that_embeds_its_sha256(tmp_path: Path):
    photo_zip = _ac_zip(tmp_path, {"FAC10000000001_div.jpg": b"photo-bytes"})
    bucket = FakePhotoBucketClient()
    key = f"FAC10000000001_div-{_checksum(b'photo-bytes')}.jpg"

    result = mirror_photos([photo_zip], bucket, public_domain=DOMAIN)

    assert result.uploaded == (key,)
    assert result.skipped == ()
    assert result.removed == ()
    assert result.photo_urls == {10000000001: f"{DOMAIN}/{key}"}
    assert result.photo_sha256s == {10000000001: _checksum(b"photo-bytes")}
    stored_bytes, stored_checksum = bucket.objects[key]
    assert stored_bytes == b"photo-bytes"
    assert stored_checksum == _checksum(b"photo-bytes")


def test_unchanged_photo_is_skipped(tmp_path: Path):
    content = b"same-bytes"
    photo_zip = _ac_zip(tmp_path, {"FAC10000000001_div.jpg": content})
    key = _key("AC", 10000000001, content)
    bucket = _SpyBucket({key: (content, _checksum(content))})

    result = mirror_photos([photo_zip], bucket, public_domain=DOMAIN)

    assert result.uploaded == ()
    assert result.skipped == (key,)
    assert result.removed == ()
    assert result.photo_urls == {10000000001: f"{DOMAIN}/{key}"}
    assert bucket.puts == []


def test_a_photo_the_tse_changed_gets_a_new_key_and_the_old_one_is_removed(tmp_path: Path):
    old_key = _key("AC", 10000000001, b"old-bytes")
    new_key = _key("AC", 10000000001, b"new-bytes")
    photo_zip = _ac_zip(tmp_path, {"FAC10000000001_div.jpg": b"new-bytes"})
    bucket = _SpyBucket({old_key: (b"old-bytes", _checksum(b"old-bytes"))})

    result = mirror_photos([photo_zip], bucket, public_domain=DOMAIN)

    assert result.uploaded == (new_key,)
    assert result.removed == (old_key,)
    assert result.photo_urls == {10000000001: f"{DOMAIN}/{new_key}"}
    assert set(bucket.objects) == {new_key}


def test_photo_gone_from_source_is_removed_from_the_bucket(tmp_path: Path):
    kept = _key("AC", 10000000001, b"still-here")
    gone = _key("AC", 10000000002, b"gone-now")
    photo_zip = _ac_zip(tmp_path, {"FAC10000000001_div.jpg": b"still-here"})
    bucket = FakePhotoBucketClient(
        {
            kept: (b"still-here", _checksum(b"still-here")),
            gone: (b"gone-now", _checksum(b"gone-now")),
        }
    )

    result = mirror_photos([photo_zip], bucket, public_domain=DOMAIN)

    assert result.removed == (gone,)
    assert gone not in bucket.objects
    assert 10000000002 not in result.photo_urls


def test_photo_urls_cover_every_uf_processed(tmp_path: Path):
    ac_zip = tmp_path / "foto_cand2026_AC_div.zip"
    sp_zip = tmp_path / "foto_cand2026_SP_div.zip"
    _make_zip(ac_zip, {"FAC10000000001_div.jpg": b"ac-photo"})
    _make_zip(sp_zip, {"FSP20000000009_div.jpg": b"sp-photo"})

    result = mirror_photos(
        [PhotoZip(uf="AC", path=ac_zip), PhotoZip(uf="SP", path=sp_zip)],
        FakePhotoBucketClient(),
        public_domain=DOMAIN + "/",
    )

    assert result.photo_urls == {
        10000000001: f"{DOMAIN}/{_key('AC', 10000000001, b'ac-photo')}",
        20000000009: f"{DOMAIN}/{_key('SP', 20000000009, b'sp-photo')}",
    }


def test_the_leiame_every_tse_zip_carries_is_ignored(tmp_path: Path):
    photo_zip = _ac_zip(
        tmp_path, {"leiame.pdf": b"readme", "FAC10000000001_div.jpg": b"photo-bytes"}
    )
    bucket = FakePhotoBucketClient()

    result = mirror_photos([photo_zip], bucket, public_domain=DOMAIN)

    assert result.uploaded == (_key("AC", 10000000001, b"photo-bytes"),)
    assert set(bucket.objects) == set(result.uploaded)


def test_unexpected_entry_fails_loudly(tmp_path: Path):
    photo_zip = _ac_zip(tmp_path, {"notes.pdf": b"something else"})

    with pytest.raises(MirrorError, match=r"notes\.pdf"):
        mirror_photos([photo_zip], FakePhotoBucketClient(), public_domain=DOMAIN)


def test_entry_uf_mismatch_fails_loudly(tmp_path: Path):
    photo_zip = _ac_zip(tmp_path, {"FSP10000000001_div.jpg": b"wrong-uf"})

    with pytest.raises(MirrorError, match="does not match UF 'AC'"):
        mirror_photos([photo_zip], FakePhotoBucketClient(), public_domain=DOMAIN)


def test_index_uf_mismatch_fails_before_any_bucket_mutation(tmp_path: Path):
    sq_candidato = 10000000001
    old_key = _key("AC", sq_candidato, b"old-photo")
    sp_zip = tmp_path / "foto_cand2026_SP_div.zip"
    _make_zip(sp_zip, {f"FSP{sq_candidato}_div.jpg": b"new-photo"})
    bucket = _SpyBucket({old_key: (b"old-photo", _checksum(b"old-photo"))})

    with pytest.raises(PhotoIntegrityError, match=f"{sq_candidato}: ZIP UF SP.*index UF AC"):
        mirror_photos(
            [PhotoZip(uf="SP", path=sp_zip)],
            bucket,
            public_domain=DOMAIN,
            candidate_ufs={sq_candidato: "AC"},
        )

    assert bucket.puts == []
    assert bucket.deletes == []
    assert bucket.objects == {old_key: (b"old-photo", _checksum(b"old-photo"))}


def test_matching_index_uf_allows_the_photo(tmp_path: Path):
    sq_candidato = 10000000001
    photo_zip = _ac_zip(tmp_path, {f"FAC{sq_candidato}_div.jpg": b"photo"})
    bucket = _SpyBucket()

    result = mirror_photos(
        [photo_zip], bucket, public_domain=DOMAIN, candidate_ufs={sq_candidato: "AC"}
    )

    assert result.uploaded == (_key("AC", sq_candidato, b"photo"),)
    assert bucket.puts == list(result.uploaded)


def test_two_different_photos_for_one_candidacy_fail_loudly(tmp_path: Path):
    ac_zip = tmp_path / "foto_cand2026_AC_div.zip"
    ac_again = tmp_path / "again" / "foto_cand2026_AC_div.zip"
    ac_again.parent.mkdir()
    _make_zip(ac_zip, {"FAC10000000001_div.jpg": b"one"})
    _make_zip(ac_again, {"FAC10000000001_div.jpg": b"another"})
    bucket = _SpyBucket()

    with pytest.raises(MirrorError, match="second, different photo for sq_candidato"):
        mirror_photos(
            [PhotoZip(uf="AC", path=ac_zip), PhotoZip(uf="AC", path=ac_again)],
            bucket,
            public_domain=DOMAIN,
        )

    assert bucket.puts == []


def test_an_object_replaced_in_the_bucket_fails_the_run_and_nothing_is_written(tmp_path: Path):
    """Someone with write access swapped the bytes behind a key the index points to."""
    content = b"the-real-photo"
    swapped = _key("AC", 10000000001, content)
    photo_zip = _ac_zip(
        tmp_path,
        {"FAC10000000001_div.jpg": content, "FAC10000000002_div.jpg": b"a-new-photo"},
    )
    stale = _key("AC", 10000000009, b"stale")
    bucket = _SpyBucket(
        {
            swapped: (b"an-attacker-photo", _checksum(content)),  # metadata lies, bytes differ
            stale: (b"stale", _checksum(b"stale")),
        }
    )

    with pytest.raises(PhotoIntegrityError, match=r"refusing to overwrite.*nothing was uploaded"):
        mirror_photos([photo_zip], bucket, public_domain=DOMAIN)

    assert bucket.puts == []
    assert bucket.deletes == []
    assert bucket.objects[swapped][0] == b"an-attacker-photo"
    assert stale in bucket.objects


class _FixedEtagBucket(_SpyBucket):
    """Reports a chosen ETag for every key, as a bucket that cannot vouch for its bytes."""

    def __init__(self, etag_of: dict[str, str]) -> None:
        super().__init__()
        self._etag_of = etag_of

    def list_objects(self) -> dict[str, str]:
        return dict(self._etag_of)


def test_a_multipart_etag_cannot_vouch_for_an_existing_key(tmp_path: Path):
    content = b"photo-bytes"
    photo_zip = _ac_zip(tmp_path, {"FAC10000000001_div.jpg": content})
    key = _key("AC", 10000000001, content)
    bucket = _FixedEtagBucket({key: hashlib.md5(content).hexdigest() + "-2"})

    with pytest.raises(PhotoIntegrityError, match="refusing to overwrite"):
        mirror_photos([photo_zip], bucket, public_domain=DOMAIN)

    assert bucket.puts == []


class _DroppingBucket(_SpyBucket):
    """A bucket whose writes do not stick, or land as other bytes."""

    def __init__(self, initial=None, *, corrupt: bool = False) -> None:
        super().__init__(initial)
        self._corrupt = corrupt

    def put(self, key: str, path: Path, checksum: str) -> None:
        self.puts.append(key)
        if self._corrupt:
            self.objects[key] = (b"corrupted", checksum)


@pytest.mark.parametrize("corrupt", [False, True])
def test_an_upload_that_did_not_stick_fails_before_anything_is_deleted(
    tmp_path: Path, corrupt: bool
):
    photo_zip = _ac_zip(tmp_path, {"FAC10000000001_div.jpg": b"photo-bytes"})
    stale = _key("AC", 10000000009, b"stale")
    bucket = _DroppingBucket({stale: (b"stale", _checksum(b"stale"))}, corrupt=corrupt)

    with pytest.raises(PhotoIntegrityError, match="nothing was deleted"):
        mirror_photos([photo_zip], bucket, public_domain=DOMAIN)

    assert bucket.deletes == []
    assert stale in bucket.objects


def test_no_image_bytes_are_left_behind_after_the_run(tmp_path: Path):
    photo_zip = _ac_zip(tmp_path, {"FAC10000000001_div.jpg": b"photo-bytes"})

    mirror_photos([photo_zip], FakePhotoBucketClient(), public_domain=DOMAIN)

    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".mirror-photos-")]
    assert leftovers == []
