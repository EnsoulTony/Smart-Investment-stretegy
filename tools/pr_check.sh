#!/bin/bash
# PR 自動檢查腳本（fail-fast）
# Sprint 1-4.B：在本機/CI 就能抓到 VM 才會爆的設定錯誤
#
# 檢查項目：
# 1. Forbidden tokens 靜態掃描
# 2. docker compose config 展開後 env 驗證
# 3. valuation-service API JSON 合約檢查
# 4. runtime guard 注入檢查
# 5. pytest（容器內）

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

step() {
  echo ""
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

warn() {
  echo -e "${YELLOW}warning:${NC} $1"
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "PRECHECK-MISSING-CMD" "missing_command=$1"
}

# ============================================================================
# Prerequisites Check
# ============================================================================
step "Prerequisites check" "command -v rg docker python3"
require_cmd rg
require_cmd docker
require_cmd python3
pass

# ============================================================================
# Step 1: Forbidden tokens scan - valuation-service
# ============================================================================
step "Forbidden tokens scan: valuation-service" "rg -n -o <pattern> services/valuation-service/app services/valuation-service/requirements.txt"

# Pattern 使用 split 技巧避免自己被掃到
VAL_PATTERN='sqlalchemy|psycopg2|psycopg2-binary|asyncpg|postgresql://|mysql://|create_engine|Session\(|'"DATA""BASE""_URL"'|'"POST""GRES_"'|PGHOST|PGPORT|PGUSER|PGPASSWORD'

VAL_TARGETS=(services/valuation-service/app services/valuation-service/requirements.txt)
echo "pattern=${VAL_PATTERN}"
echo "targets=${VAL_TARGETS[*]}"

VAL_HITS=$(rg -n -o "$VAL_PATTERN" "${VAL_TARGETS[@]}" 2>/dev/null || true)
VAL_COUNT=$(echo "$VAL_HITS" | sed '/^$/d' | wc -l | tr -d ' ')
echo "matches_count=${VAL_COUNT}"

if [ "$VAL_COUNT" != "0" ]; then
  fail "VAL-FT-1" "${VAL_HITS//$'\n'/; }"
fi
pass

# ============================================================================
# Step 2: Forbidden tokens scan - portfolio-service accounting layer
# ============================================================================
target_files=(
  services/portfolio-service/app/position_rebuilder.py
  services/portfolio-service/app/avg_cost_calculator.py
  services/portfolio-service/app/main.py
  services/portfolio-service/app/trades_repository.py
)

step "Forbidden tokens scan: portfolio-service accounting layer" "rg -n -o <pattern> position_rebuilder/avg_cost_calculator/main/trades_repository"

PORT_PATTERN='convert\(|get_rate|get_fx_provider|valuation|market_value|valuation_ccy|unrealized_pnl'
echo "pattern=${PORT_PATTERN}"
echo "targets=${target_files[*]}"

PORT_HITS=$(rg -n -o "$PORT_PATTERN" "${target_files[@]}" 2>/dev/null || true)
PORT_COUNT=$(echo "$PORT_HITS" | sed '/^$/d' | wc -l | tr -d ' ')
echo "matches_count=${PORT_COUNT}"

if [ "$PORT_COUNT" != "0" ]; then
  fail "PORT-FT-1" "${PORT_HITS//$'\n'/; }"
fi
pass

# ============================================================================
# Step 3: docker compose config env allow-list - valuation-service
# ============================================================================
step "docker compose config env allow-list: valuation-service" "docker compose config"

COMPOSE_CONFIG=$(docker compose config 2>/dev/null) || fail "PRECHECK-COMPOSE" "docker compose config failed"

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

REQUIRED_VAL_KEYS=(PORT PORTFOLIO_BASE_URL SERVICE_NAME)
OPTIONAL_VAL_KEYS=(PRICE_PROVIDER FX_PROVIDER)
ALLOWED_VAL_KEYS=("${REQUIRED_VAL_KEYS[@]}" "${OPTIONAL_VAL_KEYS[@]}")

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

for allow in "${REQUIRED_VAL_KEYS[@]}"; do
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
  fail "COMPOSE-VAL-ALLOWLIST" "missing_required_keys=${missing[*]}"
fi
pass

# ============================================================================
# Step 4: docker compose config env checks - portfolio-service
# ============================================================================
step "docker compose config env checks: portfolio-service" "docker compose config"

PORT_KEYS=( $(get_env_keys portfolio-service) )
if [ ${#PORT_KEYS[@]} -eq 0 ]; then
  fail "COMPOSE-PORT-NOENV" "portfolio-service env keys empty"
fi

echo "portfolio-service env keys (masked):"
for key in "${PORT_KEYS[@]}"; do
  echo "  - ${key}=***"
done

# 禁止明文 GOOGLE_SA_JSON
for key in "${PORT_KEYS[@]}"; do
  if [ "$key" = "GOOGLE_SA_JSON" ]; then
    fail "COMPOSE-PORT-SECRET" "forbidden_key=GOOGLE_SA_JSON (use GOOGLE_SA_JSON_PATH instead)"
  fi
done

# 檢查 GOOGLE_SA_JSON_PATH（如果存在）
HAS_SA_PATH=0
for key in "${PORT_KEYS[@]}"; do
  if [ "$key" = "GOOGLE_SA_JSON_PATH" ]; then
    HAS_SA_PATH=1
  fi
done
if [ $HAS_SA_PATH -eq 1 ]; then
  SA_PATH_VALUE=$(get_env_value portfolio-service GOOGLE_SA_JSON_PATH || true)
  EXPECTED_SA_PATH="/run/secrets/google_sa.json"
  if [ -n "$SA_PATH_VALUE" ] && [ "$SA_PATH_VALUE" != "$EXPECTED_SA_PATH" ]; then
    warn "GOOGLE_SA_JSON_PATH=*** (expected=$EXPECTED_SA_PATH)"
  fi
fi

# 必須有 DATABASE_URL
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

# ============================================================================
# Step 5: Check services are running
# ============================================================================
step "Check services are running" "docker compose ps --status running --services"

RUNNING_SERVICES=$(docker compose ps --status running --services 2>/dev/null || true)

if ! echo "$RUNNING_SERVICES" | grep -qx "portfolio-service"; then
  fail "PRECHECK-SVC-RUNNING" "portfolio-service not running; run: docker compose up -d portfolio-service"
fi
if ! echo "$RUNNING_SERVICES" | grep -qx "valuation-service"; then
  fail "PRECHECK-SVC-RUNNING" "valuation-service not running; run: docker compose up -d valuation-service"
fi
pass

# ============================================================================
# Step 6: Runtime env sanity check (valuation-service)
# ============================================================================
step "Runtime env sanity (valuation-service)" "docker compose exec -T valuation-service python -"

docker compose exec -T valuation-service python - <<'PY'
import os
import sys

# 使用 split token 避免自己被掃到
forbidden_exact = {
    "_".join(["DATA", "BASE", "URL"]),
    "_".join(["PORTFOLIO", "DATABASE", "URL"]),
    "".join(["PG", "HOST"]),
    "".join(["PG", "PORT"]),
    "".join(["PG", "USER"]),
    "".join(["PG", "PASSWORD"]),
    "".join(["PG", "DATABASE"]),
}
forbidden_prefixes = ("".join(["POST", "GRES", "_"]),)

hits = []
for key in os.environ.keys():
    if key in forbidden_exact:
        hits.append(key)
        continue
    for prefix in forbidden_prefixes:
        if key.startswith(prefix):
            hits.append(key)
            break

if hits:
    # 遮罩 key（只顯示首尾字元）
    def mask(k):
        if len(k) <= 4:
            return k[:1] + "*" * (len(k) - 1)
        return k[:1] + "*" * (len(k) - 2) + k[-1:]

    masked = [mask(k) for k in sorted(set(hits))]
    print(f"decision=fail rule_id=RUNTIME-VAL-DBENV evidence.blocked_keys={','.join(masked)}")
    sys.exit(1)

print("decision=pass runtime_guard=ok")
PY
pass

# ============================================================================
# Step 7: Runtime guard injection test (valuation-service)
# ============================================================================
step "Runtime guard injection test" "docker compose run --rm -e DATABASE_URL=x valuation-service python -c 'from app.guardrails import check_and_exit; check_and_exit()'"

# 這個測試預期要失敗（non-zero exit）
set +e
GUARD_OUTPUT=$(docker compose run --rm -e DATABASE_URL=test_injection valuation-service python -c "from app.guardrails import check_and_exit; check_and_exit()" 2>&1)
GUARD_EXIT=$?
set -e

if [ $GUARD_EXIT -eq 0 ]; then
  fail "RUNTIME-GUARD-INJECT" "expected non-zero exit when DATABASE_URL is injected, but got exit 0"
fi

# 確認輸出不包含 value
if echo "$GUARD_OUTPUT" | grep -q "test_injection"; then
  fail "RUNTIME-GUARD-LEAK" "guard output contains injected value (should be masked)"
fi

# 確認輸出包含 guardrail 資訊
if ! echo "$GUARD_OUTPUT" | grep -q "VAL-SVC-NO-DB"; then
  fail "RUNTIME-GUARD-ID" "guard output missing guardrail ID"
fi

echo "guard_exit_code=$GUARD_EXIT (expected non-zero)"
echo "guard_output_contains_value=no (good)"
echo "guard_output_contains_id=yes (good)"
pass

# ============================================================================
# Step 8: Valuation API JSON contract check
# ============================================================================
step "Valuation API JSON contract check" "curl valuation-service + python json.loads"

# 測試 409 場景（空 user）
echo "Testing 409 scenario (empty trades)..."
API_RESPONSE=$(curl -s -w "\n%{http_code}" "http://localhost:8005/valuation/portfolio?user_id=pr_check_empty_user_$(date +%s)")
HTTP_CODE=$(echo "$API_RESPONSE" | tail -n1)
BODY=$(echo "$API_RESPONSE" | sed '$d')

echo "http_code=$HTTP_CODE"

# 檢查是否為有效 JSON（使用 python，不依賴 jq）
if ! echo "$BODY" | python3 -c "import json,sys; json.loads(sys.stdin.read())" 2>/dev/null; then
  echo "body_preview=${BODY:0:200}"
  fail "API-JSON-409" "response is not valid JSON"
fi

# 檢查 content-type
CT_HEADER=$(curl -s -I "http://localhost:8005/valuation/portfolio?user_id=pr_check_test" | grep -i "content-type" | head -1 || true)
if ! echo "$CT_HEADER" | grep -qi "application/json"; then
  warn "content-type may not be application/json: $CT_HEADER"
fi

echo "409_response_is_valid_json=yes"

# 檢查 409 回傳結構
DETAIL_STATUS=$(echo "$BODY" | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('detail',{}).get('status',''))" 2>/dev/null || true)
if [ "$DETAIL_STATUS" = "precondition_failed" ]; then
  echo "409_detail_status=precondition_failed (correct)"
else
  echo "409_detail_status=$DETAIL_STATUS (may be upstream_error if portfolio-service unreachable)"
fi

pass

# ============================================================================
# Step 9: pytest (container) - portfolio-service
# ============================================================================
step "pytest (container): portfolio-service" "docker compose exec -T portfolio-service pytest -q"
docker compose exec -T portfolio-service pytest -q
pass

# ============================================================================
# Step 10: pytest collect-only (portfolio-service)
# ============================================================================
step "pytest collect-only (portfolio-service)" "docker compose exec -T portfolio-service pytest -q --collect-only | tail -n 50"
docker compose exec -T portfolio-service pytest -q --collect-only | tail -n 50
pass

# ============================================================================
# Step 11: pytest (container) - valuation-service
# ============================================================================
step "pytest (container): valuation-service" "docker compose exec -T valuation-service pytest -q"
docker compose exec -T valuation-service pytest -q
pass

# ============================================================================
# Step 12: pytest collect-only (valuation-service)
# ============================================================================
step "pytest collect-only (valuation-service)" "docker compose exec -T valuation-service pytest -q --collect-only | tail -n 50"
docker compose exec -T valuation-service pytest -q --collect-only | tail -n 50
pass

# ============================================================================
# Summary
# ============================================================================
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}All PR checks passed.${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Checks completed:"
echo "  1. Forbidden tokens scan (valuation-service)"
echo "  2. Forbidden tokens scan (portfolio-service accounting)"
echo "  3. docker compose config env allow-list (valuation-service)"
echo "  4. docker compose config env checks (portfolio-service)"
echo "  5. Services running check"
echo "  6. Runtime env sanity (valuation-service)"
echo "  7. Runtime guard injection test"
echo "  8. Valuation API JSON contract check"
echo "  9. pytest (portfolio-service)"
echo " 10. pytest collect-only (portfolio-service)"
echo " 11. pytest (valuation-service)"
echo " 12. pytest collect-only (valuation-service)"
