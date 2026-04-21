#!/usr/bin/env bash
# Run pipeline for 2 articles and sync them to WordPress. For use from cron (e.g. every 15 minutes).
# Set PIPELINE_API_BASE_URL if the API is not at http://localhost:3004 (e.g. http://mirror-ai-prod:80 in Docker).

set -e
BASE_URL="${PIPELINE_API_BASE_URL:-http://localhost:3004}"
URL="${BASE_URL}/pipeline/run?amount=2&auto_build=true&journalist=FRJ1&tone=professional&article_type=news&model=gpt-image-1&sync_to_wordpress=true"
RESP=$(curl -s -w "\n%{http_code}" -X POST "$URL" -H 'accept: application/json' -d '')
HTTP_BODY=$(echo "$RESP" | head -n -1)
HTTP_CODE=$(echo "$RESP" | tail -n 1)
if [[ "$HTTP_CODE" != 2* ]]; then
  echo "pipeline-2-wp: HTTP $HTTP_CODE — $HTTP_BODY" >&2
  exit 1
fi
echo "pipeline-2-wp: OK ($HTTP_CODE) — $HTTP_BODY"
