"""RSS feed discovery and resolution module."""

import asyncio
import aiohttp
import yaml
import re
from pathlib import Path
from typing import List, Dict, Optional, Set
from urllib.parse import urljoin, urlparse
import feedparser
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Load RSS registry
registry_path = Path(__file__).parent.parent / "config" / "rss_registry.yaml"
if registry_path.exists():
    with open(registry_path) as f:
        RSS_REGISTRY = yaml.safe_load(f)
else:
    RSS_REGISTRY = {}

# Load discovery config
config_path = Path(__file__).parent.parent / "config" / "defaults.yaml"
if config_path.exists():
    with open(config_path) as f:
        CONFIG = yaml.safe_load(f)
else:
    CONFIG = {"discovery": {"common_paths": []}}


class RSSDiscovery:
    """Discovers and resolves RSS feeds for domains."""
    
    def __init__(self):
        self.common_paths = CONFIG.get("discovery", {}).get("common_paths", [
            "/rss", "/feed", "/feeds", "/rss.xml", "/feed.xml",
            "/atom.xml", "/index.rss", "/news/rss", "/en/rss"
        ])
        self.session = None
        self.discovered_cache = {}
    
    async def resolve_feeds(self, domain: str, region: str = None, topic: str = None) -> List[str]:
        """
        Resolve RSS feeds for a domain using registry, then autodiscovery.
        
        Args:
            domain: Domain to find feeds for
            region: Region context (asia, europe, etc.)
            topic: Topic context (politics, economy, etc.)
        
        Returns:
            List of RSS feed URLs
        """
        feeds = []
        
        # Step 1: Check registry
        feeds = self._check_registry(domain, region)
        if feeds:
            logger.info(f"Found {len(feeds)} feeds for {domain} in registry")
            return feeds
        
        # Step 2: Check cache
        if domain in self.discovered_cache:
            return self.discovered_cache[domain]
        
        # Step 3: Autodiscovery
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        feeds = await self._autodiscover(domain)
        
        # Step 4: Category fallbacks based on topic
        if not feeds and topic:
            feeds = await self._category_fallbacks(domain, topic)
        
        # Cache results
        if feeds:
            self.discovered_cache[domain] = feeds
            logger.info(f"Discovered {len(feeds)} feeds for {domain}")
        
        return feeds
    
    def _check_registry(self, domain: str, region: str = None) -> List[str]:
        """Check RSS registry for known feeds."""
        feeds = []
        
        # Clean domain (remove www. if present)
        clean_domain = domain.replace("www.", "")
        
        # Search in region-specific section
        if region and region in RSS_REGISTRY:
            for reg_domain, info in RSS_REGISTRY[region].items():
                if clean_domain in reg_domain or reg_domain in clean_domain:
                    feeds.extend(info.get("rss_endpoints", []))
        
        # Search in global section
        if "global" in RSS_REGISTRY:
            for reg_domain, info in RSS_REGISTRY["global"].items():
                if clean_domain in reg_domain or reg_domain in clean_domain:
                    feeds.extend(info.get("rss_endpoints", []))
        
        # Search all regions if no feeds found
        if not feeds:
            for region_key in RSS_REGISTRY:
                if region_key != "global":
                    for reg_domain, info in RSS_REGISTRY[region_key].items():
                        if clean_domain in reg_domain or reg_domain in clean_domain:
                            feeds.extend(info.get("rss_endpoints", []))
                            break
        
        return list(set(feeds))  # Remove duplicates
    
    async def _autodiscover(self, domain: str) -> List[str]:
        """Autodiscover RSS feeds for a domain."""
        feeds = []
        base_url = f"https://{domain}"
        
        # Try to fetch homepage and parse for RSS links
        try:
            async with self.session.get(base_url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    html = await response.text()
                    feeds.extend(self._parse_html_for_feeds(html, base_url))
        except Exception as e:
            logger.debug(f"Failed to fetch homepage for {domain}: {e}")
        
        # Try common RSS paths
        if not feeds:
            tasks = []
            for path in self.common_paths:
                url = urljoin(base_url, path)
                tasks.append(self._check_feed_url(url))
            
            results = await asyncio.gather(*tasks)
            feeds = [url for url in results if url]
        
        return feeds
    
    def _parse_html_for_feeds(self, html: str, base_url: str) -> List[str]:
        """Parse HTML for RSS feed links."""
        feeds = []
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Look for <link rel="alternate" type="application/rss+xml">
            rss_links = soup.find_all('link', {'rel': 'alternate', 'type': re.compile(r'application/(rss|atom)\+xml')})
            for link in rss_links:
                href = link.get('href')
                if href:
                    feed_url = urljoin(base_url, href)
                    feeds.append(feed_url)
            
            # Look for common RSS link patterns in anchors
            rss_anchors = soup.find_all('a', href=re.compile(r'(rss|feed|atom)', re.I))
            for anchor in rss_anchors[:5]:  # Limit to prevent too many
                href = anchor.get('href')
                if href and any(x in href.lower() for x in ['rss', 'feed', 'atom', '.xml']):
                    feed_url = urljoin(base_url, href)
                    feeds.append(feed_url)
        
        except Exception as e:
            logger.debug(f"Error parsing HTML for feeds: {e}")
        
        return list(set(feeds))[:10]  # Return max 10 unique feeds
    
    async def _check_feed_url(self, url: str) -> Optional[str]:
        """Check if a URL is a valid RSS feed."""
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as response:
                if response.status == 200:
                    content = await response.text()
                    # Quick check for RSS/Atom markers
                    if any(marker in content[:1000] for marker in ['<rss', '<feed', '<channel', '<?xml']):
                        return url
        except:
            pass
        return None
    
    async def _category_fallbacks(self, domain: str, topic: str) -> List[str]:
        """Try category-specific feed paths based on topic."""
        feeds = []
        base_url = f"https://{domain}"
        
        # Topic-specific paths
        topic_paths = {
            'politics': ['/politics/rss', '/politics/feed', '/news/politics/rss'],
            'economy': ['/economy/rss', '/business/rss', '/business/feed', '/finance/rss'],
            'elections': ['/elections/rss', '/politics/elections/feed'],
            'tech': ['/tech/rss', '/technology/feed', '/tech/feed'],
            'climate': ['/environment/rss', '/climate/feed', '/environment/climate/rss'],
            'security': ['/security/rss', '/defense/feed', '/security/feed'],
            'general': ['/news/rss', '/latest/rss', '/top-stories/rss']
        }
        
        paths_to_try = topic_paths.get(topic, []) + topic_paths.get('general', [])
        
        tasks = []
        for path in paths_to_try:
            url = urljoin(base_url, path)
            tasks.append(self._check_feed_url(url))
        
        results = await asyncio.gather(*tasks)
        feeds = [url for url in results if url]
        
        return feeds
    
    def get_editorial_family(self, domain: str, region: str = None) -> str:
        """Get editorial family for a domain from registry."""
        clean_domain = domain.replace("www.", "")
        
        # Check region-specific
        if region and region in RSS_REGISTRY:
            for reg_domain, info in RSS_REGISTRY[region].items():
                if clean_domain in reg_domain or reg_domain in clean_domain:
                    return info.get("editorial_family", "unknown")
        
        # Check all regions
        for region_key in RSS_REGISTRY:
            if region_key != "global":
                for reg_domain, info in RSS_REGISTRY[region_key].items():
                    if clean_domain in reg_domain or reg_domain in clean_domain:
                        return info.get("editorial_family", "unknown")
        
        # Default based on common patterns
        if any(x in domain for x in ['bbc', 'npr', 'pbs', 'dw.com', 'france24']):
            return "public_broadcaster"
        elif any(x in domain for x in ['reuters', 'ap', 'afp', 'bloomberg']):
            return "wire"
        elif any(x in domain for x in ['dailymail', 'sun', 'mirror', 'bild']):
            return "tabloid"
        else:
            return "broadsheet"  # Default assumption
    
    async def close(self):
        """Close the aiohttp session."""
        if self.session:
            await self.session.close()


# Global instance
_discovery = None

def get_discovery() -> RSSDiscovery:
    """Get or create global discovery instance."""
    global _discovery
    if _discovery is None:
        _discovery = RSSDiscovery()
    return _discovery