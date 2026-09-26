# br-elections-mcp

Pointers only; the content lives in the files below.

- **Start at `wiki/index.md`**, then the top entry of `wiki/log.md` for the current state and
  the decisions still open with the captain.
- **`CONTEXT.md`**: the ubiquitous language. Use its English identifiers in code and its terms
  in prose; each entry lists synonyms to avoid.
- **`docs/domain-model.md`**, **`docs/codebase-design.md`**, **`docs/adr/`**: entities and
  invariants, module boundaries and tool contracts, accepted decisions. Design is settled
  there; a change that contradicts them needs a new ADR, not a silent override.
- **Guardrails**: no personal data in the index or in any response (ADR 0004; ADR 0009 adds
  the asset free text and allows the título only as an in-memory join key); the comparator
  never ranks, sorts by value or scores (ADR 0008); PostHog telemetry anonymous.
- **Voter page**: `web/` is static, no build, REST only, plus the Cloudflare Pages edge
  (`functions/[[path]].js` proxying `/api/*` and `/mcp` to Cloud Run, `_routes.json`,
  `404.html`); `web/README.md` says what it does and how to open it locally (`--web-dir web`,
  or `wrangler pages dev` for the edge), `tests/test_web.py` what CI checks of it.
- **Comparison page (next)**: `web-next/` is the React + Astryx page, comparison first, that
  replaces `web/` once wired to the comparator API; `web-next/README.md` says how to run it,
  what is still mock and the follow-ups. Vite build, not deployed yet.
- **Dev loop**: `uv sync`, `uv run ruff check .`, `uv run ruff format --check .`,
  `uv run pytest` (same as `.github/workflows/ci.yml`). Language: identifiers in English.
  Prose finalized from 2026-09-18 on (issues, tickets, reports, commit messages, new docs)
  is EN-US; docs committed before that date stay PT-BR until rewritten.
  Tests build their DuckDB index from `tests/fixtures/` with the pipeline's own `build_index`
  (`tests/conftest.py`), deliver it through `LocalDirectoryIndexSource` and exercise a real
  `Core`; MCP tests use the SDK's in-memory `mcp.Client(server)`, REST tests the Starlette
  `TestClient` with `base_url="http://localhost"` (the MCP transport rejects other hosts; an
  HTTP call to `/mcp` itself needs `"http://localhost:8000"`, since the SDK's DNS-rebinding
  guard accepts only `localhost:<port>`).
  Local run, the Claude Desktop connection and the service image over real TSE data
  (`Dockerfile`, `compose.yaml`): `docs/local-run.md`. Pipeline chain, bucket layout and the
  refresh workflow: README, "Publishing the index". Cloud Run + Cloudflare deploy checklist,
  costs and open decisions: `docs/deploy-runbook.md` (nothing provisioned yet); after a deploy,
  `scripts/smoke.sh BASE [HEALTH_BASE]` asks the four voter questions over REST and MCP.

## Sharp edges

- Cloud Run reserves some paths ending in `z` on the default `run.app` domain and answers them
  with its own 404 for external requests (a documented known issue), so `/healthz` is
  unreachable from outside even though the internal startup and liveness probes on it work.
  `GET /health` (`app.py`, exempt from the edge secret and the rate limit like `/healthz`)
  serves the same payload for external checks; `scripts/smoke.sh` and
  `docs/deploy-runbook.md` use it, while the Cloud Run probe flags in step C2 keep `/healthz`.
- The MCP SDK is `mcp` 2.x: `MCPServer` (not `FastMCP`), `mcp.Client(...)` for clients, and a
  tool returns `Annotated[CallToolResult, AnswerModel]` to keep a generated `outputSchema` while
  building its own text content. Pinned `<3` in `pyproject.toml`.
- A pydantic model used as an MCP tool input (e.g. `Near`) puts its class docstring into the
  generated `inputSchema` description, which must be PT-BR: keep the EN-US docstring as a
  comment and set the description through `json_schema_extra`.
- Starlette does not run the lifespan of mounted apps: `app.py` runs the MCP session manager
  inside the root lifespan. Keep it there when adding routes.
- Round handling lives in `core/rounds.py` (the code of codebase-design 3.4); `core.py` only
  gathers the round sets. The `tests/fixtures/acre/` index carries both rounds, so a list or
  profile without `round` may answer round 2 (president); `acre_round_1_index_dir` in
  `tests/conftest.py` is the variant without round 2.
- The fixtures are hand-written; the real TSE files differ from them in ways the fixtures only
  show through derived variants (`with_fields` and the constants below it in
  `tests/conftest.py`): a place number is unique per municipality within a zone, an aggregated
  section can be registered at another place than its main section, and a substituted
  candidacy can still be flagged on the ballot. Findings of the first real ingestion
  (2026-09-24): `docs/domain-model.md` section 7 and that date's entry in `wiki/log.md`.
- Display casing (locais/endereços/municípios/nome civil, title case with a mined acronym
  list, `nome_urna` untouched) is applied once at index build time
  (`pipeline/casing.py`/`build.py`, `codebase-design.md` section 7), not in `core`: the
  index already stores the display value, so a `core` warning that quotes a name inherits the
  casing for free. Add a name-bearing column to `_CASED_COLUMNS` there, not to `core`.
- The candidate photo ZIPs answer at
  `https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/fotos/foto_cand2026_<UF>_div.zip`
  (HEAD 200 on 2026-09-24), but nothing downloads them yet: `pipeline/mirror_photos.py` takes
  the ZIPs as file input (`PhotoZip`) and wiring the download into `refresh.yml` is a
  follow-up (README, "Mirroring candidate photos to R2").

## Agent skills

### Issue tracker

Issues, specs and tickets live in this repo's GitHub Issues, driven with `gh`; tickets block
each other through native issue dependencies. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical labels, unchanged: `needs-triage`, `needs-info`, `ready-for-agent`,
`ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
