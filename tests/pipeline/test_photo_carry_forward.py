"""A failed incremental mirror still permits a valid published index."""

from __future__ import annotations

import hashlib
import os
import subprocess
import zipfile
from pathlib import Path

import duckdb
import pytest
import yaml

from br_elections_mcp.index_schema import INDEX_FILE_NAME, MANIFEST_FILE_NAME, read_manifest
from br_elections_mcp.pipeline import __main__ as cli
from br_elections_mcp.pipeline.bucket import FakePhotoBucketClient, LocalDirectoryBucketClient
from br_elections_mcp.pipeline.build import apply_photo_urls
from br_elections_mcp.pipeline.datasets import CANDIDATE_PHOTOS_2026
from br_elections_mcp.pipeline.mirror_photos import FULL_LOAD_MARKER_KEY
from br_elections_mcp.pipeline.photo_integrity import photo_key, photo_problems
from br_elections_mcp.pipeline.publish import publish, verify_index_pair
from tests.conftest import build_fixture_index

SQ = 10000000001
DOMAIN = "https://fotos.example.org"
PHOTO = b"current-tse-photo"


def _zips(directory: Path, photo: bytes = PHOTO) -> None:
    directory.mkdir()
    for dataset in CANDIDATE_PHOTOS_2026:
        with zipfile.ZipFile(directory / dataset.file_name, "w") as zf:
            zf.writestr("leiame.pdf", b"readme")
            if dataset.file_name == "foto_cand2026_AC_div.zip":
                zf.writestr(f"FAC{SQ}_div.jpg", photo)


def _r2_args() -> list[str]:
    return [
        "--public-domain",
        DOMAIN,
        "--r2-endpoint",
        "https://example.invalid",
        "--r2-bucket",
        "bucket",
        "--r2-access-key-id",
        "id",
        "--r2-secret-access-key",
        "secret",
    ]


def _load_status_args(*, require_incomplete: bool = False) -> list[str]:
    args = ["photo-load-status", *_r2_args()[2:]]
    if require_incomplete:
        args.append("--require-incomplete")
    return args


def _photo_pair(index_dir: Path) -> tuple[str | None, str | None]:
    conn = duckdb.connect(str(index_dir / INDEX_FILE_NAME), read_only=True)
    try:
        return conn.execute(
            "SELECT DISTINCT photo_url, photo_sha256 FROM candidates WHERE sq_candidato = ?",
            [SQ],
        ).fetchone()
    finally:
        conn.close()


@pytest.mark.parametrize("r2_bytes", [PHOTO, b"swapped-photo", None])
def test_only_a_previous_photo_verified_against_tse_and_r2_survives_failed_mirror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, r2_bytes: bytes | None
):
    previous, fresh, zips = tmp_path / "previous", tmp_path / "fresh", tmp_path / "photos"
    build_fixture_index(previous)
    build_fixture_index(fresh)
    _zips(zips)
    key, digest = photo_key("AC", SQ, PHOTO)
    apply_photo_urls(previous, {SQ: f"{DOMAIN}/{key}"}, {SQ: digest})
    gcs = LocalDirectoryBucketClient(tmp_path / "gcs")
    publish(previous / INDEX_FILE_NAME, previous / MANIFEST_FILE_NAME, gcs)
    downloaded = tmp_path / "downloaded"
    assert (
        cli.main(
            [
                "current-index",
                "--local-bucket",
                str(tmp_path / "gcs"),
                "--output-dir",
                str(downloaded),
            ]
        )
        == 0
    )
    objects = {key: (r2_bytes, digest)} if r2_bytes is not None else {}
    r2 = FakePhotoBucketClient(objects)
    monkeypatch.setattr(cli, "R2BucketClient", lambda **_: r2)

    assert (
        cli.main(
            [
                "retain-photos",
                "--zips-dir",
                str(zips),
                "--index-dir",
                str(fresh),
                "--previous-index-dir",
                str(downloaded),
                *_r2_args(),
            ]
        )
        == 0
    )
    assert _photo_pair(fresh) == (
        (f"{DOMAIN}/{key}", digest) if r2_bytes == PHOTO else (None, None)
    )
    assert photo_problems(fresh / INDEX_FILE_NAME, DOMAIN) == []
    assert (
        read_manifest(fresh / MANIFEST_FILE_NAME).index_sha256
        == hashlib.sha256((fresh / INDEX_FILE_NAME).read_bytes()).hexdigest()
    )


def test_changed_tse_photo_does_not_carry_an_old_url(tmp_path: Path, monkeypatch):
    previous, fresh, zips = tmp_path / "previous", tmp_path / "fresh", tmp_path / "photos"
    build_fixture_index(previous)
    build_fixture_index(fresh)
    _zips(zips, photo=b"new-photo")
    old_key, old_digest = photo_key("AC", SQ, PHOTO)
    apply_photo_urls(previous, {SQ: f"{DOMAIN}/{old_key}"}, {SQ: old_digest})
    new_key, new_digest = photo_key("AC", SQ, b"new-photo")
    # The new key may be a partial upload from the timed-out mirror, but it was never published.
    r2 = FakePhotoBucketClient({old_key: (PHOTO, old_digest), new_key: (b"new-photo", new_digest)})
    monkeypatch.setattr(cli, "R2BucketClient", lambda **_: r2)

    assert (
        cli.main(
            [
                "retain-photos",
                "--zips-dir",
                str(zips),
                "--index-dir",
                str(fresh),
                "--previous-index-dir",
                str(previous),
                *_r2_args(),
            ]
        )
        == 0
    )
    assert _photo_pair(fresh) == (None, None)
    assert set(r2.objects) == {old_key, new_key}


def test_retain_refuses_a_previous_index_that_does_not_match_its_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    previous, fresh, zips = tmp_path / "previous", tmp_path / "fresh", tmp_path / "photos"
    build_fixture_index(previous)
    build_fixture_index(fresh)
    _zips(zips)
    (previous / INDEX_FILE_NAME).write_bytes(b"tampered")
    monkeypatch.setattr(cli, "R2BucketClient", lambda **_: pytest.fail("R2 must not be read"))

    assert (
        cli.main(
            [
                "retain-photos",
                "--zips-dir",
                str(zips),
                "--index-dir",
                str(fresh),
                "--previous-index-dir",
                str(previous),
                *_r2_args(),
            ]
        )
        == 1
    )
    assert "does not match manifest" in capsys.readouterr().err
    assert _photo_pair(fresh) == (None, None)


def test_manual_load_retains_old_r2_objects_until_a_new_index_is_published(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    index_dir, zips = tmp_path / "index", tmp_path / "photos"
    build_fixture_index(index_dir)
    _zips(zips)
    old_key, old_digest = photo_key("AC", SQ, b"old-photo")
    r2 = FakePhotoBucketClient({old_key: (b"old-photo", old_digest)})
    monkeypatch.setattr(cli, "R2BucketClient", lambda **_: r2)

    assert (
        cli.main(
            [
                "mirror-photos",
                "--zips-dir",
                str(zips),
                "--index-dir",
                str(index_dir),
                *_r2_args(),
                "--retain-old-photos",
            ]
        )
        == 0
    )
    new_key, _ = photo_key("AC", SQ, PHOTO)
    assert set(r2.objects) == {old_key, new_key}


def test_full_load_marker_gates_incremental_mirroring(tmp_path: Path, monkeypatch):
    index_dir, zips = tmp_path / "index", tmp_path / "photos"
    build_fixture_index(index_dir)
    _zips(zips)
    r2 = FakePhotoBucketClient()
    monkeypatch.setattr(cli, "R2BucketClient", lambda **_: r2)

    assert cli.main(_load_status_args()) == 3
    assert cli.main(_load_status_args(require_incomplete=True)) == 0
    assert (
        cli.main(
            [
                "mirror-photos",
                "--zips-dir",
                str(zips),
                "--index-dir",
                str(index_dir),
                *_r2_args(),
                "--retain-old-photos",
                "--mark-full-load-complete",
            ]
        )
        == 0
    )
    assert FULL_LOAD_MARKER_KEY in r2.objects
    assert cli.main(_load_status_args()) == 0
    assert cli.main(_load_status_args(require_incomplete=True)) == 1


def test_corrupted_full_load_marker_never_enables_incremental_mirroring(monkeypatch):
    r2 = FakePhotoBucketClient({FULL_LOAD_MARKER_KEY: (b"swapped", "wrong")})
    monkeypatch.setattr(cli, "R2BucketClient", lambda **_: r2)

    assert cli.main(_load_status_args()) == 2
    assert cli.main(_load_status_args(require_incomplete=True)) == 2


@pytest.mark.parametrize(
    ("status", "mirror", "failed"),
    [
        (0, "true", False),
        (3, "false", False),
        (1, "false", True),
        (2, "false", True),
        (124, "false", True),
    ],
)
def test_refresh_distinguishes_missing_marker_from_status_errors(
    tmp_path: Path, status: int, mirror: str, failed: bool
):
    workflow = yaml.safe_load(Path(".github/workflows/refresh.yml").read_text())
    steps = workflow["jobs"]["refresh"]["steps"]
    decision = next(
        step["run"]
        for step in steps
        if step.get("name") == "Decide whether to mirror candidate photos"
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    timeout = bin_dir / "timeout"
    timeout.write_text('#!/bin/bash\nexit "$PHOTO_STATUS_EXIT"\n')
    timeout.chmod(0o755)
    env_file = tmp_path / "env"
    env = os.environ | {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "GITHUB_ENV": str(env_file),
        "PHOTO_STATUS_EXIT": str(status),
        "R2_ENDPOINT": "https://example.invalid",
        "R2_BUCKET": "bucket",
        "R2_ACCESS_KEY_ID": "id",
        "R2_SECRET_ACCESS_KEY": "secret",
        "R2_PUBLIC_DOMAIN": DOMAIN,
    }
    result = subprocess.run(["bash", "-e", "-c", decision], env=env, capture_output=True, text=True)

    assert result.returncode == 0
    assert f"MIRROR_PHOTOS={mirror}" in env_file.read_text().splitlines()
    assert ("PHOTO_STATUS_FAILED=true" in env_file.read_text().splitlines()) is failed


def test_timed_out_mirror_leaves_the_publishable_pair_intact(tmp_path: Path):
    workflow = yaml.safe_load(Path(".github/workflows/refresh.yml").read_text())
    steps = workflow["jobs"]["refresh"]["steps"]
    mirror = next(
        step["run"] for step in steps if step.get("name") == "Mirror candidate photos to R2"
    )
    work = tmp_path / "work"
    index_dir = work / "index"
    build_fixture_index(index_dir)
    original_digest = verify_index_pair(index_dir).index_sha256
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    timeout = bin_dir / "timeout"
    timeout.write_text('#!/bin/bash\nwhile [ "$1" != uv ]; do shift; done\nexec "$@"\n')
    timeout.chmod(0o755)
    uv = bin_dir / "uv"
    uv.write_text(
        '#!/bin/bash\nwhile [ "$1" != --index-dir ]; do shift; done\n'
        'printf broken > "$2/index.duckdb"\nexit 124\n'
    )
    uv.chmod(0o755)
    env_file = tmp_path / "env"
    env = os.environ | {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "WORK": str(work),
        "GITHUB_ENV": str(env_file),
        "R2_ENDPOINT": "https://example.invalid",
        "R2_BUCKET": "bucket",
        "R2_ACCESS_KEY_ID": "id",
        "R2_SECRET_ACCESS_KEY": "secret",
        "R2_PUBLIC_DOMAIN": DOMAIN,
    }
    result = subprocess.run(["bash", "-e", "-c", mirror], env=env, capture_output=True, text=True)

    assert result.returncode == 124
    assert not env_file.exists()
    assert verify_index_pair(index_dir).index_sha256 == original_digest
    publish(
        index_dir / INDEX_FILE_NAME,
        index_dir / MANIFEST_FILE_NAME,
        LocalDirectoryBucketClient(tmp_path / "gcs"),
    )
