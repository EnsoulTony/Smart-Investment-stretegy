#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

step() {
  echo -e "${BLUE}==> STEP:${NC} $1"
  echo "command: $2"
}

pass() {
  echo -e "${GREEN}decision=pass${NC}"
}

fail() {
  local rule_id="$1"
  local evidence="$2"
  echo -e "${RED}decision=fail${NC} rule_id=${rule_id}"
  echo "evidence=${evidence}"
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "PRECHECK-MISSING-CMD" "missing_command=$1"
}

require_cmd rg
require_cmd docker

step "Forbidden tokens scan: valuation-service" "rg -n -o <pattern> services/valuation-service/app services/valuation-service/requirements.txt"
VAL_PATTERN='sqlalchemy|psycopg2|psycopg2-binary|asyncpg|postgresql://|mysql://|create_engine|Session\(|DATABASE_URL|POSTGRES_|PGHOST|PGPORT|PGUSER|PGPASSWORD'
VAL_HITS=$(rg -n -o "$VAL_PATTERN" services/valuation-service/app services/valuation-service/requirements.txt || true)
if [ -n "$VAL_HITS" ]; then
  fail "VAL-FT-1" "${VAL_HITS//$'\n'/; }"
fi
pass

target_files=(
  services/portfolio-service/app/position_rebuilder.py
  services/portfolio-service/app/avg_cost_calculator.py
  services/portfolio-service/app/main.py
  services/portfolio-service/app/trades_repository.py
)

step "Forbidden tokens scan: portfolio-service accounting layer" "rg -n -o <pattern> position_rebuilder/avg_cost_calculator/main/trades_repository"
PORT_PATTERN='convert\(|get_rate|get_fx_provider|valuation|market_value|valuation_ccy|unrealized_pnl'
PORT_HITS=$(rg -n -o "$PORT_PATTERN" "${target_files[@]}" || true)
if [ -n "$PORT_HITS" ]; then
  fail "PORT-FT-1" "${PORT_HITS//$'\n'/; }"
fi
pass

step "docker compose config env allow-list: valuation-service" "docker compose config | sed -n '/valuation-service:/,/^[^ ]/p'"
COMPOSE_CONFIG=$(docker compose config)

get_env_keys() {
  local svc="$1"
  echo "$COMPOSE_CONFIG" | awk -v svc="$svc" '
    $0 ~ "^  "svc":" {svc_on=1; next}
    svc_on && $0 ~ "^  [^ ]" {svc_on=0}
    svc_on && $1=="environment:" {env_on=1; next}
    svc_on && env_on && $0 ~ "^    [^ ]" {env_on=0}
    svc_on && env_on && $0 ~ "^      [A-Za-z0-9_]+:" {
      gsub(":", "", $1); print $1
    }
  '
}

get_env_value() {
  local svc="$1"
  local key="$2"
  echo "$COMPOSE_CONFIG" | awk -v svc="$svc" -v key="$key" '
    $0 ~ "^  "svc":" {svc_on=1; next}
    svc_on && $0 ~ "^  [^ ]" {svc_on=0}
    svc_on && $1=="environment:" {env_on=1; next}
    svc_on && env_on && $0 ~ "^    [^ ]" {env_on=0}
    svc_on && env_on && $1==key":" {
      $1=""; sub(/^ /, ""); print; exit
    }
  '
}

VAL_KEYS=( $(get_env_keys valuation-service) )
if [ ${#VAL_KEYS[@]} -eq 0 ]; then
  fail "COMPOSE-VAL-NOENV" "valuation-service env keys empty"
fi

echo "valuation-service env keys (masked):"
for key in "${VAL_KEYS[@]}"; do
  echo "  - ${key}=***"
  done

ALLOWED_VAL_KEYS=(PORT PORTFOLIO_BASE_URL SERVICE_NAME)
extra=()
missing=()
for key in "${VAL_KEYS[@]}"; do
  found=0
  for allow in "${ALLOWED_VAL_KEYS[@]}"; do
    if [ "$key" = "$allow" ]; then
      found=1
      break
    fi
  done
  if [ $found -eq 0 ]; then
    extra+=("$key")
  fi
 done

for allow in "${ALLOWED_VAL_KEYS[@]}"; do
  found=0
  for key in "${VAL_KEYS[@]}"; do
    if [ "$key" = "$allow" ]; then
      found=1
      break
    fi
  done
  if [ $found -eq 0 ]; then
    missing+=("$allow")
  fi
 done

if [ ${#extra[@]} -ne 0 ]; then
  fail "COMPOSE-VAL-ALLOWLIST" "extra_keys=${extra[*]}"
fi
if [ ${#missing[@]} -ne 0 ]; then
  fail "COMPOSE-VAL-ALLOWLIST" "missing_keys=${missing[*]}"
fi
pass

step "docker compose config env checks: portfolio-service" "docker compose config | sed -n '/portfolio-service:/,/^[^ ]/p'"
PORT_KEYS=( $(get_env_keys portfolio-service) )
if [ ${#PORT_KEYS[@]} -eq 0 ]; then
  fail "COMPOSE-PORT-NOENV" "portfolio-service env keys empty"
fi

echo "portfolio-service env keys (masked):"
for key in "${PORT_KEYS[@]}"; do
  echo "  - ${key}=***"
  done

for key in "${PORT_KEYS[@]}"; do
  if [ "$key" = "GOOGLE_SA_JSON" ]; then
    fail "COMPOSE-PORT-SECRET" "forbidden_key=GOOGLE_SA_JSON"
  fi
 done

HAS_SA_PATH=0
for key in "${PORT_KEYS[@]}"; do
  if [ "$key" = "GOOGLE_SA_JSON_PATH" ]; then
    HAS_SA_PATH=1
  fi
 done
if [ $HAS_SA_PATH -eq 0 ]; then
  fail "COMPOSE-PORT-SECRET" "missing_key=GOOGLE_SA_JSON_PATH"
fi

SA_PATH_VALUE=$(get_env_value portfolio-service GOOGLE_SA_JSON_PATH || true)
EXPECTED_SA_PATH="/run/secrets/google_sa.json"
if [ -n "$SA_PATH_VALUE" ] && [ "$SA_PATH_VALUE" != "$EXPECTED_SA_PATH" ]; then
  fail "COMPOSE-PORT-SECRET" "GOOGLE_SA_JSON_PATH=*** expected=/run/secrets/google_sa.json"
fi

HAS_DB_URL=0
for key in "${PORT_KEYS[@]}"; do
  if [ "$key" = "DATABASE_URL" ]; then
    HAS_DB_URL=1
  fi
 done
if [ $HAS_DB_URL -eq 0 ]; then
  fail "COMPOSE-PORT-DB" "missing_key=DATABASE_URL"
fi
pass

step "pytest (container): portfolio-service" "docker compose exec -T portfolio-service pytest -q"
RUNNING_SERVICES=$(docker compose ps --status running --services || true)
if ! echo "$RUNNING_SERVICES" | grep -qx "portfolio-service"; then
  fail "PRECHECK-SVC-RUNNING" "portfolio-service not running; run: docker compose up -d portfolio-service"
fi
if ! echo "$RUNNING_SERVICES" | grep -qx "valuation-service"; then
  fail "PRECHECK-SVC-RUNNING" "valuation-service not running; run: docker compose up -d valuation-service"
fi

docker compose exec -T portfolio-service pytest -q
pass

step "pytest collect-only (portfolio-service)" "docker compose exec -T portfolio-service pytest -q --collect-only | tail -n 50"
docker compose exec -T portfolio-service pytest -q --collect-only | tail -n 50
pass

step "pytest (container): valuation-service" "docker compose exec -T valuation-service pytest -q"
docker compose exec -T valuation-service pytest -q
pass

step "pytest collect-only (valuation-service)" "docker compose exec -T valuation-service pytest -q --collect-only | tail -n 50"
docker compose exec -T valuation-service pytest -q --collect-only | tail -n 50
pass

echo -e "${GREEN}All PR checks passed.${NC}"
