"""
Narrative clustering: groups articles into story threads.

Builds on DocumentClusterer (sentence-transformer embeddings + agglomerative
clustering) and enriches each cluster with:
  - headline (extracted from article titles)
  - sentiment arc (mean, std, direction)
  - source composition
  - geographic composition
  - salience score
"""

import logging
import numpy as np
from typing import List, Dict, Optional
from collections import Counter
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Narrative:
    """A narrative thread — a group of articles covering the same story."""

    cluster_id: int
    headline: str
    article_ids: List[str] = field(default_factory=list)
    article_count: int = 0

    # Sentiment
    mean_sentiment: float = 0.0
    sentiment_std: float = 0.0
    sentiment_direction: str = "neutral"  # negative, neutral, positive

    # Composition
    sources: Dict[str, int] = field(default_factory=dict)  # source -> count
    regions: Dict[str, int] = field(default_factory=dict)  # country -> count
    themes: List[str] = field(default_factory=list)

    # Salience: how important is this narrative?
    salience: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "cluster_id": self.cluster_id,
            "headline": self.headline,
            "article_ids": self.article_ids,
            "article_count": self.article_count,
            "mean_sentiment": round(self.mean_sentiment, 4),
            "sentiment_std": round(self.sentiment_std, 4),
            "sentiment_direction": self.sentiment_direction,
            "sources": self.sources,
            "regions": self.regions,
            "themes": self.themes,
            "salience": round(self.salience, 3),
        }


class NarrativeBuilder:
    """
    Build narrative threads from article records.

    Uses DocumentClusterer for embedding-based grouping, then enriches
    each cluster into a Narrative with metadata and salience scoring.
    """

    def __init__(self, cosine_threshold: float = 0.72, min_cluster_articles: int = 2):
        self.cosine_threshold = cosine_threshold
        self.min_cluster_articles = min_cluster_articles
        self._clusterer = None

    def _get_clusterer(self):
        if self._clusterer is None:
            from .cluster import DocumentClusterer
            self._clusterer = DocumentClusterer(config={
                "cosine_threshold": self.cosine_threshold,
            })
        return self._clusterer

    def build_narratives(self, article_records) -> List[Narrative]:
        """
        Cluster article records into narrative threads.

        Args:
            article_records: List of ArticleRecord (Pydantic models)

        Returns:
            List of Narrative objects, sorted by salience (highest first).
        """
        if len(article_records) < 2:
            return []

        # Prepare dicts for clustering
        docs = []
        for rec in article_records:
            docs.append({
                "id": rec.id,
                "title": rec.title,
                "description": rec.summary or rec.ai_summary or "",
                "content": rec.ai_summary or rec.summary or "",
            })

        # Cluster
        try:
            clusterer = self._get_clusterer()
            clustered = clusterer.cluster_articles(docs)
        except Exception as e:
            logger.debug(f"Narrative clustering failed: {e}")
            return []

        # Group by cluster_id
        clusters: Dict[int, List[int]] = {}
        for i, doc in enumerate(clustered):
            cid = doc.get("cluster_id", i)
            clusters.setdefault(cid, []).append(i)

        # Build narratives
        narratives = []
        total_articles = len(article_records)

        for cid, indices in clusters.items():
            if len(indices) < self.min_cluster_articles:
                continue

            records = [article_records[i] for i in indices]
            narrative = self._build_single(cid, records, total_articles)
            narratives.append(narrative)

        narratives.sort(key=lambda n: n.salience, reverse=True)
        return narratives

    def _build_single(self, cluster_id: int, records, total_articles: int) -> Narrative:
        """Build a single Narrative from a cluster of ArticleRecords."""

        # Headline: pick the title of the highest-relevance article
        best = max(records, key=lambda r: r.relevance)
        headline = best.title

        # Sentiment
        scores = [r.sentiment.score for r in records]
        mean_s = float(np.mean(scores))
        std_s = float(np.std(scores))
        if mean_s > 0.15:
            direction = "positive"
        elif mean_s < -0.15:
            direction = "negative"
        else:
            direction = "neutral"

        # Sources
        source_counts = Counter(r.source for r in records)

        # Regions: extract GPE entities
        region_counts = Counter()
        for r in records:
            for ent in r.entities:
                if ent.get("type") == "GPE":
                    region_counts[ent["text"]] += 1

        # Themes
        theme_counts = Counter()
        for r in records:
            if r.signals and r.signals.themes:
                theme_counts.update(r.signals.themes)
        top_themes = [t for t, _ in theme_counts.most_common(3)]

        # Salience score: combination of volume, sentiment extremity, source diversity
        volume_score = len(records) / max(total_articles, 1)
        sentiment_extremity = abs(mean_s)
        source_diversity = min(len(source_counts), 5) / 5.0
        salience = (
            0.4 * volume_score
            + 0.3 * sentiment_extremity
            + 0.3 * source_diversity
        )

        return Narrative(
            cluster_id=cluster_id,
            headline=headline,
            article_ids=[r.id for r in records],
            article_count=len(records),
            mean_sentiment=mean_s,
            sentiment_std=std_s,
            sentiment_direction=direction,
            sources=dict(source_counts),
            regions=dict(region_counts),
            themes=top_themes,
            salience=salience,
        )
