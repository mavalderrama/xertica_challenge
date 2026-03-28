"""Tests for model field definitions (no DB required — only introspecting _meta)."""


def test_alert_has_required_fields():
    from compliance_agent.models import Alert

    field_names = {f.name for f in Alert._meta.get_fields()}
    assert "external_alert_id" in field_names
    assert "customer_id" in field_names
    assert "is_pep" in field_names
    assert "amount" in field_names
    assert "status" in field_names
    assert "xgboost_score" in field_names


def test_alert_status_choices():
    from compliance_agent.models import Alert

    statuses = {c.value for c in Alert.Status}
    assert "PENDING" in statuses
    assert "ESCALATED" in statuses
    assert "DISMISSED" in statuses


def test_investigation_has_required_fields():
    from compliance_agent.models import Investigation

    field_names = {f.name for f in Investigation._meta.get_fields()}
    assert "transaction_history" in field_names
    assert "structured_context" in field_names
    assert "duration_seconds" in field_names


def test_risk_analysis_has_required_fields():
    from compliance_agent.models import RiskAnalysis

    field_names = {f.name for f in RiskAnalysis._meta.get_fields()}
    assert "risk_score" in field_names
    assert "justification" in field_names
    assert "anomalous_patterns" in field_names
    assert "token_count" in field_names


def test_decision_has_pep_override_field():
    from compliance_agent.models import Decision

    field_names = {f.name for f in Decision._meta.get_fields()}
    assert "is_pep_override_applied" in field_names
    assert "regulations_cited" in field_names
    assert "step_by_step_reasoning" in field_names


def test_audit_log_has_langfuse_field():
    from compliance_agent.models import AuditLog

    field_names = {f.name for f in AuditLog._meta.get_fields()}
    assert "langfuse_trace_id" in field_names
    assert "token_cost_usd" in field_names
    assert "duration_ms" in field_names


def test_regulation_document_sources():
    from compliance_agent.models import RegulationDocument

    sources = {c.value for c in RegulationDocument.Source}
    assert "UIAF" in sources
    assert "CNBV" in sources
    assert "SBS" in sources


def test_regulation_document_has_search_vector():
    from compliance_agent.models import RegulationDocument

    field_names = {f.name for f in RegulationDocument._meta.get_fields()}
    assert "search_vector" in field_names
    assert "related_articles" in field_names


def test_regulation_document_embedding_dimensions():
    from compliance_agent.models import RegulationDocument

    field = RegulationDocument._meta.get_field("embedding")
    assert field.dimensions == 384


def test_observability_cost_estimation():
    from compliance_agent.observability.langfuse_config import estimate_cost

    cost = estimate_cost(input_tokens=1000, output_tokens=500)
    assert cost > 0
    assert isinstance(cost, float)


def test_observability_zero_tokens():
    from compliance_agent.observability.langfuse_config import estimate_cost

    cost = estimate_cost(input_tokens=0, output_tokens=0)
    assert cost == 0.0
