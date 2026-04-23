"""
Contradiction detection within narrative threads.

Finds article pairs within the same narrative cluster that express
opposing sentiments or entity stances. Uses sentiment divergence
and NLI stance disagreement to flag genuine contradictions vs.
mere negative/positive coverage.
"""

import logging
from typing import List, Dict, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Contradiction:
    """A detected contradiction between two articles."""

    article_a_id: str
    article_a_title: str
    article_b_id: str
    article_b_title: str
    narrative_headline: str
    contradiction_type: str  # "sentiment", "stance", "both"
    severity: float  # 0-1, how strong the contradiction is
    details: str  # human-readable explanation

    def to_dict(self) -> Dict:
        return {
            "article_a_id": self.article_a_id,
            "article_a_title": self.article_a_title,
            "article_b_id": self.article_b_id,
            "article_b_title": self.article_b_title,
            "narrative_headline": self.narrative_headline,
            "contradiction_type": self.contradiction_type,
            "severity": round(self.severity, 3),
            "details": self.details,
        }


class ContradictionDetector:
    """
    Detect contradictions within narrative clusters.

    Two articles contradict when they cover the same story but reach
    opposing conclusions — one positive, one negative toward the same entity,
    or opposite sentiment polarity on the same topic.
    """

    def __init__(
        self,
        sentiment_gap: float = 0.5,
        stance_gap: float = 0.6,
    ):
        """
        Args:
            sentiment_gap: Minimum absolute sentiment difference to flag.
            stance_gap: Minimum stance score difference for same entity.
        """
        self.sentiment_gap = sentiment_gap
        self.stance_gap = stance_gap

    def detect(self, article_records, narratives) -> List[Contradiction]:
        """
        Find contradictions across all narrative threads.

        Args:
            article_records: List of ArticleRecord objects
            narratives: List of Narrative objects from NarrativeBuilder

        Returns:
            List of Contradiction objects, sorted by severity.
        """
        # Index articles by ID
        by_id = {r.id: r for r in article_records}

        contradictions = []
        for narrative in narratives:
            records = [by_id[aid] for aid in narrative.article_ids if aid in by_id]
            if len(records) < 2:
                continue

            contradictions.extend(
                self._check_cluster(records, narrative.headline)
            )

        contradictions.sort(key=lambda c: c.severity, reverse=True)
        return contradictions

    def _check_cluster(self, records, headline: str) -> List[Contradiction]:
        """Check all pairs within a cluster for contradictions."""
        results = []

        for i in range(len(records)):
            for j in range(i + 1, len(records)):
                a, b = records[i], records[j]
                contradiction = self._check_pair(a, b, headline)
                if contradiction:
                    results.append(contradiction)

        return results

    def _check_pair(self, a, b, headline: str) -> Optional[Contradiction]:
        """Check if two articles contradict each other."""
        score_a = a.sentiment.score
        score_b = b.sentiment.score
        sent_gap = abs(score_a - score_b)

        # Check sentiment contradiction
        sent_contradicts = (
            sent_gap >= self.sentiment_gap
            and score_a * score_b < 0  # opposite signs
        )

        # Check stance contradiction — same entity, opposite stances
        stance_contradicts = False
        stance_details = []

        entities_a = {s["entity"]: s for s in a.entity_stances}
        entities_b = {s["entity"]: s for s in b.entity_stances}
        shared = set(entities_a.keys()) & set(entities_b.keys())

        for entity in shared:
            sa = entities_a[entity]
            sb = entities_b[entity]
            gap = abs(sa.get("score", 0) - sb.get("score", 0))
            if gap >= self.stance_gap and sa.get("stance") != sb.get("stance"):
                stance_contradicts = True
                stance_details.append(
                    f"{entity}: {sa['stance']}({sa.get('score', 0):+.2f}) vs {sb['stance']}({sb.get('score', 0):+.2f})"
                )

        if not sent_contradicts and not stance_contradicts:
            return None

        # Determine type and severity
        if sent_contradicts and stance_contradicts:
            ctype = "both"
            severity = min(1.0, (sent_gap + max(abs(sa.get("score", 0) - sb.get("score", 0)) for entity in shared if entity in entities_a and entity in entities_b)) / 2)
        elif sent_contradicts:
            ctype = "sentiment"
            severity = min(1.0, sent_gap)
        else:
            ctype = "stance"
            severity = min(1.0, max(abs(entities_a[e].get("score", 0) - entities_b[e].get("score", 0)) for e in shared if entities_a[e].get("stance") != entities_b[e].get("stance")))

        # Build details
        parts = []
        if sent_contradicts:
            parts.append(f"sentiment: {score_a:+.2f} vs {score_b:+.2f}")
        parts.extend(stance_details)

        return Contradiction(
            article_a_id=a.id,
            article_a_title=a.title,
            article_b_id=b.id,
            article_b_title=b.title,
            narrative_headline=headline,
            contradiction_type=ctype,
            severity=severity,
            details="; ".join(parts),
        )
