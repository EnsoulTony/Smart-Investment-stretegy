#!/usr/bin/env bash
set -euo pipefail

echo "=============================================="
echo "Sprint 8 Verification Script"
echo "=============================================="

NEWS_PORT="${NEWS_PORT:-8003}"
RADAR_PORT="${RADAR_PORT:-8002}"
USER_ID="${USER_ID:-tony}"
PLUGIN="${PLUGIN:-v1.4}"
BASE_CCY="${BASE_CCY:-TWD}"
POSTGRES_SVC="${POSTGRES_SVC:-postgres}"
DB_NAME="${DB_NAME:-investment_db}"
DB_USER="${DB_USER:-investment}"

echo
echo "Config:"
echo "  NEWS_PORT=$NEWS_PORT"
echo "  RADAR_PORT=$RADAR_PORT"
echo "  USER_ID=$USER_ID"
echo "  PLUGIN=$PLUGIN"
echo "  BASE_CCY=$BASE_CCY"
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

step() { echo; echo "[$1/8] $2"; }

step "1" "Building and starting services..."
./dc.sh up -d --build
echo "  ✓ services started"

step "2" "Running DB migrations (portfolio/news/radar)..."
./dc.sh exec -T portfolio-service alembic upgrade head >/dev/null
./dc.sh exec -T news-service alembic upgrade head >/dev/null
./dc.sh exec -T radar-service alembic upgrade head >/dev/null

step "3" "Seeding news_signals by calling news-service..."
wait_http_200 "http://localhost:${NEWS_PORT}/health" "news-service"
wait_http_200 "http://localhost:${RADAR_PORT}/health" "radar-service"

curl -sf "http://localhost:${NEWS_PORT}/news/signals?as_of=2026-01-28&user_id=${USER_ID}" \
  | jq -e '.items|length >= 5' >/dev/null
echo "  ✓ news-service seeded (items >= 5)"

step "4" "Calling radar-service /radar/decision to get inputs_hash..."
DECISION_RESP="$(curl -sf "http://localhost:${RADAR_PORT}/radar/decision?as_of=2026-01-28&user_id=${USER_ID}&base_ccy=${BASE_CCY}&plugin=${PLUGIN}")"
RAW_INPUTS_HASH="$(echo "$DECISION_RESP" | jq -r '.evidence.inputs_hash // empty')"
INPUTS_HASH="$(printf '%s' "$RAW_INPUTS_HASH" | tr -d '\r\n')"
if [[ -z "${INPUTS_HASH}" ]]; then
  echo "  ✗ inputs_hash not found"
  exit 1
fi
if [[ ! "${INPUTS_HASH}" =~ ^[0-9a-f]{64}$ ]]; then
  echo "  ✗ inputs_hash invalid: ${INPUTS_HASH}"
  exit 1
fi
echo "  ✓ inputs_hash=${INPUTS_HASH}"

step "5" "POST /portfolio/outcomes (neutral)..."
curl -sf "http://localhost:8001/portfolio/outcomes" \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"${USER_ID}\",\"as_of\":\"2026-01-28\",\"plugin\":\"${PLUGIN}\",\"decision_inputs_hash\":\"${INPUTS_HASH}\",\"outcome_label\":\"neutral\",\"outcome_note\":\"\"}" \
  | jq -e '.outcome_label=="neutral"' >/dev/null
echo "  ✓ outcome neutral saved"

step "6" "POST /portfolio/outcomes (win) upsert..."
curl -sf "http://localhost:8001/portfolio/outcomes" \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"${USER_ID}\",\"as_of\":\"2026-01-28\",\"plugin\":\"${PLUGIN}\",\"decision_inputs_hash\":\"${INPUTS_HASH}\",\"outcome_label\":\"win\",\"outcome_note\":\"\"}" \
  | jq -e '.outcome_label=="win"' >/dev/null

COUNT_OUTCOME="$(./dc.sh exec -T ${POSTGRES_SVC} psql -U ${DB_USER} -d ${DB_NAME} -tAc \
  "select count(*) from decision_outcomes where user_id='${USER_ID}' and as_of='2026-01-28' and plugin='${PLUGIN}' and decision_inputs_hash='${INPUTS_HASH}';")"
if [[ "${COUNT_OUTCOME}" != "1" ]]; then
  echo "  ✗ upsert failed, count=${COUNT_OUTCOME}"
  exit 1
fi
echo "  ✓ upsert OK (count=1)"

step "7" "GET /portfolio/outcomes..."
curl -sf "http://localhost:8001/portfolio/outcomes?user_id=${USER_ID}&from=2026-01-01&to=2026-01-31&plugin=${PLUGIN}" \
  | jq -e '.items|length >= 1' >/dev/null
curl -sf "http://localhost:8001/portfolio/outcomes?user_id=${USER_ID}&from=2026-01-01&to=2026-01-31&plugin=${PLUGIN}" \
  | jq -e '.items[0].outcome_label=="win"' >/dev/null
echo "  ✓ outcomes list OK"

step "8" "Checking frontend marker..."
curl -sI "http://localhost:8080" | head -n 3 >/dev/null
if curl -s "http://localhost:8080" | grep -q "Decision History"; then
  echo "  ✓ Outcome UI marker found"
else
  echo "  ✗ Outcome UI marker missing"
  exit 1
fi

echo
echo "=============================================="
echo "✅ Sprint 8 PASSED"
echo "=============================================="
