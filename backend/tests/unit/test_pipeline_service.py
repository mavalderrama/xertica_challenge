"""
Unit tests for PipelineService.

All repositories and the compiled graph are fully mocked — no DB or LLM calls.
Written for the refactored async interface where all repo methods are awaitable.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest


def _mock_alert(*, is_pep: bool = False, alert_id: str | None = None):
    """Build a MagicMock that quacks like an Alert model instance."""
    alert = MagicMock()
    alert.id = uuid.UUID(alert_id) if alert_id else uuid.uuid4()
    alert.external_alert_id = "EXT-001"
    alert.customer_id = "CUST-001"
    alert.is_pep = is_pep
    alert.amount = Decimal("15000.00")
    alert.currency = "COP"
    alert.transaction_date = datetime(2026, 3, 25, tzinfo=UTC)
    alert.xgboost_score = 0.72
    return alert


@pytest.mark.asyncio
async def test_process_alert_sets_investigating_status():
    """process_alert transitions alert to INVESTIGATING then to the final status."""
    from compliance_agent.models import Alert
    from compliance_agent.services import PipelineService

    alert = _mock_alert()

    mock_alert_repo = MagicMock()
    mock_alert_repo.get_by_id = AsyncMock(return_value=alert)
    mock_alert_repo.update_status = AsyncMock(return_value=alert)

    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(
        return_value={
            "alert_id": str(alert.id),
            "alert_data": {},
            "decision": {"decision_type": "DISMISS"},
            "errors": [],
            "langfuse_trace_id": "",
        }
    )

    service = PipelineService(compiled_graph=mock_graph, alert_repo=mock_alert_repo)
    await service.process_alert(str(alert.id))

    assert mock_alert_repo.update_status.call_count == 2
    status_calls = mock_alert_repo.update_status.call_args_list
    assert status_calls[0][0][1] == Alert.Status.INVESTIGATING
    assert status_calls[1][0][1] == Alert.Status.DISMISSED


@pytest.mark.asyncio
async def test_process_alert_pep_escalates():
    """PEP alert's final status is ESCALATED."""
    from compliance_agent.models import Alert
    from compliance_agent.services import PipelineService

    alert = _mock_alert(is_pep=True)

    mock_alert_repo = MagicMock()
    mock_alert_repo.get_by_id = AsyncMock(return_value=alert)
    mock_alert_repo.update_status = AsyncMock(return_value=alert)

    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(
        return_value={
            "alert_id": str(alert.id),
            "alert_data": {},
            "decision": {"decision_type": "ESCALATE"},
            "errors": [],
        }
    )

    service = PipelineService(compiled_graph=mock_graph, alert_repo=mock_alert_repo)
    await service.process_alert(str(alert.id))

    status_calls = mock_alert_repo.update_status.call_args_list
    assert status_calls[0][0][1] == Alert.Status.INVESTIGATING
    assert status_calls[1][0][1] == Alert.Status.ESCALATED


@pytest.mark.asyncio
async def test_process_alert_request_info_sets_awaiting_info():
    """REQUEST_INFO decision transitions alert to AWAITING_INFO."""
    from compliance_agent.models import Alert
    from compliance_agent.services import PipelineService

    alert = _mock_alert()

    mock_alert_repo = MagicMock()
    mock_alert_repo.get_by_id = AsyncMock(return_value=alert)
    mock_alert_repo.update_status = AsyncMock(return_value=alert)

    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(
        return_value={
            "alert_id": str(alert.id),
            "alert_data": {},
            "decision": {"decision_type": "REQUEST_INFO"},
            "errors": [],
        }
    )

    service = PipelineService(compiled_graph=mock_graph, alert_repo=mock_alert_repo)
    await service.process_alert(str(alert.id))

    status_calls = mock_alert_repo.update_status.call_args_list
    assert status_calls[1][0][1] == Alert.Status.AWAITING_INFO


@pytest.mark.asyncio
async def test_process_alert_passes_langfuse_trace_id():
    """process_alert forwards an explicit langfuse_trace_id into the initial state."""
    from compliance_agent.services import PipelineService

    alert = _mock_alert()

    mock_alert_repo = MagicMock()
    mock_alert_repo.get_by_id = AsyncMock(return_value=alert)
    mock_alert_repo.update_status = AsyncMock(return_value=alert)

    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(
        return_value={
            "alert_id": str(alert.id),
            "alert_data": {},
            "decision": {"decision_type": "DISMISS"},
            "errors": [],
            "langfuse_trace_id": "my-trace-id",
        }
    )

    service = PipelineService(compiled_graph=mock_graph, alert_repo=mock_alert_repo)
    await service.process_alert(str(alert.id), langfuse_trace_id="my-trace-id")

    invoked_state = mock_graph.ainvoke.call_args[0][0]
    assert invoked_state["langfuse_trace_id"] == "my-trace-id"


@pytest.mark.asyncio
async def test_process_alert_no_decision_does_not_update_final_status():
    """If graph returns no recognised decision_type, only INVESTIGATING is set."""
    from compliance_agent.models import Alert
    from compliance_agent.services import PipelineService

    alert = _mock_alert()

    mock_alert_repo = MagicMock()
    mock_alert_repo.get_by_id = AsyncMock(return_value=alert)
    mock_alert_repo.update_status = AsyncMock(return_value=alert)

    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(
        return_value={
            "alert_id": str(alert.id),
            "alert_data": {},
            "decision": {},
            "errors": [],
        }
    )

    service = PipelineService(compiled_graph=mock_graph, alert_repo=mock_alert_repo)
    await service.process_alert(str(alert.id))

    assert mock_alert_repo.update_status.call_count == 1
    assert mock_alert_repo.update_status.call_args[0][1] == Alert.Status.INVESTIGATING
