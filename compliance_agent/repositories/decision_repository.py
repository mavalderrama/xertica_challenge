from uuid import UUID

from compliance_agent.models import Decision
from compliance_agent.repositories.interfaces import IDecisionRepository


class DecisionRepository(IDecisionRepository):
    def get_by_risk_analysis_id(self, risk_analysis_id: UUID) -> Decision:
        return Decision.objects.get(risk_analysis_id=risk_analysis_id)

    def save(self, decision: Decision) -> Decision:
        decision.save()
        return decision
