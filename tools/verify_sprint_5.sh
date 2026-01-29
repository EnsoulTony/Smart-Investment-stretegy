#!/usr/bin/env bash
set -euo pipefail

echo "=============================================="
echo "Sprint 5 Verification Script"
echo "=============================================="

NEWS_PORT="${NEWS_PORT:-8003}"
RADAR_PORT="${RADAR_PORT:-8002}"
AS_OF="${AS_OF:-2026-01-28}"
USER_ID="${USER_ID:-tony}"
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

step "1/9" "Building and starting services..."
./dc.sh up -d --build
echo "  ✓ services started"

step "2/9" "Running DB migrations (portfolio/news/radar)..."
./dc.sh exec -T portfolio-service alembic upgrade head >/dev/null
./dc.sh exec -T news-service alembic upgrade head >/dev/null
./dc.sh exec -T radar-service alembic upgrade head >/dev/null

step "3/9" "Seeding news_signals by calling news-service..."
wait_http_200 "http://localhost:${NEWS_PORT}/health" "news-service"
wait_http_200 "http://localhost:${RADAR_PORT}/health" "radar-service"

curl -sf "http://localhost:${NEWS_PORT}/news/signals?as_of=${AS_OF}&user_id=${USER_ID}" \
  | jq -e '.items|length >= 5' >/dev/null
echo "  ✓ news-service seeded (items >= 5)"

step "4/9" "Calling radar-service /radar/decision..."
RESP="$(curl -sf "http://localhost:${RADAR_PORT}/radar/decision?user_id=${USER_ID}&as_of=${AS_OF}&base_ccy=TWD&plugin=${PLUGIN}")"

echo "$RESP" | jq -e '.decision' >/dev/null
echo "$RESP" | jq -e '.mode' >/dev/null
echo "$RESP" | jq -e '.evidence.inputs_hash' >/dev/null
echo "$RESP" | jq -e '.evidence.news_context' >/dev/null
echo "$RESP" | jq -e '.evidence.news_context.tiers_count.N1 >= 0' >/dev/null
echo "$RESP" | jq -e '.evidence.news_context.tiers_count.N3 >= 0' >/dev/null
echo "$RESP" | jq -e '.actions|type=="array"' >/dev/null
echo "  ✓ radar decision response OK"

step "5/9" "Validating trigger schema fields in response..."
echo "$RESP" | jq -e '
  def has_fields: all(.[]; has("trigger_key") and has("observed_value") and has("is_triggered"));
  (
    (.actions[].falsifiable_triggers // []) | has_fields
  )
  and (
    (.evidence.news_context.watchlist_triggers // []) | has_fields
  )
  and (
    (.evidence.news_context.primary_triggers // []) | has_fields
  )
' >/dev/null
echo "  ✓ triggers include trigger_key/observed_value/is_triggered"

step "6/9" "Verifying trigger_evaluations table + constraint..."
TABLE_EXISTS="$(./dc.sh exec -T ${POSTGRES_SVC} psql -U ${DB_USER} -d ${DB_NAME} -tAc \
  "select to_regclass('public.trigger_evaluations');")"
if [[ "${TABLE_EXISTS}" != "trigger_evaluations" ]]; then
  echo "  ✗ trigger_evaluations table not found in ${DB_NAME}"
  exit 1
fi
echo "  ✓ trigger_evaluations table exists"

UNIQUE_EXISTS="$(./dc.sh exec -T ${POSTGRES_SVC} psql -U ${DB_USER} -d ${DB_NAME} -tAc \
  "select count(*) from pg_constraint where conname='uq_trigger_eval_identity';")"
if [[ "${UNIQUE_EXISTS}" -lt 1 ]]; then
  echo "  ✗ unique constraint uq_trigger_eval_identity not found"
  exit 1
fi
echo "  ✓ unique constraint exists (user_id, as_of, plugin, decision_inputs_hash, trigger_key)"

COUNT1="$(./dc.sh exec -T ${POSTGRES_SVC} psql -U ${DB_USER} -d ${DB_NAME} -tAc \
  "select count(*) from trigger_evaluations where user_id='${USER_ID}' and as_of='${AS_OF}' and plugin='${PLUGIN}';")"
if [[ "${COUNT1}" -lt 1 ]]; then
  echo "  ✗ trigger_evaluations row count is 0"
  exit 1
fi
echo "  ✓ trigger_evaluations rows inserted (count=${COUNT1})"

step "7/9" "Replaying /radar/decision to validate idempotency..."
RESP2="$(curl -sf "http://localhost:${RADAR_PORT}/radar/decision?user_id=${USER_ID}&as_of=${AS_OF}&base_ccy=TWD&plugin=${PLUGIN}")"
COUNT2="$(./dc.sh exec -T ${POSTGRES_SVC} psql -U ${DB_USER} -d ${DB_NAME} -tAc \
  "select count(*) from trigger_evaluations where user_id='${USER_ID}' and as_of='${AS_OF}' and plugin='${PLUGIN}';")"

if [[ "${COUNT2}" != "${COUNT1}" ]]; then
  echo "  ✗ idempotency failed: count before=${COUNT1}, after=${COUNT2}"
  exit 1
fi
echo "  ✓ trigger_evaluations idempotency OK (count=${COUNT2})"

step "8/9" "(Optional) Running pytest (radar-service)..."
./dc.sh exec -T radar-service pytest -q
echo "  ✓ radar-service pytest PASSED"

step "9/9" "Smoke test history endpoint..."
curl -sf "http://localhost:${RADAR_PORT}/radar/decisions/history?user_id=${USER_ID}&limit=5" \
  | jq -e 'type=="array"' >/dev/null
echo "  ✓ history endpoint OK"

echo
echo "=============================================="
echo "✅ Sprint 5 PASSED"
echo "=============================================="
