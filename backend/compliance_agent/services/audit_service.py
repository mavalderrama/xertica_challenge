from decimal import Decimal
from typing import Any

from compliance_agent.repositories.interfaces import IAuditLogRepository


class AuditService:
    def __init__(self, audit_log_repo: IAuditLogRepository) -> None:
        self.audit_log_repo = audit_log_repo

    async def log_agent_event(
        self,
        alert_id: str,
        event_type: str,
        agent_name: str,
        input_snapshot: dict,
        output_snapshot: dict,
        langfuse_trace_id: str = "",
        duration_ms: int = 0,
        token_cost_usd: float = 0.0,
    ) -> Any:
        return await self.audit_log_repo.create(
            alert_id=alert_id,
            event_type=event_type,
            agent_name=agent_name,
            input_snapshot=input_snapshot,
            output_snapshot=output_snapshot,
            langfuse_trace_id=langfuse_trace_id,
            duration_ms=duration_ms,
            token_cost_usd=Decimal(str(token_cost_usd)),
        )

    async def get_audit_trail(self, alert_id: str) -> list[Any]:
        return await self.audit_log_repo.get_by_alert_id(alert_id)
