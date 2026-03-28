# Assumptions & Architecture — Compliance AI System

> This document records every assumption made during design and implementation, explains the agent pipeline in detail, describes how users interact with the system, and walks through concrete examples.
>
> Per the challenge brief: *"Tienes dudas sobre el escenario del cliente? Anótalas y documenta tus supuestos."*

---

## Table of Contents

1. [Assumptions](#1-assumptions)
2. [Architecture Overview](#2-architecture-overview)
3. [Agent Deep Dive](#3-agent-deep-dive)
4. [RAG System](#4-rag-system)
5. [Data Model](#5-data-model)
6. [User Interaction](#6-user-interaction)
7. [Examples](#7-examples)

---

## 1. Assumptions

### 1.1 Business & Operational

| Assumption | Basis | Impact |
|---|---|---|
| Alert volume: ~2,000/month | Stated implicitly in challenge cost model ($24/alert × 8 analysts) | Used to size infrastructure (Cloud Run min=1/max=10, Cloud SQL `db-g1-small`) |
| False positive rate: 68% | Challenge description | Informs the expected DISMISS rate; the system should dismiss ~1,360 alerts/month without human review |
| 8 compliance analysts today | CTO document cost model | Baseline for ROI calculation — the system replaces 6 of these with automated triage |
| Resolution target: <30 min | Challenge requirement | Pipeline must complete p95 in <30s; human review of escalated alerts is the remaining time |
| Three regulatory jurisdictions | Challenge requirement: UIAF (Colombia), CNBV (Mexico), SBS (Peru) | All three corpora are indexed in the RAG vector store; the Decision Agent cites articles from whichever is applicable |
| Human-in-the-loop for escalations | Challenge requirement and regulatory mandate | The system outputs ESCALATE/DISMISS/REQUEST_INFO; only DISMISS closes the alert automatically |

### 1.2 Data & Infrastructure

**BigQuery transaction history**
- Assumed structure: one row per transaction, columns include `customer_id`, `transaction_id`, `amount`, `currency`, `country`, `transaction_type`, `transaction_date`
- Query window: last 90 days. The challenge says "3 years of history" — we query 90 days because that is the standard AML look-back window for alert-level investigation. 3 years of history is used for model training (the XGBoost model), not per-alert investigation.
- Table name assumed: `{project_id}.compliance.transactions`

**GCS document store**
- Assumed structure: `customers/{customer_id}/*.pdf`
- Documents represent KYC artifacts (account opening forms, identity verification, PEP screening results)
- PDF text extraction via `pypdf` — assumes text-layer PDFs, not scanned images (OCR not implemented)

**XGBoost model**
- We consume its output (`xgboost_score`, a float 0-1) as a feature in risk analysis context
- We do not retrain, explain, or modify this model — it is an upstream signal
- Assumption: alerts already exist in the database before the pipeline is triggered. The XGBoost model creates the `Alert` record; our API triggers investigation on an existing alert.

**Data residency**
- All computation runs in GCP `us-central1`
- The mock tools (used locally and in CI) never contact external services
- In production, Vertex AI (Gemini) is also hosted in `us-central1` — no customer data leaves GCP

**PostgreSQL as vector store**
- Chose pgvector over Weaviate/Pinecone/ChromaDB to reduce infrastructure surface area (one fewer managed service)
- Trade-off: pgvector approximate nearest neighbor (HNSW/IVFFlat) does not match the throughput of purpose-built vector databases at very large scale, but is entirely adequate for a regulatory document corpus of hundreds to low thousands of chunks
- pgvector extension must be enabled — handled via Terraform (`database_flag` for Cloud SQL) and `pgvector.django` in Django's `INSTALLED_APPS`

### 1.3 LLM & Model Choices

**Gemini 2.0 Flash (`gemini-2.0-flash-001`)**
- Chosen over Gemini 1.5 Pro and Claude: better cost/latency ratio for structured output tasks
- Price assumption: $0.000075/1K input tokens, $0.0003/1K output tokens → ~$0.003/alert at typical prompt lengths
- `temperature=0`: compliance decisions must be deterministic and reproducible. The same alert inputs must always produce the same output — non-zero temperature would make the audit trail non-reproducible.
- Structured output via `JsonOutputParser` — the LLM is instructed to return strict JSON; if parsing fails, the error is captured in `state["errors"]`

**Embeddings: `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions)**
- Trade-off: not the most accurate multilingual model, but fast (runs on CPU), well-supported, and produces normalized vectors suitable for cosine similarity
- Assumption: regulatory Spanish is structurally regular enough that a general-purpose multilingual model captures semantic similarity adequately
- Alternative considered: `text-multilingual-embedding-002` (Vertex AI) — rejected for local dev complexity and cost; can be swapped via the `IRetriever` interface if needed

**TF-IDF sparse vectors (30,000 dimensions)**
- Sparse retrieval catches exact regulatory term matches that dense embeddings miss (e.g., "Disposición 31a", "DCG Art. 115 LIC", "Resolución SBS 789-2018")
- 30,000 vocabulary size covers the full regulatory terminology across three jurisdictions
- `sublinear_tf=True` (log normalization) prevents high-frequency procedural terms ("el", "la", "de") from dominating scores

**Graph retrieval via Django M2M (not Neo4j/FalkorDB)**
- The challenge suggests Neo4j or FalkorDB for the graph layer
- Decision to use Django M2M `related_articles` self-referential field instead:
  - No additional infrastructure component to manage, deploy, or secure
  - For 1-hop traversal (which is all that's needed to link cross-referenced articles within a single regulatory document), a relational adjacency list is equivalent to a graph database
  - Trade-off: deeper graph traversal (2-hop, 3-hop) would require recursive SQL or Cypher; the current implementation only does 1-hop. This is sufficient given that regulatory cross-references are typically direct citations, not multi-hop chains.
  - Can be replaced with a real graph database by implementing a new `IRetriever` — the interface is already defined

### 1.4 Regulatory

| Assumption | Regulation | Implementation |
|---|---|---|
| PEP escalation is mandatory, no exceptions | SARLAFT CE 029/2014 Cap. IV (Colombia); DCG Art. 115 LIC Disp. 31a (Mexico); Res. SBS 789-2018 Art. 17 (Peru) | Deterministic hard-rule in `DecisionAgent` — runs before any LLM call, cannot be overridden by risk score |
| Audit trail must be human-readable | Challenge requirement, UIAF/CNBV/SBS reporting obligations | Every decision stores `step_by_step_reasoning` (plain text) and `regulations_cited` (structured list) in the database |
| Record retention: 10 years | Colombia: 10 years (Ley 526/1999 Art. 10); Mexico: 10 years (DCG Disp. 38a); Peru: 10 years (Ley 27693) | Not enforced in code yet — a database archival policy (Cloud SQL scheduled exports to GCS) should implement this in production |
| Reporting deadlines | Colombia: ROS inmediato (≤24h); Mexico: ROI 60 días naturales + 3 días hábiles para presentar; Peru: ROS inmediato tras decisión | The system surfaces the decision immediately but does not auto-file SAR reports — a human analyst does that after reviewing escalated alerts |
| "La IA lo decidió" is not a valid justification | Challenge regulatory constraint | Every LLM decision includes `step_by_step_reasoning` with explicit references to retrieved regulation chunks |

### 1.5 Architecture

**Django as headless ORM**
- Django is not the web framework — FastAPI is
- Django handles: model definitions, migrations, ORM queries (including async via `aget`/`asave`)
- Django does NOT handle: HTTP routing, middleware, request parsing, authentication
- This is an intentional design choice: Django's ORM and migration tooling are mature, well-tested, and support pgvector. FastAPI provides better async ergonomics and OpenAPI documentation.
- Consequence: `django.setup()` must be called at module import time in `main.py`, before any code that imports Django models

**Pipeline topology: linear, not parallel**
- The challenge says "agents that work in parallel and in sequence"
- The three agents are sequential: `InvestigadorAgent` → `RiskAnalyzerAgent` → `DecisionAgent`
- Within `InvestigadorAgent`, BigQuery and GCS calls are concurrent (`asyncio.gather`) — this is the parallelism
- The agents themselves cannot run in parallel because each depends on the previous agent's output: RiskAnalyzer needs the investigation context; DecisionAgent needs the risk score

**No authentication on the API**
- The API is deployed with `--no-allow-unauthenticated` on Cloud Run — authentication is handled at the Cloud Run ingress level via Google IAM
- The FastAPI application itself has no auth middleware — this is intentional for the assessment; in production the caller would present a GCP identity token

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                          External Caller                             │
│                    (compliance analyst system / CRM)                 │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  POST /api/v1/alerts/{id}/investigate
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         FastAPI (uvicorn)                            │
│    /health    /readiness    /api/v1/alerts/*                         │
│                         alerts.router                                │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        PipelineService                               │
│   1. load Alert from DB                                             │
│   2. build initial LangGraph state                                   │
│   3. set status = INVESTIGATING                                      │
│   4. graph.ainvoke(state)                                           │
│   5. update status based on decision_type                           │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    LangGraph StateGraph                              │
│                                                                     │
│  START ──► [investigador] ──► [risk_analyzer] ──► [decision] ──► END│
│                                                                     │
└──────┬────────────────────┬──────────────────┬───────────────────────┘
       │                    │                  │
       ▼                    ▼                  ▼
┌─────────────┐    ┌────────────────┐   ┌─────────────────────────────┐
│ Investigador│    │  RiskAnalyzer  │   │      DecisionAgent           │
│             │    │                │   │                             │
│ BigQuery ◄──┤    │ Gemini Flash ◄─┤   │ [PEP?] → hard-rule ESCALATE │
│ GCS        ◄┤    │ RISK_PROMPT    │   │ [else] → HybridRetriever    │
│             │    │                │   │          + Gemini Flash      │
│ → saves     │    │ → saves        │   │ → saves Decision            │
│  Investigation   │  RiskAnalysis  │   │   + AuditLog                │
└─────────────┘    └────────────────┘   └─────────────────────────────┘
       │                    │                  │
       └────────────────────┴──────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│               PostgreSQL + pgvector (Django ORM)                     │
│                                                                     │
│  Alert ──1:1──► Investigation ──1:1──► RiskAnalysis ──1:1──► Decision│
│  Alert ──1:N──► AuditLog                                           │
│  RegulationDocument ──M:M──► RegulationDocument (graph)            │
└─────────────────────────────────────────────────────────────────────┘
```

### Layer Responsibilities

| Layer | Component | Responsibility |
|---|---|---|
| HTTP | FastAPI routers | Parse requests, serialize responses, dependency injection |
| Service | `PipelineService` | Orchestrates the full alert lifecycle; only place that updates `Alert.status` |
| Graph | LangGraph `StateGraph` | Routes state between agents; provides replay/debugging capabilities |
| Agents | `InvestigadorAgent`, `RiskAnalyzerAgent`, `DecisionAgent` | Domain logic for each stage of the compliance investigation |
| Tools | `BigQueryTool`, `GCSTool` (real or mock) | External data access; swappable via `BigQueryToolInterface` / `GCSToolInterface` |
| RAG | `HybridRetriever`, `VectorStoreRetriever`, `SparseVectorRetriever`, `GraphRetriever` | Regulatory document retrieval for the Decision Agent |
| Persistence | 5 repository implementations | Async Django ORM operations; all behind interfaces |
| Observability | `LangfuseTracer`, `AuditLog` model | Distributed tracing + regulatory audit log |

### Technology Stack Summary

| Component | Technology | Why |
|---|---|---|
| HTTP framework | FastAPI | Async-native, OpenAPI docs, Pydantic validation |
| ORM & migrations | Django 6 + psycopg3 | Mature migration tooling, async ORM, pgvector integration |
| Agent orchestration | LangGraph 0.5 | Stateful graph execution, built-in streaming and replay |
| LLM | Gemini 2.0 Flash (Vertex AI) | Cost-effective, deterministic at temp=0, GCP-native (data residency) |
| Vector store | PostgreSQL 18 + pgvector | Single DB for relational + vector data; no extra service |
| Dense embeddings | all-MiniLM-L6-v2 | Fast, CPU-runnable, multilingual, 384-dim |
| Sparse embeddings | TF-IDF (scikit-learn) | Exact regulatory term matching |
| Retrieval fusion | Reciprocal Rank Fusion | Proven, parameter-free combination of heterogeneous rankers |
| Observability | Langfuse 2 | Agent-native tracing, cost tracking, LLM drift detection |
| Infrastructure | GCP Cloud Run + Cloud SQL | Serverless, GCP-native, managed PostgreSQL |
| IaC | Terraform | Reproducible, versioned infrastructure |
| CI/CD | GitHub Actions | Integrated with repo, supports GCP Workload Identity Federation |

---

## 3. Agent Deep Dive

### 3.1 InvestigadorAgent

**Purpose:** Pure data gathering. No LLM. Fetches all raw evidence for a fraud alert.

**Inputs (from LangGraph state):**
```python
state["alert_id"]          # UUID of the alert to investigate
state["alert_data"]["customer_id"]   # customer to look up
state["alert_data"]["is_pep"]        # flag for downstream agents
```

**Concurrent execution:**
```python
transactions, document_uris = await asyncio.gather(
    bq_tool.get_transaction_history(customer_id, days=90),
    gcs_tool.list_customer_documents(customer_id)
)
```
BigQuery and GCS calls run simultaneously — they are independent I/O operations.

**Outputs (added to state):**
```python
state["investigation"] = {
    "id": str(investigation.pk),
    "customer_id": customer_id,
    "transaction_count_90d": len(transactions),
    "total_amount_90d": sum(t["amount"] for t in transactions),
    "currencies": list of unique currencies seen,
    "countries": list of unique countries seen,
    "is_pep": alert_data["is_pep"],
    "current_alert_amount": alert_data["amount"],
    "current_alert_currency": alert_data["currency"],
    "documents_count": len(document_uris),
}
```

**Persistence:** Creates an `Investigation` record with:
- `transaction_history`: raw list of transactions (JSON)
- `documents_analyzed`: list of GCS URIs
- `structured_context`: the dict above
- `duration_seconds`: wall-clock time for this agent

**Design decisions:**
- No LLM: data gathering should be deterministic and cheap — the LLM is introduced only where judgment is required
- 90-day window: standard AML look-back; going further increases BigQuery cost without proportional signal value
- Document text is extracted but not currently stored in the investigation record — it's passed directly to the RiskAnalyzer as part of the structured context (trade-off: no re-processing, but no document text audit trail)

---

### 3.2 RiskAnalyzerAgent

**Purpose:** Assign a 1–10 risk score with regulatory justification and a human-readable summary.

**Inputs:**
```python
state["investigation"]   # structured context from InvestigadorAgent
state["alert_data"]      # original alert metadata (amount, currency, xgboost_score, etc.)
```

**LLM call:**
```
RISK_PROMPT | ChatVertexAI(temperature=0) | JsonOutputParser()
```

The prompt instructs the LLM to act as a financial crime risk analyst under UIAF/CNBV/SBS regulations and return:
```json
{
  "risk_score": 7,
  "justification": "Customer shows 12 international transfers in 90 days totaling $180,000 USD...",
  "anomalous_patterns": [
    "High transaction velocity (12 in 90 days vs. typical 3-4)",
    "Unusual corridor: Colombia → Panama → Cayman Islands"
  ],
  "human_summary": "Medium-high risk alert. Customer exhibits structuring behavior..."
}
```

**Outputs (added to state):**
```python
state["risk_analysis"] = {
    "id": str(risk_analysis.pk),
    "risk_score": 7,
    "justification": "...",
    "anomalous_patterns": [...],
    "human_summary": "...",
}
```

**Persistence:** Creates a `RiskAnalysis` record with risk score, justification, anomalous patterns, human summary, model name, and token count.

**Design decisions:**
- `JsonOutputParser` enforces structured output — the prompt explicitly instructs JSON-only responses
- `xgboost_score` from the original alert is included in the prompt context — the LLM can incorporate the existing ML signal into its reasoning
- `temperature=0` is critical here: the same investigation context must always produce the same risk score for audit trail reproducibility

---

### 3.3 DecisionAgent

**Purpose:** Make the final compliance decision: ESCALATE / DISMISS / REQUEST_INFO. Must cite specific regulations.

**Inputs:**
```python
state["alert_data"]["is_pep"]   # PEP flag
state["risk_analysis"]           # risk score + justification from RiskAnalyzerAgent
```

**Decision flow:**

```
is_pep = True?
    └── YES → ESCALATE (confidence=1.0, is_pep_override_applied=True)
               No LLM call, no RAG call
               Citations: SARLAFT CE 029/2014 Cap. IV + DCG Art. 115 LIC Disp. 31a + Res. SBS 789-2018 Art. 17
    └── NO  → HybridRetriever.retrieve(query, top_k=5)
               → format regulation chunks as context
               → DECISION_PROMPT | LLM | JsonOutputParser()
               → ESCALATE / DISMISS / REQUEST_INFO
```

**RAG query construction:**
The retrieval query combines the risk justification and the list of anomalous patterns:
```python
query = f"{risk_data['justification']} {' '.join(anomalous_patterns)}"
```
This produces a query that is semantically aligned with the actual evidence — it retrieves regulations relevant to the specific behaviors observed, not just generic AML regulations.

**LLM output (non-PEP):**
```json
{
  "decision_type": "ESCALATE",
  "confidence": 0.87,
  "regulations_cited": [
    {
      "source": "UIAF",
      "article": "Circular 002/2020 - Sección 4.2",
      "text": "Operaciones en efectivo superiores a $10,000,000 COP deben reportarse...",
      "confidence": 0.92
    }
  ],
  "step_by_step_reasoning": "1. Transaction volume (12 in 90 days) exceeds the baseline...\n2. International corridors involving Panama and Cayman Islands are flagged under...\n3. Combined with xgboost_score of 0.72, the evidence supports escalation."
}
```

**Persistence:**
- Creates a `Decision` record (decision type, confidence, citations, reasoning, PEP override flag)
- Creates an `AuditLog` record with the full input/output snapshots, duration, and token cost estimate

**Design decisions:**
- The PEP hard-rule is the most critical design decision in the system. An LLM cannot be trusted to consistently apply a binary regulatory mandate — it may weigh risk scores, transaction amounts, or other context and occasionally sub-escalate. The deterministic code path eliminates this possibility entirely.
- RAG is only invoked for non-PEP decisions. This keeps PEP escalation fast (no retrieval latency) and prevents any RAG failure mode from affecting PEP handling.
- `confidence` is the LLM's self-assessed confidence, not a calibrated probability. It is stored for audit purposes and for human analysts to prioritize their review queue.

---

## 4. RAG System

### 4.1 Retrieval Pipeline

```
Query (risk justification + anomalous patterns)
     │
     ├──► VectorStoreRetriever ──► pgvector cosine (dense, 384-dim)
     │                                         │
     ├──► SparseVectorRetriever ──► pgvector inner product (TF-IDF, 30k-dim)
     │                                         │
     └──► GraphRetriever ──► VectorStore seed (top-3) + M2M 1-hop expansion
                                               │
                         ◄────────────────────◄┘
                         Reciprocal Rank Fusion (k=60)
                         ◄────────────────────
                         Top-5 RegulationChunks
```

### 4.2 Chunking

Regulatory documents are split by a `RegulationChunker` with justified parameters:

- **Chunk size: 512 tokens** (~2,048 chars at 4 chars/token for Spanish text). Most regulatory articles fit in a single chunk — splitting mid-article would lose context.
- **Overlap: 64 tokens** (12.5%). Prevents loss of context at article boundaries — the header "Artículo 15" carries forward into the next chunk.
- **Separators (in priority order):**
  1. `"\n\nArticulo"` — split on article boundaries first
  2. `"\n\n"` — then paragraph breaks
  3. `"\n"` — then line breaks
  4. `" "` — last resort: word splits

### 4.3 Graph Layer

Cross-references between regulatory articles are stored as a self-referential M2M relationship on `RegulationDocument`. The `RegulationIndexer.link_related_articles()` method parses chunk content for patterns like `"Artículo 15"` or `"Art. 8"` and creates directed M2M edges between the referenced chunks within the same regulatory source.

At retrieval time, `GraphRetriever` fetches 3 seed documents via dense search, then traverses one hop to fetch all `related_articles` for each seed. Seed documents are scored at `SEED_WEIGHT=1.0`; their neighbors at `NEIGHBOR_WEIGHT=0.5`. This ensures the query-relevant articles rank highest while still surfacing the cross-referenced context.

### 4.4 Indexing Regulations

To add a new regulatory document:

```python
# Via Python
from compliance_agent.rag.indexer import RegulationIndexer
from compliance_agent.tools.gcs_tools import MockGCSTool

indexer = RegulationIndexer(gcs_tool=MockGCSTool())
await indexer.index_document(
    gcs_uri="gs://compliance-docs-prod/regulations/uiaf_decreto_830_2021.pdf",
    source="UIAF",
    document_ref="uiaf_decreto_830_2021"
)
```

Or in bulk (fits TF-IDF vocabulary across all documents before indexing sparse embeddings):

```python
await indexer.bulk_index(
    gcs_uris=[...],
    sources=["UIAF", "CNBV", "SBS"],
    document_refs=["uiaf_decreto_830_2021", "cnbv_dcg_art115", "sbs_resolucion_789_2018"]
)
await indexer.link_related_articles()  # builds the graph layer
```

---

## 5. Data Model

```
Alert
├── id (UUID, PK)
├── external_alert_id (unique)  ← ID from the XGBoost alert system
├── customer_id
├── is_pep (bool, indexed)
├── amount, currency
├── transaction_date
├── status: PENDING → INVESTIGATING → ESCALATED | DISMISSED | AWAITING_INFO
├── xgboost_score (float, nullable)
└── raw_payload (JSON)  ← original alert payload preserved for audit

Alert ──1:1──► Investigation
                ├── transaction_history (JSON)
                ├── documents_analyzed (JSON)
                ├── structured_context (JSON)
                └── duration_seconds

Investigation ──1:1──► RiskAnalysis
                        ├── risk_score (int, 1-10)
                        ├── justification (text)
                        ├── anomalous_patterns (JSON list)
                        ├── human_summary (text)
                        ├── model_used (str)
                        └── token_count (int)

RiskAnalysis ──1:1──► Decision
                       ├── decision_type: ESCALATE | DISMISS | REQUEST_INFO
                       ├── confidence (float)
                       ├── regulations_cited (JSON list)
                       ├── step_by_step_reasoning (text)
                       └── is_pep_override_applied (bool)

Alert ──1:N──► AuditLog
               ├── event_type
               ├── agent_name
               ├── input_snapshot (JSON)
               ├── output_snapshot (JSON)
               ├── langfuse_trace_id
               ├── duration_ms (int)
               └── token_cost_usd (Decimal 12,8)

RegulationDocument ──M:M──► RegulationDocument (related_articles, asymmetric)
├── source: UIAF | CNBV | SBS
├── document_ref
├── article_number
├── content (text)
├── embedding (vector, 384-dim)       ← dense
├── sparse_embedding (sparsevec, 30k) ← sparse
├── chunk_index (int)
└── gcs_uri
```

**Status state machine:**

```
PENDING ──► INVESTIGATING ──► ESCALATED
                           └──► DISMISSED
                           └──► AWAITING_INFO
```

`ESCALATED` → human analyst reviews → closes the alert in the source system (out of scope for this system)

---

## 6. User Interaction

### 6.1 Prerequisites

```bash
# 1. Copy and configure environment
cp backend/.env.example .env
# Edit .env: set POSTGRES_PASSWORD, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY
# For local dev, USE_MOCK_BQ=true and USE_MOCK_GCS=true are sufficient

# 2. Start services (PostgreSQL + Langfuse + API)
docker compose up

# 3. Run migrations (first time only)
make migrate
```

### 6.2 API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check — returns `{"status": "ok"}` |
| `GET` | `/readiness` | Readiness check — verifies DB connection |
| `POST` | `/api/v1/alerts/{alert_id}/investigate` | Trigger the full 3-agent pipeline for an alert |
| `GET` | `/api/v1/alerts/{alert_id}/status` | Get current alert status and metadata |
| `GET` | `/api/v1/alerts/{alert_id}/audit-trail` | Get all audit log events for an alert |

Interactive API docs: http://localhost:8000/docs (Swagger UI)

### 6.3 Typical Workflow

```
1. XGBoost model generates a fraud alert → creates Alert record in DB (status=PENDING)
2. Caller POSTs to /api/v1/alerts/{alert_id}/investigate
3. System runs InvestigadorAgent → RiskAnalyzerAgent → DecisionAgent
4. Returns decision synchronously (typical: 3-8 seconds)
5. If ESCALATED: human analyst notified via external system (out of scope)
6. Caller GETs /api/v1/alerts/{alert_id}/audit-trail for full decision trace
```

---

## 7. Examples

### 7.1 Complete Walkthrough — Non-PEP Alert

**Step 1: Trigger investigation**

```bash
curl -X POST http://localhost:8000/api/v1/alerts/550e8400-e29b-41d4-a716-446655440000/investigate \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Response (3-8 seconds):**
```json
{
  "alert_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "ESCALATE",
  "risk_analysis": {
    "risk_score": 8,
    "justification": "Customer shows 15 international transfers totaling $240,000 USD in 90 days, with 8 transfers to Panama and 4 to Cayman Islands. Transaction velocity is 4x baseline for this customer segment.",
    "anomalous_patterns": [
      "High velocity: 15 transactions in 90 days (baseline: 3-4)",
      "Unusual corridor: 12 transfers to Panama/Cayman Islands",
      "Structuring pattern: 6 transfers between $9,800 and $9,950 USD"
    ],
    "human_summary": "High-risk alert. Multiple indicators of potential structuring and international layering. Recommend immediate escalation for analyst review."
  },
  "decision": {
    "decision_type": "ESCALATE",
    "confidence": 0.91,
    "regulations_cited": [
      {
        "source": "UIAF",
        "article": "SARLAFT CE 029/2014 Num. 4.2.2 — Conocimiento del cliente",
        "text": "Operaciones fraccionadas que en conjunto superen los umbrales de reporte deben tratarse como una sola operación (estructuración). Reporte inmediato de ROS a la UIAF obligatorio.",
        "confidence": 0.94
      },
      {
        "source": "CNBV",
        "article": "DCG Art. 115 LIC — Disp. 29a Operaciones Inusuales",
        "text": "Transferencias internacionales hacia jurisdicciones de alto riesgo sin causa lícita aparente deben clasificarse como operaciones inusuales y escalarse al oficial de cumplimiento.",
        "confidence": 0.88
      }
    ],
    "step_by_step_reasoning": "1. Transaction velocity (15/90d) exceeds the structuring threshold defined in SARLAFT CE 029/2014. 2. The corridor Colombia→Panama→Cayman Islands is a known layering route per DCG Disp. 29a guidelines. 3. Six transactions between $9,800-$9,950 match the structuring pattern (fragmentation just below S/ 10,000 per-operation threshold per Res. SBS 789-2018 Art. 8). 4. Combined xgboost_score of 0.78 corroborates anomalous classification. Decision: ESCALATE with 0.91 confidence.",
    "is_pep_override_applied": false
  },
  "langfuse_trace_id": "trace_abc123def456"
}
```

**Step 2: Check status**

```bash
curl http://localhost:8000/api/v1/alerts/550e8400-e29b-41d4-a716-446655440000/status
```

```json
{
  "alert_id": "550e8400-e29b-41d4-a716-446655440000",
  "external_alert_id": "ALT-2024-00123",
  "status": "ESCALATED",
  "customer_id": "CUST-98765",
  "is_pep": false,
  "amount": 48500.00,
  "currency": "USD",
  "created_at": "2024-03-15T14:23:01Z"
}
```

**Step 3: Get audit trail**

```bash
curl http://localhost:8000/api/v1/alerts/550e8400-e29b-41d4-a716-446655440000/audit-trail
```

```json
{
  "alert_id": "550e8400-e29b-41d4-a716-446655440000",
  "events": [
    {
      "event_type": "INVESTIGATION_COMPLETED",
      "agent_name": "InvestigadorAgent",
      "duration_ms": 1240,
      "token_cost_usd": 0.0,
      "langfuse_trace_id": "trace_abc123def456",
      "created_at": "2024-03-15T14:23:02Z"
    },
    {
      "event_type": "RISK_ANALYSIS_COMPLETED",
      "agent_name": "RiskAnalyzerAgent",
      "duration_ms": 2180,
      "token_cost_usd": 0.00142,
      "langfuse_trace_id": "trace_abc123def456",
      "created_at": "2024-03-15T14:23:04Z"
    },
    {
      "event_type": "DECISION_MADE",
      "agent_name": "DecisionAgent",
      "duration_ms": 3050,
      "token_cost_usd": 0.00187,
      "langfuse_trace_id": "trace_abc123def456",
      "created_at": "2024-03-15T14:23:07Z"
    }
  ]
}
```

Total pipeline time: ~6.5 seconds. Total LLM cost: ~$0.003.

---

### 7.2 PEP Alert — Deterministic Hard-Rule

**The alert has `is_pep=true`.**

```bash
curl -X POST http://localhost:8000/api/v1/alerts/660e8400-e29b-41d4-a716-446655440001/investigate \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Response (1-2 seconds — no LLM calls):**
```json
{
  "alert_id": "660e8400-e29b-41d4-a716-446655440001",
  "status": "ESCALATE",
  "risk_analysis": {
    "risk_score": 7,
    "justification": "PEP customer with significant transaction activity...",
    "anomalous_patterns": ["PEP status requires mandatory human review"],
    "human_summary": "PEP alert. Regulatory requirement mandates escalation regardless of risk score."
  },
  "decision": {
    "decision_type": "ESCALATE",
    "confidence": 1.0,
    "regulations_cited": [
      {"source": "UIAF", "article": "SARLAFT CE 029/2014 Cap. IV — DDI",    "text": "PEPs requieren Debida Diligencia Intensificada. Ningún sistema automatizado podrá archivar alertas de clientes PEP sin revisión previa del oficial de cumplimiento.", "confidence": 1.0},
      {"source": "CNBV", "article": "DCG Art. 115 LIC — Disp. 31a PPE",   "text": "Está prohibido que sistemas automatizados archiven operaciones de PPEs sin revisión previa y expresa del oficial de cumplimiento.",                                    "confidence": 1.0},
      {"source": "SBS",  "article": "Res. SBS 789-2018 Art. 17 — DDR PEP", "text": "Escalamiento obligatorio a revisión humana de toda alerta PEP, sin excepción. Queda prohibido que los sistemas automatizados emitan decisión de archivo sobre alertas PEP.", "confidence": 1.0}
    ],
    "step_by_step_reasoning": "PEP hard-rule applied. Regulatory requirement under UIAF, CNBV, and SBS mandates human review for all PEP alerts. This decision bypasses LLM evaluation.",
    "is_pep_override_applied": true
  },
  "langfuse_trace_id": "trace_xyz789"
}
```

Key differences from non-PEP:
- `confidence = 1.0` (not LLM-estimated)
- `is_pep_override_applied = true` (stored for external auditor inspection)
- Pipeline runs in ~1.5 seconds instead of 6-8 seconds (InvestigadorAgent + RiskAnalyzer still run, but DecisionAgent returns immediately without RAG or LLM)
- All three regulators are always cited

---

### 7.3 Pipeline State at Each Stage

This is the LangGraph state dict as it flows through the pipeline:

**After InvestigadorAgent:**
```python
{
    "alert_id": "550e8400-...",
    "alert_data": {
        "customer_id": "CUST-98765",
        "is_pep": False,
        "amount": "48500.00",
        "currency": "USD",
        "transaction_date": "2024-03-15",
        "xgboost_score": 0.78,
        "external_alert_id": "ALT-2024-00123"
    },
    "investigation": {
        "id": "inv-uuid-...",
        "customer_id": "CUST-98765",
        "transaction_count_90d": 15,
        "total_amount_90d": 240000.0,
        "currencies": ["USD", "COP"],
        "countries": ["CO", "PA", "KY"],
        "is_pep": False,
        "current_alert_amount": "48500.00",
        "current_alert_currency": "USD",
        "documents_count": 3
    },
    "errors": [],
    "langfuse_trace_id": "trace_abc123def456"
}
```

**After RiskAnalyzerAgent (adds `risk_analysis`):**
```python
{
    ...,
    "risk_analysis": {
        "id": "risk-uuid-...",
        "risk_score": 8,
        "justification": "...",
        "anomalous_patterns": [...],
        "human_summary": "..."
    }
}
```

**After DecisionAgent (adds `decision`, pipeline complete):**
```python
{
    ...,
    "decision": {
        "id": "dec-uuid-...",
        "decision_type": "ESCALATE",
        "confidence": 0.91,
        "regulations_cited": [...],
        "step_by_step_reasoning": "...",
        "is_pep_override_applied": False
    }
}
```

---

### 7.4 Running Tests

```bash
# All tests with coverage gate (minimum 60%)
make test

# Unit tests only (no DB required)
make test-unit

# Integration tests (requires running PostgreSQL)
make test-integration

# Type checking
make typecheck

# Lint
make lint
```

---

### 7.5 Local Development with Docker

```bash
# Start everything
docker compose up

# In another terminal, run migrations
make migrate

# The API is now available at:
# http://localhost:8000/docs  ← Swagger UI
# http://localhost:3001       ← Langfuse dashboard (traces, costs)

# View logs
docker compose logs -f api

# Reset database
docker compose down -v && docker compose up
make migrate
```

The `docker-compose.yml` mounts `backend/compliance_agent/` and `backend/config/` as volumes, so code changes are reflected immediately without rebuilding the image.
