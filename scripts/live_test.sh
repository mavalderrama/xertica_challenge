#!/usr/bin/env bash
# =============================================================================
# live_test.sh — Compliance AI API live test walkthrough
#
# Prerequisites:
#   1. docker compose up           (DB + Langfuse + API running)
#   2. make migrate                (migrations applied)
#   3. make seed                   (synthetic alerts created)
#   4. make index-regulations      (regulatory docs indexed for RAG)
#
# Usage:
#   bash scripts/live_test.sh [SCENARIO] [BASE_URL]
#
# Arguments:
#   SCENARIO   One of: low-risk | high-risk | pep-small | pep-large |
#                      mid-risk | multi-ccy | corp | safe | all
#              Default: all
#   BASE_URL   API base URL. Default: http://localhost:8000
#
# Examples:
#   bash scripts/live_test.sh                    # runs all scenarios
#   bash scripts/live_test.sh pep-small          # tests PEP hard-rule
#   bash scripts/live_test.sh high-risk          # tests escalation path
#   bash scripts/live_test.sh all http://localhost:8001
# =============================================================================

set -euo pipefail

SCENARIO="${1:-all}"
BASE_URL="${2:-http://localhost:8000}"
API="${BASE_URL}/api/v1/alerts"

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ── Helpers ───────────────────────────────────────────────────────────────────
header() { echo -e "\n${BOLD}${BLUE}═══════════════════════════════════════════${NC}"; echo -e "${BOLD}${BLUE}  $1${NC}"; echo -e "${BOLD}${BLUE}═══════════════════════════════════════════${NC}"; }
step()   { echo -e "\n${CYAN}── $1${NC}"; }
ok()     { echo -e "${GREEN}✓ $1${NC}"; }
warn()   { echo -e "${YELLOW}⚠ $1${NC}"; }
fail()   { echo -e "${RED}✗ $1${NC}"; }
info()   { echo -e "  $1"; }

# Resolve an external_alert_id to its DB UUID by querying the API health
# The seed_data command prints UUIDs — we look them up via the status endpoint
# by scanning through the seeded external IDs against known UUIDs.
# In practice, run `make seed` first and copy the UUIDs it prints.
#
# For this script we look up IDs from the database via Django shell.
resolve_uuid() {
    local ext_id="$1"
    cd "$(dirname "$0")/../backend" 2>/dev/null || true
    uv run python manage.py shell \
        --settings=config.settings.local \
        -c "from compliance_agent.models import Alert; a=Alert.objects.filter(external_alert_id='${ext_id}').first(); print(a.id if a else 'NOT_FOUND')" \
        2>/dev/null | tail -1
}

check_api_health() {
    step "Checking API health"
    local response
    response=$(curl -s --max-time 5 "${BASE_URL}/health" 2>/dev/null || echo "")
    if echo "$response" | grep -q '"ok"'; then
        ok "API is healthy: $response"
    else
        fail "API not responding at ${BASE_URL}/health"
        echo "  Make sure: docker compose up && make migrate && make seed && make index-regulations"
        exit 1
    fi

    step "Checking readiness (DB connection)"
    local ready
    ready=$(curl -s --max-time 5 "${BASE_URL}/readiness" 2>/dev/null || echo "")
    if echo "$ready" | grep -q '"ready"'; then
        ok "DB connected: $ready"
    else
        warn "Readiness check failed: $ready"
    fi
}

run_investigation() {
    local label="$1"
    local ext_id="$2"
    local expected_decision="$3"
    local description="$4"

    header "SCENARIO: ${label}"
    info "External ID : ${ext_id}"
    info "Expected    : ${expected_decision}"
    info "Description : ${description}"

    step "Resolving UUID from external_alert_id"
    local uuid
    uuid=$(resolve_uuid "$ext_id")

    if [[ "$uuid" == "NOT_FOUND" || -z "$uuid" ]]; then
        fail "Alert '${ext_id}' not found in database. Run: make seed"
        return 1
    fi
    info "UUID: ${uuid}"

    step "GET /api/v1/alerts/${uuid}/status (before investigation)"
    local status_before
    status_before=$(curl -s --max-time 10 "${API}/${uuid}/status")
    echo "$status_before" | python3 -m json.tool 2>/dev/null || echo "$status_before"
    local current_status
    current_status=$(echo "$status_before" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','?'))" 2>/dev/null || echo "?")
    info "Current status: ${current_status}"

    if [[ "$current_status" != "PENDING" ]]; then
        warn "Alert is not PENDING (status=${current_status}). It may have been investigated already."
        warn "Run 'make seed --clear' to reset, then 'make seed' again."
    fi

    step "POST /api/v1/alerts/${uuid}/investigate  (running 3-agent pipeline...)"
    echo "  This may take 5-30 seconds depending on LLM response time."
    local start_time
    start_time=$(date +%s)

    local response
    response=$(curl -s --max-time 120 -X POST \
        -H "Content-Type: application/json" \
        -d '{}' \
        "${API}/${uuid}/investigate")

    local elapsed=$(( $(date +%s) - start_time ))

    if echo "$response" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
        echo ""
        echo "$response" | python3 -m json.tool
    else
        fail "Invalid JSON response:"
        echo "$response"
        return 1
    fi

    local decision_type
    decision_type=$(echo "$response" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','?'))" 2>/dev/null || echo "?")

    local risk_score
    risk_score=$(echo "$response" | python3 -c "import sys,json; d=json.load(sys.stdin); ra=d.get('risk_analysis') or {}; print(ra.get('risk_score','?'))" 2>/dev/null || echo "?")

    local confidence
    confidence=$(echo "$response" | python3 -c "import sys,json; d=json.load(sys.stdin); dec=d.get('decision') or {}; print(dec.get('confidence','?'))" 2>/dev/null || echo "?")

    local pep_override
    pep_override=$(echo "$response" | python3 -c "import sys,json; d=json.load(sys.stdin); dec=d.get('decision') or {}; print(dec.get('is_pep_override_applied',False))" 2>/dev/null || echo "?")

    echo ""
    echo -e "${BOLD}── Summary ──────────────────────────────────${NC}"
    info "Decision    : ${decision_type}"
    info "Risk score  : ${risk_score}/10"
    info "Confidence  : ${confidence}"
    info "PEP override: ${pep_override}"
    info "Elapsed     : ${elapsed}s"

    if [[ "$decision_type" == "$expected_decision" ]]; then
        ok "Decision matches expected: ${expected_decision}"
    else
        warn "Decision '${decision_type}' differs from expected '${expected_decision}'"
        warn "(LLM decisions are non-deterministic — this may be acceptable)"
    fi

    step "GET /api/v1/alerts/${uuid}/status (after investigation)"
    curl -s --max-time 10 "${API}/${uuid}/status" | python3 -m json.tool

    step "GET /api/v1/alerts/${uuid}/audit-trail"
    local audit
    audit=$(curl -s --max-time 10 "${API}/${uuid}/audit-trail")
    echo "$audit" | python3 -m json.tool

    local total_cost
    total_cost=$(echo "$audit" | python3 -c "
import sys, json
d = json.load(sys.stdin)
events = d.get('events', [])
total = sum(float(e.get('token_cost_usd', 0)) for e in events)
total_ms = sum(int(e.get('duration_ms', 0)) for e in events)
print(f'Total LLM cost: \${total:.6f} | Total agent time: {total_ms}ms')
" 2>/dev/null || echo "")
    info "$total_cost"
}

# ── Scenario definitions ───────────────────────────────────────────────────────
scenario_low_risk() {
    run_investigation \
        "1. Low-Risk Dismissal" \
        "LIVE-LOW-RISK-001" \
        "DISMISS" \
        "COP 3.5M, xgb=0.31, retail customer. Should be dismissed — below threshold, clean profile."
}

scenario_high_risk() {
    run_investigation \
        "2. High-Risk Escalation" \
        "LIVE-HIGH-RISK-002" \
        "ESCALATE" \
        "USD 85,000, xgb=0.89, SME. Single large transfer. Should trigger ESCALATE."
}

scenario_pep_small() {
    run_investigation \
        "3. PEP — Small Amount (hard-rule)" \
        "LIVE-PEP-SMALL-003" \
        "ESCALATE" \
        "MXN 12,000, xgb=0.45, is_pep=True. PEP hard-rule: no LLM call, instant ESCALATE."
}

scenario_pep_large() {
    run_investigation \
        "4. PEP — Large Amount (hard-rule)" \
        "LIVE-PEP-LARGE-004" \
        "ESCALATE" \
        "USD 750,000, xgb=0.92, is_pep=True, foreign official. PEP hard-rule applies."
}

scenario_mid_risk() {
    run_investigation \
        "5. Mid-Risk — Request Info" \
        "LIVE-MID-RISK-005" \
        "REQUEST_INFO" \
        "PEN 18,500, xgb=0.61, changed profession. Ambiguous — expect REQUEST_INFO."
}

scenario_multi_ccy() {
    run_investigation \
        "6. Multi-Currency Suspicious Activity" \
        "LIVE-MULTI-CCY-006" \
        "ESCALATE" \
        "USD 45,000, xgb=0.77, 4 currencies in 90 days. Layering indicators."
}

scenario_corp() {
    run_investigation \
        "7. Corporate — High COP Amount" \
        "LIVE-CORP-007" \
        "ESCALATE" \
        "COP 48M (above 10M UIAF threshold), xgb=0.83, corporate. Strong UIAF Circular 002 match."
}

scenario_safe() {
    run_investigation \
        "8. Safe Retail Customer" \
        "LIVE-SAFE-008" \
        "DISMISS" \
        "MXN 8,500, xgb=0.22, retail. Velocity trigger only, amount below threshold."
}

# ── Main ──────────────────────────────────────────────────────────────────────
echo -e "${BOLD}${BLUE}"
echo "  ╔═══════════════════════════════════════════╗"
echo "  ║   Compliance AI — Live Test Suite         ║"
echo "  ║   ${BASE_URL}   ║"
echo "  ╚═══════════════════════════════════════════╝"
echo -e "${NC}"

check_api_health

case "$SCENARIO" in
    low-risk)    scenario_low_risk ;;
    high-risk)   scenario_high_risk ;;
    pep-small)   scenario_pep_small ;;
    pep-large)   scenario_pep_large ;;
    mid-risk)    scenario_mid_risk ;;
    multi-ccy)   scenario_multi_ccy ;;
    corp)        scenario_corp ;;
    safe)        scenario_safe ;;
    all)
        scenario_low_risk
        scenario_high_risk
        scenario_pep_small
        scenario_pep_large
        scenario_mid_risk
        scenario_multi_ccy
        scenario_corp
        scenario_safe
        ;;
    *)
        fail "Unknown scenario: ${SCENARIO}"
        echo "  Valid scenarios: low-risk | high-risk | pep-small | pep-large | mid-risk | multi-ccy | corp | safe | all"
        exit 1
        ;;
esac

echo ""
echo -e "${BOLD}${GREEN}═══════════════════════════════════════════${NC}"
echo -e "${BOLD}${GREEN}  All tests complete.${NC}"
echo -e "${BOLD}${GREEN}  Langfuse traces: http://localhost:3001${NC}"
echo -e "${BOLD}${GREEN}  Swagger UI:      ${BASE_URL}/docs${NC}"
echo -e "${BOLD}${GREEN}═══════════════════════════════════════════${NC}"
