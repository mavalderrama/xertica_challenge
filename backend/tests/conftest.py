import os
from datetime import UTC

import pytest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")


def pytest_configure(config):
    os.environ["USE_MOCK_BQ"] = "true"
    os.environ["USE_MOCK_GCS"] = "true"


@pytest.fixture(scope="session")
def django_db_setup():
    pass


@pytest.fixture
def mock_llm():
    from unittest.mock import AsyncMock, MagicMock

    llm = MagicMock()
    llm.ainvoke = AsyncMock(
        return_value=MagicMock(
            content='{"risk_score": 7, "justification": "test", "anomalous_patterns": [], "human_summary": "test"}'
        )
    )
    return llm


@pytest.fixture
def mock_bq_tool():
    from compliance_agent.tools import MockBigQueryTool

    return MockBigQueryTool()


@pytest.fixture
def mock_gcs_tool():
    from compliance_agent.tools import MockGCSTool

    return MockGCSTool()


@pytest.fixture
def mock_tracer():
    from unittest.mock import MagicMock

    return MagicMock()


@pytest.fixture
def mock_audit_service():
    from unittest.mock import AsyncMock, MagicMock

    service = MagicMock()
    service.log_agent_event = AsyncMock()
    return service


@pytest.fixture
def sample_alert(db):
    from datetime import datetime

    from compliance_agent.models import Alert

    return Alert.objects.create(
        external_alert_id="TEST-ALERT-001",
        customer_id="CUST-001",
        is_pep=False,
        amount="15000.00",
        currency="COP",
        transaction_date=datetime(2026, 3, 25, 12, 0, 0, tzinfo=UTC),
        status=Alert.Status.PENDING,
        xgboost_score=0.72,
    )


@pytest.fixture
def sample_pep_alert(db):
    from datetime import datetime

    from compliance_agent.models import Alert

    return Alert.objects.create(
        external_alert_id="TEST-PEP-ALERT-001",
        customer_id="CUST-PEP-001",
        is_pep=True,
        amount="500000.00",
        currency="MXN",
        transaction_date=datetime(2026, 3, 25, 12, 0, 0, tzinfo=UTC),
        status=Alert.Status.PENDING,
        xgboost_score=0.91,
    )


@pytest.fixture
def ghost_probe_alert(db):
    """Edge case: CRITICAL xgboost score (0.97) on a trivially small USD amount ($75).
    Tests that the ML signal dominates over the low-amount heuristic."""
    from datetime import datetime

    from compliance_agent.models import Alert

    return Alert.objects.create(
        external_alert_id="TEST-GHOST-PROBE-029",
        customer_id="CUST-PROBE-029",
        is_pep=False,
        amount="75.00",
        currency="USD",
        transaction_date=datetime(2026, 3, 25, 3, 47, 0, tzinfo=UTC),
        status=Alert.Status.PENDING,
        xgboost_score=0.97,
        raw_payload={"alert_type": "ANOMALY_SCORE_CRITICAL", "segment": "retail_individual"},
    )


@pytest.fixture
def pep_phantom_alert(db):
    """Edge case: PEP=True but every other signal says DISMISS (EUR 0.01, xgb=0.02).
    Tests that the PEP hard-rule is truly unconditional."""
    from datetime import datetime

    from compliance_agent.models import Alert

    return Alert.objects.create(
        external_alert_id="TEST-PEP-PHANTOM-030",
        customer_id="CUST-PEP-030",
        is_pep=True,
        amount="0.01",
        currency="EUR",
        transaction_date=datetime(2026, 3, 25, 9, 0, 0, tzinfo=UTC),
        status=Alert.Status.PENDING,
        xgboost_score=0.02,
        raw_payload={"alert_type": "ROUTINE_CHECK", "segment": "high_value_individual"},
    )
