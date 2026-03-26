import pickle

from pgvector.django import SparseVector


class SparseVectorizer:
    """TF-IDF sparse vectorizer that converts text to pgvector SparseVector."""

    VOCAB_SIZE = 30_000  # matches SparseVectorField(dimensions=30000)

    def __init__(self, model_path: str = ".sparse_vectorizer.pkl") -> None:
        self.model_path = model_path
        self._vectorizer = None

    def fit_transform(self, texts: list[str]) -> list[SparseVector]:
        """Fit TF-IDF on texts, persist the vectorizer, return sparse vectors."""
        from sklearn.feature_extraction.text import TfidfVectorizer

        self._vectorizer = TfidfVectorizer(
            max_features=self.VOCAB_SIZE,
            sublinear_tf=True,  # log(1+tf) — reduces very frequent term dominance
        )
        matrix = self._vectorizer.fit_transform(texts)
        with open(self.model_path, "wb") as f:
            pickle.dump(self._vectorizer, f)
        return [self._to_sparse_vector(matrix.getrow(i)) for i in range(matrix.shape[0])]

    def transform(self, text: str) -> SparseVector:
        """Transform a single text using the fitted vectorizer."""
        if self._vectorizer is None:
            try:
                with open(self.model_path, "rb") as f:
                    self._vectorizer = pickle.load(f)  # noqa: S301
            except FileNotFoundError as err:
                raise RuntimeError(
                    "Vectorizer not fitted yet. Call fit_transform first."
                ) from err
        row = self._vectorizer.transform([text])
        return self._to_sparse_vector(row.getrow(0))

    def _to_sparse_vector(self, scipy_row) -> SparseVector:
        """Convert a scipy sparse row to a pgvector SparseVector."""
        coo = scipy_row.tocoo()
        mapping = {int(col): float(val) for col, val in zip(coo.col, coo.data, strict=True)}
        return SparseVector(mapping, self.VOCAB_SIZE)
