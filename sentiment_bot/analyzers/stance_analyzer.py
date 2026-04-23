"""
Stance and framing detection per entity.

Combines aspect extraction (spaCy NER) with aspect-level NLI sentiment
to produce entity-specific stances instead of flat article sentiment.

Usage:
    analyzer = StanceAnalyzer()
    stances = analyzer.analyze(text)
    # [{"entity": "Fed", "type": "ORG", "stance": "neutral", "score": 0.05, "confidence": 0.82}, ...]
"""

import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class StanceAnalyzer:
    """Extract per-entity stances from text using NLI."""

    def __init__(self):
        self._aspect_extractor = None
        self._aspect_sentiment = None
        self._ready = None  # None = unchecked, True/False after check

    def _ensure_ready(self) -> bool:
        """Skip local spaCy/NLI model loading — hangs on MPS.

        Stance detection via local models is disabled while we use
        HF Inference API for the hot path. Re-enable when a remote
        stance endpoint is available.
        """
        self._ready = False
        return False

    def analyze(self, text: str, title: str = "") -> List[Dict]:
        """
        Extract per-entity stances from text.

        Returns:
            List of {entity, type, stance, score, confidence} dicts.
            stance is one of: favorable, critical, neutral
            score is -1.0 to +1.0
        """
        if not self._ensure_ready():
            return []

        full_text = f"{title}. {text}" if title else text

        # Step 1: Extract entities via spaCy
        try:
            aspects = self._aspect_extractor.extract_aspects(full_text[:5000])
        except Exception as e:
            logger.debug(f"Aspect extraction failed: {e}")
            return []

        # Filter to named entities only (skip noun phrases)
        entity_aspects = [a for a in aspects if a.get("label") in ("PERSON", "ORG", "GPE", "LOC", "NORP")]

        if not entity_aspects:
            return []

        # Step 2: Score stance toward each entity via NLI
        try:
            scored = self._aspect_sentiment.score_aspects(full_text[:2000], entity_aspects)
        except Exception as e:
            logger.debug(f"Aspect sentiment failed: {e}")
            return []

        # Step 3: Build output
        stances = []
        for aspect in scored:
            stance_label = aspect.get("sentiment_label", "neutral")
            # Remap to clearer labels
            stance_map = {"positive": "favorable", "negative": "critical", "neutral": "neutral"}

            stances.append({
                "entity": aspect["text"],
                "type": aspect.get("label", "UNKNOWN"),
                "stance": stance_map.get(stance_label, "neutral"),
                "score": round(aspect.get("sentiment_score", 0.0), 3),
                "confidence": round(aspect.get("sentiment_confidence", 0.0), 3),
            })

        return stances

    def analyze_batch(self, articles: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Analyze stances for a batch of articles.

        Args:
            articles: List of {id, text, title} dicts

        Returns:
            Dict mapping article ID to list of stances
        """
        results = {}
        for article in articles:
            doc_id = article.get("id", "unknown")
            text = article.get("text", "")
            title = article.get("title", "")
            results[doc_id] = self.analyze(text, title)
        return results
