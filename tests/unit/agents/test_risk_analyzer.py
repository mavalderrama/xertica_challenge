import pytest


@pytest.mark.asyncio
async def test_risk_analyzer_creates_agent_without_error(mock_llm, mock_tracer):
    from unittest.mock import MagicMock

    from compliance_agent.agents.risk_analyzer import RiskAnalyzerAgent

    repo = MagicMock()
    agent = RiskAnalyzerAgent(llm=mock_llm, tracer=mock_tracer, risk_analysis_repo=repo)
    assert agent.llm is mock_llm
    assert agent.risk_analysis_repo is repo


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
