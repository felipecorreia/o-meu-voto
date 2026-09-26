# Running the service locally

Three steps: build an index from the Acre fixtures, start the server on localhost, connect a
client. Everything below was run from the repository root with `uv` 0.10 and Python 3.12.

## 1. Build the Acre fixture index

```sh
uv sync
uv run python -m br_elections_mcp.pipeline build \
  --polling-places tests/fixtures/acre/eleitorado_local_votacao_2026_AC.csv \
  --municipalities tests/fixtures/acre/municipio_tse_ibge.csv \
  --candidates tests/fixtures/acre/consulta_cand_2026_BRASIL.csv \
  --candidates-complementary tests/fixtures/acre/consulta_cand_complementar_2026_BRASIL.csv \
  --social-links tests/fixtures/acre/rede_social_candidato_2026_BRASIL.csv \
  --candidate-assets tests/fixtures/acre/bem_candidato_2026_BRASIL.csv \
  --output-dir data/index
```

Expected output:

```
index written to data/index: {'municipalities': 5, 'polling_places': 12, 'polling_sections': 20, 'candidates': 23, 'candidate_social_links': 4, 'candidate_assets': 5}
```

`data/index/` (`index.duckdb` and `manifest.json`) is git-ignored. The fixture rows are
described in `tests/fixtures/README.md`; the one that reproduces verified TSE values is Acre,
zone 9, section 422.

## 2. Start the server on localhost

```sh
uv run python -m br_elections_mcp.app --index-dir data/index --web-dir web --port 8000
```

The server prints `Uvicorn running on http://127.0.0.1:8000`. It serves:

- The voter page at `http://localhost:8000/web/`, because of `--web-dir web` (or
  `BR_ELECTIONS_WEB_DIR=web`): the static page of `web/` mounted next to the API so both share
  one origin and the page needs no CORS. A local-run convenience only; in production the page
  lives on Cloudflare Pages (ADR 0005). What the page does and how it was checked:
  [`web/README.md`](../web/README.md).

- MCP over Streamable HTTP at `http://localhost:8000/mcp` (stateless, JSON responses), with
  tools `find_polling_place`, `election_info`, `list_candidates` and `get_candidate`.
- REST at `http://localhost:8000/api/v1/polling-place?uf=&zone=&section=&round=`,
  `http://localhost:8000/api/v1/election?on=`,
  `http://localhost:8000/api/v1/candidates?uf=&office=&party=&name=&on_ballot_only=&limit=&offset=&round=`,
  `http://localhost:8000/api/v1/candidates/by-number?uf=&office=&number=&round=` and
  `http://localhost:8000/api/v1/candidates/{sq_candidato}?round=`,
  with OpenAPI at `http://localhost:8000/api/v1/openapi.json` and Swagger UI at
  `http://localhost:8000/api/v1/docs`.

Quick check in another terminal:

```sh
curl "http://localhost:8000/api/v1/polling-place?uf=ac&zone=009&section=0422"
curl "http://localhost:8000/api/v1/candidates?uf=ac&office=governador"
curl "http://localhost:8000/api/v1/candidates/by-number?uf=ac&office=governador&number=45"
```

The same app can be started with uvicorn directly, configured by environment variables:

```sh
BR_ELECTIONS_INDEX_DIR=data/index uv run uvicorn --factory br_elections_mcp.app:create_app --port 8000
```

`BR_ELECTIONS_ELECTIONS_FILE` (default `data/elections.yaml`) and `BR_ELECTIONS_HOST`
(default `127.0.0.1`) are two of the other variables. Two more configure the per-IP rate
limit (ticket #10): `BR_ELECTIONS_RATE_LIMIT_MAX_REQUESTS` (unset disables the limit, the
default) and `BR_ELECTIONS_RATE_LIMIT_WINDOW_SECONDS` (default `60`), both must be positive.
`BR_ELECTIONS_EDGE_SECRET` (unset by default, and unset locally) makes the service refuse with
`403` every request but `/healthz` and `/health` that lacks the same value in `x-edge-secret`,
the header the Cloudflare Pages Function sends; only such requests have their
`CF-Connecting-IP` trusted as the client address (ADR 0010).

### Index source: a directory or a bucket (ticket #16)

`Settings.build_index_source()` picks the `IndexSource` adapter from configuration and fails
at startup with a clear message on misconfiguration:

- `BR_ELECTIONS_INDEX_DIR` (used above): `LocalDirectoryIndexSource`, a plain directory with
  `index.duckdb` and `manifest.json`.
- `BR_ELECTIONS_INDEX_BUCKET`: `GcsIndexSource`, production. Also needs
  `BR_ELECTIONS_INDEX_CACHE_DIR` (a local directory it downloads into) and accepts
  `BR_ELECTIONS_INDEX_BUCKET_PREFIX` (default: no prefix). It authenticates with Application
  Default Credentials, resolved lazily on the first real download, never at startup or in a
  test; running against a real bucket therefore needs a real GCP credential
  (`gcloud auth application-default login` or a service account key), which this repository
  does not have and does not request. Follow-up for the captain, together with #20.

Setting both, or setting `BR_ELECTIONS_INDEX_BUCKET` without `BR_ELECTIONS_INDEX_CACHE_DIR`,
raises `RuntimeError` before the server starts.

Three more configure anonymous PostHog telemetry (ticket #17), described for the voter in the
README's "Telemetry" section: `BR_ELECTIONS_POSTHOG_API_KEY` (unset disables telemetry, the
default and the default in tests), `BR_ELECTIONS_POSTHOG_HOST` (default
`https://us.i.posthog.com`) and `BR_ELECTIONS_POSTHOG_DISTINCT_ID` (default
`br-elections-mcp`), the constant distinct id every event of this deployment carries. Getting a
PostHog project API key is a real-run step outside this repository; it needs a PostHog account,
which this task does not request or assume.

## 2b. Real TSE data, served from the service image

This runs the same service over an index built from the real TSE files, in the Docker image
that Cloud Run (#20) will run. Nothing here publishes anything or needs a credential, and
telemetry stays off.

Build the index with the pipeline chain of the README ("Publishing the index"), stopping
before `publish` (`data/raw/` is git-ignored):

```sh
uv sync --group pipeline
uv run python -m br_elections_mcp.pipeline fetch --output data/raw/zips
for zip in data/raw/zips/*.zip; do
  uv run python -m br_elections_mcp.pipeline extract --zip "$zip" --output-dir data/raw/csv
done
SOURCES="--polling-places data/raw/csv/eleitorado_local_votacao_2026_BRASIL.csv \
  --municipalities data/raw/csv/municipio_tse_ibge.csv \
  --candidates data/raw/csv/consulta_cand_2026_BRASIL.csv \
  --candidates-complementary data/raw/csv/consulta_cand_complementar_2026_BRASIL.csv \
  --social-links data/raw/csv/rede_social_candidato_2026_BRASIL.csv \
  --candidate-assets data/raw/csv/bem_candidato_2026_BRASIL.csv"
uv run python -m br_elections_mcp.pipeline build $SOURCES --output-dir data/index
uv run python -m br_elections_mcp.pipeline validate $SOURCES --index-dir data/index \
  --elections data/elections.yaml --output-dir data/index
```

(`$SOURCES` relies on word splitting: run it in `sh` or `bash`, not `zsh`.) Then serve it:

```sh
docker compose up --build -d          # INDEX_DIR=<dir> to serve another index directory
curl "http://localhost:8080/api/v1/polling-place?uf=sp&zone=251&section=72"
```

The image (`Dockerfile`) installs only the service dependencies from `uv.lock` (no dev or
pipeline group), runs as a non-root user, listens on `$PORT` (default 8080, the variable Cloud
Run sets) and takes its `IndexSource` from the environment exactly as above:
`compose.yaml` mounts the index read-only and sets `BR_ELECTIONS_INDEX_DIR`; a bucket-backed
deploy sets `BR_ELECTIONS_INDEX_BUCKET` and `BR_ELECTIONS_INDEX_CACHE_DIR` instead. MCP is at
`http://localhost:8080/mcp` (the image sets `BR_ELECTIONS_HOST=0.0.0.0`, which turns the SDK's
localhost-only Host check off, as behind the edge of ADR 0005).

Measured on 2026-09-24 on a MacBook (Apple silicon), over the files the TSE generated on
2026-09-23 (polling places) and 2026-09-24 (candidates), all UFs plus ZZ:

| Stage | Duration | Output |
|---|---|---|
| `fetch` | 6 s | 5 ZIPs, 103 MB, HTTP 200 each |
| `extract` | 1 s | 5 CSVs, 232 MB |
| `build` | 5.4 s | `index.duckdb` 46 MB: 517,179 sections, 95,601 places, 5,757 municipalities, 20,986 candidacies, 61,793 social links |
| `validate` | 7.7 s | 13 gates passed |
| `docker build --no-cache` | 8 s (base images already pulled) | image of 392 MB |

Acre alone (the `_AC` polling-places CSV with the `_AC` and `_BR` candidate CSVs) builds in
0.5 s into a 3 MB index; Sao Paulo alone in 1.8 s into 10 MB. The run log with the requests and
answers is the 2026-09-24 entry of `wiki/log.md`.

## 3. Connect Claude Desktop

Claude Desktop launches stdio servers from `claude_desktop_config.json`; to reach a local
Streamable HTTP server it needs the `mcp-remote` bridge, which runs as a stdio server and
proxies to the URL. With the server from step 2 running, add this to
`claude_desktop_config.json` (macOS:
`~/Library/Application Support/Claude/claude_desktop_config.json`; if the file does not exist
yet, enable it under Settings > Developer) and restart Claude Desktop:

```json
{
  "mcpServers": {
    "br-elections": {
      "command": "npx",
      "args": ["-y", "mcp-remote@0.14.2", "http://localhost:8000/mcp"]
    }
  }
}
```

Node.js is required (`npx` ships with it; verified with Node 25.8.1). The tools appear as
`find_polling_place` ("Onde voto"), `election_info` ("Quando é a eleição"), `list_candidates`
("Candidatos"), `get_candidate` ("Ficha do candidato"), `search_polling_places` ("Locais de
votação da cidade") and `resolve_municipality` ("Código do município"). Prompts to try: "Onde
voto? Acre, zona 9, seção 422.", "Quando é a eleição?", "Quem são os candidatos a governador do
Acre?", "Quem é o 45 para governador do Acre?" and "Quais são os locais de votação no Centro de
Rio Branco?"

### What was verified, and how

Environment used: macOS, Python 3.12.13, `uv` 0.10.10, Node 25.8.1, `mcp` SDK 2.2.0,
`mcp-remote` 0.14.2, on 2026-09-19.

- **Server over HTTP, official SDK client.** With the server on port 8765,
  `mcp.Client("http://localhost:8765/mcp")` listed the tool and called it, both with the
  modern protocol (2026-07-28, `server/discover`) and with the legacy initialize handshake
  (`mode="legacy"`, protocol 2025-11-25). Structured content carried the envelope; an unknown
  UF came back as a result with `isError`.
- **The `mcp-remote` bridge, exactly as Claude Desktop would run it.** The SDK's stdio client
  launched `npx -y mcp-remote@0.14.2 http://localhost:8765/mcp` as a subprocess, which is
  what Claude Desktop does with the config above, and through it listed the tool, called
  `find_polling_place` for Acre 9/422 (IEPTEC returned) and for an unknown UF (`isError`
  returned). The bridge connected with `StreamableHTTPClientTransport` ("http-first"
  strategy) and needed no OAuth. Two lines of evidence from its log:
  `Connected to remote server using StreamableHTTPClientTransport` and
  `Proxy established successfully between local STDIO and remote StreamableHTTPClientTransport`.
- **Claude Desktop itself was not exercised.** This document was written by an automated
  agent that must not open the captain's Claude Desktop nor edit his real
  `claude_desktop_config.json`. The snippet above follows the config format and the Claude
  Desktop section of the `mcp-remote` 0.14.2 README, with the bridge version pinned to the one
  verified. The Desktop custom connector with a plain `http://localhost` URL was not tried
  either; the bridge is the path to use first.

### Troubleshooting

- `Invalid Host header` (HTTP 421) on `/mcp`: the SDK enables DNS-rebinding protection when the
  server binds to localhost and only accepts `Host: localhost:*` or `127.0.0.1:*`. Use one of
  those in the URL, not a machine name.
- Claude Desktop shows the server but no tools: check that the server from step 2 is still
  running; the bridge only proxies, it does not start the server.
- Claude Desktop's own MCP logs on macOS: `tail -n 20 -F ~/Library/Logs/Claude/mcp*.log`.
  Adding `"--debug"` to the bridge's `args` writes a verbose log under `~/.mcp-auth/`.
