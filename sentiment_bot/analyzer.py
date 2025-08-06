"""Sentiment and volatility analysis tools.

This module prefers the :mod:`vaderSentiment` package for lexicon based
sentiment analysis.  When the dependency is missing a very small lexicon
analyzer is used as a fallback.  The fallback is intentionally simple and
is **not** a drop in replacement for VADER.  Results produced by the
fallback are flagged as ``low_quality`` so that downstream modules can
detect the degraded state and react accordingly (e.g. by skipping
automated trading decisions or prompting the user to install
``vaderSentiment``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import fmean
from typing import Iterable, List

try:  # pragma: no cover - optional dependency
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

    _vader = SentimentIntensityAnalyzer()
    VADER_AVAILABLE = True
except Exception:  # pragma: no cover - fallback

    class SentimentIntensityAnalyzer:  # type: ignore
        """Very small lexicon based sentiment analyzer.

        This is a drastically simplified analyzer used only when the real
        :mod:`vaderSentiment` package is unavailable.  It tokenises input
        using a basic regular expression and scores text by counting
        positive and negative words from small lexicons derived from the
        VADER paper.
        """

        POS = {
            "good",
            "great",
            "excellent",
            "amazing",
            "wonderful",
            "positive",
            "fortunate",
            "correct",
            "superior",
        }
        NEG = {
            "bad",
            "terrible",
            "awful",
            "horrible",
            "poor",
            "negative",
            "unfortunate",
            "wrong",
            "inferior",
        }

        word_re = re.compile(r"\b\w+\b")

        def polarity_scores(self, text: str) -> dict[str, float]:

            words = self.word_re.findall(text.lower())

            score = sum(w in self.POS for w in words) - sum(
                w in self.NEG for w in words
            )
            return {"compound": float(score)}

    _vader = SentimentIntensityAnalyzer()
    VADER_AVAILABLE = False

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
    low_quality: bool = False


@dataclass
class Snapshot:
    ts: str | None = None
    volatility: float = 0.0
    confidence: float = 0.0
    triggers: List[str] | None = None


def analyze(text: str) -> Analysis:
    """Analyse *text* and return sentiment metrics.

    The returned :class:`Analysis` object includes a ``low_quality`` flag
    which is ``True`` when the result was produced by the lightweight
    fallback analyzer rather than the full VADER implementation.
    """

    vader_score = _vader.polarity_scores(text)["compound"]
    bert_score = 0.0
    labels: List[str] = []
    summary = text[:200]
    if _bert:
        res = _bert(text)[0]
        bert_score = res.get("score", 0.0) * (
            1 if res.get("label") == "POSITIVE" else -1
        )
    if _nli:
        nli_res = _nli(text, candidate_labels=["threat", "safe"])
        cand = nli_res.get("labels", [])
        labels = cand[:1] if cand else []
    if _summarizer:
        summary = _summarizer(text[:1000])[0]["summary_text"]
    return Analysis(
        vader=vader_score,
        bert=bert_score,
        labels=labels,
        summary=summary,
        low_quality=not VADER_AVAILABLE,
    )


def aggregate(results: Iterable[Analysis]) -> Snapshot:
    """Aggregate many :class:`Analysis` objects."""

    results = list(results)
    if not results:
        return Snapshot()
    vol = fmean((abs(r.vader) + abs(r.bert)) / 2 for r in results)
    confidence = len(results) / (len(results) + 10)
    return Snapshot(volatility=vol, confidence=confidence, triggers=[])
