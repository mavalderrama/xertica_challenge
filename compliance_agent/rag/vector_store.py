from compliance_agent.rag.embeddings import HFEmbedder
from compliance_agent.rag.interfaces import IRetriever, RegulationChunk


class VectorStoreRetriever(IRetriever):
    """Retrieves regulation chunks using pgvector cosine similarity."""

    def __init__(self, embedder: HFEmbedder) -> None:
        self.embedder = embedder

    async def retrieve(self, query: str, top_k: int = 5) -> list[RegulationChunk]:
        from pgvector.django import CosineDistance

        from compliance_agent.models import RegulationDocument

        query_embedding = self.embedder.embed_single(query)
        docs = (
            RegulationDocument.objects.annotate(
                distance=CosineDistance("embedding", query_embedding)
            )
            .filter(embedding__isnull=False)
            .order_by("distance")[:top_k]
        )
        return [
            RegulationChunk(
                document_ref=doc.document_ref,
                source=doc.source,
                article_number=doc.article_number,
                content=doc.content,
                chunk_index=doc.chunk_index,
                gcs_uri=doc.gcs_uri,
                score=1.0 - (doc.distance or 0.0),
            )
            for doc in docs
        ]
