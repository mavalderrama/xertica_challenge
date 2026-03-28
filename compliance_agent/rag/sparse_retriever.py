from compliance_agent.rag.interfaces import IRetriever, RegulationChunk
from compliance_agent.rag.sparse_vectorizer import SparseVectorizer


class SparseVectorRetriever(IRetriever):
    """Sparse retrieval using TF-IDF vectors stored in pgvector sparsevec."""

    def __init__(self, vectorizer: SparseVectorizer) -> None:
        self.vectorizer = vectorizer

    async def retrieve(self, query: str, top_k: int = 5) -> list[RegulationChunk]:
        from pgvector.django import MaxInnerProduct

        from compliance_agent.models import RegulationDocument

        query_vec = self.vectorizer.transform(query)
        return [
            RegulationChunk(
                document_ref=doc.document_ref,
                source=doc.source,
                article_number=doc.article_number,
                content=doc.content,
                chunk_index=doc.chunk_index,
                gcs_uri=doc.gcs_uri,
                score=float(doc.similarity),
            )
            async for doc in RegulationDocument.objects.filter(
                sparse_embedding__isnull=False
            )
            .annotate(similarity=MaxInnerProduct("sparse_embedding", query_vec))
            .order_by("-similarity")[:top_k]
        ]
