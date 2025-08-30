"""Generic web scraper connector."""

import asyncio
import aiohttp
import yaml
from pathlib import Path
from bs4 import BeautifulSoup
from typing import AsyncIterator, Dict, Any, List
from .base import Connector
from ..ingest.utils import strip_html, make_id, parse_date, clean_text
import logging

logger = logging.getLogger(__name__)


class GenericWebConnector(Connector):
    """Scrape arbitrary websites using CSS selectors."""

    name = "generic_web"

    def __init__(self, sites_yaml: str = "config/sites.yaml", **kwargs):
        """
        Initialize generic web connector.

        Args:
            sites_yaml: Path to YAML file with site configurations
        """
        super().__init__(**kwargs)
        self.sites_yaml = sites_yaml
        self.sites = self._load_sites()

    def _load_sites(self) -> List[Dict]:
        """Load site configurations from YAML."""

        try:
            yaml_path = Path(self.sites_yaml)
            if yaml_path.exists():
                with open(yaml_path, "r") as f:
                    config = yaml.safe_load(f)
                    return config.get("sites", [])
            else:
                logger.warning(f"Sites YAML not found: {self.sites_yaml}")
                return []
        except Exception as e:
            logger.error(f"Failed to load sites config: {e}")
            return []

    async def fetch(self) -> AsyncIterator[Dict[str, Any]]:
        """Fetch content from configured websites."""

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30)
        ) as session:
            for site in self.sites:
                try:
                    async for item in self._fetch_site(session, site):
                        yield item
                except Exception as e:
                    logger.error(f"Failed to fetch site {site.get('name')}: {e}")
                    continue

                # Rate limiting
                await asyncio.sleep(2.0)

    async def _fetch_site(
        self, session: aiohttp.ClientSession, site: Dict
    ) -> AsyncIterator[Dict[str, Any]]:
        """Fetch content from a specific site."""

        url = site.get("url")
        if not url:
            return

        logger.info(f"Fetching {site.get('name', url)}")

        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.warning(f"Site returned {resp.status}: {url}")
                    return

                html = await resp.text()
                soup = BeautifulSoup(html, "lxml")

                # Find items using selector
                selector = site.get("selector", "article")
                items = soup.select(selector)

                limit = site.get("limit", 50)

                for i, item in enumerate(items[:limit]):
                    try:
                        # Extract title
                        title_selector = site.get("title", "h1,h2,h3")
                        title_elem = item.select_one(title_selector)
                        title = title_elem.get_text(strip=True) if title_elem else ""

                        # Extract body
                        body_selector = site.get("body", "p")
                        body_elems = item.select(body_selector)
                        body = " ".join(
                            [elem.get_text(strip=True) for elem in body_elems]
                        )

                        # Extract link
                        link_selector = site.get("link", "a")
                        link_elem = item.select_one(link_selector)
                        if link_elem and link_elem.get("href"):
                            item_url = link_elem["href"]
                            # Make absolute URL
                            if not item_url.startswith("http"):
                                from urllib.parse import urljoin

                                item_url = urljoin(url, item_url)
                        else:
                            item_url = f"{url}#item{i}"

                        # Extract date if selector provided
                        date = None
                        if site.get("date"):
                            date_elem = item.select_one(site["date"])
                            if date_elem:
                                date = parse_date(date_elem.get_text(strip=True))

                        if not date:
                            date = parse_date(None)  # Current time

                        yield {
                            "id": make_id(self.name, site.get("name"), item_url),
                            "source": self.name,
                            "subsource": site.get("name"),
                            "author": site.get("author"),  # Static author if configured
                            "title": title,
                            "text": clean_text(f"{title}\n\n{body}"),
                            "url": item_url,
                            "published_at": date,
                            "lang": site.get("lang", "en"),
                            "raw": None,  # Don't store HTML
                        }

                    except Exception as e:
                        logger.warning(
                            f"Failed to process item from {site.get('name')}: {e}"
                        )
                        continue

        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
