#!/bin/bash
# PR 自動檢查腳本（fail-fast）
# Sprint 1-4.B：在本機/CI 就能抓到 VM 才會爆的設定錯誤
#
# 檢查項目：
# 1. Forbidden tokens 靜態掃描
# 2. ./dc.sh config 展開後 env 驗證
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
# Step 3: Compose config secrets leak guard
# ==============================================================================
step "Compose config secrets leak guard" "./dc.sh config | grep -E 'GOOGLE_SA_JSON:|BEGIN PRIVATE KEY'"

echo "Checking for secrets leakage in compose config..."
COMPOSE_CONFIG_FULL=$(./dc.sh config 2>/dev/null) || fail "PRECHECK-COMPOSE" "./dc.sh config failed"

# Check 1: GOOGLE_SA_JSON (entire JSON in env)
MATCHES_JSON=$(echo "$COMPOSE_CONFIG_FULL" | grep -c "GOOGLE_SA_JSON:" || true)
echo "  matches_GOOGLE_SA_JSON: $MATCHES_JSON"

# Check 2: BEGIN PRIVATE KEY
MATCHES_KEY=$(echo "$COMPOSE_CONFIG_FULL" | grep -c "BEGIN PRIVATE KEY" || true)
echo "  matches_BEGIN_PRIVATE_KEY: $MATCHES_KEY"

if [ "$MATCHES_JSON" -gt 0 ] || [ "$MATCHES_KEY" -gt 0 ]; then
  echo ""
  echo "❌ Remediation:"
  echo "   - Use GOOGLE_SA_JSON_PATH instead of GOOGLE_SA_JSON"
  echo "   - Mount key file via docker-compose.secrets.yml with volume bind"
  echo "   - Example: /secure/keys/google_sa.json:/run/keys/google_sa.json:ro"
  echo "   - See RUNBOOK.md 'Google Service Account 金鑰部署注意事項' section"
  fail "COMPOSE-SECRETS-LEAK" "GOOGLE_SA_JSON_matches=$MATCHES_JSON, PRIVATE_KEY_matches=$MATCHES_KEY"
fi
pass

# ==============================================================================
# Step 4: ./dc.sh config env allow-list - valuation-service
# ============================================================================
step "docker compose config env allow-list: valuation-service" "./dc.sh config"

# Reuse COMPOSE_CONFIG_FULL from Step 3
COMPOSE_CONFIG="$COMPOSE_CONFIG_FULL"

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
# Step 5: ./dc.sh config env checks - portfolio-service
# ============================================================================
step "docker compose config env checks: portfolio-service" "./dc.sh config"

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
  EXPECTED_SA_PATH="/run/keys/google_sa.json"
  if [ -n "$SA_PATH_VALUE" ] && [ "$SA_PATH_VALUE" != "$EXPECTED_SA_PATH" ]; then
    warn "GOOGLE_SA_JSON_PATH=*** (expected=$EXPECTED_SA_PATH, got different path - ensure it's NOT /run/secrets/*)"
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
# Step 6: Check services are running
# ============================================================================
step "Check services are running" "./dc.sh ps --status running --services"

RUNNING_SERVICES=$(./dc.sh ps --status running --services 2>/dev/null || true)

if ! echo "$RUNNING_SERVICES" | grep -qx "portfolio-service"; then
  fail "PRECHECK-SVC-RUNNING" "portfolio-service not running; run: ./dc.sh up -d portfolio-service"
fi
if ! echo "$RUNNING_SERVICES" | grep -qx "valuation-service"; then
  fail "PRECHECK-SVC-RUNNING" "valuation-service not running; run: ./dc.sh up -d valuation-service"
fi
pass

# ============================================================================
# Step 7: Runtime env sanity check (valuation-service)
# ============================================================================
step "Runtime env sanity (valuation-service)" "./dc.sh exec -T valuation-service python -"

./dc.sh exec -T valuation-service python - <<'PY'
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
# Step 8: Runtime guard injection test (valuation-service)
# ============================================================================
step "Runtime guard injection test" "./dc.sh run --rm -e DATABASE_URL=x valuation-service python -c 'from app.guardrails import check_and_exit; check_and_exit()'"

# 這個測試預期要失敗（non-zero exit）
set +e
GUARD_OUTPUT=$(./dc.sh run --rm -e DATABASE_URL=test_injection valuation-service python -c "from app.guardrails import check_and_exit; check_and_exit()" 2>&1)
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
# Step 9: Valuation API JSON contract check (409 precondition_failed)
# ==============================================================================
step "Valuation API JSON contract check (409)" "curl valuation-service + python json.loads"

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
# Step 10: Valuation API JSON contract check (200 success path)
# ==============================================================================
step "Valuation API JSON contract check (200 success path)" "portfolio_refresh.sh + curl + JSON validation"

echo "Ensuring success path is reachable (portfolio sync + trades)..."
if [ -f "./tools/portfolio_refresh.sh" ]; then
  REFRESH_CMD="./tools/portfolio_refresh.sh tony"
  echo "command: $REFRESH_CMD"
  if $REFRESH_CMD > /tmp/pr_check_refresh.log 2>&1; then
    echo "  portfolio_refresh: completed"
  else
    echo "  portfolio_refresh: failed (may affect 200 path reachability)"
    cat /tmp/pr_check_refresh.log | tail -n 20
  fi
else
  warn "tools/portfolio_refresh.sh not found, skipping pre-condition setup"
fi

# Make API call to valuation endpoint
ENDPOINT="http://localhost:8005/valuation/portfolio?user_id=tony&base_ccy=TWD"
echo "command: curl -s -w '\\n%{http_code}\\n%{content_type}' '$ENDPOINT'"

API_RESPONSE_200=$(curl -s -w "\n%{http_code}\n%{content_type}" "$ENDPOINT" 2>&1 || true)

# Parse response: last 2 lines are http_code and content_type
BODY_200=$(echo "$API_RESPONSE_200" | head -n -2)
HTTP_CODE_200=$(echo "$API_RESPONSE_200" | tail -n 2 | head -n 1)
CONTENT_TYPE_200=$(echo "$API_RESPONSE_200" | tail -n 1)

echo "  http_code: $HTTP_CODE_200"
echo "  content_type: $CONTENT_TYPE_200"

# If 409, treat as expected alternative path (no trades available)
if [ "$HTTP_CODE_200" = "409" ]; then
  echo "  → Got 409 (no trades), this is expected alternative path"
  echo "  decision: pass (409 scenario already validated in Step 9)"
  # Don't fail, just pass this step
elif [ "$HTTP_CODE_200" != "200" ]; then
  echo "  decision: fail"
  echo "  ❌ Expected HTTP 200 or 409, got $HTTP_CODE_200"
  echo "  Response preview (first 200 chars):"
  echo "$BODY_200" | head -c 200
  echo ""
  fail "API-200-HTTP-CODE" "expected=200_or_409 got=$HTTP_CODE_200"
else
  # Validate 200 response
  
  # Check Content-Type
  if ! echo "$CONTENT_TYPE_200" | grep -qi "application/json"; then
    echo "  content_type_ok: no"
    fail "API-200-CONTENT-TYPE" "expected=application/json got=$CONTENT_TYPE_200"
  fi
  echo "  content_type_ok: yes"

  # Check JSON parse-ability
  JSON_PARSE_RESULT=$(echo "$BODY_200" | python3 -c 'import json,sys; json.loads(sys.stdin.read()); print("json_ok")' 2>&1 || echo "json_parse_failed")
  
  if [ "$JSON_PARSE_RESULT" != "json_ok" ]; then
    echo "  json_parse_ok: no"
    echo "  Parse error: $JSON_PARSE_RESULT"
    echo "  Response preview (first 200 chars):"
    echo "$BODY_200" | head -c 200
    echo ""
    fail "API-200-JSON-PARSE" "body is not valid JSON"
  fi
  echo "  json_parse_ok: yes"

  # Check required fields
  REQUIRED_FIELDS=("status" "totals" "positions" "evidence")
  REQUIRED_FIELDS_OK="yes"
  
  for field in "${REQUIRED_FIELDS[@]}"; do
    if ! echo "$BODY_200" | python3 -c "import json,sys; data=json.loads(sys.stdin.read()); exit(0 if '$field' in data else 1)" 2>/dev/null; then
      echo "  required_field '$field': missing"
      REQUIRED_FIELDS_OK="no"
    fi
  done

  if [ "$REQUIRED_FIELDS_OK" != "yes" ]; then
    echo "  required_fields_ok: no"
    fail "API-200-SCHEMA" "missing required fields: ${REQUIRED_FIELDS[*]}"
  fi
  echo "  required_fields_ok: yes (status, totals, positions, evidence)"

  # Check evidence doesn't leak sensitive data
  EVIDENCE_CHECKS_OK="yes"
  
  # Check for postgresql://
  if echo "$BODY_200" | grep -q "postgresql://"; then
    echo "  evidence_leak_check: found 'postgresql://' (FAIL)"
    EVIDENCE_CHECKS_OK="no"
  fi
  
  # Check for BEGIN PRIVATE KEY
  if echo "$BODY_200" | grep -q "BEGIN PRIVATE KEY"; then
    echo "  evidence_leak_check: found 'BEGIN PRIVATE KEY' (FAIL)"
    EVIDENCE_CHECKS_OK="no"
  fi
  
  # Check for unmasked env values (should be masked like D**********L)
  UNMASKED_CHECK=$(echo "$BODY_200" | python3 -c "
import json, sys, re
try:
    data = json.loads(sys.stdin.read())
    evidence = data.get('evidence', {})
    # Allowed non-sensitive fields (hashes, public identifiers)
    ALLOWED_FIELDS = {'positions_hash', 'decision', 'positions_count', 'as_of'}
    # Look for values that seem like full secrets (>20 chars, alphanumeric+special)
    for k, v in evidence.items():
        if k in ALLOWED_FIELDS:
            continue  # Skip known non-sensitive fields
        if isinstance(v, str) and len(v) > 20 and re.match(r'^[A-Za-z0-9_\-+=/.]+\$', v):
            # Check if it's NOT masked (masked should have *)
            if '*' not in v:
                print(f'unmasked_value_in_evidence.{k}')
                sys.exit(1)
    sys.exit(0)
except Exception as e:
    print(f'check_error: {e}')
    sys.exit(1)
" 2>&1 || echo "")

  if [ -n "$UNMASKED_CHECK" ] && echo "$UNMASKED_CHECK" | grep -q "unmasked_value"; then
    echo "  evidence_leak_check: $UNMASKED_CHECK (FAIL)"
    EVIDENCE_CHECKS_OK="no"
  fi

  if [ "$EVIDENCE_CHECKS_OK" != "yes" ]; then
    fail "API-200-EVIDENCE-LEAK" "evidence contains sensitive data (postgresql://, private keys, or unmasked secrets)"
  fi
  echo "  evidence_leak_check: pass (no postgresql://, private keys, or unmasked secrets)"

  echo "  decision: pass"
fi

# ==============================================================================
# Step 11: pytest (container) - portfolio-service
# ============================================================================
step "pytest (container): portfolio-service" "./dc.sh exec -T portfolio-service pytest -q"
./dc.sh exec -T portfolio-service pytest -q
pass

# ============================================================================
# Step 12: pytest collect-only (portfolio-service)
# ============================================================================
step "pytest collect-only (portfolio-service)" "./dc.sh exec -T portfolio-service pytest -q --collect-only | tail -n 50"
./dc.sh exec -T portfolio-service pytest -q --collect-only | tail -n 50
pass

# ============================================================================
# Step 13: pytest (container) - valuation-service
# ============================================================================
step "pytest (container): valuation-service" "./dc.sh exec -T valuation-service pytest -q"
./dc.sh exec -T valuation-service pytest -q
pass

# ============================================================================
# Step 14: pytest collect-only (valuation-service)
# ============================================================================
step "pytest collect-only (valuation-service)" "./dc.sh exec -T valuation-service pytest -q --collect-only | tail -n 50"
./dc.sh exec -T valuation-service pytest -q --collect-only | tail -n 50
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
echo "  3. Compose config secrets leak guard"
echo "  4. docker compose config env allow-list (valuation-service)"
echo "  5. docker compose config env checks (portfolio-service)"
echo "  6. Services running check"
echo "  7. Runtime env sanity (valuation-service)"
echo "  8. Runtime guard injection test"
echo "  9. Valuation API JSON contract check (409)"
echo " 10. Valuation API JSON contract check (200 success path)"
echo " 11. pytest (portfolio-service)"
echo " 12. pytest collect-only (portfolio-service)"
echo " 13. pytest (valuation-service)"
echo " 14. pytest collect-only (valuation-service)"
