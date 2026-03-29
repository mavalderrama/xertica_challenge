import time
from typing import Any

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

from compliance_agent.agents.base import BaseAgent
from compliance_agent.models import Decision
from compliance_agent.observability import estimate_cost
from compliance_agent.rag.interfaces import IRetriever
from compliance_agent.repositories.interfaces import (
    IDecisionRepository,
    IRiskAnalysisRepository,
)

DECISION_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a senior compliance officer AI for a Latin American financial institution.
Your decisions must cite specific regulations from UIAF (Colombia), CNBV (Mexico), or SBS (Peru).

## Decision Criteria

**DISMISS** — use when ALL of the following are true:
- Risk score ≤ 4
- Non-PEP customer
- Alert amount is below the applicable reporting threshold (COP 10,000,000 / USD 7,500 / PEN 10,000)
- No high-severity anomalous patterns (structuring, sanction lists, PEP-linked)
Dismissing low-risk alerts is the correct outcome. Over-escalation wastes compliance officer
time and degrades system effectiveness. A low risk score (1–4) with a below-threshold amount
and no PEP flag should be DISMISSED.

**REQUEST_INFO** — use when there is genuine ambiguity that additional documentation
would concretely resolve. Appropriate for risk 5–7 when:
- The customer recently changed declared profession or income source
- The amount is moderately above threshold but the xgboost score is borderline (0.55–0.70)
- Unusual patterns exist but could have a legitimate explanation
Do NOT use REQUEST_INFO for clearly low-risk alerts (risk ≤ 4) — that is a DISMISS.

**ESCALATE** — use when ANY of the following are true:
- Risk score ≥ 8
- PEP customer (already handled by hard rule before this prompt)
- Confirmed structuring pattern (fraccionamiento)
- Sanction list match
- Amount is far above threshold (>5x) with high xgboost score (≥0.65)

## Regulatory Reporting Thresholds
- SARLAFT (Colombia): COP 10,000,000 per operation for natural persons
- CNBV (Mexico): USD 7,500 equivalent per operation (≈ MXN 127,500)
- SBS (Peru): PEN 10,000 per operation

## XGBoost Score Context
The XGBoost score is a calibrated ML fraud-detection score (0.0–1.0):
- 0.00–0.30 = LOW — strong signal that this is not fraud
- 0.31–0.59 = MEDIUM — some signals, review warranted
- 0.60–0.79 = HIGH — significant fraud indicators
- 0.80–1.00 = CRITICAL — very likely fraudulent

Respond ONLY with valid JSON:
{{
  "decision_type": "<ESCALATE|DISMISS|REQUEST_INFO>",
  "confidence": <float 0.0-1.0>,
  "regulations_cited": [
    {{"source": "<UIAF|CNBV|SBS>", "article": "<ref>", "text": "<excerpt>", "confidence": <float>}}
  ],
  "step_by_step_reasoning": "<numbered steps explaining the decision>"
}}""",
        ),
        (
            "human",
            """Risk Analysis:
- Score: {risk_score}/10
- Justification: {justification}
- Anomalous patterns: {anomalous_patterns}
- Summary: {human_summary}

Customer Context:
- Is PEP: {is_pep}
- Alert amount: {amount} {currency}
- XGBoost Score: {xgboost_score}

Relevant Regulations Retrieved:
{regulations}

Make your compliance decision.""",
        ),
    ]
)

PEP_ESCALATION_REASON = (
    "PEP hard rule: Politically Exposed Persons require mandatory human escalation "
    "per SARLAFT CE 029/2014 Cap. IV (Colombia), DCG Art. 115 LIC Disp. 31a (Mexico), "
    "and Resolución SBS 789-2018 Art. 17 (Peru)."
)


class DecisionAgent(BaseAgent):
    """
    Agent 3: Makes ESCALATE/DISMISS/REQUEST_INFO decision.
    PEP hard-rule is applied deterministically BEFORE any LLM call.
    """

    def __init__(
        self,
        llm: Any,
        tracer: Any,
        retriever: IRetriever,
        decision_repo: IDecisionRepository,
        risk_analysis_repo: IRiskAnalysisRepository,
        audit_service: Any,
    ) -> None:
        super().__init__(llm, tracer)
        self.retriever = retriever
        self.decision_repo = decision_repo
        self.risk_analysis_repo = risk_analysis_repo
        self.audit_service = audit_service

    async def run(self, state: dict) -> dict:
        alert_data: dict = state["alert_data"]
        risk_data: dict = state["risk_analysis"]
        is_pep: bool = alert_data.get("is_pep", False)

        start = time.monotonic()
        risk_analysis = await self.risk_analysis_repo.get_by_id(risk_data["id"])

        # PEP hard-rule: deterministic escalation, no LLM needed
        if is_pep:
            decision = Decision(
                risk_analysis=risk_analysis,
                decision_type=Decision.DecisionType.ESCALATE,
                confidence=1.0,
                regulations_cited=[
                    {
                        "source": "UIAF",
                        "article": "SARLAFT CE 029/2014 Cap. IV — Debida Diligencia Intensificada",
                        "text": "PEPs requieren DDI y escalamiento obligatorio al oficial de cumplimiento. Ningún sistema automatizado podrá archivar alertas de clientes PEP sin revisión previa.",
                        "confidence": 1.0,
                    },
                    {
                        "source": "CNBV",
                        "article": "DCG Art. 115 LIC — Disp. 31a Personas Políticamente Expuestas",
                        "text": "Está prohibido que sistemas automatizados archiven operaciones de PPEs sin revisión previa y expresa del oficial de cumplimiento.",
                        "confidence": 1.0,
                    },
                    {
                        "source": "SBS",
                        "article": "Resolución SBS 789-2018 Art. 17 — DDR para PEPs",
                        "text": "Escalamiento obligatorio a revisión humana de toda alerta PEP, sin excepción. Queda prohibido que los sistemas automatizados emitan decisión de archivo sobre alertas PEP.",
                        "confidence": 1.0,
                    },
                ],
                step_by_step_reasoning=PEP_ESCALATION_REASON,
                is_pep_override_applied=True,
            )
            decision = await self.decision_repo.save(decision)
            duration_ms = int((time.monotonic() - start) * 1000)
            await self._write_audit_log(
                state,
                decision,
                is_pep_override=True,
                duration_ms=duration_ms,
                token_cost_usd=0.0,
            )
            return self._build_output(state, decision)

        # RAG retrieval for non-PEP decisions
        query = f"{risk_data['justification']} {' '.join(risk_data.get('anomalous_patterns', []))}"
        regulation_chunks = await self.retriever.retrieve(query, top_k=5)
        regulations_text = "\n\n".join(
            f"[{c.source}] {c.document_ref} Art.{c.article_number}:\n{c.content}"
            for c in regulation_chunks
        )

        chain = DECISION_PROMPT | self.llm
        message = await chain.ainvoke(
            {
                "risk_score": risk_data["risk_score"],
                "justification": risk_data["justification"],
                "anomalous_patterns": risk_data.get("anomalous_patterns", []),
                "human_summary": risk_data["human_summary"],
                "is_pep": is_pep,
                "amount": alert_data.get("amount", 0),
                "currency": alert_data.get("currency", "USD"),
                "xgboost_score": alert_data.get("xgboost_score", "N/A"),
                "regulations": regulations_text or "No specific regulations retrieved.",
            }
        )
        result = JsonOutputParser().parse(message.content)

        usage = getattr(message, "usage_metadata", None) or {}
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        cost_usd = estimate_cost(input_tokens, output_tokens)

        decision = Decision(
            risk_analysis=risk_analysis,
            decision_type=result["decision_type"],
            confidence=float(result["confidence"]),
            regulations_cited=result.get("regulations_cited", []),
            step_by_step_reasoning=result["step_by_step_reasoning"],
            is_pep_override_applied=False,
        )
        decision = await self.decision_repo.save(decision)
        duration_ms = int((time.monotonic() - start) * 1000)
        await self._write_audit_log(
            state,
            decision,
            is_pep_override=False,
            duration_ms=duration_ms,
            token_cost_usd=cost_usd,
        )
        return self._build_output(state, decision)

    async def _write_audit_log(
        self,
        state: dict,
        decision: Decision,
        is_pep_override: bool,
        duration_ms: int = 0,
        token_cost_usd: float = 0.0,
    ) -> None:
        await self.audit_service.log_agent_event(
            alert_id=state["alert_id"],
            event_type="DECISION",
            agent_name="DecisionAgent",
            input_snapshot={"risk_analysis_id": str(decision.risk_analysis_id)},
            output_snapshot={
                "decision_type": decision.decision_type,
                "confidence": decision.confidence,
                "is_pep_override": is_pep_override,
            },
            langfuse_trace_id=state.get("langfuse_trace_id", ""),
            duration_ms=duration_ms,
            token_cost_usd=token_cost_usd,
        )

    def _build_output(self, state: dict, decision: Decision) -> dict:
        return {
            **state,
            "decision": {
                "id": str(decision.id),
                "decision_type": decision.decision_type,
                "confidence": decision.confidence,
                "regulations_cited": decision.regulations_cited,
                "step_by_step_reasoning": decision.step_by_step_reasoning,
                "is_pep_override_applied": decision.is_pep_override_applied,
            },
        }
