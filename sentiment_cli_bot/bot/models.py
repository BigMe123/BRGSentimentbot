"""Database models used by the bot.

Only a tiny subset of fields is required for the demo implementation.
The ORM is provided by :mod:`sqlmodel` which builds on SQLAlchemy and
Pydantic.  These models are deliberately minimal so that unit tests can
run without an actual database; they can be easily extended.
"""

from __future__ import annotations

from typing import Optional

from sqlmodel import Field, SQLModel


class Article(SQLModel, table=True):  # type: ignore[call-arg]
    """Representation of a scraped news article."""

    id: Optional[int] = Field(default=None, primary_key=True)
    url: str
    title: str
    text_hash: str
    publish_dt: Optional[str] = None
    vader: Optional[float] = None
    bert: Optional[float] = None
    label: Optional[str] = None
    summary: Optional[str] = None


class Snapshot(SQLModel, table=True):  # type: ignore[call-arg]
    """Aggregated snapshot of the market sentiment."""

    id: Optional[int] = Field(default=None, primary_key=True)
    ts: str
    volatility_score: float
    confidence: float
    triggers_json: Optional[str] = None
