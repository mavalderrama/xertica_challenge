import pytest

from compliance_agent.tools import MockBigQueryTool


@pytest.mark.asyncio
async def test_mock_bq_returns_transactions():
    tool = MockBigQueryTool()
    txns = await tool.get_transaction_history("CUST-001", days=90)
    assert isinstance(txns, list)
    assert len(txns) > 0


@pytest.mark.asyncio
async def test_mock_bq_transaction_fields():
    tool = MockBigQueryTool()
    txns = await tool.get_transaction_history("CUST-001")
    required_fields = {"transaction_id", "amount", "currency", "transaction_date"}
    assert required_fields.issubset(txns[0].keys())


@pytest.mark.asyncio
async def test_mock_bq_deterministic_for_same_customer():
    tool = MockBigQueryTool()
    txns1 = await tool.get_transaction_history("CUST-XYZ")
    txns2 = await tool.get_transaction_history("CUST-XYZ")
    assert len(txns1) == len(txns2)
    assert txns1[0]["transaction_id"] == txns2[0]["transaction_id"]


@pytest.mark.asyncio
async def test_mock_bq_sorted_by_date_desc():
    tool = MockBigQueryTool()
    txns = await tool.get_transaction_history("CUST-001")
    dates = [t["transaction_date"] for t in txns]
    assert dates == sorted(dates, reverse=True)
