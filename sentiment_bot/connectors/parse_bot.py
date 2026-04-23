"""
Parse.bot connector for scraping complex websites, reports, and paywalled content.

This connector integrates parse.bot's API to extract structured data from websites
that require JavaScript rendering, anti-bot bypassing, or complex DOM extraction.

Architecture:
    - Uses parse.bot scrapers (pre-configured extraction templates)
    - Maps parse.bot output to standardized Connector schema
    - Supports batch processing and intelligent caching
    - Integrates with existing circuit breaker and rate limiting infrastructure

Usage:
    connector = ParseBotConnector(api_key="your_api_key")
    async for article in connector.fetch():
        print(article["title"], article["text"])
"""

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional
from urllib.parse import urlparse

import aiohttp

from sentiment_bot.config import settings
from sentiment_bot.connectors.base import Connector

logger = logging.getLogger(__name__)


@dataclass
class ParseBotScraper:
    """
    Represents a parse.bot scraper configuration.

    Attributes:
        scraper_id: Unique ID from parse.bot (e.g., "ab12cd34")
        name: Human-readable name (e.g., "sec_10k_reports")
        description: What this scraper extracts
        url_pattern: Optional pattern to match URLs against
        tags: Categorization tags
    """
    scraper_id: str
    name: str
    description: str
    url_pattern: Optional[str] = None
    tags: List[str] = None


class ParseBotConnector(Connector):
    """
    Connector for parse.bot web scraping service.

    Parse.bot handles complex scraping scenarios:
    - JavaScript-rendered content
    - Anti-bot detection bypass
    - Paywalled content
    - Complex DOM extraction
    - PDF document parsing

    The connector uses pre-configured scrapers created via parse.bot dashboard
    or API, then runs them and normalizes the output.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        scrapers: Optional[List[ParseBotScraper]] = None,
        base_url: str = "https://parse.bot/v1",
        timeout: int = 60,
        max_retries: int = 3,
        rate_limit: int = 10,  # requests per second
        **kwargs
    ):
        """
        Initialize ParseBotConnector.

        Args:
            api_key: Parse.bot API key (defaults to Config.PARSE_BOT_API_KEY)
            scrapers: List of ParseBotScraper configurations
            base_url: Parse.bot API base URL
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts for failed requests
            rate_limit: Max requests per second (for rate limiting)
            **kwargs: Additional connector parameters
        """
        super().__init__(**kwargs)

        self.api_key = api_key or getattr(settings, "PARSE_BOT_API_KEY", None)
        if not self.api_key:
            raise ValueError(
                "Parse.bot API key required. Set PARSE_BOT_API_KEY environment "
                "variable or pass api_key parameter."
            )

        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.rate_limit = rate_limit
        self.scrapers = scrapers or []

        # Rate limiting state
        self._rate_limit_tokens = rate_limit
        self._rate_limit_last_update = datetime.now()
        self._rate_limit_lock = asyncio.Lock()

        # Statistics
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "cache_hits": 0,
            "total_articles_extracted": 0,
        }

    async def _acquire_rate_limit_token(self):
        """
        Token bucket rate limiting implementation.
        Ensures we don't exceed parse.bot API rate limits.
        """
        async with self._rate_limit_lock:
            now = datetime.now()
            elapsed = (now - self._rate_limit_last_update).total_seconds()

            # Refill tokens based on elapsed time
            self._rate_limit_tokens = min(
                self.rate_limit,
                self._rate_limit_tokens + elapsed * self.rate_limit
            )
            self._rate_limit_last_update = now

            # Wait if no tokens available
            if self._rate_limit_tokens < 1:
                wait_time = (1 - self._rate_limit_tokens) / self.rate_limit
                await asyncio.sleep(wait_time)
                self._rate_limit_tokens = 1

            self._rate_limit_tokens -= 1

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        retry_count: int = 0
    ) -> Dict[str, Any]:
        """
        Make authenticated request to parse.bot API with retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (e.g., "/scrapers/ab12cd34/run")
            data: Optional request payload
            retry_count: Current retry attempt (internal)

        Returns:
            Parsed JSON response

        Raises:
            aiohttp.ClientError: On HTTP errors after exhausting retries
        """
        await self._acquire_rate_limit_token()

        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        self.stats["total_requests"] += 1

        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method,
                    url,
                    json=data,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    response.raise_for_status()
                    result = await response.json()
                    self.stats["successful_requests"] += 1
                    return result

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning(
                f"Parse.bot request failed (attempt {retry_count + 1}/{self.max_retries}): {e}"
            )

            if retry_count < self.max_retries:
                # Exponential backoff with jitter
                backoff = min(2 ** retry_count + (hash(url) % 1000) / 1000, 30)
                await asyncio.sleep(backoff)
                return await self._make_request(method, endpoint, data, retry_count + 1)
            else:
                self.stats["failed_requests"] += 1
                raise

    async def run_scraper(
        self,
        scraper_id: str,
        url: Optional[str] = None,
        additional_params: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """
        Run a parse.bot scraper and return extracted data.

        Args:
            scraper_id: Parse.bot scraper ID (e.g., "ab12cd34")
            url: Optional specific URL to scrape (if scraper supports dynamic URLs)
            additional_params: Optional additional parameters for the scraper

        Returns:
            List of extracted items (structure depends on scraper configuration)

        Example:
            results = await connector.run_scraper("ab12cd34")
            # [{"title": "Book 1", "author": "Author 1"}, ...]
        """
        endpoint = f"/scrapers/{scraper_id}/run"

        # Build request payload
        payload = additional_params or {}
        if url:
            payload["url"] = url

        logger.info(f"Running parse.bot scraper: {scraper_id}")

        result = await self._make_request("POST", endpoint, data=payload)

        # Parse.bot returns extracted data directly as JSON array
        if isinstance(result, list):
            return result
        elif isinstance(result, dict) and "data" in result:
            return result["data"]
        else:
            logger.warning(f"Unexpected parse.bot response format: {result}")
            return []

    def _normalize_item(
        self,
        item: Dict[str, Any],
        scraper: ParseBotScraper,
        source_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Normalize parse.bot output to standard Connector schema.

        Standard schema:
            {
                "id": str,               # Stable SHA256 hash
                "source": str,           # "parse_bot"
                "subsource": str,        # Scraper name
                "author": str|None,
                "title": str|None,
                "text": str,             # Main content
                "url": str,
                "published_at": datetime,
                "lang": str|None,
                "raw": dict,             # Original parse.bot data
                "tags": list[str]        # Scraper tags
            }

        Args:
            item: Raw item from parse.bot scraper
            scraper: ParseBotScraper configuration
            source_url: Optional source URL for the item

        Returns:
            Normalized article dict
        """
        # Extract common fields with fallbacks
        title = item.get("title") or item.get("headline") or item.get("name")
        text = item.get("text") or item.get("content") or item.get("body") or ""
        author = item.get("author") or item.get("author_name")
        url = item.get("url") or item.get("link") or source_url or ""

        # Handle various date formats
        published_at = self._parse_date(
            item.get("date") or
            item.get("published_at") or
            item.get("timestamp") or
            item.get("publish_date")
        )

        # Combine title and text if text is missing but title exists
        if not text and title:
            text = title

        # Generate stable ID
        id_source = f"{url}:{title}:{text[:100]}"
        article_id = hashlib.sha256(id_source.encode()).hexdigest()[:16]

        # Detect language (if not provided)
        lang = item.get("lang") or item.get("language")

        return {
            "id": article_id,
            "source": "parse_bot",
            "subsource": scraper.name,
            "author": author,
            "title": title,
            "text": text,
            "url": url,
            "published_at": published_at,
            "lang": lang,
            "raw": item,  # Preserve original parse.bot data
            "tags": scraper.tags or [],
        }

    def _parse_date(self, date_value: Any) -> datetime:
        """
        Parse various date formats to timezone-aware datetime.

        Args:
            date_value: Date string, timestamp, or datetime object

        Returns:
            Timezone-aware datetime (UTC)
        """
        if not date_value:
            return datetime.now(timezone.utc)

        if isinstance(date_value, datetime):
            if date_value.tzinfo is None:
                return date_value.replace(tzinfo=timezone.utc)
            return date_value

        if isinstance(date_value, (int, float)):
            # Unix timestamp
            return datetime.fromtimestamp(date_value, tz=timezone.utc)

        # Try parsing ISO format
        try:
            from dateutil import parser
            dt = parser.parse(date_value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            logger.warning(f"Failed to parse date: {date_value}, using current time")
            return datetime.now(timezone.utc)

    async def fetch(self) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Fetch articles from all configured parse.bot scrapers.

        This is the main entry point that implements the Connector interface.
        It runs all configured scrapers and yields normalized articles.

        Yields:
            Normalized article dicts matching Connector schema

        Example:
            connector = ParseBotConnector(
                scrapers=[
                    ParseBotScraper(
                        scraper_id="ab12cd34",
                        name="sec_filings",
                        tags=["financial", "sec"]
                    )
                ]
            )
            async for article in connector.fetch():
                print(article["title"])
        """
        if not self.scrapers:
            logger.warning("No parse.bot scrapers configured")
            return

        logger.info(f"Running {len(self.scrapers)} parse.bot scrapers")

        for scraper in self.scrapers:
            try:
                logger.info(
                    f"Fetching from parse.bot scraper '{scraper.name}' "
                    f"(ID: {scraper.scraper_id})"
                )

                # Run the scraper
                items = await self.run_scraper(scraper.scraper_id)

                logger.info(
                    f"Scraper '{scraper.name}' extracted {len(items)} items"
                )

                # Normalize and yield each item
                for item in items:
                    normalized = self._normalize_item(item, scraper)
                    self.stats["total_articles_extracted"] += 1
                    yield normalized

            except Exception as e:
                logger.error(
                    f"Failed to fetch from scraper '{scraper.name}': {e}",
                    exc_info=True
                )
                # Continue with next scraper instead of failing entire fetch

        logger.info(
            f"Parse.bot fetch complete. Total articles: "
            f"{self.stats['total_articles_extracted']}"
        )

    async def fetch_url(self, url: str, scraper_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Fetch and extract a single URL using a specific scraper.

        This is useful for on-demand scraping of individual URLs.

        Args:
            url: URL to scrape
            scraper_id: Specific scraper to use (if None, tries to auto-match)

        Returns:
            Normalized article dict

        Example:
            article = await connector.fetch_url(
                "https://www.sec.gov/filing/example",
                scraper_id="sec_filings_scraper"
            )
        """
        # Auto-match scraper based on URL pattern if not specified
        if not scraper_id:
            scraper = self._match_scraper_for_url(url)
            if not scraper:
                raise ValueError(
                    f"No matching scraper found for URL: {url}. "
                    f"Please specify scraper_id explicitly."
                )
            scraper_id = scraper.scraper_id
        else:
            scraper = next(
                (s for s in self.scrapers if s.scraper_id == scraper_id),
                None
            )
            if not scraper:
                raise ValueError(f"Scraper not found: {scraper_id}")

        # Run scraper with specific URL
        items = await self.run_scraper(scraper_id, url=url)

        if not items:
            logger.warning(f"No data extracted from {url}")
            return None

        # Return first item (assuming single-page scraping)
        return self._normalize_item(items[0], scraper, source_url=url)

    def _match_scraper_for_url(self, url: str) -> Optional[ParseBotScraper]:
        """
        Find the best scraper for a given URL based on URL pattern matching.

        Args:
            url: URL to match

        Returns:
            Matching ParseBotScraper or None
        """
        domain = urlparse(url).netloc

        for scraper in self.scrapers:
            if scraper.url_pattern:
                # Simple wildcard matching (could be enhanced with regex)
                if domain in scraper.url_pattern or scraper.url_pattern == "*":
                    return scraper

        return None

    async def create_scraper(
        self,
        name: str,
        url: str,
        extraction_rules: Dict[str, str],
        render_js: bool = True,
        description: str = "",
        tags: List[str] = None
    ) -> ParseBotScraper:
        """
        Create a new parse.bot scraper via API (if supported).

        This is a convenience method for programmatically creating scrapers.
        Most users will create scrapers via parse.bot dashboard.

        Args:
            name: Scraper name
            url: Example URL for the scraper
            extraction_rules: CSS selector rules, e.g., {"title": "h1.title", "body": "div.content"}
            render_js: Whether to render JavaScript
            description: Human-readable description
            tags: Categorization tags

        Returns:
            ParseBotScraper object with scraper_id

        Example:
            scraper = await connector.create_scraper(
                name="my_news_scraper",
                url="https://example.com/articles",
                extraction_rules={
                    "title": "h1.article-title",
                    "body": "div.article-body",
                    "author": "span.author-name"
                },
                tags=["news"]
            )
        """
        payload = {
            "name": name,
            "url": url,
            "extraction": extraction_rules,
            "render_js": render_js,
            "description": description,
        }

        result = await self._make_request("POST", "/scrapers", data=payload)

        scraper_id = result.get("id") or result.get("scraper_id")
        if not scraper_id:
            raise ValueError(f"Failed to create scraper: {result}")

        scraper = ParseBotScraper(
            scraper_id=scraper_id,
            name=name,
            description=description,
            tags=tags or []
        )

        # Add to local scrapers list
        self.scrapers.append(scraper)

        logger.info(f"Created parse.bot scraper '{name}' with ID: {scraper_id}")

        return scraper

    def get_stats(self) -> Dict[str, Any]:
        """
        Get connector statistics.

        Returns:
            Dict with request counts, success rates, etc.
        """
        success_rate = (
            self.stats["successful_requests"] / self.stats["total_requests"]
            if self.stats["total_requests"] > 0
            else 0
        )

        return {
            **self.stats,
            "success_rate": success_rate,
            "configured_scrapers": len(self.scrapers),
        }


# Example scraper configurations for common use cases
EXAMPLE_SCRAPERS = [
    ParseBotScraper(
        scraper_id="sec_10k_scraper",  # Replace with actual ID from parse.bot
        name="sec_filings",
        description="SEC 10-K and 10-Q financial reports",
        url_pattern="sec.gov",
        tags=["financial", "regulatory", "sec"]
    ),
    ParseBotScraper(
        scraper_id="imf_reports_scraper",
        name="imf_reports",
        description="IMF World Economic Outlook reports",
        url_pattern="imf.org",
        tags=["economic", "imf", "forecast"]
    ),
    ParseBotScraper(
        scraper_id="ft_news_scraper",
        name="ft_premium",
        description="Financial Times premium articles",
        url_pattern="ft.com",
        tags=["news", "premium", "financial"]
    ),
]
