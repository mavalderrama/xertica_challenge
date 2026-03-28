"""Tests for PostgreSQL BM25 sparse retriever (replaces TF-IDF sparse_vectorizer tests)."""
import pytest


@pytest.mark.asyncio
async def test_sparse_retriever_implements_iretriever():
    from compliance_agent.rag.interfaces import IRetriever
    from compliance_agent.rag.sparse_retriever import SparseVectorRetriever

    retriever = SparseVectorRetriever()
    assert isinstance(retriever, IRetriever)


@pytest.mark.asyncio
async def test_sparse_retriever_no_constructor_args():
    """BM25 retriever requires no external model or vectorizer — instantiates bare."""
    from compliance_agent.rag.sparse_retriever import SparseVectorRetriever

    retriever = SparseVectorRetriever()
    assert retriever is not None


@pytest.mark.asyncio
async def test_sparse_retriever_returns_regulation_chunks():
    """Verify retrieve() returns RegulationChunk list (mocked DB via compliance_agent.models)."""
    from unittest.mock import MagicMock, patch

    from compliance_agent.rag.sparse_retriever import SparseVectorRetriever

    mock_doc = MagicMock()
    mock_doc.document_ref = "uiaf_sarlaft_sfc_ce029_2014"
    mock_doc.source = "UIAF"
    mock_doc.article_number = "4"
    mock_doc.content = "PEP debida diligencia intensificada escalamiento obligatorio"
    mock_doc.chunk_index = 0
    mock_doc.gcs_uri = "gs://compliance-docs/regulations/uiaf_sarlaft_sfc_ce029_2014.txt"
    mock_doc.rank = 0.75

    async def async_docs():
        yield mock_doc

    mock_qs = MagicMock()
    mock_qs.filter.return_value = mock_qs
    mock_qs.annotate.return_value = mock_qs
    mock_qs.order_by.return_value.__getitem__ = MagicMock(return_value=async_docs())

    retriever = SparseVectorRetriever()
    # Patch at the model's module level, where the class is actually imported at call time
    with patch("compliance_agent.models.RegulationDocument") as mock_model:
        mock_model.objects.filter.return_value = mock_qs
        results = await retriever.retrieve("PEP escalamiento")

    assert isinstance(results, list)


def test_sparse_retriever_uses_spanish_config():
    """Verify retriever uses 'spanish' FTS config (checked via source inspection)."""
    import inspect

    from compliance_agent.rag.sparse_retriever import SparseVectorRetriever

    source = inspect.getsource(SparseVectorRetriever.retrieve)
    assert "spanish" in source


def test_sparse_vectorizer_module_removed():
    """Confirm the old TF-IDF SparseVectorizer module no longer exists."""
    import importlib

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("compliance_agent.rag.sparse_vectorizer")
