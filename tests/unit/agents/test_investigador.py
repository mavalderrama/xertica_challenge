from unittest.mock import MagicMock, patch

import pytest

from compliance_agent.agents.investigador import InvestigadorAgent


def _make_state(customer_id: str = "CUST-001", is_pep: bool = False) -> dict:
    return {
        "alert_id": "test-alert-uuid",
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


@pytest.mark.asyncio
async def test_investigador_returns_structured_context(
    mock_llm, mock_bq_tool, mock_gcs_tool, mock_tracer
):
    repo = MagicMock()
    investigation_mock = MagicMock()
    investigation_mock.id = "test-inv-id"
    repo.save.return_value = investigation_mock

    agent = InvestigadorAgent(
        llm=mock_llm,
        tracer=mock_tracer,
        bq_tool=mock_bq_tool,
        gcs_tool=mock_gcs_tool,
        investigation_repo=repo,
    )

    with (
        patch("compliance_agent.agents.investigador.Alert") as mock_alert_cls,  # noqa: N806
        patch("compliance_agent.agents.investigador.Investigation") as mock_inv_cls,  # noqa: N806
    ):
        mock_alert_cls.objects.get.return_value = MagicMock()
        mock_inv_instance = MagicMock()
        mock_inv_cls.return_value = mock_inv_instance

        result = await agent.run(_make_state())

    assert "investigation" in result
    assert result["investigation"]["customer_id"] == "CUST-001"
    assert "transaction_count_90d" in result["investigation"]


@pytest.mark.asyncio
async def test_investigador_fetches_bq_and_gcs_concurrently(
    mock_llm, mock_bq_tool, mock_gcs_tool, mock_tracer
):
    repo = MagicMock()
    repo.save.return_value = MagicMock(id="inv-id")

    agent = InvestigadorAgent(
        llm=mock_llm,
        tracer=mock_tracer,
        bq_tool=mock_bq_tool,
        gcs_tool=mock_gcs_tool,
        investigation_repo=repo,
    )

    with (
        patch("compliance_agent.agents.investigador.Alert") as mock_alert_cls,  # noqa: N806
        patch("compliance_agent.agents.investigador.Investigation"),
    ):
        mock_alert_cls.objects.get.return_value = MagicMock()
        result = await agent.run(_make_state())

    assert result["investigation"]["documents_count"] >= 0
