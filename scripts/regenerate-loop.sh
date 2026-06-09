#!/usr/bin/env bash
# Regenerate backlog: curl POST in a loop until 11 PM or backlog cleared.
# Scheduled via systemd — see scripts/systemd-install.sh

set -euo pipefail

BASE_URL="${PIPELINE_API_BASE_URL:-http://127.0.0.1:3004}"
AMOUNT="${REGEN_AMOUNT:-4}"
SLEEP_SEC="${REGEN_SLEEP_SEC:-300}"
END_HOUR="${REGEN_END_HOUR:-23}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG="${REGEN_LOG:-${SCRIPT_DIR}/../logs/regenerate-loop.log}"

mkdir -p "$(dirname "$LOG")"

log() {
  echo "$(date -Is) $*" | tee -a "$LOG"
}

past_end_time() {
  local hour
  hour=$((10#$(date +%H)))
  [ "$hour" -ge "$END_HOUR" ]
}

query_string="journalist=FRJ1&tone=professional&article_type=news&image_model=gpt-image-1&sync_to_wordpress=true"
URL="${BASE_URL}/pipeline/regenerate/${AMOUNT}?${query_string}"

log "regenerate-loop start amount=${AMOUNT} sleep=${SLEEP_SEC}s end_hour=${END_HOUR} url=${BASE_URL}"

while ! past_end_time; do
  response_file="$(mktemp)"

  http_code="000"
  if http_code=$(curl -sS -o "$response_file" -w "%{http_code}" -X POST "$URL" -H "accept: application/json" -d ""); then
    :
  else
    log "regenerate-loop curl failed — API not reachable; will retry in ${SLEEP_SEC}s"
    rm -f "$response_file"
    sleep "$SLEEP_SEC"
    continue
  fi

  if [ "${http_code#2}" = "$http_code" ]; then
    log "regenerate-loop HTTP ${http_code}: $(cat "$response_file")"
    rm -f "$response_file"
    sleep "$SLEEP_SEC"
    continue
  fi

  found="?"
  regenerated="?"
  if command -v jq >/dev/null 2>&1; then
    found=$(jq -r '.found_without_anchors // empty' "$response_file")
    regenerated=$(jq -r '.articles_regenerated // empty' "$response_file")
  fi
  log "regenerate-loop OK regenerated=${regenerated} found_without_anchors=${found}"

  if [ "$found" = "0" ]; then
    log "regenerate-loop backlog cleared — all old articles rewritten"
    rm -f "$response_file"
    exit 0
  fi

  rm -f "$response_file"

  if past_end_time; then
    break
  fi
  sleep "$SLEEP_SEC"
done

log "regenerate-loop stopped for tonight"
