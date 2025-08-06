"""Utilities for generating sentence embeddings."""

from __future__ import annotations

import numpy as np

try:
    from sentence_transformers import SentenceTransformer

    _model = SentenceTransformer("all-MiniLM-L6-v2")
    _dim = _model.get_sentence_embedding_dimension()
except Exception:  # pragma: no cover - optional dependency
    _model = None
    _dim = 384


def encode(texts: list[str]) -> np.ndarray:
    """Encode ``texts`` into a ``(n, d)`` float32 NumPy array."""

    import numpy as np

    if _model is None:
        return np.zeros((len(texts), _dim), dtype=np.float32)
    vectors = _model.encode(texts, convert_to_numpy=True)
    return np.asarray(vectors, dtype=np.float32)
