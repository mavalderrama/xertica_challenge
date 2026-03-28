#!/usr/bin/env python3
"""
Per-scenario visual renderer for the Compliance AI live test suite.

Called by live_test.sh after each pipeline invocation. Renders a workflow
diagram to stdout and appends the scenario result to the accumulator JSON file.

Exit code: 0 if decision matched expected, 1 if mismatch.
"""
import argparse
import json
import sys
from pathlib import Path

# ── ANSI ──────────────────────────────────────────────────────────────────────
BOLD    = "\033[1m"
DIM     = "\033[2m"
GREEN   = "\033[0;32m"
YELLOW  = "\033[1;33m"
RED     = "\033[0;31m"
CYAN    = "\033[0;36m"
BLUE    = "\033[0;34m"
MAGENTA = "\033[0;35m"
NC      = "\033[0m"

# ── Box geometry ──────────────────────────────────────────────────────────────
INNER_W    = 22          # chars between │ borders
LEFT_HALF  = 10          # dashes left of the ┬ connector
RIGHT_HALF = INNER_W - LEFT_HALF - 1   # = 11
ARROW_PAD  = " " * (3 + LEFT_HALF)     # 13 spaces — aligns │/▼ under ┬


def _top(color: str) -> str:
    return f"  {color}┌{'─' * INNER_W}┐{NC}"


def _row(label: str, detail: str, box_color: str, label_color: str = "") -> str:
    content = f" {label:<{INNER_W - 1}}"
    return f"  {box_color}│{NC}{label_color}{content}{box_color}│{NC}  {detail}"


def _bottom_arrow(color: str) -> str:
    bar = "─" * LEFT_HALF + "┬" + "─" * RIGHT_HALF
    return f"  {color}└{bar}┘{NC}\n{ARROW_PAD}{color}│{NC}\n{ARROW_PAD}{color}▼{NC}"


def _bottom(color: str) -> str:
    return f"  {color}└{'─' * INNER_W}┘{NC}"


def _decision_color(d: str) -> str:
    return {"ESCALATE": RED, "DISMISS": GREEN, "REQUEST_INFO": YELLOW}.get(d, NC)


def _fmt_amount(amount: float | None, currency: str) -> str:
    if amount is None:
        return f"? {currency}"
    if amount >= 1_000_000:
        return f"{amount / 1_000_000:.1f}M {currency}"
    if amount >= 1_000:
        return f"{amount / 1_000:.0f}K {currency}"
    return f"{amount:.0f} {currency}"


def _risk_color(score: int | None) -> str:
    if score is None:
        return NC
    if score >= 8:
        return RED
    if score >= 5:
        return YELLOW
    return GREEN


def render_workflow(
    label: str,
    scenario_num: int,
    ext_id: str,
    expected: str,
    elapsed: float,
    response: dict,
    audit: dict,
    context: dict,
) -> bool:
    """Print pipeline workflow diagram. Returns True when decision matched."""
    risk  = response.get("risk_analysis") or {}
    dec   = response.get("decision") or {}
    decision_type   = dec.get("decision_type") or response.get("status", "?")
    confidence      = dec.get("confidence", 0.0)
    is_pep_override = dec.get("is_pep_override_applied", False)
    risk_score      = risk.get("risk_score")
    human_summary   = risk.get("human_summary", "")

    events     = audit.get("events", [])
    total_cost = sum(float(e.get("token_cost_usd", 0)) for e in events)

    # Alert / investigation context
    amount     = context.get("current_alert_amount")
    currency   = context.get("current_alert_currency", "")
    is_pep     = context.get("is_pep", False)
    xgb        = context.get("xgboost_score", "?")
    tx_count   = context.get("transaction_count_90d", "?")
    total_90d  = context.get("total_amount_90d")
    currencies = context.get("currencies", [])
    countries  = context.get("countries", [])
    docs_count = context.get("documents_count", "?")
    num_regs   = len(dec.get("regulations_cited", []))

    # ── Scenario header ───────────────────────────────────────────────────────
    title = f"  SCENARIO {scenario_num}: {label}"
    print(f"\n  {BOLD}{BLUE}┌{'─' * 56}┐{NC}")
    print(f"  {BOLD}{BLUE}│ {title:<55}│{NC}")
    print(f"  {BOLD}{BLUE}└{'─' * 56}┘{NC}\n")

    # ── 1. Alert Input ────────────────────────────────────────────────────────
    pep_flag     = f"{RED}PEP ⚡{NC}" if is_pep else "No PEP"
    amt_str      = _fmt_amount(amount, currency)
    alert_detail = (
        f"{DIM}{ext_id}{NC}  │  {BOLD}{amt_str}{NC}"
        f"  │  {pep_flag}  │  xgb: {BOLD}{xgb}{NC}"
    )
    print(_top(BLUE))
    print(_row("Alert Input", alert_detail, BLUE, BOLD))
    print(_bottom_arrow(BLUE))
    print()

    # ── 2. Investigador ───────────────────────────────────────────────────────
    total_str  = _fmt_amount(total_90d, currency) if total_90d else "?"
    ccy_str    = "/".join(currencies[:4]) or "?"
    ctry_str   = "/".join(countries[:3]) or "?"
    inv_detail = (
        f"{BOLD}{tx_count}{NC} txns  │  {total_str} total"
        f"  │  {ctry_str}  │  {ccy_str}  │  {docs_count} docs"
    )
    print(_top(CYAN))
    print(_row("Investigador", inv_detail, CYAN))
    print(_bottom_arrow(CYAN))
    print()

    # ── 3. Risk Analyzer ──────────────────────────────────────────────────────
    sc_color    = _risk_color(risk_score)
    score_str   = f"{sc_color}{BOLD}{risk_score}/10{NC}" if risk_score else "?/10"
    summary_short = (human_summary[:65] + "…") if len(human_summary) > 65 else human_summary
    risk_detail   = f"Score: {score_str}  │  {DIM}\"{summary_short}\"{NC}"
    print(_top(CYAN))
    print(_row("Risk Analyzer", risk_detail, CYAN))

    # ── 4. Decision Agent or PEP Hard Rule ────────────────────────────────────
    if is_pep_override:
        print(_bottom_arrow(CYAN))
        print()
        pep_detail = (
            f"{RED}{BOLD}Mandatory escalation{NC} — no LLM call  ⚡"
            "  │  SARLAFT / DCG / SBS 789-2018"
        )
        print(_top(MAGENTA))
        print(_row("⚡ PEP HARD RULE", pep_detail, MAGENTA, BOLD))
        print(_bottom_arrow(MAGENTA))
    else:
        print(_bottom_arrow(CYAN))
        print()
        dc         = _decision_color(decision_type)
        dec_detail = (
            f"{dc}{BOLD}{decision_type}{NC} (conf: {confidence:.2f})"
            f"  │  {num_regs} regulations cited"
        )
        print(_top(CYAN))
        print(_row("Decision Agent", dec_detail, CYAN))
        print(_bottom_arrow(CYAN))
    print()

    # ── 5. Result ─────────────────────────────────────────────────────────────
    matched      = decision_type == expected
    result_icon  = f"{GREEN}✓ MATCH{NC}" if matched else f"{YELLOW}⚠ MISMATCH{NC}"
    result_color = GREEN if matched else YELLOW

    dc = _decision_color(decision_type)
    ec = _decision_color(expected)
    result_detail = (
        f"{result_icon}  │  {dc}{BOLD}{decision_type}{NC}"
        f"  (expected: {ec}{expected}{NC})"
        f"  │  {elapsed:.1f}s  │  ${total_cost:.5f}"
    )
    print(_top(result_color))
    print(_row("Result", result_detail, result_color, BOLD))
    print(_bottom(result_color))
    print()

    return matched


def accumulate_result(
    results_file: Path,
    scenario_num: int,
    label: str,
    ext_id: str,
    expected: str,
    elapsed: float,
    response: dict,
    audit: dict,
    context: dict,
) -> None:
    """Append this scenario to the JSON accumulator file."""
    dec   = response.get("decision") or {}
    risk  = response.get("risk_analysis") or {}
    events     = audit.get("events", [])
    total_cost = sum(float(e.get("token_cost_usd", 0)) for e in events)
    decision_type = dec.get("decision_type") or response.get("status", "?")

    result = {
        "scenario_number":   scenario_num,
        "scenario_label":    label,
        "external_alert_id": ext_id,
        "alert_data": {
            "amount":         context.get("current_alert_amount"),
            "currency":       context.get("current_alert_currency"),
            "is_pep":         context.get("is_pep", False),
            "xgboost_score":  context.get("xgboost_score"),
            "segment":        context.get("segment"),
        },
        "investigation": {
            "transaction_count_90d": context.get("transaction_count_90d"),
            "total_amount_90d":      context.get("total_amount_90d"),
            "currencies":            context.get("currencies", []),
            "countries":             context.get("countries", []),
            "documents_count":       context.get("documents_count"),
        },
        "risk_analysis": {
            "risk_score":         risk.get("risk_score"),
            "justification":      risk.get("justification", ""),
            "anomalous_patterns": risk.get("anomalous_patterns", []),
            "human_summary":      risk.get("human_summary", ""),
        },
        "decision": {
            "decision_type":          decision_type,
            "confidence":             dec.get("confidence", 0),
            "regulations_cited":      dec.get("regulations_cited", []),
            "step_by_step_reasoning": dec.get("step_by_step_reasoning", ""),
            "is_pep_override_applied": dec.get("is_pep_override_applied", False),
        },
        "expected_decision": expected,
        "elapsed_seconds":   round(elapsed, 2),
        "total_cost_usd":    round(total_cost, 6),
        "matched":           decision_type == expected,
    }

    existing: list = []
    if results_file.exists():
        try:
            existing = json.loads(results_file.read_text())
        except json.JSONDecodeError:
            existing = []
    existing.append(result)
    results_file.write_text(json.dumps(existing, indent=2, default=str))


def main() -> int:
    p = argparse.ArgumentParser(description="Render live-test scenario workflow")
    p.add_argument("--response",     required=True,  help="InvestigateResponse JSON string")
    p.add_argument("--audit",        required=True,  help="AuditTrailResponse JSON string")
    p.add_argument("--context",      default="{}",   help="Investigation structured_context JSON")
    p.add_argument("--ext-id",       required=True,  help="External alert ID")
    p.add_argument("--expected",     required=True,  help="Expected decision type")
    p.add_argument("--elapsed",      type=float, required=True)
    p.add_argument("--scenario-num", type=int,   required=True)
    p.add_argument("--label",        required=True)
    p.add_argument("--results-file", required=True)
    args = p.parse_args()

    try:
        response = json.loads(args.response)
    except (json.JSONDecodeError, TypeError) as exc:
        print(f"  {YELLOW}WARNING: Could not parse /investigate response ({exc}), rendering with empty data{NC}", file=sys.stderr)
        response = {}
    try:
        audit = json.loads(args.audit)
    except (json.JSONDecodeError, TypeError) as exc:
        print(f"  {YELLOW}WARNING: Could not parse /audit-trail response ({exc}), using empty audit{NC}", file=sys.stderr)
        print(f"  {YELLOW}Raw audit response: {args.audit!r}{NC}", file=sys.stderr)
        audit = {"events": []}
    try:
        context = json.loads(args.context)
    except (json.JSONDecodeError, TypeError):
        context = {}

    matched = render_workflow(
        label=args.label,
        scenario_num=args.scenario_num,
        ext_id=args.ext_id,
        expected=args.expected,
        elapsed=args.elapsed,
        response=response,
        audit=audit,
        context=context,
    )

    accumulate_result(
        results_file=Path(args.results_file),
        scenario_num=args.scenario_num,
        label=args.label,
        ext_id=args.ext_id,
        expected=args.expected,
        elapsed=args.elapsed,
        response=response,
        audit=audit,
        context=context,
    )

    return 0 if matched else 1


if __name__ == "__main__":
    sys.exit(main())
