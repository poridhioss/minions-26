"""
FAISS index module.
FAISS is a vector search library from Meta AI - it can find the
closest matching vectors among millions in milliseconds.

We use IndexFlatIP (Inner Product) which, for *normalized* vectors,
is equivalent to cosine similarity.
"""
import numpy as np
import faiss

from .config import EMBEDDING_DIM


class FaissIndex:
    """Thin wrapper around a FAISS index that stores resume embeddings."""

    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        self.dim = dim
        # IndexFlatIP = exact search using inner product (cosine sim on normalized vectors)
        self.index: faiss.IndexFlatIP = faiss.IndexFlatIP(dim)
        # We keep a parallel Python list of metadata for each vector
        self.metadata: list[dict] = []

    def add(self, vectors: np.ndarray, metadata: list[dict]) -> None:
        """
        Add a batch of vectors (shape n x dim) along with their metadata
        (e.g. candidate name, file path, original text snippet).
        """
        if vectors.shape[1] != self.dim:
            raise ValueError(
                f"Vector dim {vectors.shape[1]} does not match index dim {self.dim}"
            )
        self.index.add(vectors)
        self.metadata.extend(metadata)

    def search(self, query_vector: np.ndarray, k: int | None = None) -> list[dict]:
        """
        Find the k nearest neighbors to the query vector.
        Returns a list of dicts: {score, rank, **metadata}.
        """
        if self.index.ntotal == 0:
            return []

        if k is None or k > self.index.ntotal:
            k = self.index.ntotal

        # FAISS expects 2D queries of shape (1, dim)
        query = query_vector.reshape(1, -1).astype("float32")
        scores, indices = self.index.search(query, k)

        results: list[dict] = []
        for rank, (idx, score) in enumerate(zip(indices[0], scores[0]), start=1):
            if idx == -1:  # FAISS uses -1 for "not found"
                continue
            entry = {"rank": rank, "score": float(score), **self.metadata[idx]}
            results.append(entry)
        return results

    def reset(self) -> None:
        """Clear the index and metadata (useful between recruiter sessions)."""
        self.index.reset()
        self.metadata.clear()
