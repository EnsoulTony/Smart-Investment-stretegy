#!/usr/bin/env bash
set -euo pipefail

echo "=============================================="
echo "Sprint 9 Verification Script"
echo "=============================================="

NEWS_PORT="${NEWS_PORT:-8003}"
RADAR_PORT="${RADAR_PORT:-8002}"
PORTFOLIO_PORT="${PORTFOLIO_PORT:-8001}"
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
echo "  PORTFOLIO_PORT=$PORTFOLIO_PORT"
echo "  USER_ID=$USER_ID"
echo "  PLUGIN=$PLUGIN"
echo "  BASE_CCY=$BASE_CCY"
echo "  POSTGRES_SVC=$POSTGRES_SVC"
echo "  DB_NAME=$DB_NAME"
echo "  DB_USER=$DB_USER"
echo

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

step() { echo; echo "[$1/8] $2"; }

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

step "1" "Building and starting services..."
./dc.sh up -d --build
echo "  ✓ services started"

step "2" "Running DB migrations (portfolio/news/radar)..."
./dc.sh exec -T portfolio-service alembic upgrade head >/dev/null
./dc.sh exec -T news-service alembic upgrade head >/dev/null
./dc.sh exec -T radar-service alembic upgrade head >/dev/null
echo "  ✓ migrations complete"

step "3" "Seeding news_signals (2026-01-26/27/28)..."
wait_http_200 "http://localhost:${NEWS_PORT}/health" "news-service"
wait_http_200 "http://localhost:${RADAR_PORT}/health" "radar-service"

for DATE in 2026-01-26 2026-01-27 2026-01-28; do
  curl -sf "http://localhost:${NEWS_PORT}/news/signals?as_of=${DATE}&user_id=${USER_ID}" \
    | jq -e '.items|length >= 5' >/dev/null
  echo "  ✓ news-service seeded (${DATE})"
done

step "4" "Calling radar-service /radar/decision to get inputs_hash..."
declare -A INPUTS_HASH_BY_DATE
for DATE in 2026-01-26 2026-01-27 2026-01-28; do
  DECISION_RESP="$(curl -sf "http://localhost:${RADAR_PORT}/radar/decision?as_of=${DATE}&user_id=${USER_ID}&base_ccy=${BASE_CCY}&plugin=${PLUGIN}")"
  RAW_INPUTS_HASH="$(echo "$DECISION_RESP" | jq -r '.evidence.inputs_hash // empty')"
  INPUTS_HASH="$(printf '%s' "$RAW_INPUTS_HASH" | tr -d '\r\n')"
  if [[ -z "${INPUTS_HASH}" ]]; then
    echo "  ✗ inputs_hash not found for ${DATE}"
    exit 1
  fi
  if [[ ! "${INPUTS_HASH}" =~ ^[0-9a-f]{64}$ ]]; then
    echo "  ✗ inputs_hash invalid for ${DATE}: ${INPUTS_HASH}"
    exit 1
  fi
  INPUTS_HASH_BY_DATE["${DATE}"]="${INPUTS_HASH}"
  echo "  ✓ inputs_hash[${DATE}]=${INPUTS_HASH}"
done

step "5" "POST /portfolio/outcomes (win/loss/neutral)..."
post_outcome() {
  local as_of="$1"
  local label="$2"
  local inputs_hash="$3"

  curl -sf "http://localhost:${PORTFOLIO_PORT}/portfolio/outcomes" \
    -H "Content-Type: application/json" \
    -d "{\"user_id\":\"${USER_ID}\",\"as_of\":\"${as_of}\",\"plugin\":\"${PLUGIN}\",\"decision_inputs_hash\":\"${inputs_hash}\",\"outcome_label\":\"${label}\",\"outcome_note\":\"\"}" \
    | jq -e ".outcome_label==\"${label}\"" >/dev/null
  echo "  ✓ outcome ${label} saved (${as_of})"
}

post_outcome "2026-01-26" "win" "${INPUTS_HASH_BY_DATE["2026-01-26"]}"
post_outcome "2026-01-27" "loss" "${INPUTS_HASH_BY_DATE["2026-01-27"]}"
post_outcome "2026-01-28" "neutral" "${INPUTS_HASH_BY_DATE["2026-01-28"]}"

step "6" "GET /radar/analytics/triggers..."
TRIGGER_ANALYTICS="$(curl -sf "http://localhost:${RADAR_PORT}/radar/analytics/triggers?user_id=${USER_ID}&plugin=${PLUGIN}&from=2026-01-26&to=2026-01-28&only_triggered=true")"
echo "$TRIGGER_ANALYTICS" | jq -e '.items|length >= 1' >/dev/null
echo "$TRIGGER_ANALYTICS" | jq -e 'all(.items[]; (.wins + .losses + .neutral + .unknown) == .total)' >/dev/null
echo "  ✓ trigger analytics OK"

step "7" "GET /radar/analytics/decisions..."
DECISION_ANALYTICS="$(curl -sf "http://localhost:${RADAR_PORT}/radar/analytics/decisions?user_id=${USER_ID}&plugin=${PLUGIN}&from=2026-01-26&to=2026-01-28&group_by=decision")"
echo "$DECISION_ANALYTICS" | jq -e '.items|length >= 1' >/dev/null
echo "$DECISION_ANALYTICS" | jq -e 'all(.items[]; (.wins + .losses + .neutral + .unknown) == .total)' >/dev/null
echo "  ✓ decision analytics OK"

step "8" "Checking frontend marker..."
curl -sI "http://localhost:8080" | head -n 3 >/dev/null
if curl -s "http://localhost:8080" | grep -q "Outcome Analytics"; then
  echo "  ✓ Outcome Analytics marker found"
else
  echo "  ✗ Outcome Analytics marker missing"
  exit 1
fi

echo
echo "✅ Sprint 9 PASSED"
