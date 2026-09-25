"""The static page under ``web/`` (codebase-design 7) and the local-only mount that serves it.

The page is deployed on Cloudflare Pages, never by the service; ``web_dir`` exists so a local
run can open the page and the REST API on one origin (no CORS) and so this file can check that
every file the page references is committed.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
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


# The Pages edge (ADR 0005, docs/deploy-runbook.md step D0): the function that proxies /api
# and /mcp to Cloud Run on the page's own domain, the route list that keeps every other path
# a static asset, and the 404 page that stops Pages answering unknown paths with index.html.

EDGE_FUNCTION = WEB_DIR / "functions" / "[[path]].js"


def test_only_the_api_and_mcp_reach_the_edge_function():
    routes = json.loads((WEB_DIR / "_routes.json").read_text(encoding="utf-8"))
    # /healthz stays off the page's domain, and static requests never invoke the function.
    assert routes == {"version": 1, "include": ["/api/*", "/mcp"], "exclude": []}


def test_unknown_paths_get_a_real_404_page():
    # Without 404.html, Pages answers every unknown path, the MCP OAuth discovery probes
    # (/.well-known/oauth-*) included, with 200 and index.html.
    html = (WEB_DIR / "404.html").read_text(encoding="utf-8")
    assert '<html lang="pt-BR">' in html
    assert 'href="/"' in html


# Runs the function once per request under Node with a stub fetch and prints what it did:
# either the response it answered itself or the request it forwarded.
_EDGE_HARNESS = """
const [source, cases] = [process.argv[1], JSON.parse(process.argv[2])];
const { readFileSync } = await import("node:fs");
const { onRequest } = await import(
  "data:text/javascript," + encodeURIComponent(readFileSync(source, "utf8"))
);
const results = [];
for (const { method, url, env, body } of cases) {
  let forwarded = null;
  globalThis.fetch = async (target, init) => {
    forwarded = {
      url: String(target),
      method: init.method,
      headers: Object.fromEntries(init.headers),
      body: init.body ? await new Response(init.body).text() : null,
      cf: init.cf ?? null,
      redirect: init.redirect,
    };
    return new Response("origin");
  };
  const headers = { host: "meu-voto.pages.dev", "cf-connecting-ip": "203.0.113.7" };
  const request = new Request(url, { method, headers, body, duplex: "half" });
  const response = await onRequest({ request, env });
  results.push({ status: response.status, allow: response.headers.get("allow"), forwarded });
}
console.log(JSON.stringify(results));
"""

ORIGIN = "https://br-elections-mcp-abc123.southamerica-east1.run.app"
PAGES = "https://meu-voto.pages.dev"


def run_edge_function(*cases: dict) -> list[dict]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    completed = subprocess.run(
        [node, "--input-type=module", "-e", _EDGE_HARNESS, str(EDGE_FUNCTION), json.dumps(cases)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(completed.stdout)


def edge_request(method: str, path: str, *, secret: str | None = "s3cret", body=None) -> dict:
    env = {"ORIGIN_URL": ORIGIN} | ({"EDGE_SECRET": secret} if secret else {})
    return {"method": method, "url": PAGES + path, "env": env, "body": body}


def test_the_edge_answers_the_mcp_get_stream_with_405_without_reaching_the_origin():
    [result] = run_edge_function(edge_request("GET", "/mcp"))
    assert result == {"status": 405, "allow": "POST", "forwarded": None}


def test_the_edge_forwards_mcp_posts_with_the_edge_secret_and_the_client_ip():
    body = '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
    [result] = run_edge_function(edge_request("POST", "/mcp", body=body))
    forwarded = result["forwarded"]
    assert forwarded["url"] == f"{ORIGIN}/mcp"
    assert forwarded["method"] == "POST"
    assert forwarded["body"] == body
    assert forwarded["headers"]["x-edge-secret"] == "s3cret"
    assert forwarded["headers"]["cf-connecting-ip"] == "203.0.113.7"
    # run.app routes by Host: the Pages hostname must not reach it.
    assert "host" not in forwarded["headers"]
    assert forwarded["redirect"] == "manual"
    assert forwarded["cf"] is None


def test_the_edge_sends_no_secret_header_until_one_is_configured():
    [result] = run_edge_function(edge_request("GET", "/api/v1/election", secret=None))
    assert "x-edge-secret" not in result["forwarded"]["headers"]


def test_the_edge_caches_rest_gets_briefly_but_never_the_voters_coordinates():
    by_city = "/api/v1/polling-places?uf=ac&municipality=rio%20branco"
    cached, near, only_lat = run_edge_function(
        edge_request("GET", by_city),
        edge_request("GET", "/api/v1/polling-places?uf=ac&lat=-9.97&lon=-67.81"),
        edge_request("GET", "/api/v1/polling-places?uf=ac&lat=-9.97"),
    )
    assert cached["forwarded"]["url"] == ORIGIN + by_city
    assert cached["forwarded"]["cf"] == {"cacheTtl": 60, "cacheEverything": True}
    # ADR 0004: a query carrying the voter's location must not be kept in the edge cache.
    assert near["forwarded"]["cf"] is None
    assert only_lat["forwarded"]["cf"] is None
