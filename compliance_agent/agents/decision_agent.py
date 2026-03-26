from typing import Any

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

from compliance_agent.agents.base import BaseAgent
from compliance_agent.models import AuditLog, Decision, RiskAnalysis
from compliance_agent.rag.interfaces import IRetriever
from compliance_agent.repositories.interfaces import IDecisionRepository

DECISION_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a senior compliance officer AI for a Latin American financial institution.
Your decisions must cite specific regulations from UIAF (Colombia), CNBV (Mexico), or SBS (Peru).

Available decisions:
- ESCALATE: Requires human review. Mandatory for PEP, risk >= 8, or regulatory obligation.
- DISMISS: Alert is not suspicious. Document reasoning clearly.
- REQUEST_INFO: More information needed before deciding.

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

Relevant Regulations Retrieved:
{regulations}

Make your compliance decision.""",
        ),
    ]
)

PEP_ESCALATION_REASON = (
    "PEP hard rule: Politically Exposed Persons require mandatory human escalation "
    "per UIAF Resolution 285/2007 Art. 14, CNBV CFPIOR Art. 95, and SBS R-SBS-2019-1874 Art. 17."
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
    ) -> None:
        super().__init__(llm, tracer)
        self.retriever = retriever
        self.decision_repo = decision_repo

    async def run(self, state: dict) -> dict:
        alert_data: dict = state["alert_data"]
        risk_data: dict = state["risk_analysis"]
        is_pep: bool = alert_data.get("is_pep", False)

        risk_analysis = RiskAnalysis.objects.get(pk=risk_data["id"])

        # PEP hard-rule: deterministic escalation, no LLM needed
        if is_pep:
            decision = Decision(
                risk_analysis=risk_analysis,
                decision_type=Decision.DecisionType.ESCALATE,
                confidence=1.0,
                regulations_cited=[
                    {
                        "source": "UIAF",
                        "article": "Resolución 285/2007 Art. 14",
                        "text": "Operaciones con PEP requieren reporte obligatorio.",
                        "confidence": 1.0,
                    },
                    {
                        "source": "CNBV",
                        "article": "CFPIOR Art. 95",
                        "text": "PEPs deben ser escalados a revisión humana.",
                        "confidence": 1.0,
                    },
                    {
                        "source": "SBS",
                        "article": "R-SBS-2019-1874 Art. 17",
                        "text": "Personas políticamente expuestas: escalamiento obligatorio.",
                        "confidence": 1.0,
                    },
                ],
                step_by_step_reasoning=PEP_ESCALATION_REASON,
                is_pep_override_applied=True,
            )
            decision = self.decision_repo.save(decision)
            self._write_audit_log(state, decision, is_pep_override=True)
            return self._build_output(state, decision)

        # RAG retrieval for non-PEP decisions
        query = f"{risk_data['justification']} {' '.join(risk_data.get('anomalous_patterns', []))}"
        regulation_chunks = await self.retriever.retrieve(query, top_k=5)
        regulations_text = "\n\n".join(
            f"[{c.source}] {c.document_ref} Art.{c.article_number}:\n{c.content}"
            for c in regulation_chunks
        )

        chain = DECISION_PROMPT | self.llm | JsonOutputParser()
        result = await chain.ainvoke(
            {
                "risk_score": risk_data["risk_score"],
                "justification": risk_data["justification"],
                "anomalous_patterns": risk_data.get("anomalous_patterns", []),
                "human_summary": risk_data["human_summary"],
                "is_pep": is_pep,
                "amount": alert_data.get("amount", 0),
                "currency": alert_data.get("currency", "USD"),
                "regulations": regulations_text or "No specific regulations retrieved.",
            }
        )

        decision = Decision(
            risk_analysis=risk_analysis,
            decision_type=result["decision_type"],
            confidence=float(result["confidence"]),
            regulations_cited=result.get("regulations_cited", []),
            step_by_step_reasoning=result["step_by_step_reasoning"],
            is_pep_override_applied=False,
        )
        decision = self.decision_repo.save(decision)
        self._write_audit_log(state, decision, is_pep_override=False)
        return self._build_output(state, decision)

    def _write_audit_log(
        self, state: dict, decision: Decision, is_pep_override: bool
    ) -> None:
        AuditLog.objects.create(
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
