from uuid import UUID

from compliance_agent.models import Alert
from compliance_agent.repositories.interfaces import IAlertRepository


class AlertRepository(IAlertRepository):
    def get_by_id(self, alert_id: UUID) -> Alert:
        return Alert.objects.get(pk=alert_id)

    def get_by_external_id(self, external_id: str) -> Alert:
        return Alert.objects.get(external_alert_id=external_id)

    def save(self, alert: Alert) -> Alert:
        alert.save()
        return alert

    def update_status(self, alert_id: UUID, status: str) -> Alert:
        Alert.objects.filter(pk=alert_id).update(status=status)
        return Alert.objects.get(pk=alert_id)
