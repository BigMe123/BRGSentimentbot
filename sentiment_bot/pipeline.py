"""
High-throughput 3-stage async pipeline for concurrent fetching, rendering, and NLP.
Maintains all anti-bot features while drastically improving performance.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import AsyncIterator, Dict, List, Optional, Set, Any
from urllib.parse import urlparse
from collections import OrderedDict
import logging

logger = logging.getLogger(__name__)


@dataclass
class FetchItem:
    """Item queued for fetching."""
    url: str
    domain: str
    feed_meta: dict = field(default_factory=dict)
    retry_count: int = 0
    timestamp: float = field(default_factory=time.time)


@dataclass
class RenderItem:
    """Item queued for JS rendering."""
    url: str
    domain: str
    reason: str  # 'tiny_html' | 'blocked_403' | 'parse_failed' | 'known_js'
    html_partial: Optional[str] = None
    meta: dict = field(default_factory=dict)


@dataclass
class ArticleResult:
    """Final processed article with all metadata."""
    url: str
    title: str
    text: str
    published: Optional[str] = None
    transport: str = ""  # 'curl_cffi' | 'aiohttp' | 'playwright'
    timing_ms: dict = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    domain: str = ""
    word_count: int = 0
    sentiment_scores: dict = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.domain and self.url:
            self.domain = urlparse(self.url).netloc
        if self.text:
            self.word_count = len(self.text.split())


class LRUSet:
    """LRU set for tracking JS-required domains."""
    
    def __init__(self, maxsize: int = 200):
        self.maxsize = maxsize
        self._data: OrderedDict[str, None] = OrderedDict()
    
    def add(self, item: str):
        """Add item to set, evicting LRU if at capacity."""
        if item in self._data:
            self._data.move_to_end(item)
        else:
            self._data[item] = None
            if len(self._data) > self.maxsize:
                self._data.popitem(last=False)
    
    def __contains__(self, item: str) -> bool:
        """Check if item is in set (and update recency)."""
        if item in self._data:
            self._data.move_to_end(item)
            return True
        return False


class PipelineOrchestrator:
    """
    Orchestrates 3-stage pipeline:
    1. Fetch (curl_cffi/aiohttp)
    2. Render (Playwright for JS-required)
    3. Parse+NLP (extract & analyze)
    """
    
    def __init__(
        self,
        max_concurrency: int = 200,
        per_domain: int = 3,
        fetch_workers: int = 100,
        render_workers: int = 6,
        parse_workers: int = 8,
    ):
        self.max_concurrency = max_concurrency
        self.per_domain = per_domain
        self.fetch_workers = min(fetch_workers, max_concurrency)
        self.render_workers = render_workers
        self.parse_workers = parse_workers
        
        # Queues for pipeline stages
        self.fetch_queue: asyncio.Queue[Optional[FetchItem]] = asyncio.Queue()
        self.render_queue: asyncio.Queue[Optional[RenderItem]] = asyncio.Queue()
        self.parse_queue: asyncio.Queue[Optional[tuple]] = asyncio.Queue()
        self.result_queue: asyncio.Queue[Optional[ArticleResult]] = asyncio.Queue()
        
        # Domain management
        self.domain_semaphores: Dict[str, asyncio.Semaphore] = {}
        self.js_domains = LRUSet(maxsize=200)
        
        # Stats
        self.stats = {
            'fetched': 0,
            'rendered': 0,
            'parsed': 0,
            'errors': 0,
            'start_time': time.time(),
        }
        
        # Workers
        self.workers: List[asyncio.Task] = []
        self.playwright_pool = None
        
    def get_domain_semaphore(self, domain: str) -> asyncio.Semaphore:
        """Get or create per-domain semaphore."""
        if domain not in self.domain_semaphores:
            self.domain_semaphores[domain] = asyncio.Semaphore(self.per_domain)
            logger.debug(f"[PIPELINE] Domain semaphore for {domain}: max {self.per_domain}")
        return self.domain_semaphores[domain]
    
    async def fetch_worker(self):
        """Worker for fetch stage."""
        from .fetcher import fetch_html, needs_js_fallback
        
        while True:
            item = await self.fetch_queue.get()
            if item is None:  # Poison pill
                break
            
            start_time = time.time()
            domain_sem = self.get_domain_semaphore(item.domain)
            
            async with domain_sem:
                try:
                    # Use advanced fetch logic (curl_cffi → aiohttp)
                    html, meta = await fetch_html(item.url)
                    fetch_ms = int((time.time() - start_time) * 1000)
                    
                    # Check if JS rendering needed
                    status = meta.get('status_code', 200)
                    
                    if needs_js_fallback(
                        html, status, item.domain, 
                        parse_hint='maybe_js' if not html or len(html) < 1024 else 'ok',
                        js_domains=self.js_domains
                    ):
                        # Queue for JS rendering
                        reason = (
                            'tiny_html' if html and len(html) < 1024 else
                            'blocked_403' if status in (403, 429) else
                            'known_js' if item.domain in self.js_domains else
                            'parse_failed'
                        )
                        
                        render_item = RenderItem(
                            url=item.url,
                            domain=item.domain,
                            reason=reason,
                            html_partial=html,
                            meta={**meta, 'fetch_ms': fetch_ms}
                        )
                        await self.render_queue.put(render_item)
                        self.js_domains.add(item.domain)
                        logger.debug(f"[FETCH] {item.domain} needs JS: {reason}")
                    else:
                        # Direct to parse
                        await self.parse_queue.put((
                            item.url, html, meta.get('transport', 'unknown'),
                            {'fetch_ms': fetch_ms}, []
                        ))
                        self.stats['fetched'] += 1
                        
                except Exception as e:
                    logger.error(f"[FETCH] Error for {item.url}: {e}")
                    self.stats['errors'] += 1
                    # Still try to parse even with error
                    await self.parse_queue.put((
                        item.url, None, 'error',
                        {'fetch_ms': int((time.time() - start_time) * 1000)},
                        [str(e)]
                    ))
                finally:
                    self.fetch_queue.task_done()
    
    async def render_worker(self):
        """Worker for JS rendering stage."""
        while True:
            item = await self.render_queue.get()
            if item is None:  # Poison pill
                break
            
            start_time = time.time()
            
            try:
                if self.playwright_pool:
                    # Generate headers for this render
                    from .fetcher import generate_random_headers, shuffle_headers
                    headers = shuffle_headers(generate_random_headers())
                    
                    html = await self.playwright_pool.render(item.url, headers)
                    render_ms = int((time.time() - start_time) * 1000)
                    
                    timing = {
                        'fetch_ms': item.meta.get('fetch_ms', 0),
                        'render_ms': render_ms,
                    }
                    
                    warnings = [f"JS required: {item.reason}"]
                    
                    await self.parse_queue.put((
                        item.url, html, 'playwright', timing, warnings
                    ))
                    self.stats['rendered'] += 1
                    logger.info(f"[RENDER] {item.domain} rendered in {render_ms}ms")
                else:
                    # No Playwright pool available, pass through
                    await self.parse_queue.put((
                        item.url, item.html_partial, 'fallback',
                        item.meta, [f"No JS renderer: {item.reason}"]
                    ))
                    
            except Exception as e:
                logger.error(f"[RENDER] Error for {item.url}: {e}")
                await self.parse_queue.put((
                    item.url, item.html_partial, 'render_error',
                    item.meta, [f"Render failed: {e}"]
                ))
            finally:
                self.render_queue.task_done()
    
    async def parse_worker(self):
        """Worker for parse + NLP stage."""
        from .analyzer import parse_and_score
        
        while True:
            item = await self.parse_queue.get()
            if item is None:  # Poison pill
                break
            
            url, html, transport, timing, warnings = item
            start_time = time.time()
            
            try:
                if html:
                    # Parse and analyze
                    result = await parse_and_score(html, url)
                    result.transport = transport
                    result.timing_ms = {
                        **timing,
                        'parse_ms': int((time.time() - start_time) * 1000),
                        'total_ms': sum(timing.values()) + int((time.time() - start_time) * 1000)
                    }
                    result.warnings = warnings
                    
                    await self.result_queue.put(result)
                    self.stats['parsed'] += 1
                    
                    logger.debug(
                        f"[PARSE] {result.domain} - {result.word_count} words - "
                        f"{result.timing_ms['total_ms']}ms total"
                    )
                else:
                    # No content to parse
                    result = ArticleResult(
                        url=url,
                        title="",
                        text="",
                        transport=transport,
                        timing_ms=timing,
                        warnings=warnings + ["No content to parse"]
                    )
                    await self.result_queue.put(result)
                    
            except Exception as e:
                logger.error(f"[PARSE] Error for {url}: {e}")
                result = ArticleResult(
                    url=url,
                    title="",
                    text="",
                    transport=transport,
                    timing_ms=timing,
                    warnings=warnings + [f"Parse error: {e}"]
                )
                await self.result_queue.put(result)
            finally:
                self.parse_queue.task_done()
    
    async def start_workers(self, playwright_pool=None):
        """Start all worker tasks."""
        self.playwright_pool = playwright_pool
        
        # Start fetch workers
        for i in range(self.fetch_workers):
            task = asyncio.create_task(self.fetch_worker())
            self.workers.append(task)
        logger.info(f"[PIPELINE] Started {self.fetch_workers} fetch workers")
        
        # Start render workers
        for i in range(self.render_workers):
            task = asyncio.create_task(self.render_worker())
            self.workers.append(task)
        logger.info(f"[PIPELINE] Started {self.render_workers} render workers")
        
        # Start parse workers
        for i in range(self.parse_workers):
            task = asyncio.create_task(self.parse_worker())
            self.workers.append(task)
        logger.info(f"[PIPELINE] Started {self.parse_workers} parse workers")
    
    async def stop_workers(self):
        """Stop all workers gracefully."""
        # Send poison pills
        for _ in range(self.fetch_workers):
            await self.fetch_queue.put(None)
        for _ in range(self.render_workers):
            await self.render_queue.put(None)
        for _ in range(self.parse_workers):
            await self.parse_queue.put(None)
        
        # Wait for workers to finish
        await asyncio.gather(*self.workers, return_exceptions=True)
        
        # Final poison pill for results
        await self.result_queue.put(None)
        
        logger.info(f"[PIPELINE] Workers stopped. Stats: {self.stats}")
    
    async def process_urls(self, urls: List[str]) -> AsyncIterator[ArticleResult]:
        """Process URLs through the pipeline, yielding results as they complete."""
        # Queue all URLs
        for url in urls:
            domain = urlparse(url).netloc
            item = FetchItem(url=url, domain=domain)
            await self.fetch_queue.put(item)
        
        logger.info(f"[PIPELINE] Queued {len(urls)} URLs for processing")
        
        # Yield results as they come
        processed = 0
        while processed < len(urls):
            result = await self.result_queue.get()
            if result is None:
                break
            processed += 1
            yield result
        
        logger.info(f"[PIPELINE] Processed {processed}/{len(urls)} URLs")


async def run_pipeline(
    urls: List[str],
    *,
    max_concurrency: int = 200,
    per_domain: int = 3,
    playwright_pool=None
) -> AsyncIterator[ArticleResult]:
    """
    Run the high-throughput pipeline with all URLs.
    
    Args:
        urls: List of URLs to process
        max_concurrency: Maximum concurrent operations
        per_domain: Maximum concurrent requests per domain
        playwright_pool: Optional PlaywrightPool instance
    
    Yields:
        ArticleResult objects as they complete
    """
    orchestrator = PipelineOrchestrator(
        max_concurrency=max_concurrency,
        per_domain=per_domain,
        fetch_workers=min(100, max_concurrency),
        render_workers=6,
        parse_workers=8,
    )
    
    # Start workers
    await orchestrator.start_workers(playwright_pool)
    
    try:
        # Process and yield results
        async for result in orchestrator.process_urls(urls):
            yield result
    finally:
        # Clean shutdown
        await orchestrator.stop_workers()