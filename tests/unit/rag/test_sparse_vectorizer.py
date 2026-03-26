"""Tests for SparseVectorizer — no DB required, no sentence-transformers required."""
import pytest


def test_fit_transform_returns_same_count():
    from unittest.mock import MagicMock, patch

    from pgvector.django import SparseVector

    from compliance_agent.rag.sparse_vectorizer import SparseVectorizer

    texts = ["compliance fraud alert", "money laundering detection", "PEP screening"]
    vectorizer = SparseVectorizer(model_path="/tmp/test_vectorizer.pkl")

    mock_file = MagicMock()
    mock_file.__enter__ = MagicMock(return_value=mock_file)
    mock_file.__exit__ = MagicMock(return_value=False)
    with patch("builtins.open", return_value=mock_file), patch("pickle.dump"):
        result = vectorizer.fit_transform(texts)

    assert len(result) == len(texts)
    assert all(isinstance(v, SparseVector) for v in result)


def test_transform_returns_sparse_vector_with_correct_dimension():
    import pickle
    from unittest.mock import mock_open, patch

    from pgvector.django import SparseVector
    from sklearn.feature_extraction.text import TfidfVectorizer

    from compliance_agent.rag.sparse_vectorizer import SparseVectorizer

    # Build and pickle a real vectorizer
    tfidf = TfidfVectorizer(max_features=30000, sublinear_tf=True)
    tfidf.fit(["compliance", "fraud", "alert"])
    pickled = pickle.dumps(tfidf)

    vectorizer = SparseVectorizer(model_path="/tmp/test_vectorizer.pkl")
    with patch("builtins.open", mock_open(read_data=pickled)), patch(
        "pickle.load", return_value=tfidf
    ):
        result = vectorizer.transform("compliance alert")

    assert isinstance(result, SparseVector)
    assert result.dimensions() == 30000


def test_unseen_query_terms_handled_gracefully():
    import pickle
    from unittest.mock import mock_open, patch

    from pgvector.django import SparseVector
    from sklearn.feature_extraction.text import TfidfVectorizer

    from compliance_agent.rag.sparse_vectorizer import SparseVectorizer

    tfidf = TfidfVectorizer(max_features=30000, sublinear_tf=True)
    tfidf.fit(["compliance fraud"])
    pickled = pickle.dumps(tfidf)

    vectorizer = SparseVectorizer(model_path="/tmp/test_vectorizer.pkl")
    with patch("builtins.open", mock_open(read_data=pickled)), patch(
        "pickle.load", return_value=tfidf
    ):
        # "xyzzy" is an OOV token — should not crash
        result = vectorizer.transform("xyzzy unknown term never seen before")

    assert isinstance(result, SparseVector)
    assert result.dimensions() == 30000


def test_to_sparse_vector_produces_correct_sparsity():
    import scipy.sparse as sp

    from compliance_agent.rag.sparse_vectorizer import SparseVectorizer

    vectorizer = SparseVectorizer()
    row = sp.csr_matrix([[0.0, 0.5, 0.0, 0.8, 0.0]])
    result = vectorizer._to_sparse_vector(row.getrow(0))

    # Only 2 non-zero values
    assert len(result.indices()) == 2


def test_transform_without_fit_raises():
    from compliance_agent.rag.sparse_vectorizer import SparseVectorizer

    vectorizer = SparseVectorizer(model_path="/tmp/nonexistent_file_xyz.pkl")
    with pytest.raises(RuntimeError, match="Vectorizer not fitted yet"):
        vectorizer.transform("test")
