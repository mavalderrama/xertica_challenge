"""
Hybrid retrieval using Reciprocal Rank Fusion (RRF).

RRF formula: score(d) = Σ 1 / (k + rank_i(d))
where k=60 (empirically robust constant) and rank_i is the rank in retriever i.

Combines:
1. Dense (vector) retrieval — semantic similarity via pgvector cosine (all-MiniLM-L6-v2, 384-dim)
2. Sparse retrieval — PostgreSQL BM25 full-text search (tsvector/ts_rank, 'spanish' config)
3. Graph retrieval (optional) — 1-hop M2M expansion for multi-article regulatory reasoning
"""

from __future__ import annotations

import asyncio

from compliance_agent.rag.interfaces import IRetriever, RegulationChunk

RRF_K = 60


class HybridRetriever(IRetriever):
    def __init__(
        self,
        vector_retriever: IRetriever,
        sparse_retriever: IRetriever,
        graph_retriever: IRetriever | None = None,
        rrf_k: int = RRF_K,
    ) -> None:
        self.vector_retriever = vector_retriever
        self.sparse_retriever = sparse_retriever
        self.graph_retriever = graph_retriever
        self.rrf_k = rrf_k

    async def retrieve(self, query: str, top_k: int = 5) -> list[RegulationChunk]:
        fetch_k = top_k * 3

        retrievers = [self.vector_retriever, self.sparse_retriever]
        if self.graph_retriever is not None:
            retrievers.append(self.graph_retriever)

        all_results = await asyncio.gather(
            *[r.retrieve(query, fetch_k) for r in retrievers]
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
