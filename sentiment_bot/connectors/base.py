"""Base connector interface for all data sources."""

from typing import AsyncIterator, Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class Connector:
    """Base interface for all connectors."""

    name: str = "base"  # Short machine name

    def __init__(self, **kwargs):
        """Initialize connector with config."""
        self.config = kwargs
        self.logger = logging.getLogger(f"{__name__}.{self.name}")

    async def fetch(self) -> AsyncIterator[Dict[str, Any]]:
        """
        Yield normalized records matching the contract:
        {
            "id": str,               # stable per item
            "source": str,           # e.g., "reddit", "google_news", "hn"
            "subsource": str|None,   # e.g., subreddit, query, site
            "author": str|None,
            "title": str|None,
            "text": str,             # best-effort fulltext
            "url": str,
            "published_at": datetime,  # timezone-aware
            "lang": str|None,        # ISO code when detectable
            "raw": dict|None         # original payload for audits
        }

        Must never raise on individual item failures; log and continue.
        """
        raise NotImplementedError("Subclasses must implement fetch()")

    async def __aiter__(self):
        """Allow async iteration over the connector."""
        async for item in self.fetch():
            yield item
