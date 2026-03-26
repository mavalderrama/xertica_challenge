from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_pep_escalation_reason_contains_regulations():
    from compliance_agent.agents.decision_agent import PEP_ESCALATION_REASON

    assert "UIAF" in PEP_ESCALATION_REASON
    assert "CNBV" in PEP_ESCALATION_REASON
    assert "SBS" in PEP_ESCALATION_REASON


def test_decision_types():
    from compliance_agent.models import Decision

    assert Decision.DecisionType.ESCALATE == "ESCALATE"
    assert Decision.DecisionType.DISMISS == "DISMISS"
    assert Decision.DecisionType.REQUEST_INFO == "REQUEST_INFO"


@pytest.mark.asyncio
async def test_pep_hard_rule_skips_llm(mock_llm, mock_tracer):
    retriever = MagicMock()
    retriever.retrieve = AsyncMock(return_value=[])

    saved_decision = MagicMock()
    saved_decision.id = "decision-id"
    saved_decision.decision_type = "ESCALATE"
    saved_decision.confidence = 1.0
    saved_decision.regulations_cited = []
    saved_decision.step_by_step_reasoning = "PEP hard rule"
    saved_decision.is_pep_override_applied = True

    decision_repo = MagicMock()
    decision_repo.save.return_value = saved_decision

    from compliance_agent.agents.decision_agent import DecisionAgent

    agent = DecisionAgent(
        llm=mock_llm,
        tracer=mock_tracer,
        retriever=retriever,
        decision_repo=decision_repo,
    )

    state = {
        "alert_id": "some-alert-id",
        "alert_data": {"is_pep": True, "amount": 500000, "currency": "MXN"},
        "risk_analysis": {
            "id": "risk-id",
            "risk_score": 9,
            "justification": "PEP test",
            "anomalous_patterns": [],
            "human_summary": "PEP alert",
        },
        "errors": [],
        "langfuse_trace_id": "",
    }

    mock_ra = MagicMock()

    with (
        patch("compliance_agent.agents.decision_agent.RiskAnalysis") as mock_ra_cls,  # noqa: N806
        patch("compliance_agent.agents.decision_agent.AuditLog"),
        patch("compliance_agent.agents.decision_agent.Decision") as mock_decision_cls,  # noqa: N806
    ):
        mock_ra_cls.objects.get.return_value = mock_ra
        mock_decision_cls.DecisionType.ESCALATE = "ESCALATE"
        mock_decision_instance = MagicMock()
        mock_decision_instance.decision_type = "ESCALATE"
        mock_decision_instance.is_pep_override_applied = True
        mock_decision_cls.return_value = mock_decision_instance
        decision_repo.save.return_value = mock_decision_instance

        result = await agent.run(state)

    mock_llm.ainvoke.assert_not_called()
    assert result["decision"]["decision_type"] == "ESCALATE"
    assert result["decision"]["is_pep_override_applied"] is True
    retriever.retrieve.assert_not_called()
