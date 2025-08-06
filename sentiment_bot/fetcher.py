from __future__ import annotations
import asyncio
import logging
import hashlib
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional, Iterable, Dict, Any, Set, Tuple
from urllib.parse import urljoin, urlparse, urlunparse
from collections import defaultdict

import aiohttp
import feedparser
from bs4 import BeautifulSoup

from .config import settings

# Configure logging for risk analysis
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - RiskSentiment - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SourceReliability(Enum):
    """Source reliability scoring for confidence calculation."""
    TIER_1 = 1.0  # Major news outlets, official sources
    TIER_2 = 0.8  # Regional news, industry publications  
    TIER_3 = 0.6  # Blogs, smaller publications
    UNKNOWN = 0.5  # Unverified sources


@dataclass
class SentimentMetadata:
    """Metadata for sentiment analysis confidence scoring."""
    source_tier: SourceReliability = SourceReliability.UNKNOWN
    word_count: int = 0
    has_verified_author: bool = False
    published_date_verified: bool = False
    extraction_completeness: float = 0.0  # 0-1 score of how much content was extracted
    domain_authority: Optional[float] = None
    content_hash: Optional[str] = None


@dataclass
class ArticleData:
    """Article data optimized for risk sentiment analysis."""
    url: str
    title: str
    text: str
    published: Optional[str] = None
    domain: str = ""
    metadata: SentimentMetadata = field(default_factory=SentimentMetadata)
    extraction_method: str = "unknown"
    fetch_success: bool = True
    

@dataclass 
class CollectionStats:
    """Track collection statistics for confidence scoring."""
    total_feeds_attempted: int = 0
    total_feeds_successful: int = 0
    total_articles_attempted: int = 0
    total_articles_collected: int = 0
    total_words_collected: int = 0
    unique_domains: Set[str] = field(default_factory=set)
    collection_duration_ms: int = 0
    
    @property
    def collection_rate(self) -> float:
        """Calculate successful collection rate."""
        if self.total_articles_attempted == 0:
            return 0.0
        return self.total_articles_collected / self.total_articles_attempted
    
    @property
    def confidence_score(self) -> float:
        """Calculate overall confidence based on volume and diversity."""
        volume_score = min(self.total_articles_collected / 100, 1.0)  # Max at 100 articles
        diversity_score = min(len(self.unique_domains) / 20, 1.0)  # Max at 20 domains
        success_rate = self.collection_rate
        word_volume_score = min(self.total_words_collected / 100000, 1.0)  # Max at 100k words
        
        # Weighted confidence calculation
        confidence = (
            volume_score * 0.3 +
            diversity_score * 0.2 +
            success_rate * 0.2 +
            word_volume_score * 0.3
        )
        return confidence


class AggressiveFetcher:
    """Aggressive parallel fetching to maximize article collection."""
    
    # Known high-value sources for risk analysis
    TIER_1_DOMAINS = {
        'reuters.com', 'bloomberg.com', 'ft.com', 'wsj.com', 'economist.com',
        'nytimes.com', 'washingtonpost.com', 'bbc.com', 'cnn.com', 'apnews.com',
        'guardian.com', 'forbes.com', 'businessinsider.com', 'cnbc.com'
    }
    
    TIER_2_DOMAINS = {
        'techcrunch.com', 'venturebeat.com', 'zdnet.com', 'arstechnica.com',
        'theregister.com', 'axios.com', 'politico.com', 'thehill.com'
    }
    
    def __init__(self, max_concurrent: int = 50, timeout: int = 15):
        """Initialize with aggressive settings for maximum collection."""
        self.max_concurrent = max_concurrent  # High concurrency for speed
        self.timeout = timeout
        self.stats = CollectionStats()
        self.session: Optional[aiohttp.ClientSession] = None
        
    def classify_source(self, url: str) -> SourceReliability:
        """Classify source reliability for confidence weighting."""
        domain = urlparse(url).netloc.lower().replace('www.', '')
        
        if any(tier1 in domain for tier1 in self.TIER_1_DOMAINS):
            return SourceReliability.TIER_1
        elif any(tier2 in domain for tier2 in self.TIER_2_DOMAINS):
            return SourceReliability.TIER_2
        elif domain.endswith('.gov') or domain.endswith('.edu'):
            return SourceReliability.TIER_1
        else:
            return SourceReliability.TIER_3
    
    async def __aenter__(self):
        """Async context manager entry."""
        connector = aiohttp.TCPConnector(
            limit=self.max_concurrent,
            limit_per_host=10,
            ttl_dns_cache=300
        )
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={'User-Agent': 'RiskSentimentAnalyzer/1.0'}
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    def extract_all_text(self, soup: BeautifulSoup) -> Tuple[str, float]:
        """Extract maximum text content for sentiment analysis."""
        # Remove only script and style - keep everything else for maximum content
        for element in soup(['script', 'style', 'noscript']):
            element.decompose()
        
        # Get all text-bearing elements
        text_elements = soup.find_all(['p', 'div', 'article', 'section', 'main', 
                                       'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                                       'blockquote', 'li', 'td', 'th'])
        
        text_parts = []
        total_possible = len(text_elements)
        extracted = 0
        
        for elem in text_elements:
            text = elem.get_text(separator=' ', strip=True)
            if len(text) > 20:  # Minimum viable text length
                text_parts.append(text)
                extracted += 1
        
        full_text = '\n'.join(text_parts)
        completeness = extracted / total_possible if total_possible > 0 else 0.0
        
        # Clean but preserve maximum content
        full_text = re.sub(r'\s+', ' ', full_text)
        full_text = re.sub(r'\n{3,}', '\n\n', full_text)
        
        return full_text.strip(), completeness
    
    async def fetch_article(self, url: str) -> ArticleData:
        """Fetch single article with multiple fallback methods."""
        start_time = time.time()
        domain = urlparse(url).netloc.lower().replace('www.', '')
        
        # Try newspaper3k first for quality extraction
        try:
            from newspaper import Article  # type: ignore
            
            def parse_newspaper() -> ArticleData:
                art = Article(url)
                art.download()
                art.parse()
                
                metadata = SentimentMetadata(
                    source_tier=self.classify_source(url),
                    word_count=len(art.text.split()) if art.text else 0,
                    has_verified_author=bool(art.authors),
                    published_date_verified=bool(art.publish_date),
                    extraction_completeness=0.9 if art.text else 0.1
                )
                
                return ArticleData(
                    url=url,
                    title=art.title or "",
                    text=art.text or "",
                    published=art.publish_date.isoformat() if art.publish_date else None,
                    domain=domain,
                    metadata=metadata,
                    extraction_method="newspaper3k"
                )
            
            article = await asyncio.to_thread(parse_newspaper)
            if article.text:  # Only return if we got content
                return article
        except Exception as e:
            logger.debug(f"Newspaper extraction failed for {url}: {e}")
        
        # Fallback to direct HTTP fetch with BeautifulSoup
        try:
            async with self.session.get(url, ssl=False) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Extract maximum content
                    text, completeness = self.extract_all_text(soup)
                    
                    # Get title
                    title = ""
                    if soup.title:
                        title = soup.title.get_text(strip=True)
                    elif soup.find('h1'):
                        title = soup.find('h1').get_text(strip=True)
                    
                    # Get publish date from meta tags
                    published = None
                    date_meta = soup.find('meta', {'property': 'article:published_time'})
                    if date_meta:
                        published = date_meta.get('content')
                    
                    metadata = SentimentMetadata(
                        source_tier=self.classify_source(url),
                        word_count=len(text.split()),
                        extraction_completeness=completeness,
                        published_date_verified=bool(published)
                    )
                    
                    return ArticleData(
                        url=url,
                        title=title,
                        text=text,
                        published=published,
                        domain=domain,
                        metadata=metadata,
                        extraction_method="beautifulsoup"
                    )
        except Exception as e:
            logger.warning(f"Failed to fetch {url}: {e}")
        
        # Return empty article to track attempt
        return ArticleData(
            url=url,
            title="",
            text="",
            domain=domain,
            fetch_success=False,
            extraction_method="failed"
        )
    
    async def fetch_feed_articles(self, feed_url: str) -> List[ArticleData]:
        """Fetch all articles from a feed."""
        articles = []
        
        try:
            # Parse feed
            feed = await asyncio.to_thread(feedparser.parse, feed_url)
            self.stats.total_feeds_attempted += 1
            
            if feed.entries:
                self.stats.total_feeds_successful += 1
                
                # Extract all article URLs
                article_urls = []
                for entry in feed.entries:
                    if link := entry.get('link'):
                        article_urls.append(link)
                
                # Fetch all articles in parallel
                self.stats.total_articles_attempted += len(article_urls)
                
                tasks = [self.fetch_article(url) for url in article_urls]
                articles = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Filter out exceptions and empty articles
                valid_articles = []
                for art in articles:
                    if isinstance(art, ArticleData) and art.text:
                        valid_articles.append(art)
                        self.stats.total_articles_collected += 1
                        self.stats.total_words_collected += art.metadata.word_count
                        self.stats.unique_domains.add(art.domain)
                
                return valid_articles
                
        except Exception as e:
            logger.error(f"Failed to process feed {feed_url}: {e}")
            self.stats.total_feeds_attempted += 1
        
        return articles


async def fetch_and_parse_url(url: str) -> ArticleData:
    """Legacy interface - single URL fetch."""
    async with AggressiveFetcher(max_concurrent=1) as fetcher:
        return await fetcher.fetch_article(url)


async def fetch_and_parse(url: str) -> ArticleData:
    """Public wrapper for single URL fetch."""
    return await fetch_and_parse_url(url)


async def gather_rss(feeds: Iterable[str] | None = None) -> Tuple[List[ArticleData], CollectionStats]:
    """
    Aggressively gather articles from all feeds in parallel.
    Returns articles and collection statistics for confidence scoring.
    """
    start_time = time.time()
    feed_urls = list(feeds or settings.RSS_FEEDS)
    
    # Use aggressive fetcher with high concurrency
    async with AggressiveFetcher(max_concurrent=50, timeout=15) as fetcher:
        # Fetch all feeds in parallel
        tasks = [fetcher.fetch_feed_articles(feed_url) for feed_url in feed_urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Flatten results
        all_articles = []
        for result in results:
            if isinstance(result, list):
                all_articles.extend(result)
        
        # Deduplicate by URL while preserving order
        seen_urls = set()
        unique_articles = []
        for article in all_articles:
            if article.url not in seen_urls:
                seen_urls.add(article.url)
                unique_articles.append(article)
        
        fetcher.stats.collection_duration_ms = int((time.time() - start_time) * 1000)
        
        logger.info(f"Collection complete: {fetcher.stats.total_articles_collected}/{fetcher.stats.total_articles_attempted} articles "
                   f"from {len(fetcher.stats.unique_domains)} domains. "
                   f"Confidence score: {fetcher.stats.confidence_score:.2%}")
        
        return unique_articles, fetcher.stats


async def gather_all_sources(feeds: Iterable[str] | None = None) -> Tuple[List[ArticleData], CollectionStats]:
    """
    Main entry point for risk sentiment analysis data collection.
    Maximizes article collection for high confidence scoring.
    """
    articles, stats = await gather_rss(feeds)
    
    # Log confidence metrics
    logger.info(f"Risk Sentiment Data Collection Summary:")
    logger.info(f"  - Total articles: {stats.total_articles_collected}")
    logger.info(f"  - Total words: {stats.total_words_collected:,}")
    logger.info(f"  - Unique domains: {len(stats.unique_domains)}")
    logger.info(f"  - Collection rate: {stats.collection_rate:.1%}")
    logger.info(f"  - CONFIDENCE SCORE: {stats.confidence_score:.1%}")
    logger.info(f"  - Duration: {stats.collection_duration_ms}ms")
    
    return articles, stats
