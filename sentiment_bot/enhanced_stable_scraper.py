#!/usr/bin/env python3
"""
Enhanced Stable Scraper with Comprehensive Error Handling
=========================================================

Production-ready scraper with advanced error handling, circuit breakers,
retry logic, and comprehensive monitoring for BSG sentiment analysis.
"""

import asyncio
import aiohttp
import feedparser
import time
import logging
import json
from typing import List, Dict, Optional, Tuple, Callable, Set
from datetime import datetime, timedelta
from urllib.parse import urlparse, urljoin
from dataclasses import dataclass, field
from enum import Enum
import random
import ssl
from collections import defaultdict, deque
import hashlib

logger = logging.getLogger(__name__)

class ErrorType(Enum):
    """Classification of scraping errors."""
    NETWORK_ERROR = "network"
    HTTP_ERROR = "http"
    PARSE_ERROR = "parse"
    TIMEOUT_ERROR = "timeout"
    RATE_LIMIT = "rate_limit"
    SSL_ERROR = "ssl"
    CONTENT_ERROR = "content"
    UNKNOWN_ERROR = "unknown"

@dataclass
class ScrapingAttempt:
    """Record of a scraping attempt."""
    url: str
    timestamp: datetime
    success: bool
    error_type: Optional[ErrorType] = None
    error_message: str = ""
    response_time: float = 0.0
    articles_found: int = 0
    retry_count: int = 0

@dataclass
class CircuitBreakerState:
    """Circuit breaker state for a domain."""
    failures: int = 0
    last_failure: Optional[datetime] = None
    last_success: Optional[datetime] = None
    state: str = "closed"  # closed, open, half-open
    failure_threshold: int = 5
    timeout_seconds: int = 300  # 5 minutes

    def should_allow_request(self) -> bool:
        """Check if requests should be allowed."""
        if self.state == "closed":
            return True
        elif self.state == "open":
            if self.last_failure and (datetime.now() - self.last_failure).seconds > self.timeout_seconds:
                self.state = "half-open"
                return True
            return False
        else:  # half-open
            return True

    def record_success(self):
        """Record a successful request."""
        self.failures = 0
        self.last_success = datetime.now()
        self.state = "closed"

    def record_failure(self):
        """Record a failed request."""
        self.failures += 1
        self.last_failure = datetime.now()
        if self.failures >= self.failure_threshold:
            self.state = "open"

class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(self, rate: float = 10.0, burst: int = 20):
        """
        Initialize rate limiter.

        Args:
            rate: Requests per second
            burst: Maximum burst size
        """
        self.rate = rate
        self.burst = burst
        self.tokens = burst
        self.last_update = time.time()

    async def acquire(self) -> bool:
        """Acquire a token, waiting if necessary."""
        now = time.time()
        elapsed = now - self.last_update
        self.last_update = now

        # Add tokens based on elapsed time
        self.tokens = min(self.burst, self.tokens + elapsed * self.rate)

        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True

        # Wait for next token
        wait_time = (1.0 - self.tokens) / self.rate
        await asyncio.sleep(wait_time)
        self.tokens = 0.0
        return True

class EnhancedStableScraper:
    """
    Production-ready scraper with comprehensive error handling.

    Features:
    - Circuit breakers per domain
    - Exponential backoff with jitter
    - Rate limiting
    - Content validation
    - Comprehensive error tracking
    - Real-time monitoring
    """

    def __init__(
        self,
        max_retries: int = 3,
        timeout: int = 15,
        max_concurrent: int = 50,
        rate_limit: float = 10.0,
        user_agent: str = None,
        enable_circuit_breakers: bool = True,
        content_validation: bool = True
    ):
        """Initialize enhanced scraper."""
        self.max_retries = max_retries
        self.timeout = timeout
        self.max_concurrent = max_concurrent
        self.rate_limiter = RateLimiter(rate_limit, burst=max_concurrent)
        self.enable_circuit_breakers = enable_circuit_breakers
        self.content_validation = content_validation

        # Circuit breakers per domain
        self.circuit_breakers: Dict[str, CircuitBreakerState] = defaultdict(CircuitBreakerState)

        # Error tracking
        self.attempts: List[ScrapingAttempt] = []
        self.error_counts: Dict[ErrorType, int] = defaultdict(int)
        self.domain_stats: Dict[str, Dict] = defaultdict(lambda: {
            'attempts': 0, 'successes': 0, 'failures': 0, 'avg_response_time': 0.0
        })

        # Content filters
        self.content_filters = [
            self._filter_non_english,
            self._filter_short_content,
            self._filter_spam_content,
            self._filter_duplicate_content
        ]

        # Seen content tracking for deduplication
        self.seen_content_hashes: Set[str] = set()
        self.seen_urls: Set[str] = set()

        # User agent
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )

        # SSL context for problematic sites
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE

    async def fetch_rss_enhanced(
        self,
        url: str,
        source_metadata: Dict = None,
        progress_callback: Callable = None
    ) -> Tuple[bool, Optional[Dict], ErrorType, str]:
        """
        Enhanced RSS fetching with comprehensive error handling.

        Returns:
            (success, data, error_type, error_message)
        """
        start_time = time.time()
        domain = urlparse(url).netloc
        source_metadata = source_metadata or {}

        # Circuit breaker check
        if self.enable_circuit_breakers:
            breaker = self.circuit_breakers[domain]
            if not breaker.should_allow_request():
                error_msg = f"Circuit breaker open for {domain}"
                self._record_attempt(url, False, ErrorType.RATE_LIMIT, error_msg, 0, 0)
                return False, None, ErrorType.RATE_LIMIT, error_msg

        # Rate limiting
        await self.rate_limiter.acquire()

        # Update domain stats
        self.domain_stats[domain]['attempts'] += 1

        for attempt in range(self.max_retries):
            try:
                # Exponential backoff with jitter
                if attempt > 0:
                    backoff_time = (2 ** attempt) + random.uniform(0, 1)
                    await asyncio.sleep(backoff_time)

                # Create timeout for this attempt
                timeout = aiohttp.ClientTimeout(total=self.timeout)

                # SSL configuration
                connector = aiohttp.TCPConnector(
                    ssl=False if domain in self._get_problematic_ssl_domains() else None,
                    limit=self.max_concurrent,
                    limit_per_host=10
                )

                async with aiohttp.ClientSession(
                    connector=connector,
                    timeout=timeout,
                    headers={'User-Agent': self.user_agent}
                ) as session:

                    async with session.get(url) as response:
                        # Check HTTP status
                        if response.status == 404:
                            error_msg = "Feed not found (404)"
                            self._record_attempt(url, False, ErrorType.HTTP_ERROR, error_msg, 0, attempt)
                            return False, None, ErrorType.HTTP_ERROR, error_msg

                        elif response.status == 403:
                            error_msg = "Access forbidden (403)"
                            self._record_attempt(url, False, ErrorType.HTTP_ERROR, error_msg, 0, attempt)
                            return False, None, ErrorType.HTTP_ERROR, error_msg

                        elif response.status == 429:
                            # Rate limited - respect the server
                            retry_after = response.headers.get('Retry-After', '60')
                            error_msg = f"Rate limited (429), retry after {retry_after}s"
                            if attempt < self.max_retries - 1:
                                await asyncio.sleep(int(retry_after))
                                continue
                            self._record_attempt(url, False, ErrorType.RATE_LIMIT, error_msg, 0, attempt)
                            return False, None, ErrorType.RATE_LIMIT, error_msg

                        elif response.status >= 500:
                            # Server error - retry
                            if attempt < self.max_retries - 1:
                                continue
                            error_msg = f"Server error ({response.status})"
                            self._record_attempt(url, False, ErrorType.HTTP_ERROR, error_msg, 0, attempt)
                            return False, None, ErrorType.HTTP_ERROR, error_msg

                        elif response.status != 200:
                            error_msg = f"HTTP error ({response.status})"
                            self._record_attempt(url, False, ErrorType.HTTP_ERROR, error_msg, 0, attempt)
                            return False, None, ErrorType.HTTP_ERROR, error_msg

                        # Read content
                        content = await response.text()

                        # Parse feed
                        feed = feedparser.parse(content)

                        # Validate feed structure
                        if not hasattr(feed, 'entries') or not feed.entries:
                            if attempt < self.max_retries - 1:
                                continue
                            error_msg = "No entries found in feed"
                            self._record_attempt(url, False, ErrorType.CONTENT_ERROR, error_msg, 0, attempt)
                            return False, None, ErrorType.CONTENT_ERROR, error_msg

                        # Process articles
                        articles = await self._process_feed_entries(
                            feed.entries, url, source_metadata
                        )

                        if not articles:
                            error_msg = "No valid articles after processing"
                            self._record_attempt(url, False, ErrorType.CONTENT_ERROR, error_msg, 0, attempt)
                            return False, None, ErrorType.CONTENT_ERROR, error_msg

                        # Success!
                        response_time = time.time() - start_time
                        self._record_attempt(url, True, None, "", response_time, attempt, len(articles))

                        # Update circuit breaker
                        if self.enable_circuit_breakers:
                            self.circuit_breakers[domain].record_success()

                        # Update domain stats
                        self.domain_stats[domain]['successes'] += 1
                        self._update_avg_response_time(domain, response_time)

                        # Progress callback
                        if progress_callback:
                            progress_callback(url, True, len(articles), None)

                        return True, {
                            'articles': articles,
                            'feed_info': feed.feed,
                            'source_metadata': source_metadata,
                            'response_time': response_time,
                            'attempt_count': attempt + 1
                        }, None, ""

            except asyncio.TimeoutError:
                error_msg = f"Request timeout after {self.timeout}s"
                if attempt == self.max_retries - 1:
                    self._record_attempt(url, False, ErrorType.TIMEOUT_ERROR, error_msg, 0, attempt)
                    return False, None, ErrorType.TIMEOUT_ERROR, error_msg
                continue

            except aiohttp.ClientError as e:
                error_msg = f"Network error: {str(e)[:100]}"
                if attempt == self.max_retries - 1:
                    self._record_attempt(url, False, ErrorType.NETWORK_ERROR, error_msg, 0, attempt)
                    return False, None, ErrorType.NETWORK_ERROR, error_msg
                continue

            except ssl.SSLError as e:
                error_msg = f"SSL error: {str(e)[:100]}"
                if attempt == self.max_retries - 1:
                    self._record_attempt(url, False, ErrorType.SSL_ERROR, error_msg, 0, attempt)
                    return False, None, ErrorType.SSL_ERROR, error_msg
                continue

            except Exception as e:
                error_msg = f"Unexpected error: {str(e)[:100]}"
                if attempt == self.max_retries - 1:
                    self._record_attempt(url, False, ErrorType.UNKNOWN_ERROR, error_msg, 0, attempt)
                    return False, None, ErrorType.UNKNOWN_ERROR, error_msg
                continue

        # All retries failed
        if self.enable_circuit_breakers:
            self.circuit_breakers[domain].record_failure()

        self.domain_stats[domain]['failures'] += 1
        return False, None, ErrorType.UNKNOWN_ERROR, "Max retries exceeded"

    async def _process_feed_entries(
        self,
        entries: List,
        source_url: str,
        source_metadata: Dict
    ) -> List[Dict]:
        """Process feed entries into articles with validation."""
        articles = []
        domain = urlparse(source_url).netloc

        for entry in entries[:100]:  # Limit per feed
            try:
                article = await self._parse_entry_enhanced(entry, source_url, source_metadata)

                if article and self._validate_article(article):
                    # Content filtering
                    if self.content_validation:
                        if not self._passes_content_filters(article):
                            continue

                    # Deduplication
                    content_hash = self._get_content_hash(article)
                    if content_hash in self.seen_content_hashes:
                        continue

                    if article['url'] in self.seen_urls:
                        continue

                    # Add to tracking
                    self.seen_content_hashes.add(content_hash)
                    self.seen_urls.add(article['url'])

                    # Enrich with metadata
                    article.update({
                        'scraped_at': datetime.now().isoformat(),
                        'source_domain': domain,
                        'source_metadata': source_metadata,
                        'processing_flags': {
                            'content_filtered': self.content_validation,
                            'deduplicated': True
                        }
                    })

                    articles.append(article)

            except Exception as e:
                logger.debug(f"Failed to process entry from {source_url}: {e}")
                continue

        return articles

    async def _parse_entry_enhanced(
        self,
        entry: Dict,
        source_url: str,
        source_metadata: Dict
    ) -> Optional[Dict]:
        """Enhanced entry parsing with comprehensive field extraction."""
        try:
            # Basic fields
            article = {
                'title': self._clean_text(entry.get('title', '')),
                'url': entry.get('link', ''),
                'description': self._extract_description(entry),
                'content': self._extract_content(entry),
                'published_date': self._parse_date_enhanced(entry),
                'author': self._extract_author(entry),
                'tags': self._extract_tags(entry),
                'category': self._extract_category(entry),
                'language': self._detect_language(entry),
                'source_info': {
                    'name': source_metadata.get('name', ''),
                    'domain': urlparse(source_url).netloc,
                    'country': source_metadata.get('country', ''),
                    'region': source_metadata.get('region', ''),
                    'topics': source_metadata.get('topics', [])
                }
            }

            # Validate required fields
            if not article['title'] or not article['url']:
                return None

            # Ensure absolute URL
            if not article['url'].startswith('http'):
                article['url'] = urljoin(source_url, article['url'])

            return article

        except Exception as e:
            logger.debug(f"Error parsing entry: {e}")
            return None

    def _extract_description(self, entry: Dict) -> str:
        """Extract description with fallbacks."""
        fields = ['summary', 'description', 'subtitle']

        for field in fields:
            if field in entry:
                content = entry[field]
                if isinstance(content, str):
                    return self._clean_text(content)[:2000]
                elif isinstance(content, list) and content:
                    if isinstance(content[0], dict):
                        return self._clean_text(content[0].get('value', ''))[:2000]
                    else:
                        return self._clean_text(str(content[0]))[:2000]

        return ""

    def _extract_content(self, entry: Dict) -> str:
        """Extract full content if available."""
        if 'content' in entry and isinstance(entry['content'], list):
            for content_item in entry['content']:
                if isinstance(content_item, dict) and 'value' in content_item:
                    return self._clean_text(content_item['value'])[:10000]

        # Fallback to description
        return self._extract_description(entry)

    def _extract_author(self, entry: Dict) -> str:
        """Extract author information."""
        author_fields = ['author', 'dc_creator', 'author_detail']

        for field in author_fields:
            if field in entry:
                author = entry[field]
                if isinstance(author, str):
                    return self._clean_text(author)
                elif isinstance(author, dict):
                    return self._clean_text(author.get('name', ''))

        return ""

    def _extract_tags(self, entry: Dict) -> List[str]:
        """Extract tags/keywords."""
        tags = []

        if 'tags' in entry:
            for tag in entry['tags']:
                if isinstance(tag, dict):
                    tags.append(tag.get('term', ''))
                else:
                    tags.append(str(tag))

        return [self._clean_text(tag) for tag in tags if tag]

    def _extract_category(self, entry: Dict) -> str:
        """Extract category information."""
        if 'category' in entry:
            return self._clean_text(entry['category'])
        elif 'tags' in entry and entry['tags']:
            return self._clean_text(entry['tags'][0].get('term', ''))
        return ""

    def _detect_language(self, entry: Dict) -> str:
        """Simple language detection."""
        # This could be enhanced with a proper language detection library
        text = entry.get('title', '') + ' ' + entry.get('summary', '')

        # Simple heuristics
        if any(word in text.lower() for word in ['the', 'and', 'is', 'to', 'of']):
            return 'en'
        elif any(word in text.lower() for word in ['der', 'die', 'das', 'und', 'ist']):
            return 'de'
        elif any(word in text.lower() for word in ['le', 'la', 'et', 'est', 'de']):
            return 'fr'

        return 'unknown'

    def _parse_date_enhanced(self, entry: Dict) -> datetime:
        """Enhanced date parsing with multiple fallbacks."""
        # Try parsed time first
        date_fields = ['published_parsed', 'updated_parsed', 'created_parsed']

        for field in date_fields:
            if hasattr(entry, field) and getattr(entry, field):
                try:
                    return datetime.fromtimestamp(time.mktime(getattr(entry, field)))
                except:
                    continue

        # Try string parsing
        string_fields = ['published', 'updated', 'created', 'pubDate']

        for field in string_fields:
            if field in entry and entry[field]:
                try:
                    # Handle RFC 2822 format
                    from email.utils import parsedate_to_datetime
                    return parsedate_to_datetime(entry[field])
                except:
                    try:
                        # Handle ISO format
                        return datetime.fromisoformat(entry[field].replace('Z', '+00:00'))
                    except:
                        continue

        # Default to now if no date found
        return datetime.now()

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text."""
        if not text:
            return ""

        # Basic HTML tag removal
        import re
        text = re.sub(r'<[^>]+>', '', text)

        # Normalize whitespace
        text = ' '.join(text.split())

        return text.strip()

    def _validate_article(self, article: Dict) -> bool:
        """Validate article has required fields and content."""
        required_fields = ['title', 'url']

        for field in required_fields:
            if not article.get(field):
                return False

        # Minimum content length
        if len(article.get('title', '')) < 10:
            return False

        return True

    def _passes_content_filters(self, article: Dict) -> bool:
        """Check if article passes all content filters."""
        for filter_func in self.content_filters:
            if not filter_func(article):
                return False
        return True

    def _filter_non_english(self, article: Dict) -> bool:
        """Filter for English content (can be disabled for multilingual)."""
        # For now, allow all languages
        return True

    def _filter_short_content(self, article: Dict) -> bool:
        """Filter out articles with too little content."""
        title_len = len(article.get('title', ''))
        desc_len = len(article.get('description', ''))

        return title_len >= 10 and (desc_len >= 50 or len(article.get('content', '')) >= 100)

    def _filter_spam_content(self, article: Dict) -> bool:
        """Filter out obvious spam content."""
        title = article.get('title', '').lower()

        # Simple spam indicators
        spam_indicators = [
            'click here', 'buy now', 'limited time', 'act now',
            'free trial', 'special offer', 'exclusive deal'
        ]

        return not any(indicator in title for indicator in spam_indicators)

    def _filter_duplicate_content(self, article: Dict) -> bool:
        """Check for duplicate content (already handled in main processing)."""
        return True

    def _get_content_hash(self, article: Dict) -> str:
        """Generate hash for content deduplication."""
        content = f"{article.get('title', '')}{article.get('url', '')}"
        return hashlib.md5(content.encode()).hexdigest()

    def _get_problematic_ssl_domains(self) -> Set[str]:
        """Get list of domains with SSL issues."""
        return {
            'some-problematic-site.com',
            # Add known problematic domains
        }

    def _record_attempt(
        self,
        url: str,
        success: bool,
        error_type: Optional[ErrorType],
        error_message: str,
        response_time: float,
        retry_count: int,
        articles_found: int = 0
    ):
        """Record a scraping attempt for monitoring."""
        attempt = ScrapingAttempt(
            url=url,
            timestamp=datetime.now(),
            success=success,
            error_type=error_type,
            error_message=error_message,
            response_time=response_time,
            articles_found=articles_found,
            retry_count=retry_count
        )

        self.attempts.append(attempt)

        # Track error counts
        if error_type:
            self.error_counts[error_type] += 1

        # Keep only recent attempts (memory management)
        if len(self.attempts) > 10000:
            self.attempts = self.attempts[-5000:]

    def _update_avg_response_time(self, domain: str, response_time: float):
        """Update average response time for domain."""
        stats = self.domain_stats[domain]
        current_avg = stats['avg_response_time']
        success_count = stats['successes']

        if success_count == 1:
            stats['avg_response_time'] = response_time
        else:
            stats['avg_response_time'] = (current_avg * (success_count - 1) + response_time) / success_count

    async def fetch_multiple_sources_enhanced(
        self,
        sources: List[Dict],
        progress_callback: Callable = None,
        display_manager = None
    ) -> List[Dict]:
        """
        Enhanced parallel fetching with comprehensive monitoring.
        """
        if display_manager:
            with display_manager.stage_context(display_manager.current_stage):
                return await self._fetch_sources_internal(sources, progress_callback, display_manager)
        else:
            return await self._fetch_sources_internal(sources, progress_callback)

    async def _fetch_sources_internal(
        self,
        sources: List[Dict],
        progress_callback: Callable = None,
        display_manager = None
    ) -> List[Dict]:
        """Internal method for fetching sources."""
        all_articles = []
        total_sources = len(sources)
        completed = 0
        successful = 0
        failed = 0

        # Create semaphore for concurrent limit
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def fetch_single_source(source: Dict) -> List[Dict]:
            """Fetch from a single source with semaphore."""
            async with semaphore:
                # Try multiple URL field names
                url = source.get('rss_url') or source.get('url') or source.get('feed_url') or source.get('link')
                if not url:
                    logger.warning(f"No RSS URL found for source: {source.get('name', 'Unknown')}")
                    return []

                success, data, error_type, error_msg = await self.fetch_rss_enhanced(
                    url, source, progress_callback
                )

                nonlocal completed, successful, failed
                completed += 1

                if success and data:
                    successful += 1
                    articles = data.get('articles', [])

                    # Add source metadata to each article
                    for article in articles:
                        article['source_name'] = source.get('name', '')
                        article['source_priority'] = source.get('priority', 0.5)

                    # Update display
                    if display_manager:
                        display_manager.update_stage_progress(
                            display_manager.current_stage,
                            completed_items=completed,
                            total_items=total_sources,
                            activity=f"Processed {source.get('name', urlparse(url).netloc)} - {len(articles)} articles"
                        )

                    return articles
                else:
                    failed += 1
                    logger.debug(f"Failed to fetch {url}: {error_msg}")

                    # Update display
                    if display_manager:
                        display_manager.update_stage_progress(
                            display_manager.current_stage,
                            completed_items=completed,
                            total_items=total_sources,
                            activity=f"Failed {source.get('name', urlparse(url).netloc)}: {error_msg}"
                        )

                    return []

        # Process all sources concurrently
        tasks = [fetch_single_source(source) for source in sources]

        for completed_task in asyncio.as_completed(tasks):
            try:
                articles = await completed_task
                all_articles.extend(articles)

                # Progress callback
                if progress_callback:
                    progress_callback(completed, total_sources, successful, failed, len(all_articles))

            except Exception as e:
                logger.error(f"Task failed: {e}")
                failed += 1

        logger.info(
            f"Fetching complete: {len(all_articles)} articles from "
            f"{successful}/{total_sources} sources ({failed} failed)"
        )

        return all_articles

    def get_comprehensive_report(self) -> Dict:
        """Get comprehensive scraping report."""
        if not self.attempts:
            return {"message": "No scraping attempts recorded"}

        total_attempts = len(self.attempts)
        successful_attempts = sum(1 for a in self.attempts if a.success)

        # Error analysis
        error_breakdown = {}
        for error_type in ErrorType:
            count = self.error_counts.get(error_type, 0)
            if count > 0:
                error_breakdown[error_type.value] = count

        # Domain performance
        domain_performance = {}
        for domain, stats in self.domain_stats.items():
            if stats['attempts'] > 0:
                domain_performance[domain] = {
                    'success_rate': stats['successes'] / stats['attempts'],
                    'avg_response_time': round(stats['avg_response_time'], 2),
                    'total_attempts': stats['attempts']
                }

        # Circuit breaker status
        circuit_status = {}
        for domain, breaker in self.circuit_breakers.items():
            if breaker.failures > 0 or breaker.state != "closed":
                circuit_status[domain] = {
                    'state': breaker.state,
                    'failures': breaker.failures,
                    'last_failure': breaker.last_failure.isoformat() if breaker.last_failure else None
                }

        # Recent performance
        recent_attempts = [a for a in self.attempts if (datetime.now() - a.timestamp).seconds < 3600]
        recent_success_rate = (
            sum(1 for a in recent_attempts if a.success) / len(recent_attempts)
            if recent_attempts else 0
        )

        return {
            'summary': {
                'total_attempts': total_attempts,
                'success_rate': successful_attempts / total_attempts,
                'recent_success_rate': recent_success_rate,
                'total_articles_fetched': sum(a.articles_found for a in self.attempts),
                'unique_domains_attempted': len(self.domain_stats),
                'domains_with_circuit_breakers_open': len([
                    d for d, b in self.circuit_breakers.items() if b.state == "open"
                ])
            },
            'error_breakdown': error_breakdown,
            'top_performing_domains': sorted(
                domain_performance.items(),
                key=lambda x: x[1]['success_rate'],
                reverse=True
            )[:10],
            'problematic_domains': sorted(
                domain_performance.items(),
                key=lambda x: x[1]['success_rate']
            )[:10],
            'circuit_breaker_status': circuit_status,
            'content_stats': {
                'unique_articles_processed': len(self.seen_content_hashes),
                'duplicate_articles_filtered': total_attempts - len(self.seen_content_hashes)
            }
        }

    def reset_tracking(self):
        """Reset all tracking data."""
        self.attempts.clear()
        self.error_counts.clear()
        self.domain_stats.clear()
        self.circuit_breakers.clear()
        self.seen_content_hashes.clear()
        self.seen_urls.clear()


# Factory function for easy integration
def create_enhanced_scraper(**kwargs) -> EnhancedStableScraper:
    """Create a configured enhanced scraper instance."""
    return EnhancedStableScraper(**kwargs)