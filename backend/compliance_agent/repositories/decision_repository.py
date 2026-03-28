from uuid import UUID

from compliance_agent.models import Decision
from compliance_agent.repositories.interfaces import IDecisionRepository


class DecisionRepository(IDecisionRepository):
    async def get_by_risk_analysis_id(self, risk_analysis_id: UUID) -> Decision:
        return await Decision.objects.aget(risk_analysis_id=risk_analysis_id)

    async def save(self, decision: Decision) -> Decision:
        await decision.asave()
        return decision
