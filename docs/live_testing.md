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
Done — 8 created, 0 skipped.
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

### One scenario at a time

```bash
make live-test SCENARIO=pep-small      # PEP hard-rule (fastest, no LLM)
make live-test SCENARIO=high-risk      # escalation path
make live-test SCENARIO=low-risk       # dismissal path
make live-test SCENARIO=mid-risk       # request-info path
make live-test SCENARIO=corp           # UIAF threshold match
make live-test SCENARIO=multi-ccy      # multi-currency layering
make live-test SCENARIO=pep-large      # PEP + high value
make live-test SCENARIO=safe           # safe retail customer
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

| # | Scenario | External ID | Amount | Currency | PEP | xgb | Expected Decision |
|---|---|---|---|---|---|---|---|
| 1 | Low-risk dismissal | `LIVE-LOW-RISK-001` | 3,500,000 | COP | No | 0.31 | **DISMISS** |
| 2 | High-risk escalation | `LIVE-HIGH-RISK-002` | 85,000 | USD | No | 0.89 | **ESCALATE** |
| 3 | PEP — small amount | `LIVE-PEP-SMALL-003` | 12,000 | MXN | **Yes** | 0.45 | **ESCALATE** ¹ |
| 4 | PEP — large amount | `LIVE-PEP-LARGE-004` | 750,000 | USD | **Yes** | 0.92 | **ESCALATE** ¹ |
| 5 | Mid-risk / ambiguous | `LIVE-MID-RISK-005` | 18,500 | PEN | No | 0.61 | **REQUEST_INFO** |
| 6 | Multi-currency activity | `LIVE-MULTI-CCY-006` | 45,000 | USD | No | 0.77 | **ESCALATE** |
| 7 | Corporate high COP | `LIVE-CORP-007` | 48,000,000 | COP | No | 0.83 | **ESCALATE** |
| 8 | Safe retail customer | `LIVE-SAFE-008` | 8,500 | MXN | No | 0.22 | **DISMISS** |

¹ PEP scenarios use the deterministic hard-rule — no LLM or RAG call is made. These run in ~1-2 seconds instead of the typical 5-15 seconds.

---

## What to Observe

### PEP hard-rule (scenarios 3 and 4)

- `is_pep_override_applied: true` in the response
- `confidence: 1.0` (not LLM-estimated)
- All three regulators cited: SARLAFT CE 029/2014 Cap. IV + DCG Art. 115 LIC Disp. 31a + Res. SBS 789-2018 Art. 17
- Faster pipeline time (no RAG retrieval, no LLM call in the decision step)

### RAG citations (non-PEP scenarios)

- `regulations_cited` contains specific articles with source, article number, and quoted text
- `step_by_step_reasoning` explains each decision step referencing the retrieved regulations
- For scenario 7 (48M COP), expect UIAF Circular 002 Sección 4.2 to be cited

### Audit trail

- Three events: `INVESTIGATION_COMPLETED`, `RISK_ANALYSIS_COMPLETED`, `DECISION_MADE`
- Each event shows `duration_ms` and `token_cost_usd`
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
