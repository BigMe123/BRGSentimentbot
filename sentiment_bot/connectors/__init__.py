"""Free data connectors for diverse sources - COMPREHENSIVE DATA COLLECTION."""

from .base import Connector
from .reddit_rss import RedditRSS
from .google_news import GoogleNewsRSS
from .hackernews import HackerNews
from .stackexchange import StackExchange
from .mastodon import MastodonConnector
from .bluesky import BlueskyConnector
from .youtube import YouTubeConnector
from .wikipedia import WikipediaConnector
from .gdelt import GDELTConnector
from .generic_web import GenericWebConnector
from .twitter_snscrape import TwitterSnscrape
from .twitter_improved import TwitterImproved
from .parse_bot import ParseBotConnector, ParseBotScraper

# Comprehensive data connectors - ALL DATA TYPES
from .comprehensive_data import (
    SECFilingsConnector,
    EarningsCallsConnector,
    PropertyDataConnector,
    WeatherCrisisConnector,
    FinancialNewsConnector,
    CryptoDataConnector,
    CommoditiesDataConnector,
    GovernmentDataConnector,
    CorporateFilingsConnector,
    ResearchReportsConnector,
    ComprehensiveDataAggregator,
)

__all__ = [
    "Connector",
    "RedditRSS",
    "GoogleNewsRSS",
    "HackerNews",
    "StackExchange",
    "MastodonConnector",
    "BlueskyConnector",
    "YouTubeConnector",
    "WikipediaConnector",
    "GDELTConnector",
    "GenericWebConnector",
    "TwitterSnscrape",
    "TwitterImproved",
    "ParseBotConnector",
    "ParseBotScraper",
    # Comprehensive data connectors
    "SECFilingsConnector",
    "EarningsCallsConnector",
    "PropertyDataConnector",
    "WeatherCrisisConnector",
    "FinancialNewsConnector",
    "CryptoDataConnector",
    "CommoditiesDataConnector",
    "GovernmentDataConnector",
    "CorporateFilingsConnector",
    "ResearchReportsConnector",
    "ComprehensiveDataAggregator",
]
