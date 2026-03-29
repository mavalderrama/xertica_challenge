# Live Testing Guide

Step-by-step instructions to run a live demo of the Compliance AI pipeline.

---

## Prerequisites

- Docker Desktop running
- `uv` installed (`brew install uv`)
- GCP credentials configured if using real Vertex AI (`gcloud auth application-default login`)
- For local dev with mocks: no GCP credentials needed (`USE_MOCK_BQ=true`, `USE_MOCK_GCS=true` are the defaults)

---

## Setup (one-time)

### Option A — All-in-one

```bash
make populate
```

This runs `migrate` → `seed` → `index-regulations` → `live-test-judge` in order. Use for a fresh environment.

### Option B — Step by step

```bash
# 1. Install dependencies
make dev-install

# 2. Start PostgreSQL + Langfuse + API
docker compose up

# 3. Apply database migrations (new terminal)
make migrate

# 4. Seed synthetic test alerts
make seed

# 5. Index regulatory documents into the vector store (for RAG)
make index-regulations
```

Expected output from `make seed`:

```
Created [LIVE-LOW-RISK-001]  customer=CUST-LOW-001   amount=3500000.00 COP  pep=False  xgb=0.31  → id=<uuid>
Created [LIVE-HIGH-RISK-002] customer=CUST-HIGH-002  amount=85000.00 USD    pep=False  xgb=0.89  → id=<uuid>
Created [LIVE-PEP-SMALL-003] customer=CUST-PEP-003   amount=12000.00 MXN   pep=True   xgb=0.45  → id=<uuid>
...
Done — 30 created, 0 skipped.
```

Expected output from `make index-regulations`:

```
Indexed 14 new chunks total
  [UIAF] uiaf_sarlaft_sfc_ce029_2014    3 chunks
  [UIAF] uiaf_decreto_830_2021          2 chunks
  [CNBV] cnbv_dcg_art115                3 chunks
  [SBS ] sbs_resolucion_789_2018        3 chunks
  [SBS ] sbs_ley_27693_uif              3 chunks
Created 0 article cross-reference links
Vector store ready: 14 chunks across 5 documents
```

---

## Running Tests

### All scenarios (automated)

```bash
make live-test
```

### All scenarios + LLM Judge evaluation

```bash
make live-test-judge
```

Runs all 30 scenarios then evaluates each decision with an LLM judge (requires `OPENAI_API_KEY` in `backend/.env`). Outputs a summary table to the terminal and writes a full untruncated markdown report to `judge_report_YYYYMMDD_HHMMSS.md` in the repo root.

### One scenario at a time

```bash
# Original 8 scenarios
make live-test SCENARIO=low-risk       # dismissal path (COP)
make live-test SCENARIO=high-risk      # escalation path (USD)
make live-test SCENARIO=pep-small      # PEP hard-rule (MXN, fastest — no LLM)
make live-test SCENARIO=pep-large      # PEP hard-rule (USD)
make live-test SCENARIO=mid-risk       # request-info path (PEN)
make live-test SCENARIO=multi-ccy      # multi-currency layering
make live-test SCENARIO=corp           # UIAF threshold match (COP)
make live-test SCENARIO=safe           # safe retail customer (MXN)

# Structuring & fraud patterns
make live-test SCENARIO=struct         # COP structuring (fraccionamiento)
make live-test SCENARIO=under-thresh   # USD just-under CNBV threshold
make live-test SCENARIO=mule           # money-mule pass-through
make live-test SCENARIO=intl-wire      # FATF high-risk international wire

# PEP variants
make live-test SCENARIO=pep-corp       # PEP corporate USD (hard-rule)
make live-test SCENARIO=pep-pen        # PEP small PEN (hard-rule)

# ESCALATE — high-amount
make live-test SCENARIO=high-pen       # High PEN above threshold
make live-test SCENARIO=large-mxn      # Large MXN wire
make live-test SCENARIO=large-usd      # Large USD SME wire

# REQUEST_INFO — ambiguous
make live-test SCENARIO=new-acct       # New account + large USD
make live-test SCENARIO=id-change      # Identity change + PEN
make live-test SCENARIO=odd-timing     # Unusual-hour PEN
make live-test SCENARIO=corp-med       # Corporate MXN unusual deposits
make live-test SCENARIO=income-gap     # Income gap COP

# DISMISS — low-risk
make live-test SCENARIO=micro          # Micro USD transaction
make live-test SCENARIO=safe-pen       # Safe PEN retail
make live-test SCENARIO=sme-low        # SME low-risk MXN
make live-test SCENARIO=remittance     # Family remittance USD
make live-test SCENARIO=below-cop      # Below-threshold COP
make live-test SCENARIO=tiny-cop       # Tiny COP routine

# Extreme edge cases
make live-test SCENARIO=ghost-probe    # xgboost=0.97 on $75 USD (critical ML vs trivial amount)
make live-test SCENARIO=pep-phantom    # PEP=True on EUR 0.01 xgb=0.02 (hard-rule unconditional)
```

### Manual curl (copy UUID from `make seed` output)

```bash
# Trigger investigation
curl -s -X POST http://localhost:8000/api/v1/alerts/<uuid>/investigate \
  -H "Content-Type: application/json" \
  -d '{}' | python3 -m json.tool

# Check status
curl -s http://localhost:8000/api/v1/alerts/<uuid>/status | python3 -m json.tool

# Get full audit trail
curl -s http://localhost:8000/api/v1/alerts/<uuid>/audit-trail | python3 -m json.tool
```

---

## Test Scenarios

| # | Label | External ID | Amount | Currency | PEP | xgb | Expected |
|---|-------|-------------|--------|----------|-----|-----|----------|
| 1 | Low-Risk Dismissal | `LIVE-LOW-RISK-001` | 3,500,000 | COP | No | 0.31 | **DISMISS** |
| 2 | High-Risk Escalation | `LIVE-HIGH-RISK-002` | 85,000 | USD | No | 0.89 | **ESCALATE** |
| 3 | PEP — Small Amount | `LIVE-PEP-SMALL-003` | 12,000 | MXN | **Yes** | 0.45 | **ESCALATE** ¹ |
| 4 | PEP — Large Amount | `LIVE-PEP-LARGE-004` | 750,000 | USD | **Yes** | 0.92 | **ESCALATE** ¹ |
| 5 | Mid-Risk Request Info | `LIVE-MID-RISK-005` | 18,500 | PEN | No | 0.61 | **REQUEST_INFO** |
| 6 | Multi-Currency Activity | `LIVE-MULTI-CCY-006` | 45,000 | USD | No | 0.77 | **ESCALATE** |
| 7 | Corporate High COP | `LIVE-CORP-007` | 48,000,000 | COP | No | 0.83 | **ESCALATE** |
| 8 | Safe Retail Customer | `LIVE-SAFE-008` | 8,500 | MXN | No | 0.22 | **DISMISS** |
| 9 | COP Structuring Pattern | `LIVE-STRUCT-009` | 9,800,000 | COP | No | 0.76 | **ESCALATE** |
| 10 | New Account Large USD | `LIVE-NEW-ACCT-010` | 18,500 | USD | No | 0.56 | **REQUEST_INFO** |
| 11 | Micro-Transaction USD | `LIVE-MICRO-011` | 320 | USD | No | 0.14 | **DISMISS** |
| 12 | PEP Corporate High USD | `LIVE-PEP-CORP-012` | 92,000 | USD | **Yes** | 0.87 | **ESCALATE** ¹ |
| 13 | High PEN Above Threshold | `LIVE-HIGH-PEN-013` | 43,000 | PEN | No | 0.79 | **ESCALATE** |
| 14 | Safe PEN Retail | `LIVE-SAFE-PEN-014` | 3,800 | PEN | No | 0.24 | **DISMISS** |
| 15 | USD Structuring CNBV | `LIVE-UNDER-THRESH-015` | 7,300 | USD | No | 0.83 | **ESCALATE** |
| 16 | FATF High-Risk Wire | `LIVE-INTL-WIRE-016` | 34,000 | USD | No | 0.81 | **ESCALATE** |
| 17 | SME Low-Risk MXN | `LIVE-SME-LOW-017` | 9,200 | MXN | No | 0.33 | **DISMISS** |
| 18 | Identity Change PEN | `LIVE-ID-CHANGE-018` | 13,500 | PEN | No | 0.55 | **REQUEST_INFO** |
| 19 | Large MXN Wire | `LIVE-LARGE-MXN-019` | 195,000 | MXN | No | 0.88 | **ESCALATE** |
| 20 | Family Remittance USD | `LIVE-REMITTANCE-020` | 280 | USD | No | 0.16 | **DISMISS** |
| 21 | Unusual-Hour PEN | `LIVE-ODD-TIMING-021` | 16,000 | PEN | No | 0.63 | **REQUEST_INFO** |
| 22 | Large USD SME Wire | `LIVE-LARGE-USD-022` | 67,000 | USD | No | 0.86 | **ESCALATE** |
| 23 | PEP Small PEN | `LIVE-PEP-PEN-023` | 2,800 | PEN | **Yes** | 0.38 | **ESCALATE** ¹ |
| 24 | Below-Threshold COP | `LIVE-BELOW-COP-024` | 3,200,000 | COP | No | 0.27 | **DISMISS** |
| 25 | Corporate MXN Unusual | `LIVE-CORP-MED-025` | 62,000 | MXN | No | 0.59 | **REQUEST_INFO** |
| 26 | Money-Mule Pass-Through | `LIVE-MULE-026` | 9,600 | USD | No | 0.84 | **ESCALATE** |
| 27 | Tiny COP Routine | `LIVE-TINY-COP-027` | 480,000 | COP | No | 0.11 | **DISMISS** |
| 28 | Income Gap COP | `LIVE-INCOME-GAP-028` | 21,500,000 | COP | No | 0.67 | **REQUEST_INFO** |
| 29 | Ghost Probe | `LIVE-GHOST-PROBE-029` | 75 | USD | No | **0.97** | **ESCALATE** ² |
| 30 | PEP Phantom | `LIVE-PEP-PHANTOM-030` | **0.01** | EUR | **Yes** | 0.02 | **ESCALATE** ¹ |

¹ PEP scenarios use the deterministic hard-rule — no LLM or RAG call is made. These run in ~1-2 seconds instead of the typical 5-15 seconds. (Scenarios 3, 4, 12, 23, 30)

² Ghost Probe tests that the CRITICAL xgboost band (0.80–1.0) triggers ESCALATE regardless of the raw transaction amount. The $75 USD amount is below any reporting threshold, but the XGBoost model signals a behavioural anomaly pattern (dormant account reactivation + micro-burst) that no human analyst should dismiss without review.

**Decision distribution:** 10 DISMISS · 15 ESCALATE · 5 REQUEST_INFO

---

## LLM Judge Evaluation

```bash
make live-test-judge
```

After all 30 scenarios run, the LLM judge scores each decision on four dimensions (each 1–5):

| Dimension | What it measures |
|-----------|-----------------|
| `decision_correctness` | Does the decision match the expected outcome? |
| `regulatory_compliance` | Are the cited regulations accurate and relevant? |
| `reasoning_quality` | Is the step-by-step reasoning coherent and complete? |
| `risk_score_accuracy` | Is the 1–10 risk score calibrated to the evidence? |

The judge also flags **critical failures**:
- PEP alert not escalated (regulatory violation)
- DISMISS when risk score ≥ 8
- Amount above reporting threshold dismissed without justification

**Outputs:**
- Terminal summary table with scores per scenario
- Full untruncated markdown report: `judge_report_YYYYMMDD_HHMMSS.md` in the repo root

**Requires:** `OPENAI_API_KEY` set in `backend/.env` (judge uses GPT-4o).

**Calibration loop:** Judge findings directly inform prompt updates in `RISK_PROMPT` (risk_analyzer.py) and `DECISION_PROMPT` (decision_agent.py). For example, the original prompts over-escalated scenarios 1 and 8 — the judge identified this as missing xgboost calibration context and currency-to-USD conversion. Adding those to the prompts resolved both cases.

---

## What to Observe

### PEP hard-rule (scenarios 3, 4, 12, 23, 30)

- `is_pep_override_applied: true` in the response
- `confidence: 1.0` (not LLM-estimated)
- All three regulators cited: SARLAFT CE 029/2014 Cap. IV + DCG Art. 115 LIC Disp. 31a + Res. SBS 789-2018 Art. 17
- Faster pipeline time (no RAG retrieval, no LLM call in the decision step)

### RAG citations (non-PEP scenarios)

- `regulations_cited` contains specific articles with source, article number, and quoted text
- `step_by_step_reasoning` explains each decision step referencing the retrieved regulations
- For scenario 7 (48M COP), expect UIAF Circular 002 Sección 4.2 to be cited

### Audit trail

- Three events per alert: `INVESTIGATION`, `RISK_ANALYSIS`, `DECISION`
- Each event shows `duration_ms`, `token_cost_usd`, and `langfuse_trace_id`
- All three events share the same `langfuse_trace_id` (set at API layer, propagated through pipeline state)
- Total LLM cost per non-PEP alert should be < $0.01 with Gemini Flash

### Langfuse traces

Open http://localhost:3001 to see distributed traces for each pipeline run. Default credentials: `admin` / `password`.

---

## Resetting State

```bash
# Re-seed alerts (clears all existing, creates fresh set)
make seed-clear

# Re-index regulations (useful after changing fixture docs)
cd backend && uv run python manage.py index_regulations --clear --settings=config.settings.local

# Full reset
docker compose down -v   # wipes DB volumes
docker compose up
make migrate
make seed
make index-regulations
```

---

## Observability

| URL | Description |
|---|---|
| http://localhost:8000/docs | Swagger UI — interactive API explorer |
| http://localhost:8000/health | Liveness check |
| http://localhost:8000/readiness | Readiness check (DB connection) |
| http://localhost:3001 | Langfuse — traces, latency, cost per alert |
