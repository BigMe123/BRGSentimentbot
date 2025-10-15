#!/usr/bin/env python3
"""
Discovery Agents - Find New Sources and Articles
These agents actively explore the web to discover new content sources
"""

import asyncio
import aiohttp
import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Set
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
import feedparser

from .ai_agents import AIBaseAgent, AgentJob, Signal

logger = logging.getLogger(__name__)


class SourceDiscoveryAgent(AIBaseAgent):
    """
    Discovers NEW sources (RSS feeds, news sites, blogs)
    Explores the web to find content sources we don't know about yet
    """

    def __init__(self):
        super().__init__("source_discovery_agent")
        self.discovered_sources = []
        self.visited_domains = set()

    async def process_job(self, job: AgentJob) -> List[Signal]:
        """Discover new sources related to a topic"""
        topic = job.params.get('topic', 'news')
        seed_urls = job.params.get('seed_urls', [])
        max_sources = job.params.get('max_sources', 20)
        max_depth = job.params.get('max_depth', 2)

        logger.info(f"[SourceDiscovery] 🔍 Discovering sources for: {topic}")
        logger.info(f"[SourceDiscovery] Seed URLs: {len(seed_urls)}")

        # ========================================
        # STEP 1: SEARCH FOR SOURCES
        # ========================================

        discovered = await self._search_for_sources(topic, max_sources)

        # ========================================
        # STEP 2: EXPLORE SEED URLS
        # ========================================

        if seed_urls:
            explored = await self._explore_seeds(seed_urls, max_depth)
            discovered.extend(explored)

        # ========================================
        # STEP 3: VALIDATE SOURCES
        # ========================================

        validated = await self._validate_sources(discovered)

        logger.info(f"[SourceDiscovery] ✅ Found {len(validated)} valid sources")

        # ========================================
        # STEP 4: CREATE DISCOVERY SIGNALS
        # ========================================

        signals = []
        for source in validated[:max_sources]:
            signal = self.create_signal(
                title=f"New Source Discovered: {source['name']}",
                summary=f"Found new {source['type']} source: {source['url']}. "
                       f"Domain: {source['domain']}. "
                       f"Credibility score: {source['credibility']:.2f}. "
                       f"Has RSS feed: {source['has_rss']}. "
                       f"Discovered via: {source['discovery_method']}.",
                category='discovery',
                entity=source['domain'],
                confidence=source['credibility'],
                tags=[source['type'], 'source_discovery', topic, source['domain']],
                raw_data={
                    'source_info': source,
                    'discovery_method': source['discovery_method'],
                    'topic': topic
                }
            )
            signals.append(signal)

        return signals

    async def _search_for_sources(self, topic: str, max_sources: int) -> List[Dict]:
        """Search for sources using multiple methods"""
        sources = []

        # Method 1: Search for RSS feeds
        rss_sources = await self._search_rss_feeds(topic)
        sources.extend(rss_sources)

        # Method 2: Search for news sites
        news_sources = await self._search_news_sites(topic)
        sources.extend(news_sources)

        # Method 3: Search for blogs
        blog_sources = await self._search_blogs(topic)
        sources.extend(blog_sources)

        return sources[:max_sources]

    async def _search_rss_feeds(self, topic: str) -> List[Dict]:
        """Search for RSS feeds related to topic"""
        sources = []

        logger.info(f"[SourceDiscovery] 📰 Searching for RSS feeds...")

        # Search patterns
        search_queries = [
            f"{topic} RSS feed",
            f"{topic} news RSS",
            f"{topic} blog RSS",
            f"{topic} feed.xml"
        ]

        async with aiohttp.ClientSession() as session:
            for query in search_queries[:2]:  # Limit queries
                try:
                    # Use DuckDuckGo HTML search
                    search_url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"
                    headers = {'User-Agent': 'Mozilla/5.0'}

                    async with session.get(search_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status != 200:
                            continue

                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')

                        # Extract result links
                        for link in soup.find_all('a', class_='result__url')[:5]:
                            url = link.get('href', '')
                            if url:
                                # Check if it's an RSS feed
                                if await self._is_rss_feed(session, url):
                                    sources.append({
                                        'name': self._extract_domain(url),
                                        'url': url,
                                        'domain': self._extract_domain(url),
                                        'type': 'rss_feed',
                                        'has_rss': True,
                                        'credibility': 0.7,
                                        'discovery_method': 'rss_search'
                                    })

                    await asyncio.sleep(1)  # Rate limit

                except Exception as e:
                    logger.error(f"RSS search failed: {e}")

        logger.info(f"[SourceDiscovery] Found {len(sources)} RSS feeds")
        return sources

    async def _search_news_sites(self, topic: str) -> List[Dict]:
        """Search for news websites"""
        sources = []

        logger.info(f"[SourceDiscovery] 📡 Searching for news sites...")

        # Common news site patterns
        news_patterns = [
            r'.*news.*',
            r'.*press.*',
            r'.*times.*',
            r'.*post.*',
            r'.*daily.*',
            r'.*gazette.*',
            r'.*herald.*'
        ]

        async with aiohttp.ClientSession() as session:
            try:
                # Search for news sites about topic
                search_url = f"https://html.duckduckgo.com/html/?q={topic.replace(' ', '+')}+news"
                headers = {'User-Agent': 'Mozilla/5.0'}

                async with session.get(search_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        return sources

                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')

                    # Extract result links
                    for link in soup.find_all('a', class_='result__url')[:10]:
                        url = link.get('href', '')
                        if not url:
                            continue

                        domain = self._extract_domain(url)

                        # Check if it looks like a news site
                        is_news = any(re.match(pattern, domain.lower()) for pattern in news_patterns)

                        if is_news:
                            # Try to find RSS feed
                            rss_url = await self._find_rss_feed(session, url)

                            sources.append({
                                'name': domain,
                                'url': url,
                                'domain': domain,
                                'type': 'news_site',
                                'has_rss': bool(rss_url),
                                'rss_url': rss_url,
                                'credibility': 0.8,
                                'discovery_method': 'news_search'
                            })

            except Exception as e:
                logger.error(f"News site search failed: {e}")

        logger.info(f"[SourceDiscovery] Found {len(sources)} news sites")
        return sources

    async def _search_blogs(self, topic: str) -> List[Dict]:
        """Search for blogs related to topic"""
        sources = []

        logger.info(f"[SourceDiscovery] ✍️ Searching for blogs...")

        async with aiohttp.ClientSession() as session:
            try:
                # Search for blogs
                search_url = f"https://html.duckduckgo.com/html/?q={topic.replace(' ', '+')}+blog"
                headers = {'User-Agent': 'Mozilla/5.0'}

                async with session.get(search_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        return sources

                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')

                    # Extract blog links
                    for link in soup.find_all('a', class_='result__url')[:5]:
                        url = link.get('href', '')
                        if not url or 'blog' not in url.lower():
                            continue

                        domain = self._extract_domain(url)

                        # Try to find RSS feed
                        rss_url = await self._find_rss_feed(session, url)

                        sources.append({
                            'name': domain,
                            'url': url,
                            'domain': domain,
                            'type': 'blog',
                            'has_rss': bool(rss_url),
                            'rss_url': rss_url,
                            'credibility': 0.6,
                            'discovery_method': 'blog_search'
                        })

            except Exception as e:
                logger.error(f"Blog search failed: {e}")

        logger.info(f"[SourceDiscovery] Found {len(sources)} blogs")
        return sources

    async def _explore_seeds(self, seed_urls: List[str], max_depth: int) -> List[Dict]:
        """Explore seed URLs to find more sources"""
        sources = []
        to_visit = [(url, 0) for url in seed_urls]
        visited = set()

        logger.info(f"[SourceDiscovery] 🕷️ Crawling seed URLs (depth={max_depth})...")

        async with aiohttp.ClientSession() as session:
            while to_visit and len(sources) < 50:
                url, depth = to_visit.pop(0)

                if url in visited or depth > max_depth:
                    continue

                visited.add(url)

                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status != 200:
                            continue

                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')

                        # Find RSS feeds on page
                        rss_links = soup.find_all('link', type='application/rss+xml')
                        for rss_link in rss_links:
                            rss_url = rss_link.get('href', '')
                            if rss_url:
                                rss_url = urljoin(url, rss_url)
                                sources.append({
                                    'name': self._extract_domain(rss_url),
                                    'url': rss_url,
                                    'domain': self._extract_domain(url),
                                    'type': 'rss_feed',
                                    'has_rss': True,
                                    'credibility': 0.75,
                                    'discovery_method': 'crawl'
                                })

                        # Find links to follow (if depth allows)
                        if depth < max_depth:
                            for link in soup.find_all('a', href=True)[:20]:
                                next_url = urljoin(url, link['href'])
                                if next_url not in visited:
                                    to_visit.append((next_url, depth + 1))

                    await asyncio.sleep(0.5)  # Rate limit

                except Exception as e:
                    logger.debug(f"Failed to crawl {url}: {e}")

        logger.info(f"[SourceDiscovery] Crawled {len(visited)} pages, found {len(sources)} sources")
        return sources

    async def _find_rss_feed(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        """Try to find RSS feed for a website"""
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status != 200:
                    return None

                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')

                # Method 1: Check for RSS link in head
                rss_link = soup.find('link', type='application/rss+xml')
                if rss_link and rss_link.get('href'):
                    return urljoin(url, rss_link['href'])

                # Method 2: Common RSS locations
                base_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
                common_paths = ['/feed', '/rss', '/feed.xml', '/rss.xml', '/atom.xml']

                for path in common_paths:
                    test_url = base_url + path
                    if await self._is_rss_feed(session, test_url):
                        return test_url

        except Exception:
            pass

        return None

    async def _is_rss_feed(self, session: aiohttp.ClientSession, url: str) -> bool:
        """Check if URL is a valid RSS feed"""
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status != 200:
                    return False

                content = await response.text()

                # Quick check for RSS/Atom markers
                if any(marker in content[:1000] for marker in ['<rss', '<feed', '<channel>', 'application/rss']):
                    # Validate with feedparser
                    feed = feedparser.parse(content)
                    return bool(feed.entries)

        except Exception:
            pass

        return False

    async def _validate_sources(self, sources: List[Dict]) -> List[Dict]:
        """Validate and score discovered sources"""
        validated = []

        logger.info(f"[SourceDiscovery] 🔍 Validating {len(sources)} sources...")

        for source in sources:
            # Skip duplicates
            if source['domain'] in self.visited_domains:
                continue

            self.visited_domains.add(source['domain'])

            # Calculate credibility score
            credibility = await self._calculate_credibility(source)
            source['credibility'] = credibility

            # Only keep sources with decent credibility
            if credibility >= 0.5:
                validated.append(source)

        logger.info(f"[SourceDiscovery] ✅ {len(validated)} sources passed validation")
        return validated

    async def _calculate_credibility(self, source: Dict) -> float:
        """Calculate credibility score for a source"""
        score = 0.5  # Base score

        # Domain age (older = more credible)
        # Note: Would need WHOIS API for real implementation
        if any(tld in source['domain'] for tld in ['.gov', '.edu', '.org']):
            score += 0.2

        # Has RSS feed
        if source.get('has_rss'):
            score += 0.1

        # Type bonus
        if source['type'] == 'news_site':
            score += 0.1
        elif source['type'] == 'rss_feed':
            score += 0.15

        # Known reputable domains
        reputable = ['reuters', 'bbc', 'nytimes', 'wsj', 'ft', 'bloomberg', 'cnn', 'guardian']
        if any(rep in source['domain'].lower() for rep in reputable):
            score += 0.3

        return min(score, 1.0)

    def _extract_domain(self, url: str) -> str:
        """Extract clean domain from URL"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc or parsed.path
            # Remove www.
            domain = domain.replace('www.', '')
            return domain
        except:
            return url


class ArticleSpiderAgent(AIBaseAgent):
    """
    Spiders websites to discover new articles
    Follows links to find hidden/unlisted content
    """

    def __init__(self):
        super().__init__("article_spider_agent")
        self.discovered_articles = []
        self.visited_urls = set()

    async def process_job(self, job: AgentJob) -> List[Signal]:
        """Spider websites to discover articles"""
        start_urls = job.params.get('start_urls', [])
        topic = job.params.get('topic', '')
        max_articles = job.params.get('max_articles', 50)
        max_depth = job.params.get('max_depth', 3)

        logger.info(f"[ArticleSpider] 🕷️ Spidering for articles on: {topic}")
        logger.info(f"[ArticleSpider] Starting from {len(start_urls)} URLs")

        # ========================================
        # STEP 1: CRAWL WEBSITES
        # ========================================

        articles = await self._spider_sites(start_urls, topic, max_depth, max_articles)

        logger.info(f"[ArticleSpider] ✅ Discovered {len(articles)} articles")

        # ========================================
        # STEP 2: FILTER RELEVANT ARTICLES
        # ========================================

        filtered = self._filter_articles(articles, topic)

        # ========================================
        # STEP 3: CREATE DISCOVERY SIGNALS
        # ========================================

        signals = []
        for article in filtered[:max_articles]:
            signal = self.create_signal(
                title=f"Discovered: {article['title'][:100]}",
                summary=f"Found new article: {article['title']}. "
                       f"Source: {article['domain']}. "
                       f"Published: {article.get('published', 'unknown')}. "
                       f"Depth: {article['depth']}. "
                       f"{article['text'][:300]}...",
                category='discovery',
                entity=article['domain'],
                confidence=article['relevance'],
                tags=['article_discovery', topic, article['domain']],
                raw_data={
                    'article_info': article,
                    'discovery_method': 'spider',
                    'topic': topic
                }
            )
            signals.append(signal)

        return signals

    async def _spider_sites(self, start_urls: List[str], topic: str, max_depth: int, max_articles: int) -> List[Dict]:
        """Spider websites to discover articles"""
        articles = []
        to_visit = [(url, 0) for url in start_urls]

        logger.info(f"[ArticleSpider] Starting crawl (max_depth={max_depth}, max_articles={max_articles})")

        async with aiohttp.ClientSession() as session:
            while to_visit and len(articles) < max_articles:
                if not to_visit:
                    break

                url, depth = to_visit.pop(0)

                if url in self.visited_urls or depth > max_depth:
                    continue

                self.visited_urls.add(url)

                try:
                    headers = {'User-Agent': 'Mozilla/5.0 (BSGBOT/1.0)'}
                    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status != 200:
                            continue

                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')

                        # Extract article content
                        article = self._extract_article(soup, url, depth)
                        if article:
                            articles.append(article)
                            logger.info(f"[ArticleSpider] Found article: {article['title'][:50]}...")

                        # Find more links to follow
                        if depth < max_depth:
                            links = self._find_article_links(soup, url)
                            for link in links[:10]:  # Limit links per page
                                if link not in self.visited_urls:
                                    to_visit.append((link, depth + 1))

                    await asyncio.sleep(1)  # Rate limit

                except Exception as e:
                    logger.debug(f"Failed to spider {url}: {e}")

        logger.info(f"[ArticleSpider] Crawled {len(self.visited_urls)} pages, found {len(articles)} articles")
        return articles

    def _extract_article(self, soup: BeautifulSoup, url: str, depth: int) -> Optional[Dict]:
        """Extract article content from HTML"""
        try:
            # Find article title
            title = None
            for tag in ['h1', 'h2', 'title']:
                element = soup.find(tag)
                if element:
                    title = element.get_text().strip()
                    break

            if not title:
                return None

            # Find article content
            text = ''

            # Try common article containers
            for selector in ['article', 'div.content', 'div.article-body', 'main']:
                container = soup.find(selector)
                if container:
                    paragraphs = container.find_all('p')
                    text = ' '.join(p.get_text().strip() for p in paragraphs)
                    break

            # Fallback: get all paragraphs
            if not text:
                paragraphs = soup.find_all('p')
                text = ' '.join(p.get_text().strip() for p in paragraphs[:10])

            if len(text) < 100:  # Too short, probably not an article
                return None

            # Extract metadata
            domain = self._extract_domain(url)

            # Try to find publish date
            published = None
            for meta in soup.find_all('meta'):
                if meta.get('property') in ['article:published_time', 'datePublished']:
                    published = meta.get('content')
                    break

            return {
                'title': title,
                'text': text[:5000],  # Limit text length
                'url': url,
                'domain': domain,
                'published': published or 'unknown',
                'depth': depth,
                'word_count': len(text.split()),
                'relevance': 0.7  # Will be calculated later
            }

        except Exception as e:
            logger.debug(f"Failed to extract article from {url}: {e}")
            return None

    def _find_article_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """Find links that likely point to articles"""
        links = []

        # Article patterns
        article_patterns = [
            r'/article/',
            r'/news/',
            r'/blog/',
            r'/post/',
            r'/\d{4}/\d{2}/',  # Date-based URLs
            r'/story/',
            r'/[a-z-]+/\d+/',  # category/id
        ]

        for link in soup.find_all('a', href=True):
            href = link['href']

            # Skip non-article links
            if any(skip in href.lower() for skip in ['#', 'javascript:', 'mailto:', '.pdf', '.jpg', '.png']):
                continue

            # Make absolute URL
            full_url = urljoin(base_url, href)

            # Check if looks like article URL
            if any(re.search(pattern, full_url) for pattern in article_patterns):
                links.append(full_url)

        return links

    def _filter_articles(self, articles: List[Dict], topic: str) -> List[Dict]:
        """Filter articles by relevance to topic"""
        filtered = []

        topic_lower = topic.lower()

        for article in articles:
            # Calculate relevance score
            title_match = topic_lower in article['title'].lower()
            text_match = topic_lower in article['text'].lower()

            if title_match:
                article['relevance'] = 0.9
                filtered.append(article)
            elif text_match:
                article['relevance'] = 0.7
                filtered.append(article)

        # Sort by relevance
        filtered.sort(key=lambda x: x['relevance'], reverse=True)

        return filtered

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL"""
        try:
            parsed = urlparse(url)
            return parsed.netloc.replace('www.', '')
        except:
            return url


# Discovery Agent Registry
DISCOVERY_AGENT_REGISTRY = {
    'discover_sources': SourceDiscoveryAgent,
    'spider_articles': ArticleSpiderAgent
}


def get_discovery_agent(agent_type: str) -> AIBaseAgent:
    """Get discovery agent instance"""
    agent_class = DISCOVERY_AGENT_REGISTRY.get(agent_type)
    if not agent_class:
        raise ValueError(f"Unknown discovery agent: {agent_type}. Available: {list(DISCOVERY_AGENT_REGISTRY.keys())}")
    return agent_class()


async def run_discovery_agent_job(agent_type: str, job: AgentJob) -> Dict[str, Any]:
    """Run a discovery agent job"""
    agent = get_discovery_agent(agent_type)
    return await agent.run_job(job)
