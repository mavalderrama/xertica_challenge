import pytest

from compliance_agent.tools import MockGCSTool


@pytest.mark.asyncio
async def test_mock_gcs_extract_pdf_returns_text():
    tool = MockGCSTool()
    text = await tool.extract_pdf_text("gs://mock-bucket/doc.pdf")
    assert isinstance(text, str)
    assert len(text) > 0


@pytest.mark.asyncio
async def test_mock_gcs_list_documents_returns_uris():
    tool = MockGCSTool()
    uris = await tool.list_customer_documents("CUST-001")
    assert isinstance(uris, list)
    assert all(uri.startswith("gs://") for uri in uris)
    assert len(uris) > 0


@pytest.mark.asyncio
async def test_mock_gcs_list_contains_customer_id():
    tool = MockGCSTool()
    customer_id = "CUST-TEST-99"
    uris = await tool.list_customer_documents(customer_id)
    assert all(customer_id in uri for uri in uris)
