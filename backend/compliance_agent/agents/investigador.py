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
        audit_service: Any,
    ) -> None:
        super().__init__(llm, tracer)
        self.bq_tool = bq_tool
        self.gcs_tool = gcs_tool
        self.investigation_repo = investigation_repo
        self.alert_repo = alert_repo
        self.audit_service = audit_service

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

        customer_profile = self._extract_customer_profile(documents_analyzed)

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
            "customer_profile": customer_profile,
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

        duration_ms = int(duration * 1000)
        await self.audit_service.log_agent_event(
            alert_id=alert_id,
            event_type="INVESTIGATION",
            agent_name="InvestigadorAgent",
            input_snapshot={"customer_id": customer_id},
            output_snapshot=structured_context,
            langfuse_trace_id=state.get("langfuse_trace_id", ""),
            duration_ms=duration_ms,
            token_cost_usd=0.0,
        )

        return {**state, "investigation": {"id": str(investigation.id), **structured_context}}

    @staticmethod
    def _extract_customer_profile(documents_analyzed: list[dict]) -> dict:
        """
        Parse KYC profile fields from document text.

        Looks for lines of the form "- Key: Value" in the first document that
        contains a KYC profile section. Returns a dict of extracted fields.
        """
        import re

        _FIELD_RE = re.compile(r"^-\s+([^:]+):\s+(.+)$")
        _FIELD_MAP = {
            "account opened": "account_opened",
            "kyc status": "kyc_status",
            "last kyc update": "last_kyc_update",
            "risk category": "risk_category",
            "segment": "segment",
            "declared profession": "declared_profession",
            "annual declared income": "annual_declared_income",
            "country of residence": "country",
            "previous alerts": "previous_alerts",
            "escalated alerts": "escalated_alerts",
            "notes": "compliance_notes",
        }

        for doc in documents_analyzed:
            text = doc.get("text", "")
            if "KYC Profile" not in text and "Customer Profile" not in text:
                continue
            profile: dict = {}
            for line in text.splitlines():
                m = _FIELD_RE.match(line.strip())
                if not m:
                    continue
                key_raw = m.group(1).strip().lower()
                value = m.group(2).strip()
                mapped = _FIELD_MAP.get(key_raw)
                if mapped:
                    profile[mapped] = value
            if profile:
                return profile

        return {}
