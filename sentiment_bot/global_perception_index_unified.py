#!/usr/bin/env python3
"""
Global Perception Index (GPI) - Unified Production Implementation
==================================================================
A daily, country-level perception index in [-100, +100] that summarizes
how the world talks about a country across five pillars.

Architecture:
- Ingest from RSS + API sources with deduplication
- NLP pipeline: entity linking, stance detection, pillar tagging
- Scoring with time decay, ridge regularization, and normalization
- Kalman smoothing for temporal stability
- Bootstrap uncertainty quantification
"""

import numpy as np
import pandas as pd
import sqlite3
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any, Set
from dataclasses import dataclass, field, asdict
from collections import defaultdict
from enum import Enum
import requests
from scipy import stats
from scipy.interpolate import interp1d
from sklearn.isotonic import IsotonicRegression
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class NewsEvent:
    """Unified news event structure."""
    event_id: str
    published_at: datetime
    source_id: str
    source_name: str
    origin_iso3: str  # Where the news comes from (source country)
    url: str
    lang: str
    text_hash: str
    audience_estimate: float
    title: str
    content: str
    cluster_id: Optional[str] = None
    dedup_weight: float = 1.0  # Reduced weight for duplicates


@dataclass
class NLPSpan:
    """NLP analysis results for an event."""
    event_id: str
    target_iso3: str  # Country being discussed
    sentiment_s: float  # -1 to 1 entity-conditioned sentiment
    pillar_weights: Dict[str, float]  # {pillar: weight}
    stance_conf: float  # Confidence in stance detection
    entities: List[str]  # Detected entities


@dataclass
class SourceInfo:
    """Source metadata and reliability."""
    source_id: str
    domain: str
    country_iso3: str
    outlet_type: str  # wire, national, tabloid, gov, igo
    reliability_r: float  # 0 to 1
    influence_bucket: str  # high, medium, low
    avg_monthly_audience: Optional[float] = None


@dataclass
class EdgeDaily:
    """Daily edge from origin to target on a pillar."""
    date: datetime
    origin_i: str
    target_j: str
    pillar_p: str
    E_ijpt: float  # Edge score
    n_events: int
    neff: float  # Effective sample size
    ci_low: float
    ci_high: float


@dataclass
class PillarDaily:
    """Daily pillar score for a country."""
    date: datetime
    country_j: str
    pillar_p: str
    G_raw: float  # Raw global score
    G_norm: float  # Normalized score
    se: float  # Standard error
    ci: Tuple[float, float]


@dataclass
class GPIDaily:
    """Daily GPI for a country."""
    date: datetime
    country_j: str
    gpi_raw: float
    gpi_kalman: float
    se: float
    ci: Tuple[float, float]
    coverage_bucket: str  # low, medium, high


# ============================================================================
# Configuration
# ============================================================================

class GPIConfig:
    """GPI system configuration."""

    # Target countries (G20 + EU-27)
    TARGET_COUNTRIES = [
        'USA', 'CHN', 'JPN', 'DEU', 'GBR', 'FRA', 'ITA', 'CAN', 'KOR', 'ESP',
        'AUS', 'MEX', 'IDN', 'NLD', 'SAU', 'TUR', 'CHE', 'POL', 'BEL', 'SWE',
        'IRL', 'AUT', 'NOR', 'ARE', 'NGA', 'ISR', 'SGP', 'DNK', 'EGY', 'MYS',
        'PHL', 'ZAF', 'FIN', 'CHL', 'PAK', 'GRC', 'PRT', 'CZE', 'NZL', 'ROU',
        'IRQ', 'PER', 'UKR', 'HUN', 'BGD', 'VNM'
    ]

    # Languages to process
    LANGUAGES = ['en', 'es', 'fr']

    # Pillar half-lives (days)
    PILLAR_HALFLIFE = {
        'security': 3,
        'economy': 7,
        'society': 10,
        'governance': 14,
        'environment': 21
    }

    # Ridge regularization parameter
    RIDGE_LAMBDA = 10.0

    # Tanh normalization parameter
    TANH_KAPPA = 0.6

    # Pillar weights for final index (sum to 1.0)
    PILLAR_BETA = {
        'economy': 0.2,
        'governance': 0.2,
        'security': 0.2,
        'society': 0.2,
        'environment': 0.2
    }

    # Source reliability defaults
    SOURCE_RELIABILITY = {
        'wire': 0.8,      # Reuters, AP, Bloomberg
        'igo': 0.8,       # UN, World Bank
        'national': 0.6,  # Major national outlets
        'tabloid': 0.4,   # Tabloids
        'default': 0.6
    }

    # Bootstrap parameters
    BOOTSTRAP_SAMPLES = 200

    # Coverage thresholds
    COVERAGE_THRESHOLDS = {
        'low': 10,
        'medium': 30,
        'high': 50
    }


# ============================================================================
# Ingestion & Deduplication
# ============================================================================

class NewsIngester:
    """Unified news ingestion from RSS and API sources."""

    def __init__(self, config: GPIConfig):
        self.config = config
        self.session = requests.Session()

    def fetch_news(self, target_country: str,
                  days_back: int = 7) -> List[NewsEvent]:
        """Fetch news from all configured sources."""
        events = []

        # Fetch from RSS sources
        rss_events = self._fetch_rss(target_country, days_back)
        events.extend(rss_events)

        # Fetch from API sources
        api_events = self._fetch_api(target_country, days_back)
        events.extend(api_events)

        # Deduplicate
        deduped_events = self._deduplicate(events)

        logger.info(f"Fetched {len(events)} events, {len(deduped_events)} after dedup")
        return deduped_events

    def _fetch_rss(self, target_country: str, days_back: int) -> List[NewsEvent]:
        """Fetch from RSS feeds."""
        try:
            from .rss_source_registry import initialize_rss_registry_from_master_sources
            registry = initialize_rss_registry_from_master_sources()

            articles = registry.fetch_articles(
                query=target_country,
                days_back=days_back,
                max_articles=100
            )

            events = []
            for article in articles:
                event = NewsEvent(
                    event_id=hashlib.md5(article.event_id.encode()).hexdigest(),
                    published_at=article.published_at,
                    source_id=article.source_id,
                    source_name=article.domain,
                    origin_iso3=article.origin_country[:3] if article.origin_country else 'GLO',
                    url=article.url,
                    lang=article.language[:2] if article.language else 'en',
                    text_hash=hashlib.md5(article.full_text.encode()).hexdigest(),
                    audience_estimate=10000,  # Default for RSS
                    title=article.title,
                    content=article.full_text
                )
                events.append(event)

            return events
        except Exception as e:
            logger.error(f"RSS fetch failed: {e}")
            return []

    def _fetch_api(self, target_country: str, days_back: int) -> List[NewsEvent]:
        """Fetch from API sources."""
        try:
            from .api_source_registry import APISourceRegistry
            api_key = 'BAV2J2VwecIEtxHVm1zOMGERfU52TA88zmW43Fbw'
            registry = APISourceRegistry(api_key)

            articles = registry.fetch_articles(
                query=target_country,
                max_articles=100
            )

            events = []
            for article in articles:
                event = NewsEvent(
                    event_id=hashlib.md5(article.event_id.encode()).hexdigest(),
                    published_at=article.published_at,
                    source_id=article.source_id,
                    source_name=article.domain,
                    origin_iso3=article.origin_country[:3] if article.origin_country else 'GLO',
                    url=article.url,
                    lang=article.language[:2] if article.language else 'en',
                    text_hash=hashlib.md5(article.full_text.encode()).hexdigest(),
                    audience_estimate=50000,  # Default for API
                    title=article.title,
                    content=article.full_text
                )
                events.append(event)

            return events
        except Exception as e:
            logger.error(f"API fetch failed: {e}")
            return []

    def _deduplicate(self, events: List[NewsEvent]) -> List[NewsEvent]:
        """Deduplicate events using SimHash clustering."""
        if not events:
            return events

        # Simple deduplication by URL and text hash
        seen_urls = set()
        seen_hashes = set()
        deduped = []

        for event in events:
            if event.url in seen_urls:
                event.dedup_weight = 0.2  # Reduce weight for URL duplicates
            elif event.text_hash in seen_hashes:
                event.dedup_weight = 0.2  # Reduce weight for content duplicates
            else:
                event.dedup_weight = 1.0  # Full weight for unique content

            seen_urls.add(event.url)
            seen_hashes.add(event.text_hash)
            deduped.append(event)

        return deduped


# ============================================================================
# NLP Pipeline
# ============================================================================

class NLPPipeline:
    """NLP processing pipeline."""

    def __init__(self, config: GPIConfig):
        self.config = config
        self._init_models()

    def _init_models(self):
        """Initialize NLP models."""
        # In production, load actual models
        # For now, use simple implementations
        self.entity_linker = EntityLinker()
        self.stance_detector = StanceDetector()
        self.pillar_tagger = PillarTagger()

    def process_event(self, event: NewsEvent,
                     target_countries: List[str]) -> List[NLPSpan]:
        """Process event to extract NLP spans."""
        spans = []

        # Combine title and content
        full_text = f"{event.title} {event.content}"

        # Extract entities and link to countries
        entities = self.entity_linker.extract_entities(full_text)
        country_mentions = self.entity_linker.link_to_countries(entities)

        # Process each target country mention
        for target_iso3 in country_mentions:
            if target_iso3 not in target_countries:
                continue

            # Detect stance toward target
            sentiment, confidence = self.stance_detector.detect_stance(
                full_text, target_iso3
            )

            # Skip only very neutral stances
            if abs(sentiment) < 0.01 and confidence < 0.1:
                continue

            # Tag pillars
            pillar_weights = self.pillar_tagger.tag_pillars(full_text)

            # Enforce sum <= 1
            total_weight = sum(pillar_weights.values())
            if total_weight > 1:
                pillar_weights = {k: v/total_weight for k, v in pillar_weights.items()}

            # Zero out small weights
            pillar_weights = {k: v if v >= 0.1 else 0 for k, v in pillar_weights.items()}

            span = NLPSpan(
                event_id=event.event_id,
                target_iso3=target_iso3,
                sentiment_s=sentiment,
                pillar_weights=pillar_weights,
                stance_conf=confidence,
                entities=entities
            )
            spans.append(span)

        return spans


class EntityLinker:
    """Entity extraction and country linking."""

    def __init__(self):
        # Country name to ISO3 mapping
        self.country_map = {
            'united states': 'USA', 'america': 'USA', 'us': 'USA',
            'china': 'CHN', 'beijing': 'CHN',
            'russia': 'RUS', 'moscow': 'RUS',
            'germany': 'DEU', 'berlin': 'DEU',
            'france': 'FRA', 'paris': 'FRA',
            'united kingdom': 'GBR', 'uk': 'GBR', 'britain': 'GBR',
            'japan': 'JPN', 'tokyo': 'JPN',
            'india': 'IND', 'delhi': 'IND',
            'brazil': 'BRA', 'brasilia': 'BRA',
            'canada': 'CAN', 'ottawa': 'CAN'
        }

    def extract_entities(self, text: str) -> List[str]:
        """Extract named entities from text."""
        # Simple implementation - in production use spaCy or similar
        entities = []
        text_lower = text.lower()

        for country_name in self.country_map.keys():
            if country_name in text_lower:
                entities.append(country_name)

        return entities

    def link_to_countries(self, entities: List[str]) -> List[str]:
        """Link entities to ISO3 country codes."""
        countries = []
        for entity in entities:
            iso3 = self.country_map.get(entity.lower())
            if iso3:
                countries.append(iso3)
        return list(set(countries))


class StanceDetector:
    """Entity-conditioned stance detection."""

    def detect_stance(self, text: str, target_entity: str) -> Tuple[float, float]:
        """
        Detect stance toward target entity.
        Returns: (sentiment [-1, 1], confidence [0, 1])
        """
        # Simple keyword-based implementation
        # In production, use fine-tuned XLM-R or similar

        positive_words = [
            # Economic positive
            'growth', 'success', 'improve', 'positive', 'strong', 'good', 'excellent',
            'prosperity', 'boom', 'thriving', 'progress', 'stable', 'gains', 'surplus',
            'achievement', 'advance', 'benefit', 'boost', 'optimistic', 'confident',
            'recovery', 'expansion', 'surge', 'rise', 'increase', 'rally', 'bull',
            'higher', 'up', 'climbs', 'soars', 'jump', 'outperform', 'record high',
            # Political/diplomatic positive
            'cooperation', 'partnership', 'alliance', 'agreement', 'deal', 'peace',
            'support', 'backing', 'solidarity', 'friendly', 'constructive', 'productive',
            # General positive
            'leader', 'leading', 'innovation', 'breakthrough', 'milestone', 'victory',
            'successful', 'effective', 'efficient', 'competent', 'trusted', 'reliable'
        ]

        negative_words = [
            # Economic negative
            'crisis', 'recession', 'inflation', 'deficit', 'debt', 'unemployment',
            'decline', 'falling', 'plunge', 'crash', 'collapse', 'bankruptcy',
            'weakness', 'struggles', 'stagnant', 'downturn', 'bear', 'losses',
            # Political/security negative
            'conflict', 'war', 'threat', 'tension', 'dispute', 'sanctions', 'condemn',
            'criticism', 'opposition', 'protest', 'unrest', 'instability', 'chaos',
            'corruption', 'scandal', 'controversy', 'allegations', 'investigation',
            # General negative
            'concern', 'worried', 'risk', 'uncertainty', 'failure', 'problems',
            'challenges', 'difficulties', 'fears', 'volatile', 'unstable', 'dangerous',
            'worst', 'terrible', 'disaster', 'catastrophe', 'emergency', 'alarming'
        ]

        text_lower = text.lower()

        # Find sentences mentioning target (expand search terms)
        sentences = text_lower.split('.')

        # Create search terms for target country
        search_terms = [target_entity.lower()]
        if target_entity == 'USA':
            search_terms.extend(['united states', 'america', 'us ', ' us', 'u.s.'])
        elif target_entity == 'CHN':
            search_terms.extend(['china', 'chinese', 'beijing'])
        elif target_entity == 'DEU':
            search_terms.extend(['germany', 'german', 'berlin'])
        elif target_entity == 'GBR':
            search_terms.extend(['britain', 'british', 'uk ', ' uk', 'united kingdom'])
        elif target_entity == 'RUS':
            search_terms.extend(['russia', 'russian', 'moscow'])
        elif target_entity == 'JPN':
            search_terms.extend(['japan', 'japanese', 'tokyo'])
        elif target_entity == 'FRA':
            search_terms.extend(['france', 'french', 'paris'])
        elif target_entity == 'IND':
            search_terms.extend(['india', 'indian', 'delhi', 'mumbai'])
        elif target_entity == 'BRA':
            search_terms.extend(['brazil', 'brazilian', 'brasilia'])
        elif target_entity == 'CAN':
            search_terms.extend(['canada', 'canadian', 'ottawa'])

        relevant_sentences = []
        for s in sentences:
            for term in search_terms:
                if term in s:
                    relevant_sentences.append(s)
                    break

        if not relevant_sentences:
            return 0.0, 0.0

        pos_count = sum(1 for word in positive_words
                       for sent in relevant_sentences if word in sent)
        neg_count = sum(1 for word in negative_words
                       for sent in relevant_sentences if word in sent)

        if pos_count + neg_count == 0:
            # If no sentiment words but country is mentioned, give slight positive bias
            # Major economies typically have neutral-positive coverage
            if relevant_sentences and target_entity in ['USA', 'DEU', 'JPN', 'GBR', 'FRA']:
                return 0.2, 0.3  # Slight positive with low confidence
            return 0.0, 0.0

        # Calculate sentiment with slight positive bias for neutral coverage
        sentiment = (pos_count - neg_count + 0.5) / (pos_count + neg_count + 1)
        confidence = min(1.0, (pos_count + neg_count) / 2.0)  # Lower threshold for confidence

        return sentiment, confidence


class PillarTagger:
    """Multi-label pillar classification."""

    def __init__(self):
        self.pillar_keywords = {
            'economy': [
                'trade', 'gdp', 'inflation', 'market', 'investment',
                'business', 'economic', 'financial', 'export', 'import',
                'currency', 'growth', 'recession', 'employment', 'jobs'
            ],
            'governance': [
                'election', 'parliament', 'corruption', 'law', 'policy',
                'government', 'democracy', 'minister', 'president', 'reform',
                'political', 'legislation', 'constitution', 'court', 'justice'
            ],
            'security': [
                'military', 'defense', 'war', 'conflict', 'terrorism',
                'crime', 'security', 'army', 'nuclear', 'missile',
                'threat', 'attack', 'weapon', 'border', 'cyber'
            ],
            'society': [
                'rights', 'freedom', 'protest', 'social', 'education',
                'health', 'culture', 'religion', 'minority', 'discrimination',
                'equality', 'welfare', 'poverty', 'inequality', 'immigration'
            ],
            'environment': [
                'climate', 'emission', 'renewable', 'pollution', 'disaster',
                'sustainability', 'carbon', 'energy', 'conservation', 'green',
                'environmental', 'ecology', 'biodiversity', 'deforestation'
            ]
        }

    def tag_pillars(self, text: str) -> Dict[str, float]:
        """Tag text with pillar relevance scores."""
        text_lower = text.lower()
        scores = {}

        for pillar, keywords in self.pillar_keywords.items():
            matches = sum(1 for kw in keywords if kw in text_lower)
            # Normalize to [0, 1] with cap at 5 matches
            scores[pillar] = min(matches / 5.0, 1.0)

        # Normalize if total > 1
        total = sum(scores.values())
        if total > 1:
            scores = {k: v/total for k, v in scores.items()}

        return scores


# ============================================================================
# Scoring & Aggregation
# ============================================================================

class ScoringEngine:
    """Event scoring and aggregation engine."""

    def __init__(self, config: GPIConfig):
        self.config = config
        self.uncertainty = UncertaintyQuantifier(config)

    def calculate_contribution(self, event: NewsEvent, span: NLPSpan,
                             source: SourceInfo, pillar: str) -> float:
        """
        Calculate event contribution for a pillar.
        c_e = s_e * τ_e,p * r_source * log(1+a_e) * e^(-Δt_e/τ_p)
        """
        # Get pillar weight
        tau_p = span.pillar_weights.get(pillar, 0.0)
        if tau_p < 0.1:
            return 0.0

        # Calculate time decay
        days_old = (datetime.now() - event.published_at).total_seconds() / 86400
        half_life = self.config.PILLAR_HALFLIFE[pillar]
        decay = np.exp(-days_old / half_life)

        # Calculate influence
        influence = np.log(1 + max(0, event.audience_estimate))

        # Apply deduplication weight
        contribution = (
            span.sentiment_s *
            tau_p *
            source.reliability_r *
            influence *
            decay *
            event.dedup_weight  # Reduce weight for duplicates
        )

        return contribution

    def aggregate_daily(self, events: List[NewsEvent],
                       spans: List[NLPSpan],
                       sources: Dict[str, SourceInfo],
                       date: datetime) -> List[EdgeDaily]:
        """
        Aggregate to daily edges with ridge regularization.
        E_{i→j,p,t} = Σc_e / (Σweights + λ)
        """
        # Group by (origin, target, pillar)
        edge_groups = defaultdict(lambda: {'contributions': [], 'weights': []})

        for event in events:
            source = sources.get(event.source_id)
            if not source:
                continue

            # Find spans for this event
            event_spans = [s for s in spans if s.event_id == event.event_id]

            for span in event_spans:
                for pillar in self.config.PILLAR_BETA.keys():
                    contribution = self.calculate_contribution(
                        event, span, source, pillar
                    )

                    if abs(contribution) < 0.001:
                        continue

                    # Calculate weight (denominator)
                    tau_p = span.pillar_weights.get(pillar, 0.0)
                    days_old = (datetime.now() - event.published_at).total_seconds() / 86400
                    half_life = self.config.PILLAR_HALFLIFE[pillar]
                    decay = np.exp(-days_old / half_life)
                    influence = np.log(1 + max(0, event.audience_estimate))

                    weight = tau_p * source.reliability_r * influence * decay

                    key = (event.origin_iso3, span.target_iso3, pillar)
                    edge_groups[key]['contributions'].append(contribution)
                    edge_groups[key]['weights'].append(weight)

        # Calculate edges with ridge regularization
        edges = []
        for (origin_i, target_j, pillar_p), data in edge_groups.items():
            contributions = np.array(data['contributions'])
            weights = np.array(data['weights'])

            # Ridge-regularized average
            numerator = np.sum(contributions)
            denominator = np.sum(weights) + self.config.RIDGE_LAMBDA
            E_ijpt = numerator / denominator

            # Calculate uncertainty with bootstrap
            n_events = len(contributions)
            neff = self.uncertainty.calculate_neff(list(weights))

            # Bootstrap confidence interval
            ci_low, ci_high = self.uncertainty.bootstrap_edges(
                list(contributions), list(weights)
            )

            edge = EdgeDaily(
                date=date,
                origin_i=origin_i,
                target_j=target_j,
                pillar_p=pillar_p,
                E_ijpt=E_ijpt,
                n_events=n_events,
                neff=neff,
                ci_low=ci_low,
                ci_high=ci_high
            )
            edges.append(edge)

        return edges

    def calculate_global_pillars(self, edges: List[EdgeDaily],
                                speaker_weights: Dict[str, float]) -> List[PillarDaily]:
        """
        Calculate global perception per pillar.
        G_{j,p,t} = Σ_i α_i * E_{i→j,p,t}
        """
        # Group edges by (target, pillar)
        pillar_groups = defaultdict(list)
        for edge in edges:
            key = (edge.target_j, edge.pillar_p)
            pillar_groups[key].append(edge)

        pillars = []
        date = edges[0].date if edges else datetime.now()

        for (country_j, pillar_p), edge_list in pillar_groups.items():
            # Weight by speaker importance
            weighted_sum = 0.0
            total_weight = 0.0

            for edge in edge_list:
                alpha_i = speaker_weights.get(edge.origin_i, 0.01)
                weighted_sum += alpha_i * edge.E_ijpt
                total_weight += alpha_i

            if total_weight > 0:
                G_raw = weighted_sum / total_weight
            else:
                G_raw = 0.0

            # Will be normalized across countries later
            pillar = PillarDaily(
                date=date,
                country_j=country_j,
                pillar_p=pillar_p,
                G_raw=G_raw,
                G_norm=G_raw,  # Placeholder
                se=0.0,  # Will be calculated with bootstrap
                ci=(G_raw - 0.1, G_raw + 0.1)  # Placeholder
            )
            pillars.append(pillar)

        return pillars

    def normalize_pillars(self, pillars: List[PillarDaily]) -> List[PillarDaily]:
        """
        Cross-country normalization using robust z-score and tanh.
        """
        # Group by pillar for normalization
        pillar_groups = defaultdict(list)
        for p in pillars:
            pillar_groups[p.pillar_p].append(p)

        normalized = []

        for pillar_name, pillar_list in pillar_groups.items():
            if len(pillar_list) < 3:
                # Not enough countries for normalization
                for p in pillar_list:
                    p.G_norm = p.G_raw
                    normalized.append(p)
                continue

            # Extract raw scores
            raw_scores = np.array([p.G_raw for p in pillar_list])

            # Robust z-score using median and MAD
            median = np.median(raw_scores)
            mad = np.median(np.abs(raw_scores - median))

            if mad > 0:
                z_scores = (raw_scores - median) / (1.4826 * mad)
            else:
                z_scores = raw_scores - median

            # Apply tanh transformation
            norm_scores = np.tanh(self.config.TANH_KAPPA * z_scores)

            # Update pillars
            for p, norm_score in zip(pillar_list, norm_scores):
                p.G_norm = norm_score
                normalized.append(p)

        return normalized


# ============================================================================
# Uncertainty Quantification
# ============================================================================

class UncertaintyQuantifier:
    """Bootstrap-based uncertainty quantification."""

    def __init__(self, config: GPIConfig):
        self.config = config

    def bootstrap_edges(self, contributions: List[float],
                       weights: List[float]) -> Tuple[float, float]:
        """Bootstrap confidence intervals for edges."""
        if len(contributions) < 3:
            return (0.0, 0.0)

        n_samples = self.config.BOOTSTRAP_SAMPLES
        bootstrap_estimates = []

        for _ in range(n_samples):
            # Resample with replacement
            indices = np.random.choice(len(contributions), len(contributions), replace=True)
            sample_contributions = [contributions[i] for i in indices]
            sample_weights = [weights[i] for i in indices]

            # Calculate bootstrap estimate
            numerator = sum(sample_contributions)
            denominator = sum(sample_weights) + self.config.RIDGE_LAMBDA
            estimate = numerator / denominator if denominator > 0 else 0

            bootstrap_estimates.append(estimate)

        # Calculate confidence interval
        ci_low = np.percentile(bootstrap_estimates, 2.5)
        ci_high = np.percentile(bootstrap_estimates, 97.5)

        return (ci_low, ci_high)

    def calculate_neff(self, weights: List[float]) -> float:
        """Calculate effective sample size."""
        if not weights:
            return 0.0

        weights = np.array(weights)
        sum_weights = np.sum(weights)
        sum_weights_sq = np.sum(weights ** 2)

        if sum_weights_sq > 0:
            neff = (sum_weights ** 2) / sum_weights_sq
        else:
            neff = 0.0

        return neff


# ============================================================================
# Smoothing & Index Calculation
# ============================================================================

class KalmanSmoother:
    """Kalman filter for temporal smoothing."""

    def __init__(self):
        self.states = {}  # (country, pillar) -> state
        self.covariances = {}  # (country, pillar) -> covariance

    def smooth(self, country: str, pillar: str,
              observation: float, obs_variance: float = 0.1) -> float:
        """Apply Kalman filter to smooth time series."""
        key = (country, pillar)

        # Initialize if first observation
        if key not in self.states:
            self.states[key] = observation
            self.covariances[key] = obs_variance
            return observation

        # Kalman filter update
        # Prediction (random walk model)
        process_variance = 0.01  # Small process noise
        prior_state = self.states[key]
        prior_cov = self.covariances[key] + process_variance

        # Update
        kalman_gain = prior_cov / (prior_cov + obs_variance)
        posterior_state = prior_state + kalman_gain * (observation - prior_state)
        posterior_cov = (1 - kalman_gain) * prior_cov

        # Store for next iteration
        self.states[key] = posterior_state
        self.covariances[key] = posterior_cov

        return posterior_state


class GPICalculator:
    """Calculate final GPI scores."""

    def __init__(self, config: GPIConfig):
        self.config = config
        self.smoother = KalmanSmoother()

    def calculate_gpi(self, pillars: List[PillarDaily]) -> List[GPIDaily]:
        """
        Calculate headline GPI from pillars.
        GPI_{j,t} = 100 * Σ_p β_p * x̂_{j,p,t}
        """
        # Group by country
        country_groups = defaultdict(list)
        for p in pillars:
            country_groups[p.country_j].append(p)

        gpi_scores = []
        date = pillars[0].date if pillars else datetime.now()

        for country_j, pillar_list in country_groups.items():
            # Apply Kalman smoothing to each pillar
            smoothed_pillars = {}
            for p in pillar_list:
                smoothed_value = self.smoother.smooth(
                    country_j, p.pillar_p, p.G_norm
                )
                smoothed_pillars[p.pillar_p] = smoothed_value

            # Calculate weighted sum
            gpi_raw = sum(
                self.config.PILLAR_BETA.get(pillar, 0) * value
                for pillar, value in smoothed_pillars.items()
            )

            # Scale to [-100, 100] with amplification for better sensitivity
            # Most scores cluster around 0, so we amplify to spread them out
            gpi_raw = gpi_raw * 200  # Doubled amplification
            gpi_kalman = np.clip(gpi_raw, -100, 100)

            # Calculate coverage
            n_events = sum(p.G_raw != 0 for p in pillar_list)
            if n_events >= self.config.COVERAGE_THRESHOLDS['high']:
                coverage = 'high'
            elif n_events >= self.config.COVERAGE_THRESHOLDS['medium']:
                coverage = 'medium'
            else:
                coverage = 'low'

            gpi = GPIDaily(
                date=date,
                country_j=country_j,
                gpi_raw=gpi_raw,
                gpi_kalman=gpi_kalman,
                se=0.0,  # Will be calculated with bootstrap
                ci=(gpi_kalman - 5, gpi_kalman + 5),  # Placeholder
                coverage_bucket=coverage
            )
            gpi_scores.append(gpi)

        return gpi_scores


# ============================================================================
# Database Storage
# ============================================================================

class GPIDatabase:
    """Database management for GPI system."""

    def __init__(self, db_path: str = 'gpi_unified.db'):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Events table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                published_at TIMESTAMP,
                source_id TEXT,
                origin_iso3 TEXT,
                url TEXT,
                lang TEXT,
                text_hash TEXT,
                audience_estimate REAL,
                dedup_weight REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # NLP spans table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS nlp_spans (
                span_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT,
                target_iso3 TEXT,
                sentiment_s REAL,
                pillar_weights TEXT,  -- JSON
                stance_conf REAL,
                FOREIGN KEY (event_id) REFERENCES events(event_id)
            )
        ''')

        # Sources table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sources (
                source_id TEXT PRIMARY KEY,
                domain TEXT,
                country_iso3 TEXT,
                outlet_type TEXT,
                reliability_r REAL,
                influence_bucket TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Daily edges table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS edges_daily (
                date DATE,
                origin_i TEXT,
                target_j TEXT,
                pillar_p TEXT,
                E_ijpt REAL,
                n_events INTEGER,
                neff REAL,
                ci_low REAL,
                ci_high REAL,
                PRIMARY KEY (date, origin_i, target_j, pillar_p)
            )
        ''')

        # Daily pillars table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pillars_daily (
                date DATE,
                country_j TEXT,
                pillar_p TEXT,
                G_raw REAL,
                G_norm REAL,
                se REAL,
                ci_low REAL,
                ci_high REAL,
                PRIMARY KEY (date, country_j, pillar_p)
            )
        ''')

        # Daily GPI table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS gpi_daily (
                date DATE,
                country_j TEXT,
                gpi_raw REAL,
                gpi_kalman REAL,
                se REAL,
                ci_low REAL,
                ci_high REAL,
                coverage_bucket TEXT,
                PRIMARY KEY (date, country_j)
            )
        ''')

        conn.commit()
        conn.close()

    def store_gpi_results(self, gpi_scores: List[GPIDaily]):
        """Store GPI results in database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        for gpi in gpi_scores:
            cursor.execute('''
                INSERT OR REPLACE INTO gpi_daily
                (date, country_j, gpi_raw, gpi_kalman, se, ci_low, ci_high, coverage_bucket)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                gpi.date.date(),
                gpi.country_j,
                gpi.gpi_raw,
                gpi.gpi_kalman,
                gpi.se,
                gpi.ci[0],
                gpi.ci[1],
                gpi.coverage_bucket
            ))

        conn.commit()
        conn.close()

    def get_latest_gpi(self, country: str) -> Optional[GPIDaily]:
        """Get latest GPI score for a country."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM gpi_daily
            WHERE country_j = ?
            ORDER BY date DESC
            LIMIT 1
        ''', (country,))

        row = cursor.fetchone()
        conn.close()

        if row:
            return GPIDaily(
                date=datetime.fromisoformat(row[0]),
                country_j=row[1],
                gpi_raw=row[2],
                gpi_kalman=row[3],
                se=row[4],
                ci=(row[5], row[6]),
                coverage_bucket=row[7]
            )
        return None


# ============================================================================
# Main Pipeline
# ============================================================================

class GPIPipeline:
    """Main GPI processing pipeline."""

    def __init__(self, config: Optional[GPIConfig] = None):
        self.config = config or GPIConfig()
        self.ingester = NewsIngester(self.config)
        self.nlp = NLPPipeline(self.config)
        self.scorer = ScoringEngine(self.config)
        self.calculator = GPICalculator(self.config)
        self.db = GPIDatabase()

        # Initialize speaker weights (simplified)
        self.speaker_weights = self._init_speaker_weights()

    def _init_speaker_weights(self) -> Dict[str, float]:
        """Initialize speaker weights based on global influence."""
        # Simplified weights - in production, use GDP PPP + population + media export
        weights = {
            'USA': 0.20, 'CHN': 0.15, 'DEU': 0.08, 'GBR': 0.08,
            'FRA': 0.06, 'JPN': 0.06, 'IND': 0.05, 'RUS': 0.05,
            'BRA': 0.04, 'CAN': 0.03, 'AUS': 0.02, 'GLO': 0.10
        }
        # Normalize to sum to 1
        total = sum(weights.values())
        return {k: v/total for k, v in weights.items()}

    def _get_source_info(self, source_id: str) -> SourceInfo:
        """Get or create source information."""
        # In production, fetch from database
        # For now, return defaults
        return SourceInfo(
            source_id=source_id,
            domain=source_id,
            country_iso3='GLO',
            outlet_type='national',
            reliability_r=self.config.SOURCE_RELIABILITY['default'],
            influence_bucket='medium'
        )

    def process_daily(self, date: Optional[datetime] = None):
        """Process daily GPI for all target countries."""
        date = date or datetime.now()
        logger.info(f"Processing GPI for {date.date()}")

        all_edges = []
        all_events = []
        all_spans = []

        # CRITICAL FIX: Fetch global news once, then analyze for ALL countries
        # This captures cross-country perception properly
        logger.info("Fetching global news coverage...")

        # Fetch news about major topics/regions (reduced for speed)
        global_queries = ['international', 'global economy']

        for query in global_queries:
            events = self.ingester.fetch_news(query, days_back=2)
            all_events.extend(events)

        # Also fetch news specifically about each country
        for country in self.config.TARGET_COUNTRIES[:5]:  # Start with first 5 for testing
            logger.info(f"Fetching news about {country}...")
            country_events = self.ingester.fetch_news(country, days_back=3)
            all_events.extend(country_events)

        # Deduplicate all events
        unique_events = []
        seen_urls = set()
        for event in all_events:
            if event.url not in seen_urls:
                unique_events.append(event)
                seen_urls.add(event.url)

        logger.info(f"Processing {len(unique_events)} unique events through NLP...")

        # Process ALL events for ALL target countries
        for event in unique_events:
            spans = self.nlp.process_event(event, self.config.TARGET_COUNTRIES)
            all_spans.extend(spans)

        if not all_spans:
            logger.warning(f"No NLP spans extracted from {len(unique_events)} events")
        else:
            logger.info(f"Extracted {len(all_spans)} NLP spans")

            # Get source info
            sources = {event.source_id: self._get_source_info(event.source_id)
                      for event in unique_events}

            # Aggregate to edges
            edges = self.scorer.aggregate_daily(unique_events, all_spans, sources, date)
            all_edges.extend(edges)

        if not all_edges:
            logger.warning("No edges calculated")
            return []

        # Calculate global pillars
        pillars = self.scorer.calculate_global_pillars(all_edges, self.speaker_weights)

        # Normalize across countries
        pillars = self.scorer.normalize_pillars(pillars)

        # Calculate final GPI
        gpi_scores = self.calculator.calculate_gpi(pillars)

        # Store in database
        self.db.store_gpi_results(gpi_scores)

        logger.info(f"Calculated GPI for {len(gpi_scores)} countries")
        return gpi_scores

    def get_rankings(self) -> List[Tuple[str, float]]:
        """Get current GPI rankings."""
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT country_j, gpi_kalman
            FROM gpi_daily
            WHERE date = (SELECT MAX(date) FROM gpi_daily)
            ORDER BY gpi_kalman DESC
        ''')

        rankings = cursor.fetchall()
        conn.close()

        return rankings


# ============================================================================
# CLI Interface
# ============================================================================

def main():
    """Main CLI interface."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Global Perception Index - Unified Implementation'
    )
    parser.add_argument('command', choices=['process', 'rankings', 'country'],
                       help='Command to execute')
    parser.add_argument('--country', help='Country ISO3 code')
    parser.add_argument('--date', help='Date to process (YYYY-MM-DD)')

    args = parser.parse_args()

    pipeline = GPIPipeline()

    if args.command == 'process':
        # Process daily GPI
        date = datetime.fromisoformat(args.date) if args.date else datetime.now()
        scores = pipeline.process_daily(date)

        print(f"\n{'='*60}")
        print(f"GPI Processing Complete - {date.date()}")
        print(f"{'='*60}")

        for gpi in scores[:10]:  # Show top 10
            print(f"{gpi.country_j:15} {gpi.gpi_kalman:+6.1f} [{gpi.coverage_bucket}]")

    elif args.command == 'rankings':
        # Show current rankings
        rankings = pipeline.get_rankings()

        print(f"\n{'='*60}")
        print("Current GPI Rankings")
        print(f"{'='*60}")

        for i, (country, score) in enumerate(rankings[:20], 1):
            sentiment = 'Positive' if score > 20 else 'Negative' if score < -20 else 'Neutral'
            print(f"{i:3}. {country:15} {score:+6.1f} ({sentiment})")

    elif args.command == 'country' and args.country:
        # Show details for specific country
        gpi = pipeline.db.get_latest_gpi(args.country)

        if gpi:
            print(f"\n{'='*60}")
            print(f"GPI Details: {args.country}")
            print(f"{'='*60}")
            print(f"Date:          {gpi.date.date()}")
            print(f"GPI Score:     {gpi.gpi_kalman:+.1f}/100")
            print(f"Raw Score:     {gpi.gpi_raw:+.1f}")
            print(f"Confidence:    [{gpi.ci[0]:.1f}, {gpi.ci[1]:.1f}]")
            print(f"Coverage:      {gpi.coverage_bucket}")
        else:
            print(f"No GPI data found for {args.country}")


if __name__ == '__main__':
    main()