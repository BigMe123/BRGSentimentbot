from __future__ import annotations

import asyncio
import logging
import json
import re
import time
import random
import brotli
import gzip
import platform
from contextlib import suppress
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse
from bs4 import BeautifulSoup, Comment

import aiohttp
import feedparser
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn

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

# Browser profiles with TLS fingerprints for advanced anti-detection
BROWSER_PROFILES = {
    "chrome110": {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "sec_ch_ua_mobile": "?0",
        "sec_ch_ua_platform": '"Windows"',
        "accept_encoding": "gzip, deflate, br, zstd",
        "tls_client_id": "chrome110" if HAS_CURL_CFFI else None,
    },
    "firefox102": {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
        "accept_encoding": "gzip, deflate, br",
        "tls_client_id": "firefox102" if HAS_CURL_CFFI else None,
    },
    "safari15_5": {
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
        "accept_encoding": "gzip, deflate, br",
        "tls_client_id": "safari15_5" if HAS_CURL_CFFI else None,
    },
    "edge101": {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
        "sec_ch_ua": '"Not_A Brand";v="8", "Chromium";v="120", "Microsoft Edge";v="120"',
        "sec_ch_ua_mobile": "?0",
        "sec_ch_ua_platform": '"Windows"',
        "accept_encoding": "gzip, deflate, br, zstd",
        "tls_client_id": "edge101" if HAS_CURL_CFFI else None,
    },
}

# Enhanced User-Agent pool with 50+ variations across platforms and browsers
USER_AGENTS = [
    # Chrome - Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    
    # Chrome - macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    
    # Chrome - Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    
    # Firefox - Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/118.0",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    
    # Firefox - macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.0; rv:109.0) Gecko/20100101 Firefox/121.0",
    
    # Firefox - Linux
    "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/121.0",
    
    # Safari - macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    
    # Edge - Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    
    # Mobile Chrome - Android
    "Mozilla/5.0 (Linux; Android 14; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36",
    
    # Mobile Safari - iOS
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
    
    # Opera
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 OPR/106.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 OPR/106.0.0.0",
    
    # Additional varied Chrome versions
    "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    
    # Additional Firefox versions
    "Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:109.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/119.0",
    
    # Brave (Chrome-based)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Brave/120",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Brave/120",
    
    # Vivaldi
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Vivaldi/6.4.3160.47",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Vivaldi/6.4.3160.47",
    
    # Additional Chrome mobile variant
    "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
]

# Accept-Language variations for different regions
ACCEPT_LANGUAGES = [
    "en-US,en;q=0.9",
    "en-US,en;q=0.9,fr;q=0.8",
    "en-US,en;q=0.9,es;q=0.8,de;q=0.7",
    "en-GB,en;q=0.9,en-US;q=0.8",
    "en-US,en;q=0.8,fr-FR;q=0.6,fr;q=0.4",
    "en-CA,en;q=0.9,fr;q=0.8",
    "en-AU,en;q=0.9,en-GB;q=0.8",
    "en,en-US;q=0.9,en-GB;q=0.8",
    "en-US,en;q=0.5"
]

# Referer variations to simulate different entry points
REFERERS = [
    "https://www.google.com/",
    "https://www.google.com/search?q=news",
    "https://www.bing.com/",
    "https://duckduckgo.com/",
    "https://news.google.com/",
    "https://www.reddit.com/",
    "https://twitter.com/",
    "https://www.facebook.com/",
    "https://news.ycombinator.com/",
    "",  # No referer sometimes
]

BASE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

_domain_semaphores: Dict[str, asyncio.Semaphore] = {}
_offline_domains: set[str] = set()


def generate_random_headers(browser_profile: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """Generate randomized headers with human-like variations and browser profile support."""
    headers = BASE_HEADERS.copy()
    
    if browser_profile:
        # Use browser profile for consistency
        headers["User-Agent"] = browser_profile["user_agent"]
        if "accept_encoding" in browser_profile:
            headers["Accept-Encoding"] = browser_profile["accept_encoding"]
        
        # Add browser-specific headers
        for key in ["sec_ch_ua", "sec_ch_ua_mobile", "sec_ch_ua_platform"]:
            if key in browser_profile:
                headers[key.replace("_", "-").title()] = browser_profile[key]
    else:
        # Fallback to random selection
        headers["User-Agent"] = random.choice(USER_AGENTS)
        
        # Add Chrome-specific headers for Chrome UAs
        if "Chrome/" in headers["User-Agent"] and "Edg/" not in headers["User-Agent"]:
            headers["Sec-CH-UA"] = '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"'
            headers["Sec-CH-UA-Mobile"] = "?0"
            headers["Sec-CH-UA-Platform"] = f'"{random.choice(["Windows", "macOS", "Linux"])}"'
    
    headers["Accept-Language"] = random.choice(ACCEPT_LANGUAGES)
    
    # Randomly add referer (80% of the time)
    if random.random() < 0.8:
        headers["Referer"] = random.choice(REFERERS)
    
    # Platform-specific adjustments
    ua = headers["User-Agent"]
    if "Windows" in ua:
        if random.random() < 0.3:
            headers["Sec-CH-UA-Arch"] = '"x86"' if random.random() < 0.5 else '"arm"'
    elif "Mac" in ua:
        headers["Sec-CH-UA-Platform-Version"] = f'"{random.choice(["10.15", "11.0", "12.0", "13.0"])}"'
    
    return headers


def shuffle_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """Randomize header order to avoid bot detection."""
    items = list(headers.items())
    random.shuffle(items)
    return dict(items)


def create_random_connector() -> aiohttp.TCPConnector:
    """Create TCP connector with random local port for IP-like rotation."""
    try:
        # Try IPv6 first for better rotation
        use_ipv6 = random.random() < 0.7  # 70% chance to use IPv6
        if use_ipv6:
            port = random.randint(40000, 65000)
            local_addr = ("::", port)
            logger.debug(f"[FEATURE] IPv6 source rotation: port {port}")
        else:
            port = random.randint(40000, 65000)
            local_addr = ("0.0.0.0", port)
            logger.debug(f"[FEATURE] IPv4 source rotation: port {port}")
        
        return aiohttp.TCPConnector(
            local_addr=local_addr,
            limit=10,
            limit_per_host=3,
            ttl_dns_cache=300,
            use_dns_cache=True,
            ssl=True
        )
    except Exception:
        # Fallback to IPv4 if IPv6 fails
        return aiohttp.TCPConnector(
            local_addr=("0.0.0.0", random.randint(40000, 65000)),
            limit=10,
            limit_per_host=3,
            ttl_dns_cache=300,
            use_dns_cache=True,
            ssl=True
        )


def add_random_query_params(url: str) -> str:
    """Add harmless query parameters to RSS URLs for uniqueness."""
    if "?" in url:
        separator = "&"
    else:
        separator = "?"
    
    # Only add params occasionally to avoid pattern detection
    if random.random() < 0.3:
        logger.debug(f"[FEATURE] Adding random query parameters to RSS URL")
        random_params = []
        
        # Common tracking parameters
        if random.random() < 0.5:
            random_params.append(f"utm_source=feed_reader_{random.randint(100, 999)}")
        if random.random() < 0.3:
            random_params.append(f"v={random.randint(1000000, 9999999)}")
        if random.random() < 0.2:
            random_params.append(f"t={int(time.time())}")
        
        if random_params:
            url += separator + "&".join(random_params)
    
    return url


async def decompress_response(content: bytes, encoding: str) -> str:
    """Decompress response content based on encoding."""
    try:
        if encoding == 'br':
            return brotli.decompress(content).decode('utf-8', errors='ignore')
        elif encoding == 'gzip':
            return gzip.decompress(content).decode('utf-8', errors='ignore')
        elif encoding == 'deflate':
            import zlib
            return zlib.decompress(content).decode('utf-8', errors='ignore')
        else:
            return content.decode('utf-8', errors='ignore')
    except Exception as e:
        logger.debug(f"Decompression failed for {encoding}: {e}")
        return content.decode('utf-8', errors='ignore')


def select_browser_profile() -> Dict[str, Any]:
    """Select random browser profile with TLS fingerprint."""
    profile_name = random.choice(list(BROWSER_PROFILES.keys()))
    logger.debug(f"[FEATURE] Browser profile selected: {profile_name}")
    return BROWSER_PROFILES[profile_name]


async def fetch_with_curl_cffi(url: str, headers: Dict[str, str], profile: Dict[str, Any]) -> Optional[str]:
    """Fetch URL using curl_cffi for TLS fingerprint spoofing."""
    if not HAS_CURL_CFFI or not profile.get("tls_client_id"):
        logger.debug(f"[FEATURE] curl_cffi not available or no TLS client ID")
        return None
        
    try:
        from curl_cffi.requests import AsyncSession
        
        tls_client_id = profile["tls_client_id"]
        timeout = 30
        logger.info(f"[FEATURE] curl_cffi using TLS fingerprint: {tls_client_id}")
        
        async with AsyncSession() as session:
            response = await session.get(
                url,
                headers=headers,
                timeout=timeout,
                impersonate=tls_client_id
            )
            
            if response.status_code < 400:
                return response.text
            elif response.status_code in (403, 429):
                logger.debug(f"curl_cffi got {response.status_code} for {url}")
                return None
            else:
                response.raise_for_status()
                
    except Exception as e:
        logger.debug(f"curl_cffi failed for {url}: {e}")
        return None


async def fetch_with_playwright(url: str, profile: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Fetch URL using Playwright for JavaScript-heavy sites with enhanced stealth."""
    if not HAS_PLAYWRIGHT:
        logger.debug(f"[FEATURE] Playwright not available for {url}")
        return None
        
    try:
        logger.info(f"[FEATURE] Activating Playwright JS rendering fallback for {url}")
        async with async_playwright() as p:
            # Random browser choice
            browser_type = random.choice(['chromium', 'firefox', 'webkit'])
            logger.debug(f"[FEATURE] Using {browser_type} browser engine")
            
            browser = await getattr(p, browser_type).launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled'] if browser_type == 'chromium' else []
            )
            
            # Use profile if provided, otherwise random
            user_agent = profile["user_agent"] if profile else random.choice(USER_AGENTS)
            
            context = await browser.new_context(
                user_agent=user_agent,
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',
                java_script_enabled=True,
                ignore_https_errors=False,  # Keep SSL verification ON
            )
            
            # Additional stealth settings
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
            
            page = await context.new_page()
            
            # Mimic human behavior with random timing
            await asyncio.sleep(random.uniform(0.1, 0.3))
            
            # Set headers
            headers = {
                'Accept-Language': random.choice(ACCEPT_LANGUAGES),
            }
            if random.random() < 0.8:
                headers['Referer'] = random.choice(REFERERS)
            
            await page.set_extra_http_headers(headers)
            logger.debug(f"[FEATURE] Playwright headers set, navigating to {url}")
            
            response = await page.goto(url, timeout=30000, wait_until='domcontentloaded')
            
            # Wait for additional content to load
            await asyncio.sleep(random.uniform(0.5, 1.0))
            
            if response and response.status < 400:
                content = await page.content()
                await browser.close()
                logger.info(f"[FEATURE] Playwright successfully rendered {url}")
                return content
            else:
                await browser.close()
                logger.warning(f"[FEATURE] Playwright got status {response.status if response else 'None'} for {url}")
                return None
                
    except Exception as e:
        logger.warning(f"[FEATURE] Playwright failed for {url}: {e}")
        return None


async def soft_check_url_head(session: aiohttp.ClientSession, url: str) -> bool:
    """Check if URL is accessible with HEAD request before full download."""
    try:
        async with session.head(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            return resp.status < 400
    except Exception:
        return True  # Assume accessible if HEAD fails, try full request


def _get_domain_semaphore(domain: str) -> asyncio.Semaphore:
    """Get or create semaphore for domain with 2-3 concurrent requests max."""
    if domain not in _domain_semaphores:
        # Randomize between 2-3 concurrent requests per domain for load distribution
        limit = random.choice([2, 3])
        _domain_semaphores[domain] = asyncio.Semaphore(limit)
        logger.info(f"[FEATURE] Domain concurrency limiter: {domain} max {limit} concurrent requests")
    return _domain_semaphores[domain]


async def _fetch_and_parse_url(url: str) -> ArticleData:
    """
    Advanced multi-transport fetch with TLS fingerprinting, compression handling, and JS fallback.
    Implements full transport chain: curl_cffi → aiohttp → Playwright for maximum success rate.
    """
    # Check cache first
    cached = content_cache.get(url)
    if cached:
        return cached

    # Check circuit breaker
    if circuit_breaker.is_open(url):
        logger.debug(f"Circuit breaker open for {url}, skipping")
        return ArticleData(url=url, title="", text="", published=None)

    domain = urlparse(url).netloc
    if domain in _offline_domains:
        return ArticleData(url=url, title="", text="", published=None)

    # Select browser profile for consistency across transports
    browser_profile = select_browser_profile()
    logger.info(f"[FEATURE] Selected browser profile: {list(browser_profile.keys())[0] if browser_profile else 'random'}")
    
    # Try curl_cffi first for TLS fingerprinting
    if HAS_CURL_CFFI and browser_profile.get("tls_client_id"):
        logger.info(f"[FEATURE] Attempting curl_cffi with TLS fingerprint: {browser_profile.get('tls_client_id')}")
        headers = shuffle_headers(generate_random_headers(browser_profile))
        html = await fetch_with_curl_cffi(url, headers, browser_profile)
        if html:
            logger.info(f"[FEATURE] curl_cffi succeeded for {url}")
        else:
            logger.debug(f"[FEATURE] curl_cffi failed, falling back to aiohttp")
    
    # Enhanced fetch with compression handling and better retry logic
    max_retries = 3 if not html else 0  # Skip if curl_cffi succeeded
    backoff = 1
    
    for attempt in range(max_retries):
        # Generate fresh headers and connector for each attempt
        headers = shuffle_headers(generate_random_headers(browser_profile))
        connector = create_random_connector()
        sem = _get_domain_semaphore(domain)
        
        logger.info(f"[FEATURE] aiohttp attempt {attempt + 1}/{max_retries} for {url}")
        logger.debug(f"[FEATURE] Using connector with local_addr: {connector._local_addr if hasattr(connector, '_local_addr') else 'default'}")
        
        try:
            async with sem:
                # Random delay before DNS resolution
                await asyncio.sleep(random.uniform(0.05, 0.2))
                
                timeout = aiohttp.ClientTimeout(total=30, connect=10)
                async with aiohttp.ClientSession(
                    headers=headers, 
                    timeout=timeout,
                    connector=connector
                ) as session:
                    
                    # Optional HEAD request check for better stealth
                    if random.random() < 0.3:  # 30% of requests do HEAD first
                        logger.info(f"[FEATURE] Performing HEAD request check (30% probability)")
                        head_ok = await soft_check_url_head(session, url)
                        if not head_ok:
                            logger.debug(f"[FEATURE] HEAD check failed for {url}, skipping")
                            continue
                        else:
                            logger.debug(f"[FEATURE] HEAD check passed, proceeding with GET")
                    
                    try:
                        # Mimic browser timing with small delay before request
                        delay = random.uniform(0.1, 0.5)
                        logger.debug(f"[FEATURE] Browser-like timing: {delay:.2f}s delay before request")
                        await asyncio.sleep(delay)
                        
                        async with session.get(url) as resp:
                            # Soft retry for 403/429 with different headers before backoff
                            if resp.status in (403, 429):
                                if attempt == 0:  # First attempt - try once more immediately
                                    logger.warning(f"[FEATURE] Status {resp.status} for {url}, activating soft retry")
                                    await asyncio.sleep(random.uniform(0.5, 1.0))
                                    
                                    # Quick retry with different UA and connector
                                    retry_headers = shuffle_headers(generate_random_headers())
                                    retry_connector = create_random_connector()
                                    
                                    async with aiohttp.ClientSession(
                                        headers=retry_headers, 
                                        timeout=timeout,
                                        connector=retry_connector
                                    ) as retry_session:
                                        try:
                                            async with retry_session.get(url) as retry_resp:
                                                if retry_resp.status < 400:
                                                    # Enhanced compression handling for retry
                                                    content_bytes = await retry_resp.read()
                                                    encoding = retry_resp.headers.get('content-encoding', '').lower()
                                                    logger.info(f"[FEATURE] Decompressing response with encoding: {encoding or 'none'}")
                                                    html = await decompress_response(content_bytes, encoding)
                                                    logger.info(f"[FEATURE] Soft retry succeeded for {url}")
                                                    break
                                        except Exception:
                                            pass
                                
                                # If still failing, use normal backoff
                                if not html and attempt < max_retries - 1 and not NEWS_OFFLINE:
                                    logger.warning(f"Status {resp.status} for {url}, backing off")
                                    await asyncio.sleep(random.uniform(2, 5))
                                    continue
                                
                                if not html:
                                    circuit_breaker.record_failure(url)
                                    return ArticleData(url=url, title="", text="", published=None)
                            
                            if not html:
                                resp.raise_for_status()
                                
                                # Enhanced compression handling
                                try:
                                    content_bytes = await resp.read()
                                    encoding = resp.headers.get('content-encoding', '').lower()
                                    logger.info(f"[FEATURE] Response encoding: {encoding or 'none'}, decompressing")
                                    html = await decompress_response(content_bytes, encoding)
                                    
                                except asyncio.TimeoutError:
                                    logger.warning(f"Timeout reading {url}")
                                    raise
                    except asyncio.TimeoutError:
                        logger.warning(f"Timeout connecting {url}")
                        raise
            
            if html:
                break
                
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
            if "Network is unreachable" in str(e) and attempt < max_retries - 1 and not NEWS_OFFLINE:
                await asyncio.sleep(backoff)
                backoff *= 2
                continue
            logger.error("Fetch failed %s: %s", url, e)
            if attempt < max_retries - 1 and not NEWS_OFFLINE:
                await asyncio.sleep(backoff)
                backoff *= 2
                continue
            _offline_domains.add(domain)
            circuit_breaker.record_failure(url)
            return ArticleData(url=url, title="", text="", published=None)

    # If no HTML content obtained, try Playwright as final fallback
    if not html:
        logger.warning(f"[FEATURE] aiohttp failed, attempting Playwright JS rendering as final fallback")
        html = await fetch_with_playwright(url, browser_profile)
        
        if not html:
            circuit_breaker.record_failure(url)
            logger.error(f"[FEATURE] All transport methods failed for {url}")
            return ArticleData(url=url, title="", text="", published=None)
        else:
            logger.info(f"[FEATURE] Playwright fallback succeeded for {url}")
    
    # Parse HTML with smart extraction
    try:
        soup = await asyncio.wait_for(
            asyncio.to_thread(BeautifulSoup, html, "html.parser"),
            timeout=30,
        )
    except asyncio.TimeoutError:
        logger.warning(f"Timeout parsing {url}")
        _offline_domains.add(domain)
        circuit_breaker.record_failure(url)
        return ArticleData(url=url, title="", text="", published=None)

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
    logger.info(f"[FEATURE] Article successfully fetched and cached for {url}")

    return article


async def fetch_and_parse(url: str) -> ArticleData:
    """Public wrapper around :func:`_fetch_and_parse_url` for easier patching."""
    return await _fetch_and_parse_url(url)


async def gather_rss(
    feeds: Iterable[str] | None = None,
    region: Optional[str] = None,
    topic: Optional[str] = None,
) -> tuple[List[ArticleData], Dict[str, Any]]:
    """Parse RSS feeds and return articles with collection stats.
    
    Args:
        feeds: Optional list of RSS feed URLs
        region: Optional region filter (e.g., 'asia', 'europe')
        topic: Optional topic filter (e.g., 'elections', 'defense')
    """
    console = Console()
    
    # Import filter if region/topic specified
    filter_func = None
    if region or topic:
        try:
            from .filter import is_relevant
            filter_func = is_relevant
            logger.info(f"Filtering enabled - Region: {region}, Topic: {topic}")
        except ImportError:
            logger.warning("Filter module not available, skipping filtering")
    
    if NEWS_OFFLINE:
        return [
            ArticleData(
                url="http://stub/a", title="Asia trade", text="trade asia"
            ),
            ArticleData(
                url="http://stub/b", title="Africa oil", text="energy africa"
            ),
        ], {"total": 2}
    feed_urls = list(feeds or settings.RSS_FEEDS)
    all_article_urls: List[str] = []

    async def parse_feed(feed_url: str) -> List[str]:
        domain = urlparse(feed_url).netloc
        if domain in _offline_domains:
            return []
        max_retries = 3
        backoff = 1
        last_error = ""
        for attempt in range(1, max_retries + 1):
            # Apply random query params to RSS feed URL
            modified_feed_url = add_random_query_params(feed_url)
            headers = shuffle_headers(generate_random_headers())
            logger.debug(f"[FEATURE] RSS feed headers randomized with {len(headers)} headers")
            sem = _get_domain_semaphore(domain)
            try:
                async with sem:
                    # Random delay with browser-like timing
                    delay = random.uniform(0.1, 0.8)
                    logger.debug(f"[FEATURE] RSS feed delay: {delay:.2f}s for natural timing")
                    await asyncio.sleep(delay)
                    parsed = await asyncio.wait_for(
                        asyncio.to_thread(
                            feedparser.parse, modified_feed_url, request_headers=headers
                        ),
                        timeout=30,
                    )
                if getattr(parsed, "status", 200) == 403:
                    if attempt < max_retries and not NEWS_OFFLINE:
                        logger.warning(f"403 for feed {feed_url}, retrying")
                        await asyncio.sleep(random.uniform(2, 5))
                        continue
                    _offline_domains.add(domain)
                    return []
                return [e.get("link") for e in parsed.entries if e.get("link")]
            except asyncio.TimeoutError:
                last_error = "timeout"
                logger.warning(f"[feed timeout attempt {attempt}] {feed_url}")
            except Exception as e:
                last_error = str(e)
                if "Network is unreachable" in last_error and attempt < max_retries and not NEWS_OFFLINE:
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue
                logger.warning(f"[feed attempt {attempt}] Failed {feed_url}: {e}")
            if attempt < max_retries and not NEWS_OFFLINE:
                await asyncio.sleep(backoff)
                backoff *= 2
                continue
            break
        if "Network is unreachable" in last_error:
            _offline_domains.add(domain)
        return []

    with Progress(
        SpinnerColumn(),
        "[progress.description]{task.description}",
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        console=console,
    ) as progress:
        feed_task = progress.add_task("Fetching feeds", total=len(feed_urls))
        feed_tasks = [parse_feed(url) for url in feed_urls]
        for coro in asyncio.as_completed(feed_tasks):
            urls = await coro
            all_article_urls.extend(urls)
            progress.advance(feed_task)

    unique_links = list(dict.fromkeys(all_article_urls))
    if hasattr(settings, "MAX_ARTICLES"):
        unique_links = unique_links[: settings.MAX_ARTICLES]
    console.print(f"Total unique articles to fetch: {len(unique_links)}")

    sem = asyncio.Semaphore(
        settings.MAX_CONCURRENT_REQUESTS
        if hasattr(settings, "MAX_CONCURRENT_REQUESTS")
        else 30
    )
    results: List[ArticleData] = []
    failed_count = 0
    filtered_count = 0

    async def _worker(link: str) -> None:
        nonlocal failed_count, filtered_count
        async with sem:
            for attempt in range(1, (getattr(settings, "REQUEST_RETRIES", 2) + 1)):
                try:
                    art = await asyncio.wait_for(
                        fetch_and_parse(link),
                        timeout=30,
                    )
                    if art and art.text:
                        # Apply relevance filter if configured
                        if filter_func and region and topic:
                            is_relevant_result, reason, scores = filter_func(
                                art.text, art.title, region, topic
                            )
                            if not is_relevant_result:
                                filtered_count += 1
                                logger.debug(f"[FILTER] Dropped {link} - {reason}")
                                logger.debug(f"         Scores: region={scores['region']:.2f}, topic={scores['topic']:.2f}")
                                return
                            else:
                                logger.debug(f"[KEEP] {link} - Scores: region={scores['region']:.2f}, topic={scores['topic']:.2f}")
                        
                        results.append(art)
                        return
                except asyncio.TimeoutError:
                    logger.warning(f"[article timeout attempt {attempt}] {link}")
                except Exception:
                    logger.exception(f"[article attempt {attempt}] {link}")
            failed_count += 1

    with Progress(
        SpinnerColumn(),
        "[progress.description]{task.description}",
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        console=console,
    ) as progress:
        task = progress.add_task("Downloading articles", total=len(unique_links))
        workers = [_worker(link) for link in unique_links]
        for coro in asyncio.as_completed(workers):
            await coro
            progress.advance(task)

    total_words = sum(len(art.text.split()) for art in results)
    unique_domains = len(set(urlparse(art.url).netloc for art in results))
    success_rate = len(results) / len(unique_links) if unique_links else 0

    volume_score = min(len(results) / 100, 1.0)
    diversity_score = min(unique_domains / 20, 1.0)
    word_volume_score = min(total_words / 100000, 1.0)
    confidence = (
        volume_score * 0.3
        + diversity_score * 0.2
        + success_rate * 0.2
        + word_volume_score * 0.3
    )

    stats = {
        "total": len(results),
        "attempted": len(unique_links),
        "success_rate": success_rate * 100,
        "words_collected": total_words,
        "unique_domains": unique_domains,
        "cache_hits": sum(1 for _ in content_cache.cache),
        "circuit_breakers": sum(
            1 for url in circuit_breaker.failures if circuit_breaker.is_open(url)
        ),
        "data_quality": confidence * 100,
        "filtered": filtered_count if filter_func else 0,
    }

    if not feed_urls or not results:
        console.print(
            "No articles found. Provide RSS URLs in rss_sources.txt or set RSS_SOURCES_FILE."
        )

    return results, stats


async def fetch_html(url: str) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    Fetch HTML using advanced anti-bot stack (curl_cffi → aiohttp).
    Used by the fast pipeline for concurrent fetching.
    
    Returns:
        Tuple of (html_content, metadata_dict)
    """
    meta = {
        'url': url,
        'timestamp': time.time(),
        'transport': 'unknown',
        'status_code': None,
    }
    
    # Generate random headers and profile
    profile = select_browser_profile()
    headers = shuffle_headers(generate_random_headers(profile))
    
    # Try curl_cffi first
    try:
        html = await fetch_with_curl_cffi(url, headers, profile)
        if html:
            meta['transport'] = 'curl_cffi'
            meta['status_code'] = 200
            return html, meta
    except Exception as e:
        logger.debug(f"curl_cffi failed for {url}: {e}")
    
    # Fallback to aiohttp
    try:
        connector = create_random_connector()
        timeout = aiohttp.ClientTimeout(total=10)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            async with session.get(url, headers=headers, allow_redirects=True) as response:
                meta['status_code'] = response.status
                
                if response.status == 200:
                    content = await response.read()
                    
                    # Handle compression
                    encoding = response.headers.get('Content-Encoding', '').lower()
                    if encoding and encoding in ('gzip', 'br', 'deflate'):
                        try:
                            html = await decompress_response(content, encoding)
                        except:
                            # If decompression fails, try as plain text
                            html = content.decode('utf-8', errors='ignore')
                    else:
                        html = content.decode('utf-8', errors='ignore')
                    
                    meta['transport'] = 'aiohttp'
                    return html, meta
                else:
                    return None, meta
                    
    except Exception as e:
        logger.debug(f"aiohttp failed for {url}: {e}")
        meta['error'] = str(e)
        return None, meta


def needs_js_fallback(
    html: Optional[str], 
    status: Optional[int], 
    domain: str, 
    parse_hint: str = 'ok',
    js_domains: Optional[Any] = None
) -> bool:
    """
    Determine if JS rendering is needed based on heuristics.
    Used by the fast pipeline to decide when to use Playwright.
    
    Args:
        html: HTML content (may be None or partial)
        status: HTTP status code
        domain: Domain of the URL
        parse_hint: Hint about parse quality ('ok', 'maybe_js', etc.)
        js_domains: Optional LRUSet of known JS-required domains
    
    Returns:
        True if JS rendering is recommended
    """
    # Check if domain is known to require JS
    if js_domains and domain in js_domains:
        return True
    
    # Check status code
    if status in (403, 429):
        return True  # Likely bot detection
    
    # Check HTML size (too small = likely JS-rendered)
    if html and len(html) < 1024:
        return True
    
    # Check for common JS framework indicators
    if html:
        js_indicators = [
            'window.__INITIAL_STATE__',
            'window.__PRELOADED_STATE__',
            'React.createElement',
            'angular.module',
            'Vue.component',
            '__NEXT_DATA__',
            'data-reactroot',
            'ng-app',
            'v-app',
        ]
        
        for indicator in js_indicators:
            if indicator in html:
                return True
    
    # Check parse hint
    if parse_hint == 'maybe_js':
        return True
    
    return False


async def gather_all_sources(
    feeds: Iterable[str] | None = None,
    region: Optional[str] = None,
    topic: Optional[str] = None,
) -> List[ArticleData]:
    """Compatibility wrapper returning only articles with optional filtering.
    
    Args:
        feeds: Optional list of RSS feed URLs
        region: Optional region filter (e.g., 'asia', 'europe')
        topic: Optional topic filter (e.g., 'elections', 'defense')
    """
    articles, _ = await gather_rss(feeds, region, topic)
    return articles
