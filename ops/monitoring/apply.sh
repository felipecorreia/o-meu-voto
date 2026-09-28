#!/usr/bin/env bash
# Applies the Cloud Monitoring objects kept in ops/monitoring/ (ops/README.md): the email
# notification channel, the dashboard, the /health uptime check and its alert policy (the only
# alert, by design: ops/README.md section 3).
# Idempotent: each object is found by its displayName and replaced in place, or created once.
# Usage: PROJECT_ID=... ops/monitoring/apply.sh [--dry-run] [TARGET...]
#   TARGET: channel, dashboard, uptime, policy-uptime; default all four, in that order (the
#   policy needs the uptime check and the channel).
#   ALERT_EMAIL is read only when the channel does not exist yet; an existing channel is reused
#   untouched. --dry-run only reads: it prints what each target would create or update and the
#   request body, and changes nothing.
#   REGION and SERVICE default to southamerica-east1 and br-elections-mcp.
# Calls the Monitoring REST API with `gcloud auth print-access-token`, so it needs no gcloud
# alpha/beta components; needs gcloud, curl and jq. The project ID, the run.app host and the
# alert email are read at apply time and never written to the repository.
set -euo pipefail
: "${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-southamerica-east1}"
SERVICE="${SERVICE:-br-elections-mcp}"
CHANNEL_NAME="$SERVICE alerts"
DIR="$(cd "$(dirname "$0")" && pwd)"
API=https://monitoring.googleapis.com
DRY=0
if [[ "${1:-}" == --dry-run ]]; then DRY=1; shift; fi
ALL=(channel dashboard uptime policy-uptime)
TARGETS=("$@")
[[ ${#TARGETS[@]} -gt 0 ]] || TARGETS=("${ALL[@]}")
for t in "${TARGETS[@]}"; do
  [[ " ${ALL[*]} " == *" $t "* ]] || { echo "unknown target: $t (known: ${ALL[*]})" >&2; exit 2; }
done

fail() { echo "FAIL: $*" >&2; exit 1; }
TOKEN="$(gcloud auth print-access-token)"
call() { # call METHOD URL [BODY] -> response body; exits on a non-2xx answer
  local out code
  out="$(curl -sS -X "$1" "$2" -w $'\n%{http_code}' \
    -H "authorization: Bearer $TOKEN" -H "x-goog-user-project: $PROJECT_ID" \
    -H 'content-type: application/json' ${3:+--data-binary "$3"})"
  code="${out##*$'\n'}"
  out="${out%$'\n'*}"
  [[ "$code" == 2* ]] || fail "$1 $2 answered $code: $out"
  printf '%s' "$out"
}
find_name() { # find_name COLLECTION_URL ITEMS_KEY DISPLAY_NAME -> resource name, or empty
  local names
  names="$(call GET "$1?pageSize=1000" |
    jq -r --arg k "$2" --arg n "$3" '.[$k][]? | select(.displayName == $n) | .name')"
  [[ "$(grep -c . <<<"$names")" -le 1 ]] || fail "more than one object named '$3' in $1"
  printf '%s' "$names"
}
upsert() { # upsert KIND COLLECTION_URL ITEMS_KEY BODY [UPDATE_MASK]
  local name display
  display="$(jq -r .displayName <<<"$4")"
  name="$(find_name "$2" "$3" "$display")"
  if [[ $DRY == 1 ]]; then
    if [[ -n "$name" ]]; then echo "would update $1 '$display': $name"
    else echo "would create $1 '$display':"; fi
    jq . <<<"$4"
    return
  fi
  if [[ -n "$name" ]]; then
    local url="${2%%/projects/*}/$name" etag
    # A dashboard update must carry the live etag; the other kinds have none.
    etag="$(call GET "$url" | jq -r '.etag // empty')"
    call PATCH "$url${5:+?updateMask=$5}" "$(jq --arg n "$name" --arg e "$etag" \
      '.name = $n | if $e == "" then . else .etag = $e end' <<<"$4")" >/dev/null
    echo "updated $1 '$display': $name"
  else
    name="$(call POST "$2" "$4" | jq -r .name)"
    echo "created $1 '$display': $name"
  fi
}
wants() { [[ " ${TARGETS[*]} " == *" $1 "* ]]; }

V1="$API/v1/projects/$PROJECT_ID"
V3="$API/v3/projects/$PROJECT_ID"

channel=""
resolve_channel() {
  channel="$(find_name "$V3/notificationChannels" notificationChannels "$CHANNEL_NAME")"
}
resolve_channel
if wants channel; then
  if [[ -n "$channel" ]]; then
    echo "reusing channel '$CHANNEL_NAME': $channel"
  elif [[ $DRY == 1 ]]; then
    echo "would create email channel '$CHANNEL_NAME' for ALERT_EMAIL"
  else
    : "${ALERT_EMAIL:?set ALERT_EMAIL to create the notification channel}"
    channel="$(call POST "$V3/notificationChannels" "$(jq -n --arg n "$CHANNEL_NAME" \
      --arg e "$ALERT_EMAIL" '{type: "email", displayName: $n, labels: {email_address: $e}}')" |
      jq -r .name)"
    echo "created channel '$CHANNEL_NAME': $channel"
  fi
fi

if wants dashboard; then
  upsert dashboard "$V1/dashboards" dashboards "$(cat "$DIR/dashboard.json")"
fi

if wants uptime; then
  host="$(gcloud run services describe "$SERVICE" --region="$REGION" --project="$PROJECT_ID" \
    --format='value(status.url)')"
  host="${host#https://}"
  [[ -n "$host" ]] || fail "no URL for Cloud Run service $SERVICE"
  upsert "uptime check" "$V3/uptimeCheckConfigs" uptimeCheckConfigs \
    "$(jq --arg p "$PROJECT_ID" --arg h "$host" \
      '.monitoredResource.labels = {project_id: $p, host: $h}' "$DIR/uptime-health.json")" \
    displayName,httpCheck,period,timeout,selectedRegions
fi

if wants policy-uptime; then
  if [[ -z "$channel" ]]; then
    [[ $DRY == 1 ]] || fail "no channel '$CHANNEL_NAME' yet: apply the channel target first"
    channel="projects/$PROJECT_ID/notificationChannels/NEW"
  fi
  check="$(find_name "$V3/uptimeCheckConfigs" uptimeCheckConfigs \
    "$(jq -r .displayName "$DIR/uptime-health.json")")"
  if [[ -z "$check" ]]; then
    [[ $DRY == 1 ]] || fail "no uptime check yet: apply the uptime target first"
    check=NEW
  fi
  upsert "alert policy" "$V3/alertPolicies" alertPolicies \
    "$(jq --arg c "$channel" --arg id "${check##*/}" '.notificationChannels = [$c]
      | .conditions[0].conditionThreshold.filter |= sub("__CHECK_ID__"; $id)' \
      "$DIR/policy-uptime.json")"
fi
