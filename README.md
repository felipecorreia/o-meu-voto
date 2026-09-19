# br-elections-mcp

MCP server and REST API over the open data of the Tribunal Superior Eleitoral (TSE), the
Brazilian electoral court. It answers the questions a voter asks before election day, for any
LLM connected through MCP and for a static web page, without touching any personal data.

## What it answers

- **Where do I vote?** The state, zone and section printed on the voter's title become the
  polling place address, with warnings when the place changed or the section votes at another one.
- **Polling places by city and neighborhood**, for voters who do not know their section.
- **Candidates** by office, name or ballot number: ballot name, party, federation, coalition,
  status, occupation and photo. Never CPF, voter title, birth date or e-mail.
- **Election date and voting hours**, from the official electoral calendar.

## What it never answers

Anything that depends on the individual voter registration: zone and section from a name or
CPF, the status of a voter's title, justifications or debts. Those questions are redirected to
the official e-Titulo app and TSE self-service.

## Status

Two tools in place over an Acre fixture index (pipeline `build` stage, `core`): "where do I
vote" (MCP tool `find_polling_place`, `GET /api/v1/polling-place`) and "when is the election"
(MCP tool `election_info`, `GET /api/v1/election`). To run it locally and connect Claude
Desktop, see [`docs/local-run.md`](docs/local-run.md). The design documents remain the
reference:

- [`CONTEXT.md`](CONTEXT.md) - the glossary of the domain.
- [`docs/domain-model.md`](docs/domain-model.md) - entities, invariants and the mapping from
  TSE CSV columns, including the columns discarded for privacy (LGPD).
- [`docs/codebase-design.md`](docs/codebase-design.md) - module boundaries and the contracts of
  the six tools.
- [`docs/adr/`](docs/adr/) - architecture decision records.
- [`data/elections.yaml`](data/elections.yaml) - the hand-curated electoral calendar.

## Development

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

Tests build their index from the CSV fixtures in `tests/fixtures/` with the pipeline's own
`build` stage; none of them touches the network.

The refresh pipeline has its own dependency group, `pipeline`, which the service image never
installs (`curl_cffi` lives there; see below):

```sh
uv sync --group pipeline
uv run python -m br_elections_mcp.pipeline fetch --output /tmp/tse
```

`fetch` downloads the TSE ZIPs into the given directory and writes `fetch.json` next to them
(URL, HTTP status, `Last-Modified` and size per dataset), so `build` can run alone from that
directory. `--from-dir DIR` reads the ZIPs from a local directory instead of the CDN, which is
what the tests do: no test touches the network.

## How the pipeline downloads from the TSE

The TSE's web infrastructure, including the open-data portal and the CDN that serves the ZIPs,
sits behind a WAF (Akamai) that answers `403` to `curl`, `requests` and headless browsers, even
with browser headers. The block is on the TLS/HTTP2 fingerprint, not on a cookie or a
JavaScript challenge. The pipeline therefore downloads with
[`curl_cffi`](https://github.com/lexiforest/curl_cffi) impersonating a desktop Chrome
fingerprint. We state this openly rather than hide it
([ADR 0003](docs/adr/0003-curl-cffi-for-tse-downloads.md)):

- **Volume.** One download per file per refresh, and nothing else: five ZIPs (about 95 MB in
  total) for the datasets listed in
  [`docs/tse/README.md`](docs/tse/README.md), at most a few times a day, aligned with the
  cadence the TSE itself declares for each dataset. The service never calls the TSE at request
  time; only the pipeline does.
- **Data.** The datasets are open data under CC-BY. Every answer attributes the TSE and cites
  the dataset, file and generation timestamp.
- **Contact.** We are asking the TSE (`estatistica@tse.jus.br`, the contact named in each
  `leiame.pdf`, and the ouvidoria) for guidance or a sanctioned route for automated reuse. If
  the TSE prefers another arrangement, we will follow it. Until then the position is: use now,
  ask at the same time.
- **A `403` is a result, not an obstacle.** The manual workflow
  [`tse-access-test.yml`](.github/workflows/tse-access-test.yml) runs the production `fetch`
  from a GitHub-hosted runner and reports the status per dataset in the job summary. If a
  datacenter IP is blocked, the plan B of ADR 0003 (a self-hosted runner or a Cloud Run Job in
  `southamerica-east1`) is a decision to take, not a technique to add.

## Data source and attribution

Data: Tribunal Superior Eleitoral - Portal de Dados Abertos (CC-BY),
<https://dadosabertos.tse.jus.br>. Every response carries the dataset, file and generation
timestamp it came from.

## License

MIT. See [`LICENSE`](LICENSE).
