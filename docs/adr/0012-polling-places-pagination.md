# 0012. Paginate polling places with a stable order

Status: accepted, 2026-09-28. Amends the polling places contract in `docs/codebase-design.md`
sections 3, 4 and 8.2.

## Context

The city polling places page needs to load 20 places at a time. Rio Branco, AC, has 233 places
in the published index, while `search_polling_places` and its REST route previously returned
at most 50 and ignored `offset`. Repeating a request with a different offset repeated the first
page. The candidate list already accepted an offset and echoed it in the answer.

## Decision

Add offset pagination across Core, REST and MCP, matching the candidate list. The index query
must sort deterministically before pagination; within one municipality and round, number and
zone break ties uniquely. The current input, output and ordering contract is in
`docs/codebase-design.md` section 8.2.

## Consequences

Existing calls without an offset preserve the previous sort keys before the unique tie-breaker.
Clients can request successive pages until they receive fewer than `limit` places. Production
needs a Cloud Run service deploy before the public page can use this parameter.
