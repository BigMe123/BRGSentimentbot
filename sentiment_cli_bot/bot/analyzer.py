"""Simple sentiment analysis helpers.

The real project envisions a rich ensemble of NLP models.  To keep the
example lightweight we only load VADER which is tiny and fast.  The
interfaces however mirror the planned future expansion so additional
models can be slotted in later.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean
from typing import Iterable

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer


_vader = SentimentIntensityAnalyzer()


@dataclass
class AnalysisResult:
    """Result for a single document."""

    polarity_vader: float
    polarity_bert: float
    threat_labels: list[str]
    summary: str


@dataclass
class VolatilitySnapshot:
    """Aggregated metrics across analysed articles."""

    volatility_score: float
    confidence: float
    top_triggers: list[str]


def analyze(text: str) -> AnalysisResult:
    """Analyse a block of text and return sentiment information."""

    vader_score = _vader.polarity_scores(text)["compound"]
    # The BERT and zero-shot models are heavy; we return placeholders with
    # TODO markers for future contributors.
    return AnalysisResult(
        polarity_vader=vader_score,
        polarity_bert=0.0,  # TODO: integrate transformers pipeline
        threat_labels=[],  # TODO: integrate zero-shot classifier
        summary=text[:200],  # TODO: summarise with BART
    )


def aggregate(results: Iterable[AnalysisResult]) -> VolatilitySnapshot:
    """Aggregate many :class:`AnalysisResult` objects into a snapshot."""

    results = list(results)
    if not results:
        return VolatilitySnapshot(volatility_score=0.0, confidence=0.0, top_triggers=[])

    # Simple aggregation: average absolute VADER score.
    vol = fmean(abs(r.polarity_vader) for r in results)
    confidence = len(results) / (len(results) + 10)
    return VolatilitySnapshot(
        volatility_score=vol, confidence=confidence, top_triggers=[]
    )
