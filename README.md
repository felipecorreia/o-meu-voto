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

## Telemetry

Anonymous product telemetry, off by default and switchable off by configuration. When enabled,
each MCP tool call and REST request sends one PostHog event with the tool name or route, the
latency, whether the answer was stale and which round it answered, and the not-found reason
when there was one. It never carries the caller's IP, any part of the request (UF, zone,
section, municipality, name, ballot number), or a session or device identifier; the distinct id
is a constant fixed per deployment, never generated per caller. Telemetry is sent outside the
request path and a PostHog outage never delays or fails a query. See
[`docs/local-run.md`](docs/local-run.md) for the environment variables that enable it.

## Status

Six tools in place over an Acre fixture index (pipeline `build` stage, `core`): "where do I
vote" (MCP tool `find_polling_place`, `GET /api/v1/polling-place`), "when is the election"
(MCP tool `election_info`, `GET /api/v1/election`), the sanitized candidate list (MCP tool
`list_candidates`, `GET /api/v1/candidates`), the candidate profile (MCP tool `get_candidate`,
`GET /api/v1/candidates/by-number` and `GET /api/v1/candidates/{sq_candidato}`), "what is this
municipality's TSE code" (MCP tool
`resolve_municipality`, `GET /api/v1/municipalities`) and "polling places by city or
neighborhood" (MCP tool `search_polling_places`, `GET /api/v1/polling-places`). To run it
locally and connect Claude Desktop, see [`docs/local-run.md`](docs/local-run.md). The design
documents remain the reference:

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
installs (`curl_cffi` and the GCS client live there; see below):

```sh
uv sync --group pipeline
uv run python -m br_elections_mcp.pipeline fetch --output /tmp/tse
```

`fetch` downloads the TSE ZIPs into the given directory and writes `fetch.json` next to them
(URL, HTTP status, `Last-Modified` and size per dataset), so `build` can run alone from that
directory. `--from-dir DIR` reads the ZIPs from a local directory instead of the CDN, which is
what the tests do: no test touches the network.

## Publishing the index

The whole pipeline is `fetch -> extract -> build -> validate -> publish`, each a subcommand of
`python -m br_elections_mcp.pipeline` that reads and writes files, so any one of them runs
alone. `extract` takes the `_BRASIL` CSV (or the only CSV) out of a fetched ZIP;
`current-manifest` downloads the manifest currently published, which `validate` takes as
`--previous-manifest` for its count-stability gate; `publish` sends `index.duckdb` and
`manifest.json` to the index bucket. A local run against a directory standing in for the
bucket, which `LocalDirectoryIndexSource` can then serve:

```sh
uv run python -m br_elections_mcp.pipeline publish --index-dir /tmp/tse/index \
  --local-bucket /tmp/index-bucket --prefix index
```

Layout under the prefix: `versions/{version}/index.duckdb` and
`versions/{version}/manifest.json` are kept for every published index (`{version}` is the UTC
build time plus the first twelve hex digits of the index SHA-256, so the listing sorts by
build); `index.duckdb` and `manifest.json` at the root are the current pair, the manifest
written last. Rolling back is copying an older `versions/{version}/` pair over the current
one, index first and manifest last. `publish` refuses a manifest whose `index_sha256` is not
the SHA-256 of the index next to it, and it only ever knows those two files: the raw ZIPs
and CSVs stay in the runner's temporary directory and are removed at the end of the run
(ADR 0004).

The scheduled workflow [`refresh.yml`](.github/workflows/refresh.yml) runs the chain on the
cadences the TSE declares (daily after 06:25 for polling places, four times a day after
08:30, 12:30, 16:30 and 19:30 for candidates, all America/Sao_Paulo) and on
`workflow_dispatch`; it stops at the first failed stage and writes the fetch statuses, the
manifest (generation timestamp per dataset, counts, election, SHA-256), the validation gates
and the published version to the job summary. It needs two repository secrets, which are not
in the repo and are set by the maintainer: `INDEX_BUCKET` (the GCS bucket name) and
`GCP_CREDENTIALS_JSON` (the key of a service account allowed to write that bucket);
`INDEX_BUCKET_PREFIX` is an optional repository variable. Production writes go through
`GcsBucketClient` (`pipeline/bucket.py`), the only pipeline code that talks to GCS; the tests
use an in-memory fake of the same port. The off-season run over the monthly `ATUAL` file is
not wired into the workflow yet.

### Mirroring candidate photos to R2

The `mirror-photos` stage syncs the per-UF candidate photo ZIPs
(`foto_cand<year>_<UF>_div.zip`) to an R2 bucket and writes `photo_url` into an already-built
`index.duckdb` (ADR 0004, ADR 0005):

```sh
uv run python -m br_elections_mcp.pipeline mirror-photos \
  --zips-dir /tmp/tse-photos \
  --index-dir data/index \
  --public-domain https://fotos.example.org \
  --r2-endpoint https://<account>.r2.cloudflarestorage.com \
  --r2-bucket <bucket> \
  --r2-access-key-id <id> \
  --r2-secret-access-key <secret>
```

The scheduled workflow ([`refresh.yml`](.github/workflows/refresh.yml)) runs this stage after
`validate` and before `publish`, reading the R2 credentials from five repository secrets, not
in the repo and set by the captain: `R2_PUBLIC_DOMAIN`, `R2_ENDPOINT`, `R2_BUCKET`,
`R2_ACCESS_KEY_ID` and `R2_SECRET_ACCESS_KEY` (`--public-domain` and the `--r2-*` flags above,
in order). Until they are set, the step logs why and skips; the rest of the refresh runs as
before.

One thing a real run still needs, a follow-up for the captain, not something this change
guesses at:

- **Where the photo ZIPs come from.** `--zips-dir` expects the ZIPs already on disk; unlike the
  other datasets in `pipeline/datasets.py`, the exact CDN URL for
  `foto_cand<year>_<UF>_div.zip` was not verified against the TSE portal for this change (only
  the CKAN dataset and file name pattern are documented, docs/domain-model.md section 2), so
  `refresh.yml` does not fetch them yet: `$WORK/photos` stays empty and the mirror-photos step
  skips with a log line rather than syncing an empty set, which would delete every photo
  already mirrored to R2. Wiring that download is the next step before this stage does
  anything in production.

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
