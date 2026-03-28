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
    """Returns synthetic document text for local development and testing."""

    async def extract_pdf_text(self, gcs_uri: str) -> str:
        return (
            f"[MOCK PDF] Document from {gcs_uri}\n\n"
            "Customer Profile Summary:\n"
            "- Account opened: 2019-03-15\n"
            "- KYC status: VERIFIED\n"
            "- Risk category: MEDIUM\n"
            "- Previous alerts: 2 (both dismissed)\n"
            "- Business activity: Import/Export\n"
            "- Annual declared income: USD 450,000\n"
        )

    async def list_customer_documents(self, customer_id: str) -> list[str]:
        return [
            f"gs://mock-bucket/customers/{customer_id}/kyc_document.pdf",
            f"gs://mock-bucket/customers/{customer_id}/income_statement.pdf",
            f"gs://mock-bucket/customers/{customer_id}/corporate_registry.pdf",
        ]
