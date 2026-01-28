#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Sprint 3 Verification Script
# - news-service: /news/signals (N1/N3) contract + deterministic stub
# - pytest: news-service (+ optional radar-service if it consumes signals)
# ============================================================

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ---- Config (override via env) ----
NEWS_PORT="${NEWS_PORT:-8003}"          # <-- updated default
RADAR_PORT="${RADAR_PORT:-8002}"
AS_OF="${AS_OF:-$(date +%F)}"
USER_ID="${USER_ID:-tony}"
POSTGRES_SVC="${POSTGRES_SVC:-postgres}"
DB_NAME="${DB_NAME:-investment_db}"
DB_USER="${DB_USER:-investment}"

echo "=============================================="
echo "Sprint 3 Verification Script"
echo "=============================================="
echo
echo "Config:"
echo "  NEWS_PORT=${NEWS_PORT}"
echo "  RADAR_PORT=${RADAR_PORT}"
echo "  AS_OF=${AS_OF}"
echo "  USER_ID=${USER_ID}"
echo "  POSTGRES_SVC=${POSTGRES_SVC}"
echo "  DB_NAME=${DB_NAME}"
echo "  DB_USER=${DB_USER}"
echo

cd "${ROOT_DIR}"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "❌ Missing required command: $1"
    exit 1
  }
}

wait_http_200() {
  local url="$1"
  local name="$2"
  local tries="${3:-30}"
  local sleep_sec="${4:-1}"

  for i in $(seq 1 "${tries}"); do
    if curl -fsS "${url}" >/dev/null 2>&1; then
      echo "  ✓ ${name} is ready"
      return 0
    fi
    echo "  Waiting for ${name}... (attempt ${i}/${tries})"
    sleep "${sleep_sec}"
  done

  echo "❌ ${name} not ready after ${tries} attempts: ${url}"
  exit 1
}

need_cmd curl
need_cmd jq

echo "[1/7] Building and starting services..."
./dc.sh up -d --build

echo
echo "[1.5/7] Running DB migrations for portfolio-service..."
./dc.sh exec -T portfolio-service alembic upgrade head

echo
echo "[1.6/7] Running DB migrations for news-service..."
./dc.sh exec -T news-service alembic upgrade head

echo
echo "[2/7] Waiting for services to be ready..."
wait_http_200 "http://localhost:${NEWS_PORT}/health" "news-service"
# radar-service not strictly required for Sprint 3, but handy if later integration exists
wait_http_200 "http://localhost:${RADAR_PORT}/health" "radar-service" || true

echo
echo "[2.5/7] Checking war-room UI availability..."
UI_URL="${UI_URL:-http://localhost:8080}"
if curl -fsS "${UI_URL}" >/tmp/warroom.html; then
  if grep -Eq "Sprint 3 War Room|Smart Investment Strategy" /tmp/warroom.html; then
    echo "  ✓ war-room UI is available (${UI_URL})"
  else
    echo "❌ war-room UI loaded but content check failed (missing expected marker)"
    exit 1
  fi
else
  echo "❌ war-room UI not reachable: ${UI_URL}"
  exit 1
fi

echo
echo "[3/7] Testing news-service signals endpoint..."
SIGNALS_URL="http://localhost:${NEWS_PORT}/news/signals?user_id=${USER_ID}&as_of=${AS_OF}"

# Basic HTTP + content-type check
CONTENT_TYPE="$(curl -sI "${SIGNALS_URL}" | tr -d '\r' | awk -F': ' 'tolower($1)=="content-type"{print $2}' | tail -n1)"
if [[ "${CONTENT_TYPE}" != application/json* ]]; then
  echo "❌ Expected Content-Type application/json, got: ${CONTENT_TYPE:-<empty>}"
  exit 1
fi
echo "  ✓ Content-Type: ${CONTENT_TYPE}"

# Fetch payload once
PAYLOAD="$(curl -fsS "${SIGNALS_URL}")"

# Top-level required fields (adjust names if your schema differs, but keep it strict)
echo "${PAYLOAD}" | jq -e '
  .schema_version and
  .as_of and
  .source and
  (.items | type=="array")
' >/dev/null
echo "  ✓ Required top-level fields present (schema_version/as_of/source/items)"

# Must have >= 5 items (stub: 2 N1 + 3 N3)
ITEMS_LEN="$(echo "${PAYLOAD}" | jq '.items | length')"
if [[ "${ITEMS_LEN}" -lt 5 ]]; then
  echo "❌ Expected items length >= 5, got: ${ITEMS_LEN}"
  exit 1
fi
echo "  ✓ items length >= 5 (${ITEMS_LEN})"

# Each item required fields + triggers >= 1
echo "${PAYLOAD}" | jq -e '
  .items[] |
  (.id and .tier and .title and .published_at and .summary_zh and
   (.symbols|type=="array") and
   (.factor_groups|type=="array") and
   (.themes|type=="array") and
   (.falsifiable_triggers|type=="array") and
   (.confidence != null)
  )
' >/dev/null
echo "  ✓ All items contain required fields"

# triggers length >= 1 for each item
BAD_TRIGGERS="$(echo "${PAYLOAD}" | jq '[.items[] | select((.falsifiable_triggers|length) < 1)] | length')"
if [[ "${BAD_TRIGGERS}" -ne 0 ]]; then
  echo "❌ Found ${BAD_TRIGGERS} items with falsifiable_triggers length < 1"
  exit 1
fi
echo "  ✓ All items have >= 1 falsifiable_triggers"

# Tier distribution checks: expect at least 2 N1 and 3 N3
N1_COUNT="$(echo "${PAYLOAD}" | jq '[.items[] | select(.tier=="N1")] | length')"
N3_COUNT="$(echo "${PAYLOAD}" | jq '[.items[] | select(.tier=="N3")] | length')"

if [[ "${N1_COUNT}" -lt 2 ]]; then
  echo "❌ Expected N1 >= 2, got: ${N1_COUNT}"
  exit 1
fi
if [[ "${N3_COUNT}" -lt 3 ]]; then
  echo "❌ Expected N3 >= 3, got: ${N3_COUNT}"
  exit 1
fi
echo "  ✓ Tier distribution OK (N1=${N1_COUNT}, N3=${N3_COUNT})"

echo
echo "[4/7] Sprint 3 hard acceptance checks..."
# Ensure tiers are only N1 or N3
BAD_TIER="$(echo "${PAYLOAD}" | jq '[.items[] | select(.tier!="N1" and .tier!="N3")] | length')"
if [[ "${BAD_TIER}" -ne 0 ]]; then
  echo "❌ Found ${BAD_TIER} items with invalid tier (must be N1 or N3)"
  exit 1
fi
echo "  ✓ Tier enum valid (N1/N3 only)"

# Ensure trigger objects have required keys: type,name,condition,value
echo "${PAYLOAD}" | jq -e '
  .items[].falsifiable_triggers[] |
  (.type and .name and .condition and (.value != null))
' >/dev/null
echo "  ✓ All triggers contain required keys (type/name/condition/value)"

echo "  ✓ Sprint 3 hard acceptance checks passed"

echo
echo "[4.5/7] Verifying news_signals persistence in Postgres..."
TABLE_EXISTS="$(./dc.sh exec -T "${POSTGRES_SVC}" psql -U "${DB_USER}" -d "${DB_NAME}" -tAc "SELECT to_regclass('public.news_signals');")"
TABLE_EXISTS="$(echo "${TABLE_EXISTS}" | tr -d '[:space:]')"
if [[ -z "${TABLE_EXISTS}" || "${TABLE_EXISTS}" == "null" ]]; then
  echo "❌ news_signals table not found in ${DB_NAME}. Expected public.news_signals."
  exit 1
fi
echo "  ✓ news_signals table exists (${TABLE_EXISTS})"

ROW_COUNT="$(./dc.sh exec -T "${POSTGRES_SVC}" psql -U "${DB_USER}" -d "${DB_NAME}" -tAc "SELECT COUNT(*) FROM public.news_signals;")"
ROW_COUNT="$(echo "${ROW_COUNT}" | tr -d '[:space:]')"
if [[ -z "${ROW_COUNT}" || "${ROW_COUNT}" -lt 1 ]]; then
  echo "❌ news_signals table has no rows (count=${ROW_COUNT:-0})"
  exit 1
fi
echo "  ✓ news_signals has >= 1 rows (count=${ROW_COUNT})"

echo
echo "[5/7] Running pytest in news-service container..."
./dc.sh exec -T news-service pytest -q
echo "  ✓ news-service pytest PASSED"

echo
echo "[6/7] (Optional) Running pytest in radar-service container..."
RUN_RADAR_TESTS="${RUN_RADAR_TESTS:-1}"
if [[ "${RUN_RADAR_TESTS}" == "1" ]]; then
  ./dc.sh exec -T radar-service pytest -q
  echo "  ✓ radar-service pytest PASSED"
else
  echo "  (skipped)"
fi

echo
echo "=============================================="
echo "✅ Sprint 3 PASSED"
echo "=============================================="
echo
echo "Summary:"
echo "  - news-service: GET /news/signals ✓"
echo "  - items: ${ITEMS_LEN}"
echo "  - tiers: N1=${N1_COUNT}, N3=${N3_COUNT}"
echo "  - triggers: all items have >=1"
echo "  - pytest (news-service): PASSED"
if [[ "${RUN_RADAR_TESTS}" == "1" ]]; then
  echo "  - pytest (radar-service): PASSED"
fi
