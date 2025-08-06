"""FAISS backed vector store."""

from __future__ import annotations

import gzip
import pickle
from pathlib import Path
from typing import List

import faiss
import numpy as np


class VectorStore:
    """Small wrapper around a FAISS index with ID mapping."""

    def __init__(self, dim: int, path: Path) -> None:
        self.dim = dim
        self.path = path
        self.index = faiss.IndexFlatIP(dim)
        self.id_map: List[int] = []

    def add(self, ids: List[int], vectors: np.ndarray) -> None:
        vectors = np.asarray(vectors, dtype=np.float32)
        if vectors.ndim != 2 or vectors.shape[1] != self.dim:
            raise ValueError("vectors shape mismatch")
        self.index.add(vectors)
        self.id_map.extend(ids)

    def query(self, vector: np.ndarray, topk: int = 5) -> List[int]:
        vec = np.asarray(vector, dtype=np.float32).reshape(1, -1)
        scores, idxs = self.index.search(vec, topk)
        return [self.id_map[i] for i in idxs[0] if i < len(self.id_map)]

    def save(self) -> None:
        data = {
            "index": faiss.serialize_index(self.index),
            "id_map": self.id_map,
            "dim": self.dim,
        }
        with gzip.open(self.path, "wb") as f:
            pickle.dump(data, f)

    @classmethod
    def load(cls, path: Path) -> "VectorStore":
        with gzip.open(path, "rb") as f:
            data = pickle.load(f)
        vs = cls(data["dim"], path)
        vs.index = faiss.deserialize_index(data["index"])
        vs.id_map = list(data["id_map"])
        return vs
