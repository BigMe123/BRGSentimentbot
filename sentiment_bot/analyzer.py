"""Sentiment and volatility analysis tools."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean
from typing import Iterable, List

try:  # pragma: no cover - optional dependency
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

    _vader = SentimentIntensityAnalyzer()
except Exception:  # pragma: no cover - fallback
    class SentimentIntensityAnalyzer:  # type: ignore
        POS = {"good", "great", "excellent", "amazing", "wonderful"}
        NEG = {"bad", "terrible", "awful"}

        def polarity_scores(self, text: str) -> dict[str, float]:
            words = text.lower().split()
            score = sum(w in self.POS for w in words) - sum(w in self.NEG for w in words)
            return {"compound": float(score)}

    _vader = SentimentIntensityAnalyzer()

try:  # pragma: no cover - optional heavy deps
    from transformers import pipeline
    try:
        _bert = pipeline("sentiment-analysis")
    except Exception:
        _bert = None
    try:
        _nli = pipeline("zero-shot-classification")
    except Exception:
        _nli = None
    try:
        _summarizer = pipeline("summarization")
    except Exception:
        _summarizer = None
except Exception:  # pragma: no cover - optional dependency
    pipeline = None  # type: ignore
    _bert = _nli = _summarizer = None


@dataclass
class Analysis:
    vader: float
    bert: float
    labels: List[str]
    summary: str


@dataclass
class Snapshot:
    ts: str | None = None
    volatility: float = 0.0
    confidence: float = 0.0
    triggers: List[str] | None = None


def analyze(text: str) -> Analysis:
    """Analyse *text* and return sentiment metrics."""

    vader_score = _vader.polarity_scores(text)["compound"]
    bert_score = 0.0
    labels: List[str] = []
    summary = text[:200]
    if _bert:
        res = _bert(text)[0]
        bert_score = res.get("score", 0.0) * (1 if res.get("label") == "POSITIVE" else -1)
    if _nli:
        nli_res = _nli(text, candidate_labels=["threat", "safe"])
        labels = [nli_res.get("labels", [])[0]]
    if _summarizer:
        summary = _summarizer(text[:1000])[0]["summary_text"]
    return Analysis(vader=vader_score, bert=bert_score, labels=labels, summary=summary)


def aggregate(results: Iterable[Analysis]) -> Snapshot:
    """Aggregate many :class:`Analysis` objects."""

    results = list(results)
    if not results:
        return Snapshot()
    vol = fmean(abs(r.vader) for r in results)
    confidence = len(results) / (len(results) + 10)
    return Snapshot(volatility=vol, confidence=confidence, triggers=[])
