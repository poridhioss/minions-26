"""
Embedder module.
Loads the all-MiniLM-L6-v2 model and produces 384-dim sentence embeddings.
A sentence embedding is a list of numbers that captures the *meaning*
of a piece of text - similar texts end up close together in vector space.
"""
import numpy as np
from sentence_transformers import SentenceTransformer

from .config import EMBEDDING_MODEL_NAME


class Embedder:
    """Lazy-loaded wrapper around the sentence-transformer model."""

    _model: SentenceTransformer | None = None

    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME) -> None:
        self.model_name = model_name
        # The actual model is loaded on first use to keep app startup fast.

    def _load(self) -> SentenceTransformer:
        if Embedder._model is None:
            print(f"[embedder] Loading model: {self.model_name}")
            Embedder._model = SentenceTransformer(self.model_name)
        return Embedder._model

    def embed(self, text: str) -> np.ndarray:
        """Embed a single string -> 1D numpy array of shape (384,)."""
        model = self._load()
        vector = model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
        return vector.astype("float32")

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        """Embed a list of strings -> 2D numpy array of shape (n, 384)."""
        model = self._load()
        vectors = model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vectors.astype("float32")
