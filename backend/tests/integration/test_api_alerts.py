import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from compliance_agent.api.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.mark.asyncio
async def test_health_endpoint(app):
    """GET /health returns 200 with status ok."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_readiness_endpoint(app):
    """GET /readiness returns 200 when DB is reachable."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/readiness")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_investigate_alert_endpoint(app, sample_alert):
    """POST /api/v1/alerts/{id}/investigate returns investigation result."""
    mock_pipeline_service = MagicMock()
    mock_pipeline_service.process_alert = AsyncMock(
        return_value={
            "alert_id": str(sample_alert.id),
            "alert_data": {},
            "investigation": {
                "id": str(uuid.uuid4()),
                "transaction_count_90d": 5,
            },
            "risk_analysis": {
                "id": str(uuid.uuid4()),
                "risk_score": 3,
                "justification": "Low risk",
                "anomalous_patterns": [],
                "human_summary": "Normal transaction",
            },
            "decision": {
                "id": str(uuid.uuid4()),
                "decision_type": "DISMISS",
                "confidence": 0.9,
                "regulations_cited": [],
                "step_by_step_reasoning": "Low risk, no anomalies",
                "is_pep_override_applied": False,
            },
            "errors": [],
            "langfuse_trace_id": "",
        }
    )

    # get_pipeline_service is used via FastAPI Depends in the alerts router.
    # Patch the dependency at the source location used by the router.
    with patch(
        "compliance_agent.api.dependencies.get_pipeline_service",
        return_value=mock_pipeline_service,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                f"/api/v1/alerts/{sample_alert.id}/investigate"
            )

    assert response.status_code == 200
    data = response.json()
    assert data["alert_id"] == str(sample_alert.id)
    assert data["risk_analysis"]["risk_score"] == 3
    assert data["decision"]["decision_type"] == "DISMISS"
