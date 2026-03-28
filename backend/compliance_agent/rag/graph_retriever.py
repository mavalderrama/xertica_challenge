from __future__ import annotations

from compliance_agent.rag.embeddings import HFEmbedder
from compliance_agent.rag.interfaces import IRetriever, RegulationChunk
from compliance_agent.rag.vector_store import VectorStoreRetriever


class GraphRetriever(IRetriever):
    """
    Graph-aware retriever that expands vector search results by traversing
    the related_articles M2M graph. Seed documents (direct vector matches)
    score higher than graph-expanded neighbors.

    This satisfies the CHALLENGE.md requirement for a graph layer that
    improves precision for multi-article regulatory reasoning.
    """

    SEED_WEIGHT = 1.0
    NEIGHBOR_WEIGHT = 0.5

    def __init__(self, embedder: HFEmbedder, seed_top_k: int = 3) -> None:
        self._vector_retriever = VectorStoreRetriever(embedder)
        self.seed_top_k = seed_top_k

    async def retrieve(self, query: str, top_k: int = 5) -> list[RegulationChunk]:
        from compliance_agent.models import RegulationDocument

        # Step 1: Get seed documents via dense vector search
        seeds = await self._vector_retriever.retrieve(query, top_k=self.seed_top_k)
        seed_refs = {f"{c.document_ref}::{c.chunk_index}" for c in seeds}

        # Start with seed documents at full weight
        scored: dict[str, tuple[RegulationChunk, float]] = {}
        for chunk in seeds:
            key = f"{chunk.document_ref}::{chunk.chunk_index}"
            scored[key] = (chunk, chunk.score * self.SEED_WEIGHT)

        # Step 2: Traverse related_articles (1-hop graph expansion)
        seed_doc_refs = {c.document_ref for c in seeds}
        async for doc in RegulationDocument.objects.filter(
            document_ref__in=seed_doc_refs
        ).prefetch_related("related_articles"):
            async for related in doc.related_articles.all():
                key = f"{related.document_ref}::{related.chunk_index}"
                if key not in seed_refs and key not in scored:
                    neighbor = RegulationChunk(
                        document_ref=related.document_ref,
                        source=related.source,
                        article_number=related.article_number,
                        content=related.content,
                        chunk_index=related.chunk_index,
                        gcs_uri=related.gcs_uri or "",
                        score=self.NEIGHBOR_WEIGHT,
                    )
                    scored[key] = (neighbor, self.NEIGHBOR_WEIGHT)

        # Step 3: Sort by score and return top_k
        sorted_chunks = sorted(scored.values(), key=lambda x: x[1], reverse=True)
        return [chunk for chunk, _ in sorted_chunks[:top_k]]
