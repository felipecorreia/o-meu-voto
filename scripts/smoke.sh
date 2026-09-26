#!/usr/bin/env bash
# Smoke test of the four voter questions and the candidate comparison over REST and MCP
# (docs/deploy-runbook.md, step F1).
# Usage: scripts/smoke.sh https://BASE [https://HEALTH_BASE]
#   /health is read from HEALTH_BASE (default BASE): the Pages domain does not route /health,
#   so behind Cloudflare pass the run.app URL as HEALTH_BASE. Use /health, not /healthz: Cloud
#   Run reserves paths ending in "z" on the default run.app domain and answers them with its
#   own 404 for external requests (a documented known issue); the internal startup and
#   liveness probes are unaffected and stay on /healthz. Needs curl and jq.
# Acre zone 9, section 422 is the fixture row that reproduces verified TSE values, so it exists
# in the fixture index and in the real one alike.
set -euo pipefail
BASE="${1:?usage: smoke.sh https://BASE [https://HEALTH_BASE]}"
HEALTH="${2:-$BASE}"
fail() { echo "FAIL: $*" >&2; exit 1; }
get() { curl -fsS --max-time 20 "$1"; }
rest() { get "$BASE/api/v1/$1"; }
mcp() { # mcp <tool> <json arguments>
  curl -fsS --max-time 20 -X POST "$BASE/mcp" \
    -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
    -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"$1\",\"arguments\":$2}}"
}
# check <label> <json> <jq filter that must be true> [jq filter to print]
check() {
  jq -e "$3" >/dev/null <<<"$2" || fail "$1"
  echo "ok  $1${4:+: $(jq -c "$4" <<<"$2")}"
}

check health "$(get "$HEALTH/health")" '.index_version != null' \
  '{index_version, index_built_at, stale, last_index_check_at}'
# Q1 onde voto
check "REST Q1 polling-place AC 9/422" "$(rest 'polling-place?uf=ac&zone=9&section=422')" \
  '.data.place.name | length > 0' '.data.place.name'
# Q2 locais da cidade
check "REST Q2 polling-places Rio Branco" "$(rest 'polling-places?uf=ac&municipality=rio%20branco&limit=3')" \
  '.data.places | length > 0' '.data.places | length'
# Q3 candidatos
candidates="$(rest 'candidates?uf=ac&office=governador')"
check "REST Q3 candidates AC governador" "$candidates" \
  '.data.candidates | length > 0' '.data.candidates | length'
# The comparison page's call: the first two on-ballot candidacies of that list, side by side.
read -r sq1 sq2 < <(jq -r '[.data.candidates[] | select(.on_ballot) | .sq_candidato][:2] | @tsv' <<<"$candidates")
[ -n "${sq2:-}" ] || fail "fewer than two on-ballot candidacies to compare"
check "REST compare AC governador" "$(rest "candidates/compare?uf=ac&office=governador&sq=$sq1&sq=$sq2")" \
  '(.data.candidates | length) == 2 and (.data.candidates | map(.number) | . == sort)' \
  '[.data.candidates[] | {number, vote_destination, assets: .assets.state}]'
# Q4 quando
check "REST Q4 election" "$(rest election)" '.data.name | length > 0' '.data.name'
# The same four over MCP
for call in \
  'find_polling_place {"uf":"AC","zone":9,"section":422}' \
  'search_polling_places {"uf":"AC","municipality":"Rio Branco","limit":3}' \
  'list_candidates {"uf":"AC","office":"governador"}' \
  'election_info {}' \
  "compare_candidates {\"uf\":\"AC\",\"office\":\"governador\",\"sq_candidatos\":[$sq1,$sq2]}"; do
  tool="${call%% *}"
  args="${call#* }"
  check "MCP $tool" "$(mcp "$tool" "$args")" \
    '.result.isError != true and .result.structuredContent.data != null'
done
echo "ALL OK against $BASE"
