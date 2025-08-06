"""Lightweight vector store with JSON persistence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from .config import settings
from .models import Article


def _load(path: Path) -> list[list[float]]:
    if not path.exists():
        return []
    return json.loads(path.read_text())


def _save(path: Path, data: list[list[float]]) -> None:
    path.write_text(json.dumps(data))


def build_index(articles: List[Article]):
    """Build index from ``articles`` and persist it."""

    vectors = [a.embedding or [] for a in articles]
    path = Path(settings.VECTOR_INDEX_PATH)
    _save(path, vectors)
    return vectors


def load_index():
    """Load index from disk."""
    return _load(Path(settings.VECTOR_INDEX_PATH))


def add_documents(new: List[Article]):
    """Add documents avoiding exact duplicate vectors."""

    path = Path(settings.VECTOR_INDEX_PATH)
    index = _load(path)
    existing = {tuple(v) for v in index}
    for art in new:
        vec = art.embedding or []
        if tuple(vec) not in existing:
            index.append(vec)
            existing.add(tuple(vec))
    _save(path, index)
    return index
