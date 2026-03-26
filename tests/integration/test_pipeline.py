import pytest


@pytest.mark.asyncio
@pytest.mark.integration
async def test_full_pipeline_non_pep(mock_llm, mock_bq_tool, mock_gcs_tool, mock_tracer, sample_alert):
    """Integration stub: full pipeline for a non-PEP alert."""
    pass


@pytest.mark.asyncio
@pytest.mark.integration
async def test_full_pipeline_pep_always_escalates(mock_llm, mock_bq_tool, mock_gcs_tool, mock_tracer, sample_pep_alert):
    """Integration stub: PEP alerts must always produce ESCALATE."""
    pass
