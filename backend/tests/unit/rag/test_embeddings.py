"""Tests for HFEmbedder — uses mocked SentenceTransformer to avoid downloading models."""

import math
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_model():
    """Returns a mock SentenceTransformer that produces 384-dim unit vectors."""
    import numpy as np

    model = MagicMock()
    model.encode.side_effect = lambda texts, normalize_embeddings=True: np.array(
        [[1.0 / math.sqrt(384)] * 384 for _ in texts]
    )
    return model


def test_embed_single_returns_384_dims(mock_model):
    from compliance_agent.rag.embeddings import HFEmbedder

    embedder = HFEmbedder()
    with patch(
        "compliance_agent.rag.embeddings.HFEmbedder._get_model", return_value=mock_model
    ):
        result = embedder.embed_single("test regulatory document")

    assert isinstance(result, list)
    assert len(result) == 384


def test_embed_single_is_unit_normalized(mock_model):
    from compliance_agent.rag.embeddings import HFEmbedder

    embedder = HFEmbedder()
    with patch(
        "compliance_agent.rag.embeddings.HFEmbedder._get_model", return_value=mock_model
    ):
        result = embedder.embed_single("test")

    norm = math.sqrt(sum(x**2 for x in result))
    assert abs(norm - 1.0) < 1e-5


def test_batch_embed_matches_single(mock_model):
    import numpy as np

    from compliance_agent.rag.embeddings import HFEmbedder

    texts = ["UIAF article 14", "CNBV resolution", "SBS compliance"]
    embedder = HFEmbedder()
    with patch(
        "compliance_agent.rag.embeddings.HFEmbedder._get_model", return_value=mock_model
    ):
        batch = embedder.embed(texts)
        single = embedder.embed_single(texts[0])

    assert len(batch) == len(texts)
    assert len(batch[0]) == 384
    # All rows identical since mock returns uniform vectors
    assert np.allclose(batch[0], single, atol=1e-6)


def test_model_lazy_loaded():
    from compliance_agent.rag.embeddings import HFEmbedder

    embedder = HFEmbedder()
    assert embedder._model is None  # not loaded yet


def test_dimensions_constant():
    from compliance_agent.rag.embeddings import HFEmbedder

    assert HFEmbedder.DIMENSIONS == 384
    assert HFEmbedder.MODEL_NAME == "sentence-transformers/all-MiniLM-L6-v2"
