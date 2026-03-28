from django.contrib.postgres.search import SearchQuery, SearchRank

from compliance_agent.rag.interfaces import IRetriever, RegulationChunk


class SparseVectorRetriever(IRetriever):
    """Sparse BM25 retrieval using PostgreSQL native full-text search (tsvector/tsquery).

    Uses the built-in 'spanish' text search configuration for stemming and
    stopword removal. SearchRank computes a BM25-equivalent relevance score.
    No external model or pickled file required.
    """

    async def retrieve(self, query: str, top_k: int = 5) -> list[RegulationChunk]:
        from compliance_agent.models import RegulationDocument

        search_query = SearchQuery(query, config="spanish", search_type="websearch")
        return [
            RegulationChunk(
                document_ref=doc.document_ref,
                source=doc.source,
                article_number=doc.article_number,
                content=doc.content,
                chunk_index=doc.chunk_index,
                gcs_uri=doc.gcs_uri,
                score=float(doc.rank),
            )
            async for doc in RegulationDocument.objects.filter(
                search_vector=search_query
            )
            .annotate(rank=SearchRank("search_vector", search_query))
            .order_by("-rank")[:top_k]
        ]
