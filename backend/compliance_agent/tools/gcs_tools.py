import os

from compliance_agent.tools.base import GCSToolInterface


class GCSTool(GCSToolInterface):
    """Real GCS implementation using the GCP SDK."""

    def __init__(self, bucket_name: str | None = None) -> None:
        self.bucket_name = bucket_name or os.environ.get("GCS_BUCKET_NAME", "")

    async def extract_pdf_text(self, gcs_uri: str) -> str:
        import io

        from google.cloud import storage

        client = storage.Client()
        bucket_name, blob_name = gcs_uri.replace("gs://", "").split("/", 1)
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        pdf_bytes = blob.download_as_bytes()

        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(pdf_bytes))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    async def list_customer_documents(self, customer_id: str) -> list[str]:
        from google.cloud import storage

        client = storage.Client()
        bucket = client.bucket(self.bucket_name)
        prefix = f"customers/{customer_id}/"
        blobs = bucket.list_blobs(prefix=prefix)
        return [f"gs://{self.bucket_name}/{blob.name}" for blob in blobs]


class MockGCSTool(GCSToolInterface):
    """
    Returns per-customer synthetic document text for local development and testing.

    For known test customers (seeded in customer_profiles.json), returns a profile
    that is consistent with the scenario's risk level and expected decision.
    For unknown customers, falls back to a generated profile seeded on customer_id.
    """

    _PROFILES: dict | None = None
    _PROFILES_PATH = (
        os.path.dirname(__file__) + "/../../tests/fixtures/customer_profiles.json"
    )

    @classmethod
    def _load_profiles(cls) -> dict:
        if cls._PROFILES is None:
            import json
            from pathlib import Path

            profiles_file = Path(cls._PROFILES_PATH).resolve()
            cls._PROFILES = (
                json.loads(profiles_file.read_text()) if profiles_file.exists() else {}
            )
        return cls._PROFILES

    async def extract_pdf_text(self, gcs_uri: str) -> str:
        # Extract customer_id from the GCS URI path
        # Expected format: gs://mock-bucket/customers/{customer_id}/filename.pdf
        parts = gcs_uri.rstrip("/").split("/")
        customer_id = parts[-2] if len(parts) >= 2 else "UNKNOWN"

        profiles = self._load_profiles()
        if customer_id in profiles:
            p = profiles[customer_id]
            notes_line = f"- Notes: {p['notes']}\n" if p.get("notes") else ""
            return (
                f"[MOCK PDF] Document: {parts[-1]}  —  Customer: {customer_id}\n\n"
                "=== Customer KYC Profile ===\n"
                f"- Account opened:          {p.get('account_opened', 'N/A')}\n"
                f"- KYC status:              {p.get('kyc_status', 'N/A')}\n"
                f"- Last KYC update:         {p.get('last_kyc_update', 'N/A')}\n"
                f"- Risk category:           {p.get('risk_category', 'N/A')}\n"
                f"- Segment:                 {p.get('segment', 'N/A')}\n"
                f"- Declared profession:     {p.get('declared_profession', 'N/A')}\n"
                f"- Annual declared income:  {p.get('annual_declared_income', 'N/A')}\n"
                f"- Country of residence:    {p.get('country', 'N/A')}\n"
                f"- Previous alerts:         {p.get('previous_alerts', 0)}\n"
                f"- Escalated alerts:        {p.get('escalated_alerts', 0)}\n"
                f"{notes_line}"
            )

        # Fallback: generated profile seeded on customer_id (deterministic)
        import random

        rng = random.Random(customer_id)
        risk_categories = ["LOW", "MEDIUM", "HIGH"]
        segments = ["retail_individual", "sme", "corporate"]
        activities = [
            "Domestic commerce",
            "Import/Export",
            "Salaried employee",
            "Freelance",
        ]
        return (
            f"[MOCK PDF] Document: {parts[-1]}  —  Customer: {customer_id}\n\n"
            "=== Customer KYC Profile ===\n"
            f"- Account opened:          201{rng.randint(5, 9)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}\n"
            f"- KYC status:              VERIFIED\n"
            f"- Last KYC update:         2025-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}\n"
            f"- Risk category:           {rng.choice(risk_categories)}\n"
            f"- Segment:                 {rng.choice(segments)}\n"
            f"- Declared profession:     {rng.choice(activities)}\n"
            f"- Annual declared income:  USD {rng.randint(20, 200) * 1000:,}\n"
            f"- Previous alerts:         {rng.randint(0, 3)}\n"
            f"- Escalated alerts:        {rng.randint(0, 1)}\n"
        )

    async def list_customer_documents(self, customer_id: str) -> list[str]:
        return [
            f"gs://mock-bucket/customers/{customer_id}/kyc_document.pdf",
            f"gs://mock-bucket/customers/{customer_id}/income_statement.pdf",
            f"gs://mock-bucket/customers/{customer_id}/corporate_registry.pdf",
        ]
