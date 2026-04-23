"""
Active learning: surface low-confidence articles for human labeling.

Identifies articles where the model is least certain and exports them
as candidates for human annotation, building the gold set over time.
"""

import json
import logging
from pathlib import Path
from typing import List, Dict
from datetime import datetime

logger = logging.getLogger(__name__)

CANDIDATES_DIR = Path(__file__).parent.parent / "state" / "active_learning"


class ActiveLearner:
    """
    Surface articles where the model is least confident.

    Strategies:
    - uncertainty: lowest confidence scores
    - disagreement: largest gap between ensemble members
    - boundary: scores closest to decision boundaries (0.0 for sentiment)
    """

    def __init__(self, strategy: str = "uncertainty"):
        """
        Args:
            strategy: "uncertainty", "boundary", or "mixed"
        """
        self.strategy = strategy

    def select_candidates(
        self,
        article_records,
        n: int = 20,
    ) -> List[Dict]:
        """
        Select articles most valuable for human labeling.

        Args:
            article_records: List of ArticleRecord objects
            n: Number of candidates to select

        Returns:
            List of candidate dicts sorted by priority.
        """
        scored = []
        for r in article_records:
            priority = self._score_priority(r)
            scored.append({
                "id": r.id,
                "title": r.title,
                "url": r.url,
                "source": r.source,
                "sentiment_label": r.sentiment.label,
                "sentiment_score": round(r.sentiment.score, 4),
                "confidence": round(r.sentiment.confidence or 0.5, 4),
                "priority": round(priority, 4),
                "reason": self._explain_priority(r, priority),
            })

        scored.sort(key=lambda x: x["priority"], reverse=True)
        return scored[:n]

    def _score_priority(self, record) -> float:
        """Score how valuable this article would be for labeling."""
        conf = record.sentiment.confidence or 0.5

        if self.strategy == "uncertainty":
            # Lower confidence = higher priority
            return 1.0 - conf

        elif self.strategy == "boundary":
            # Closer to decision boundary (score near 0) = higher priority
            boundary_dist = abs(record.sentiment.score)
            return max(0, 1.0 - boundary_dist * 2)

        else:  # mixed
            uncertainty = 1.0 - conf
            boundary = max(0, 1.0 - abs(record.sentiment.score) * 2)
            return 0.6 * uncertainty + 0.4 * boundary

    def _explain_priority(self, record, priority: float) -> str:
        """Human-readable explanation of why this article was selected."""
        conf = record.sentiment.confidence or 0.5
        score = record.sentiment.score

        parts = []
        if conf < 0.6:
            parts.append(f"low confidence ({conf:.2f})")
        if abs(score) < 0.15:
            parts.append(f"near boundary (score={score:+.3f})")
        if not parts:
            parts.append(f"moderate uncertainty")
        return "; ".join(parts)

    def export_candidates(self, candidates: List[Dict], run_id: str = "") -> Path:
        """
        Export candidates to JSONL for human labeling.

        Each record includes fields for annotators to fill:
        gold_sentiment_label, gold_themes, notes

        Returns:
            Path to the exported file.
        """
        CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"candidates_{run_id or ts}.jsonl"
        path = CANDIDATES_DIR / filename

        with open(path, "w") as f:
            for c in candidates:
                record = {
                    **c,
                    # Fields for human annotator
                    "gold_sentiment_label": "",  # Fill: pos, neg, neu
                    "gold_themes": [],  # Fill: list of themes
                    "notes": "",  # Optional annotator notes
                    "annotated": False,
                }
                f.write(json.dumps(record) + "\n")

        return path
