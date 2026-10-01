# 0010. Edge secret instead of Cloudflare IP ranges; `CF-Connecting-IP` trusted on a valid secret

Status: accepted, 2026-09-25. Amends ADR 0005.

## Context

ADR 0005 put the service on Cloud Run, reachable only through Cloudflare, and read the client
IP from `CF-Connecting-IP` only when the request came from Cloudflare's published ranges. The
deploy runbook (the private operations runbook, 2026-09-24) found that neither half holds on Cloud Run
with the Cloudflare Free plan:

- Cloud Run ingress offers only `all`, `internal` and `internal-and-cloud-load-balancing`, with
  no IP allow-list, and nothing found says Cloud Run can check the client certificates that
  Cloudflare Authenticated Origin Pulls needs. The `run.app` URL stays public.
- The TCP peer the app sees on Cloud Run is Google's front end, never a Cloudflare address, so
  the range check never passed: every voter would share one rate-limit bucket per instance.
- On the Free plan the page's domain reaches `run.app` only through a Pages Function
  (`web-next/functions/[[path]].js`), a Worker subrequest. Cloudflare sets `CF-Connecting-IP` on
  that subrequest to the real client IP, and a client cannot alter it
  (https://developers.cloudflare.com/fundamentals/reference/http-headers/).
- `GET /mcp` opens a Streamable HTTP event stream that never closes on its own; on Cloud Run
  each open stream keeps an instance billed at the active rate.

The captain answered the runbook's decisions on 2026-09-25: trust `CF-Connecting-IP` on a valid
edge secret and correct the min-instance cost of ADR 0005 (D8); the edge secret lands before the
public announcement, because Cloudflare does not close direct `run.app` access by itself (D7);
no warm instance for now, to see how the service runs and is adopted first (D6).

## Decision

- The Pages Function sends a shared secret as `x-edge-secret`. When `BR_ELECTIONS_EDGE_SECRET`
  is set, the service answers `403` to every request that does not carry it, except `/healthz`,
  which Cloud Run's probes call directly. Unset (local runs, tests), nothing is checked.
- `CF-Connecting-IP` is trusted only on a request that carried the valid secret: it becomes the
  client address the per-IP rate limit counts by. Without a configured secret the header is
  ignored. The Cloudflare IP-range check is removed.
- The service answers `GET /mcp` with `405` (`Allow: POST`), as the Streamable HTTP spec
  allows a server that sends no server-initiated messages. The Pages Function does the same at
  the edge; the app covers traffic that reaches `run.app` directly.
- The check lives in `edge.py`, an ASGI middleware at the composition root outside the rate
  limit (codebase-design section 4). Neither adapter knows about it.

## Consequences

- "Origin restricted to Cloudflare" in ADR 0005 now means "origin answers only requests that
  carry the edge secret". The `run.app` URL still answers `/healthz`, which carries no personal
  data.
- The secret lives in two places, the Pages project (`EDGE_SECRET`) and the Cloud Run service
  (`BR_ELECTIONS_EDGE_SECRET`); rotating it means setting both, and requests fail with `403`
  between the two changes.
- The app-level per-IP limit can be turned on in production once the secret is set; the
  Cloudflare rate-limiting rule stays the first level.
- The min-instance cost in ADR 0005 ("na ordem de US$ 6 a 7 por mês") was out of date. At the
  Tier-2 idle price for `southamerica-east1` read on 2026-09-24 (US$ 0.0000035 per vCPU-second
  plus US$ 0.0000035 per GiB-second, https://cloud.google.com/run/pricing), one warm instance
  of 1 vCPU and 1 GiB costs about US$ 18.40 a month, or about US$ 4.23 for election week
  alone. No warm instance for now (D6); the cold start of ADR 0005 applies.
