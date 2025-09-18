#!/usr/bin/env python3
"""
Real-Time Analysis Pipeline
Complete pipeline for real-time news analysis with economic predictions
"""

import asyncio
import time
from typing import Dict, List, Optional, Tuple, Any, AsyncGenerator
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
import json
import logging
from pathlib import Path
import pandas as pd
from collections import deque, defaultdict
import numpy as np
from enum import Enum

# Import system components
from .rss_monitor import RSSMonitor, FeedHealth, FeedItem
from .economic_models import UnifiedEconomicModel, EconomicForecast
from ..analyzers.llm_analyzer import LLMAnalyzer
from ..relevance_filter import RelevanceFilter
from ..utils.entity_extractor import EntityExtractor

logger = logging.getLogger(__name__)


class AnalysisStage(Enum):
    """Analysis pipeline stages"""
    INGESTION = "ingestion"
    DEDUPLICATION = "deduplication"
    RELEVANCE = "relevance"
    SENTIMENT = "sentiment"
    ENTITY = "entity"
    ECONOMIC = "economic"
    OUTPUT = "output"


@dataclass
class ArticleAnalysis:
    """Complete analysis result for an article"""

    # Article metadata
    article_id: str
    title: str
    url: str
    published: datetime
    source: str

    # Content
    text: str

    # Timestamp
    ingested_at: datetime = field(default_factory=datetime.now)
    summary: Optional[str] = None

    # Analysis results
    sentiment: Dict[str, float] = field(default_factory=dict)
    sentiment_score: float = 0.0  # Convenience field
    entities: List[Dict] = field(default_factory=list)
    topics: List[str] = field(default_factory=list)
    relevance_score: float = 0.0

    # Economic impacts
    predictor_impacts: Dict[str, float] = field(default_factory=dict)
    market_signals: Dict[str, Any] = field(default_factory=dict)

    # Quality metrics
    confidence_score: float = 0.0
    processing_time_ms: float = 0.0


@dataclass
class PipelineMetrics:
    """Real-time pipeline performance metrics"""

    # Throughput
    articles_per_second: float = 0.0
    articles_processed: int = 0
    articles_dropped: int = 0

    # Latency
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0

    # Stage timings
    stage_timings: Dict[str, float] = field(default_factory=dict)

    # Quality
    relevance_rate: float = 0.0
    dedup_rate: float = 0.0
    error_rate: float = 0.0

    # System
    memory_usage_mb: float = 0.0
    cpu_usage_pct: float = 0.0


class RealtimeAnalysisPipeline:
    """
    Production real-time analysis pipeline with streaming processing,
    economic modeling, and performance monitoring
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}

        # Initialize components
        self.rss_monitor = RSSMonitor()
        self.economic_model = UnifiedEconomicModel()
        self.relevance_filter = RelevanceFilter()
        self.entity_extractor = EntityExtractor()

        # Initialize LLM analyzer if available
        try:
            self.llm_analyzer = LLMAnalyzer()
            self.has_llm = True
        except:
            self.llm_analyzer = None
            self.has_llm = False
            logger.warning("LLM analyzer not available")

        # Pipeline configuration
        self.batch_size = self.config.get("batch_size", 10)
        self.window_size = self.config.get("window_size", 100)
        self.dedup_window = self.config.get("dedup_window_hours", 24)

        # State management
        self.running = False
        self.processed_hashes = deque(maxlen=10000)
        self.article_buffer = deque(maxlen=self.window_size)
        self.metrics_buffer = deque(maxlen=1000)

        # Deduplication cache
        self.dedup_cache = {}

        # Performance tracking
        self.metrics = PipelineMetrics()
        self.stage_timers = defaultdict(list)

    async def process_stream(
        self,
        feed_urls: List[str],
        target_region: Optional[str] = None,
        target_topics: Optional[List[str]] = None,
        output_callback: Optional[callable] = None
    ) -> AsyncGenerator[ArticleAnalysis, None]:
        """
        Process continuous stream of articles from RSS feeds

        Args:
            feed_urls: List of RSS feed URLs
            target_region: Target region for relevance filtering
            target_topics: Target topics for relevance filtering
            output_callback: Optional callback for processed articles

        Yields:
            ArticleAnalysis objects as they're processed
        """
        self.running = True
        logger.info(f"Starting real-time pipeline with {len(feed_urls)} feeds")

        try:
            while self.running:
                start_cycle = time.time()

                # Stage 1: Ingestion
                articles = await self._ingest_articles(feed_urls)
                logger.info(f"Ingested {len(articles)} articles")

                # Stage 2: Deduplication
                unique_articles = self._deduplicate(articles)
                logger.info(f"After dedup: {len(unique_articles)} unique articles")

                # Stage 3: Relevance filtering
                relevant_articles = self._filter_relevance(
                    unique_articles,
                    target_region,
                    target_topics
                )
                logger.info(f"After relevance: {len(relevant_articles)} relevant articles")

                # Process in batches
                for i in range(0, len(relevant_articles), self.batch_size):
                    batch = relevant_articles[i:i + self.batch_size]

                    # Stage 4-7: Full analysis
                    analyzed = await self._analyze_batch(batch)

                    # Yield results
                    for article_analysis in analyzed:
                        # Update metrics
                        self._update_metrics(article_analysis)

                        # Callback if provided
                        if output_callback:
                            await output_callback(article_analysis)

                        yield article_analysis

                # Update cycle metrics
                cycle_time = time.time() - start_cycle
                self.metrics.articles_per_second = len(articles) / cycle_time if cycle_time > 0 else 0

                # Rate limiting
                await asyncio.sleep(self.config.get("poll_interval", 60))

        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            raise
        finally:
            self.running = False

    async def _ingest_articles(self, feed_urls: List[str]) -> List[FeedItem]:
        """Ingest articles from RSS feeds"""
        start_time = time.time()

        # Check all feeds in parallel
        health_results = await self.rss_monitor.check_all_feeds(feed_urls)

        # Collect articles from healthy feeds
        all_articles = []
        for url, (health, items) in health_results.items():
            if health.is_healthy():
                all_articles.extend(items)

        # Track timing
        self.stage_timers[AnalysisStage.INGESTION].append(
            (time.time() - start_time) * 1000
        )

        return all_articles

    def _deduplicate(self, articles: List[FeedItem]) -> List[FeedItem]:
        """Deduplicate articles based on content hash"""
        start_time = time.time()
        unique = []

        for article in articles:
            if article.content_hash not in self.processed_hashes:
                self.processed_hashes.append(article.content_hash)
                unique.append(article)

        # Track metrics
        self.metrics.dedup_rate = 1 - (len(unique) / len(articles)) if articles else 0
        self.stage_timers[AnalysisStage.DEDUPLICATION].append(
            (time.time() - start_time) * 1000
        )

        return unique

    def _filter_relevance(
        self,
        articles: List[FeedItem],
        target_region: Optional[str],
        target_topics: Optional[List[str]]
    ) -> List[FeedItem]:
        """Filter articles by relevance"""
        start_time = time.time()
        relevant = []

        for article in articles:
            # Convert FeedItem to dict for relevance filter
            article_dict = {
                "title": article.title,
                "description": article.description,
                "content": article.description,  # Use description as content
                "categories": article.categories
            }

            score = self.relevance_filter.verify_relevance(
                article=article_dict,
                target_region=target_region,
                target_topics=target_topics,
                strict=False
            )

            if score.should_keep:
                article.relevance_score = score.weight
                relevant.append(article)

        # Track metrics
        self.metrics.relevance_rate = len(relevant) / len(articles) if articles else 0
        self.stage_timers[AnalysisStage.RELEVANCE].append(
            (time.time() - start_time) * 1000
        )

        return relevant

    async def _analyze_batch(self, articles: List[FeedItem]) -> List[ArticleAnalysis]:
        """Perform full analysis on article batch"""
        analyzed = []

        for article in articles:
            try:
                analysis = await self._analyze_article(article)
                analyzed.append(analysis)
            except Exception as e:
                logger.error(f"Failed to analyze article: {e}")
                self.metrics.error_rate += 1

        return analyzed

    async def _analyze_article(self, article: FeedItem) -> ArticleAnalysis:
        """Analyze single article"""
        start_time = time.time()

        # Initialize analysis
        analysis = ArticleAnalysis(
            article_id=article.content_hash,
            title=article.title,
            url=article.link,
            published=article.published,
            source=article.source_url,
            text=article.description or ""
        )

        # Stage 4: Sentiment analysis
        sentiment_start = time.time()
        if self.has_llm:
            sentiment_result = await self._analyze_sentiment_llm(article)
        else:
            sentiment_result = self._analyze_sentiment_basic(article)
        analysis.sentiment = sentiment_result
        self.stage_timers[AnalysisStage.SENTIMENT].append(
            (time.time() - sentiment_start) * 1000
        )

        # Stage 5: Entity extraction
        entity_start = time.time()
        entities = self.entity_extractor.extract_entities(analysis.text)
        analysis.entities = [{"text": e["text"], "type": e["type"]} for e in entities]

        # Extract topics and tickers
        analysis.topics = self.entity_extractor.extract_themes(
            analysis.text,
            primary_topic=None
        )
        tickers = self.entity_extractor.extract_tickers(analysis.text)
        if tickers:
            analysis.entities.extend([{"text": t, "type": "TICKER"} for t in tickers])

        self.stage_timers[AnalysisStage.ENTITY].append(
            (time.time() - entity_start) * 1000
        )

        # Stage 6: Economic impact assessment
        econ_start = time.time()
        impacts = self._assess_economic_impact(analysis)
        analysis.predictor_impacts = impacts["predictor_impacts"]
        analysis.market_signals = impacts["market_signals"]
        self.stage_timers[AnalysisStage.ECONOMIC].append(
            (time.time() - econ_start) * 1000
        )

        # Calculate confidence
        analysis.confidence_score = self._calculate_confidence(analysis)

        # Total processing time
        analysis.processing_time_ms = (time.time() - start_time) * 1000

        return analysis

    async def _analyze_sentiment_llm(self, article: FeedItem) -> Dict[str, float]:
        """Analyze sentiment using LLM"""
        try:
            result = await self.llm_analyzer.analyze_single(
                title=article.title,
                text=article.description or "",
                url=article.link
            )

            # Map to standard format
            sentiment_map = {
                "POSITIVE": 1.0,
                "NEGATIVE": -1.0,
                "NEUTRAL": 0.0
            }

            label = result.get("sentiment", "NEUTRAL").upper()
            score = sentiment_map.get(label, 0.0)

            return {
                "score": score,
                "label": label.lower(),
                "confidence": result.get("confidence", 0.5),
                "subjectivity": result.get("subjectivity", 0.5)
            }

        except Exception as e:
            logger.warning(f"LLM sentiment failed, using basic: {e}")
            return self._analyze_sentiment_basic(article)

    def _analyze_sentiment_basic(self, article: FeedItem) -> Dict[str, float]:
        """Basic sentiment analysis"""
        text = f"{article.title} {article.description or ''}"

        # Simple keyword-based sentiment
        positive_words = ["growth", "increase", "improve", "gain", "rise", "strong"]
        negative_words = ["decline", "fall", "drop", "weak", "concern", "risk"]

        text_lower = text.lower()
        pos_count = sum(1 for word in positive_words if word in text_lower)
        neg_count = sum(1 for word in negative_words if word in text_lower)

        if pos_count > neg_count:
            score = min(1.0, pos_count * 0.2)
            label = "positive"
        elif neg_count > pos_count:
            score = max(-1.0, -neg_count * 0.2)
            label = "negative"
        else:
            score = 0.0
            label = "neutral"

        return {
            "score": score,
            "label": label,
            "confidence": 0.5,
            "subjectivity": 0.5
        }

    def _assess_economic_impact(self, analysis: ArticleAnalysis) -> Dict[str, Any]:
        """Assess economic impact of article"""

        impacts = {
            "predictor_impacts": {},
            "market_signals": {}
        }

        # Extract economic signals from text
        text_lower = analysis.text.lower()

        # GDP impact signals
        gdp_positive = ["growth", "expansion", "recovery", "boom"]
        gdp_negative = ["recession", "contraction", "slowdown", "decline"]

        gdp_signal = 0.0
        for word in gdp_positive:
            if word in text_lower:
                gdp_signal += 0.1
        for word in gdp_negative:
            if word in text_lower:
                gdp_signal -= 0.1

        impacts["predictor_impacts"]["gdp"] = np.clip(gdp_signal, -0.5, 0.5)

        # Inflation signals
        inflation_positive = ["inflation", "prices rise", "cost increase"]
        inflation_negative = ["deflation", "prices fall", "cost decrease"]

        inflation_signal = 0.0
        for phrase in inflation_positive:
            if phrase in text_lower:
                inflation_signal += 0.1
        for phrase in inflation_negative:
            if phrase in text_lower:
                inflation_signal -= 0.1

        impacts["predictor_impacts"]["inflation"] = np.clip(inflation_signal, -0.5, 0.5)

        # Employment signals
        employment_positive = ["hiring", "jobs added", "unemployment falls"]
        employment_negative = ["layoffs", "job cuts", "unemployment rises"]

        employment_signal = 0.0
        for phrase in employment_positive:
            if phrase in text_lower:
                employment_signal += 0.1
        for phrase in employment_negative:
            if phrase in text_lower:
                employment_signal -= 0.1

        impacts["predictor_impacts"]["employment"] = np.clip(employment_signal, -0.5, 0.5)

        # Market signals
        impacts["market_signals"] = {
            "volatility": self.entity_extractor.detect_volatility(analysis.text),
            "risk_level": self.entity_extractor.detect_risk_level(
                analysis.text,
                analysis.sentiment["score"]
            ),
            "urgency": "high" if any(
                word in text_lower
                for word in ["breaking", "urgent", "alert", "emergency"]
            ) else "normal"
        }

        return impacts

    def _calculate_confidence(self, analysis: ArticleAnalysis) -> float:
        """Calculate overall confidence score"""
        factors = []

        # Sentiment confidence
        factors.append(analysis.sentiment.get("confidence", 0.5))

        # Entity extraction quality
        entity_score = min(1.0, len(analysis.entities) * 0.1)
        factors.append(entity_score)

        # Text length (longer = more confident)
        text_score = min(1.0, len(analysis.text.split()) / 200)
        factors.append(text_score)

        # Source reliability (would look up in database)
        factors.append(0.7)  # Default

        return np.mean(factors)

    def _update_metrics(self, analysis: ArticleAnalysis):
        """Update pipeline metrics"""
        self.metrics.articles_processed += 1

        # Update latency tracking
        self.metrics_buffer.append(analysis.processing_time_ms)

        if len(self.metrics_buffer) >= 100:
            latencies = list(self.metrics_buffer)
            self.metrics.avg_latency_ms = np.mean(latencies)
            self.metrics.p95_latency_ms = np.percentile(latencies, 95)
            self.metrics.p99_latency_ms = np.percentile(latencies, 99)

        # Update stage timings
        for stage, timings in self.stage_timers.items():
            if timings:
                self.metrics.stage_timings[stage.value] = np.mean(timings[-100:])

    async def generate_economic_forecast(
        self,
        country: str = "US",
        horizon: str = "nowcast"
    ) -> EconomicForecast:
        """
        Generate economic forecast based on recent articles

        Args:
            country: Country to forecast
            horizon: Forecast horizon

        Returns:
            EconomicForecast object
        """
        # Aggregate recent sentiment
        recent_articles = list(self.article_buffer)[-100:]

        if not recent_articles:
            logger.warning("No recent articles for forecast")
            sentiment_data = {"overall": 0.5}
        else:
            sentiments = [a.sentiment.get("score", 0) for a in recent_articles]
            sentiment_data = {
                "overall": np.mean(sentiments),
                "volatility": np.std(sentiments),
                "trend": sentiments[-1] - sentiments[0] if len(sentiments) > 1 else 0
            }

            # Topic-specific sentiments
            for topic in ["economy", "trade", "employment", "inflation"]:
                topic_articles = [
                    a for a in recent_articles
                    if topic in " ".join(a.topics).lower()
                ]
                if topic_articles:
                    topic_sentiments = [a.sentiment.get("score", 0) for a in topic_articles]
                    sentiment_data[topic] = np.mean(topic_sentiments)

        # Generate forecast
        forecast = self.economic_model.forecast_gdp(
            country=country,
            sentiment_data=sentiment_data,
            horizon=horizon
        )

        return forecast

    def get_pipeline_metrics(self) -> Dict[str, Any]:
        """Get current pipeline metrics"""
        return {
            "throughput": {
                "articles_per_second": self.metrics.articles_per_second,
                "total_processed": self.metrics.articles_processed,
                "total_dropped": self.metrics.articles_dropped
            },
            "latency": {
                "avg_ms": self.metrics.avg_latency_ms,
                "p95_ms": self.metrics.p95_latency_ms,
                "p99_ms": self.metrics.p99_latency_ms
            },
            "quality": {
                "relevance_rate": self.metrics.relevance_rate,
                "dedup_rate": self.metrics.dedup_rate,
                "error_rate": self.metrics.error_rate / max(1, self.metrics.articles_processed)
            },
            "stages": self.metrics.stage_timings,
            "timestamp": datetime.now().isoformat()
        }

    async def _process_article(self, article: Dict[str, Any]) -> Optional[ArticleAnalysis]:
        """
        Process a single article through the pipeline

        Args:
            article: Raw article data

        Returns:
            Processed ArticleAnalysis or None if filtered
        """
        import hashlib

        # Create article ID
        article_id = hashlib.md5(
            f"{article.get('title', '')}{article.get('url', '')}".encode()
        ).hexdigest()[:8]

        # Check deduplication
        text_hash = hashlib.md5(
            article.get('content', article.get('title', '')).encode()
        ).hexdigest()

        if text_hash in self.dedup_cache:
            self.metrics.articles_dropped += 1
            return None

        self.dedup_cache[text_hash] = datetime.now()

        # Create analysis object
        analysis = ArticleAnalysis(
            article_id=article_id,
            title=article.get('title', 'Untitled'),
            url=article.get('url', ''),
            published=datetime.fromisoformat(article.get('published', datetime.now().isoformat())),
            source=article.get('source', 'unknown'),
            text=article.get('content', article.get('title', '')),
            sentiment_score=0.0,
            entities=[],
            topics=[]
        )

        # Simple sentiment analysis (mock)
        if 'growth' in analysis.text.lower() or 'positive' in analysis.text.lower():
            analysis.sentiment_score = 0.5
        elif 'decline' in analysis.text.lower() or 'negative' in analysis.text.lower():
            analysis.sentiment_score = -0.5
        else:
            analysis.sentiment_score = 0.0

        # Extract entities (mock)
        analysis.entities = [
            {"text": "United States", "type": "LOCATION"},
            {"text": "GDP", "type": "ECONOMIC_INDICATOR"}
        ]

        # Assign topics (mock)
        analysis.topics = ["economy", "growth", "gdp"]

        self.metrics.articles_processed += 1

        return analysis

    def stop(self):
        """Stop the pipeline"""
        self.running = False
        logger.info("Pipeline stopped")


# Export main classes
__all__ = ["RealtimeAnalysisPipeline", "ArticleAnalysis", "PipelineMetrics", "AnalysisStage"]