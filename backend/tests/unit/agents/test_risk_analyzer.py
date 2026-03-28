from unittest.mock import MagicMock

import pytest


@pytest.mark.asyncio
async def test_risk_analyzer_creates_agent_without_error(mock_llm, mock_tracer, mock_audit_service):
    from compliance_agent.agents.risk_analyzer import RiskAnalyzerAgent

    risk_repo = MagicMock()
    investigation_repo = MagicMock()
    agent = RiskAnalyzerAgent(
        llm=mock_llm,
        tracer=mock_tracer,
        risk_analysis_repo=risk_repo,
        investigation_repo=investigation_repo,
        audit_service=mock_audit_service,
    )
    assert agent.llm is mock_llm
    assert agent.risk_analysis_repo is risk_repo
    assert agent.investigation_repo is investigation_repo


@pytest.mark.asyncio
async def test_risk_score_validation():
    from compliance_agent.models import RiskAnalysis

    field = RiskAnalysis._meta.get_field("risk_score")
    assert field is not None


def test_risk_analyzer_prompt_has_required_fields():
    from compliance_agent.agents.risk_analyzer import RISK_PROMPT

    prompt_str = str(RISK_PROMPT)
    assert "risk_score" in prompt_str
    assert "justification" in prompt_str
    assert "anomalous_patterns" in prompt_str
