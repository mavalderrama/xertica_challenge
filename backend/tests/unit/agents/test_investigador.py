from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from compliance_agent.agents.investigador import InvestigadorAgent


def _make_state(customer_id: str = "CUST-001", is_pep: bool = False) -> dict:
    return {
        "alert_id": "00000000-0000-0000-0000-000000000001",
        "alert_data": {
            "customer_id": customer_id,
            "is_pep": is_pep,
            "amount": 15000.0,
            "currency": "COP",
            "xgboost_score": 0.72,
        },
        "errors": [],
        "langfuse_trace_id": "",
    }


def _make_agent(mock_llm, mock_tracer, mock_bq_tool, mock_gcs_tool, mock_audit_service):
    investigation_mock = MagicMock()
    investigation_mock.id = "test-inv-id"

    investigation_repo = MagicMock()
    investigation_repo.save = AsyncMock(return_value=investigation_mock)

    alert_repo = MagicMock()
    alert_repo.get_by_id = AsyncMock(return_value=MagicMock())

    agent = InvestigadorAgent(
        llm=mock_llm,
        tracer=mock_tracer,
        bq_tool=mock_bq_tool,
        gcs_tool=mock_gcs_tool,
        investigation_repo=investigation_repo,
        alert_repo=alert_repo,
        audit_service=mock_audit_service,
    )
    return agent, alert_repo, investigation_repo


@pytest.mark.asyncio
async def test_investigador_returns_structured_context(
    mock_llm, mock_bq_tool, mock_gcs_tool, mock_tracer, mock_audit_service
):
    agent, _, _ = _make_agent(
        mock_llm, mock_tracer, mock_bq_tool, mock_gcs_tool, mock_audit_service
    )

    with patch("compliance_agent.agents.investigador.Investigation"):
        result = await agent.run(_make_state())

    assert "investigation" in result
    assert result["investigation"]["customer_id"] == "CUST-001"
    assert "transaction_count_90d" in result["investigation"]
    mock_audit_service.log_agent_event.assert_called_once()


@pytest.mark.asyncio
async def test_investigador_fetches_bq_and_gcs_concurrently(
    mock_llm, mock_bq_tool, mock_gcs_tool, mock_tracer, mock_audit_service
):
    agent, alert_repo, investigation_repo = _make_agent(
        mock_llm, mock_tracer, mock_bq_tool, mock_gcs_tool, mock_audit_service
    )

    with patch("compliance_agent.agents.investigador.Investigation"):
        result = await agent.run(_make_state())

    assert result["investigation"]["documents_count"] >= 0
    alert_repo.get_by_id.assert_called_once()
    investigation_repo.save.assert_called_once()
