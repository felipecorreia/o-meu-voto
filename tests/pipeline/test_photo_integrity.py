"""The photo chain of ADR 0013: key, recorded digest, validate gate, and the mirror-photos CLI."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import duckdb
import pytest

from br_elections_mcp.index_schema import INDEX_FILE_NAME, MANIFEST_FILE_NAME, read_manifest
from br_elections_mcp.pipeline import __main__ as cli
from br_elections_mcp.pipeline.bucket import FakePhotoBucketClient
from br_elections_mcp.pipeline.build import apply_photo_urls
from br_elections_mcp.pipeline.datasets import CANDIDATE_PHOTOS_2026
from br_elections_mcp.pipeline.photo_integrity import photo_key, photo_problems
from tests.conftest import build_fixture_index
from tests.pipeline.test_validate import _gate, run_validate

SQ = 10000000001
DOMAIN = "https://fotos.example.org"


def test_photo_key_embeds_the_sha256_of_the_bytes():
    key, digest = photo_key("ac", SQ, b"photo")

    assert digest == hashlib.sha256(b"photo").hexdigest()
    assert key == f"FAC{SQ}_div-{digest}.jpg"
    assert photo_key("AC", SQ, b"other")[0] != key


def _index_with_photo(tmp_path: Path, *, url: str | None = None, digest: str | None = None) -> Path:
    index_dir = tmp_path / "index"
    build_fixture_index(index_dir)
    key, real = photo_key("AC", SQ, b"photo")
    apply_photo_urls(index_dir, {SQ: url or f"{DOMAIN}/{key}"}, {SQ: digest or real})
    return index_dir


def test_a_fresh_index_and_a_correctly_mirrored_one_have_no_problems(tmp_path: Path):
    fresh = tmp_path / "fresh"
    build_fixture_index(fresh)
    mirrored = _index_with_photo(tmp_path)

    assert photo_problems(fresh / INDEX_FILE_NAME) == []
    assert photo_problems(mirrored / INDEX_FILE_NAME) == []
    assert photo_problems(mirrored / INDEX_FILE_NAME, DOMAIN) == []


def test_a_different_host_with_the_right_digest_fails_the_configured_domain(tmp_path: Path):
    key, _ = photo_key("AC", SQ, b"photo")
    index_dir = _index_with_photo(tmp_path, url=f"https://attacker.example/{key}")

    assert "configured public domain" in " ".join(
        photo_problems(index_dir / INDEX_FILE_NAME, DOMAIN)
    )


@pytest.mark.parametrize("public_domain", [None, DOMAIN])
def test_photo_key_rejects_a_noncanonical_candidate_number(
    tmp_path: Path, public_domain: str | None
):
    _, digest = photo_key("AC", SQ, b"photo")
    url = f"{DOMAIN}/FAC0{SQ}_div-{digest}.jpg"
    index_dir = _index_with_photo(tmp_path, url=url)

    assert "does not carry the recorded photo_sha256" in " ".join(
        photo_problems(index_dir / INDEX_FILE_NAME, public_domain)
    )

    from br_elections_mcp.pipeline.validate import ValidationError

    with pytest.raises(ValidationError) as excinfo:
        run_validate(index_dir, output_dir=tmp_path / "report", photo_public_domain=public_domain)

    gate = _gate(excinfo.value, "photo_chain")
    assert "does not carry the recorded photo_sha256" in gate.message


@pytest.mark.parametrize("public_domain", [None, DOMAIN])
def test_photo_key_uf_must_match_the_candidacy(tmp_path: Path, public_domain: str | None):
    index_dir = _index_with_photo(tmp_path)
    index_path = index_dir / INDEX_FILE_NAME
    assert photo_problems(index_path, public_domain) == []
    assert (
        _gate(
            run_validate(
                index_dir, output_dir=tmp_path / "passing", photo_public_domain=public_domain
            ),
            "photo_chain",
        ).status
        == "pass"
    )

    wrong_key, _ = photo_key("SP", SQ, b"photo")
    conn = duckdb.connect(str(index_path))
    try:
        conn.execute(
            "UPDATE candidates SET photo_url = ? WHERE sq_candidato = ?",
            [f"{DOMAIN}/{wrong_key}", SQ],
        )
    finally:
        conn.close()

    (problem,) = photo_problems(index_path, public_domain)
    assert "key UF does not match the candidacy UF" in problem
    assert str(SQ) in problem

    from br_elections_mcp.pipeline.validate import ValidationError

    with pytest.raises(ValidationError) as excinfo:
        run_validate(index_dir, output_dir=tmp_path / "failing", photo_public_domain=public_domain)

    assert "key UF does not match the candidacy UF" in _gate(excinfo.value, "photo_chain").message


@pytest.mark.parametrize(
    "url_suffix",
    ["?v=1", "#photo", "?", "#"],
)
def test_a_url_with_query_or_fragment_is_rejected(tmp_path: Path, url_suffix: str):
    key, _ = photo_key("AC", SQ, b"photo")
    index_dir = _index_with_photo(tmp_path, url=f"{DOMAIN}/{key}{url_suffix}")

    assert "query or fragment" in " ".join(photo_problems(index_dir / INDEX_FILE_NAME))


def test_validate_rejects_a_different_host_among_photo_urls(tmp_path: Path):
    index_dir = tmp_path / "index"
    build_fixture_index(index_dir)
    first_key, first_digest = photo_key("AC", SQ, b"photo")
    second_sq = SQ + 1
    second_key, second_digest = photo_key("AC", second_sq, b"other photo")
    apply_photo_urls(
        index_dir,
        {SQ: f"{DOMAIN}/{first_key}", second_sq: f"https://attacker.example/{second_key}"},
        {SQ: first_digest, second_sq: second_digest},
    )

    from br_elections_mcp.pipeline.validate import ValidationError

    with pytest.raises(ValidationError) as excinfo:
        run_validate(index_dir, output_dir=tmp_path / "report")

    assert "do not share one scheme and host" in _gate(excinfo.value, "photo_chain").message


def test_validate_rejects_a_wrong_host_with_explicit_domain(tmp_path: Path):
    key, _ = photo_key("AC", SQ, b"photo")
    index_dir = _index_with_photo(tmp_path, url=f"https://attacker.example/{key}")

    from br_elections_mcp.pipeline.validate import ValidationError

    with pytest.raises(ValidationError) as excinfo:
        run_validate(index_dir, output_dir=tmp_path / "report", photo_public_domain=DOMAIN)

    assert "configured public domain" in _gate(excinfo.value, "photo_chain").message


@pytest.mark.parametrize(
    ("url", "digest", "message"),
    [
        (f"{DOMAIN}/FAC{SQ}_div.jpg", None, "not a content-addressed key"),
        (None, "A" * 64, "not a content-addressed key or the digest is malformed"),
        (None, "abc", "not a content-addressed key or the digest is malformed"),
        (
            f"{DOMAIN}/FAC{SQ}_div-{hashlib.sha256(b'swapped').hexdigest()}.jpg",
            None,
            "does not carry the recorded photo_sha256",
        ),
        (
            f"{DOMAIN}/FAC10000000002_div-{hashlib.sha256(b'photo').hexdigest()}.jpg",
            None,
            "does not carry the recorded photo_sha256",
        ),
    ],
)
def test_a_url_that_does_not_carry_its_recorded_digest_is_a_problem(
    tmp_path: Path, url, digest, message
):
    index_dir = _index_with_photo(tmp_path, url=url, digest=digest)

    problems = photo_problems(index_dir / INDEX_FILE_NAME)

    assert len(problems) == 1
    assert message in problems[0]
    assert str(SQ) in problems[0]


def test_a_url_without_a_digest_or_the_reverse_is_a_problem(tmp_path: Path):
    index_dir = _index_with_photo(tmp_path)
    conn = duckdb.connect(str(index_dir / INDEX_FILE_NAME))
    try:
        conn.execute("UPDATE candidates SET photo_sha256 = NULL WHERE sq_candidato = ?", [SQ])
    finally:
        conn.close()

    (problem,) = photo_problems(index_dir / INDEX_FILE_NAME)

    assert "not set together" in problem


@pytest.mark.parametrize("public_domain", [None, DOMAIN])
@pytest.mark.parametrize("change", ["clear", "replace"])
def test_photo_chain_requires_the_same_pair_in_every_round(
    tmp_path: Path, public_domain: str | None, change: str
):
    index_dir = tmp_path / "index"
    build_fixture_index(index_dir)
    sq_candidato = 20000000003
    key, digest = photo_key("BR", sq_candidato, b"photo")
    apply_photo_urls(index_dir, {sq_candidato: f"{DOMAIN}/{key}"}, {sq_candidato: digest})
    index_path = index_dir / INDEX_FILE_NAME

    assert photo_problems(index_path, public_domain) == []
    assert (
        _gate(
            run_validate(
                index_dir, output_dir=tmp_path / "passing", photo_public_domain=public_domain
            ),
            "photo_chain",
        ).status
        == "pass"
    )

    conn = duckdb.connect(str(index_path))
    try:
        rounds = conn.execute(
            'SELECT "round" FROM candidates WHERE sq_candidato = ? ORDER BY "round"',
            [sq_candidato],
        ).fetchall()
        assert rounds == [(1,), (2,)]
        if change == "clear":
            new_url, new_digest = None, None
        else:
            new_key, new_digest = photo_key("BR", sq_candidato, b"different photo")
            new_url = f"{DOMAIN}/{new_key}"
        conn.execute(
            "UPDATE candidates SET photo_url = ?, photo_sha256 = ? "
            'WHERE sq_candidato = ? AND "round" = 2',
            [new_url, new_digest, sq_candidato],
        )
    finally:
        conn.close()

    assert "differ across rounds" in " ".join(photo_problems(index_path, public_domain))

    from br_elections_mcp.pipeline.validate import ValidationError

    with pytest.raises(ValidationError) as excinfo:
        run_validate(index_dir, output_dir=tmp_path / "failing", photo_public_domain=public_domain)

    assert "differ across rounds" in _gate(excinfo.value, "photo_chain").message


def test_validate_passes_the_photo_chain_gate_with_and_without_photos(
    acre_index_dir: Path, tmp_path: Path
):
    assert _gate(run_validate(acre_index_dir, output_dir=tmp_path), "photo_chain").status == "pass"


def test_validate_fails_the_photo_chain_gate_when_a_url_no_longer_matches_its_digest(
    tmp_path: Path,
):
    index_dir = _index_with_photo(tmp_path)
    conn = duckdb.connect(str(index_dir / INDEX_FILE_NAME))
    try:
        conn.execute(
            "UPDATE candidates SET photo_sha256 = ? WHERE sq_candidato = ?",
            [hashlib.sha256(b"swapped").hexdigest(), SQ],
        )
    finally:
        conn.close()

    from br_elections_mcp.pipeline.validate import ValidationError

    with pytest.raises(ValidationError) as excinfo:
        run_validate(index_dir, output_dir=tmp_path / "report")

    (gate,) = excinfo.value.report.failed
    assert gate.name == "photo_chain"
    assert "does not carry the recorded photo_sha256" in gate.message


# --- the mirror-photos command, over a fake bucket ---------------------------------------


def _photo_zips(directory: Path, photo: bytes) -> None:
    """The complete set of 28 ZIPs; only AC carries a photo of a fixture candidacy."""
    directory.mkdir(parents=True, exist_ok=True)
    for dataset in CANDIDATE_PHOTOS_2026:
        with zipfile.ZipFile(directory / dataset.file_name, "w") as zf:
            zf.writestr("leiame.pdf", b"readme")
            if dataset.file_name == "foto_cand2026_AC_div.zip":
                zf.writestr(f"FAC{SQ}_div.jpg", photo)


@pytest.fixture
def bucket(monkeypatch: pytest.MonkeyPatch) -> FakePhotoBucketClient:
    fake = FakePhotoBucketClient()
    monkeypatch.setattr(cli, "R2BucketClient", lambda **_: fake)
    return fake


def _mirror(zips: Path, index_dir: Path, *, public_domain: str = DOMAIN) -> int:
    return cli.main(
        [
            "mirror-photos",
            "--zips-dir",
            str(zips),
            "--index-dir",
            str(index_dir),
            "--public-domain",
            public_domain,
            "--r2-endpoint",
            "https://example.invalid",
            "--r2-bucket",
            "bucket",
            "--r2-access-key-id",
            "id",
            "--r2-secret-access-key",
            "secret",
        ]
    )


def test_mirror_photos_records_the_digest_in_the_index_and_validate_accepts_it(
    tmp_path: Path, bucket, capsys
):
    zips, index_dir = tmp_path / "photos", tmp_path / "index"
    _photo_zips(zips, b"the-real-photo")
    build_fixture_index(index_dir)

    assert _mirror(zips, index_dir) == 0

    key, digest = photo_key("AC", SQ, b"the-real-photo")
    assert set(bucket.objects) == {key}
    conn = duckdb.connect(str(index_dir / INDEX_FILE_NAME), read_only=True)
    try:
        rows = conn.execute(
            "SELECT DISTINCT photo_url, photo_sha256 FROM candidates WHERE sq_candidato = ?", [SQ]
        ).fetchall()
    finally:
        conn.close()
    assert rows == [(f"{DOMAIN}/{key}", digest)]
    assert (
        read_manifest(index_dir / MANIFEST_FILE_NAME).index_sha256
        == hashlib.sha256((index_dir / INDEX_FILE_NAME).read_bytes()).hexdigest()
    )
    gate = _gate(
        run_validate(index_dir, output_dir=tmp_path / "report", photo_public_domain=DOMAIN),
        "photo_chain",
    )
    assert gate.status == "pass"
    assert "uploaded 1" in capsys.readouterr().out


def test_mirror_cli_rejects_an_existing_url_on_another_host(tmp_path: Path, bucket, capsys):
    zips = tmp_path / "photos"
    _photo_zips(zips, b"photo")
    key, _ = photo_key("AC", SQ, b"photo")
    wrong_url = f"https://attacker.example/{key}"
    index_dir = _index_with_photo(tmp_path, url=wrong_url)

    assert _mirror(zips, index_dir) == 1

    assert "configured public domain" in capsys.readouterr().err
    assert bucket.objects == {}
    conn = duckdb.connect(str(index_dir / INDEX_FILE_NAME), read_only=True)
    try:
        urls = conn.execute(
            "SELECT DISTINCT photo_url FROM candidates WHERE sq_candidato = ?", [SQ]
        ).fetchall()
    finally:
        conn.close()
    assert urls == [(wrong_url,)]


def test_mirror_cli_rejects_a_photo_from_the_wrong_uf_before_writing(
    tmp_path: Path, bucket, capsys
):
    zips = tmp_path / "photos"
    zips.mkdir()
    for dataset in CANDIDATE_PHOTOS_2026:
        with zipfile.ZipFile(zips / dataset.file_name, "w") as zf:
            zf.writestr("leiame.pdf", b"readme")
            if dataset.file_name == "foto_cand2026_SP_div.zip":
                zf.writestr(f"FSP{SQ}_div.jpg", b"new-photo")
    index_dir = _index_with_photo(tmp_path)
    index_path = index_dir / INDEX_FILE_NAME
    before = index_path.read_bytes()
    old_key, old_digest = photo_key("AC", SQ, b"photo")
    bucket.objects[old_key] = (b"photo", old_digest)

    assert _mirror(zips, index_dir) == 1

    assert f"sq_candidato {SQ}: ZIP UF SP does not match index UF AC" in capsys.readouterr().err
    assert bucket.objects == {old_key: (b"photo", old_digest)}
    assert index_path.read_bytes() == before


def test_mirror_cli_rejects_conflicting_index_ufs_before_opening_bucket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    zips = tmp_path / "photos"
    _photo_zips(zips, b"photo")
    index_dir = tmp_path / "index"
    build_fixture_index(index_dir)
    index_path = index_dir / INDEX_FILE_NAME
    sq_candidato = 20000000003
    conn = duckdb.connect(str(index_path))
    try:
        conn.execute(
            'UPDATE candidates SET uf = ? WHERE sq_candidato = ? AND "round" = 2',
            ["SP", sq_candidato],
        )
    finally:
        conn.close()
    before = index_path.read_bytes()
    old_key, old_digest = photo_key("BR", sq_candidato, b"old-photo")
    bucket = FakePhotoBucketClient({old_key: (b"old-photo", old_digest)})
    client_calls = []

    def make_bucket(**kwargs):
        client_calls.append(kwargs)
        return bucket

    monkeypatch.setattr(cli, "R2BucketClient", make_bucket)

    assert _mirror(zips, index_dir) == 1

    error = capsys.readouterr().err
    assert f"sq_candidato {sq_candidato} has conflicting index UFs" in error
    assert "BR" in error and "SP" in error
    assert client_calls == []
    assert bucket.objects == {old_key: (b"old-photo", old_digest)}
    assert index_path.read_bytes() == before


@pytest.mark.parametrize(
    "public_domain",
    [
        "https://fotos.example.org?x=1",
        "https://fotos.example.org#photos",
        "https://user@fotos.example.org",
        "",
        "ftp://fotos.example.org",
        "https://fotos.example.org:99999",
    ],
)
def test_mirror_cli_rejects_an_invalid_public_domain_before_bucket_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys, public_domain: str
):
    zips = tmp_path / "photos"
    _photo_zips(zips, b"new-photo")
    index_dir = tmp_path / "index"
    build_fixture_index(index_dir)
    index_path = index_dir / INDEX_FILE_NAME
    before = index_path.read_bytes()
    old_key, old_digest = photo_key("AC", SQ, b"old-photo")
    bucket = FakePhotoBucketClient({old_key: (b"old-photo", old_digest)})
    client_calls = []

    def make_bucket(**kwargs):
        client_calls.append(kwargs)
        return bucket

    monkeypatch.setattr(cli, "R2BucketClient", make_bucket)

    assert _mirror(zips, index_dir, public_domain=public_domain) == 1

    assert "public domain must be an http(s) URL" in capsys.readouterr().err
    assert client_calls == []
    assert bucket.objects == {old_key: (b"old-photo", old_digest)}
    assert index_path.read_bytes() == before


def test_a_rerun_is_idempotent_and_a_replaced_object_fails_the_run(tmp_path: Path, bucket, capsys):
    zips, index_dir = tmp_path / "photos", tmp_path / "index"
    _photo_zips(zips, b"the-real-photo")
    build_fixture_index(index_dir)
    assert _mirror(zips, index_dir) == 0
    assert _mirror(zips, index_dir) == 0
    assert "uploaded 0, skipped 1" in capsys.readouterr().out

    key, _ = photo_key("AC", SQ, b"the-real-photo")
    bucket.objects[key] = (b"an-attacker-photo", hashlib.sha256(b"the-real-photo").hexdigest())

    assert _mirror(zips, index_dir) == 1

    assert "refusing to overwrite" in capsys.readouterr().err
    assert bucket.objects[key][0] == b"an-attacker-photo"  # never overwritten, never deleted
