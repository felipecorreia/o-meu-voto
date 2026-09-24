"""The static page under ``web/`` (codebase-design 7) and the local-only mount that serves it.

The page is deployed on Cloudflare Pages, never by the service; ``web_dir`` exists so a local
run can open the page and the REST API on one origin (no CORS) and so this file can check that
every file the page references is committed.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from br_elections_mcp.app import ENV_INDEX_DIR, ENV_WEB_DIR, Settings, build_app
from br_elections_mcp.core import Core
from br_elections_mcp.index_store import LocalDirectoryIndexSource
from tests.conftest import ELECTIONS_FILE, REPO, fixed_clock

WEB_DIR = REPO / "web"


@pytest.fixture
def client(acre_index_dir: Path) -> Iterator[TestClient]:
    core = Core(LocalDirectoryIndexSource(acre_index_dir), ELECTIONS_FILE, clock=fixed_clock())
    with TestClient(build_app(core, web_dir=WEB_DIR), base_url="http://localhost") as client:
        yield client


def test_index_is_served_under_web_next_to_the_api(client: TestClient):
    response = client.get("/web/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<title>Onde Voto?</title>" in response.text
    # The page fetches the API relative to its own origin, so both live together here.
    assert client.get("/api/v1/election").status_code == 200
    assert client.get("/healthz").status_code == 200


def test_every_local_file_the_page_references_is_committed(client: TestClient):
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    references = re.findall(r'\b(?:src|href)="([^"]+)"', html)
    local = [r for r in references if not re.match(r"^(https?:|data:|#|mailto:)", r)]
    assert local, "the page is expected to load at least its stylesheet and script"
    for reference in local:
        assert (WEB_DIR / reference).is_file(), reference
        assert client.get(f"/web/{reference}").status_code == 200, reference


def test_the_page_is_light_themed_pt_br_and_calls_the_rest_api_relatively():
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    assert '<html lang="pt-BR">' in html
    assert '<meta name="br-elections-api-base" content="/api/v1">' in html
    # ADR 0004: the page never asks for anything from the electoral register.
    for forbidden in ("cpf", "título de eleitor", "titulo"):
        assert f'name="{forbidden}"' not in html.lower()


def test_without_web_dir_nothing_is_mounted_under_web(acre_index_dir: Path):
    core = Core(LocalDirectoryIndexSource(acre_index_dir), ELECTIONS_FILE, clock=fixed_clock())
    with TestClient(build_app(core), base_url="http://localhost") as client:
        assert client.get("/web/").status_code == 404


def test_settings_read_web_dir_from_the_environment(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv(ENV_INDEX_DIR, str(tmp_path))
    monkeypatch.setenv(ENV_WEB_DIR, str(WEB_DIR))
    assert Settings.from_env().web_dir == WEB_DIR
    monkeypatch.delenv(ENV_WEB_DIR)
    assert Settings.from_env().web_dir is None
