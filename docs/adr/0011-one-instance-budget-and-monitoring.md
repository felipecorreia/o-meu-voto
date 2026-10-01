# 0011. One Cloud Run instance, a R$ 150 budget and monitoring as code

Status: accepted, 2026-09-28. Amends ADR 0005 (capacity of the Cloud Run service). The log
exclusion it also decided, meant to make ADR 0004's "user inputs are not persisted" hold in the
platform logs, was tried and removed the same day (Decision, Logs).

## Context

The GCP security review of 2026-09-27 (kept outside the repository, findings H1, H2 and I4)
found:

- The service ran with `--max-instances=5` (revision) under a service-level ceiling of 20, and
  the runbook's "about US$ 16/day worst case" counted only instance time. Egress, per-request
  fees and log ingestion scale with requests served; the review inferred about US$ 175-330/day
  of abuse exposure at five instances, while the project budget was R$ 50/month and only sent
  emails. The instance ceiling is also the election-day capacity: instances times concurrency
  80, then Cloud Run answers 429 (I4).
- Every request writes its full URL to two logs kept 30 days in the `_Default` bucket: the
  platform request log `run.googleapis.com/requests` and the uvicorn access log on
  `run.googleapis.com/stdout`. For `GET /api/v1/polling-places?lat=...&lon=...` and
  `GET /api/v1/polling-place?zone=...&section=...` that URL is the voter's location or polling
  section, against ADR 0004's "Entradas do usuário não são persistidas" (H1).
- Nothing watched the service: no dashboard, uptime check or alert policy existed.

The captain decided on 2026-09-28: one instance, since this is a portfolio project that will not
see a traffic explosion, and a R$ 150 budget for the project; a normal Cloud Monitoring
dashboard built from the CLI, with alert policies, since a dashboard alone protects nothing when
nobody is watching it on election day; and option (a) for the logs, excluding only the entries
that carry those parameters rather than the whole request log. Later the same day, seeing the
alert policies proposed one by one, the captain cut them to the one that matters, to keep the
inbox down to messages that need acting on; and, once the log exclusion failed to drop the
entries it targeted, removed it.

## Decision

- **Capacity.** The service runs on at most one instance, set at both levels so that neither a
  redeploy with an old revision flag nor a raised service default lifts it: `--max=1`
  (service) and `--max-instances=1` (revision), min-instances 0 (runbook step C2). No automatic
  kill switch.
- **Budget.** The project budget is R$ 150/month, emailing at 50%, 90% and 100% of actual
  spend and at 100% of forecast spend (`ops/README.md` section 2). It alerts; it never stops
  the service.
- **Monitoring as code.** The dashboard, the `/health` uptime check and one alert policy,
  `/health` failing, are JSON in `ops/monitoring/`, applied by the idempotent
  `ops/monitoring/apply.sh`. One alert by design: 5xx errors, saturation and instance count
  are dashboard-only, because every extra alert is one more email to remember and, from
  2027-09-01, one more per-metric charge. The alert and the budget go to one email channel
  whose address is read at apply time and never committed; `ops/README.md` has the threshold
  and its reason.
- **Logs.** An exclusion on the `_Default` sink meant to drop every log entry of the service
  whose request URL or text carries `lat=`, `lon=`, `zone=` or `section=` was added on
  2026-09-28. It did not drop the entries at ingestion within 6.5 minutes (a landmark request
  was stored in both logs twice, while the same filter as a read query selected it), and it was
  removed by captain decision. No log exclusion is in place; the details and the untried
  alternative are in `ops/README.md` section 4. The dashboard has no logs panel, since it
  would display those URLs.

## Consequences

- Capacity is one instance with concurrency 80. Past 80 simultaneous requests Cloud Run answers
  429. Nothing pages on it: the dashboard shows concurrency against the limit, and a
  sustained overload shows up only when someone looks or when `/health` starts failing.
  Raising the ceiling is one command
  (`ops/README.md`) and a captain decision, because it multiplies the abuse exposure.
- At one instance the abuse exposure is about a fifth of the review's estimate for five, and the
  edge secret (step D3b, set) already answers direct `run.app` traffic with a 403 of a few
  bytes. The budget emails follow billing data, which lags by hours.
- The voter's location and polling section stay in the request and access logs for the
  bucket's 30 days, so ADR 0004's "user inputs are not persisted" does not hold in the Cloud
  Run logs, and neither does its "no full IP" rule (`httpRequest.remoteIp`). Option (b) of the
  review, excluding the whole request log, was not chosen; item 9 of the private wiki's
  pending list stays open.
- No alert watches the 5xx ratio; a failure shows on the dashboard or when `/health` fails.
- The project ID, the `run.app` URL, the billing account and the alert email stay out of the
  repository: the apply script and the runbook read them at apply time.
