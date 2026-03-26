from typing import Any

from compliance_agent.graph.state import PipelineState
from compliance_agent.repositories.interfaces import IAlertRepository


class PipelineService:
    def __init__(
        self,
        compiled_graph: Any,
        alert_repo: IAlertRepository,
    ) -> None:
        self.compiled_graph = compiled_graph
        self.alert_repo = alert_repo

    async def process_alert(
        self, alert_id: str, langfuse_trace_id: str = ""
    ) -> PipelineState:
        from compliance_agent.models import Alert

        alert = self.alert_repo.get_by_id(alert_id)
        alert_data = {
            "customer_id": alert.customer_id,
            "is_pep": alert.is_pep,
            "amount": float(alert.amount),
            "currency": alert.currency,
            "transaction_date": alert.transaction_date.isoformat(),
            "xgboost_score": alert.xgboost_score,
            "external_alert_id": alert.external_alert_id,
        }

        initial_state: PipelineState = {
            "alert_id": str(alert.id),
            "alert_data": alert_data,
            "errors": [],
            "langfuse_trace_id": langfuse_trace_id,
        }

        self.alert_repo.update_status(alert.id, Alert.Status.INVESTIGATING)
        final_state = await self.compiled_graph.ainvoke(initial_state)

        decision_type = final_state.get("decision", {}).get("decision_type", "")
        if decision_type == "ESCALATE":
            self.alert_repo.update_status(alert.id, Alert.Status.ESCALATED)
        elif decision_type == "DISMISS":
            self.alert_repo.update_status(alert.id, Alert.Status.DISMISSED)
        elif decision_type == "REQUEST_INFO":
            self.alert_repo.update_status(alert.id, Alert.Status.AWAITING_INFO)

        return final_state
