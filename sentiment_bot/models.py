"""Database models for articles and snapshots using :mod:`sqlmodel`."""

from __future__ import annotations

from typing import List, Optional

try:  # pragma: no cover - optional dependency
    from sqlalchemy import Column, JSON
    from sqlmodel import Field, SQLModel

    class Article(SQLModel, table=True):  # type: ignore[misc]
        """Representation of a scraped news article."""

        id: Optional[int] = Field(default=None, primary_key=True)
        url: str
        title: str
        hash: str
        published: Optional[str] = None
        vader: Optional[float] = None
        bert: Optional[float] = None
        threat_probs: Optional[List[float]] = Field(default=None, sa_column=Column(JSON))
        embedding: Optional[List[float]] = Field(default=None, sa_column=Column(JSON))

    class Snapshot(SQLModel, table=True):  # type: ignore[misc]
        """Aggregated snapshot of current volatility."""

        id: Optional[int] = Field(default=None, primary_key=True)
        ts: str
        volatility: float
        confidence: float
        triggers: List[str] = Field(default_factory=list, sa_column=Column(JSON))
except Exception:  # pragma: no cover - fallback dataclasses
    from dataclasses import dataclass, field

    @dataclass
    class Article:
        url: str
        title: str
        hash: str
        published: Optional[str] = None
        vader: Optional[float] = None
        bert: Optional[float] = None
        threat_probs: Optional[List[float]] = None
        embedding: Optional[List[float]] = None

    @dataclass
    class Snapshot:
        ts: str
        volatility: float
        confidence: float
        triggers: List[str] = field(default_factory=list)
