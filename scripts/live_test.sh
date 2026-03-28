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
#   bash scripts/live_test.sh [SCENARIO] [BASE_URL] [--judge|--no-judge]
#
# Arguments:
#   SCENARIO     One of: low-risk | high-risk | pep-small | pep-large |
#                        mid-risk | multi-ccy | corp | safe | all  (default: all)
#   BASE_URL     API base URL. Default: http://localhost:8000
#   --judge      Force-run the LLM judge after scenarios complete
#   --no-judge   Skip the LLM judge (useful when running a single scenario)
#
# LLM judge runs automatically when SCENARIO=all (override with --no-judge).
# =============================================================================

set -euo pipefail

# ── Argument parsing ───────────────────────────────────────────────────────────
SCENARIO="${1:-all}"
BASE_URL="${2:-http://localhost:8000}"
RUN_JUDGE="auto"   # auto | true | false
for _arg in "${@:3}"; do
    case "$_arg" in
        --judge)    RUN_JUDGE="true"  ;;
        --no-judge) RUN_JUDGE="false" ;;
    esac
done

API="${BASE_URL}/api/v1/alerts"
SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPTS_DIR}/../backend" && pwd)"

# ── Colours ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ── Result accumulators ────────────────────────────────────────────────────────
RESULTS_FILE=$(mktemp /tmp/compliance_live_XXXXXX.json)
echo '[]' > "$RESULTS_FILE"
SCENARIO_COUNT=0
PASS_COUNT=0
FAIL_COUNT=0

cleanup() { rm -f "$RESULTS_FILE"; }
trap cleanup EXIT

# ── Helpers ────────────────────────────────────────────────────────────────────
step() { echo -e "\n${CYAN}── $1${NC}"; }
ok()   { echo -e "${GREEN}✓ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠ $1${NC}"; }
fail() { echo -e "${RED}✗ $1${NC}"; }

# Resolve an external_alert_id to its DB UUID
resolve_uuid() {
    local ext_id="$1"
    cd "$BACKEND_DIR"
    uv run python manage.py shell \
        --settings=config.settings.local \
        -c "from compliance_agent.models import Alert; \
a=Alert.objects.filter(external_alert_id='${ext_id}').first(); \
print(a.id if a else 'NOT_FOUND')" \
        2>/dev/null | tail -1
}

# Fetch investigation structured_context + alert fields from the DB
fetch_investigation_context() {
    local uuid="$1"
    cd "$BACKEND_DIR"
    uv run python manage.py shell \
        --settings=config.settings.local \
        -c "
import json
from compliance_agent.models import Alert
a = Alert.objects.select_related('investigation').filter(id='${uuid}').first()
if a:
    ctx = {}
    try:
        ctx = dict(a.investigation.structured_context)
    except Exception:
        pass
    ctx['current_alert_amount']   = float(a.amount)
    ctx['current_alert_currency'] = a.currency
    ctx['is_pep']                 = a.is_pep
    ctx['xgboost_score']          = a.xgboost_score
    ctx['segment']                = (a.raw_payload or {}).get('segment', '')
    print(json.dumps(ctx))
else:
    print('{}')
" 2>/dev/null | tail -1
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
        ok "DB connected"
    else
        warn "Readiness check failed: $ready"
    fi
}

# ── Core investigation runner ──────────────────────────────────────────────────
run_investigation() {
    local label="$1"
    local ext_id="$2"
    local expected_decision="$3"
    # $4 = description (unused now — shown in the visual diagram)
    local scenario_num="$5"

    SCENARIO_COUNT=$((SCENARIO_COUNT + 1))

    # ── Resolve UUID ────────────────────────────────────────────────────────
    local uuid
    uuid=$(resolve_uuid "$ext_id")
    if [[ "$uuid" == "NOT_FOUND" || -z "$uuid" ]]; then
        fail "Alert '${ext_id}' not found. Run: make seed"
        return 1
    fi

    # ── Pre-investigation status ─────────────────────────────────────────────
    local current_status
    current_status=$(curl -s --max-time 10 "${API}/${uuid}/status" \
        | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','?'))" \
        2>/dev/null || echo "?")
    if [[ "$current_status" != "PENDING" ]]; then
        warn "Alert ${ext_id} is already '${current_status}'. Run: make seed-clear && make seed"
    fi

    # ── Run pipeline (POST /investigate) ────────────────────────────────────
    local start_time elapsed response
    start_time=$(python3 -c "import time; print(time.time())")

    response=$(curl -s --max-time 120 \
        -X POST -H "Content-Type: application/json" -d '{}' \
        "${API}/${uuid}/investigate")

    elapsed=$(python3 -c "import time; print(round(time.time() - ${start_time}, 2))")

    if ! echo "$response" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
        fail "Invalid JSON from /investigate for ${ext_id}:"
        echo "$response"
        return 1
    fi

    # ── Audit trail ──────────────────────────────────────────────────────────
    local audit
    audit=$(curl -s --max-time 10 "${API}/${uuid}/audit-trail")
    if ! echo "$audit" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
        warn "Invalid JSON from /audit-trail for ${ext_id} — using empty audit. Raw: ${audit}"
        audit='{"alert_id":"'${uuid}'","events":[]}'
    fi

    # ── Investigation context from DB ────────────────────────────────────────
    local context
    context=$(fetch_investigation_context "$uuid")
    [[ -z "$context" ]] && context="{}"

    # ── Render visual workflow + accumulate result ───────────────────────────
    local match_exit=0
    python3 "${SCRIPTS_DIR}/live_test_render.py" \
        --response     "$response" \
        --audit        "$audit" \
        --context      "$context" \
        --ext-id       "$ext_id" \
        --expected     "$expected_decision" \
        --elapsed      "$elapsed" \
        --scenario-num "$scenario_num" \
        --label        "$label" \
        --results-file "$RESULTS_FILE" \
        || match_exit=$?

    if [[ $match_exit -eq 0 ]]; then
        PASS_COUNT=$((PASS_COUNT + 1))
    else
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
}

# ── Scenario definitions ───────────────────────────────────────────────────────
scenario_low_risk()  {
    run_investigation "Low-Risk Dismissal"        "LIVE-LOW-RISK-001"  "DISMISS"       "" 1
}
scenario_high_risk() {
    run_investigation "High-Risk Escalation"      "LIVE-HIGH-RISK-002" "ESCALATE"      "" 2
}
scenario_pep_small() {
    run_investigation "PEP — Small Amount"        "LIVE-PEP-SMALL-003" "ESCALATE"      "" 3
}
scenario_pep_large() {
    run_investigation "PEP — Large Amount"        "LIVE-PEP-LARGE-004" "ESCALATE"      "" 4
}
scenario_mid_risk()  {
    run_investigation "Mid-Risk Request Info"     "LIVE-MID-RISK-005"  "REQUEST_INFO"  "" 5
}
scenario_multi_ccy() {
    run_investigation "Multi-Currency Activity"   "LIVE-MULTI-CCY-006" "ESCALATE"      "" 6
}
scenario_corp()      {
    run_investigation "Corporate High COP Amount" "LIVE-CORP-007"      "ESCALATE"      "" 7
}
scenario_safe()      {
    run_investigation "Safe Retail Customer"      "LIVE-SAFE-008"      "DISMISS"       "" 8
}

# ── Main ───────────────────────────────────────────────────────────────────────
echo -e "${BOLD}${BLUE}"
echo "  ╔═══════════════════════════════════════════╗"
echo "  ║   Compliance AI — Live Test Suite         ║"
echo "  ║   ${BASE_URL}   ║"
echo "  ╚═══════════════════════════════════════════╝"
echo -e "${NC}"

check_api_health

case "$SCENARIO" in
    low-risk)  scenario_low_risk  ;;
    high-risk) scenario_high_risk ;;
    pep-small) scenario_pep_small ;;
    pep-large) scenario_pep_large ;;
    mid-risk)  scenario_mid_risk  ;;
    multi-ccy) scenario_multi_ccy ;;
    corp)      scenario_corp      ;;
    safe)      scenario_safe      ;;
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

# ── Summary ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${BLUE}═══════════════════════════════════════════${NC}"
if [[ $SCENARIO_COUNT -gt 0 ]]; then
    echo -e "${BOLD}  Results: ${PASS_COUNT}/${SCENARIO_COUNT} decisions matched expected${NC}"
fi
echo -e "${GREEN}  Langfuse traces: http://localhost:3001${NC}"
echo -e "${GREEN}  Swagger UI:      ${BASE_URL}/docs${NC}"
echo -e "${BOLD}${BLUE}═══════════════════════════════════════════${NC}"

# ── LLM Judge ─────────────────────────────────────────────────────────────────
_should_judge=false
if   [[ "$RUN_JUDGE" == "true" ]]; then
    _should_judge=true
elif [[ "$RUN_JUDGE" == "auto" && "$SCENARIO" == "all" && $SCENARIO_COUNT -gt 0 ]]; then
    _should_judge=true
fi

if [[ "$_should_judge" == "true" ]]; then
    cd "$BACKEND_DIR"
    uv run python "${SCRIPTS_DIR}/llm_judge.py" "$RESULTS_FILE" \
        || warn "LLM judge evaluation failed (check OPENAI_API_KEY in backend/.env)"
fi
