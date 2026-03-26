from abc import ABC, abstractmethod


class BigQueryToolInterface(ABC):
    @abstractmethod
    async def get_transaction_history(
        self, customer_id: str, days: int = 90
    ) -> list[dict]:
        pass


class GCSToolInterface(ABC):
    @abstractmethod
    async def extract_pdf_text(self, gcs_uri: str) -> str:
        pass

    @abstractmethod
    async def list_customer_documents(self, customer_id: str) -> list[str]:
        pass
