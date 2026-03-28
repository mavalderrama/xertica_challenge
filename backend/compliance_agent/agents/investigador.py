import asyncio
import time
from typing import Any

from compliance_agent.agents.base import BaseAgent
from compliance_agent.models import Investigation
from compliance_agent.repositories.interfaces import (
    IAlertRepository,
    IInvestigationRepository,
)
from compliance_agent.tools.base import BigQueryToolInterface, GCSToolInterface


class InvestigadorAgent(BaseAgent):
    """
    Agent 1: Gathers transaction history from BigQuery and documents from GCS
    concurrently, then builds structured context for downstream agents.
    """

    def __init__(
        self,
        llm: Any,
        tracer: Any,
        bq_tool: BigQueryToolInterface,
        gcs_tool: GCSToolInterface,
        investigation_repo: IInvestigationRepository,
        alert_repo: IAlertRepository,
    ) -> None:
        super().__init__(llm, tracer)
        self.bq_tool = bq_tool
        self.gcs_tool = gcs_tool
        self.investigation_repo = investigation_repo
        self.alert_repo = alert_repo

    async def run(self, state: dict) -> dict:
        alert_data: dict = state["alert_data"]
        customer_id: str = alert_data["customer_id"]
        alert_id: str = str(state["alert_id"])

        start = time.monotonic()

        tx_history, doc_uris = await asyncio.gather(
            self.bq_tool.get_transaction_history(customer_id, days=90),
            self.gcs_tool.list_customer_documents(customer_id),
        )

        doc_texts = await asyncio.gather(
            *[self.gcs_tool.extract_pdf_text(uri) for uri in doc_uris]
        )
        documents_analyzed = [
            {"uri": uri, "text": text} for uri, text in zip(doc_uris, doc_texts, strict=True)
        ]

        total_amount = sum(t.get("amount", 0) for t in tx_history)
        currencies = list({t.get("currency") for t in tx_history})
        countries = list({t.get("country_code") for t in tx_history})

        structured_context = {
            "customer_id": customer_id,
            "transaction_count_90d": len(tx_history),
            "total_amount_90d": total_amount,
            "currencies": currencies,
            "countries": countries,
            "is_pep": alert_data.get("is_pep", False),
            "current_alert_amount": float(alert_data.get("amount", 0)),
            "current_alert_currency": alert_data.get("currency", "USD"),
            "documents_count": len(documents_analyzed),
        }

        duration = time.monotonic() - start

        alert = await self.alert_repo.get_by_id(alert_id)
        investigation = Investigation(
            alert=alert,
            transaction_history=tx_history,
            documents_analyzed=documents_analyzed,
            structured_context=structured_context,
            duration_seconds=round(duration, 3),
        )
        investigation = await self.investigation_repo.save(investigation)

        return {**state, "investigation": {"id": str(investigation.id), **structured_context}}
