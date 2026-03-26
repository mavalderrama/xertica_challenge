import pytest

from compliance_agent.rag.hybrid_retriever import RRF_K, HybridRetriever
from compliance_agent.rag.interfaces import RegulationChunk


def _make_chunk(ref: str, idx: int, score: float = 1.0) -> RegulationChunk:
    return RegulationChunk(
        document_ref=ref,
        source="UIAF",
        article_number=str(idx),
        content=f"Content {ref} {idx}",
        chunk_index=idx,
        score=score,
    )


@pytest.mark.asyncio
async def test_hybrid_retriever_combines_results():
    from unittest.mock import AsyncMock, MagicMock

    vec = MagicMock()
    vec.retrieve = AsyncMock(
        return_value=[_make_chunk("doc-A", 0), _make_chunk("doc-B", 1)]
    )
    sparse = MagicMock()
    sparse.retrieve = AsyncMock(
        return_value=[_make_chunk("doc-B", 1), _make_chunk("doc-C", 2)]
    )

    retriever = HybridRetriever(vector_retriever=vec, sparse_retriever=sparse)
    results = await retriever.retrieve("test query", top_k=3)

    assert len(results) <= 3
    keys = [f"{r.document_ref}::{r.chunk_index}" for r in results]
    assert "doc-B::1" in keys


@pytest.mark.asyncio
async def test_rrf_scores_overlap_higher():
    from unittest.mock import AsyncMock, MagicMock

    shared_chunk = _make_chunk("shared-doc", 0)
    exclusive_chunk = _make_chunk("exclusive-doc", 0)

    vec = MagicMock()
    vec.retrieve = AsyncMock(return_value=[shared_chunk, exclusive_chunk])
    sparse = MagicMock()
    sparse.retrieve = AsyncMock(return_value=[shared_chunk])

    retriever = HybridRetriever(vector_retriever=vec, sparse_retriever=sparse)
    results = await retriever.retrieve("query", top_k=5)

    scores = {f"{r.document_ref}::{r.chunk_index}": r.score for r in results}
    assert scores["shared-doc::0"] > scores.get("exclusive-doc::0", 0)


def test_rrf_k_constant():
    assert RRF_K == 60
