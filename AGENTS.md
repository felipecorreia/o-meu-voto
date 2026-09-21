# br-elections-mcp

Pointers only; the content lives in the files below.

- **Start at `wiki/index.md`**, then the top entry of `wiki/log.md` for the current state and
  the decisions still open with the captain.
- **`CONTEXT.md`**: the ubiquitous language. Use its English identifiers in code and its terms
  in prose; each entry lists synonyms to avoid.
- **`docs/domain-model.md`**, **`docs/codebase-design.md`**, **`docs/adr/`**: entities and
  invariants, module boundaries and tool contracts, accepted decisions. Design is settled
  there; a change that contradicts them needs a new ADR, not a silent override.
- **Guardrails**: no personal data in the index or in any response (ADR 0004); PostHog
  telemetry anonymous.
- **Dev loop**: `uv sync`, `uv run ruff check .`, `uv run ruff format --check .`,
  `uv run pytest` (same as `.github/workflows/ci.yml`). Language: identifiers in English.
  Prose finalized from 2026-09-18 on (issues, tickets, reports, commit messages, new docs)
  is EN-US; docs committed before that date stay PT-BR until rewritten.
  Tests build their DuckDB index from `tests/fixtures/` with the pipeline's own `build_index`
  (`tests/conftest.py`), deliver it through `LocalDirectoryIndexSource` and exercise a real
  `Core`; MCP tests use the SDK's in-memory `mcp.Client(server)`, REST tests the Starlette
  `TestClient` with `base_url="http://localhost"` (the MCP transport rejects other hosts).
  Local run and the Claude Desktop connection: `docs/local-run.md`. Pipeline chain, bucket
  layout and the refresh workflow: README, "Publishing the index".

## Sharp edges

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
- The TSE vocabulary of `DS_SITU_SECAO_ACESSIBILIDADE`, `DS_SITU_LOCAL_VOTACAO` and every
  `DS_CARGO` text except `"DEPUTADO FEDERAL"` in the fixtures is a guess; `build` fails loudly
  on unknown texts (`OFFICE_BY_DS_CARGO` in `pipeline/build.py` for offices), so the first real
  ingestion fixes them (`tests/fixtures/README.md`).
- The CDN URL for the per-UF candidate photo ZIPs (`foto_cand<year>_<UF>_div.zip`) was never
  verified against the TSE portal; only the CKAN dataset and file name are documented
  (`docs/domain-model.md`, section 2). `pipeline/mirror_photos.py` takes the ZIPs as file input
  (`PhotoZip`) rather than guessing the URL; wiring the download is a follow-up left for the
  scheduled workflow (README, "Mirroring candidate photos to R2").

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
