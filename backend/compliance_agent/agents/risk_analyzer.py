import time
from typing import Any

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

from compliance_agent.agents.base import BaseAgent
from compliance_agent.models import RiskAnalysis
from compliance_agent.observability import estimate_cost
from compliance_agent.repositories.interfaces import (
    IInvestigationRepository,
    IRiskAnalysisRepository,
)

RISK_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a financial crime risk analyst for a compliance system operating
under UIAF (Colombia), CNBV (Mexico), and SBS (Peru) regulations.

Analyze the provided customer context and assign a risk score from 1 (minimal risk)
to 10 (critical risk). Identify specific anomalous patterns.

## XGBoost Pre-Screening Score Interpretation
The XGBoost score (0.0–1.0) is the output of a calibrated ML model trained on confirmed fraud cases.
It is a strong, reliable prior for risk calibration:
- 0.00–0.30 → LOW risk — model sees no significant fraud signal
- 0.31–0.64 → MEDIUM risk — some unusual signals, warrants review
- 0.65–0.79 → HIGH risk — strong fraud indicators present
- 0.80–1.00 → CRITICAL risk — very high probability of fraudulent activity

## Currency Context (approximate exchange rates to USD)
- COP (Colombian Peso):  4,100 COP ≈ 1 USD
- MXN (Mexican Peso):       17 MXN ≈ 1 USD
- PEN (Peruvian Sol):       3.7 PEN ≈ 1 USD
Use these to assess whether amounts are genuinely significant before scoring.

## Regulatory Reporting Thresholds
- SARLAFT (Colombia): COP 10,000,000 per operation for natural persons (≈ USD 2,440)
- CNBV (Mexico): USD 7,500 equivalent per operation (≈ MXN 127,500)
- SBS (Peru): PEN 10,000 per operation (≈ USD 2,700)
Amounts below these thresholds by a comfortable margin are not reportable by themselves.

## Multi-Currency / Multi-Country Activity
In Latin American regional banking, retail customers often hold or transact in COP, MXN, PEN,
and USD due to cross-border trade, tourism, and remittances. The presence of 3-4 currencies
or 2-3 country codes in transaction history is NORMAL for retail_individual and sme segments
and does NOT by itself indicate suspicious activity. Only flag multi-currency as anomalous
when it is combined with other high-risk indicators (high xgboost score, large amounts,
PEP status, or patterns inconsistent with declared activity).

## Risk Score Calibration
The risk score must be proportional to actual evidence of financial crime, not theoretical
regulatory possibilities. Be accurate — over-scoring causes false escalations.

Guidelines:
- Score 1–3: Low xgboost (<0.40), below-threshold amounts, non-PEP, no structural patterns
- Score 4–6: Medium xgboost (0.40–0.64), some unusual patterns, borderline or moderately above-threshold amounts, ambiguous profile changes
- Score 5–7: Borderline-high xgboost (0.60–0.70), above-threshold amounts with unexplained profile changes — more information needed before concluding
- Score 7–8: High xgboost (≥0.65), significantly above-threshold amounts, structural patterns, or corporate segment
- Score 9–10: Near-certain fraud signal — reserve for xgboost ≥0.80 with large amounts or confirmed structuring

Respond ONLY with valid JSON matching this schema:
{{
  "risk_score": <integer 1-10>,
  "justification": "<detailed regulatory justification>",
  "anomalous_patterns": ["<pattern1>", "<pattern2>"],
  "human_summary": "<2-3 sentence plain-language summary for compliance officer>"
}}""",
        ),
        (
            "human",
            """Customer Context:
{structured_context}

Current Alert:
- Amount: {amount} {currency}
- Is PEP: {is_pep}
- XGBoost Score: {xgboost_score}
- Alert Type: {alert_type}
- Customer Segment: {segment}

Transaction Summary (last 90 days):
- Total transactions: {tx_count}
- Total amount: {total_amount}
- Countries involved: {countries}
- Currencies: {currencies}

Analyze and return the risk JSON.""",
        ),
    ]
)


class RiskAnalyzerAgent(BaseAgent):
    """
    Agent 2: Scores risk 1-10 with regulatory justification using Gemini.
    """

    def __init__(
        self,
        llm: Any,
        tracer: Any,
        risk_analysis_repo: IRiskAnalysisRepository,
        investigation_repo: IInvestigationRepository,
        audit_service: Any,
    ) -> None:
        super().__init__(llm, tracer)
        self.risk_analysis_repo = risk_analysis_repo
        self.investigation_repo = investigation_repo
        self.audit_service = audit_service

    async def run(self, state: dict) -> dict:
        investigation_data: dict = state["investigation"]
        alert_data: dict = state["alert_data"]

        start = time.monotonic()
        chain = RISK_PROMPT | self.llm
        raw_payload = alert_data.get("raw_payload") or {}
        message = await chain.ainvoke(
            {
                "structured_context": str(investigation_data),
                "amount": alert_data.get("amount", 0),
                "currency": alert_data.get("currency", "USD"),
                "is_pep": alert_data.get("is_pep", False),
                "xgboost_score": alert_data.get("xgboost_score", "N/A"),
                "alert_type": raw_payload.get("alert_type", "UNKNOWN"),
                "segment": raw_payload.get("segment", "unknown"),
                "tx_count": investigation_data.get("transaction_count_90d", 0),
                "total_amount": investigation_data.get("total_amount_90d", 0),
                "countries": investigation_data.get("countries", []),
                "currencies": investigation_data.get("currencies", []),
            }
        )
        result = JsonOutputParser().parse(message.content)

        investigation = await self.investigation_repo.get_by_id(
            investigation_data["id"]
        )
        usage = getattr(message, "usage_metadata", None) or {}
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        token_count = input_tokens + output_tokens

        risk_analysis = RiskAnalysis(
            investigation=investigation,
            risk_score=int(result["risk_score"]),
            justification=result["justification"],
            anomalous_patterns=result.get("anomalous_patterns", []),
            human_summary=result["human_summary"],
            model_used=getattr(self.llm, "model_name", "gemini-2.0-flash"),
            token_count=token_count,
        )
        risk_analysis = await self.risk_analysis_repo.save(risk_analysis)

        duration_ms = int((time.monotonic() - start) * 1000)
        cost_usd = estimate_cost(input_tokens, output_tokens)
        await self.audit_service.log_agent_event(
            alert_id=str(state["alert_id"]),
            event_type="RISK_ANALYSIS",
            agent_name="RiskAnalyzerAgent",
            input_snapshot={"investigation_id": investigation_data["id"]},
            output_snapshot={
                "risk_score": risk_analysis.risk_score,
                "justification": risk_analysis.justification,
            },
            langfuse_trace_id=state.get("langfuse_trace_id", ""),
            duration_ms=duration_ms,
            token_cost_usd=cost_usd,
        )

        return {
            **state,
            "risk_analysis": {
                "id": str(risk_analysis.id),
                "risk_score": risk_analysis.risk_score,
                "justification": risk_analysis.justification,
                "anomalous_patterns": risk_analysis.anomalous_patterns,
                "human_summary": risk_analysis.human_summary,
            },
        }
