#!/usr/bin/env python3
"""
LLM-as-Judge evaluator for the Compliance AI live test suite.

Usage:
    python scripts/llm_judge.py <results_json_file>

Reads accumulated scenario results produced by live_test.sh, loads regulatory
documents, calls the OpenAI API to evaluate each decision, then renders a
scored report in the terminal.

Model: OPENAI_MODEL from backend/.env (same as the pipeline model).
Override with LLM_JUDGE_MODEL env var.
"""
import json
import os
import re
import sys
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
_HERE        = Path(__file__).resolve().parent
BACKEND_DIR  = _HERE.parent / "backend"
REG_DOCS_DIR = BACKEND_DIR / "tests" / "fixtures" / "regulatory_docs"
ENV_FILE     = BACKEND_DIR / ".env"

# ── ANSI ──────────────────────────────────────────────────────────────────────
BOLD    = "\033[1m"
DIM     = "\033[2m"
GREEN   = "\033[0;32m"
YELLOW  = "\033[1;33m"
RED     = "\033[0;31m"
CYAN    = "\033[0;36m"
BLUE    = "\033[0;34m"
NC      = "\033[0m"

_ANSI = re.compile(r"\033\[[0-9;]*m")


def _dlen(s: str) -> int:
    """Display length of a string, ignoring ANSI escape codes."""
    return len(_ANSI.sub("", s))


def _pad(s: str, width: int, align: str = "^") -> str:
    """Pad s to display-width, correctly accounting for ANSI codes."""
    gap = max(0, width - _dlen(s))
    if align == "<":
        return s + " " * gap
    if align == ">":
        return " " * gap + s
    lpad = gap // 2
    return " " * lpad + s + " " * (gap - lpad)


def _score_fmt(score: int) -> str:
    color = GREEN if score >= 5 else (YELLOW if score >= 3 else RED)
    return f"{color}{BOLD}{score}/5{NC}"


def _decision_color(d: str) -> str:
    return {"ESCALATE": RED, "DISMISS": GREEN, "REQUEST_INFO": YELLOW}.get(d, NC)


# ── Table geometry ────────────────────────────────────────────────────────────
# Row format: ║ <scenario(28)> │ <dec(8)> │ <comp(10)> │ <reason(9)> │ <risk(6)> │ <total(9)> ║
# Content width = 1+28+3+8+3+10+3+9+3+6+3+9+1 = 87
W_SCENARIO = 28
W_DEC      = 8
W_COMP     = 10
W_REASON   = 9
W_RISK     = 6
W_TOTAL    = 9
TABLE_W    = 1 + W_SCENARIO + 3 + W_DEC + 3 + W_COMP + 3 + W_REASON + 3 + W_RISK + 3 + W_TOTAL + 1


def _row(scenario: str, dec: str, comp: str, reason: str, risk: str, total: str) -> str:
    sep = f" {BLUE}│{NC} "
    parts = (
        " "
        + _pad(scenario, W_SCENARIO, "<")
        + sep + _pad(dec,    W_DEC)
        + sep + _pad(comp,   W_COMP)
        + sep + _pad(reason, W_REASON)
        + sep + _pad(risk,   W_RISK)
        + sep + _pad(total,  W_TOTAL)
        + " "
    )
    return f"  {BOLD}{BLUE}║{NC}{parts}{BOLD}{BLUE}║{NC}"


def _divider(char: str = "─") -> str:
    return f"  {BOLD}{BLUE}╠{char * TABLE_W}╣{NC}"


def _full_row(text: str, bold: bool = False) -> str:
    prefix = BOLD if bold else ""
    return f"  {BOLD}{BLUE}║{NC}{prefix}{_pad(text, TABLE_W)}{NC if bold else ''}{BOLD}{BLUE}║{NC}"


# ── Judge prompts ─────────────────────────────────────────────────────────────
_SYSTEM = """\
You are a senior compliance evaluation judge for a Latin American financial
institution's AI-powered alert processing system. Evaluate automated compliance
decisions against the regulatory framework of three jurisdictions:

  • UIAF/SARLAFT — Colombia  (CE 029/2014, Decreto 830/2021)
  • CNBV          — Mexico   (DCG per Art. 115 LIC)
  • SBS/UIF-Perú  — Peru     (Resolución SBS 789-2018, Ley 27693)

Key regulatory rules to check:
  • PEP alerts MUST be escalated — mandatory in all three jurisdictions, no exceptions
  • Colombia: COP 10M (natural person) / COP 50M (legal entity) cash thresholds; ROS immediate
  • Mexico: USD 7,500 equivalent for Relevant Operations; ROI within 60 calendar days
  • Peru: S/ 10,000 single operation; S/ 30,000 cumulative/30 days; ROS immediate
  • Multi-currency without documented justification = high-risk signal everywhere
  • Profile inconsistency (declared income vs. transaction volume) = alert signal everywhere

Evaluate on 4 dimensions (1–5 scale):

1. decision_correctness
   Is ESCALATE / DISMISS / REQUEST_INFO the right call for this alert profile?
   5=clearly right | 4=correct, minor context missed | 3=defensible/ambiguous |
   2=questionable, compliance officer would object | 1=clearly wrong (regulatory risk)

2. regulatory_compliance
   Are cited regulations correct, relevant, and complete? Are mandatory rules applied?
   5=all applicable regulations correctly cited, hard rules respected |
   4=key regs cited, minor omissions | 3=some regs cited, important ones missing |
   2=cited regulations largely irrelevant to the facts | 1=wrong or none

3. reasoning_quality
   Is the step-by-step reasoning logically sound and evidence-based?
   5=exceptional, clear causal chain | 4=good, minor gaps | 3=adequate but shallow |
   2=weak, circular, or unsupported | 1=absent or contradictory

4. risk_score_accuracy
   Is the 1–10 risk score properly calibrated to the scenario?
   5=perfect | 4=off by ≤1 | 3=off by ≤2 | 2=off by 3+ | 1=completely miscalibrated

Flag critical_failure=true if ANY of these occur:
  • PEP customer is NOT escalated (direct regulatory violation)
  • Decision is DISMISS when risk_score ≥ 8
  • A mandatory reporting threshold breach is dismissed without documented justification

Respond ONLY with valid JSON (no markdown, no extra text):
{
  "decision_correctness":   {"score": <1-5>, "explanation": "<1-2 sentences>"},
  "regulatory_compliance":  {"score": <1-5>, "explanation": "<1-2 sentences>"},
  "reasoning_quality":      {"score": <1-5>, "explanation": "<1-2 sentences>"},
  "risk_score_accuracy":    {"score": <1-5>, "explanation": "<1-2 sentences>"},
  "critical_failure":       <true|false>,
  "critical_failure_reason":"<null or brief reason>"
}"""


def _build_user_message(scenario: dict, reg_text: str) -> str:
    alert = scenario.get("alert_data") or {}
    inv   = scenario.get("investigation") or {}
    risk  = scenario.get("risk_analysis") or {}
    dec   = scenario.get("decision") or {}

    return f"""\
## Scenario: {scenario.get("scenario_label", "?")}

### Alert Profile
- External ID  : {scenario.get("external_alert_id", "?")}
- Amount       : {alert.get("amount", "?")} {alert.get("currency", "")}
- Is PEP       : {alert.get("is_pep", False)}
- XGBoost score: {alert.get("xgboost_score", "?")}
- Segment      : {alert.get("segment", "?")}

### Investigation Data (90-day window)
- Transactions : {inv.get("transaction_count_90d", "?")}
- Total amount : {inv.get("total_amount_90d", "?")} {alert.get("currency", "")}
- Currencies   : {", ".join(inv.get("currencies", []))}
- Countries    : {", ".join(inv.get("countries", []))}
- Documents    : {inv.get("documents_count", "?")}

### Risk Analysis
- Score        : {risk.get("risk_score", "?")}/10
- Justification: {risk.get("justification", "N/A")}
- Anomalous patterns: {"; ".join(risk.get("anomalous_patterns", []))}
- Human summary: {risk.get("human_summary", "N/A")}

### Decision Made
- Type         : {dec.get("decision_type", "?")}
- Confidence   : {dec.get("confidence", "?")}
- PEP override : {dec.get("is_pep_override_applied", False)}
- Regulations cited:
{json.dumps(dec.get("regulations_cited", []), indent=2, ensure_ascii=False)}
- Step-by-step reasoning:
{dec.get("step_by_step_reasoning", "N/A")}

### Expected Decision (for reference)
{scenario.get("expected_decision", "?")}

---

## Applicable Regulatory Framework

{reg_text}"""


def _evaluate_one(client, model: str, scenario: dict, reg_text: str) -> dict:
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user",   "content": _build_user_message(scenario, reg_text)},
            ],
            temperature=0,
            max_completion_tokens=1024,
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as exc:
        return {
            "decision_correctness":  {"score": 0, "explanation": f"Judge error: {exc}"},
            "regulatory_compliance": {"score": 0, "explanation": ""},
            "reasoning_quality":     {"score": 0, "explanation": ""},
            "risk_score_accuracy":   {"score": 0, "explanation": ""},
            "critical_failure":      False,
            "critical_failure_reason": None,
        }


# ── Report rendering ──────────────────────────────────────────────────────────

def render_report(scenarios: list[dict], evaluations: list[dict]) -> None:
    # ── Table ─────────────────────────────────────────────────────────────────
    print()
    print(f"  {BOLD}{BLUE}╔{'═' * TABLE_W}╗{NC}")
    print(_full_row("LLM JUDGE EVALUATION REPORT", bold=True))
    print(_divider("═"))
    print(_row("Scenario", "Decision", "Compliance", "Reasoning", "Risk", "Total"))
    print(_divider("─"))

    total_pts  = 0
    max_pts    = 0
    crit_count = 0
    pep_correct, pep_total = 0, 0

    for scenario, ev in zip(scenarios, evaluations):
        s_dec    = ev.get("decision_correctness",  {}).get("score", 0)
        s_comp   = ev.get("regulatory_compliance", {}).get("score", 0)
        s_reason = ev.get("reasoning_quality",     {}).get("score", 0)
        s_risk   = ev.get("risk_score_accuracy",   {}).get("score", 0)
        row_sum  = s_dec + s_comp + s_reason + s_risk
        total_pts += row_sum
        max_pts   += 20

        if ev.get("critical_failure"):
            crit_count += 1

        is_pep = scenario.get("alert_data", {}).get("is_pep", False)
        if is_pep:
            pep_total += 1
            if scenario.get("decision", {}).get("decision_type") == "ESCALATE":
                pep_correct += 1

        matched = scenario.get("matched", False)
        icon    = f"{GREEN}✓{NC}" if matched else f"{YELLOW}⚠{NC}"
        label   = scenario.get("scenario_label", "?")[:W_SCENARIO - 2]
        crit    = f" {RED}!{NC}" if ev.get("critical_failure") else ""
        total_str = f"{BOLD}{row_sum}/20{NC}{crit}"

        print(_row(
            f"{icon} {label}",
            _score_fmt(s_dec),
            _score_fmt(s_comp),
            _score_fmt(s_reason),
            _score_fmt(s_risk),
            total_str,
        ))

    print(_divider("═"))

    # ── Summary footer ────────────────────────────────────────────────────────
    pct       = (total_pts / max_pts * 100) if max_pts else 0
    pct_color = GREEN if pct >= 80 else (YELLOW if pct >= 60 else RED)
    crit_c    = RED if crit_count else GREEN

    print(f"  {BOLD}{BLUE}║{NC}  "
          f"{BOLD}Overall:{NC} {pct_color}{BOLD}{total_pts}/{max_pts} ({pct:.1f}%){NC}"
          f"   {BOLD}Critical failures:{NC} {crit_c}{BOLD}{crit_count}{NC}")

    if pep_total > 0:
        pep_pct = pep_correct / pep_total * 100
        pep_c   = GREEN if pep_pct == 100 else RED
        print(f"  {BOLD}{BLUE}║{NC}  "
              f"{BOLD}PEP compliance:{NC} {pep_c}{BOLD}{pep_correct}/{pep_total} ({pep_pct:.0f}%){NC}")

    print(f"  {BOLD}{BLUE}║{NC}  "
          f"{DIM}Columns: Decision Correctness │ Regulatory Compliance │ "
          f"Reasoning Quality │ Risk Score Accuracy{NC}")
    print(f"  {BOLD}{BLUE}╚{'═' * TABLE_W}╝{NC}")

    # ── Detailed findings per scenario ────────────────────────────────────────
    print(f"\n  {BOLD}{CYAN}── Detailed Findings ──────────────────────────────────────{NC}\n")
    dims = [
        ("decision_correctness",  "Decision"),
        ("regulatory_compliance", "Compliance"),
        ("reasoning_quality",     "Reasoning"),
        ("risk_score_accuracy",   "Risk Score"),
    ]
    for scenario, ev in zip(scenarios, evaluations):
        label    = scenario.get("scenario_label", "?")
        dec_type = scenario.get("decision", {}).get("decision_type", "?")
        matched  = scenario.get("matched", False)
        icon     = f"{GREEN}✓{NC}" if matched else f"{YELLOW}⚠{NC}"
        dc       = _decision_color(dec_type)
        print(f"  {icon}  {BOLD}{label}{NC}  →  {dc}{BOLD}{dec_type}{NC}")

        for key, name in dims:
            d  = ev.get(key, {})
            s  = d.get("score", 0)
            ex = (d.get("explanation") or "")[:95]
            print(f"      {_score_fmt(s)}  {DIM}{name}: {ex}{NC}")

        if ev.get("critical_failure"):
            reason = ev.get("critical_failure_reason") or ""
            print(f"      {RED}{BOLD}⚠ CRITICAL FAILURE: {reason}{NC}")
        print()


# ── Bootstrap ─────────────────────────────────────────────────────────────────

def _load_env() -> None:
    if not ENV_FILE.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(ENV_FILE)
    except ImportError:
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def _load_regulatory_docs() -> str:
    docs = []
    for path in sorted(REG_DOCS_DIR.glob("*.txt")):
        docs.append(f"=== {path.stem.upper()} ===\n{path.read_text(encoding='utf-8')}")
    return "\n\n".join(docs)


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/llm_judge.py <results_json_file>", file=sys.stderr)
        return 1

    _load_env()

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print(f"{RED}ERROR: OPENAI_API_KEY not set in backend/.env{NC}", file=sys.stderr)
        return 1

    # Use the same model as the pipeline (configurable via LLM_JUDGE_MODEL)
    model = (
        os.environ.get("LLM_JUDGE_MODEL")
        or os.environ.get("OPENAI_MODEL")
        or "gpt-4o-mini"
    )

    results_path = Path(sys.argv[1])
    if not results_path.exists():
        print(f"{RED}ERROR: Results file not found: {results_path}{NC}", file=sys.stderr)
        return 1

    try:
        scenarios = json.loads(results_path.read_text())
    except Exception as exc:
        print(f"{RED}ERROR: Could not parse results file: {exc}{NC}", file=sys.stderr)
        return 1

    if not scenarios:
        print("No scenario results to evaluate.", file=sys.stderr)
        return 0

    try:
        from openai import OpenAI
    except ImportError:
        print(f"{RED}ERROR: openai package not available. Run: uv sync{NC}", file=sys.stderr)
        return 1

    reg_text = _load_regulatory_docs()
    client   = OpenAI(api_key=api_key)

    n = len(scenarios)
    print(f"\n  {CYAN}Running LLM-as-Judge: {n} scenario(s) using '{model}'...{NC}")

    evaluations = []
    for i, scenario in enumerate(scenarios, 1):
        label = scenario.get("scenario_label", f"#{i}")
        print(f"  {DIM}  [{i}/{n}] Evaluating: {label}...{NC}" + " " * 10, end="\r", flush=True)
        evaluations.append(_evaluate_one(client, model, scenario, reg_text))

    print(" " * 70, end="\r")  # clear progress line
    render_report(scenarios, evaluations)
    return 0


if __name__ == "__main__":
    sys.exit(main())
