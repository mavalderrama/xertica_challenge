from uuid import UUID

from compliance_agent.models import Investigation
from compliance_agent.repositories.interfaces import IInvestigationRepository


class InvestigationRepository(IInvestigationRepository):
    def get_by_alert_id(self, alert_id: UUID) -> Investigation:
        return Investigation.objects.get(alert_id=alert_id)

    def save(self, investigation: Investigation) -> Investigation:
        investigation.save()
        return investigation
