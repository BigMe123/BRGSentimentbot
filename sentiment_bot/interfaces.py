#!/usr/bin/env python3
"""
Standardized API Interfaces
===========================

Defines consistent interfaces for all BSG components to fix interdependency issues.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, AsyncIterator, Union
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class AnalysisMode(Enum):
    """Standardized analysis modes."""
    SMART = "smart"
    ECONOMIC = "economic"
    MARKET = "market"
    AI_QUESTION = "ai_question"
    COMPREHENSIVE = "comprehensive"


@dataclass
class Article:
    """Standardized article representation."""
    title: str
    text: str
    url: str
    published_at: Optional[datetime] = None
    source: str = "unknown"
    country: Optional[str] = None
    region: Optional[str] = None
    topics: List[str] = None
    sentiment_score: Optional[float] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.topics is None:
            self.topics = []
        if self.metadata is None:
            self.metadata = {}


@dataclass
class SentimentResult:
    """Standardized sentiment analysis result."""
    score: float  # -1 to +1 (compound score)
    label: str   # "positive", "negative", "neutral"
    confidence: float = 0.0  # 0 to 1
    components: Dict[str, float] = None  # breakdown by analyzer

    def __post_init__(self):
        if self.components is None:
            self.components = {}

    # Legacy compatibility
    @property
    def compound(self) -> float:
        return self.score


@dataclass
class Source:
    """Standardized source representation."""
    name: str
    url: str
    domain: str
    country: str
    region: str
    topics: List[str]
    priority: float = 0.5
    language: str = "en"
    rss_endpoints: List[str] = None

    def __post_init__(self):
        if self.rss_endpoints is None:
            self.rss_endpoints = []


@dataclass
class PredictionResult:
    """Standardized prediction result."""
    value: float
    confidence: float
    confidence_interval: tuple
    horizon: str  # "1_month", "1_quarter", etc.
    drivers: List[str] = None
    methodology: str = "unknown"
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.drivers is None:
            self.drivers = []
        if self.metadata is None:
            self.metadata = {}


class SentimentAnalyzer(ABC):
    """Interface for sentiment analyzers."""

    @abstractmethod
    def analyze(self, text: str) -> SentimentResult:
        """Analyze sentiment of text."""
        pass

    # Legacy compatibility methods
    def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """Legacy method for backward compatibility."""
        result = self.analyze(text)
        return {
            'compound': result.score,
            'label': result.label,
            'confidence': result.confidence
        }

    def score_article(self, text: str, title: str = None) -> SentimentResult:
        """Alternative method name for compatibility."""
        return self.analyze(text)


class SourceSelector(ABC):
    """Interface for source selectors."""

    @abstractmethod
    def select_sources(
        self,
        mode: AnalysisMode,
        region: Optional[str] = None,
        countries: Optional[List[str]] = None,
        topics: Optional[List[str]] = None,
        max_sources: int = 50
    ) -> List[Source]:
        """Select sources based on criteria."""
        pass


class ArticleScraper(ABC):
    """Interface for article scrapers."""

    @abstractmethod
    async def fetch_articles(
        self,
        sources: List[Source],
        max_per_source: int = 10
    ) -> AsyncIterator[Article]:
        """Fetch articles from sources."""
        pass


class EconomicPredictor(ABC):
    """Interface for economic predictors."""

    @abstractmethod
    def predict(
        self,
        articles: List[Article],
        target: str = "gdp",
        horizon: str = "1_quarter"
    ) -> PredictionResult:
        """Generate economic prediction."""
        pass

    # Legacy compatibility methods
    def predict_with_transparency(
        self,
        sentiment_score: float,
        topic_factors: Dict[str, float],
        context_text: str = ""
    ) -> Dict[str, Any]:
        """Legacy method for backward compatibility."""
        # Create mock article
        article = Article(
            title="Mock",
            text=context_text,
            url="",
            sentiment_score=sentiment_score
        )

        result = self.predict([article])
        return {
            'gdp_forecast': result.value,
            'confidence': result.confidence,
            'drivers': result.drivers,
            'methodology': result.methodology
        }


class MarketProcessor(ABC):
    """Interface for market processors."""

    @abstractmethod
    async def process_tick(self, data: Dict[str, Any]) -> bool:
        """Process market tick."""
        pass

    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """Get processing statistics."""
        pass


class ConfidenceAnalyzer(ABC):
    """Interface for consumer confidence analyzers."""

    @abstractmethod
    def analyze_confidence(
        self,
        sentiment_data: Dict[str, float],
        economic_data: Optional[Dict[str, float]] = None,
        behavioral_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Analyze consumer confidence."""
        pass

    # Legacy compatibility
    def analyze(self, *args, **kwargs):
        """Legacy method wrapper."""
        return self.analyze_confidence(*args, **kwargs)


# Adapter classes for existing components
class SentimentEnsembleAdapter(SentimentAnalyzer):
    """Adapter for existing SentimentEnsemble."""

    def __init__(self, ensemble):
        self.ensemble = ensemble

    def analyze(self, text: str) -> SentimentResult:
        """Convert ensemble result to standard format."""
        try:
            # Try the standard method first
            if hasattr(self.ensemble, 'score_article'):
                result = self.ensemble.score_article(text)
                if hasattr(result, 'score') and hasattr(result, 'label'):
                    return SentimentResult(
                        score=result.score,
                        label=result.label,
                        confidence=getattr(result, 'confidence', 0.5)
                    )

            # Fallback for other methods
            if hasattr(self.ensemble, 'analyze_sentiment'):
                result = self.ensemble.analyze_sentiment(text)
                return SentimentResult(
                    score=result.get('compound', 0.0),
                    label=result.get('label', 'neutral'),
                    confidence=result.get('confidence', 0.5)
                )

            # Last resort - return neutral
            return SentimentResult(score=0.0, label='neutral', confidence=0.0)

        except Exception:
            # Safe fallback
            return SentimentResult(score=0.0, label='neutral', confidence=0.0)


class UnifiedSourceSelectorAdapter(SourceSelector):
    """Adapter for existing UnifiedSourceSelector."""

    def __init__(self, selector):
        self.selector = selector

    def select_sources(
        self,
        mode: AnalysisMode,
        region: Optional[str] = None,
        countries: Optional[List[str]] = None,
        topics: Optional[List[str]] = None,
        max_sources: int = 50
    ) -> List[Source]:
        """Convert selector result to standard format."""
        try:
            # Map mode to string
            mode_str = mode.value if isinstance(mode, AnalysisMode) else str(mode).upper()

            # Try different method signatures
            if hasattr(self.selector, 'select_for_mode'):
                sources = self.selector.select_for_mode(
                    mode=mode_str,
                    region=region,
                    countries=countries,
                    max_sources=max_sources
                )
            elif hasattr(self.selector, 'select_sources'):
                sources = self.selector.select_sources(
                    region=region,
                    topics=topics,
                    max_sources=max_sources
                )
            else:
                return []

            # Convert to standard format
            standardized = []
            for source in sources:
                if isinstance(source, dict):
                    standardized.append(Source(
                        name=source.get('name', source.get('domain', 'Unknown')),
                        url=source.get('url', source.get('rss_url', '')),
                        domain=source.get('domain', ''),
                        country=source.get('country', 'unknown'),
                        region=source.get('region', 'global'),
                        topics=source.get('topics', []),
                        priority=source.get('priority', 0.5),
                        rss_endpoints=source.get('rss_endpoints', [])
                    ))
                else:
                    # Assume it's already a Source object
                    standardized.append(source)

            return standardized

        except Exception:
            return []


class EnhancedScraperAdapter(ArticleScraper):
    """Adapter for existing EnhancedStableScraper."""

    def __init__(self, scraper):
        self.scraper = scraper

    async def fetch_articles(
        self,
        sources: List[Source],
        max_per_source: int = 10
    ) -> AsyncIterator[Article]:
        """Convert scraper results to standard format."""
        try:
            # Convert sources to dict format
            source_dicts = []
            for source in sources:
                source_dicts.append({
                    'name': source.name,
                    'url': source.url,
                    'domain': source.domain,
                    'country': source.country,
                    'rss_endpoints': source.rss_endpoints
                })

            # Try different scraper methods
            if hasattr(self.scraper, 'fetch_batch'):
                async for article in self.scraper.fetch_batch(source_dicts, max_per_source):
                    yield self._convert_article(article)
            elif hasattr(self.scraper, 'fetch'):
                async for article in self.scraper.fetch(source_dicts):
                    yield self._convert_article(article)

        except Exception as e:
            # Log error but don't crash
            import logging
            logging.warning(f"Scraper error: {e}")

    def _convert_article(self, article_data) -> Article:
        """Convert article dict to Article object."""
        if isinstance(article_data, dict):
            return Article(
                title=article_data.get('title', ''),
                text=article_data.get('text', article_data.get('content', '')),
                url=article_data.get('url', article_data.get('link', '')),
                published_at=article_data.get('published_at'),
                source=article_data.get('source', article_data.get('domain', 'unknown')),
                country=article_data.get('country'),
                topics=article_data.get('topics', []),
                metadata=article_data
            )
        else:
            # Assume it's already an Article
            return article_data


class ProductionEconomicPredictorAdapter(EconomicPredictor):
    """Adapter for existing ProductionEconomicPredictor."""

    def __init__(self, predictor):
        self.predictor = predictor

    def predict(
        self,
        articles: List[Article],
        target: str = "gdp",
        horizon: str = "1_quarter"
    ) -> PredictionResult:
        """Convert predictor result to standard format."""
        try:
            if not articles:
                return PredictionResult(
                    value=0.0,
                    confidence=0.0,
                    confidence_interval=(0.0, 0.0),
                    horizon=horizon
                )

            # Extract sentiment from first article
            sentiment_score = articles[0].sentiment_score or 0.0

            # Try different predictor methods
            if hasattr(self.predictor, 'predict_with_transparency'):
                result = self.predictor.predict_with_transparency(
                    sentiment_score=sentiment_score,
                    topic_factors={'economy': abs(sentiment_score)},
                    context_text=articles[0].text[:500]
                )

                return PredictionResult(
                    value=result.get('gdp_forecast', 0.0),
                    confidence=result.get('confidence', 0.5),
                    confidence_interval=(
                        result.get('gdp_forecast', 0.0) - 1.0,
                        result.get('gdp_forecast', 0.0) + 1.0
                    ),
                    horizon=horizon,
                    drivers=result.get('drivers', []),
                    methodology=result.get('methodology', 'production_predictor')
                )

            # Fallback
            return PredictionResult(
                value=sentiment_score * 2.0,  # Simple mapping
                confidence=0.5,
                confidence_interval=(-1.0, 5.0),
                horizon=horizon
            )

        except Exception:
            return PredictionResult(
                value=0.0,
                confidence=0.0,
                confidence_interval=(0.0, 0.0),
                horizon=horizon
            )


# Factory functions for creating adapted components
def create_sentiment_analyzer(component=None) -> SentimentAnalyzer:
    """Create standardized sentiment analyzer."""
    if component is None:
        from sentiment_bot.analyzers.sentiment_ensemble import SentimentEnsemble
        component = SentimentEnsemble()
    return SentimentEnsembleAdapter(component)


def create_source_selector(component=None) -> SourceSelector:
    """Create standardized source selector."""
    if component is None:
        from sentiment_bot.unified_source_selector import UnifiedSourceSelector
        component = UnifiedSourceSelector()
    return UnifiedSourceSelectorAdapter(component)


def create_article_scraper(component=None) -> ArticleScraper:
    """Create standardized article scraper."""
    if component is None:
        from sentiment_bot.enhanced_stable_scraper import EnhancedStableScraper
        component = EnhancedStableScraper()
    return EnhancedScraperAdapter(component)


def create_economic_predictor(component=None) -> EconomicPredictor:
    """Create standardized economic predictor."""
    if component is None:
        from sentiment_bot.production_economic_predictor import ProductionEconomicPredictor
        component = ProductionEconomicPredictor()
    return ProductionEconomicPredictorAdapter(component)