"""
Output models for institutional-style reporting.
Stable schemas for machine consumption and human analysis.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any
from datetime import datetime


class Sentiment(BaseModel):
    """Sentiment analysis result."""

    label: Literal["pos", "neg", "neu"]
    score: float = Field(..., ge=-1.0, le=1.0)
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)


class AspectScore(BaseModel):
    """Aspect-based sentiment score."""

    aspect: str
    sentiment: float = Field(..., ge=-1.0, le=1.0)


class EntityCount(BaseModel):
    """Named entity with occurrence count."""

    text: str
    type: str  # ORG, GPE, PERSON, etc.
    count: int = Field(..., ge=1)


class SourceCount(BaseModel):
    """Source article count."""

    domain: str
    articles: int = Field(..., ge=0)


class SignalData(BaseModel):
    """Market/risk signals from analysis."""

    volatility: float = Field(..., ge=0.0, le=1.0)
    risk_level: Literal["low", "normal", "elevated", "high", "critical"]
    themes: List[str] = Field(default_factory=list)


class AnalysisBlock(BaseModel):
    """Aggregate analysis metrics."""

    sentiment_total: int  # -100 to +100 scale
    breakdown: Dict[str, int]  # pos/neg/neu counts
    avg_sentiment: float = Field(..., ge=-1.0, le=1.0)
    top_triggers: List[str] = Field(default_factory=list)
    top_entities: List[EntityCount] = Field(default_factory=list)
    volatility_index: float = Field(..., ge=0.0, le=1.0)


class DiversityBlock(BaseModel):
    """Source diversity metrics."""

    sources: int = Field(..., ge=0)
    languages: int = Field(..., ge=0)
    regions: int = Field(..., ge=0)
    editorial_families: int = Field(..., ge=0)
    score: float = Field(..., ge=0.0, le=1.0)


class CollectionBlock(BaseModel):
    """Article collection statistics."""

    attempted_feeds: int = Field(..., ge=0)
    articles_raw: int = Field(..., ge=0)
    unique_after_dedupe: int = Field(..., ge=0)
    fresh_window_h: int = Field(..., ge=1)
    fresh_count: int = Field(..., ge=0)
    relevant_count: int = Field(..., ge=0)


class ConfigBlock(BaseModel):
    """Run configuration."""

    region: Optional[str] = None
    topic: Optional[str] = None
    budget_sec: int = Field(..., ge=1)
    min_sources: int = Field(..., ge=1)
    discover: bool = False
    max_age_hours: int = Field(default=24, ge=1)


class ArticleRecord(BaseModel):
    """Individual article record for JSONL output."""

    run_id: str
    id: str  # unique article ID
    title: str
    url: str
    published_at: str  # ISO format
    source: str  # domain
    region: str
    topic: str
    language: str = "en"

    # Optional enrichments
    authors: List[str] = Field(default_factory=list)
    tickers: List[str] = Field(default_factory=list)
    entities: List[Dict[str, str]] = Field(default_factory=list)
    summary: str = ""
    text_chars: int = Field(0, ge=0)
    hash: str = ""

    # Analysis results
    relevance: float = Field(..., ge=0.0, le=1.0)
    sentiment: Sentiment
    aspects: List[AspectScore] = Field(default_factory=list)
    signals: Optional[SignalData] = None

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class RunSummary(BaseModel):
    """Complete run summary for JSON output."""

    run_id: str
    started_at: str  # ISO format
    finished_at: str  # ISO format
    config: ConfigBlock
    collection: CollectionBlock
    analysis: AnalysisBlock
    sources: List[SourceCount]
    diversity: DiversityBlock
    errors: List[str] = Field(default_factory=list)
    schema_version: str = "1.0.0"

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}
