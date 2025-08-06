from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass
from typing import List, Optional, Iterable
import aiohttp
import feedparser
from bs4 import BeautifulSoup
from .config import settings

# Configure logging for risk sentiment analysis
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - RiskSentiment - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class ArticleData:
    """Holds URL, title, text, and optional published timestamp."""
    url: str
    title: str
    text: str
    published: Optional[str] = None


async def _fetch_and_parse_url(url: str) -> ArticleData:
    """
    Fetch a single URL and extract maximum text for sentiment analysis.
    Aggressive extraction to maximize content collection for confidence.
    """
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
        if article.text:  # Only return if we got content
            return article
    except Exception:
        pass  # Continue to fallback methods
    
    # Aggressive fallback with aiohttp + BeautifulSoup
    try:
        # Create session with high timeout for maximum collection
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, ssl=False) as resp:
                html = await resp.text()
    except Exception as e:
        # Final fallback to urllib with extended timeout
        logging.debug("Failed HTTP fetch, falling back to urllib for %s: %s", url, e)
        from urllib.error import URLError  # noqa: E402
        from urllib.request import urlopen  # noqa: E402
        import socket  # noqa: E402
        
        def _urlopen_read() -> str:
            try:
                # Increased timeout for maximum collection
                with urlopen(url, timeout=20) as resp:
                    return resp.read().decode(errors="ignore")
            except (URLError, socket.timeout) as err:
                logging.debug("Failed urllib fetch for %s: %s", url, err)
                raise
        
        try:
            html = await asyncio.to_thread(_urlopen_read)
        except Exception:
            # Return empty article rather than failing
            return ArticleData(url=url, title="", text="", published=None)
    
    # Extract maximum content from HTML
    soup = BeautifulSoup(html, "html.parser")
    
    # Remove only scripts and styles - keep all other content
    for element in soup(['script', 'style', 'noscript']):
        element.decompose()
    
    # Get ALL text-bearing elements for maximum sentiment data
    text_elements = []
    
    # Primary content containers
    for tag in ['article', 'main', 'section', 'div']:
        text_elements.extend(soup.find_all(tag))
    
    # Also get all paragraphs, headers, lists
    text_elements.extend(soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'blockquote']))
    
    # Extract and combine all text
    seen_text = set()
    text_parts = []
    
    for elem in text_elements:
        text = elem.get_text(separator=' ', strip=True)
        # Deduplicate while preserving order
        if text and len(text) > 20 and text not in seen_text:
            seen_text.add(text)
            text_parts.append(text)
    
    # Combine all text
    full_text = "\n\n".join(text_parts)
    
    # Get title with fallbacks
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""
    if not title:
        h1 = soup.find("h1")
        title = h1.get_text(strip=True) if h1 else ""
    
    # Try to extract publish date
    published = None
    date_meta = soup.find('meta', {'property': 'article:published_time'})
    if date_meta:
        published = date_meta.get('content')
    
    return ArticleData(
        url=url,
        title=title,
        text=full_text,
        published=published,
    )


async def fetch_and_parse(url: str) -> ArticleData:
    """Public wrapper around :func:`_fetch_and_parse_url` for easier patching."""
    return await _fetch_and_parse_url(url)


async def gather_rss(feeds: Iterable[str] | None = None) -> List[ArticleData]:
    """
    Parse RSS feeds and fetch articles with maximum parallelization.
    Optimized for high-volume collection to increase sentiment confidence.
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
    sem = asyncio.Semaphore(50)  # Increased from 10 for maximum parallelization
    results: List[ArticleData] = []
    failed_count = 0
    
    async def _worker(link: str):
        async with sem:
            try:
                art = await fetch_and_parse(link)
                if art.text:  # Only count successful extractions
                    results.append(art)
                    logger.debug(f"Successfully extracted: {link} ({len(art.text)} chars)")
                else:
                    nonlocal failed_count
                    failed_count += 1
                    logger.debug(f"No content extracted from: {link}")
            except Exception:
                nonlocal failed_count
                failed_count += 1
                logger.debug(f"Failed to fetch or parse {link}")
    
    # Execute all fetches concurrently
    await asyncio.gather(*[_worker(link) for link in unique_links])
    
    # Log collection statistics for confidence assessment
    total_words = sum(len(art.text.split()) for art in results)
    unique_domains = len(set(art.url.split('/')[2] for art in results if '/' in art.url))
    
    logger.info(f"""
    ========== SENTIMENT DATA COLLECTION SUMMARY ==========
    Total articles collected: {len(results)}/{len(unique_links)}
    Success rate: {len(results)/len(unique_links)*100:.1f}%
    Total words collected: {total_words:,}
    Unique domains: {unique_domains}
    Confidence Score: {min(len(results)/50, 1.0)*100:.1f}%
    ========================================================
    """)
    
    return results


async def gather_all_sources(feeds: Iterable[str] | None = None) -> List[ArticleData]:
    """
    Main entry point for risk sentiment data collection.
    Maximizes article volume for high-confidence analysis.
    """
    return await gather_rss(feeds)
