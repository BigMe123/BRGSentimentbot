"""
Optimized HTTP client with connection pooling, DNS caching, and byte caps.
Implements Phase 1 of the performance optimization plan.
"""

import asyncio
import time
import logging
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urlparse
import aiohttp
from aiohttp import ClientTimeout, TCPConnector, DummyCookieJar
import aiodns
from aiohttp_client_cache import CachedSession, SQLiteBackend
import hashlib
import random

logger = logging.getLogger(__name__)


class OptimizedHTTPClient:
    """
    High-performance HTTP client with:
    - Connection pooling & keep-alive
    - DNS caching (5 min TTL)
    - Global and per-domain concurrency limits
    - Byte caps and streaming
    - Compression support
    - ETag/Last-Modified caching
    """

    def __init__(
        self,
        global_concurrency: int = 64,
        per_domain_limit: int = 6,
        total_timeout: int = 10,
        connect_timeout: int = 5,
        max_response_size: int = 2_621_440,  # 2.5MB
        dns_ttl: int = 300,  # 5 minutes
        enable_http2: bool = True,
    ):
        self.global_concurrency = global_concurrency
        self.per_domain_limit = per_domain_limit
        self.total_timeout = total_timeout
        self.connect_timeout = connect_timeout
        self.max_response_size = max_response_size
        self.dns_ttl = dns_ttl
        self.enable_http2 = enable_http2

        # Per-domain semaphores
        self.domain_semaphores: Dict[str, asyncio.Semaphore] = {}
        self.global_semaphore = asyncio.Semaphore(global_concurrency)

        # DNS cache
        self.dns_cache: Dict[str, Tuple[str, float]] = {}

        # ETag/Last-Modified cache
        self.etag_cache: Dict[str, Dict[str, str]] = {}

        # Circuit breaker state
        self.circuit_breakers: Dict[str, Dict[str, Any]] = {}

        # Stats
        self.stats = {
            "requests": 0,
            "successes": 0,
            "timeouts": 0,
            "errors": 0,
            "bytes_downloaded": 0,
            "cache_hits": 0,
            "circuit_opens": 0,
        }

        # Session (created on first use)
        self._session: Optional[aiohttp.ClientSession] = None
        self._connector: Optional[TCPConnector] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the HTTP session with optimized settings."""
        if self._session is None or self._session.closed:
            # Create optimized connector
            self._connector = TCPConnector(
                limit=self.global_concurrency,
                limit_per_host=self.per_domain_limit,
                ttl_dns_cache=self.dns_ttl,
                enable_cleanup_closed=True,
                force_close=False,  # Keep connections alive
                keepalive_timeout=30,
                use_dns_cache=True,
            )

            # Timeout configuration
            timeout = ClientTimeout(
                total=self.total_timeout,
                connect=self.connect_timeout,
                sock_connect=self.connect_timeout,
                sock_read=self.total_timeout,
            )

            # Create session with compression and connection pooling
            self._session = aiohttp.ClientSession(
                connector=self._connector,
                timeout=timeout,
                cookie_jar=DummyCookieJar(),  # Don't store cookies
                headers={
                    "Accept-Encoding": "gzip, deflate, br",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "User-Agent": self._get_random_user_agent(),
                    "Cache-Control": "max-age=0",
                    "DNT": "1",
                },
                trust_env=True,
                auto_decompress=True,  # Auto handle compression
            )

            # Warm up the connection pool
            await self._warm_up_connections()

        return self._session

    async def _warm_up_connections(self):
        """Pre-open a few connections to popular domains."""
        warm_up_domains = [
            "feeds.bbci.co.uk",
            "rss.nytimes.com",
            "feeds.reuters.com",
        ]

        tasks = []
        for domain in warm_up_domains[:3]:  # Limit warm-up
            task = self._ping_domain(domain)
            tasks.append(task)

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.debug(f"Warmed up {len(tasks)} connections")

    async def _ping_domain(self, domain: str):
        """Ping a domain to establish connection."""
        try:
            session = await self._get_session()
            async with session.head(f"https://{domain}", timeout=2) as resp:
                pass
        except:
            pass  # Ignore warm-up failures

    def _get_random_user_agent(self) -> str:
        """Get a random user agent for diversity."""
        agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
        ]
        return random.choice(agents)

    def _get_domain_semaphore(self, domain: str) -> asyncio.Semaphore:
        """Get or create per-domain semaphore."""
        if domain not in self.domain_semaphores:
            self.domain_semaphores[domain] = asyncio.Semaphore(self.per_domain_limit)
        return self.domain_semaphores[domain]

    def _is_circuit_open(self, domain: str) -> bool:
        """Check if circuit breaker is open for domain."""
        if domain not in self.circuit_breakers:
            return False

        cb = self.circuit_breakers[domain]
        if cb["state"] == "open":
            # Check if cooldown period has passed
            if time.time() - cb["opened_at"] > 60:  # 1 minute cooldown
                cb["state"] = "half_open"
                cb["failures"] = 0
                return False
            return True
        return False

    def _record_failure(self, domain: str, reason: str):
        """Record a failure for circuit breaker."""
        if domain not in self.circuit_breakers:
            self.circuit_breakers[domain] = {
                "state": "closed",
                "failures": 0,
                "last_failure": None,
                "opened_at": None,
            }

        cb = self.circuit_breakers[domain]
        cb["failures"] += 1
        cb["last_failure"] = reason

        # Open circuit after 3 consecutive failures
        if cb["failures"] >= 3:
            cb["state"] = "open"
            cb["opened_at"] = time.time()
            self.stats["circuit_opens"] += 1
            logger.warning(
                f"Circuit breaker opened for {domain} after {cb['failures']} failures"
            )

    def _record_success(self, domain: str):
        """Record a success for circuit breaker."""
        if domain in self.circuit_breakers:
            self.circuit_breakers[domain]["failures"] = 0
            if self.circuit_breakers[domain]["state"] == "half_open":
                self.circuit_breakers[domain]["state"] = "closed"

    async def fetch(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        use_cache: bool = True,
        stream_chunks: bool = True,
    ) -> Tuple[Optional[bytes], Dict[str, Any]]:
        """
        Fetch URL with all optimizations.

        Returns:
            Tuple of (content_bytes, metadata_dict)
        """
        domain = urlparse(url).netloc

        # Check circuit breaker
        if self._is_circuit_open(domain):
            logger.debug(f"Circuit breaker open for {domain}, skipping")
            return None, {
                "status": "circuit_open",
                "domain": domain,
                "url": url,
            }

        # Get semaphores
        domain_sem = self._get_domain_semaphore(domain)

        # Stats tracking
        start_time = time.time()
        self.stats["requests"] += 1

        async with self.global_semaphore:
            async with domain_sem:
                try:
                    session = await self._get_session()

                    # Prepare headers with conditional request
                    req_headers = headers or {}
                    if use_cache and url in self.etag_cache:
                        cached = self.etag_cache[url]
                        if "etag" in cached:
                            req_headers["If-None-Match"] = cached["etag"]
                        if "last_modified" in cached:
                            req_headers["If-Modified-Since"] = cached["last_modified"]

                    # Make request
                    async with session.get(
                        url, headers=req_headers, allow_redirects=True
                    ) as response:
                        # Handle 304 Not Modified
                        if response.status == 304:
                            self.stats["cache_hits"] += 1
                            logger.debug(f"Cache hit (304) for {url}")
                            return None, {
                                "status": "unchanged_etag",
                                "cached": True,
                                "domain": domain,
                                "url": url,
                            }

                        # Check status
                        if response.status >= 400:
                            self._record_failure(domain, f"HTTP {response.status}")
                            return None, {
                                "status": f"http_{response.status}",
                                "domain": domain,
                                "url": url,
                            }

                        # Update cache validators
                        if use_cache:
                            cache_entry = {}
                            if "ETag" in response.headers:
                                cache_entry["etag"] = response.headers["ETag"]
                            if "Last-Modified" in response.headers:
                                cache_entry["last_modified"] = response.headers[
                                    "Last-Modified"
                                ]
                            if cache_entry:
                                self.etag_cache[url] = cache_entry

                        # Stream content with byte cap
                        content = b""
                        bytes_read = 0

                        if stream_chunks:
                            async for chunk in response.content.iter_chunked(
                                65536
                            ):  # 64KB chunks
                                content += chunk
                                bytes_read += len(chunk)

                                if bytes_read > self.max_response_size:
                                    logger.warning(
                                        f"Response size exceeded {self.max_response_size} bytes for {url}"
                                    )
                                    break
                        else:
                            content = await response.read()
                            bytes_read = len(content)

                        # Record success
                        self._record_success(domain)
                        self.stats["successes"] += 1
                        self.stats["bytes_downloaded"] += bytes_read

                        elapsed = time.time() - start_time

                        return content, {
                            "status": "ok",
                            "status_code": response.status,
                            "content_type": response.headers.get("Content-Type", ""),
                            "content_length": bytes_read,
                            "elapsed_ms": int(elapsed * 1000),
                            "domain": domain,
                            "url": url,
                            "cached": False,
                        }

                except asyncio.TimeoutError:
                    self.stats["timeouts"] += 1
                    self._record_failure(domain, "timeout")
                    logger.debug(f"Timeout fetching {url}")
                    return None, {
                        "status": "timeout",
                        "domain": domain,
                        "url": url,
                    }

                except Exception as e:
                    self.stats["errors"] += 1
                    self._record_failure(domain, str(e))
                    logger.debug(f"Error fetching {url}: {e}")
                    return None, {
                        "status": "error",
                        "error": str(e),
                        "domain": domain,
                        "url": url,
                    }

    async def fetch_batch(
        self, urls: list[str]
    ) -> list[Tuple[Optional[bytes], Dict[str, Any]]]:
        """Fetch multiple URLs concurrently."""
        tasks = [self.fetch(url) for url in urls]
        return await asyncio.gather(*tasks)

    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics."""
        stats = self.stats.copy()
        if stats["requests"] > 0:
            stats["success_rate"] = stats["successes"] / stats["requests"]
            stats["timeout_rate"] = stats["timeouts"] / stats["requests"]
            stats["error_rate"] = stats["errors"] / stats["requests"]
            stats["cache_hit_rate"] = stats["cache_hits"] / stats["requests"]

        stats["open_circuits"] = sum(
            1 for cb in self.circuit_breakers.values() if cb["state"] == "open"
        )

        return stats

    async def close(self):
        """Close the HTTP client and clean up."""
        if self._session:
            await self._session.close()
        if self._connector:
            await self._connector.close()

        logger.info(f"HTTP client closed. Stats: {self.get_stats()}")


# Global client instance for reuse
_global_client: Optional[OptimizedHTTPClient] = None


async def get_http_client() -> OptimizedHTTPClient:
    """Get or create the global HTTP client."""
    global _global_client
    if _global_client is None:
        _global_client = OptimizedHTTPClient()
    return _global_client


async def close_http_client():
    """Close the global HTTP client."""
    global _global_client
    if _global_client:
        await _global_client.close()
        _global_client = None
