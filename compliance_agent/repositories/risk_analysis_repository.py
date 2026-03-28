from compliance_agent.models import RiskAnalysis
from compliance_agent.repositories.interfaces import IRiskAnalysisRepository


class RiskAnalysisRepository(IRiskAnalysisRepository):
    async def get_by_investigation_id(self, investigation_id) -> RiskAnalysis:
        return await RiskAnalysis.objects.aget(investigation_id=investigation_id)

    async def get_by_id(self, id) -> RiskAnalysis:
        return await RiskAnalysis.objects.aget(pk=id)

    async def save(self, risk_analysis: RiskAnalysis) -> RiskAnalysis:
        await risk_analysis.asave()
        return risk_analysis
