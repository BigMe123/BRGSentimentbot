from __future__ import annotations

import asyncio
import logging
import json
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse
from bs4 import BeautifulSoup, Comment

import aiohttp
import feedparser

from .config import settings

# Configure logging for risk sentiment analysis
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - RiskSentiment - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class ArticleData:
    """Holds URL, title, text, and optional published timestamp."""

    url: str
    title: str
    text: str
    published: Optional[str] = None


class CircuitBreaker:
    """Circuit breaker pattern for handling failing sources."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures: Dict[str, int] = defaultdict(int)
        self.last_failure_time: Dict[str, float] = {}

    def is_open(self, url: str) -> bool:
        """Check if circuit is open (should skip this URL)."""
        if self.failures[url] < self.failure_threshold:
            return False

        time_since_failure = time.time() - self.last_failure_time.get(url, 0)
        if time_since_failure > self.recovery_timeout:
            # Reset after recovery timeout
            self.failures[url] = 0
            return False
        return True

    def record_success(self, url: str):
        """Record successful fetch."""
        self.failures[url] = 0

    def record_failure(self, url: str):
        """Record failed fetch."""
        self.failures[url] += 1
        self.last_failure_time[url] = time.time()


class ContentCache:
    """Simple in-memory cache with TTL to avoid re-fetching."""

    def __init__(self, ttl_seconds: int = 3600, max_size: int = 1000):
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self.cache: Dict[str, Tuple[ArticleData, float]] = {}
        self.access_order: Deque[str] = deque(maxlen=max_size)

    def get(self, url: str) -> Optional[ArticleData]:
        """Get cached article if not expired."""
        if url in self.cache:
            article, timestamp = self.cache[url]
            if time.time() - timestamp < self.ttl_seconds:
                logger.debug(f"Cache hit for {url}")
                return article
            else:
                del self.cache[url]
        return None

    def set(self, url: str, article: ArticleData):
        """Cache article with current timestamp."""
        if len(self.cache) >= self.max_size:
            if self.access_order:
                oldest = self.access_order.popleft()
                self.cache.pop(oldest, None)

        self.cache[url] = (article, time.time())
        self.access_order.append(url)


class ContentExtractor:
    """Advanced content extraction with multiple strategies."""

    # Common non-content class/id patterns
    NEGATIVE_PATTERNS = re.compile(
        r"(sidebar|footer|header|nav|menu|comment|ad|advertisement|banner|"
        r"social|share|related|recommended|popup|overlay|modal)",
        re.IGNORECASE,
    )

    # Positive indicators for main content
    POSITIVE_PATTERNS = re.compile(
        r"(article|content|main|body|post|entry|text|story|paragraph)", re.IGNORECASE
    )

    @staticmethod
    def calculate_text_density(element) -> float:
        """Calculate text density for an element."""
        text_length = len(element.get_text(strip=True))
        html_length = len(str(element))
        return text_length / html_length if html_length > 0 else 0

    @staticmethod
    def clean_text(text: str) -> str:
        """Clean and normalize extracted text."""
        # Remove excessive whitespace
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Remove common artifacts
        text = re.sub(r"^\s*Advertisement\s*$", "", text, flags=re.MULTILINE)
        text = re.sub(r"^\s*ADVERTISEMENT\s*$", "", text, flags=re.MULTILINE)

        return text.strip()

    @staticmethod
    def extract_metadata(soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract metadata from HTML for better context."""
        metadata = {}

        # Open Graph
        og_title = soup.find("meta", property="og:title")
        if og_title:
            metadata["og_title"] = og_title.get("content")

        og_desc = soup.find("meta", property="og:description")
        if og_desc:
            metadata["description"] = og_desc.get("content")

        # Article metadata
        article_author = soup.find("meta", {"name": "author"})
        if article_author:
            metadata["author"] = article_author.get("content")

        # Published time from multiple sources
        for prop in ["article:published_time", "datePublished", "publish_date"]:
            date_meta = soup.find("meta", {"property": prop}) or soup.find(
                "meta", {"name": prop}
            )
            if date_meta:
                metadata["published"] = date_meta.get("content")
                break

        # JSON-LD structured data
        json_ld = soup.find("script", type="application/ld+json")
        if json_ld:
            try:
                data = json.loads(json_ld.string)
                if isinstance(data, dict):
                    if "headline" in data:
                        metadata["headline"] = data["headline"]
                    if "datePublished" in data:
                        metadata["published"] = data["datePublished"]
            except json.JSONDecodeError:
                pass

        return metadata

    @classmethod
    def smart_extract(cls, soup: BeautifulSoup) -> str:
        """Smart content extraction using heuristics for maximum content."""
        # Remove script, style, and comments
        for element in soup(["script", "style", "noscript"]):
            element.decompose()
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

        # Strategy 1: Look for main content containers
        main_content = None

        # Check for article tag
        article = soup.find("article")
        if article:
            main_content = article

        # Check for main tag
        if not main_content:
            main_tag = soup.find("main")
            if main_tag:
                main_content = main_tag

        # Look for divs with positive indicators
        if not main_content:
            candidates = []
            for div in soup.find_all("div", class_=True):
                classes = " ".join(div.get("class", []))
                if cls.POSITIVE_PATTERNS.search(
                    classes
                ) and not cls.NEGATIVE_PATTERNS.search(classes):
                    density = cls.calculate_text_density(div)
                    candidates.append((density, div))

            if candidates:
                candidates.sort(key=lambda x: x[0], reverse=True)
                main_content = candidates[0][1]

        # Fallback to body
        if not main_content:
            main_content = soup.body if soup.body else soup

        # Extract text from ALL relevant elements for maximum sentiment data
        text_elements = main_content.find_all(
            [
                "p",
                "div",
                "section",
                "article",
                "h1",
                "h2",
                "h3",
                "h4",
                "h5",
                "h6",
                "blockquote",
                "li",
                "td",
                "th",
                "span",
            ]
        )

        seen_text = set()
        text_parts = []

        for elem in text_elements:
            # Skip elements in negative containers
            parent_classes = " ".join(
                elem.parent.get("class", []) if elem.parent else []
            )
            if cls.NEGATIVE_PATTERNS.search(parent_classes):
                continue

            text = elem.get_text(separator=" ", strip=True)
            # Keep more text for sentiment analysis - reduced minimum from 20 to 15
            if len(text) > 15 and text not in seen_text:
                seen_text.add(text)
                text_parts.append(text)

        return "\n\n".join(text_parts)


# Global instances for reuse
circuit_breaker = CircuitBreaker()
content_cache = ContentCache()
content_extractor = ContentExtractor()


async def _fetch_and_parse_url(url: str) -> ArticleData:
    """
    Fetch a single URL with caching, circuit breaking, and smart extraction.
    """
    # Check cache first
    cached = content_cache.get(url)
    if cached:
        return cached

    # Check circuit breaker
    if circuit_breaker.is_open(url):
        logger.debug(f"Circuit breaker open for {url}, skipping")
        return ArticleData(url=url, title="", text="", published=None)

    # Try newspaper3k first
    try:
        from newspaper import Article  # type: ignore

        def _parse() -> ArticleData:
            art = Article(url)
            art.download()
            art.parse()
            return ArticleData(
                url=url,
                title=art.title or "",
                text=art.text or "",
                published=art.publish_date.isoformat() if art.publish_date else None,
            )

        article = await asyncio.to_thread(_parse)
        if article.text:
            circuit_breaker.record_success(url)
            content_cache.set(url, article)
            return article
    except Exception:
        pass

    # Fallback to aiohttp + BeautifulSoup with retry
    max_retries = 3
    retry_delay = 1

    for attempt in range(max_retries):
        try:
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, ssl=False) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        break
        except Exception:
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (attempt + 1))
                continue
            else:
                # Final fallback to urllib
                try:
                    from urllib.request import urlopen

                    def _urlopen_read() -> str:
                        with urlopen(url, timeout=20) as resp:
                            return resp.read().decode(errors="ignore")

                    html = await asyncio.to_thread(_urlopen_read)
                except Exception:
                    circuit_breaker.record_failure(url)
                    logger.debug(f"All fetch attempts failed for {url}")
                    return ArticleData(url=url, title="", text="", published=None)

    # Parse HTML with smart extraction
    soup = BeautifulSoup(html, "html.parser")

    # Extract metadata
    metadata = content_extractor.extract_metadata(soup)

    # Smart content extraction
    text = content_extractor.smart_extract(soup)

    # Clean text
    text = content_extractor.clean_text(text)

    # Get title with fallbacks
    title = ""
    if "og_title" in metadata:
        title = metadata["og_title"]
    elif "headline" in metadata:
        title = metadata["headline"]
    elif soup.title:
        title = soup.title.get_text(strip=True)
    elif soup.find("h1"):
        title = soup.find("h1").get_text(strip=True)

    # Get published date
    published = metadata.get("published")

    article = ArticleData(
        url=url,
        title=title,
        text=text,
        published=published,
    )

    circuit_breaker.record_success(url)
    content_cache.set(url, article)

    return article


async def fetch_and_parse(url: str) -> ArticleData:
    """Public wrapper around :func:`_fetch_and_parse_url` for easier patching."""
    return await _fetch_and_parse_url(url)


async def gather_rss(feeds: Iterable[str] | None = None) -> List[ArticleData]:
    """
    Parse RSS feeds with maximum parallelization and smart features.
    """
    feed_urls = list(feeds or settings.RSS_FEEDS)
    all_article_urls = []

    # Parse all feeds in parallel
    async def parse_feed(feed_url: str) -> List[str]:
        try:
            parsed = await asyncio.to_thread(feedparser.parse, feed_url)
            urls = []
            for entry in parsed.entries:
                if link := entry.get("link"):
                    urls.append(link)
            logger.info(f"Found {len(urls)} articles in feed: {feed_url}")
            return urls
        except Exception as e:
            logger.warning(f"Failed to parse feed {feed_url}: {e}")
            return []

    # Gather all URLs from all feeds concurrently
    feed_tasks = [parse_feed(feed_url) for feed_url in feed_urls]
    feed_results = await asyncio.gather(*feed_tasks)

    for urls in feed_results:
        all_article_urls.extend(urls)

    # Deduplicate URLs while preserving order
    unique_links = list(dict.fromkeys(all_article_urls))

    logger.info(f"Total unique articles to fetch: {len(unique_links)}")

    # Aggressive concurrent fetching with high semaphore limit
    sem = asyncio.Semaphore(50)
    results: List[ArticleData] = []
    failed_count = 0

    async def _worker(link: str):
        nonlocal failed_count
        async with sem:
            try:
                art = await fetch_and_parse(link)
                if art.text:
                    results.append(art)
                    logger.debug(
                        f"Successfully extracted: {link} ({len(art.text)} chars)"
                    )
                else:
                    failed_count += 1
            except Exception:
                failed_count += 1
                logger.exception(f"Failed to fetch or parse {link}")

    # Execute all fetches concurrently
    await asyncio.gather(*[_worker(link) for link in unique_links])

    # Log collection statistics
    total_words = sum(len(art.text.split()) for art in results)
    unique_domains = len(set(urlparse(art.url).netloc for art in results))

    # Calculate confidence score based on volume and diversity
    volume_score = min(len(results) / 100, 1.0)  # Max at 100 articles
    diversity_score = min(unique_domains / 20, 1.0)  # Max at 20 domains
    success_rate = len(results) / len(unique_links) if unique_links else 0
    word_volume_score = min(total_words / 100000, 1.0)  # Max at 100k words

    confidence = (
        volume_score * 0.3
        + diversity_score * 0.2
        + success_rate * 0.2
        + word_volume_score * 0.3
    )

    logger.info(
        f"""
    ========== SENTIMENT DATA COLLECTION SUMMARY ==========
    Total articles collected: {len(results)}/{len(unique_links)}
    Success rate: {success_rate*100:.1f}%
    Total words collected: {total_words:,}
    Unique domains: {unique_domains}
    Cache hits: {sum(1 for _ in content_cache.cache)}
    Circuit breakers active: {sum(1 for url in circuit_breaker.failures if circuit_breaker.is_open(url))}
    CONFIDENCE SCORE: {confidence*100:.1f}%
    ========================================================
    """
    )

    return results


async def gather_all_sources(feeds: Iterable[str] | None = None) -> List[ArticleData]:
    """
    Main entry point for risk sentiment data collection.
    Maximizes article volume with smart features for high-confidence analysis.
    """
    return await gather_rss(feeds)
