"""Free data connectors for diverse sources."""

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
]
