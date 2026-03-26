import os
import random
from datetime import UTC, datetime, timedelta

from compliance_agent.tools.base import BigQueryToolInterface


class BigQueryTool(BigQueryToolInterface):
    """Real BigQuery implementation using the GCP SDK."""

    def __init__(self, project_id: str | None = None) -> None:
        self.project_id = project_id or os.environ.get("GCP_PROJECT_ID", "")

    async def get_transaction_history(
        self, customer_id: str, days: int = 90
    ) -> list[dict]:
        from google.cloud import bigquery

        client = bigquery.Client(project=self.project_id)
        query = f"""
            SELECT transaction_id, amount, currency, transaction_date, merchant_id,
                   transaction_type, country_code
            FROM `{self.project_id}.compliance.transactions`
            WHERE customer_id = @customer_id
              AND transaction_date >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @days DAY)
            ORDER BY transaction_date DESC
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("customer_id", "STRING", customer_id),
                bigquery.ScalarQueryParameter("days", "INT64", days),
            ]
        )
        results = client.query(query, job_config=job_config).result()
        return [dict(row) for row in results]


class MockBigQueryTool(BigQueryToolInterface):
    """Returns synthetic transaction data for local development and testing."""

    async def get_transaction_history(
        self, customer_id: str, days: int = 90
    ) -> list[dict]:
        rng = random.Random(customer_id)
        now = datetime.now(tz=UTC)
        transactions = []
        for i in range(rng.randint(10, 30)):
            delta_days = rng.randint(0, days - 1)
            delta_hours = rng.randint(0, 23)
            txn_date = now - timedelta(days=delta_days, hours=delta_hours)
            transactions.append(
                {
                    "transaction_id": f"TXN-{customer_id}-{i:04d}",
                    "amount": round(rng.uniform(100, 50_000), 2),
                    "currency": rng.choice(["COP", "MXN", "PEN", "USD"]),
                    "transaction_date": txn_date.isoformat(),
                    "merchant_id": f"MERCHANT-{rng.randint(1000, 9999)}",
                    "transaction_type": rng.choice(
                        ["TRANSFER", "DEPOSIT", "WITHDRAWAL", "PAYMENT"]
                    ),
                    "country_code": rng.choice(["CO", "MX", "PE"]),
                }
            )
        transactions.sort(key=lambda x: x["transaction_date"], reverse=True)
        return transactions
