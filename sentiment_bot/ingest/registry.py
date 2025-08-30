"""Connector registry and configuration loader."""

from typing import Dict, Type, List, Any
from pathlib import Path
import yaml
import logging
from ..connectors.base import Connector

# Import all connectors
from ..connectors.reddit_rss import RedditRSS
from ..connectors.google_news import GoogleNewsRSS
from ..connectors.hackernews import HackerNews
from ..connectors.hackernews_search import HackerNewsSearch
from ..connectors.stackexchange import StackExchange
from ..connectors.mastodon import MastodonConnector
from ..connectors.bluesky import BlueskyConnector
from ..connectors.youtube import YouTubeConnector
from ..connectors.wikipedia import WikipediaConnector
from ..connectors.gdelt import GDELTConnector
from ..connectors.generic_web import GenericWebConnector
from ..connectors.twitter_snscrape import TwitterSnscrape

logger = logging.getLogger(__name__)

# Registry of available connectors
CONNECTORS: Dict[str, Type[Connector]] = {
    "reddit": RedditRSS,
    "google_news": GoogleNewsRSS,
    "hackernews": HackerNews,
    "hackernews_search": HackerNewsSearch,
    "stackexchange": StackExchange,
    "mastodon": MastodonConnector,
    "bluesky": BlueskyConnector,
    "youtube": YouTubeConnector,
    "wikipedia": WikipediaConnector,
    "gdelt": GDELTConnector,
    "generic_web": GenericWebConnector,
    "twitter": TwitterSnscrape,
}


class ConnectorRegistry:
    """Manage and instantiate connectors from configuration."""

    def __init__(self, config_path: str = "config/sources.yaml"):
        """
        Initialize the registry.

        Args:
            config_path: Path to YAML configuration file
        """
        self.config_path = Path(config_path)
        self.connectors: List[Connector] = []
        self._load_config()

    def _load_config(self):
        """Load connectors from YAML configuration."""

        if not self.config_path.exists():
            logger.warning(f"Configuration file not found: {self.config_path}")
            return

        try:
            with open(self.config_path, "r") as f:
                config = yaml.safe_load(f)

            sources = config.get("sources", [])

            for source_config in sources:
                connector_type = source_config.get("type")
                if not connector_type:
                    logger.warning("Source configuration missing 'type' field")
                    continue

                if connector_type not in CONNECTORS:
                    logger.warning(f"Unknown connector type: {connector_type}")
                    continue

                # Get the connector class
                connector_class = CONNECTORS[connector_type]

                # Extract parameters
                params = {k: v for k, v in source_config.items() if k != "type"}

                try:
                    # Instantiate the connector
                    connector = connector_class(**params)
                    self.connectors.append(connector)
                    logger.info(f"Loaded connector: {connector_type}")
                except Exception as e:
                    logger.error(f"Failed to initialize {connector_type}: {e}")

        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")

    def get_connectors(self) -> List[Connector]:
        """Get all loaded connectors."""
        return self.connectors

    def get_connector(self, name: str) -> Connector:
        """Get a specific connector by name."""
        for connector in self.connectors:
            if connector.name == name:
                return connector
        return None

    async def fetch_all(self):
        """Fetch from all connectors."""

        for connector in self.connectors:
            try:
                logger.info(f"Fetching from {connector.name}")
                async for item in connector.fetch():
                    yield item
            except Exception as e:
                logger.error(f"Failed to fetch from {connector.name}: {e}")
                continue
