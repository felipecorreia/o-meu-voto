"""Public setup representations keep one source and remain ordinary static assets."""

from __future__ import annotations

import json
import re
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

from br_elections_mcp.domain import UF
from tests.conftest import REPO

WEB = REPO / "web-next"
SITE = "https://omeuvoto.pages.dev"


class SetupHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_pre = False
        self.instructions = ""
        self.links = []
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == "pre":
            self.in_pre = True
        if tag == "a":
            self.links.append(dict(attrs)["href"])

    def handle_endtag(self, tag):
        if tag == "pre":
            self.in_pre = False

    def handle_data(self, data):
        if self.in_pre:
            self.instructions += data


def render_resources(source: Path, output: Path) -> SetupHTML:
    subprocess.run(
        ["node", str(WEB / "scripts/build-assistant-resources.mjs"), str(source), str(output)],
        check=True,
        capture_output=True,
        text=True,
    )
    parser = SetupHTML()
    parser.feed((output / "prompt-llm.html").read_text())
    return parser


def test_setup_representations_preserve_the_authored_text_and_link_to_the_api(tmp_path):
    source = WEB / "public/prompt-llm.md"
    html = render_resources(source, tmp_path)
    assert (tmp_path / "prompt-llm.txt").read_bytes() == source.read_bytes()
    assert html.instructions == source.read_text()
    assert f"{SITE}/api/v1/openapi.json" in html.links
    assert "script" not in html.tags


def test_html_representation_links_every_url_of_the_instructions(tmp_path):
    # ChatGPT opens URLs that appear as links on a page it read, not URLs it builds.
    source = WEB / "public/prompt-llm.md"
    html = render_resources(source, tmp_path)
    urls = set(
        re.findall(
            r"https://omeuvoto\.pages\.dev[^\s<>\"'`()\[\]]*[^\s<>\"'`()\[\].,;:]",
            source.read_text(),
        )
    )
    assert "https://omeuvoto.pages.dev/api/v1/candidates?uf=SP&office=senador" in urls
    templates = {url for url in urls if "{" in url}
    assert urls - templates <= set(html.links)
    assert not [link for link in html.links if "{" in link]


def test_generated_setup_output_links_no_route_the_assistant_must_build(tmp_path):
    # Claude's reader answers a new URL with an already seen URL of the same path, so the
    # generated copies carry candidate-list links only (issue #115).
    html = render_resources(WEB / "public/prompt-llm.md", tmp_path)
    text_urls = re.findall(
        r"https?://[^\s<>\"'`()\[\]]+", (tmp_path / "prompt-llm.txt").read_text()
    )
    built = {"compare", "by-number", "polling-place", "polling-places", "municipalities"}
    for url in [*text_urls, *html.links]:
        parts = urlsplit(url.rstrip(".,;:"))
        route = parts.path.removeprefix("/api/v1/").removeprefix("candidates/")
        assert not (parts.path.startswith("/api/v1/") and route in built), url
    assert f"{SITE}/api/v1/candidates?uf=SP&office=senador" in html.links


def test_html_representation_lists_ready_candidate_links_for_every_uf_and_office(tmp_path):
    html = render_resources(WEB / "public/prompt-llm.md", tmp_path)
    expected = {f"{SITE}/api/v1/election", f"{SITE}/api/v1/candidates?uf=BR&office=presidente"}
    for uf in set(UF) - {UF.ZZ, UF.BR}:
        local = "deputado_distrital" if uf == UF.DF else "deputado_estadual"
        for office in ("governador", "senador", "deputado_federal", local):
            expected.add(f"{SITE}/api/v1/candidates?uf={uf}&office={office}")
    assert expected <= set(html.links)
    assert f"{SITE}/api/v1/candidates?uf=SP&office=senador" in html.links


def test_html_representation_escapes_instruction_content(tmp_path):
    source = tmp_path / "source.md"
    text = '<script>alert("example")</script> & <a href="https://example.test/?a=1&b=2">x</a>.\n'
    source.write_text(text)
    html = render_resources(source, tmp_path / "output")
    assert html.instructions == text
    assert "script" not in html.tags
    # The authored anchor stays text; only its URL becomes a link, cut at the escaped quote.
    assert "https://example.test/?a=1&b=2" in html.links
    assert not [link for link in html.links if '"' in link or ">" in link]


def test_pages_headers_declare_fetchable_representations_outside_the_edge_function():
    headers = {}
    current = None
    for line in (WEB / "public/_headers").read_text().splitlines():
        if line.startswith("/"):
            current = line
            headers[current] = {}
        elif line.strip():
            key, value = line.strip().split(":", 1)
            headers[current][key.lower()] = value.strip()
    for path in ("/prompt-llm.md", "/prompt-llm.txt"):
        assert headers[path]["content-type"] == "text/plain; charset=utf-8"
    # Pages serves prompt-llm.html at /prompt-llm and redirects the .html path there.
    assert headers["/prompt-llm"]["content-type"] == "text/html; charset=utf-8"
    # Setup fetches stay static; API calls still use the existing secret-bearing edge.
    routes = json.loads((WEB / "public/_routes.json").read_text())
    assert routes["include"] == ["/api/*", "/mcp"]


def test_robots_allows_assistant_fetches_including_google_extended():
    # Without this file Cloudflare serves a rule-less content-signals preamble (issue #115).
    groups: dict[str, list[str]] = {}
    agent = None
    for line in (WEB / "public/robots.txt").read_text().splitlines():
        field, _, value = line.partition(":")
        if field.strip().lower() == "user-agent":
            agent = value.strip()
            groups[agent] = []
        elif agent and line.strip() and not line.startswith("#"):
            groups[agent].append(line.strip())
    for agent in ("*", "Googlebot", "Google-Extended"):
        assert "Allow: /" in groups[agent]
        assert not [rule for rule in groups[agent] if rule.lower().startswith("disallow")]
    assert "ai-input=yes" in " ".join(groups["*"])
