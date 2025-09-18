#!/usr/bin/env python3
"""
Global Perception Index - RSS Version
=====================================
RSS-only version of GPI system for country perception measurement.
Scale: -100 to +100 (0 = neutral)
"""

import numpy as np
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
import logging
from pathlib import Path
import json
from collections import defaultdict

# Import RSS-only news system
from .rss_source_registry import RSSSourceRegistry, UnifiedEvent, initialize_rss_registry_from_master_sources

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class PerceptionSignal:
    """Processed signal from a news event."""
    origin_country: str
    target_country: str
    sentiment: float  # -100 to +100
    confidence: float  # 0.0 to 1.0
    source_reliability: float  # 0.0 to 1.0
    audience_weight: float  # 0.0 to 1.0
    timestamp: datetime
    event_id: str
    pillar: str  # economy, governance, security, society, environment


class StanceAnalyzer:
    """Analyzes country sentiment from text."""

    def analyze_stance(self, text: str, target_entity: str, hint: Optional[float] = None) -> float:
        """Analyze stance towards target entity in text."""
        text = text.lower()
        target = target_entity.lower()

        # Simple keyword-based sentiment analysis
        positive_words = ['good', 'great', 'excellent', 'positive', 'strong', 'success', 'growing', 'improved']
        negative_words = ['bad', 'terrible', 'poor', 'negative', 'weak', 'failure', 'declining', 'crisis']

        # Context-aware scoring
        sentences = text.split('.')
        target_sentences = [s for s in sentences if target in s]

        if not target_sentences:
            return 0.0

        scores = []
        for sentence in target_sentences:
            pos_count = sum(1 for word in positive_words if word in sentence)
            neg_count = sum(1 for word in negative_words if word in sentence)

            if pos_count + neg_count == 0:
                scores.append(0.0)
            else:
                score = (pos_count - neg_count) / (pos_count + neg_count) * 100
                scores.append(score)

        return np.mean(scores) if scores else 0.0


class PillarClassifier:
    """Classifies content into GPI pillars."""

    def __init__(self):
        self.pillar_keywords = {
            'economy': ['economic', 'economy', 'trade', 'business', 'financial', 'market', 'gdp', 'growth'],
            'governance': ['government', 'political', 'democracy', 'policy', 'law', 'regulation', 'election'],
            'security': ['security', 'military', 'defense', 'war', 'conflict', 'terrorism', 'peace'],
            'society': ['social', 'culture', 'education', 'health', 'human rights', 'equality', 'welfare'],
            'environment': ['environment', 'climate', 'pollution', 'energy', 'sustainable', 'green', 'carbon']
        }

    def classify(self, text: str) -> Dict[str, float]:
        """Classify text into pillar categories."""
        text = text.lower()
        scores = {}

        for pillar, keywords in self.pillar_keywords.items():
            score = sum(1 for keyword in keywords if keyword in text)
            scores[pillar] = score

        # Normalize
        total = sum(scores.values())
        if total > 0:
            scores = {k: v / total for k, v in scores.items()}
        else:
            # Default distribution if no keywords found
            scores = {k: 0.2 for k in self.pillar_keywords.keys()}

        return scores


class GPIRss:
    """RSS-based Global Perception Index calculator."""

    def __init__(self):
        self.registry = initialize_rss_registry_from_master_sources()
        self.stance_analyzer = StanceAnalyzer()
        self.pillar_classifier = PillarClassifier()

        # Pillar weights (sum to 1.0)
        self.pillar_weights = {
            'economy': 0.3,
            'governance': 0.25,
            'security': 0.2,
            'society': 0.15,
            'environment': 0.1
        }

    def calculate_gpi(self, target_country: str, days_back: int = 7) -> Dict[str, Any]:
        """Calculate GPI for target country using RSS sources."""
        logger.info(f"Calculating RSS-based GPI for {target_country}...")

        # Fetch relevant articles
        events = self.registry.fetch_articles(
            query=target_country,
            days_back=days_back,
            max_articles=50
        )

        logger.info(f"Fetched {len(events)} RSS articles for {target_country}")

        if not events:
            return {
                'target_country': target_country,
                'overall_score': 0.0,
                'confidence': 0.0,
                'articles_processed': 0,
                'data_source': 'RSS',
                'message': 'No articles found in RSS feeds'
            }

        # Process events into signals
        signals = []
        for event in events:
            signal = self.process_event(event, target_country)
            if signal:
                signals.append(signal)

        if not signals:
            return {
                'target_country': target_country,
                'overall_score': 0.0,
                'confidence': 0.0,
                'articles_processed': len(events),
                'data_source': 'RSS',
                'message': 'No perception signals extracted'
            }

        # Aggregate signals by pillar
        pillar_scores = self.aggregate_to_pillars(signals)

        # Calculate overall score
        overall_score = sum(
            pillar_scores.get(pillar, 0.0) * weight
            for pillar, weight in self.pillar_weights.items()
        )

        # Calculate confidence
        confidence = min(len(signals) / 20.0, 1.0)  # Max confidence at 20+ signals

        return {
            'target_country': target_country,
            'overall_score': overall_score,
            'pillar_scores': pillar_scores,
            'confidence': confidence,
            'articles_processed': len(events),
            'signals_extracted': len(signals),
            'data_source': 'RSS',
            'timestamp': datetime.now().isoformat()
        }

    def process_event(self, event: UnifiedEvent, target_country: str) -> Optional[PerceptionSignal]:
        """Process RSS event into perception signal."""
        try:
            # Analyze sentiment towards target country
            content = event.title + ' ' + event.full_text
            sentiment = self.stance_analyzer.analyze_stance(content, target_country)

            # Skip neutral articles
            if abs(sentiment) < 5.0:
                return None

            # Classify into pillars
            pillar_scores = self.pillar_classifier.classify(content)
            dominant_pillar = max(pillar_scores.items(), key=lambda x: x[1])[0]

            # Create signal
            signal = PerceptionSignal(
                origin_country=event.origin_country,
                target_country=target_country,
                sentiment=sentiment,
                confidence=0.8,  # Base confidence for RSS
                source_reliability=0.7,  # Assume decent reliability for RSS
                audience_weight=0.5,  # Medium weight
                timestamp=event.published_at,
                event_id=event.event_id,
                pillar=dominant_pillar
            )

            return signal

        except Exception as e:
            logger.error(f"Error processing event {event.event_id}: {e}")
            return None

    def aggregate_to_pillars(self, signals: List[PerceptionSignal]) -> Dict[str, float]:
        """Aggregate signals into pillar scores."""
        pillar_scores = defaultdict(list)

        for signal in signals:
            weighted_sentiment = (
                signal.sentiment *
                signal.confidence *
                signal.source_reliability *
                signal.audience_weight
            )
            pillar_scores[signal.pillar].append(weighted_sentiment)

        # Calculate average for each pillar
        result = {}
        for pillar in self.pillar_weights.keys():
            if pillar_scores[pillar]:
                result[pillar] = np.mean(pillar_scores[pillar])
            else:
                result[pillar] = 0.0

        return result

    def get_country_rankings(self, countries: List[str], days_back: int = 7) -> List[Tuple[str, float]]:
        """Get GPI rankings for multiple countries."""
        results = []

        for country in countries:
            gpi_result = self.calculate_gpi(country, days_back)
            score = gpi_result.get('overall_score', 0.0)
            results.append((country, score))

        # Sort by score (highest first)
        results.sort(key=lambda x: x[1], reverse=True)
        return results


def test_rss_gpi():
    """Test the RSS-based GPI system."""
    print("🌍 RSS-BASED GLOBAL PERCEPTION INDEX TEST")
    print("=" * 60)

    gpi = GPIRss()

    # Test with Germany
    print("\nTesting Germany GPI calculation...")
    result = gpi.calculate_gpi("Germany", days_back=7)

    print(f"\n📊 GERMANY GPI RESULTS")
    print(f"Overall Score: {result.get('overall_score', 0):.1f}/100")
    print(f"Confidence: {result.get('confidence', 0):.2f}")
    print(f"Articles Processed: {result.get('articles_processed', 0)}")
    print(f"Signals Extracted: {result.get('signals_extracted', 0)}")
    print(f"Data Source: {result.get('data_source', 'Unknown')}")

    if 'pillar_scores' in result:
        print(f"\n🏛️ PILLAR BREAKDOWN:")
        for pillar, score in result['pillar_scores'].items():
            print(f"  {pillar.title()}: {score:.1f}/100")

    # Test rankings
    print(f"\n🏆 SAMPLE COUNTRY RANKINGS")
    countries = ["Germany", "France", "Italy"]
    rankings = gpi.get_country_rankings(countries, days_back=7)

    for i, (country, score) in enumerate(rankings, 1):
        print(f"  {i}. {country}: {score:.1f}/100")


if __name__ == "__main__":
    test_rss_gpi()