# The refresh pipeline

**Who this is for:** whoever runs or changes the data refresh. This is operator material, not
an introduction. To use or call the service, start at the [README](../README.md); to run it
locally, read [`local-run.md`](local-run.md). Come here to fetch the TSE files, build and
publish the index, or load the candidate photos.

How the index the service reads is built and published, and how candidate photos reach R2. The
architecture overview is [`architecture.md`](architecture.md); the stage contracts are in
[`codebase-design.md`](codebase-design.md), section 5.

## Running the stages

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

The workflow [`refresh.yml`](../.github/workflows/refresh.yml) runs the chain on the cadences
the TSE declares (daily after 06:25 for polling places, four times a day after 08:30, 12:30,
16:30 and 19:30 for candidates, all America/Sao_Paulo), started through `workflow_dispatch`
by Cloud Scheduler, since GitHub's own cron fired hours late ([`ops/README.md`](../ops/README.md),
section 6), or by hand; index stages stop at the first failure, while photo failures are reported
after a valid index is published. The job summary writes the fetch statuses, the
manifest (generation timestamp per dataset, counts, election, SHA-256), the validation gates
and the published version to the job summary. It reaches Google Cloud without a stored key,
through Workload Identity Federation: each run trades its GitHub OIDC token for a short-lived
token of the publisher service account, and the provider accepts only this repository's
`main` branch. The configuration is not in the repo and is set by the maintainer
(the private operations runbook, step B3): the `INDEX_BUCKET` secret (the GCS bucket name) and two
repository variables, `GCP_WORKLOAD_IDENTITY_PROVIDER` (the provider's full resource name) and
`GCP_PUBLISHER_SA` (the email of the service account allowed to write that bucket);
`INDEX_BUCKET_PREFIX` is an optional repository variable. The first step fails with a message
naming whatever is missing. Production writes go through
`GcsBucketClient` (`pipeline/bucket.py`), the only pipeline code that talks to GCS; the tests
use an in-memory fake of the same port. The off-season run over the monthly `ATUAL` file is
not wired into the workflow yet.

### Mirroring candidate photos to R2

Two stages carry the per-UF candidate photo ZIPs (`foto_cand<year>_<UF>_div.zip`) to an R2
bucket and write `photo_url` into an already-built `index.duckdb` (ADR 0004, ADR 0005).
`fetch --photos` downloads them through the same `Downloader` port as the datasets (ADR 0003)
and leaves a `fetch.json` next to them, with URL, status, `Last-Modified` and size per file;
`mirror-photos` syncs them:

```sh
uv run python -m br_elections_mcp.pipeline fetch --photos --output /tmp/tse-photos
uv run python -m br_elections_mcp.pipeline mirror-photos \
  --zips-dir /tmp/tse-photos \
  --index-dir data/index \
  --public-domain https://fotos.example.org \
  --r2-endpoint https://<account>.r2.cloudflarestorage.com \
  --r2-bucket <bucket> \
  --r2-access-key-id <id> \
  --r2-secret-access-key <secret> \
  --retain-old-photos
```

The CDN serves 28 ZIPs at
`https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/fotos/foto_cand2026_<UF>_div.zip`:
the 26 states, `DF` and `BR` (the president and vice; `ZZ` has no candidacies). All 28 answered
200 on 2026-09-29, about 125 MB together and 20,984 photos, one per candidacy. Each ZIP also
carries a `leiame.pdf`, which `mirror-photos` ignores; any other entry that is not a
`F<UF><SQ_CANDIDATO>_div.jpg` still fails the run. The registry is `CANDIDATE_PHOTOS_2026` in
`pipeline/datasets.py`, kept out of `DATASETS` because the index build never reads it.

The refresh workflow ([`refresh.yml`](../.github/workflows/refresh.yml)) reads the R2 credentials
from five repository secrets, not in the repo and set by the captain: `R2_PUBLIC_DOMAIN`,
`R2_ENDPOINT`, `R2_BUCKET`, `R2_ACCESS_KEY_ID` and `R2_SECRET_ACCESS_KEY` (`--public-domain`
and the `--r2-*` flags above, in order). Until all five are set, it logs why and neither
downloads the photo ZIPs nor mirrors them; the rest of the refresh runs as before, and every
`photo_url` stays null. With credentials set, the workflow waits for the verified completion
marker written by the manual full load. It then runs `fetch --photos` right after the
dataset fetch and gives `mirror-photos` a 15-minute budget after `validate`. A failed photo
step, or a failed completion-marker query, does not block index publication; it fails the run
after `publish` so the photo failure remains visible. The run summary lists how many photo ZIPs answered 200 and each photo-step
outcome. The first full load has a separate manually dispatched workflow with a six-hour
job budget; see below and [ADR 0014](adr/0014-photo-refresh-independent-of-index-publication.md).

The production workflow passes `--retain-old-photos`: the mirror leaves content-addressed
objects in R2 even when the TSE changes or removes a photo, because deleting an old key before
a new index is published can break the live index. They are removed later, after `publish`,
by `clean-photos` (below). `mirror-photos` still refuses a `--zips-dir` that lacks
any of the 28 ZIPs. Before mirroring, the refresh carries previously published photo URLs
only when the prior index is hash-verified, the current TSE photo has the same SHA-256, and
the R2 ETag matches its bytes. A timed-out mirror therefore cannot publish a URL for a
partial upload. The final photo chain is checked again before `publish`.
The full-load marker is written only after all photos and the temporary index have been
verified; refreshes that overlap the first load skip their own mirror and still publish.

The first production full load completed on 2026-09-30. For a new deployment, run the full load
once from `main`:

```sh
gh workflow run photo-full-load.yml --ref main
```

Wait for **Full candidate photo load** to finish successfully. Its mirror output reports
the R2 object count seen before the run, uploads every 500 objects, and ends with uploaded
and skipped totals. In the Cloudflare R2 bucket dashboard, confirm the object count is at
least 20,984 (the 2026-09-29 source count; superseded keys may make it higher). Then run or
wait for the next ordinary **Refresh index**. With GCP read access to the index bucket and
`INDEX_BUCKET`/`INDEX_BUCKET_PREFIX` set, inspect the newly published index:

```sh
prefix="${INDEX_BUCKET_PREFIX#/}"
prefix="${prefix%/}"
gcloud storage cp "gs://$INDEX_BUCKET/${prefix:+$prefix/}index.duckdb" ./index.duckdb
uv run python - <<'PY'
import duckdb
conn = duckdb.connect("index.duckdb", read_only=True)
print("photo URLs:", conn.execute("SELECT count(*) FROM candidates WHERE photo_url IS NOT NULL").fetchone()[0])
print("sample URL:", conn.execute("SELECT photo_url FROM candidates WHERE photo_url IS NOT NULL LIMIT 1").fetchone()[0])
PY
```

The count must be positive. Fetch the printed sample `*.r2.dev` URL and confirm HTTP 200
and `Content-Type: image/jpeg` (for example, `curl -I '<sample URL>'`). For a new deployment,
publish Cloudflare Pages after verifying the photo URLs.

#### Removing photos the TSE no longer publishes

`clean-photos` runs in the refresh right after `publish`, only when every photo stage of the run
succeeded, and never in the full load ([ADR 0015](adr/0015-publication-aware-photo-cleanup.md)).
It deletes an R2 object only after no index current in the last 48 hours has referenced it: a
Cloud Run instance swaps its index only after a query, so an idle one can still serve a pair
several refreshes old. The first-unreferenced times live in a ledger in the index bucket,
`photo-cleanup/unreferenced.json`. The stage refuses, deleting nothing and failing the run, when
a pair does not verify, the live manifest is not the pair just published, the R2 listing lacks
an object the published index references (these write no ledger, so the clocks restart), or
more than 10% of the photo objects would go (this one keeps the ledger, so the clocks keep
running and every following refresh fails the same way until someone looks; run the stage by
hand with a higher `--max-delete-fraction` when the removal is legitimate). The stage's output,
refusal included, is in the "Photo steps" section of the refresh run summary.

Deletion is off on merge: until the repository variable `PHOTO_CLEANUP_MODE` is `delete`, every
refresh runs the stage as a dry run. It writes the ledger so the 48-hour clock runs, deletes
nothing, and prints the counts in the run summary and in the "Clean up R2 photos no served
index references" step:

```sh
gh workflow run refresh.yml --ref main   # or wait for the next scheduled refresh
gh run view --log "$(gh run list --workflow refresh.yml --limit 1 --json databaseId --jq '.[0].databaseId')" | grep clean-photos
```

The dry run reports `would delete 0` until 48 hours of consecutive dry runs have passed. When
its counts look right, enable deletion with `gh variable set PHOTO_CLEANUP_MODE --body delete`;
`gh variable delete PHOTO_CLEANUP_MODE` (or any value other than `delete`) goes back to dry
runs. Deleting needs the R2 token to allow `DeleteObject` on the bucket.

#### Photo integrity: what stops a swapped photo

A candidate's face is what a voter recognises first, and it is served from a public bucket the
index does not control. The design is in [ADR 0013](adr/0013-content-addressed-photo-mirror.md):

- Objects are named after the SHA-256 of the JPEG bytes in the TSE ZIP,
  `F<UF><SQ>_div-<sha256>.jpg`, and the index records the same digest in `photo_sha256` next to
  `photo_url`. A key has exactly one legitimate content; when the TSE changes a photo, the URL
  changes.
- `mirror-photos` never overwrites a key. If one already exists with a checksum (R2's ETag)
  that is not the MD5 of the ZIP's photo, the run fails with `PhotoIntegrityError`, having
  uploaded and deleted nothing, and names the key. After uploading it lists the bucket again
  and requires every photo of the run to be there with the expected checksum before it deletes
  anything (production skips the deletion with `--retain-old-photos`).
- Once the index is written, `photo_url` must carry the recorded digest and the candidacy's
  `sq_candidato`; `mirror-photos` checks it and `validate` has a gate for it (`photo_chain`).
  `verify-photos` runs that check on the pair about to be published and stops the run before
  `publish` on any failure, so the index in the bucket is never replaced by one with a broken
  chain. A failed mirror step does not: the validated index goes out with the photo URLs
  already verified.
- A failed mirror step is the alarm for an object still expected from the current TSE ZIPs:
  `refusing to overwrite` means that object is not what the TSE published. The refresh
  publishes a valid index first, then marks the run failed.
  Delete that object, rotate the R2 token and re-run; the pipeline does not repair it silently.

| Threat | Covered? |
|---|---|
| R2 credentials leak; someone replaces or corrupts a photo object | Detected at the next refresh when the current TSE ZIPs still contain that photo: the mirror refuses to overwrite it. Carry-forward also drops a prior URL whose current bytes do not match R2. The index can publish without that URL, and the run then reports the photo failure. **Not prevented:** until detection, voters see the swapped photo because an `<img>` cannot verify a digest. |
| Someone uploads extra objects to the bucket | Not served (the index never points to them). With `PHOTO_CLEANUP_MODE=delete`, `clean-photos` removes those with a photo key after 48 hours unreferenced; objects with any other key stay. |
| The index or a `photo_url` is edited by hand or half-written | `photo_chain` rejects broken digest and candidate pairs, malformed URLs, and mixed origins; with `--photo-public-domain`, it also requires the exact configured base URL and key. `mirror-photos` checks that exact URL before touching R2 and again after updating the index. A consistently rewritten index still requires a trusted public domain at validation. |
| R2 credentials **and** the GCS publisher (or the workflow itself) are compromised | Not covered: both the objects and the index can be rewritten consistently. Keep the two credentials separate and the R2 token scoped to this bucket. |
| The TSE, or the CDN download, serves a wrong photo | Not covered: it is mirrored faithfully. The digest proves which bytes we took, not that the TSE meant them; the TSE publishes no signature. |
| Old objects deleted while an index still points to them | Production mirroring retains old objects; `clean-photos` deletes only after `publish` and only objects no index current in the last 48 hours references. A rollback to a version superseded longer ago can point to deleted photos until the next refresh re-mirrors them. |

The bucket name and public URL are configuration (`R2_BUCKET`, `R2_PUBLIC_DOMAIN`), never
hard-coded. Beyond this change, still to do: an audit that downloads the public URLs and
compares them with the index digests (closing the detection window), and a bucket-scoped R2
token with a bucket lock where available.

## How the pipeline downloads from the TSE

The TSE's web infrastructure, including the open-data portal and the CDN that serves the ZIPs,
sits behind a WAF (Akamai) that answers `403` to `curl`, `requests` and headless browsers, even
with browser headers. The block is on the TLS/HTTP2 fingerprint, not on a cookie or a
JavaScript challenge. The pipeline therefore downloads with
[`curl_cffi`](https://github.com/lexiforest/curl_cffi) impersonating a desktop Chrome
fingerprint. We state this openly rather than hide it
([ADR 0003](adr/0003-curl-cffi-for-tse-downloads.md)):

- **Volume.** Each refresh downloads the six dataset ZIPs in `DATASETS`, once per file. When
  photo mirroring is enabled, it also downloads up to 28 candidate photo ZIPs. Refreshes run
  at most a few times a day, aligned with the TSE's stated cadence for each dataset. The
  service never calls the TSE at request time; only the pipeline does.
- **Data.** The datasets are open data under CC-BY. Every answer attributes the TSE and cites
  the dataset, file and generation timestamp.
- **Contact.** We are asking the TSE (`estatistica@tse.jus.br`, the contact named in each
  `leiame.pdf`, and the ouvidoria) for guidance or a sanctioned route for automated reuse. If
  the TSE prefers another arrangement, we will follow it. Until then the position is: use now,
  ask at the same time.
- **A `403` is a result, not an obstacle.** The manual workflow
  [`tse-access-test.yml`](../.github/workflows/tse-access-test.yml) runs the production `fetch`
  from a GitHub-hosted runner and reports the status per dataset in the job summary. If a
  datacenter IP is blocked, the plan B of ADR 0003 (a self-hosted runner or a Cloud Run Job in
  `southamerica-east1`) is a decision to take, not a technique to add.
