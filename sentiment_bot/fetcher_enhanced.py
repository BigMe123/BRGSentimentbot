"""
Enhanced Fetcher with HTML Crawling, Advanced Anti-Bot, and Unlimited Scaling
Preserves all existing anti-bot features and adds HTML crawling capabilities.
"""

from __future__ import annotations

import asyncio
import logging
import json
import re
import time
import random
import brotli
import gzip
import hashlib
from contextlib import suppress
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Iterable, List, Optional, Tuple, Set
from urllib.parse import urlparse, urljoin, parse_qs, urlencode, urlunparse
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from bs4 import BeautifulSoup, Comment

import aiohttp
import feedparser
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rapidfuzz import fuzz

from .config import NEWS_OFFLINE, settings

# Try to import advanced libraries (optional for enhanced features)
try:
    import curl_cffi
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

try:
    from playwright.async_api import async_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

try:
    from newspaper import Article as NewspaperArticle
    HAS_NEWSPAPER = True
except ImportError:
    HAS_NEWSPAPER = False

# Configure enhanced logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
console = Console()


@dataclass
class ArticleData:
    """Enhanced article data with source type and fetch metadata."""
    url: str
    title: str
    text: str
    published: Optional[str] = None
    source_type: str = "RSS"  # RSS or HTML
    source_domain: str = ""
    fetch_method: str = ""  # curl_cffi, aiohttp, playwright
    tls_profile: str = ""
    compression: str = ""
    retry_count: int = 0
    word_count: int = 0
    
    def __post_init__(self):
        if not self.source_domain and self.url:
            self.source_domain = urlparse(self.url).netloc
        if self.text:
            self.word_count = len(self.text.split())


@dataclass
class FetchResult:
    """Result of a fetch operation with detailed metadata."""
    success: bool
    content: Optional[str] = None
    status_code: Optional[int] = None
    method: str = ""
    tls_profile: str = ""
    compression: str = ""
    retry_count: int = 0
    error: Optional[str] = None


@dataclass
class CrawlConfig:
    """Configuration for HTML crawling."""
    max_depth: int = 3
    max_pages: int = 10
    cutoff_date: Optional[datetime] = None
    min_article_length: int = 100
    follow_pagination: bool = True
    extract_categories: bool = True


class SessionManager:
    """Manages persistent sessions with cookies for returning visitor simulation."""
    
    def __init__(self):
        self.sessions: Dict[str, aiohttp.ClientSession] = {}
        self.cookies: Dict[str, Dict[str, str]] = defaultdict(dict)
    
    async def get_session(self, domain: str, headers: Dict[str, str]) -> aiohttp.ClientSession:
        """Get or create a session for a domain with persistent cookies."""
        if domain not in self.sessions or self.sessions[domain].closed:
            connector = create_random_connector()
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            
            # Create cookie jar with stored cookies
            jar = aiohttp.CookieJar()
            if domain in self.cookies:
                for name, value in self.cookies[domain].items():
                    jar.update_cookies({name: value})
            
            self.sessions[domain] = aiohttp.ClientSession(
                headers=headers,
                timeout=timeout,
                connector=connector,
                cookie_jar=jar
            )
            logger.debug(f"[SESSION] Created new session for {domain} with {len(self.cookies[domain])} cookies")
        
        return self.sessions[domain]
    
    def store_cookies(self, domain: str, cookies: Dict[str, str]):
        """Store cookies for a domain."""
        self.cookies[domain].update(cookies)
        logger.debug(f"[SESSION] Stored {len(cookies)} cookies for {domain}")
    
    async def close_all(self):
        """Close all sessions."""
        for session in self.sessions.values():
            if not session.closed:
                await session.close()


class EnhancedContentExtractor:
    """Advanced content extraction with HTML crawling support."""
    
    # Common article link patterns
    ARTICLE_PATTERNS = [
        r'/article[s]?/',
        r'/story/',
        r'/news/',
        r'/\d{4}/\d{2}/\d{2}/',  # Date-based URLs
        r'/post[s]?/',
        r'/blog/',
    ]
    
    # Pagination patterns
    PAGINATION_PATTERNS = [
        r'[?&]page=(\d+)',
        r'/page/(\d+)',
        r'[?&]p=(\d+)',
        r'/p(\d+)',
        r'[?&]offset=(\d+)',
    ]
    
    # Tracking params to strip
    TRACKING_PARAMS = [
        'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
        'fbclid', 'gclid', 'ref', 'source', 'share'
    ]
    
    @classmethod
    def extract_article_links(cls, html: str, base_url: str) -> Set[str]:
        """Extract article links from HTML page."""
        soup = BeautifulSoup(html, 'html.parser')
        links = set()
        
        for a in soup.find_all('a', href=True):
            href = a['href']
            # Make absolute URL
            full_url = urljoin(base_url, href)
            
            # Check if it looks like an article
            if any(re.search(pattern, full_url) for pattern in cls.ARTICLE_PATTERNS):
                # Strip tracking params
                clean_url = cls.strip_tracking_params(full_url)
                links.add(clean_url)
                
        logger.info(f"[CRAWLER] Extracted {len(links)} article links from {base_url}")
        return links
    
    @classmethod
    def extract_pagination_links(cls, html: str, base_url: str, current_page: int = 1) -> List[str]:
        """Extract pagination links from HTML."""
        soup = BeautifulSoup(html, 'html.parser')
        pages = []
        
        # Look for pagination containers
        pagination = soup.find_all(['nav', 'div'], class_=re.compile(r'paginat|page|Paginat|Page'))
        
        for container in pagination:
            for a in container.find_all('a', href=True):
                href = urljoin(base_url, a['href'])
                for pattern in cls.PAGINATION_PATTERNS:
                    match = re.search(pattern, href)
                    if match:
                        page_num = int(match.group(1))
                        if page_num > current_page:
                            pages.append(href)
        
        # Also check for "next" links
        next_links = soup.find_all('a', string=re.compile(r'next|Next|→|»', re.I))
        for link in next_links:
            if link.get('href'):
                pages.append(urljoin(base_url, link['href']))
        
        return list(set(pages))[:5]  # Limit to 5 pagination links
    
    @classmethod
    def strip_tracking_params(cls, url: str) -> str:
        """Strip tracking parameters from URL."""
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        
        # Remove tracking params
        cleaned_params = {k: v for k, v in params.items() 
                         if k not in cls.TRACKING_PARAMS}
        
        # Rebuild URL
        new_query = urlencode(cleaned_params, doseq=True)
        return urlunparse(parsed._replace(query=new_query))
    
    @classmethod
    def extract_with_newspaper(cls, html: str, url: str) -> Optional[ArticleData]:
        """Extract article using newspaper3k library."""
        if not HAS_NEWSPAPER:
            return None
            
        try:
            article = NewspaperArticle(url)
            article.set_html(html)
            article.parse()
            
            if article.text and len(article.text) > 100:
                return ArticleData(
                    url=url,
                    title=article.title or "",
                    text=article.text,
                    published=str(article.publish_date) if article.publish_date else None
                )
        except Exception as e:
            logger.debug(f"[NEWSPAPER] Failed to extract {url}: {e}")
        
        return None


# Import all existing features from original fetcher first
from .fetcher import (
    CircuitBreaker,
    ContentCache,
    ContentExtractor,
    USER_AGENTS,
    BROWSER_PROFILES,
    ACCEPT_LANGUAGES,
    REFERERS,
    BASE_HEADERS,
    generate_random_headers,
    shuffle_headers,
    create_random_connector,
    add_random_query_params,
    decompress_response,
    select_browser_profile,
    _get_domain_semaphore,
    _domain_semaphores,
    _offline_domains,
)

# Enhanced Accept-Language for different regions
ACCEPT_LANGUAGES_ENHANCED = [
    "en-US,en;q=0.9",
    "en-GB,en;q=0.9",
    "en-SG,en;q=0.9",
    "en-IN,en;q=0.9",
    "en-AU,en;q=0.9",
    "en-CA,en;q=0.9",
    "en-NZ,en;q=0.9",
    "en-ZA,en;q=0.9",
]

# Viewport sizes for Playwright
VIEWPORT_SIZES = [
    {"width": 1920, "height": 1080},  # Desktop FHD
    {"width": 1366, "height": 768},   # Laptop
    {"width": 1536, "height": 864},   # Laptop HD
    {"width": 1440, "height": 900},   # MacBook
    {"width": 2560, "height": 1440},  # Desktop QHD
]

# Enhanced global instances
circuit_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)
content_cache = ContentCache(ttl_seconds=3600, max_size=1000)
session_manager = SessionManager()
content_extractor = EnhancedContentExtractor()


def generate_site_referrer(url: str) -> str:
    """Generate a plausible referrer from the same site."""
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    
    # Common internal pages
    internal_pages = [
        "/",
        "/news",
        "/world",
        "/politics",
        "/business",
        "/technology",
        "/latest",
        "/archive",
        "/topics",
    ]
    
    return base + random.choice(internal_pages)


async def fetch_with_enhanced_playwright(
    url: str, 
    profile: Optional[Dict[str, Any]] = None,
    interact: bool = False
) -> Optional[FetchResult]:
    """Enhanced Playwright fetch with viewport randomization and JS interaction."""
    if not HAS_PLAYWRIGHT:
        return None
    
    try:
        logger.info(f"[PLAYWRIGHT] Starting enhanced fetch for {url}")
        async with async_playwright() as p:
            browser_type = random.choice(['chromium', 'firefox', 'webkit'])
            logger.debug(f"[PLAYWRIGHT] Using {browser_type} browser")
            
            browser = await getattr(p, browser_type).launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled'] if browser_type == 'chromium' else []
            )
            
            # Random viewport
            viewport = random.choice(VIEWPORT_SIZES)
            logger.debug(f"[PLAYWRIGHT] Viewport: {viewport['width']}x{viewport['height']}")
            
            user_agent = profile["user_agent"] if profile else random.choice(USER_AGENTS)
            
            context = await browser.new_context(
                user_agent=user_agent,
                viewport=viewport,
                locale='en-US',
                java_script_enabled=True,
                ignore_https_errors=False,
            )
            
            # Anti-detection script
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });
            """)
            
            page = await context.new_page()
            
            # Set headers with site referrer
            headers = {
                'Accept-Language': random.choice(ACCEPT_LANGUAGES_ENHANCED),
                'Referer': generate_site_referrer(url),
            }
            await page.set_extra_http_headers(headers)
            
            # Navigate with random timing
            await asyncio.sleep(random.uniform(0.1, 0.3))
            response = await page.goto(url, timeout=30000, wait_until='domcontentloaded')
            
            if interact:
                # Simulate human interaction
                logger.debug(f"[PLAYWRIGHT] Simulating human interaction")
                
                # Random scroll
                for _ in range(random.randint(2, 4)):
                    await page.evaluate(f"window.scrollBy(0, {random.randint(100, 500)})")
                    await asyncio.sleep(random.uniform(0.5, 1.5))
                
                # Wait for dynamic content
                await page.wait_for_timeout(random.randint(1000, 3000))
            
            if response and response.status < 400:
                content = await page.content()
                await browser.close()
                
                return FetchResult(
                    success=True,
                    content=content,
                    status_code=response.status,
                    method="playwright",
                    tls_profile=browser_type,
                )
            
            await browser.close()
            return FetchResult(
                success=False,
                status_code=response.status if response else None,
                method="playwright",
                error=f"Status {response.status if response else 'None'}"
            )
            
    except Exception as e:
        logger.warning(f"[PLAYWRIGHT] Failed: {e}")
        return FetchResult(success=False, method="playwright", error=str(e))


async def enhanced_fetch_with_curl_cffi(
    url: str, 
    headers: Dict[str, str], 
    profile: Dict[str, Any]
) -> Optional[FetchResult]:
    """Enhanced curl_cffi fetch with detailed result."""
    if not HAS_CURL_CFFI or not profile.get("tls_client_id"):
        return None
    
    try:
        from curl_cffi.requests import AsyncSession
        
        tls_client_id = profile["tls_client_id"]
        logger.info(f"[CURL_CFFI] Using TLS: {tls_client_id}")
        
        async with AsyncSession() as session:
            response = await session.get(
                url,
                headers=headers,
                timeout=30,
                impersonate=tls_client_id
            )
            
            if response.status_code < 400:
                return FetchResult(
                    success=True,
                    content=response.text,
                    status_code=response.status_code,
                    method="curl_cffi",
                    tls_profile=tls_client_id,
                )
            else:
                return FetchResult(
                    success=False,
                    status_code=response.status_code,
                    method="curl_cffi",
                    tls_profile=tls_client_id,
                    error=f"Status {response.status_code}"
                )
                
    except Exception as e:
        logger.debug(f"[CURL_CFFI] Failed: {e}")
        return FetchResult(success=False, method="curl_cffi", error=str(e))


async def enhanced_fetch_url(url: str, use_js: bool = False) -> FetchResult:
    """
    Enhanced fetch with full anti-bot stack and detailed logging.
    Transport chain: curl_cffi → aiohttp → Playwright
    """
    domain = urlparse(url).netloc
    
    # Check cache
    cached = content_cache.get(url)
    if cached:
        logger.info(f"[CACHE] Hit for {domain}")
        return FetchResult(
            success=True,
            content=cached.text,
            method="cache"
        )
    
    # Check circuit breaker
    if circuit_breaker.is_open(url):
        logger.warning(f"[CIRCUIT] Breaker open for {domain}")
        return FetchResult(success=False, error="Circuit breaker open")
    
    # Select browser profile for consistency
    browser_profile = select_browser_profile()
    profile_name = list(BROWSER_PROFILES.keys())[list(BROWSER_PROFILES.values()).index(browser_profile)]
    
    result = None
    retry_count = 0
    
    # Try curl_cffi first
    if HAS_CURL_CFFI and browser_profile.get("tls_client_id"):
        headers = shuffle_headers(generate_random_headers(browser_profile))
        headers['Referer'] = generate_site_referrer(url)
        headers['Accept-Language'] = random.choice(ACCEPT_LANGUAGES_ENHANCED)
        
        result = await enhanced_fetch_with_curl_cffi(url, headers, browser_profile)
        if result and result.success:
            logger.info(f"[✅] {domain} — {len(result.content)} bytes — TLS: {result.tls_profile} — OK")
            circuit_breaker.record_success(url)
            return result
    
    # Try aiohttp with retries
    max_retries = 3
    for attempt in range(max_retries):
        retry_count = attempt
        
        headers = shuffle_headers(generate_random_headers(browser_profile))
        headers['Referer'] = generate_site_referrer(url)
        headers['Accept-Language'] = random.choice(ACCEPT_LANGUAGES_ENHANCED)
        
        sem = _get_domain_semaphore(domain)
        
        try:
            async with sem:
                # Browser-like timing
                await asyncio.sleep(random.uniform(0.05, 0.5))
                
                session = await session_manager.get_session(domain, headers)
                
                async with session.get(url) as resp:
                    if resp.status in (403, 429):
                        if attempt == 0:
                            logger.warning(f"[⚠] {domain} — Blocked ({resp.status}) — Retrying...")
                            await asyncio.sleep(random.uniform(0.5, 2.0))
                            continue
                    
                    if resp.status < 400:
                        content_bytes = await resp.read()
                        encoding = resp.headers.get('content-encoding', '').lower()
                        content = await decompress_response(content_bytes, encoding)
                        
                        # Store cookies
                        if resp.cookies:
                            session_manager.store_cookies(domain, dict(resp.cookies))
                        
                        compression_info = f"— {encoding or 'none'} decompressed" if encoding else ""
                        logger.info(f"[✅] {domain} — {len(content)} bytes {compression_info} — OK")
                        
                        circuit_breaker.record_success(url)
                        return FetchResult(
                            success=True,
                            content=content,
                            status_code=resp.status,
                            method="aiohttp",
                            compression=encoding,
                            retry_count=retry_count
                        )
                        
        except Exception as e:
            logger.debug(f"[AIOHTTP] Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
    
    # Fallback to Playwright
    if use_js or not result or not result.success:
        logger.warning(f"[⚠] {domain} — Falling back to Playwright JS rendering...")
        result = await fetch_with_enhanced_playwright(url, browser_profile, interact=use_js)
        
        if result and result.success:
            logger.info(f"[✅] {domain} (Playwright) — {len(result.content)} bytes — OK")
            circuit_breaker.record_success(url)
            return result
        else:
            logger.error(f"[❌] {domain} — All methods failed — Skipped")
            circuit_breaker.record_failure(url)
    
    return FetchResult(success=False, error="All methods failed", retry_count=retry_count)


async def crawl_html(
    url: str,
    config: CrawlConfig = CrawlConfig(),
    topic_filter: Optional[str] = None,
    region_filter: Optional[str] = None
) -> List[ArticleData]:
    """
    Crawl HTML page for articles with pagination support.
    """
    articles = []
    visited_urls = set()
    pages_crawled = 0
    
    async def crawl_page(page_url: str, depth: int = 0):
        nonlocal pages_crawled
        
        if depth > config.max_depth or pages_crawled >= config.max_pages:
            return
        
        if page_url in visited_urls:
            return
        
        visited_urls.add(page_url)
        pages_crawled += 1
        
        logger.info(f"[CRAWLER] Crawling page {pages_crawled}/{config.max_pages}: {page_url}")
        
        # Fetch page
        result = await enhanced_fetch_url(page_url)
        if not result.success or not result.content:
            return
        
        # Extract article links
        article_links = content_extractor.extract_article_links(result.content, page_url)
        
        # Fetch articles
        for article_url in article_links:
            if article_url in visited_urls:
                continue
            
            article_result = await enhanced_fetch_url(article_url)
            if not article_result.success:
                continue
            
            # Try newspaper extraction first
            article_data = content_extractor.extract_with_newspaper(
                article_result.content, article_url
            )
            
            # Fallback to BeautifulSoup extraction
            if not article_data:
                soup = BeautifulSoup(article_result.content, 'html.parser')
                metadata = ContentExtractor.extract_metadata(soup)
                text = ContentExtractor.smart_extract(soup)
                
                if len(text) < config.min_article_length:
                    continue
                
                article_data = ArticleData(
                    url=article_url,
                    title=metadata.get('og_title', ''),
                    text=text,
                    published=metadata.get('published'),
                    source_type="HTML",
                    fetch_method=article_result.method,
                    tls_profile=article_result.tls_profile,
                    compression=article_result.compression,
                    retry_count=article_result.retry_count
                )
            
            # Apply topic/region filters
            if topic_filter and topic_filter.lower() not in article_data.text.lower():
                logger.debug(f"[FILTER] Skipping {article_url} - no topic match")
                continue
            
            if region_filter and region_filter.lower() not in article_data.text.lower():
                logger.debug(f"[FILTER] Skipping {article_url} - no region match")
                continue
            
            # Check cutoff date
            if config.cutoff_date and article_data.published:
                try:
                    pub_date = datetime.fromisoformat(article_data.published)
                    if pub_date < config.cutoff_date:
                        logger.debug(f"[FILTER] Skipping {article_url} - too old")
                        continue
                except:
                    pass
            
            articles.append(article_data)
            visited_urls.add(article_url)
        
        # Follow pagination if enabled
        if config.follow_pagination and depth < config.max_depth:
            pagination_links = content_extractor.extract_pagination_links(
                result.content, page_url, depth + 1
            )
            
            for next_page in pagination_links:
                await crawl_page(next_page, depth + 1)
    
    await crawl_page(url)
    
    logger.info(f"[CRAWLER] Crawled {pages_crawled} pages, found {len(articles)} articles")
    return articles


def deduplicate_articles(articles: List[ArticleData], threshold: float = 0.85) -> List[ArticleData]:
    """
    Deduplicate articles by URL and text similarity.
    """
    if not articles:
        return []
    
    # First pass: URL deduplication
    seen_urls = set()
    url_deduped = []
    
    for article in articles:
        clean_url = content_extractor.strip_tracking_params(article.url)
        if clean_url not in seen_urls:
            seen_urls.add(clean_url)
            url_deduped.append(article)
    
    # Second pass: Text similarity deduplication
    final_articles = []
    
    for article in url_deduped:
        is_duplicate = False
        
        for existing in final_articles:
            # Use rapidfuzz for efficient similarity comparison
            similarity = fuzz.ratio(article.text[:500], existing.text[:500]) / 100.0
            
            if similarity > threshold:
                is_duplicate = True
                logger.debug(f"[DEDUP] Removing duplicate: {article.url} (similarity: {similarity:.2f})")
                break
        
        if not is_duplicate:
            final_articles.append(article)
    
    logger.info(f"[DEDUP] Reduced {len(articles)} → {len(final_articles)} articles")
    return final_articles


async def load_mixed_sources(file_path: str = "sources.txt") -> Dict[str, List[str]]:
    """
    Load mixed RSS and HTML sources from file.
    Format: TYPE|URL where TYPE is RSS or HTML
    """
    sources = {"RSS": [], "HTML": []}
    
    try:
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                parts = line.split('|', 1)
                if len(parts) == 2:
                    source_type, url = parts
                    if source_type.upper() in sources:
                        sources[source_type.upper()].append(url)
    except FileNotFoundError:
        logger.warning(f"Sources file {file_path} not found, using defaults")
    
    return sources


async def gather_with_thresholds(
    sources: Dict[str, List[str]],
    volatility_threshold: float = 0.5,
    certainty_threshold: float = 0.5,
    topic_filter: Optional[str] = None,
    region_filter: Optional[str] = None,
    max_iterations: int = 10
) -> Tuple[List[ArticleData], Dict[str, Any]]:
    """
    Gather articles until volatility and certainty thresholds are met.
    """
    all_articles = []
    stats = {
        "iterations": 0,
        "total_sources": 0,
        "volatility": 0.0,
        "certainty": 0.0,
    }
    
    # Create source queue
    rss_queue = deque(sources.get("RSS", []))
    html_queue = deque(sources.get("HTML", []))
    
    for iteration in range(max_iterations):
        stats["iterations"] = iteration + 1
        batch_articles = []
        
        # Fetch from RSS sources
        if rss_queue:
            rss_url = rss_queue.popleft()
            logger.info(f"[ITERATION {iteration + 1}] Fetching RSS: {rss_url}")
            
            # Parse RSS feed
            try:
                parsed = await asyncio.to_thread(
                    feedparser.parse, 
                    add_random_query_params(rss_url)
                )
                
                for entry in parsed.entries[:20]:  # Limit per feed
                    if entry.get('link'):
                        result = await enhanced_fetch_url(entry['link'])
                        if result.success:
                            # Extract article
                            article = content_extractor.extract_with_newspaper(
                                result.content, entry['link']
                            )
                            if article:
                                article.source_type = "RSS"
                                article.fetch_method = result.method
                                
                                # Apply filters
                                if topic_filter and topic_filter.lower() not in article.text.lower():
                                    continue
                                if region_filter and region_filter.lower() not in article.text.lower():
                                    continue
                                
                                batch_articles.append(article)
            except Exception as e:
                logger.error(f"RSS feed error: {e}")
            
            # Re-queue for next iteration if needed
            rss_queue.append(rss_url)
        
        # Fetch from HTML sources
        if html_queue:
            html_url = html_queue.popleft()
            logger.info(f"[ITERATION {iteration + 1}] Crawling HTML: {html_url}")
            
            crawler_config = CrawlConfig(
                max_pages=5,
                max_depth=2,
                cutoff_date=datetime.now() - timedelta(days=7)
            )
            
            html_articles = await crawl_html(
                html_url,
                config=crawler_config,
                topic_filter=topic_filter,
                region_filter=region_filter
            )
            
            batch_articles.extend(html_articles)
            
            # Re-queue for next iteration if needed
            html_queue.append(html_url)
        
        # Deduplicate batch
        batch_articles = deduplicate_articles(batch_articles)
        all_articles.extend(batch_articles)
        
        # Deduplicate all articles
        all_articles = deduplicate_articles(all_articles)
        
        # Calculate metrics
        if all_articles:
            # Simple volatility calculation (variance in sentiment scores)
            word_counts = [a.word_count for a in all_articles]
            if word_counts:
                mean_words = sum(word_counts) / len(word_counts)
                variance = sum((w - mean_words) ** 2 for w in word_counts) / len(word_counts)
                stats["volatility"] = min(variance / 10000, 1.0)  # Normalize
            
            # Certainty based on data quality
            unique_domains = len(set(a.source_domain for a in all_articles))
            avg_word_count = sum(a.word_count for a in all_articles) / len(all_articles)
            
            stats["certainty"] = min(
                (len(all_articles) / 100) * 0.3 +  # Volume
                (unique_domains / 20) * 0.3 +      # Diversity
                (avg_word_count / 1000) * 0.4,     # Quality
                1.0
            )
        
        logger.info(
            f"[METRICS] Iteration {iteration + 1}: "
            f"Articles={len(all_articles)}, "
            f"Volatility={stats['volatility']:.2f}, "
            f"Certainty={stats['certainty']:.2f}"
        )
        
        # Check thresholds
        if stats["volatility"] >= volatility_threshold and stats["certainty"] >= certainty_threshold:
            logger.info(f"[SUCCESS] Thresholds met after {iteration + 1} iterations")
            break
        
        # Add delay between iterations
        await asyncio.sleep(random.uniform(2, 5))
    
    stats["total_sources"] = len(sources.get("RSS", [])) + len(sources.get("HTML", []))
    stats["total_articles"] = len(all_articles)
    
    return all_articles, stats


async def enhanced_gather_all_sources(
    feeds: Optional[Iterable[str]] = None,
    topic_filter: Optional[str] = None,
    region_filter: Optional[str] = None,
    use_thresholds: bool = True
) -> Tuple[List[ArticleData], Dict[str, Any]]:
    """
    Main entry point for enhanced gathering with all features.
    """
    console.print("[bold cyan]🚀 Enhanced Fetcher with Anti-Bot & HTML Crawling[/bold cyan]")
    
    # Load mixed sources
    sources = await load_mixed_sources()
    
    # Add provided feeds if any
    if feeds:
        sources["RSS"].extend(feeds)
    
    # Use default RSS feeds if no sources
    if not sources["RSS"] and not sources["HTML"]:
        sources["RSS"] = settings.RSS_FEEDS[:10]  # Start with subset
    
    console.print(f"Sources: {len(sources['RSS'])} RSS, {len(sources['HTML'])} HTML")
    
    if use_thresholds:
        # Gather with threshold enforcement
        articles, stats = await gather_with_thresholds(
            sources,
            volatility_threshold=0.5,
            certainty_threshold=0.5,
            topic_filter=topic_filter,
            region_filter=region_filter
        )
    else:
        # Simple gathering without thresholds
        all_articles = []
        
        # Fetch RSS
        for rss_url in sources["RSS"][:20]:
            try:
                parsed = await asyncio.to_thread(feedparser.parse, rss_url)
                for entry in parsed.entries[:10]:
                    if entry.get('link'):
                        result = await enhanced_fetch_url(entry['link'])
                        if result.success:
                            article = content_extractor.extract_with_newspaper(
                                result.content, entry['link']
                            )
                            if article:
                                article.source_type = "RSS"
                                all_articles.append(article)
            except Exception as e:
                logger.error(f"RSS error: {e}")
        
        # Crawl HTML
        for html_url in sources["HTML"][:5]:
            articles = await crawl_html(
                html_url,
                topic_filter=topic_filter,
                region_filter=region_filter
            )
            all_articles.extend(articles)
        
        # Deduplicate
        articles = deduplicate_articles(all_articles)
        
        stats = {
            "total_articles": len(articles),
            "unique_domains": len(set(a.source_domain for a in articles)),
            "avg_word_count": sum(a.word_count for a in articles) / len(articles) if articles else 0
        }
    
    # Log final summary with enhanced format
    console.print("\n[bold green]Fetch Summary:[/bold green]")
    for article in articles[:5]:  # Show first 5
        status = "✅" if article.word_count > 100 else "⚠️"
        method_info = f"{article.fetch_method}" if article.fetch_method else "cache"
        tls_info = f"TLS: {article.tls_profile}" if article.tls_profile else ""
        compression_info = f"{article.compression} decompressed" if article.compression else ""
        
        details = " — ".join(filter(None, [
            f"{article.source_domain} ({article.source_type})",
            f"{article.word_count} words",
            method_info,
            tls_info,
            compression_info,
            "OK" if article.word_count > 100 else "Short"
        ]))
        
        console.print(f"[{status}] {details}")
    
    if len(articles) > 5:
        console.print(f"... and {len(articles) - 5} more articles")
    
    console.print(f"\n[bold]Total:[/bold] {stats.get('total_articles', len(articles))} articles from {stats.get('unique_domains', 0)} domains")
    
    # Clean up sessions
    await session_manager.close_all()
    
    return articles, stats