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
  --output-dir data/index
```

Expected output:

```
index written to data/index: {'municipalities': 2, 'polling_places': 3, 'polling_sections': 6, 'candidates': 16, 'candidate_social_links': 4}
```

`data/index/` (`index.duckdb` and `manifest.json`) is git-ignored. The fixture rows are
described in `tests/fixtures/README.md`; the one that reproduces verified TSE values is Acre,
zone 9, section 422.

## 2. Start the server on localhost

```sh
uv run python -m br_elections_mcp.app --index-dir data/index --port 8000
```

The server prints `Uvicorn running on http://127.0.0.1:8000`. It serves:

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
