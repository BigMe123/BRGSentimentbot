#!/usr/bin/env python3
"""
Responsible Stealth Scraper for BSG Sentiment Analysis
=====================================================

A defensive scraping approach that focuses on legitimate RSS feeds and respects
website policies while handling anti-bot protection when necessary for news gathering.
"""

import asyncio
import logging
import random
import time
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass
from urllib.parse import urlparse
import requests
import aiohttp
import feedparser
from urllib.robotparser import RobotFileParser
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

@dataclass
class ResponsibleConfig:
    """Configuration for responsible scraping."""
    respect_robots_txt: bool = True
    min_delay_seconds: float = 2.0
    max_delay_seconds: float = 5.0
    max_concurrent: int = 5
    timeout: int = 30
    user_agent: str = "BSG-SentimentBot/1.0 (+https://github.com/bsg/sentiment-analysis)"
    rate_limit_per_domain: float = 0.5  # Requests per second per domain

class ResponsibleStealthScraper:
    """
    A responsible scraper that uses stealth techniques only when necessary
    for legitimate news gathering while respecting website policies.
    """

    def __init__(self, config: ResponsibleConfig = None):
        """Initialize responsible scraper."""
        self.config = config or ResponsibleConfig()
        self.robots_cache: Dict[str, RobotFileParser] = {}
        self.domain_last_request: Dict[str, datetime] = {}
        self.failed_domains: Dict[str, datetime] = {}
        self.session_stats = {
            'requests_made': 0,
            'rss_feeds_processed': 0,
            'articles_extracted': 0,
            'robots_txt_checked': 0,
            'domains_respected': 0
        }

    async def can_fetch_url(self, url: str) -> Tuple[bool, str]:
        """
        Check if we can fetch the URL according to robots.txt and responsible practices.

        Returns:
            (can_fetch, reason)
        """
        domain = urlparse(url).netloc.lower()

        # Check if domain is temporarily failed
        if domain in self.failed_domains:
            failed_time = self.failed_domains[domain]
            if datetime.now() - failed_time < timedelta(hours=1):
                return False, "Domain temporarily failed"

        # Check robots.txt if configured
        if self.config.respect_robots_txt:
            try:
                can_fetch = await self._check_robots_txt(url)
                if not can_fetch:
                    self.session_stats['domains_respected'] += 1
                    return False, "Blocked by robots.txt"
            except Exception as e:
                logger.warning(f"Could not check robots.txt for {domain}: {e}")
                # If we can't check robots.txt, err on the side of caution but allow RSS
                if not url.endswith(('.rss', '.xml')) and 'feed' not in url.lower():
                    return False, "Could not verify robots.txt permissions"

        # Check rate limiting
        if domain in self.domain_last_request:
            time_since_last = datetime.now() - self.domain_last_request[domain]
            min_interval = timedelta(seconds=1.0 / self.config.rate_limit_per_domain)
            if time_since_last < min_interval:
                wait_time = (min_interval - time_since_last).total_seconds()
                return False, f"Rate limited, wait {wait_time:.1f}s"

        return True, "OK"

    async def _check_robots_txt(self, url: str) -> bool:
        """Check robots.txt for the domain."""
        domain = urlparse(url).netloc.lower()

        if domain not in self.robots_cache:
            try:
                robots_url = f"https://{domain}/robots.txt"

                # Use a simple timeout for robots.txt check
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                    async with session.get(robots_url) as response:
                        if response.status == 200:
                            robots_content = await response.text()

                            rp = RobotFileParser()
                            rp.set_url(robots_url)
                            rp.read()

                            # Parse the content manually if needed
                            lines = robots_content.split('\n')
                            for line in lines:
                                rp.read_line(line)

                            self.robots_cache[domain] = rp
                            self.session_stats['robots_txt_checked'] += 1
                        else:
                            # If no robots.txt, assume we can fetch
                            self.robots_cache[domain] = None

            except Exception as e:
                logger.debug(f"Could not fetch robots.txt for {domain}: {e}")
                self.robots_cache[domain] = None

        rp = self.robots_cache[domain]
        if rp is None:
            return True  # No robots.txt means we can fetch

        return rp.can_fetch(self.config.user_agent, url)

    async def fetch_rss_responsibly(self, url: str, source_metadata: Dict = None) -> Tuple[bool, Optional[Dict], str]:
        """
        Fetch RSS feed responsibly with appropriate delays and respect for policies.

        Returns:
            (success, data, error_message)
        """
        source_metadata = source_metadata or {}
        domain = urlparse(url).netloc.lower()

        # Check if we can fetch
        can_fetch, reason = await self.can_fetch_url(url)
        if not can_fetch:
            return False, None, reason

        # Apply rate limiting delay
        await self._apply_respectful_delay(domain)

        try:
            self.session_stats['requests_made'] += 1
            self.domain_last_request[domain] = datetime.now()

            # Use feedparser for RSS feeds (it handles many edge cases)
            feed = feedparser.parse(url, agent=self.config.user_agent)

            # Check for errors
            if hasattr(feed, 'status') and feed.status >= 400:
                if feed.status >= 500:
                    # Mark domain as temporarily failed for server errors
                    self.failed_domains[domain] = datetime.now()
                return False, None, f"HTTP {feed.status}"

            if feed.bozo and not feed.entries:
                return False, None, "Invalid RSS feed format"

            # Process entries
            articles = []
            for entry in feed.entries[:50]:  # Limit to avoid memory issues
                try:
                    article = self._extract_article_info(entry, url, source_metadata)
                    if article:
                        articles.append(article)
                except Exception as e:
                    logger.debug(f"Error processing entry: {e}")
                    continue

            if articles:
                self.session_stats['rss_feeds_processed'] += 1
                self.session_stats['articles_extracted'] += len(articles)

                return True, {
                    'articles': articles,
                    'feed_info': feed.feed,
                    'source_metadata': source_metadata
                }, ""
            else:
                return False, None, "No valid articles found"

        except Exception as e:
            logger.warning(f"Error fetching RSS from {url}: {e}")
            return False, None, str(e)

    def _extract_article_info(self, entry: Dict, source_url: str, source_metadata: Dict) -> Optional[Dict]:
        """Extract article information from RSS entry."""
        try:
            # Basic article data
            article = {
                'title': entry.get('title', '').strip(),
                'url': entry.get('link', ''),
                'description': self._get_text_content(entry.get('summary', '')),
                'content': self._extract_content(entry),
                'published_date': self._parse_date(entry),
                'author': entry.get('author', ''),
                'source_name': source_metadata.get('name', urlparse(source_url).netloc),
                'source_domain': urlparse(source_url).netloc,
                'source_country': source_metadata.get('country', ''),
                'source_region': source_metadata.get('region', ''),
                'topics': source_metadata.get('topics', []),
                'scraped_at': datetime.now().isoformat(),
                'extraction_method': 'rss'
            }

            # Validate required fields
            if not article['title'] or not article['url']:
                return None

            # Clean and validate data
            article['title'] = self._clean_text(article['title'])
            article['description'] = self._clean_text(article['description'])

            if len(article['title']) < 10:  # Too short
                return None

            return article

        except Exception as e:
            logger.debug(f"Error extracting article: {e}")
            return None

    def _get_text_content(self, content: Any) -> str:
        """Extract text content from various formats."""
        if isinstance(content, str):
            return content
        elif isinstance(content, list) and content:
            if isinstance(content[0], dict):
                return content[0].get('value', '')
            else:
                return str(content[0])
        elif hasattr(content, 'value'):
            return content.value
        return ""

    def _extract_content(self, entry: Dict) -> str:
        """Extract full content from entry."""
        # Try content field first
        if 'content' in entry:
            content = entry['content']
            if isinstance(content, list) and content:
                for item in content:
                    if isinstance(item, dict) and 'value' in item:
                        return self._clean_text(item['value'])

        # Fall back to summary
        return self._get_text_content(entry.get('summary', ''))

    def _parse_date(self, entry: Dict) -> Optional[datetime]:
        """Parse publication date from entry."""
        # Try parsed time first
        time_fields = ['published_parsed', 'updated_parsed']
        for field in time_fields:
            if hasattr(entry, field) and getattr(entry, field):
                try:
                    import time
                    return datetime.fromtimestamp(time.mktime(getattr(entry, field)))
                except:
                    continue

        # Try string parsing
        string_fields = ['published', 'updated']
        for field in string_fields:
            if field in entry and entry[field]:
                try:
                    from email.utils import parsedate_to_datetime
                    return parsedate_to_datetime(entry[field])
                except:
                    continue

        return datetime.now()  # Default to now

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text content."""
        if not text:
            return ""

        # Remove HTML tags
        import re
        text = re.sub(r'<[^>]+>', '', text)

        # Normalize whitespace
        text = ' '.join(text.split())

        return text.strip()

    async def _apply_respectful_delay(self, domain: str):
        """Apply respectful delay between requests."""
        # Random delay to avoid appearing robotic
        delay = random.uniform(self.config.min_delay_seconds, self.config.max_delay_seconds)

        # Additional delay for the same domain
        if domain in self.domain_last_request:
            time_since_last = datetime.now() - self.domain_last_request[domain]
            min_interval = timedelta(seconds=1.0 / self.config.rate_limit_per_domain)

            if time_since_last < min_interval:
                additional_delay = (min_interval - time_since_last).total_seconds()
                delay = max(delay, additional_delay)

        if delay > 0:
            await asyncio.sleep(delay)

    async def fetch_multiple_sources_responsibly(
        self,
        sources: List[Dict],
        progress_callback: Optional[callable] = None
    ) -> List[Dict]:
        """
        Fetch from multiple sources responsibly with proper coordination.
        """
        all_articles = []
        completed = 0
        successful = 0
        failed = 0

        # Process sources with limited concurrency
        semaphore = asyncio.Semaphore(self.config.max_concurrent)

        async def fetch_single_source(source: Dict) -> List[Dict]:
            """Fetch from a single source with semaphore."""
            async with semaphore:
                nonlocal completed, successful, failed

                url = source.get('url') or source.get('rss_url') or source.get('feed_url')
                if not url:
                    failed += 1
                    return []

                success, data, error_msg = await self.fetch_rss_responsibly(url, source)
                completed += 1

                if success and data:
                    successful += 1
                    articles = data.get('articles', [])

                    if progress_callback:
                        progress_callback(completed, len(sources), successful, failed)

                    return articles
                else:
                    failed += 1
                    logger.debug(f"Failed to fetch {url}: {error_msg}")

                    if progress_callback:
                        progress_callback(completed, len(sources), successful, failed)

                    return []

        # Process all sources
        tasks = [fetch_single_source(source) for source in sources]

        for completed_task in asyncio.as_completed(tasks):
            try:
                articles = await completed_task
                all_articles.extend(articles)
            except Exception as e:
                logger.error(f"Task failed: {e}")
                failed += 1

        logger.info(
            f"Responsible scraping complete: {len(all_articles)} articles from "
            f"{successful}/{len(sources)} sources (respecting {self.session_stats['domains_respected']} robots.txt restrictions)"
        )

        return all_articles

    def get_session_report(self) -> Dict[str, Any]:
        """Get comprehensive session report."""
        return {
            'session_stats': self.session_stats,
            'domains_processed': len(self.domain_last_request),
            'domains_failed': len(self.failed_domains),
            'robots_txt_cache_size': len(self.robots_cache),
            'config': {
                'respects_robots_txt': self.config.respect_robots_txt,
                'min_delay': self.config.min_delay_seconds,
                'max_delay': self.config.max_delay_seconds,
                'rate_limit_per_domain': self.config.rate_limit_per_domain,
                'user_agent': self.config.user_agent
            },
            'responsible_features': [
                'Respects robots.txt',
                'Rate limiting per domain',
                'Appropriate delays between requests',
                'Focused on RSS feeds',
                'Transparent user agent',
                'Error handling and backoff'
            ]
        }

    def reset_session(self):
        """Reset session data."""
        self.domain_last_request.clear()
        self.failed_domains.clear()
        self.session_stats = {
            'requests_made': 0,
            'rss_feeds_processed': 0,
            'articles_extracted': 0,
            'robots_txt_checked': 0,
            'domains_respected': 0
        }

# Integration function for existing system
def create_responsible_scraper(**kwargs) -> ResponsibleStealthScraper:
    """Create a configured responsible scraper."""
    config = ResponsibleConfig(**kwargs)
    return ResponsibleStealthScraper(config)

# Drop-in replacement for stealth scraping with responsible defaults
async def fetch_articles_responsibly(
    sources: List[Dict],
    progress_callback: Optional[callable] = None,
    **config_kwargs
) -> List[Dict]:
    """
    Responsible article fetching that respects website policies.

    This is a drop-in replacement for more aggressive scraping methods,
    focused on RSS feeds and legitimate news gathering.
    """
    scraper = create_responsible_scraper(**config_kwargs)

    try:
        articles = await scraper.fetch_multiple_sources_responsibly(sources, progress_callback)

        # Log responsible behavior
        report = scraper.get_session_report()
        logger.info(f"Responsible scraping session: {report['session_stats']}")

        return articles

    except Exception as e:
        logger.error(f"Responsible scraping failed: {e}")
        return []