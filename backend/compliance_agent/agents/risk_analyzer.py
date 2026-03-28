from typing import Any

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

from compliance_agent.agents.base import BaseAgent
from compliance_agent.models import RiskAnalysis
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
    ) -> None:
        super().__init__(llm, tracer)
        self.risk_analysis_repo = risk_analysis_repo
        self.investigation_repo = investigation_repo

    async def run(self, state: dict) -> dict:
        investigation_data: dict = state["investigation"]
        alert_data: dict = state["alert_data"]

        chain = RISK_PROMPT | self.llm | JsonOutputParser()
        result = await chain.ainvoke(
            {
                "structured_context": str(investigation_data),
                "amount": alert_data.get("amount", 0),
                "currency": alert_data.get("currency", "USD"),
                "is_pep": alert_data.get("is_pep", False),
                "xgboost_score": alert_data.get("xgboost_score", "N/A"),
                "tx_count": investigation_data.get("transaction_count_90d", 0),
                "total_amount": investigation_data.get("total_amount_90d", 0),
                "countries": investigation_data.get("countries", []),
                "currencies": investigation_data.get("currencies", []),
            }
        )

        investigation = await self.investigation_repo.get_by_id(investigation_data["id"])
        usage_metadata = getattr(self.llm, "last_token_usage", {})
        token_count = usage_metadata.get("total_tokens", 0)

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
