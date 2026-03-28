from uuid import UUID

from compliance_agent.models import Alert
from compliance_agent.repositories.interfaces import IAlertRepository


class AlertRepository(IAlertRepository):
    async def get_by_id(self, alert_id: UUID) -> Alert:
        return await Alert.objects.aget(pk=alert_id)

    async def get_by_external_id(self, external_id: str) -> Alert:
        return await Alert.objects.aget(external_alert_id=external_id)

    async def save(self, alert: Alert) -> Alert:
        await alert.asave()
        return alert

    async def update_status(self, alert_id: UUID, status: str) -> Alert:
        await Alert.objects.filter(pk=alert_id).aupdate(status=status)
        return await Alert.objects.aget(pk=alert_id)
