class HFEmbedder:
    """Local embedder using sentence-transformers/all-MiniLM-L6-v2 (384-dim)."""

    MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
    DIMENSIONS = 384

    def __init__(self) -> None:
        self._model = None  # lazy-loaded

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.MODEL_NAME)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._get_model().encode(texts, normalize_embeddings=True).tolist()

    def embed_single(self, text: str) -> list[float]:
        return self.embed([text])[0]
