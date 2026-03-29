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
#   bash scripts/live_test.sh [OPTIONS] [SCENARIO] [BASE_URL]
#
# Options:
#   -s NUM       Run only scenario number NUM (1-30)
#   -l NUM       Run the first NUM scenarios (1-30)
#   --judge      Force-run the LLM judge after scenarios complete
#   --no-judge   Skip the LLM judge (useful when running a single scenario)
#
# Arguments:
#   SCENARIO     One of: low-risk | high-risk | pep-small | pep-large |
#                        mid-risk | multi-ccy | corp | safe | ghost-probe |
#                        pep-phantom | all  (default: all)
#   BASE_URL     API base URL. Default: http://localhost:8000
#
# LLM judge runs automatically when SCENARIO=all (override with --no-judge).
# Edge case scenarios:
#   ghost-probe   — xgboost=0.97 on $75 USD (critical ML signal vs trivial amount)
#   pep-phantom   — PEP=True on EUR 0.01 xgb=0.02 (hard-rule against all signals)
# =============================================================================

set -euo pipefail

# ── Argument parsing ───────────────────────────────────────────────────────────
SCENARIO="all"
BASE_URL="http://localhost:8000"
RUN_JUDGE="auto"   # auto | true | false
SCENARIO_NUM=""    # -s NUM: run only this scenario number
LIMIT=""           # -l NUM: run only the first N scenarios

while [[ $# -gt 0 ]]; do
    case "$1" in
        -s) SCENARIO_NUM="$2"; shift 2 ;;
        -l) LIMIT="$2"; shift 2 ;;
        --judge)    RUN_JUDGE="true";  shift ;;
        --no-judge) RUN_JUDGE="false"; shift ;;
        http://*|https://*)  BASE_URL="$1"; shift ;;
        *)  SCENARIO="$1"; shift ;;
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

# ── Scenario table: (num, name, ext_id, expected_decision) ────────────────────
# Used for both named-scenario dispatch and numeric -s / -l selection.
declare -a SCENARIO_NAMES=(
    ""                    # 0-indexed padding; scenarios start at 1
    "low-risk"            # 1
    "high-risk"           # 2
    "pep-small"           # 3
    "pep-large"           # 4
    "mid-risk"            # 5
    "multi-ccy"           # 6
    "corp"                # 7
    "safe"                # 8
    "struct"              # 9
    "new-acct"            # 10
    "micro"               # 11
    "pep-corp"            # 12
    "high-pen"            # 13
    "safe-pen"            # 14
    "under-thresh"        # 15
    "intl-wire"           # 16
    "sme-low"             # 17
    "id-change"           # 18
    "large-mxn"           # 19
    "remittance"          # 20
    "odd-timing"          # 21
    "large-usd"           # 22
    "pep-pen"             # 23
    "below-cop"           # 24
    "corp-med"            # 25
    "mule"                # 26
    "tiny-cop"            # 27
    "income-gap"          # 28
    "ghost-probe"         # 29
    "pep-phantom"         # 30
)
TOTAL_SCENARIOS=30

run_scenario_by_num() {
    local n="$1"
    case "$n" in
        1)  run_investigation "Low-Risk Dismissal"        "LIVE-LOW-RISK-001"     "DISMISS"      "" "$n" ;;
        2)  run_investigation "High-Risk Escalation"      "LIVE-HIGH-RISK-002"    "ESCALATE"     "" "$n" ;;
        3)  run_investigation "PEP — Small Amount"        "LIVE-PEP-SMALL-003"    "ESCALATE"     "" "$n" ;;
        4)  run_investigation "PEP — Large Amount"        "LIVE-PEP-LARGE-004"    "ESCALATE"     "" "$n" ;;
        5)  run_investigation "Mid-Risk Request Info"     "LIVE-MID-RISK-005"     "REQUEST_INFO" "" "$n" ;;
        6)  run_investigation "Multi-Currency Activity"   "LIVE-MULTI-CCY-006"    "ESCALATE"     "" "$n" ;;
        7)  run_investigation "Corporate High COP Amount" "LIVE-CORP-007"         "ESCALATE"     "" "$n" ;;
        8)  run_investigation "Safe Retail Customer"      "LIVE-SAFE-008"         "DISMISS"      "" "$n" ;;
        9)  run_investigation "COP Structuring Pattern"   "LIVE-STRUCT-009"       "ESCALATE"     "" "$n" ;;
        10) run_investigation "New Account Large USD"     "LIVE-NEW-ACCT-010"     "REQUEST_INFO" "" "$n" ;;
        11) run_investigation "Micro-Transaction USD"     "LIVE-MICRO-011"        "DISMISS"      "" "$n" ;;
        12) run_investigation "PEP Corporate High USD"    "LIVE-PEP-CORP-012"     "ESCALATE"     "" "$n" ;;
        13) run_investigation "High PEN Above Threshold"  "LIVE-HIGH-PEN-013"     "ESCALATE"     "" "$n" ;;
        14) run_investigation "Safe PEN Retail"           "LIVE-SAFE-PEN-014"     "DISMISS"      "" "$n" ;;
        15) run_investigation "USD Structuring CNBV"      "LIVE-UNDER-THRESH-015" "ESCALATE"     "" "$n" ;;
        16) run_investigation "FATF High-Risk Wire"       "LIVE-INTL-WIRE-016"    "ESCALATE"     "" "$n" ;;
        17) run_investigation "SME Low-Risk MXN"          "LIVE-SME-LOW-017"      "DISMISS"      "" "$n" ;;
        18) run_investigation "Identity Change PEN"       "LIVE-ID-CHANGE-018"    "REQUEST_INFO" "" "$n" ;;
        19) run_investigation "Large MXN Wire"            "LIVE-LARGE-MXN-019"    "ESCALATE"     "" "$n" ;;
        20) run_investigation "Family Remittance USD"     "LIVE-REMITTANCE-020"   "DISMISS"      "" "$n" ;;
        21) run_investigation "Unusual-Hour PEN"          "LIVE-ODD-TIMING-021"   "REQUEST_INFO" "" "$n" ;;
        22) run_investigation "Large USD SME Wire"        "LIVE-LARGE-USD-022"    "ESCALATE"     "" "$n" ;;
        23) run_investigation "PEP Small PEN"             "LIVE-PEP-PEN-023"      "ESCALATE"     "" "$n" ;;
        24) run_investigation "Below-Threshold COP"       "LIVE-BELOW-COP-024"    "DISMISS"      "" "$n" ;;
        25) run_investigation "Corporate MXN Unusual"     "LIVE-CORP-MED-025"     "REQUEST_INFO" "" "$n" ;;
        26) run_investigation "Money-Mule Pass-Through"   "LIVE-MULE-026"         "ESCALATE"     "" "$n" ;;
        27) run_investigation "Tiny COP Routine"          "LIVE-TINY-COP-027"     "DISMISS"      "" "$n" ;;
        28) run_investigation "Income Gap COP"            "LIVE-INCOME-GAP-028"   "REQUEST_INFO" "" "$n" ;;
        29) run_investigation "Ghost Probe"               "LIVE-GHOST-PROBE-029"  "ESCALATE"     "" "$n" ;;
        30) run_investigation "PEP Phantom"               "LIVE-PEP-PHANTOM-030"  "ESCALATE"     "" "$n" ;;
        *)  fail "Unknown scenario number: $n (valid: 1-${TOTAL_SCENARIOS})"; exit 1 ;;
    esac
}

# Convert a named scenario to its number
name_to_num() {
    local name="$1"
    for i in $(seq 1 $TOTAL_SCENARIOS); do
        [[ "${SCENARIO_NAMES[$i]}" == "$name" ]] && echo "$i" && return
    done
    echo ""
}

# ── Main ───────────────────────────────────────────────────────────────────────
echo -e "${BOLD}${BLUE}"
echo "  ╔═══════════════════════════════════════════╗"
echo "  ║   Compliance AI — Live Test Suite         ║"
echo "  ║   ${BASE_URL}   ║"
echo "  ╚═══════════════════════════════════════════╝"
echo -e "${NC}"

check_api_health

if [[ -n "$SCENARIO_NUM" ]]; then
    # -s NUM: run exactly one scenario by number
    if ! [[ "$SCENARIO_NUM" =~ ^[0-9]+$ ]] || (( SCENARIO_NUM < 1 || SCENARIO_NUM > TOTAL_SCENARIOS )); then
        fail "Invalid scenario number: ${SCENARIO_NUM} (valid: 1-${TOTAL_SCENARIOS})"
        exit 1
    fi
    run_scenario_by_num "$SCENARIO_NUM"
elif [[ -n "$LIMIT" ]]; then
    # -l NUM: run first N scenarios
    if ! [[ "$LIMIT" =~ ^[0-9]+$ ]] || (( LIMIT < 1 || LIMIT > TOTAL_SCENARIOS )); then
        fail "Invalid limit: ${LIMIT} (valid: 1-${TOTAL_SCENARIOS})"
        exit 1
    fi
    for i in $(seq 1 "$LIMIT"); do
        run_scenario_by_num "$i"
    done
else
    # Named scenario or "all"
    case "$SCENARIO" in
        all)
            for i in $(seq 1 $TOTAL_SCENARIOS); do
                run_scenario_by_num "$i"
            done
            ;;
        *)
            num=$(name_to_num "$SCENARIO")
            if [[ -z "$num" ]]; then
                fail "Unknown scenario: ${SCENARIO}"
                echo "  Valid names: ${SCENARIO_NAMES[*]:1}"
                echo "  Or use: -s NUM (1-${TOTAL_SCENARIOS}) | -l NUM"
                exit 1
            fi
            run_scenario_by_num "$num"
            ;;
    esac
fi

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
