from typing import Any
from uuid import UUID

from compliance_agent.models import AuditLog
from compliance_agent.repositories.interfaces import IAuditLogRepository


class AuditLogRepository(IAuditLogRepository):
    def create(self, **kwargs: Any) -> AuditLog:
        return AuditLog.objects.create(**kwargs)

    def get_by_alert_id(self, alert_id: UUID) -> list[AuditLog]:
        return list(AuditLog.objects.filter(alert_id=alert_id).order_by("created_at"))
