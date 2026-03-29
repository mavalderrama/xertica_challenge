# Compliance AI — Multi-Agent Fraud Alert Processing

> Reduces alert resolution from **4.2 hours → <30 minutes** while maintaining full regulatory audit trails for UIAF (Colombia), CNBV (Mexico), and SBS (Peru).

---

## Table of Contents

1. [Quick Start](#1-quick-start)
2. [Project Structure](#2-project-structure)
3. [Assumptions](#3-assumptions)
   - [3.1 Business & Operational](#31-business--operational)
   - [3.2 Data & Infrastructure](#32-data--infrastructure)
   - [3.3 LLM & Model Choices](#33-llm--model-choices)
   - [3.4 Regulatory](#34-regulatory)
   - [3.5 Architecture](#35-architecture)
4. [Architecture Overview](#4-architecture-overview)
   - [4.1 System Diagram](#41-system-diagram)
   - [4.2 Agent Summary](#42-agent-summary)
   - [4.3 Layer Responsibilities](#43-layer-responsibilities)
   - [4.4 Technology Stack](#44-technology-stack)
5. [Agent Deep Dive](#5-agent-deep-dive)
   - [5.1 InvestigadorAgent](#51-investigadoragent)
   - [5.2 RiskAnalyzerAgent](#52-riskanalyzeragent)
   - [5.3 DecisionAgent](#53-decisionagent)
   - [5.4 Observability: End-to-End Audit Trail](#54-observability-end-to-end-audit-trail)
   - [5.5 LLM-as-Judge: Decision Quality Evaluation](#55-llm-as-judge-decision-quality-evaluation)
6. [LLM Provider: OpenAI (Development) → Vertex AI (Production)](#6-llm-provider-openai-development--vertex-ai-production)
7. [RAG System](#7-rag-system)
   - [7.1 The Problem: Why a Single Retriever Fails](#71-the-problem-why-a-single-retriever-fails)
   - [7.2 Retrieval Pipeline](#72-retrieval-pipeline)
   - [7.3 Dense Retriever](#73-dense-retriever)
   - [7.4 Sparse Retriever](#74-sparse-retriever)
   - [7.5 Graph Retriever](#75-graph-retriever)
   - [7.6 How RRF Fuses the Rankings](#76-how-rrf-fuses-the-rankings)
   - [7.7 Chunking Strategy](#77-chunking-strategy)
   - [7.8 Graph Layer Infrastructure Choice](#78-graph-layer-infrastructure-choice)
   - [7.9 RAG Quality Metrics](#79-rag-quality-metrics)
   - [7.10 Evaluation Framework: RAGAS vs DeepEval vs Custom](#710-evaluation-framework-ragas-vs-deepeval-vs-custom)
   - [7.11 Indexing Regulations](#711-indexing-regulations)
8. [Data Model](#8-data-model)
9. [User Interaction & API](#9-user-interaction--api)
   - [9.1 API Endpoints](#91-api-endpoints)
   - [9.2 Typical Workflow](#92-typical-workflow)
10. [Pregunta Abierta — Sistema en Producción](#10-pregunta-abierta--sistema-en-producción)
11. [Examples](#11-examples)
    - [11.1 Complete Walkthrough — Non-PEP Alert](#111-complete-walkthrough--non-pep-alert)
    - [11.2 PEP Alert — Deterministic Hard-Rule](#112-pep-alert--deterministic-hard-rule)
    - [11.3 Pipeline State at Each Stage](#113-pipeline-state-at-each-stage)
    - [11.4 Running Tests](#114-running-tests)
    - [11.5 Local Development with Docker](#115-local-development-with-docker)
12. [Infrastructure](#12-infrastructure)
13. [Observability](#13-observability)
14. [Mi Flujo con AI](#14-mi-flujo-con-ai)
15. [Deliverables](#15-deliverables)

---

## 1. Quick Start

```bash
# 1. Copy environment config
cp backend/.env.example backend/.env
# Edit backend/.env: set OPENAI_API_KEY (or LLM_PROVIDER=vertexai + GCP credentials)

# 2. Start all services (PostgreSQL + pgvector, Langfuse, API)
docker compose up

# 3. Run migrations, seed 30 test scenarios, index 5 regulatory documents
make populate

# 4. Run tests (83 tests, 60% coverage gate)
make test
```

---

## 2. Project Structure

```
.
├── backend/
│   ├── compliance_agent/
│   │   ├── agents/                   # 3 specialized agents
│   │   │   ├── investigador.py       # Agent 1: BQ + GCS concurrent context builder
│   │   │   ├── risk_analyzer.py      # Agent 2: LLM risk scoring (1-10 + justification)
│   │   │   └── decision_agent.py     # Agent 3: PEP hard-rule + hybrid RAG decision
│   │   ├── api/                      # FastAPI layer with dependency injection
│   │   │   ├── main.py
│   │   │   ├── dependencies.py       # LLM_PROVIDER switch: OpenAI ↔ Vertex AI
│   │   │   ├── routers/              # /alerts/{id}/investigate, /status, /audit-trail
│   │   │   └── schemas/
│   │   ├── graph/                    # LangGraph pipeline orchestration
│   │   │   ├── pipeline.py           # START → investigador → risk_analyzer → decision → END
│   │   │   └── state.py              # PipelineState TypedDict
│   │   ├── models/                   # Django ORM (Alert, Investigation, RiskAnalysis,
│   │   │   │                         #   Decision, AuditLog, RegulationDocument)
│   │   ├── rag/                      # Hybrid retrieval system
│   │   │   ├── hybrid_retriever.py   # RRF fusion: dense + sparse + graph
│   │   │   ├── vector_store.py       # pgvector cosine (all-MiniLM-L6-v2, 384-dim)
│   │   │   ├── sparse_retriever.py   # PostgreSQL tsvector/tsquery (Spanish, BM25-equiv)
│   │   │   ├── graph_retriever.py    # Django M2M 1-hop expansion (related_articles)
│   │   │   ├── chunking.py           # Article-boundary-aware splitter (512t / 64t overlap)
│   │   │   ├── indexer.py            # Bulk index + cross-reference graph builder
│   │   │   └── embeddings.py         # HFEmbedder (lazy-loaded, batch support)
│   │   ├── repositories/             # Repository pattern for all 5 models
│   │   ├── services/                 # AuditService, PipelineService
│   │   ├── tools/                    # BigQueryTool + GCSTool (real + mock variants)
│   │   ├── observability/            # Langfuse tracing config + cost estimation
│   │   └── management/commands/      # seed_data (30 scenarios), index_regulations
│   ├── config/settings/              # Django settings (base, local, production)
│   ├── tests/                        # 83 tests (unit + integration)
│   │   ├── unit/agents/              # 8 tests: investigador, risk_analyzer, decision_agent
│   │   ├── unit/rag/                 # 22 tests: chunking, embeddings, retrievers
│   │   ├── unit/tools/               # 7 tests: BigQuery + GCS mocks
│   │   ├── integration/              # 5 tests: full pipeline + API endpoints
│   │   └── fixtures/regulatory_docs/ # 5 regulatory documents (UIAF, CNBV, SBS)
│   ├── Dockerfile
│   └── pyproject.toml
├── terraform/                        # GCP IaC (4 modules)
│   ├── main.tf / variables.tf / outputs.tf / versions.tf
│   └── modules/                      # cloud_run, cloud_sql, gcs, iam
├── .github/workflows/
│   ├── ci.yml                        # Lint + test (60% coverage gate enforced)
│   └── deploy.yml                    # Build → Artifact Registry → Cloud Run
├── notebooks/
│   └── rag_evaluation.ipynb          # RAG metrics evaluation + framework justification
├── scripts/
│   ├── live_test.sh                  # 30-scenario end-to-end test runner
│   ├── llm_judge.py                  # LLM-as-Judge evaluator (4 scoring dimensions)
│   └── live_test_render.py           # Visual pipeline workflow renderer
├── docs/
│   ├── cto_document.md               # 2-page CTO/CFO business case
│   └── live_testing.md               # Full scenario table + test guide
├── docker-compose.yml                # PostgreSQL 18 + pgvector, Langfuse, API
├── Makefile                          # All dev commands (migrate, seed, test, live-test)
└── README.md
```

---

## 3. Assumptions

> Per the challenge brief: *"Tienes dudas sobre el escenario del cliente? Anótalas y documenta tus supuestos."*

### 3.1 Business & Operational

| Assumption | Basis | Impact |
|---|---|---|
| Alert volume: ~2,000/month | Stated implicitly in challenge cost model ($24/alert × 8 analysts) | Used to size infrastructure (Cloud Run min=1/max=10, Cloud SQL `db-g1-small`) |
| False positive rate: 68% | Challenge description | Informs the expected DISMISS rate; the system should dismiss ~1,360 alerts/month without human review |
| 8 compliance analysts today | CTO document cost model | Baseline for ROI calculation — the system replaces 6 of these with automated triage |
| Resolution target: <30 min | Challenge requirement | Pipeline must complete p95 in <30s; human review of escalated alerts is the remaining time |
| Three regulatory jurisdictions | Challenge requirement: UIAF (Colombia), CNBV (Mexico), SBS (Peru) | All three corpora are indexed in the RAG vector store; the Decision Agent cites articles from whichever is applicable |
| Human-in-the-loop for escalations | Challenge requirement and regulatory mandate | The system outputs ESCALATE/DISMISS/REQUEST_INFO; only DISMISS closes the alert automatically |

### 3.2 Data & Infrastructure

**BigQuery transaction history**
- Assumed structure: one row per transaction, columns include `customer_id`, `transaction_id`, `amount`, `currency`, `country`, `transaction_type`, `transaction_date`
- Query window: last 90 days. The challenge says "3 years of history" — we query 90 days because that is the standard AML look-back window for alert-level investigation. 3 years of history is used for model training (the XGBoost model), not per-alert investigation.
- Table name assumed: `{project_id}.compliance.transactions`

**GCS document store**
- Assumed structure: `customers/{customer_id}/*.pdf`
- Documents represent KYC artifacts (account opening forms, identity verification, PEP screening results)
- PDF text extraction via `pypdf` — assumes text-layer PDFs, not scanned images (OCR not implemented)

**XGBoost model**
- We consume its output (`xgboost_score`, a float 0–1) as a feature in risk analysis context
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

### 3.3 LLM & Model Choices

**ChatGPT Model**
- Chosen over Gemini models because it is the current api key that I have access to, can be changed as needed as env var.
- Price assumption: \$0.000075/1K input tokens, \$0.0003/1K output tokens → ~$0.003/alert at typical prompt lengths, can be changed as needed as env var.
- `temperature=0`: compliance decisions must be deterministic and reproducible. The same alert inputs must always produce the same output — non-zero temperature would make the audit trail non-reproducible.
- Structured output via `JsonOutputParser` — the LLM is instructed to return strict JSON; if parsing fails, the error is captured in `state["errors"]`

**Embeddings: `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions)**
- Trade-off: not the most accurate multilingual model, but fast (runs on CPU), well-supported, and produces normalized vectors suitable for cosine similarity
- Assumption: regulatory Spanish is structurally regular enough that a general-purpose multilingual model captures semantic similarity adequately
- Alternative considered: `text-multilingual-embedding-002` (Vertex AI) — rejected for local dev complexity and cost; can be swapped via the `IRetriever` interface if needed

**Graph retrieval via Django M2M (not Neo4j/FalkorDB)**
- The challenge suggests Neo4j or FalkorDB for the graph layer
- Decision to use Django M2M `related_articles` self-referential field instead:
  - No additional infrastructure component to manage, deploy, or secure
  - For 1-hop traversal (which is all that's needed to link cross-referenced articles within a single regulatory document), a relational adjacency list is equivalent to a graph database
  - Trade-off: deeper graph traversal (2-hop, 3-hop) would require recursive SQL or Cypher; the current implementation only does 1-hop. This is sufficient given that regulatory cross-references are typically direct citations, not multi-hop chains.
  - Can be replaced with a real graph database by implementing a new `IRetriever` — the interface is already defined

### 3.4 Regulatory

| Assumption | Regulation | Implementation |
|---|---|---|
| PEP escalation is mandatory, no exceptions | SARLAFT CE 029/2014 Cap. IV (Colombia); DCG Art. 115 LIC Disp. 31a (Mexico); Res. SBS 789-2018 Art. 17 (Peru) | Deterministic hard-rule in `DecisionAgent` — runs before any LLM call, cannot be overridden by risk score |
| Audit trail must be human-readable | Challenge requirement, UIAF/CNBV/SBS reporting obligations | Every decision stores `step_by_step_reasoning` (plain text) and `regulations_cited` (structured list) in the database |
| Record retention: 10 years | Colombia: 10 years (Ley 526/1999 Art. 10); Mexico: 10 years (DCG Disp. 38a); Peru: 10 years (Ley 27693) | Not enforced in code yet — a database archival policy (Cloud SQL scheduled exports to GCS) should implement this in production |
| Reporting deadlines | Colombia: ROS inmediato (≤24h); Mexico: ROI 60 días naturales + 3 días hábiles para presentar; Peru: ROS inmediato tras decisión | The system surfaces the decision immediately but does not auto-file SAR reports — a human analyst does that after reviewing escalated alerts |
| "La IA lo decidió" is not a valid justification | Challenge regulatory constraint | Every LLM decision includes `step_by_step_reasoning` with explicit references to retrieved regulation chunks |

### 3.5 Architecture

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

## 4. Architecture Overview

### 4.1 System Diagram

```
                         ┌─────────────────────┐
                         │   LLM Judge         │  (offline)
                         │  llm_judge.py       │
                         │  4-dim evaluation   │◄── judge_report_*.md
                         │  prompt calibration │
                         └──────────┬──────────┘
                                    │ feedback → prompts
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          External Caller                             │
│                    (compliance analyst system / CRM)                 │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  POST /api/v1/alerts/{id}/investigate
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         FastAPI (uvicorn)                            │
│    /health    /readiness    /api/v1/alerts/*                         │
│    alerts.router                                                     │
│    → tracer.create_trace_id() → langfuse_trace_id                   │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  langfuse_trace_id flows through state
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        PipelineService                               │
│   1. load Alert from DB                                             │
│   2. build initial LangGraph state (with langfuse_trace_id)         │
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
│ GCS        ◄┤    │ RISK_PROMPT*   │   │ [else] → HybridRetriever    │
│             │    │ (calibrated)   │   │          + DECISION_PROMPT*  │
│ → saves     │    │ → saves        │   │          (calibrated)        │
│  Investigation   │  RiskAnalysis  │   │ → saves Decision            │
│ → AuditLog ─┤    │ → AuditLog ────┤   │ → AuditLog ─────────────────┤
│  (duration) │    │ (duration+cost)│   │   (duration+cost)           │
└─────────────┘    └────────────────┘   └─────────────────────────────┘
       │                    │                  │
       └────────────────────┴──────────────────┘
                            │ all agents share langfuse_trace_id
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│               PostgreSQL + pgvector (Django ORM)                     │
│                                                                     │
│  Alert ──1:1──► Investigation ──1:1──► RiskAnalysis ──1:1──► Decision│
│  Alert ──1:N──► AuditLog (INVESTIGATION, RISK_ANALYSIS, DECISION)   │
│                 [langfuse_trace_id, duration_ms, token_cost_usd]    │
│  RegulationDocument ──M:M──► RegulationDocument (graph)            │
└─────────────────────────────────────────────────────────────────────┘

* RISK_PROMPT and DECISION_PROMPT calibrated by LLM Judge feedback loop
```

### 4.2 Agent Summary

Three agents run in a LangGraph pipeline:

1. **InvestigadorAgent** — Fetches 90-day transaction history from BigQuery and customer documents from GCS concurrently via `asyncio.gather()`. Parses KYC fields from documents and builds `structured_context`.
2. **RiskAnalyzerAgent** — Calls the LLM with a structured prompt (XGBoost calibration bands, multi-currency thresholds) to assign a 1–10 risk score with regulatory justification.
3. **DecisionAgent** — Applies a **PEP hard-rule first** (deterministic, no LLM) then uses hybrid RAG to cite specific regulations for non-PEP decisions.

Every decision produces an `AuditLog` entry (event_type: `INVESTIGATION` / `RISK_ANALYSIS` / `DECISION`) with `duration_ms`, `token_cost_usd`, and `langfuse_trace_id` — satisfying regulatory audit trail requirements.

A **30-scenario live test suite** (`make live-test`) covers DISMISS, ESCALATE, and REQUEST_INFO paths across all three currencies (COP/MXN/PEN/USD), PEP hard-rule variants, structuring patterns, money mule detection, identity changes, income gaps, FATF high-risk wires, and two extreme edge cases (Ghost Probe: critical ML signal on trivial amount; PEP Phantom: PEP hard-rule against every other signal). See `docs/live_testing.md` for the full scenario table.

### 4.3 Layer Responsibilities

| Layer | Component | Responsibility |
|---|---|---|
| HTTP | FastAPI routers | Parse requests, serialize responses, dependency injection; creates Langfuse trace ID |
| Service | `PipelineService` | Orchestrates the full alert lifecycle; only place that updates `Alert.status` |
| Graph | LangGraph `StateGraph` | Routes state between agents; propagates `langfuse_trace_id` through all nodes |
| Agents | `InvestigadorAgent`, `RiskAnalyzerAgent`, `DecisionAgent` | Domain logic for each stage; each writes an `AuditLog` entry via `AuditService` |
| Tools | `BigQueryTool`, `GCSTool` (real or mock) | External data access; swappable via `BigQueryToolInterface` / `GCSToolInterface` |
| RAG | `HybridRetriever`, `VectorStoreRetriever`, `SparseVectorRetriever`, `GraphRetriever` | Regulatory document retrieval for the Decision Agent |
| Persistence | 5 repository implementations | Async Django ORM operations; all behind interfaces |
| Observability | `LangfuseTracer`, `AuditService`, `AuditLog` model | Distributed tracing + full regulatory audit trail (trace ID, duration, cost per agent) |
| Evaluation | `scripts/llm_judge.py` (offline) | LLM-as-Judge: 4-dimension scoring, critical failure detection, markdown report; drives prompt calibration |

### 4.4 Technology Stack

| Component | Technology                                    | Why |
|---|-----------------------------------------------|---|
| HTTP framework | FastAPI                                       | Async-native, OpenAPI docs, Pydantic validation |
| ORM & migrations | Django 6 + psycopg3                           | Mature migration tooling, async ORM, pgvector integration |
| Agent orchestration | LangGraph 0.5                                 | Stateful graph execution, built-in streaming and replay |
| LLM | Gemini 2.0 Flash (Vertex AI) / OpenAI ChatGPT | Cost-effective, deterministic at temp=0, GCP-native (data residency) |
| Vector store | PostgreSQL 18 + pgvector                      | Single DB for relational + vector data; no extra service |
| Dense embeddings | all-MiniLM-L6-v2                              | Fast, CPU-runnable, multilingual, 384-dim |
| Sparse embeddings | PostgreSQL tsvector/tsquery                   | Exact regulatory term matching, native to the DB |
| Retrieval fusion | Reciprocal Rank Fusion                        | Proven, parameter-free combination of heterogeneous rankers |
| Observability | Langfuse 2                                    | Agent-native tracing, cost tracking, LLM drift detection |
| Infrastructure | GCP Cloud Run + Cloud SQL                     | Serverless, GCP-native, managed PostgreSQL |
| IaC | Terraform                                     | Reproducible, versioned infrastructure |
| CI/CD | GitHub Actions                                | Integrated with repo, supports GCP Workload Identity Federation |

---

## 5. Agent Deep Dive

### 5.1 InvestigadorAgent

**Purpose:** Pure data gathering. No LLM. Fetches all raw evidence for a fraud alert.

**Inputs (from LangGraph state):**
```python
state["alert_id"]                    # UUID of the alert to investigate
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
    "customer_profile": parsed KYC fields dict,  # account_opened, risk_category, etc.
}
```

**Persistence:**
1. Creates an `Investigation` record with:
   - `transaction_history`: raw list of transactions (JSON)
   - `documents_analyzed`: list of GCS URIs + extracted text
   - `structured_context`: the dict above
   - `duration_seconds`: wall-clock time for this agent

2. Writes an `AuditLog` entry via injected `AuditService`:
   - `event_type`: `"INVESTIGATION"`
   - `duration_ms`: wall-clock time in milliseconds
   - `token_cost_usd`: `0.0` (no LLM call)
   - `langfuse_trace_id`: propagated from `state["langfuse_trace_id"]`

**Design decisions:**
- No LLM: data gathering should be deterministic and cheap — the LLM is introduced only where judgment is required
- `audit_service` is injected as `Any` (not typed to `AuditService`) to avoid circular imports between the `agents` and `services` packages
- 90-day window: standard AML look-back; going further increases BigQuery cost without proportional signal value
- `customer_profile` is parsed from document text by `_extract_customer_profile()` and included in `structured_context` so downstream LLMs see KYC data (risk category, declared income, prior alerts, compliance notes) without receiving raw PDF bytes

---

### 5.2 RiskAnalyzerAgent

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

The prompt instructs the LLM to act as a financial crime risk analyst under UIAF/CNBV/SBS regulations. **RISK_PROMPT calibration** (iterated via LLM Judge feedback):

| Guidance block | Content | Why it was added |
|---|---|---|
| XGBoost interpretation | 0.00–0.30=LOW, 0.31–0.64=MEDIUM, 0.65–0.79=HIGH, 0.80–1.00=CRITICAL | Judge found low-xgb alerts being over-scored without this |
| Currency exchange rates | COP≈4,100/USD, MXN≈17/USD, PEN≈3.7/USD | 3.5M COP ≈ $850 USD — LLM needs this to assess materiality |
| Regulatory thresholds | SARLAFT COP 10M, CNBV USD 7,500, SBS PEN 10,000 | Below-threshold amounts were inflating scores |
| Multi-currency nuance | 3-4 currencies normal for LatAm retail | Mock data generates multi-currency for all customers; without this context the LLM flags it as suspicious |
| Score calibration guide | 1–3 (xgb<0.40, below threshold), 4–6 (medium xgb, borderline), 5–7 (borderline-high, profile changes), 7–8 (high xgb, above threshold), 9–10 (xgb≥0.80, structuring) | Prevents score drift without concrete anchors |

**Inputs passed to chain:**
```python
{
    "structured_context": str(investigation_data),
    "amount": alert_data["amount"],
    "currency": alert_data["currency"],
    "is_pep": alert_data["is_pep"],
    "xgboost_score": alert_data["xgboost_score"],
    "alert_type": raw_payload.get("alert_type"),   # e.g. "STRUCTURING_PATTERN"
    "segment": raw_payload.get("segment"),          # e.g. "retail_individual"
    "tx_count": investigation["transaction_count_90d"],
    "total_amount": investigation["total_amount_90d"],
    "countries": investigation["countries"],
    "currencies": investigation["currencies"],
}
```

**LLM output:**
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

**Persistence:**
1. Creates a `RiskAnalysis` record with risk score, justification, anomalous patterns, human summary, model name, and token count.
2. Writes an `AuditLog` entry via `AuditService`:
   - `event_type`: `"RISK_ANALYSIS"`
   - `duration_ms`: wall-clock time in milliseconds
   - `token_cost_usd`: computed via `estimate_cost(input_tokens, output_tokens)` using Gemini Flash pricing
   - `langfuse_trace_id`: from `state["langfuse_trace_id"]`

**Design decisions:**
- `JsonOutputParser` enforces structured output — the prompt explicitly instructs JSON-only responses
- `temperature=0` is critical here: the same investigation context must always produce the same risk score for audit trail reproducibility
- Calibration is iterative: the LLM Judge evaluates each run and its `risk_score_accuracy` dimension directly feeds back into RISK_PROMPT refinements

---

### 5.3 DecisionAgent

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

**DECISION_PROMPT calibration** (iterated via LLM Judge feedback):

| Guidance block | Content | Why it was added |
|---|---|---|
| Explicit DISMISS criteria | risk ≤ 4 AND non-PEP AND below threshold AND no severe patterns | Without this, LLMs default to conservatism and over-escalate low-risk alerts |
| Explicit REQUEST_INFO criteria | risk 5–7, borderline xgb (0.55–0.70), ambiguous factors (new account, identity change, income mismatch) | Prevents REQUEST_INFO being used as a fallback for all mid-range scores |
| Explicit ESCALATE criteria | risk ≥ 8 OR confirmed structuring OR sanction match OR amount >5× threshold with high xgb | Bounds escalation to actual high-risk signals, not general uncertainty |
| Regulatory thresholds | Same as RISK_PROMPT (COP 10M, USD 7,500, PEN 10,000) | Enables threshold-relative amount assessment in decision |
| XGBoost context | 0.00–0.30=LOW, etc. | Decision agent sees ML signal directly, not just the LLM-interpreted risk score |
| Anti-over-escalation | "Dismissing low-risk alerts is correct and expected" | Counteracts LLM conservatism bias in compliance domains |

**LLM output (non-PEP):**
```json
{
  "decision_type": "ESCALATE",
  "confidence": 0.87,
  "regulations_cited": [
    {
      "source": "UIAF",
      "article": "SARLAFT CE 029/2014 Num. 4.2.3 — Reporte de Operaciones Sospechosas",
      "text": "Transacciones en múltiples monedas extranjeras en períodos cortos sin justificación...",
      "confidence": 0.92
    }
  ],
  "step_by_step_reasoning": "1. Transaction volume exceeds structuring threshold...\n2. International corridors involving Panama and Cayman Islands are flagged under...\n3. Combined with xgboost_score of 0.72, the evidence supports escalation."
}
```

**Persistence:**
1. Creates a `Decision` record (decision type, confidence, citations, reasoning, PEP override flag).
2. Writes an `AuditLog` entry via `AuditService`:
   - `event_type`: `"DECISION"`
   - `duration_ms`: wall-clock time (includes RAG + LLM for non-PEP; near-zero for PEP hard-rule)
   - `token_cost_usd`: `estimate_cost(input, output)` for non-PEP; `0.0` for PEP hard-rule
   - `langfuse_trace_id`: from `state["langfuse_trace_id"]`

**Design decisions:**
- The PEP hard-rule is the most critical design decision in the system. An LLM cannot be trusted to consistently apply a binary regulatory mandate — it may weigh risk scores, transaction amounts, or other context and occasionally sub-escalate. The deterministic code path eliminates this possibility entirely.
- RAG is only invoked for non-PEP decisions. This keeps PEP escalation fast (no retrieval latency) and prevents any RAG failure mode from affecting PEP handling.
- `confidence` is the LLM's self-assessed confidence, not a calibrated probability. It is stored for audit purposes and for human analysts to prioritize their review queue.

---

### 5.4 Observability: End-to-End Audit Trail

Every pipeline run produces a complete, linked audit trail satisfying UIAF/CNBV/SBS regulatory reporting requirements.

**Trace creation (API layer):**
```python
# compliance_agent/api/routers/alerts.py
trace_id = tracer.create_trace_id("investigate_alert", {"alert_id": alert_id})
final_state = await pipeline_service.process_alert(alert_id, langfuse_trace_id=trace_id)
```
`create_trace_id()` uses the Langfuse v3 API to generate a 32-char hex trace ID. If Langfuse is unavailable, it returns `""` — the pipeline continues unaffected.

**Trace propagation:**
The `trace_id` enters `PipelineState["langfuse_trace_id"]` and is forwarded unchanged through all three agents. No agent needs to know about Langfuse — they receive and forward the string via the state dict.

**Per-agent audit log writes (via `AuditService.log_agent_event()`):**

| Agent | `event_type` | `duration_ms` | `token_cost_usd` |
|---|---|---|---|
| `InvestigadorAgent` | `INVESTIGATION` | BQ + GCS wall-clock time | `0.0` (no LLM) |
| `RiskAnalyzerAgent` | `RISK_ANALYSIS` | LLM call wall-clock time | `estimate_cost(input, output)` |
| `DecisionAgent` (non-PEP) | `DECISION` | RAG + LLM wall-clock time | `estimate_cost(input, output)` |
| `DecisionAgent` (PEP) | `DECISION` | Hard-rule only (near-zero) | `0.0` |

**Cost estimation:**
```python
# compliance_agent/observability/langfuse_config.py
GEMINI_FLASH_INPUT_COST_PER_1K  = 0.000075  # USD/1K input tokens
GEMINI_FLASH_OUTPUT_COST_PER_1K = 0.0003    # USD/1K output tokens

def estimate_cost(input_tokens: int, output_tokens: int) -> float: ...
```

**Retrieving the audit trail:**
```bash
curl http://localhost:8000/api/v1/alerts/{alert_id}/audit-trail
```
Returns 3 events with `langfuse_trace_id`, `duration_ms`, and `token_cost_usd` all populated. See [section 11.1](#111-complete-walkthrough--non-pep-alert) for a complete example.

---

### 5.5 LLM-as-Judge: Decision Quality Evaluation

`scripts/llm_judge.py` is an offline evaluation component that scores pipeline decisions against the regulatory corpus and drives iterative prompt calibration.

**How it runs:**
```bash
make live-test-judge   # runs all 30 scenarios, then evaluates with the judge
```

**Evaluation dimensions (each scored 1–5):**

| Dimension | What it measures |
|---|---|
| `decision_correctness` | Is ESCALATE/DISMISS/REQUEST_INFO the right call for this alert profile? |
| `regulatory_compliance` | Are cited regulations correct, relevant, and complete? |
| `reasoning_quality` | Is the step-by-step reasoning logically sound and evidence-based? |
| `risk_score_accuracy` | Is the 1–10 risk score properly calibrated to the scenario? |

**Critical failure detection:** The judge flags `critical_failure=true` if:
- A PEP alert is not escalated (direct regulatory violation)
- Decision is DISMISS when `risk_score ≥ 8`
- A mandatory reporting threshold breach is dismissed without justification

**Output:**
- Terminal: color-coded table with per-scenario scores + detailed findings
- File: `judge_report_YYYYMMDD_HHMMSS.md` at the repo root — full untruncated report with all fields, regulations cited, reasoning, and judge explanations

**Calibration feedback loop:**

```
run live-test-judge
      │
      ▼
 judge scores + critical failures
      │
      ▼
 identify miscalibrated scenarios
 (e.g. scenario 1: ESCALATE instead of DISMISS)
      │
      ▼
 trace root cause in RISK_PROMPT or DECISION_PROMPT
 (e.g. missing xgboost interpretation, no DISMISS criteria)
      │
      ▼
 update prompt in risk_analyzer.py / decision_agent.py
      │
      ▼
 re-run live-test-judge → verify scores improved
```

**Concrete example from this project:**

| Scenario | Before calibration | After calibration | Root cause fixed |
|---|---|---|---|
| 1 (COP 3.5M, xgb=0.31) | ESCALATE | DISMISS | Added xgboost bands + currency context to RISK_PROMPT |
| 8 (MXN 8.5K, xgb=0.22) | ESCALATE | DISMISS | Same; plus below-threshold context |
| 5 (PEN 18.5K, xgb=0.61) | ESCALATE | REQUEST_INFO | Shifted xgb HIGH threshold 0.60→0.65; expanded REQUEST_INFO criteria to risk 5–7 |

The judge acts as a continuous quality gate: any regression in prompt behavior is detectable before deployment by comparing judge scores across runs.

---

## 6. LLM Provider: OpenAI (Development) → Vertex AI (Production)

The challenge recommends Vertex AI (Gemini) and explicitly says to *"justificar si usas otra opción"*. Here is that justification.

**Why OpenAI is used here:** `gpt-5-mini-2025-08-07` via `langchain-openai` is used throughout this assessment because it is the only LLM API key currently available. This is a pragmatic development-time choice, not an architectural decision.

**The architecture is fully provider-agnostic.** The `LLM_PROVIDER` environment variable in `backend/compliance_agent/api/dependencies.py` selects the backend at startup:

```python
# dependencies.py — provider switch
if provider == "openai":
    llm = ChatOpenAI(model=os.environ.get("OPENAI_MODEL", "gpt-5-mini-2025-08-07"), ...)
else:
    llm = ChatVertexAI(model=os.environ.get("GEMINI_MODEL", "gemini-2.0-flash-001"), ...)
```

Both `langchain-openai` and `langchain-google-vertexai` are listed as production dependencies in `pyproject.toml`. All three agents receive the LLM via constructor injection — there is zero provider-specific code anywhere in agent logic. The same prompts, structured output schemas, and LCEL chains work identically with either backend.

**Production target: Gemini 2.0 Flash on Vertex AI (`us-central1`).** This satisfies the critical GCP data-residency constraint (no customer data sent to external APIs). The `.env.example` and all architecture documents reference `gemini-2.0-flash-001` as the production model. The CTO cost model is built on Gemini Flash pricing ($0.000075/1K input tokens).

**To switch to Vertex AI (no code changes required):**

```bash
# In backend/.env
LLM_PROVIDER=vertexai
GEMINI_MODEL=gemini-2.0-flash-001
GCP_PROJECT_ID=your-project
GCP_LOCATION=us-central1
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```

---

## 7. RAG System

### 7.1 The Problem: Why a Single Retriever Fails for Regulatory Compliance

Regulatory documents present a retrieval challenge that no single method handles well:

- **Semantic queries** ("What applies to a PEP international transfer?") need *meaning*-based search — dense embeddings excel here but miss exact legal identifiers.
- **Exact-term queries** ("Disposición 31a", "DCG Art. 115 LIC", "Resolución SBS 789-2018") need *literal string matching* — dense embeddings collapse these distinct legal references into similar vectors, returning the wrong article. Sparse (BM25) search matches them exactly.
- **Multi-article queries** ("What are all the rules for $50K USD from a legal entity?") need context that spans *related* articles across a regulation — neither dense nor sparse retrieval knows that Art. 15 references Art. 8 in the same SBS resolution.

Each retriever solves one failure mode but introduces another. **Hybrid retrieval via RRF solves all three simultaneously.**

### 7.2 Retrieval Pipeline

```
Query: "risk justification text + anomalous patterns list"
     │
     │ (asyncio.gather — all three run in parallel)
     │
     ├──► VectorStoreRetriever
     │    pgvector CosineDistance(embedding, query_embedding)
     │    "What does this query MEAN?" → semantic recall
     │    File: rag/vector_store.py
     │
     ├──► SparseVectorRetriever
     │    SearchQuery(query, config="spanish") → SearchRank(search_vector)
     │    "What EXACT TERMS appear?" → lexical precision
     │    File: rag/sparse_retriever.py
     │
     └──► GraphRetriever
          Step 1: VectorStoreRetriever.retrieve(query, seed_top_k=3)
          Step 2: for each seed → doc.related_articles.all() [1-hop M2M]
          Step 3: seed.score × 1.0 (SEED_WEIGHT)
                  neighbor.score = 0.5 (NEIGHBOR_WEIGHT)
          "What is LINKED to the best matches?" → cross-referenced articles
          File: rag/graph_retriever.py
               │
               ▼
     HybridRetriever.retrieve()
     ─────────────────────────────────────────────────────
     For each (document_ref, chunk_index) key:
       rrf_score += 1.0 / (60 + rank + 1)  per retriever that ranked it
     ─────────────────────────────────────────────────────
     Sort by rrf_score descending → top_k=5
     File: rag/hybrid_retriever.py
               │
               ▼
     Top-5 RegulationChunks → DecisionAgent context
```

### 7.3 Dense Retriever

**File:** `rag/vector_store.py`

```python
# At query time:
query_embedding = self.embedder.embed_single(query)   # 384-dim float array
RegulationDocument.objects
    .annotate(distance=CosineDistance("embedding", query_embedding))
    .order_by("distance")[:top_k]
```

- **Model:** `sentence-transformers/all-MiniLM-L6-v2` — 384 dimensions, runs on CPU, lazy-loaded singleton to avoid repeated model initialization across requests.
- **Why cosine (not dot product):** All embeddings are L2-normalized at index time, so cosine similarity == dot product == Euclidean distance (monotonically). Cosine makes the score scale-invariant to document length.
- **What it catches:** "Politically exposed persons must be escalated" matches "Personas políticamente expuestas — escalamiento obligatorio" without exact word overlap. Paraphrased queries, multilingual variance, synonyms.
- **What it misses:** Two articles with nearly identical vocabulary but different legal meaning (e.g., Art. 14 and Art. 15 of the same resolution) may have very close embeddings. "DCG Art. 115" and "DCG Art. 116" are nearly indistinguishable semantically.

### 7.4 Sparse Retriever

**File:** `rag/sparse_retriever.py`

```python
search_query = SearchQuery(query, config="spanish", search_type="websearch")
RegulationDocument.objects
    .filter(search_vector=search_query)
    .annotate(rank=SearchRank("search_vector", search_query))
    .order_by("-rank")[:top_k]
```

- **Implementation:** PostgreSQL native full-text search. `search_vector` is a pre-indexed `tsvector` field populated at index time. At retrieval time, the query is converted to `tsquery` and matched against the index — no model inference required at query time.
- **Language config `"spanish"`:** Applies Spanish stemming (e.g., "transferencia" → "transfer", "obligatorias" → "obligatori") and removes Spanish stopwords. This lets "transferencia internacional" match "transferencias internacionales".
- **`search_type="websearch"`:** Converts multi-word queries into AND operators (all terms must appear), without requiring manual boolean syntax.
- **What it catches:** Exact regulatory identifiers — "SARLAFT", "Resolución SBS 789-2018", "Ley 27693", "DCG Art. 115 LIC Disp. 31a". These are proper nouns that appear verbatim in regulations. Dense embeddings fail here because proper nouns are rare in general training corpora.
- **What it misses:** Conceptual queries. "What must happen when a politically exposed person triggers an alert?" has very low term overlap with regulation text.

### 7.5 Graph Retriever

**File:** `rag/graph_retriever.py`

Cross-references are built at **index time** by `RegulationIndexer.link_related_articles()`:
- Scans each chunk's content for patterns like `"Artículo 15"`, `"Art. 8"`, `"Artículo 15 bis"`.
- For each match, creates a directed M2M edge from the current chunk to all chunks of the **same source** (`UIAF`/`CNBV`/`SBS`) with that `article_number`.
- Result: `RegulationDocument.related_articles` is a self-referential M2M that encodes the citation graph within each regulatory corpus.

At **retrieval time:**
1. `VectorStoreRetriever.retrieve(query, seed_top_k=3)` — get the 3 most semantically relevant chunks.
2. For each seed's `document_ref`, fetch all `related_articles` via `prefetch_related("related_articles")` — one DB query.
3. Assign `score = SEED_WEIGHT (1.0)` to seeds, `NEIGHBOR_WEIGHT (0.5)` to neighbors.
4. Deduplicate (a neighbor can't outrank a seed), sort, return top_k.

**What it catches:** Multi-article reasoning queries. When SBS Resolución 789-2018 Art. 17 (PEP escalation) is a seed, its cross-reference to Ley 27693 Art. 8 (record retention obligations) is automatically surfaced — giving the Decision Agent broader regulatory context in a single retrieval pass.

**Why 1-hop is sufficient:** Regulatory cross-references are direct citations, not multi-hop inference chains. A 2-hop traversal would add articles referenced by the *neighbors* of the seed, which are likely too tangential and would degrade precision.

### 7.6 How RRF Fuses the Rankings

Each retriever produces an independently ranked list. The scores are **not comparable** across retrievers — cosine distance (0–1), BM25 rank scores, and graph-weighted scores have different scales. Traditional approaches (linear combination, score normalization) require tuning weights per retriever. **RRF eliminates this problem entirely** by fusing *ranks*, not scores:

```
RRF_score(d) = Σᵢ  1 / (k + rankᵢ(d))    where k = 60
```

`k=60` is a damping constant from Cormack et al. (2009) that smooths the reward for being rank 1 vs. rank 2 — making the fusion tolerant to rank perturbations in any single method.

**Why this works:**
- **Consensus amplification:** A chunk ranked highly by *all three* retrievers accumulates three independent `1/(k+rank)` contributions — it rises to the top because multiple independent methods agree.
- **Noise suppression:** A chunk ranked highly by only *one* retriever gets a single small contribution. It can only reach the top if the other retrievers also find it, which filters out retriever-specific false positives.
- **No weight tuning required:** Unlike weighted linear combination, RRF doesn't need `α·dense + β·sparse + γ·graph` coefficients that require calibration on labeled data.

**Concrete example — query: "What applies to a $50K USD international PEP transfer?"**

| Chunk | Dense rank | Sparse rank | Graph rank | RRF score | Why |
|-------|-----------|-------------|------------|-----------|-----|
| SBS Res. 789 Art. 17 (PEP escalation) | 1 | 3 | 1 | 1/61 + 1/63 + 1/61 = **0.0487** | All 3 agree — rises to top |
| UIAF SARLAFT Cap. IV Art. 14 (PEP DD) | 2 | 1 | — | 1/62 + 1/61 = **0.0325** | Dense semantic + sparse exact "PEP" |
| CNBV DCG Art. 115 Disp. 31a (PEP prohibition) | 4 | 2 | — | 1/64 + 1/62 = **0.0318** | Sparse exact "Disposición 31a" rescues rank |
| SBS Ley 27693 Art. 8 (record retention) | — | — | 2 | 1/62 = **0.0161** | Graph only — cross-ref from Art. 17 |
| Unrelated structuring article | 5 | — | — | 1/65 = **0.0154** | Only 1 retriever, low rank → filtered |

### 7.7 Chunking Strategy

Regulatory documents are split by `RegulationChunker` (`rag/chunking.py`):

- **Chunk size: 512 tokens** (~2,048 chars at 4 chars/token for Spanish text). Most regulatory articles fit in one chunk — splitting mid-article severs legal context.
- **Overlap: 64 tokens** (12.5%). Prevents loss of article header at chunk boundaries — "Artículo 15" carries forward into the next chunk so the article number is always recoverable.
- **Separators (priority order):**
  1. `"\n\nArtículo"` — split on article boundaries first (preserves atomic unit of regulatory text)
  2. `"\n\n"` — paragraph breaks
  3. `"\n"` — line breaks
  4. `" "` — word splits (last resort)

### 7.8 Graph Layer Infrastructure Choice

The challenge suggests Neo4j or FalkorDB for the graph layer. Decision: use Django M2M `related_articles` self-referential field instead.

**Why this is equivalent for our use case:** The graph is a simple adjacency list with one traversal depth. PostgreSQL handles a 1-hop JOIN on a well-indexed M2M table in microseconds. Neo4j adds value for multi-hop traversals (3+ hops), graph algorithms (PageRank, community detection), and billion-edge scale — none of which apply to a corpus of hundreds of regulatory chunks.

**Trade-off accepted:** 2-hop or deeper traversal would require recursive SQL or Cypher. The current design cannot be extended to deeper traversal without replacing the `GraphRetriever`. This is documented and accepted — the `IRetriever` interface means a `Neo4jGraphRetriever` can be dropped in without touching any agent code.

### 7.9 RAG Quality Metrics

A compliance RAG system has a unique failure mode compared to general-purpose RAG: if the retriever misses a regulation, the Decision Agent cannot cite it — and the resulting decision may silently violate that regulation. Standard chatbot RAG tolerates imprecise retrieval; **compliance RAG cannot** — a missed article is a potential regulatory violation.

#### Information Retrieval Metrics (measure the retriever)

These evaluate whether the retriever surfaces the correct regulatory articles *before* the LLM ever sees them. If retrieval fails, no prompt engineering can fix the output.

| Metric | Formula | What It Measures | Why We Need It | Target |
|--------|---------|------------------|----------------|--------|
| **Hit Rate @5** | `1 if any relevant doc in top-5, else 0` (mean over queries) | Binary recall: did at least one correct regulation make it into the top-5 context window? | The Decision Agent receives top-5 chunks. If zero relevant regulations appear, the agent either hallucinates a citation or decides with no regulatory grounding. This is the most basic safety net. | ≥ 0.80 |
| **MRR** | `1/rank` of first relevant result, averaged over queries | Rank quality: how high does the first correct regulation appear? | LLMs exhibit position bias — they attend more strongly to chunks earlier in the context. If the correct regulation sits at position 5, the LLM anchors on irrelevant chunks above it. | ≥ 0.70 |
| **NDCG@5** | `DCG@5 / IDCG@5` where `DCG = Σ(rel_i / log₂(i+2))` | Graded ranking quality across *all* relevant docs, not just the first hit. | A PEP transfer query may need regulations from UIAF, CNBV, *and* SBS. MRR = 1.0 if just one jurisdiction is rank 1, even if the others are buried. NDCG penalizes this. | ≥ 0.75 |

#### Generation Quality Metrics (measure the LLM output)

These evaluate what the Decision Agent *does* with the retrieved context. Good retrieval is necessary but not sufficient — the LLM can still hallucinate citations or drift off-topic.

| Metric | Formula | What It Measures | Why We Need It | Target |
|--------|---------|------------------|----------------|--------|
| **Faithfulness** | `grounded_citations / total_citations` (source + article match against retrieved chunks) | Grounding: does every cited regulation actually come from retrieved chunks? | The hallucination detector. An LLM may "know" SARLAFT Art. 14 from training data and cite it even though the retriever returned different articles. The audit trail would reference a regulation never actually retrieved — an auditor would find the citation fabricated. | ≥ 0.90 |
| **Answer Relevance** | `cosine(embed(question), embed(answer))` via all-MiniLM-L6-v2 | Topical alignment: is the reasoning actually about the question asked? | High faithfulness alone doesn't mean the answer is useful — the agent could cite real regulations but about the wrong topic. Answer Relevance catches off-topic drift. | ≥ 0.85 |

See `notebooks/rag_evaluation.ipynb` for full evaluation with test queries, per-retriever comparison, and results.

### 7.10 Evaluation Framework: RAGAS vs DeepEval vs Custom

**CHALLENGE.md asks:** *"¿Usarías RAGAS, DeepEval u otro framework? Justifica tu decisión."*

| Framework | Strengths | Limitations |
|-----------|-----------|-------------|
| **RAGAS** | Standard metrics (faithfulness, context precision, answer relevancy), broad community adoption | Requires LLM API call per evaluation batch, English-centric prompt design, opaque scoring internals, heavyweight dependency for what are conceptually simple formulas |
| **DeepEval** | Rich metric library, supports custom LLM judges, pytest integration | Complex API surface, non-trivial setup overhead, overkill for a well-defined 5-metric evaluation |
| **Custom (chosen)** | Full control over scoring criteria, domain-specific regulatory rules, deterministic IR metrics (no API cost), transparent and auditable | Must maintain metric implementations |

**Decision: Custom metrics + LLM-Judge hybrid.**

**For the three IR metrics (HR@5, MRR, NDCG@5):** These are standard information retrieval formulas. The implementations are ~30 lines of Python with no dependencies. RAGAS adds no value here — it would wrap the same formula in an LLM call for zero benefit.

**For Faithfulness:** We use grounded-citation-ratio: deterministic string matching (source + article number) against retrieved chunks. This is more transparent and cheaper than RAGAS's LLM-based claim decomposition. For a regulatory compliance context, the evaluation methodology itself must be auditable.

**For Answer Relevance:** Cosine similarity between question and answer embeddings via the same `all-MiniLM-L6-v2` embedder already in the pipeline — zero additional infrastructure cost.

**For end-to-end decision quality:** The LLM Judge (`scripts/llm_judge.py`) covers what RAGAS and DeepEval address at the generation quality level, but with domain-specific scoring rubrics: regulatory compliance scoring (UIAF/CNBV/SBS), critical failure detection for PEP violations, and risk score accuracy per XGBoost calibration bands.

**Compliance note:** For a regulatory compliance product, the evaluation methodology is itself subject to auditor scrutiny. A custom implementation with explicit formulas is more defensible than a framework whose LLM-generated intermediate scores may change between framework versions.

### 7.11 Indexing Regulations

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

## 8. Data Model

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

## 9. User Interaction & API

### 9.1 API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check — returns `{"status": "ok"}` |
| `GET` | `/readiness` | Readiness check — verifies DB connection |
| `POST` | `/api/v1/alerts/{alert_id}/investigate` | Trigger the full 3-agent pipeline for an alert |
| `GET` | `/api/v1/alerts/{alert_id}/status` | Get current alert status and metadata |
| `GET` | `/api/v1/alerts/{alert_id}/audit-trail` | Get all audit log events for an alert |

Interactive API docs: http://localhost:8000/docs (Swagger UI)

### 9.2 Typical Workflow

```
1. XGBoost model generates a fraud alert → creates Alert record in DB (status=PENDING)
2. Caller POSTs to /api/v1/alerts/{alert_id}/investigate
3. System runs InvestigadorAgent → RiskAnalyzerAgent → DecisionAgent
4. Returns decision synchronously (typical: 3-8 seconds)
5. If ESCALATED: human analyst notified via external system (out of scope)
6. Caller GETs /api/v1/alerts/{alert_id}/audit-trail for full decision trace
```

---

## 10. Pregunta Abierta — Sistema en Producción

> **Escenario:** Después de 3 semanas en producción, el sistema tiene una tasa de escalación al humano del 12% (el target era 15% — el equipo está contento). Sin embargo, un auditor externo detecta que el sistema está sistemáticamente sub-escalando alertas de personas políticamente expuestas (PEPs): las está resolviendo de forma automática cuando la regulación exige escalarlas siempre.

### 1. How to detect this before an auditor finds it (day-1 monitoring)

The key insight is that PEP sub-escalation is a **silent failure** — the system produces confident decisions, latency looks normal, and no exceptions are raised. Only the _outcome_ is wrong. Day-1 monitoring must therefore track decision distribution, not just system health.

**Monitoring setup:**

```sql
-- Alert if any PEP alert is NOT escalated
SELECT alert_id, decision_type, is_pep
FROM compliance_agent_decision d
JOIN compliance_agent_riskanalysis ra ON d.risk_analysis_id = ra.id
JOIN compliance_agent_investigation i ON ra.investigation_id = i.id
JOIN compliance_agent_alert a ON i.alert_id = a.id
WHERE a.is_pep = TRUE AND d.decision_type != 'ESCALATE';
```

**Day-1 Dashboards (Langfuse + Cloud Monitoring):**
- `pep_escalation_rate` — must be 1.0 (100%). Alert if < 1.0.
- `pep_override_applied_rate` — must match `pep_escalation_rate`. If they diverge, the LLM overrode the hard-rule.
- `decision_distribution_by_pep` — segmented bar chart. Any DISMISS or REQUEST_INFO on PEP = P0 incident.
- `p95_pipeline_latency` — PEP alerts should be faster (no LLM call if hard-rule fires); anomalous latency may indicate the rule is not firing.

**Automated test in CI:**

```python
def test_pep_always_escalates(sample_pep_alert):
    result = run_pipeline(sample_pep_alert)
    assert result["decision"]["decision_type"] == "ESCALATE"
    assert result["decision"]["is_pep_override_applied"] is True
```

This test must run on every deploy and block any regression from shipping.

### 2. Most likely root cause

Three candidates, in order of likelihood:

**a) Prompt failure (most likely):** The Risk Analyzer prompt returns a low score (e.g., 3/10) for a PEP with a small transaction, and the Decision Agent prompt is written to DISMISS when `risk_score < 4`. The PEP status may be present in the context but the prompt's few-shot examples didn't include PEP+low-score combinations, causing the LLM to treat risk score as the only relevant factor.

**b) RAG gap:** The regulatory documents in the vector store don't include the PEP-mandatory-escalation articles (UIAF Art.14, CNBV Art.95, SBS Art.17), or these documents have poor embedding quality or bad chunking strategy. The Decision Agent has no retrieved regulation telling it to escalate PEPs, and defaults to a risk-score-based decision.

**c) Decision agent design flaw:** The PEP hard-rule check was never implemented as deterministic code — instead, it relies on the LLM to infer PEP escalation from retrieved regulations. This is the architectural antipattern: compliance-critical invariants should never be delegated to an LLM.

### 3. Concrete technical fix

The fix is in `compliance_agent/agents/decision_agent.py`:

```python
# PEP hard-rule: deterministic escalation, no LLM needed
if is_pep:
    decision = Decision(
        decision_type=Decision.DecisionType.ESCALATE,
        confidence=1.0,
        is_pep_override_applied=True,
        ...
    )
    return self._build_output(state, decision)

# Only reach RAG + LLM for non-PEP decisions
```

The key properties:
- PEP check happens **before** any LLM call
- `is_pep_override_applied=True` is stored in the DB for audit
- Confidence is always `1.0` (not LLM-estimated)
- No amount or risk score threshold can override this

If the bug existed in production, the hotfix is:
1. Deploy the deterministic PEP check
2. Re-run all DISMISS/REQUEST_INFO decisions on PEP alerts from the past 3 weeks
3. File a SAR (Suspicious Activity Report) for any PEP alerts that were incorrectly dismissed
4. Notify compliance officer and legal team immediately

### 4. Architectural changes to prevent recurrence

**Hard invariants as code, not prompts:** Any regulatory rule that is a _mandatory_ obligation (not a judgment call) must be expressed as deterministic Python code that runs before the LLM. The LLM should only make decisions in the space left open by hard rules.

**Separate rule engine from LLM reasoning:** Introduce a `RuleEngine` layer between the Risk Analyzer and Decision Agent:

```
RiskAnalyzer → RuleEngine → DecisionAgent (LLM)
                    ↓
         [ESCALATE_IMMEDIATELY if PEP]
         [ESCALATE if score >= 9]
         → passes remaining cases to LLM
```

**Invariant testing in CI:** The test suite must include a dedicated `tests/invariants/` directory with tests that enumerate all known hard regulatory rules. These tests run in CI with `--tb=long` and any failure blocks deployment.

**Compliance canary in production:** A synthetic PEP alert is submitted to the pipeline daily. Its decision is checked by an automated monitor. If it's ever not ESCALATE, a P0 alert fires immediately.

**Audit log anomaly detection:** Langfuse monitors the ratio `pep_alerts / pep_escalations`. Any deviation from 1.0 triggers an immediate PagerDuty alert to the compliance officer.

---

## 11. Examples

### 11.1 Complete Walkthrough — Non-PEP Alert

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
    "step_by_step_reasoning": "1. Transaction velocity (15/90d) exceeds the structuring threshold defined in SARLAFT CE 029/2014. 2. The corridor Colombia→Panama→Cayman Islands is a known layering route per DCG Disp. 29a guidelines. 3. Six transactions between $9,800-$9,950 match the structuring pattern. 4. Combined xgboost_score of 0.78 corroborates anomalous classification. Decision: ESCALATE with 0.91 confidence.",
    "is_pep_override_applied": false
  },
  "langfuse_trace_id": "a3f8c2d1e5b74690a1b2c3d4e5f60718"
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
      "event_type": "INVESTIGATION",
      "agent_name": "InvestigadorAgent",
      "duration_ms": 1240,
      "token_cost_usd": 0.0,
      "langfuse_trace_id": "a3f8c2d1e5b74690a1b2c3d4e5f60718",
      "created_at": "2024-03-15T14:23:02Z"
    },
    {
      "event_type": "RISK_ANALYSIS",
      "agent_name": "RiskAnalyzerAgent",
      "duration_ms": 2180,
      "token_cost_usd": 0.00142,
      "langfuse_trace_id": "a3f8c2d1e5b74690a1b2c3d4e5f60718",
      "created_at": "2024-03-15T14:23:04Z"
    },
    {
      "event_type": "DECISION",
      "agent_name": "DecisionAgent",
      "duration_ms": 3050,
      "token_cost_usd": 0.00187,
      "langfuse_trace_id": "a3f8c2d1e5b74690a1b2c3d4e5f60718",
      "created_at": "2024-03-15T14:23:07Z"
    }
  ]
}
```

All three events share the same `langfuse_trace_id`. Total pipeline time: ~6.5 seconds. Total LLM cost: ~$0.003.

---

### 11.2 PEP Alert — Deterministic Hard-Rule

**The alert has `is_pep=true`.**

```bash
curl -X POST http://localhost:8000/api/v1/alerts/660e8400-e29b-41d4-a716-446655440001/investigate \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Response (1-2 seconds — no LLM calls in the decision step):**
```json
{
  "alert_id": "660e8400-e29b-41d4-a716-446655440001",
  "status": "ESCALATE",
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
  }
}
```

Key differences from non-PEP:
- `confidence = 1.0` (not LLM-estimated)
- `is_pep_override_applied = true` (stored for external auditor inspection)
- Pipeline runs in ~1.5 seconds instead of 6-8 seconds
- All three regulators are always cited

---

### 11.3 Pipeline State at Each Stage

**After InvestigadorAgent:**
```python
{
    "alert_id": "550e8400-...",
    "alert_data": {
        "customer_id": "CUST-98765",
        "is_pep": False,
        "amount": "48500.00",
        "currency": "USD",
        "xgboost_score": 0.78,
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
        "documents_count": 3,
        "customer_profile": {"risk_category": "HIGH", "kyc_status": "UNDER_REVIEW", ...}
    },
    "errors": [],
    "langfuse_trace_id": "a3f8c2d1e5b74690a1b2c3d4e5f60718"
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

### 11.4 Running Tests

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

### 11.5 Local Development with Docker

```bash
# Start PostgreSQL + Langfuse (API runs separately — see below)
docker compose up

# In another terminal, run migrations
make migrate

# Start the API (required — not included in docker compose)
make run
# or: cd backend && uv run uvicorn compliance_agent.api.main:app --reload --port 8000

# The API is now available at:
# http://localhost:8000/docs  ← Swagger UI
# http://localhost:3000       ← Langfuse dashboard (traces, costs)
#   Default credentials: admin / password

# View DB/Langfuse logs
docker compose logs -f

# Reset database
docker compose down -v && docker compose up
make migrate
```

> **Note:** `docker compose up` starts only `db` and `langfuse`. The compliance API must be started separately with `make run`.

---

## 12. Infrastructure

See `terraform/` for full IaC. Key resources:

- **Cloud Run** — Compliance API, min 1 / max 10 instances, 2 vCPU / 2 GiB
- **Cloud SQL (PostgreSQL 16 + pgvector)** — Private network, point-in-time recovery
- **GCS** — Versioned bucket for customer compliance documents (lifecycle: 365d → Nearline)
- **IAM** — Least-privilege service account (BigQuery viewer, GCS viewer, Vertex AI user, Cloud SQL client, Secret Manager accessor)

---

## 13. Observability

| Signal | Tool | Alert Threshold |
|--------|------|----------------|
| p95 pipeline latency | Cloud Monitoring | > 30s |
| Cost per alert | Langfuse | > $0.05 |
| PEP escalation rate | Custom metric | < 100% |
| Human escalation rate | Langfuse dashboard | > 40% (possible calibration issue) |
| LLM drift (risk score distribution) | Langfuse scores | KS-test p < 0.05 vs. baseline |
| Decision quality (LLM Judge) | `judge_report_*.md` | avg score < 4.0/5 on any dimension |

---

## 14. Mi Flujo con AI

During this assessment I used AI assistance in the following ways:

1. **Architecture design** — Used Claude to reason about LangGraph topology and validate that the PEP hard-rule placement (before LLM) was architecturally correct.
2. **Regulatory research** — Asked Claude to summarize UIAF, CNBV, and SBS PEP obligations to inform the decision agent prompt and regulatory document fixtures.
3. **Code generation** — Generated boilerplate for repositories, FastAPI routers, and Terraform modules. All generated code was reviewed and modified to match project conventions.
4. **Test design** — Designed the PEP hard-rule test collaboratively: identified the critical invariant, then wrote the test to verify `mock_llm.ainvoke.assert_not_called()`.
5. **RAG evaluation metrics** — Used Claude to verify the RRF formula and explain why k=60 is a robust default.
6. **LLM-as-Judge calibration loop** — Built an offline judge (`scripts/llm_judge.py`) that scores each pipeline decision on four dimensions (decision correctness, regulatory compliance, reasoning quality, risk score accuracy) and writes a full markdown report. The judge output drove concrete prompt improvements:
   - **Iteration 1:** Scenarios 1 and 8 (low-risk COP and MXN) were over-escalated. The judge identified the root cause as missing xgboost calibration bands and no currency-to-USD context in the prompts. Added calibration bands (0.00–0.30 LOW, 0.31–0.64 MEDIUM, 0.65–0.79 HIGH) and exchange rates (COP≈4,100/USD, MXN≈17/USD, PEN≈3.7/USD) to both RISK_PROMPT and DECISION_PROMPT. Re-run confirmed correct DISMISS decisions.
   - **Iteration 2:** Scenario 5 (PEN 18,500, xgb=0.61) was misclassified as ESCALATE instead of REQUEST_INFO. The judge flagged the missing risk 5–7 band in the decision criteria. Shifted the HIGH xgboost threshold from 0.60 to 0.65 and added an explicit REQUEST_INFO band for borderline-ambiguous cases. Re-run confirmed correct REQUEST_INFO decision.
   - This feedback loop is now integrated into `make live-test-judge` — judge findings are the primary input for any future prompt calibration.

The most critical human judgment: ensuring the PEP hard-rule is truly deterministic and that no path through the code can bypass it. AI-generated code for this section was scrutinized carefully against the regulatory requirements.

---

## 15. Deliverables

| Deliverable | Location | Status |
|-------------|----------|--------|
| **Agentic code** — 3 agents, `docker compose up` | `backend/compliance_agent/agents/` | ✅ |
| **RAG + GraphRAG** — hybrid retrieval, 5 regulatory docs | `backend/compliance_agent/rag/` | ✅ |
| **RAG evaluation notebook** — HR@5, MRR, NDCG@5, Faithfulness, Answer Relevance | `notebooks/rag_evaluation.ipynb` | ✅ |
| **CTO Document** — 2-page business case, ROI model, break-even | `docs/cto_document.md` | ✅ |
| **Terraform IaC** — Cloud Run, Cloud SQL, GCS, IAM (4 modules) | `terraform/` | ✅ |
| **CI/CD pipelines** — lint + test (60% gate) + build + deploy | `.github/workflows/` | ✅ |
| **Pregunta Abierta** — PEP sub-escalation (600+ words) | [Section 10](#10-pregunta-abierta--sistema-en-producción) | ✅ |
| **Mi Flujo con AI** — AI tool usage documentation | [Section 14](#14-mi-flujo-con-ai) | ✅ |
| **Live test suite** — 30 scenarios, LLM-as-Judge calibration | `scripts/`, `docs/live_testing.md` | ✅ |
| **Test suite** — 83 tests, unit + integration, 60% coverage | `backend/tests/` | ✅ |
