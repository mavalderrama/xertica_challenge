from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from compliance_agent.rag.graph_retriever import GraphRetriever
from compliance_agent.rag.interfaces import RegulationChunk

# RegulationDocument is imported *locally* inside GraphRetriever.retrieve(), so
# we must patch it in the source module (compliance_agent.models), not in
# compliance_agent.rag.graph_retriever.
_MODEL_PATH = "compliance_agent.models.RegulationDocument"


def make_chunk(doc_ref: str, chunk_index: int = 0, score: float = 0.8) -> RegulationChunk:
    return RegulationChunk(
        document_ref=doc_ref,
        source="UIAF",
        article_number="15",
        content=f"Content of {doc_ref}",
        chunk_index=chunk_index,
        gcs_uri="",
        score=score,
    )


def _empty_filter_mock():
    """Returns a queryset mock that yields nothing when async-iterated."""

    async def _aiter(_self):
        return
        yield  # make this an async generator

    mock_filter = MagicMock()
    mock_filter.prefetch_related.return_value = mock_filter
    mock_filter.__aiter__ = _aiter
    return mock_filter


@pytest.mark.asyncio
async def test_graph_retriever_returns_seed_results():
    """GraphRetriever returns the seed docs when no related articles exist."""
    seed_chunks = [make_chunk("DOC-A", score=0.9), make_chunk("DOC-B", score=0.7)]
    mock_embedder = MagicMock()
    retriever = GraphRetriever(embedder=mock_embedder, seed_top_k=2)

    with (
        patch.object(retriever._vector_retriever, "retrieve", AsyncMock(return_value=seed_chunks)),
        patch(_MODEL_PATH) as mock_model,
    ):
        mock_model.objects.filter.return_value = _empty_filter_mock()
        results = await retriever.retrieve("test query", top_k=5)

    assert len(results) >= 1
    assert results[0].document_ref in {"DOC-A", "DOC-B"}


@pytest.mark.asyncio
async def test_seed_documents_score_higher_than_neighbors():
    """Seed documents always score higher than graph-expanded neighbors."""
    seed_chunk = make_chunk("SEED-DOC", score=0.8)

    neighbor = MagicMock()
    neighbor.document_ref = "NEIGHBOR-DOC"
    neighbor.source = "CNBV"
    neighbor.article_number = "8"
    neighbor.content = "Related content"
    neighbor.chunk_index = 0
    neighbor.gcs_uri = ""

    seed_doc = MagicMock()
    seed_doc.document_ref = "SEED-DOC"

    async def aiter_related():
        yield neighbor

    seed_doc.related_articles.all = lambda: aiter_related()

    async def aiter_docs():
        yield seed_doc

    mock_embedder = MagicMock()
    retriever = GraphRetriever(embedder=mock_embedder, seed_top_k=1)

    with (
        patch.object(retriever._vector_retriever, "retrieve", AsyncMock(return_value=[seed_chunk])),
        patch(_MODEL_PATH) as mock_model,
    ):
        mock_filter = MagicMock()
        mock_filter.prefetch_related.return_value = mock_filter
        mock_filter.__aiter__ = lambda self: aiter_docs()
        mock_model.objects.filter.return_value = mock_filter

        results = await retriever.retrieve("test query", top_k=5)

    seed_result = next((r for r in results if r.document_ref == "SEED-DOC"), None)
    neighbor_result = next((r for r in results if r.document_ref == "NEIGHBOR-DOC"), None)
    assert seed_result is not None
    if neighbor_result is not None:
        assert seed_result.score > neighbor_result.score


def test_graph_retriever_seed_weight_constant():
    """SEED_WEIGHT is always greater than NEIGHBOR_WEIGHT."""
    assert GraphRetriever.SEED_WEIGHT > GraphRetriever.NEIGHBOR_WEIGHT


@pytest.mark.asyncio
async def test_graph_retriever_respects_top_k():
    """GraphRetriever returns at most top_k results."""
    seeds = [make_chunk(f"DOC-{i}", score=0.9 - i * 0.1) for i in range(4)]
    mock_embedder = MagicMock()
    retriever = GraphRetriever(embedder=mock_embedder, seed_top_k=4)

    with (
        patch.object(retriever._vector_retriever, "retrieve", AsyncMock(return_value=seeds)),
        patch(_MODEL_PATH) as mock_model,
    ):
        mock_model.objects.filter.return_value = _empty_filter_mock()
        results = await retriever.retrieve("test query", top_k=2)

    assert len(results) <= 2
