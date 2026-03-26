# Compliance AI — Multi-Agent Fraud Alert Processing

> Reduces alert resolution from **4.2 hours → <30 minutes** while maintaining full regulatory audit trails for UIAF (Colombia), CNBV (Mexico), and SBS (Peru).

## Quick Start

```bash
# 1. Copy environment config
cp .env.example .env

# 2. Start all services (DB, Langfuse, API)
docker compose up

# 3. Run migrations
make migrate

# 4. Run tests
make test
```

## Architecture

```
Alert → InvestigadorAgent → RiskAnalyzerAgent → DecisionAgent → AuditLog
          (BQ + GCS)         (Gemini Flash)       (RAG + Rules)
```

Three agents run in a LangGraph pipeline:

1. **InvestigadorAgent** — Fetches 90-day transaction history from BigQuery and customer documents from GCS concurrently via `asyncio.gather()`. Builds `structured_context`.
2. **RiskAnalyzerAgent** — Calls Gemini 2.0 Flash with a structured prompt to assign a 1–10 risk score with regulatory justification.
3. **DecisionAgent** — Applies a **PEP hard-rule first** (deterministic, no LLM) then uses hybrid RAG to cite specific regulations for non-PEP decisions.

Every decision produces an `AuditLog` entry satisfying regulatory audit trail requirements.

## RAG System

### Retrieval Strategy

Hybrid retrieval combining two sources via **Reciprocal Rank Fusion (RRF)**:

| Retriever | Method | Strength |
|-----------|--------|----------|
| Dense | pgvector cosine (all-MiniLM-L6-v2, 384-dim) | Semantic recall |
| Sparse | pgvector inner product (TF-IDF sparsevec, 30k-dim) | Exact term precision |

**RRF Formula:**

```
score(d) = Σᵢ  1 / (k + rankᵢ(d))
```

where `k=60` (empirically robust constant from Cormack et al., 2009).

### Chunking Strategy

- **Chunk size:** 512 tokens (~2048 chars) — fits most regulatory articles in one chunk
- **Overlap:** 64 tokens — prevents article header loss at boundaries
- **Separators:** `["\n\nArtículo", "\n\n", "\n"]` — splits on article boundaries first

### RAG Quality Metrics

| Metric | Formula | Target |
|--------|---------|--------|
| **Hit Rate @5** | `relevant_retrieved / total_relevant` | ≥ 0.80 |
| **MRR** | `Σ 1/rank_of_first_relevant` / queries | ≥ 0.70 |
| **NDCG@5** | Σ `(2^rel - 1) / log₂(rank+1)` / ideal | ≥ 0.75 |
| **Faithfulness** | LLM-as-judge: cited ⊆ retrieved | ≥ 0.90 |
| **Answer Relevance** | Cosine(answer, question) | ≥ 0.85 |

See `notebooks/rag_evaluation.ipynb` for full evaluation with test queries.

---

## Open Production Scenario: PEP Sub-Escalation

> After 3 weeks in production, the system sub-escalates PEP alerts — resolving them automatically when regulation requires mandatory human escalation.

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

**b) RAG gap:** The regulatory documents in the vector store don't include the PEP-mandatory-escalation articles (UIAF Art.14, CNBV Art.95, SBS Art.17), or these documents have poor embedding quality. The Decision Agent has no retrieved regulation telling it to escalate PEPs, and defaults to a risk-score-based decision.

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

## Mi Flujo con AI

During this assessment I used AI assistance in the following ways:

1. **Architecture design** — Used Claude to reason about LangGraph topology and validate that the PEP hard-rule placement (before LLM) was architecturally correct.
2. **Regulatory research** — Asked Claude to summarize UIAF, CNBV, and SBS PEP obligations to inform the decision agent prompt and regulatory document fixtures.
3. **Code generation** — Generated boilerplate for repositories, FastAPI routers, and Terraform modules. All generated code was reviewed and modified to match project conventions.
4. **Test design** — Designed the PEP hard-rule test collaboratively: identified the critical invariant, then wrote the test to verify `mock_llm.ainvoke.assert_not_called()`.
5. **RAG evaluation metrics** — Used Claude to verify the RRF formula and explain why k=60 is a robust default.

The most critical human judgment: ensuring the PEP hard-rule is truly deterministic and that no path through the code can bypass it. AI-generated code for this section was scrutinized carefully against the regulatory requirements.

---

## Infrastructure

See `terraform/` for full IaC. Key resources:

- **Cloud Run** — Compliance API, min 1 / max 10 instances, 2 vCPU / 2 GiB
- **Cloud SQL (PostgreSQL 16 + pgvector)** — Private network, point-in-time recovery
- **GCS** — Versioned bucket for customer compliance documents
- **IAM** — Least-privilege service account (BigQuery viewer, GCS viewer, Vertex AI user, Cloud SQL client)

## Observability

| Signal | Tool | Alert Threshold |
|--------|------|----------------|
| p95 pipeline latency | Cloud Monitoring | > 30s |
| Cost per alert | Langfuse | > $0.05 |
| PEP escalation rate | Custom metric | < 100% |
| Human escalation rate | Langfuse dashboard | > 40% (possible calibration issue) |
| LLM drift (risk score distribution) | Langfuse scores | KS-test p < 0.05 vs. baseline |
