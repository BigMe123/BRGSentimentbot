"""Sentiment analysis helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class AnalysisResult:
    vader: Optional[float] = None
    bert: Optional[float] = None
    volatility: float = 0.0


class Analyzer:
    """Run sentiment models and compute a volatility score."""

    def __init__(self) -> None:
        try:  # optional dependency
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

            self.vader = SentimentIntensityAnalyzer()
            self.low_quality = False
        except Exception:  # pragma: no cover - fallback when vader not installed
            self.vader = None
            self.low_quality = True

        try:  # transformers are optional
            from transformers import pipeline

            self.bert = pipeline("sentiment-analysis")
        except Exception:  # pragma: no cover - optional
            self.bert = None

    # ------------------------------------------------------------------
    def analyze(self, text: str) -> AnalysisResult:
        scores: list[float] = []
        vader_score: Optional[float] = None
        bert_score: Optional[float] = None

        if self.vader:
            vader_score = self.vader.polarity_scores(text)["compound"]
            scores.append(abs(vader_score))
        if self.bert:
            out = self.bert(text[:512])[0]
            bert_score = out["score"] if out["label"].lower() == "positive" else -out["score"]
            scores.append(abs(bert_score))

        volatility = sum(scores) / len(scores) if scores else 0.0
        return AnalysisResult(vader=vader_score, bert=bert_score, volatility=volatility)

