from uuid import UUID

from compliance_agent.models import Investigation
from compliance_agent.repositories.interfaces import IInvestigationRepository


class InvestigationRepository(IInvestigationRepository):
    async def get_by_alert_id(self, alert_id: UUID) -> Investigation:
        return await Investigation.objects.aget(alert_id=alert_id)

    async def get_by_id(self, investigation_id: UUID) -> Investigation:
        return await Investigation.objects.aget(pk=investigation_id)

    async def save(self, investigation: Investigation) -> Investigation:
        await investigation.asave()
        return investigation
