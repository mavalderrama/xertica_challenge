"""
Hybrid retrieval using Reciprocal Rank Fusion (RRF).

RRF formula: score(d) = Σ 1 / (k + rank_i(d))
where k=60 (empirically robust constant) and rank_i is the rank in retriever i.

Combines:
1. Dense (vector) retrieval — semantic similarity via pgvector cosine (all-MiniLM-L6-v2, 384-dim)
2. Sparse retrieval — TF-IDF inner product via pgvector sparsevec (30k-dim)
"""

from compliance_agent.rag.interfaces import IRetriever, RegulationChunk

RRF_K = 60


class HybridRetriever(IRetriever):
    def __init__(
        self,
        vector_retriever: IRetriever,
        sparse_retriever: IRetriever,
        rrf_k: int = RRF_K,
    ) -> None:
        self.vector_retriever = vector_retriever
        self.sparse_retriever = sparse_retriever
        self.rrf_k = rrf_k

    async def retrieve(self, query: str, top_k: int = 5) -> list[RegulationChunk]:
        fetch_k = top_k * 3

        import asyncio

        all_results = await asyncio.gather(
            self.vector_retriever.retrieve(query, fetch_k),
            self.sparse_retriever.retrieve(query, fetch_k),
        )

        rrf_scores: dict[str, float] = {}
        chunk_map: dict[str, RegulationChunk] = {}

        for ranked_list in all_results:
            for rank, chunk in enumerate(ranked_list):
                key = f"{chunk.document_ref}::{chunk.chunk_index}"
                rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (
                    self.rrf_k + rank + 1
                )
                chunk_map[key] = chunk

        sorted_keys = sorted(rrf_scores, key=lambda k: rrf_scores[k], reverse=True)
        results = []
        for key in sorted_keys[:top_k]:
            chunk = chunk_map[key]
            chunk.score = rrf_scores[key]
            results.append(chunk)
        return results
