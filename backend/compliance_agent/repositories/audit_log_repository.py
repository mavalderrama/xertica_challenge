from typing import Any
from uuid import UUID

from compliance_agent.models import AuditLog
from compliance_agent.repositories.interfaces import IAuditLogRepository


class AuditLogRepository(IAuditLogRepository):
    async def create(self, **kwargs: Any) -> AuditLog:
        return await AuditLog.objects.acreate(**kwargs)

    async def get_by_alert_id(self, alert_id: UUID) -> list[AuditLog]:
        return [
            log
            async for log in AuditLog.objects.filter(alert_id=alert_id).order_by(
                "created_at"
            )
        ]
