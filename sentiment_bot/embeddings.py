"""Utilities for generating sentence embeddings."""

from __future__ import annotations

try:
    from sentence_transformers import SentenceTransformer

    _model = SentenceTransformer("all-MiniLM-L6-v2")
    _dim = _model.get_sentence_embedding_dimension()
except Exception:  # pragma: no cover - optional dependency
    _model = None
    _dim = 384


def encode(text: str) -> list[float]:
    """Return an embedding vector for *text*.

    The fallback implementation returns a list of zeros so tests can run
    without the transformer model or NumPy installed.
    """

    if _model is None:
        return [0.0] * _dim
    vec = _model.encode(text, convert_to_numpy=False)
    return list(map(float, vec))
