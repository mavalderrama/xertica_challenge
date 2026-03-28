from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class RegulationChunk:
    document_ref: str
    source: str
    article_number: str
    content: str
    chunk_index: int
    gcs_uri: str = ""
    score: float = 0.0
    metadata: dict = field(default_factory=dict)


class IRetriever(ABC):
    @abstractmethod
    async def retrieve(self, query: str, top_k: int = 5) -> list[RegulationChunk]:
        pass


class IIndexer(ABC):
    @abstractmethod
    async def index_document(self, gcs_uri: str, source: str, document_ref: str) -> int:
        """Index a document from GCS. Returns number of chunks created."""
        pass
