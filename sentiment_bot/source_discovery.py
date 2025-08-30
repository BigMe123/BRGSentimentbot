"""
Source Discovery Engine - Finds new sources for obscure topics.
Includes RSS autodiscovery, sitemap parsing, and limited crawling.
"""

import asyncio
import aiohttp
import feedparser
import re
import logging
from typing import List, Dict, Any, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from dataclasses import dataclass
import time

from .skb_catalog import SourceRecord, get_catalog

logger = logging.getLogger(__name__)


@dataclass
class DiscoveryResult:
    """Result from source discovery."""

    url: str
    domain: str
    feed_type: str  # "rss", "atom", "sitemap"
    title: Optional[str] = None
    description: Optional[str] = None
    topics: List[str] = None
    language: Optional[str] = None
    discovery_method: str = "autodiscovery"
    confidence: float = 0.5


class SourceDiscovery:
    """Discovers new sources through various methods."""

    # Patterns for finding RSS/Atom feeds
    RSS_LINK_PATTERNS = [
        r'<link[^>]*type="application/rss\+xml"[^>]*href="([^"]+)"',
        r'<link[^>]*type="application/atom\+xml"[^>]*href="([^"]+)"',
        r'<link[^>]*rel="alternate"[^>]*type="application/rss\+xml"[^>]*href="([^"]+)"',
        r'<a[^>]*href="([^"]*\.xml)"[^>]*>.*?(?:RSS|Feed|Subscribe)',
        r'<a[^>]*href="([^"]*feed[^"]*)"[^>]*>',
        r'<a[^>]*href="([^"]*rss[^"]*)"[^>]*>',
    ]

    # Common RSS paths to try
    COMMON_RSS_PATHS = [
        "/rss",
        "/rss.xml",
        "/feed",
        "/feed.xml",
        "/feeds",
        "/atom.xml",
        "/index.xml",
        "/feed/rss",
        "/rss/feed",
        "/news/rss",
        "/blog/rss",
        "/articles/rss",
    ]

    # Sitemap paths
    SITEMAP_PATHS = [
        "/sitemap.xml",
        "/sitemap_index.xml",
        "/news-sitemap.xml",
        "/sitemap_news.xml",
        "/sitemaps/sitemap.xml",
    ]

    def __init__(
        self,
        max_concurrent: int = 5,
        timeout: int = 10,
        max_domains: int = 20,
        max_pages: int = 100,
    ):
        self.max_concurrent = max_concurrent
        self.timeout = timeout
        self.max_domains = max_domains
        self.max_pages = max_pages
        self.pages_fetched = 0
        self.domains_discovered = set()
        self.catalog = get_catalog()

    async def discover_sources(
        self,
        topic: str,
        region: Optional[str] = None,
        seed_urls: Optional[List[str]] = None,
        time_budget: float = 30.0,
    ) -> List[DiscoveryResult]:
        """
        Discover new sources for a topic within time budget.

        Args:
            topic: Topic to search for
            region: Optional region constraint
            seed_urls: Optional starting URLs
            time_budget: Maximum time in seconds
        """
        start_time = time.time()
        results = []

        # Normalize topic
        topic_keywords = self._extract_keywords(topic)

        # Build seed URLs if not provided
        if not seed_urls:
            seed_urls = self._generate_seed_urls(topic, region)

        logger.info(f"Starting discovery for '{topic}' with {len(seed_urls)} seed URLs")

        # Create HTTP session
        timeout_config = aiohttp.ClientTimeout(total=self.timeout)
        async with aiohttp.ClientSession(timeout=timeout_config) as session:
            # Process seed URLs
            tasks = []
            for url in seed_urls[: self.max_domains]:
                if time.time() - start_time > time_budget:
                    break

                tasks.append(
                    self._discover_from_url(session, url, topic_keywords, region)
                )

            # Gather results
            discovered = await asyncio.gather(*tasks, return_exceptions=True)

            for result in discovered:
                if isinstance(result, Exception):
                    logger.debug(f"Discovery error: {result}")
                    continue

                if result:
                    if isinstance(result, list):
                        results.extend(result)
                    else:
                        results.append(result)

        # Deduplicate and score results
        unique_results = self._deduplicate_results(results)
        scored_results = self._score_results(unique_results, topic_keywords, region)

        logger.info(
            f"Discovered {len(scored_results)} potential sources in "
            f"{time.time() - start_time:.1f}s"
        )

        return scored_results

    async def _discover_from_url(
        self,
        session: aiohttp.ClientSession,
        url: str,
        topic_keywords: Set[str],
        region: Optional[str],
    ) -> List[DiscoveryResult]:
        """Discover feeds from a single URL."""

        if self.pages_fetched >= self.max_pages:
            return []

        domain = urlparse(url).netloc
        if domain in self.domains_discovered:
            return []

        self.domains_discovered.add(domain)
        results = []

        try:
            # Try RSS autodiscovery first
            feeds = await self._autodiscover_feeds(session, url)
            for feed_url, feed_type in feeds:
                # Validate feed is relevant
                if await self._validate_feed(session, feed_url, topic_keywords):
                    results.append(
                        DiscoveryResult(
                            url=feed_url,
                            domain=domain,
                            feed_type=feed_type,
                            topics=list(topic_keywords),
                            discovery_method="autodiscovery",
                            confidence=0.7,
                        )
                    )

            # If no feeds found, try common paths
            if not results:
                for path in self.COMMON_RSS_PATHS[:5]:
                    feed_url = urljoin(url, path)
                    if await self._check_feed_exists(session, feed_url):
                        if await self._validate_feed(session, feed_url, topic_keywords):
                            results.append(
                                DiscoveryResult(
                                    url=feed_url,
                                    domain=domain,
                                    feed_type="rss",
                                    topics=list(topic_keywords),
                                    discovery_method="common_path",
                                    confidence=0.5,
                                )
                            )
                            break

            # Try sitemap if still no results
            if not results and self.pages_fetched < self.max_pages - 10:
                sitemap_feeds = await self._discover_from_sitemap(
                    session, url, topic_keywords
                )
                results.extend(sitemap_feeds)

        except Exception as e:
            logger.debug(f"Error discovering from {url}: {e}")

        return results

    async def _autodiscover_feeds(
        self, session: aiohttp.ClientSession, url: str
    ) -> List[Tuple[str, str]]:
        """Autodiscover RSS/Atom feeds from HTML page."""
        feeds = []

        try:
            async with session.get(url) as response:
                if response.status != 200:
                    return feeds

                html = await response.text()
                self.pages_fetched += 1

                # Look for feed links in HTML
                for pattern in self.RSS_LINK_PATTERNS:
                    matches = re.findall(pattern, html, re.IGNORECASE)
                    for match in matches:
                        feed_url = urljoin(url, match)
                        feed_type = "atom" if "atom" in match.lower() else "rss"
                        feeds.append((feed_url, feed_type))

                # Parse with BeautifulSoup for more thorough search
                if not feeds and len(html) < 500000:  # Limit parsing large pages
                    soup = BeautifulSoup(html, "html.parser")

                    # Look for link tags
                    for link in soup.find_all(
                        "link", type=re.compile(r"application/(rss|atom)\+xml")
                    ):
                        href = link.get("href")
                        if href:
                            feed_url = urljoin(url, href)
                            feed_type = (
                                "atom" if "atom" in link.get("type", "") else "rss"
                            )
                            feeds.append((feed_url, feed_type))

                    # Look for RSS links in anchors
                    for a in soup.find_all(
                        "a", href=re.compile(r"(rss|feed|atom)", re.I)
                    ):
                        href = a.get("href")
                        if href:
                            feed_url = urljoin(url, href)
                            feeds.append((feed_url, "rss"))

        except Exception as e:
            logger.debug(f"Autodiscovery error for {url}: {e}")

        return feeds[:10]  # Limit to 10 feeds per page

    async def _check_feed_exists(
        self, session: aiohttp.ClientSession, url: str
    ) -> bool:
        """Check if a URL is a valid feed."""
        try:
            async with session.head(url) as response:
                if response.status == 200:
                    content_type = response.headers.get("Content-Type", "")
                    return any(
                        t in content_type.lower() for t in ["xml", "rss", "atom"]
                    )
        except:
            pass

        return False

    async def _validate_feed(
        self, session: aiohttp.ClientSession, feed_url: str, topic_keywords: Set[str]
    ) -> bool:
        """Validate that a feed is relevant to the topic."""
        try:
            async with session.get(feed_url) as response:
                if response.status != 200:
                    return False

                content = await response.text()
                self.pages_fetched += 1

                # Quick relevance check
                content_lower = content.lower()
                matches = sum(
                    1 for keyword in topic_keywords if keyword.lower() in content_lower
                )

                # Need at least 20% keyword match
                return matches >= len(topic_keywords) * 0.2

        except:
            return False

    async def _discover_from_sitemap(
        self, session: aiohttp.ClientSession, base_url: str, topic_keywords: Set[str]
    ) -> List[DiscoveryResult]:
        """Discover feeds from sitemap."""
        results = []
        domain = urlparse(base_url).netloc

        for sitemap_path in self.SITEMAP_PATHS[:3]:
            if self.pages_fetched >= self.max_pages:
                break

            sitemap_url = urljoin(base_url, sitemap_path)

            try:
                async with session.get(sitemap_url) as response:
                    if response.status != 200:
                        continue

                    content = await response.text()
                    self.pages_fetched += 1

                    # Parse sitemap
                    root = ET.fromstring(content)

                    # Look for news sections
                    for url_elem in root.findall(
                        ".//{http://www.sitemaps.org/schemas/sitemap/0.9}url"
                    ):
                        loc = url_elem.find(
                            "{http://www.sitemaps.org/schemas/sitemap/0.9}loc"
                        )
                        if loc is not None and loc.text:
                            url_text = loc.text.lower()

                            # Check if URL might be news-related
                            if any(
                                term in url_text
                                for term in ["news", "article", "blog", "press"]
                            ):
                                # Check for topic relevance
                                if any(
                                    keyword.lower() in url_text
                                    for keyword in topic_keywords
                                ):
                                    results.append(
                                        DiscoveryResult(
                                            url=loc.text,
                                            domain=domain,
                                            feed_type="sitemap",
                                            topics=list(topic_keywords),
                                            discovery_method="sitemap",
                                            confidence=0.4,
                                        )
                                    )

                    if results:
                        break  # Found relevant content

            except Exception as e:
                logger.debug(f"Sitemap error for {sitemap_url}: {e}")

        return results[:20]  # Limit results per sitemap

    def _extract_keywords(self, topic: str) -> Set[str]:
        """Extract keywords from topic string."""
        # Normalize and split
        words = re.findall(r"\w+", topic.lower())

        # Remove common stopwords
        stopwords = {
            "the",
            "in",
            "of",
            "and",
            "or",
            "for",
            "with",
            "on",
            "at",
            "to",
            "from",
            "by",
            "about",
            "into",
            "through",
            "during",
            "before",
            "after",
            "above",
            "below",
            "between",
            "under",
        }

        keywords = {w for w in words if w not in stopwords and len(w) > 2}

        # Add some variations
        variations = set()
        for keyword in keywords:
            # Add plural/singular variations
            if keyword.endswith("s"):
                variations.add(keyword[:-1])
            else:
                variations.add(keyword + "s")

        keywords.update(variations)

        return keywords

    def _generate_seed_urls(self, topic: str, region: Optional[str]) -> List[str]:
        """Generate seed URLs for discovery based on topic and region."""
        seed_urls = []

        # Region-specific news aggregators
        region_seeds = {
            "asia": [
                "https://asia.nikkei.com",
                "https://www.scmp.com",
                "https://www.straitstimes.com",
                "https://www.bangkokpost.com",
            ],
            "middle_east": [
                "https://www.aljazeera.com",
                "https://www.middleeasteye.net",
                "https://www.arabnews.com",
                "https://www.haaretz.com",
            ],
            "europe": [
                "https://www.euronews.com",
                "https://www.politico.eu",
                "https://www.dw.com",
                "https://www.france24.com",
            ],
            "americas": [
                "https://www.reuters.com",
                "https://apnews.com",
                "https://www.npr.org",
                "https://www.cbc.ca",
            ],
            "africa": [
                "https://allafrica.com",
                "https://www.africanews.com",
                "https://mg.co.za",
                "https://www.thenewhumanitarian.org",
            ],
        }

        if region and region in region_seeds:
            seed_urls.extend(region_seeds[region])

        # Topic-specific seeds
        topic_lower = topic.lower()
        if "tech" in topic_lower or "semiconductor" in topic_lower:
            seed_urls.extend(
                [
                    "https://www.theverge.com",
                    "https://arstechnica.com",
                    "https://www.wired.com",
                ]
            )
        elif "energy" in topic_lower:
            seed_urls.extend(
                [
                    "https://www.energy.gov",
                    "https://oilprice.com",
                    "https://www.renewable-energy-world.com",
                ]
            )
        elif "climate" in topic_lower:
            seed_urls.extend(
                ["https://www.climatechangenews.com", "https://insideclimatenews.org"]
            )

        # Add general news sites if not enough seeds
        if len(seed_urls) < 5:
            seed_urls.extend(
                [
                    "https://www.bbc.com",
                    "https://www.theguardian.com",
                    "https://www.nytimes.com",
                ]
            )

        return seed_urls[: self.max_domains]

    def _deduplicate_results(
        self, results: List[DiscoveryResult]
    ) -> List[DiscoveryResult]:
        """Deduplicate discovery results."""
        seen = set()
        unique = []

        for result in results:
            key = (result.domain, result.url)
            if key not in seen:
                seen.add(key)
                unique.append(result)

        return unique

    def _score_results(
        self,
        results: List[DiscoveryResult],
        topic_keywords: Set[str],
        region: Optional[str],
    ) -> List[DiscoveryResult]:
        """Score and rank discovery results."""

        for result in results:
            score = result.confidence

            # Boost for discovery method
            if result.discovery_method == "autodiscovery":
                score *= 1.2
            elif result.discovery_method == "common_path":
                score *= 1.0
            else:  # sitemap
                score *= 0.8

            # Boost for feed type
            if result.feed_type in ["rss", "atom"]:
                score *= 1.1

            # Update confidence
            result.confidence = min(1.0, score)

        # Sort by confidence
        results.sort(key=lambda x: x.confidence, reverse=True)

        return results

    async def add_to_catalog(self, results: List[DiscoveryResult], region: str):
        """Add discovered sources to the catalog as staging entries."""
        added = 0

        for result in results:
            source = SourceRecord(
                domain=result.domain,
                name=result.title or result.domain,
                region=region or "global",
                languages=["en"],  # Default, will be updated later
                topics=result.topics or [],
                rss_endpoints=(
                    [result.url] if result.feed_type in ["rss", "atom"] else []
                ),
                sitemap_endpoints=[result.url] if result.feed_type == "sitemap" else [],
                priority=0.3,  # Start with low priority
                policy="allow",
                discovery_method=result.discovery_method,
                validation_status="staging",
            )

            if self.catalog.add_discovered_source(source):
                added += 1

        logger.info(f"Added {added} discovered sources to staging")
        return added
