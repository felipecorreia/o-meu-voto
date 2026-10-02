# API guide

How to call O meu voto from an agent or a program: over MCP for AI assistants, or over REST for
anything else. Both doors serve the same query core and return the same answer envelope. This
page is the guide; the field-by-field reference is the generated OpenAPI, so it never goes
stale:

- **OpenAPI:** <https://omeuvoto.pages.dev/api/v1/openapi.json>
- **Interactive page (Swagger UI):** <https://omeuvoto.pages.dev/api/v1/docs>

Field names are English identifiers; the domain values, warnings and guidance texts are in
Portuguese, the language of the voter and of the TSE.

## Base URL and access

| | |
|---|---|
| REST | `https://omeuvoto.pages.dev/api/v1` (GET only) |
| MCP | `https://omeuvoto.pages.dev/mcp` (Streamable HTTP, POST only) |
| Auth | None. No API key, no sign-in, no OAuth |
| Data | TSE open data, CC-BY, read-only; every answer cites its source |

There are no CORS headers, so call it from a server, an agent or the command line, not from a
script on a page of another origin.

## Connect over MCP

Claude Code:

```sh
claude mcp add --transport http --scope project o-meu-voto https://omeuvoto.pages.dev/mcp
```

Clients that read an `mcpServers` file with a remote URL, such as Cursor:

```json
{
  "mcpServers": {
    "o-meu-voto": {
      "url": "https://omeuvoto.pages.dev/mcp"
    }
  }
}
```

The setup text for chat assistants, with the exact steps for each client (in Portuguese), is
[`web-next/public/prompt-llm.md`](../web-next/public/prompt-llm.md), served at
<https://omeuvoto.pages.dev/prompt-llm>.

The server is stateless and sends no server-initiated messages, so `GET /mcp` answers `405`;
every call is a JSON-RPC `POST`. A raw call, without a client SDK:

```sh
curl -s -X POST https://omeuvoto.pages.dev/mcp \
  -H 'content-type: application/json' \
  -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"election_info","arguments":{}}}'
```

The result carries `structuredContent` (the envelope below, described by each tool's
`outputSchema`) and a short Portuguese `content` text for clients that ignore structured output.

## Tools and routes

Seven read-only tools, one REST route each (the profile has two routes, by id and by ballot
number). The tool and the route take the same inputs under the same names, except where noted.

| MCP tool | REST route | Answers | Key inputs |
|---|---|---|---|
| `election_info` | `GET /election` | Election dates, rounds, voting hours, offices, official calendar source | `on` (date, default today) |
| `list_candidates` | `GET /candidates` | Candidates of one office in one state, paged | `uf` (`BR` for president), `office`, `party`, `name`, `limit`, `offset`, `round` |
| `get_candidate` | `GET /candidates/{sq_candidato}`, `GET /candidates/by-number` | One candidate profile with running mates, declared social links and the official TSE page | `sq_candidato`, or `uf` + `office` + `number` |
| `compare_candidates` | `GET /candidates/compare` | 2 to 4 candidacies of one office side by side, always in ballot-number order | `uf`, `office`, `numbers` or `sq_candidatos` (REST: `number`, `sq`) |
| `find_polling_place` | `GET /polling-place` | The polling place of a zone and section from the voter title | `uf`, `zone`, `section` |
| `search_polling_places` | `GET /polling-places` | Polling places of a city, filtered or sorted by distance | `uf`, `municipality`, `neighborhood`, `query`, `near` (REST: `lat` + `lon`), `limit`, `offset` |
| `resolve_municipality` | `GET /municipalities` | The TSE code of a city from its name, with or without accents | `name`, `uf` |

`office` is one of `presidente`, `governador`, `senador`, `deputado_federal`,
`deputado_estadual`, `deputado_distrital`. Every candidate and polling-place tool also takes an
optional `round`; without it, candidates answer for the most recent round of the office and
polling places for the next round the TSE has published. Nothing takes a name or CPF of a
voter: the zone and section come from the voter title.

## REST quickstart

When is the election:

```sh
curl -s https://omeuvoto.pages.dev/api/v1/election
```

Compare two Senate candidates in São Paulo by ballot number (repeat `number` or separate the
values with commas):

```sh
curl -s 'https://omeuvoto.pages.dev/api/v1/candidates/compare?uf=SP&office=senador&number=180,400'
```

Find the polling place of zone 1, section 1 in São Paulo:

```sh
curl -s 'https://omeuvoto.pages.dev/api/v1/polling-place?uf=SP&zone=1&section=1'
```

An abridged, illustrative comparison answer (fictional candidate and example values, not live
data), to show the envelope:

```json
{
  "data": {
    "round": 1,
    "uf": "SP",
    "office": "senador",
    "candidates": [
      {
        "sq_candidato": 100000000001,
        "number": 111,
        "ballot_name": "CANDIDATA EXEMPLO",
        "party": { "number": 11, "acronym": "EXE", "name": "PARTIDO EXEMPLO" },
        "adjudication_status": "DEFERIDO",
        "on_ballot": true,
        "assets": { "state": "declarados", "total": 100000.00 }
      }
    ],
    "missing": [],
    "...": "..."
  },
  "not_found": null,
  "warnings": ["Exemplo de aviso: os dados podem ter mudado desde a última atualização do TSE."],
  "election": {
    "id": "general-2026",
    "name": "Eleições Gerais 2026",
    "round": { "number": 1, "date": "2026-10-04" },
    "...": "..."
  },
  "source": {
    "kind": "dataset",
    "dataset": "Candidatos - 2026",
    "dataset_url": "https://dadosabertos.tse.jus.br/dataset/candidatos-2026",
    "file": "consulta_cand_2026_BRASIL.csv",
    "generated_at": "2026-01-01T00:00:00-03:00",
    "stale": false,
    "license": "CC-BY",
    "attribution": "Tribunal Superior Eleitoral - Portal de Dados Abertos"
  }
}
```

## The answer envelope

Every tool and route returns the same five top-level fields:

- `data`: the answer, or `null` when `not_found` is set.
- `not_found`: `null`, or `reason` (a Portuguese enum such as `secao_nao_encontrada` or
  `candidaturas_insuficientes`), `guidance` (what the voter can do next) and, for an ambiguous
  city, `options`. A miss is a normal answer, not an error.
- `warnings`: Portuguese sentences to pass on to the voter, such as stale data, a polling place
  that changed or a round the TSE has not published yet. Empty when nothing applies.
- `election`: the election and round the answer refers to.
- `source`: the TSE dataset, file and generation timestamp the answer came from, the age of the
  data and the CC-BY attribution. `election_info` cites the electoral calendar instead.

An assistant should answer only from these fields, cite `source` and relay `warnings`. The
contract behind the envelope is section 8 of [`codebase-design.md`](codebase-design.md) (in
Portuguese).

## Errors and status codes

| Status | When | Body |
|---|---|---|
| `200` | An answer, including a `not_found` miss | The envelope |
| `400` | An input outside the domain, such as an unknown state or office | `{"detail": "UF desconhecida: 'XX'"}` |
| `422` | A required parameter is missing, or `sq_candidato` is not a number | FastAPI's validation `detail` list |
| `429` | Over the per-IP rate limit | `{"detail": "too many requests"}`, with a `Retry-After` header in seconds |
| `503` | The index is not loaded yet | `{"detail": "..."}` |

Over MCP, a `400` case is a tool result with `isError: true` and the same message as text; an
unavailable index is a JSON-RPC internal error.

## Usage notes

- The service applies a per-IP rate limit, with a separate budget for `/mcp`; the numbers are
  deployment settings, not part of the contract. Back off on `429`.
- REST answers are cached at the edge for 60 seconds, except requests that carry coordinates
  (`lat`/`lon`), which are never cached.
- The data refreshes several times a day; `source.generated_at` and `source.stale` say how
  fresh an answer is.
- No answer carries a candidate's CPF, voter title number, birth date or e-mail, and the
  comparison never ranks, scores or recommends. [Data and privacy](../README.md#data-and-privacy)
  in the README has the details.
