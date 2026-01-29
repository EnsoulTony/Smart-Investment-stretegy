#!/usr/bin/env bash
set -euo pipefail

echo "=============================================="
echo "Sprint 7 Verification Script"
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

step() { echo; echo "[$1] $2"; }

step "1/7" "Building and starting services..."
./dc.sh up -d --build
echo "  ✓ services started"

step "2/7" "Running DB migrations (portfolio/news/radar)..."
./dc.sh exec -T portfolio-service alembic upgrade head >/dev/null
./dc.sh exec -T news-service alembic upgrade head >/dev/null
./dc.sh exec -T radar-service alembic upgrade head >/dev/null

step "3/7" "Seeding news_signals by calling news-service..."
wait_http_200 "http://localhost:${NEWS_PORT}/health" "news-service"
wait_http_200 "http://localhost:${RADAR_PORT}/health" "radar-service"

curl -sf "http://localhost:${NEWS_PORT}/news/signals?as_of=2026-01-28&user_id=${USER_ID}" \
  | jq -e '.items|length >= 5' >/dev/null
echo "  ✓ news-service seeded (items >= 5)"

step "4/7" "Calling radar-service /radar/decision..."
curl -sf "http://localhost:${RADAR_PORT}/radar/decision?as_of=2026-01-28&user_id=${USER_ID}&base_ccy=${BASE_CCY}&plugin=${PLUGIN}" \
  | jq -e '.decision' >/dev/null

COUNT_TRIGGER="$(./dc.sh exec -T ${POSTGRES_SVC} psql -U ${DB_USER} -d ${DB_NAME} -tAc \
  "select count(*) from trigger_evaluations where user_id='${USER_ID}' and plugin='${PLUGIN}';")"
if [[ "${COUNT_TRIGGER}" -lt 1 ]]; then
  echo "  ✗ trigger_evaluations empty"
  exit 1
fi
echo "  ✓ trigger_evaluations has rows (count=${COUNT_TRIGGER})"

step "5/7" "Calling /radar/triggers/history..."
HISTORY_RESP="$(curl -sf "http://localhost:${RADAR_PORT}/radar/triggers/history?user_id=${USER_ID}&plugin=${PLUGIN}&from=2026-01-01&to=2026-01-31")"
echo "$HISTORY_RESP" | jq -e '.items|length >= 1' >/dev/null
echo "  ✓ history endpoint returns items"

step "6/7" "Checking frontend war-room UI..."
curl -sI "http://localhost:8080" | head -n 3 >/dev/null
echo "  ✓ frontend reachable"

if curl -s "http://localhost:8080/war-room/triggers" | grep -q "Trigger Timeline"; then
  echo "  ✓ Trigger Timeline marker found"
else
  echo "  ✗ Trigger Timeline marker not found"
  exit 1
fi

step "7/7" "Done"

echo
echo "=============================================="
echo "✅ Sprint 7 PASSED"
echo "=============================================="
