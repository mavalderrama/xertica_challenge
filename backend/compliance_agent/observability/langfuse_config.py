import os
from typing import Any

# Gemini Flash 2.0 pricing (us-central1, as of 2025-03)
GEMINI_FLASH_INPUT_COST_PER_1K = 0.000075  # USD per 1K input tokens
GEMINI_FLASH_OUTPUT_COST_PER_1K = 0.0003  # USD per 1K output tokens


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    input_cost = (input_tokens / 1000) * GEMINI_FLASH_INPUT_COST_PER_1K
    output_cost = (output_tokens / 1000) * GEMINI_FLASH_OUTPUT_COST_PER_1K
    return round(input_cost + output_cost, 8)


class LangfuseTracer:
    def __init__(
        self,
        public_key: str | None = None,
        secret_key: str | None = None,
        host: str | None = None,
    ) -> None:
        self.public_key = public_key or os.environ.get("LANGFUSE_PUBLIC_KEY", "")
        self.secret_key = secret_key or os.environ.get("LANGFUSE_SECRET_KEY", "")
        self.host = host or os.environ.get("LANGFUSE_HOST", "http://localhost:3000")
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            from langfuse import Langfuse

            self._client = Langfuse(
                public_key=self.public_key,
                secret_key=self.secret_key,
                host=self.host,
            )
        return self._client

    def create_trace(self, name: str, metadata: dict | None = None) -> Any:
        return self._get_client().trace(name=name, metadata=metadata or {})

    def create_span(self, trace: Any, name: str, input_data: dict | None = None) -> Any:
        return trace.span(name=name, input=input_data or {})

    def get_langchain_handler(self, trace: Any) -> Any:
        return trace.get_langchain_handler()

    def create_trace_id(self, name: str = "", metadata: dict | None = None) -> str:
        """Generate a Langfuse trace ID using the v3 API. Returns empty string if unavailable."""
        try:
            client = self._get_client()
            return client.create_trace_id()
        except Exception:
            return ""
