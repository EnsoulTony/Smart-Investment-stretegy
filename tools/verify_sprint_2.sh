#!/usr/bin/env bash
# =============================================================================
# Sprint 2 Verification Script
# =============================================================================
# Validates:
# 1. indicator-service: GET /indicators/sector-rotation returns 200 with required fields
# 2. radar-service: GET /radar/decision returns OutputSchema with evidence.inputs_hash
# 3. pytest passes for both services in containers
#
# Usage:
#   ./tools/verify_sprint_2.sh
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=============================================="
echo "Sprint 2 Verification Script"
echo "=============================================="
echo ""

# Step 1: Build and start services
echo -e "${YELLOW}[1/6] Building and starting services...${NC}"
./dc.sh up -d --build

# Step 2: Wait for services to be ready
echo -e "${YELLOW}[2/6] Waiting for services to be ready...${NC}"

wait_for_service() {
    local service_name=$1
    local url=$2
    local max_attempts=30
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        if curl -s "$url" > /dev/null 2>&1; then
            echo -e "  ${GREEN}✓${NC} $service_name is ready"
            return 0
        fi
        echo "  Waiting for $service_name... (attempt $attempt/$max_attempts)"
        sleep 2
        attempt=$((attempt + 1))
    done

    echo -e "  ${RED}✗${NC} $service_name failed to start"
    return 1
}

wait_for_service "indicator-service" "http://localhost:8006/health"
wait_for_service "radar-service" "http://localhost:8002/health"
wait_for_service "portfolio-service" "http://localhost:8001/health"

echo ""

# Step 3: Test indicator-service endpoint
echo -e "${YELLOW}[3/6] Testing indicator-service endpoint...${NC}"

INDICATOR_RESPONSE=$(curl -s -w "\n%{http_code}" "http://localhost:8006/indicators/sector-rotation?symbols=XLU,XLK")
INDICATOR_BODY=$(echo "$INDICATOR_RESPONSE" | head -n -1)
INDICATOR_STATUS=$(echo "$INDICATOR_RESPONSE" | tail -n 1)

if [ "$INDICATOR_STATUS" != "200" ]; then
    echo -e "  ${RED}✗${NC} indicator-service returned HTTP $INDICATOR_STATUS (expected 200)"
    echo "  Response: $INDICATOR_BODY"
    exit 1
fi

# Check content-type
INDICATOR_CT=$(curl -s -I "http://localhost:8006/indicators/sector-rotation?symbols=XLU,XLK" | grep -i "content-type" | tr -d '\r')
if [[ ! "$INDICATOR_CT" =~ "application/json" ]]; then
    echo -e "  ${RED}✗${NC} indicator-service content-type is not application/json"
    exit 1
fi
echo -e "  ${GREEN}✓${NC} Content-Type: application/json"

# Check required fields
REQUIRED_FIELDS=("as_of" "version" "source" "XLU" "XLK" "ratio")
for field in "${REQUIRED_FIELDS[@]}"; do
    if ! echo "$INDICATOR_BODY" | jq -e ".$field" > /dev/null 2>&1; then
        echo -e "  ${RED}✗${NC} Missing required field: $field"
        exit 1
    fi
done
echo -e "  ${GREEN}✓${NC} All required top-level fields present"

# Check XLU/XLK have close, ma20, ma50
for symbol in XLU XLK; do
    for subfield in close ma20 ma50; do
        if ! echo "$INDICATOR_BODY" | jq -e ".$symbol.$subfield" > /dev/null 2>&1; then
            echo -e "  ${RED}✗${NC} Missing $symbol.$subfield"
            exit 1
        fi
    done
done
echo -e "  ${GREEN}✓${NC} XLU and XLK have close, ma20, ma50"

# Check ratio has required fields including slope5
for subfield in pair value ma20 ma50 slope5; do
    if ! echo "$INDICATOR_BODY" | jq -e ".ratio.$subfield" > /dev/null 2>&1; then
        echo -e "  ${RED}✗${NC} Missing ratio.$subfield"
        exit 1
    fi
done
echo -e "  ${GREEN}✓${NC} ratio has pair, value, ma20, ma50, slope5"

echo -e "  ${GREEN}✓${NC} indicator-service endpoint OK"
echo ""

# Step 4: Test radar-service decision endpoint
echo -e "${YELLOW}[4/6] Testing radar-service decision endpoint...${NC}"

RADAR_RESPONSE=$(curl -s -w "\n%{http_code}" "http://localhost:8002/radar/decision?user_id=tony&base_ccy=TWD")
RADAR_BODY=$(echo "$RADAR_RESPONSE" | head -n -1)
RADAR_STATUS=$(echo "$RADAR_RESPONSE" | tail -n 1)

if [ "$RADAR_STATUS" != "200" ]; then
    echo -e "  ${RED}✗${NC} radar-service returned HTTP $RADAR_STATUS (expected 200)"
    echo "  Response: $RADAR_BODY"
    exit 1
fi
echo -e "  ${GREEN}✓${NC} HTTP 200 OK"

# Check OutputSchema required fields
OUTPUT_FIELDS=("schema_version" "as_of" "user_id" "mode" "decision" "actions" "evidence")
for field in "${OUTPUT_FIELDS[@]}"; do
    if ! echo "$RADAR_BODY" | jq -e ".$field" > /dev/null 2>&1; then
        echo -e "  ${RED}✗${NC} Missing required field: $field"
        exit 1
    fi
done
echo -e "  ${GREEN}✓${NC} All OutputSchema fields present"

# Check evidence.inputs_hash exists and is 64 chars (SHA256)
INPUTS_HASH=$(echo "$RADAR_BODY" | jq -r ".evidence.inputs_hash")
if [ -z "$INPUTS_HASH" ] || [ "$INPUTS_HASH" == "null" ]; then
    echo -e "  ${RED}✗${NC} Missing evidence.inputs_hash"
    exit 1
fi
HASH_LEN=${#INPUTS_HASH}
if [ "$HASH_LEN" != "64" ]; then
    echo -e "  ${RED}✗${NC} evidence.inputs_hash length is $HASH_LEN (expected 64)"
    exit 1
fi
echo -e "  ${GREEN}✓${NC} evidence.inputs_hash present (SHA256: ${INPUTS_HASH:0:16}...)"

# Check mode is valid
MODE=$(echo "$RADAR_BODY" | jq -r ".mode")
if [[ ! "$MODE" =~ ^(RISK_ON|RISK_OFF|TRANSITION)$ ]]; then
    echo -e "  ${RED}✗${NC} Invalid mode: $MODE"
    exit 1
fi
echo -e "  ${GREEN}✓${NC} mode=$MODE"

# Check decision is valid
DECISION=$(echo "$RADAR_BODY" | jq -r ".decision")
if [[ ! "$DECISION" =~ ^(NO_ACTION|REDUCE_RISK|REBALANCE|WATCHLIST)$ ]]; then
    echo -e "  ${RED}✗${NC} Invalid decision: $DECISION"
    exit 1
fi
echo -e "  ${GREEN}✓${NC} decision=$DECISION"

# Check that actions have falsifiable_triggers (if actions exist)
ACTIONS_COUNT=$(echo "$RADAR_BODY" | jq ".actions | length")
if [ "$ACTIONS_COUNT" -gt 0 ]; then
    FIRST_ACTION_TRIGGERS=$(echo "$RADAR_BODY" | jq ".actions[0].falsifiable_triggers | length")
    if [ "$FIRST_ACTION_TRIGGERS" -lt 1 ]; then
        echo -e "  ${RED}✗${NC} First action has no falsifiable_triggers"
        exit 1
    fi
    echo -e "  ${GREEN}✓${NC} Actions have falsifiable_triggers ($ACTIONS_COUNT actions)"
else
    echo -e "  ${YELLOW}!${NC} No actions in response (empty positions case)"
fi

# Check cooldown_days = 5 for all actions
if [ "$ACTIONS_COUNT" -gt 0 ]; then
    COOLDOWNS=$(echo "$RADAR_BODY" | jq "[.actions[].constraints.cooldown_days] | unique")
    if [ "$COOLDOWNS" != "[5]" ] && [ "$COOLDOWNS" != "[]" ]; then
        echo -e "  ${RED}✗${NC} Not all actions have cooldown_days=5: $COOLDOWNS"
        exit 1
    fi
    echo -e "  ${GREEN}✓${NC} All actions have cooldown_days=5"
fi

echo -e "  ${GREEN}✓${NC} radar-service decision endpoint OK"
echo ""

# Step 5: Run pytest in indicator-service container
echo -e "${YELLOW}[5/6] Running pytest in indicator-service container...${NC}"

if ! ./dc.sh exec -T indicator-service pytest -q; then
    echo -e "  ${RED}✗${NC} indicator-service pytest FAILED"
    exit 1
fi
echo -e "  ${GREEN}✓${NC} indicator-service pytest PASSED"
echo ""

# Step 6: Run pytest in radar-service container
echo -e "${YELLOW}[6/6] Running pytest in radar-service container...${NC}"

if ! ./dc.sh exec -T radar-service pytest -q; then
    echo -e "  ${RED}✗${NC} radar-service pytest FAILED"
    exit 1
fi
echo -e "  ${GREEN}✓${NC} radar-service pytest PASSED"
echo ""

# Final result
echo "=============================================="
echo -e "${GREEN}✅ Sprint 2 PASSED${NC}"
echo "=============================================="
echo ""
echo "Summary:"
echo "  - indicator-service: GET /indicators/sector-rotation ✓"
echo "  - radar-service: GET /radar/decision ✓"
echo "  - evidence.inputs_hash: present (SHA256)"
echo "  - falsifiable_triggers: present"
echo "  - cooldown_days: 5"
echo "  - pytest (indicator-service): PASSED"
echo "  - pytest (radar-service): PASSED"
echo ""
