#!/usr/bin/env bash
set -euo pipefail

echo "=============================================="
echo "Sprint 4 Verification Script"
echo "=============================================="

NEWS_PORT="${NEWS_PORT:-8003}"
RADAR_PORT="${RADAR_PORT:-8002}"
AS_OF="${AS_OF:-2026-01-28}"
USER_ID="${USER_ID:-tony}"
BASE_CCY="${BASE_CCY:-TWD}"
PLUGIN="${PLUGIN:-v1.4}"

POSTGRES_SVC="${POSTGRES_SVC:-postgres}"
DB_NAME="${DB_NAME:-investment_db}"
DB_USER="${DB_USER:-investment}"

echo
echo "Config:"
echo "  NEWS_PORT=$NEWS_PORT"
echo "  RADAR_PORT=$RADAR_PORT"
echo "  AS_OF=$AS_OF"
echo "  USER_ID=$USER_ID"
echo "  BASE_CCY=$BASE_CCY"
echo "  PLUGIN=$PLUGIN"
echo "  POSTGRES_SVC=$POSTGRES_SVC"
echo "  DB_NAME=$DB_NAME"
echo "  DB_USER=$DB_USER"
echo

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
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

step() { echo; echo "[$1] $2"; }

step "1/8" "Building and starting services..."
./dc.sh up -d --build
echo "  ✓ services started"

step "2/8" "Running DB migrations (portfolio/news/radar)..."
./dc.sh exec -T portfolio-service alembic upgrade head >/dev/null
./dc.sh exec -T news-service alembic upgrade head >/dev/null
./dc.sh exec -T radar-service alembic upgrade head >/dev/null

step "3/8" "Seeding news_signals by calling news-service..."
wait_http_200 "http://localhost:${NEWS_PORT}/health" "news-service"
wait_http_200 "http://localhost:${RADAR_PORT}/health" "radar-service"

curl -sf "http://localhost:${NEWS_PORT}/news/signals?as_of=${AS_OF}&user_id=${USER_ID}" \
  | jq -e '.items|length >= 5' >/dev/null
echo "  ✓ news-service seeded (items >= 5)"

step "4/8" "Testing radar-service decision fusion endpoint..."
RESP="$(curl -sf "http://localhost:${RADAR_PORT}/radar/decision?user_id=${USER_ID}&as_of=${AS_OF}&base_ccy=${BASE_CCY}&plugin=${PLUGIN}")"

echo "$RESP" | jq -e '.decision' >/dev/null
echo "$RESP" | jq -e '.mode' >/dev/null
echo "$RESP" | jq -e '.evidence.inputs_hash' >/dev/null
echo "$RESP" | jq -e '.evidence.news_context' >/dev/null
echo "$RESP" | jq -e '.evidence.news_context.tiers_count.N1 >= 0' >/dev/null
echo "$RESP" | jq -e '.evidence.news_context.tiers_count.N3 >= 0' >/dev/null
echo "$RESP" | jq -e '.actions|type=="array"' >/dev/null
echo "  ✓ radar decision fusion response schema OK"

step "5/8" "Verifying decision_snapshots persistence + idempotency..."
TABLE_EXISTS="$(./dc.sh exec -T ${POSTGRES_SVC} psql -U ${DB_USER} -d ${DB_NAME} -tAc \
  "select to_regclass('public.decision_snapshots');")"
if [[ "${TABLE_EXISTS}" != "decision_snapshots" ]]; then
  echo "  ✗ decision_snapshots table not found in ${DB_NAME}"
  exit 1
fi
echo "  ✓ decision_snapshots table exists"

UNIQUE_EXISTS="$(./dc.sh exec -T ${POSTGRES_SVC} psql -U ${DB_USER} -d ${DB_NAME} -tAc \
  "select count(*) from pg_constraint where conname='uq_decision_snapshots_user_asof_plugin';")"
if [[ "${UNIQUE_EXISTS}" -lt 1 ]]; then
  echo "  ✗ unique constraint uq_decision_snapshots_user_asof_plugin not found"
  exit 1
fi
echo "  ✓ unique constraint exists (user_id, as_of, plugin)"

COUNT_BEFORE="$(./dc.sh exec -T ${POSTGRES_SVC} psql -U ${DB_USER} -d ${DB_NAME} -tAc \
  "select count(*) from decision_snapshots where user_id='${USER_ID}' and as_of='${AS_OF}' and plugin='${PLUGIN}';")"

RESP2="$(curl -sf "http://localhost:${RADAR_PORT}/radar/decision?user_id=${USER_ID}&as_of=${AS_OF}&base_ccy=${BASE_CCY}&plugin=${PLUGIN}")"

COUNT_AFTER="$(./dc.sh exec -T ${POSTGRES_SVC} psql -U ${DB_USER} -d ${DB_NAME} -tAc \
  "select count(*) from decision_snapshots where user_id='${USER_ID}' and as_of='${AS_OF}' and plugin='${PLUGIN}';")"

if [[ "${COUNT_BEFORE}" != "${COUNT_AFTER}" ]]; then
  echo "  ✗ idempotency failed: count before=${COUNT_BEFORE}, after=${COUNT_AFTER}"
  exit 1
fi
echo "  ✓ decision_snapshots idempotency OK (count=${COUNT_AFTER})"

HASH1="$(echo "$RESP"  | jq -r '.evidence.inputs_hash')"
HASH2="$(echo "$RESP2" | jq -r '.evidence.inputs_hash')"
if [[ "${HASH1}" != "${HASH2}" ]]; then
  echo "  ✗ inputs_hash changed between identical calls: ${HASH1} vs ${HASH2}"
  exit 1
fi
echo "  ✓ inputs_hash stable across identical calls"

step "6/8" "Hard acceptance checks (news_context + triggers)..."
echo "$RESP" | jq -e '
  (
    ([.actions[].falsifiable_triggers|length] | add // 0) >= 1
  ) and (
    (.evidence.news_context.items_used|length // 0) >= 1
  )
' >/dev/null
echo "  ✓ triggers + items_used present"

step "7/8" "Running pytest (radar-service)..."
./dc.sh exec -T radar-service pytest -q
echo "  ✓ radar-service pytest PASSED"

step "8/8" "(Optional) Smoke test history endpoint..."
curl -sf "http://localhost:${RADAR_PORT}/radar/decisions/history?user_id=${USER_ID}&limit=5" \
  | jq -e 'type=="array"' >/dev/null
echo "  ✓ history endpoint OK"

echo
echo "=============================================="
echo "✅ Sprint 4 PASSED"
echo "=============================================="
