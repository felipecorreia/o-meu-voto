# Operating the Cloud Run service: capacity, budget, monitoring

What ADR 0011 decided, as commands and files: one instance at most, a R$ 150/month budget, a
Cloud Monitoring dashboard with one alert policy kept as code. The log exclusion ADR 0011 also
decided was tried and removed (section 4). Every command below changes the live
project; run each one on its own and check it before the next.

```sh
export PROJECT_ID=PROJECT_ID               # the live project; kept out of the repository
export REGION=southamerica-east1
export SERVICE=br-elections-mcp
export BILLING_ACCOUNT_ID=BILLING_ACCOUNT_ID  # gcloud billing projects describe "$PROJECT_ID"
export CLOUDSDK_PYTHON=$(uv python find 3.12)
```

Pass `--project="$PROJECT_ID"` on every gcloud call rather than changing the active config.
Budget commands also need `--billing-project="$PROJECT_ID"`, because the Budget API may be off
on the default quota project.

| File | What it is |
|---|---|
| `monitoring/dashboard.json` | The dashboard `br-elections-mcp - Cloud Run` |
| `monitoring/uptime-health.json` | Uptime check on `GET /health` of the `run.app` URL; the host is filled in at apply time |
| `monitoring/policy-uptime.json` | The one alert policy, `/health` failing |
| `monitoring/apply.sh` | Applies the channel, dashboard, uptime check and policies, idempotently |

## 1. Capacity: one instance

```sh
gcloud run services update "$SERVICE" --region="$REGION" --project="$PROJECT_ID" \
  --max=1 --max-instances=1 --min-instances=0
```

- `--max` is the service-level ceiling and changes without a new revision; `--max-instances`
  is fixed on each revision, so this command deploys a new revision of the same image (one cold
  start). Cloud Run applies the lower of the two, so a later `gcloud run deploy` that forgets
  `--max-instances` still cannot pass one instance. Runbook step C2 carries both flags.
- Verify: `gcloud run services describe "$SERVICE" --region="$REGION" --project="$PROJECT_ID"
  --format=yaml | grep -i maxscale` prints `'1'` for both `run.googleapis.com/maxScale` and
  `autoscaling.knative.dev/maxScale`.
- Undo (the values before 2026-09-28): `--max=20 --max-instances=5`.
- Cost: none by itself; it lowers the worst case. Capacity becomes one instance at
  concurrency 80, then Cloud Run answers 429.

## 2. Budget: R$ 150 per month

The project budget already exists (created in runbook step A2); update it instead of adding a
second one. Find its ID with
`gcloud billing budgets list --billing-account="$BILLING_ACCOUNT_ID" --billing-project="$PROJECT_ID" --project="$PROJECT_ID"`,
picking the one whose `budgetFilter.projects` names this project.

```sh
gcloud billing budgets update BUDGET_ID --billing-account="$BILLING_ACCOUNT_ID" \
  --billing-project="$PROJECT_ID" --project="$PROJECT_ID" --budget-amount=150BRL \
  --clear-threshold-rules \
  --add-threshold-rule=percent=0.5 --add-threshold-rule=percent=0.9 \
  --add-threshold-rule=percent=1.0 --add-threshold-rule=percent=1.0,basis=forecasted-spend \
  --notifications-rule-monitoring-notification-channels=CHANNEL
```

- Emails at 50%, 90% and 100% of actual spend and at 100% of forecast spend, to the billing
  account's administrators and to the alert channel of section 3 (`CHANNEL` is the channel's
  full name that `apply.sh channel` prints). The amount must be in the billing account's
  currency (`gcloud billing accounts describe "$BILLING_ACCOUNT_ID" --format='value(currencyCode)'`).
- It alerts only. Billing data lags by hours, so an abuse spike shows on the dashboard long
  before the budget email.
- Verify: the same `budgets list` shows `units: '150'` and the four rules.
- `percent` is a fraction (0.5 is 50%), whatever `--help` says. Do not use
  `--threshold-rules-from-file` instead: in gcloud 560 its GA (v1) branch also sets the
  v1beta1 request's `updateMask`, a field the v1 request lacks
  (`command_lib/billingbudgets/hooks.py`, read, not run).
- Undo: the same command with `--budget-amount=50BRL` and only the three current-spend
  `--add-threshold-rule` flags after `--clear-threshold-rules`.
- Cost: free.

## 3. Dashboard, uptime check and alert policy

```sh
ALERT_EMAIL=you@example.com ops/monitoring/apply.sh --dry-run   # reads only, prints the plan
ALERT_EMAIL=you@example.com ops/monitoring/apply.sh channel     # then one target at a time:
ops/monitoring/apply.sh dashboard
ops/monitoring/apply.sh uptime
ops/monitoring/apply.sh policy-uptime
```

With no target it applies all four in that order. Each object is found by its display name and
replaced in place, or created once, so running it again after editing a JSON file updates the
live object; edits made in the console are overwritten by the next apply. The channel is
created only when missing (`ALERT_EMAIL` is read only then) and an existing one is reused
untouched. The script calls the Monitoring REST API with `gcloud auth print-access-token`, so
it needs no gcloud alpha or beta component. `--dry-run` does not ask the API to validate the bodies; for
the dashboard, a POST of `dashboard.json` to `v1/projects/$PROJECT_ID/dashboards?validateOnly=true`
does, without creating anything.

**Reading the dashboard** (Monitoring, Dashboards, `br-elections-mcp - Cloud Run`):

- Requests per second by response class: `2xx` is normal traffic; a band of `4xx` is usually
  the edge secret's 403 on direct `run.app` calls or the app rate limiter's 429.
- 5xx ratio: the share of requests that failed on the server, with a reference line at 5%.
- Latency p50/p95/p99: server time of each request. About 55 ms at p95 on 2026-09-28.
- Instances by state, with the ceiling of 1 as a line. `active` is serving, `idle` is kept
  warm; the uptime check's requests every 20 seconds should keep one instance warm (inferred).
- Max concurrent requests per instance, p99, against the concurrency limit of 80, with a
  reference line at 60: the capacity gauge at one instance.
- CPU and memory utilization, p50 and p99, with a reference line at 80% CPU.
- Container startup latency: the cold start, including the index download. About 10.5 s at
  p99 on 2026-09-28.
- Uptime check: the fraction of `/health` checks that passed, per checker region.

**One alert, by design.** The only alert policy is `/health failing`: it emails the channel
when the uptime check fails from 2 or more of its 3 regions for 2 minutes, and closes itself
30 minutes after it clears. One region failing is usually that region's network; two for two
checks is the service, and the email arrives within about 3 minutes. Besides it, only the
budget emails (section 2) reach the inbox.

5xx errors, saturation and instance count are dashboard-only, on 2026-09-28's decision: every
extra alert is one more email to remember to act on, and from 2027-09-01 each policy is billed
per metric it references. The reference lines on the dashboard (5% of 5xx, concurrency 60 of
80, CPU 80%) mark where to worry when looking; they page nobody. An alert on instance count at
the ceiling would also be useless here: at a ceiling of one instance it holds whenever an
instance is up.

The `/health` check uses the `run.app` URL because `/health` is exempt from the edge secret
and the Pages domain does not route it (`scripts/smoke.sh`). It hits the service 3 times a
minute.

**Undo:** delete by name (the names are printed by `apply.sh` and listed by the commands below):

```sh
gcloud monitoring dashboards list --project="$PROJECT_ID" --format='value(name,displayName)'
gcloud monitoring dashboards delete DASHBOARD_NAME --project="$PROJECT_ID"
gcloud monitoring uptime list-configs --project="$PROJECT_ID" --format='value(name,displayName)'
gcloud monitoring uptime delete UPTIME_CHECK_ID --project="$PROJECT_ID"
# The alert policy and the channel, with the REST API (gcloud has them only in alpha/beta):
curl -X DELETE -H "authorization: Bearer $(gcloud auth print-access-token)" \
  "https://monitoring.googleapis.com/v3/POLICY_OR_CHANNEL_NAME"
```

Delete the policy before the uptime check and the channel, which it references.

**Cost:** Google Cloud system metrics and dashboards are free. Uptime checks: 1 million
executions per project per month free, then US$ 0.30 per 1,000; this check runs about 130,000 a
month. Alert policies are free until 2027-09-01, then US$ 0.35 a month per metric referenced
(the one policy references one, the uptime check). Email channels: free.
Pricing read 2026-09-28 at https://cloud.google.com/stackdriver/pricing.

## 4. Logs: the voter-location exclusion was tried and removed

Every request writes its URL to the platform request log `run.googleapis.com/requests` and to
the uvicorn access log `run.googleapis.com/stdout`, kept 30 days in the `_Default` bucket. For
`/api/v1/polling-places?lat=...&lon=...` and `/api/v1/polling-place?zone=...&section=...` that
URL is the voter's location or polling section (ADR 0004, ADR 0011).

On 2026-09-28 an exclusion on the `_Default` sink was added to drop those entries:

```sh
gcloud logging sinks update _Default --project="$PROJECT_ID" \
  --add-exclusion="name=voter-location-params,description=...,filter=FILTER"
# FILTER: resource.type="cloud_run_revision" AND resource.labels.service_name="br-elections-mcp"
#   AND (httpRequest.requestUrl=~"(?i)[?&](lat|lon|zone|section)="
#   OR textPayload=~"(?i)[?&](lat|lon|zone|section)=")
```

The same filter used as a `gcloud logging read` query selected exactly the right entries, but
the exclusion did not drop them at ingestion: one request at the public landmark coordinates of
the 2026-09-26 security review (`lat=-9.9754&lon=-67.8109`, never a real voter's), sent
through Pages about 90 seconds and again about 6.5 minutes after the exclusion was added, was
stored both times in both logs. The cause was not found (propagation delay or a difference in
how ingestion evaluates the regex are the guesses). The captain decided to remove it the same
day:

```sh
gcloud logging sinks update _Default --project="$PROJECT_ID" --remove-exclusions=voter-location-params
```

So request logs carrying lat/lon or zone/section keep their 30-day retention, and ADR 0004's
"user inputs are not persisted" still does not hold in the Cloud Run logs; `wiki/pendencias.md`
item 9 stays open. For the same reason the dashboard has no logs panel (a test keeps it out):
it would display those URLs. A retry should check the exclusion with the landmark request
before trusting it; a regex-free filter using the `:` substring operator is the untried
alternative.
