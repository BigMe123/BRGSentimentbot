"""Configuration constants for the sentiment CLI bot.

These settings are intentionally lightweight so the tool can run in a
limited environment.  They can be tweaked by advanced users.
"""

from __future__ import annotations

RSS_FEEDS = [
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://www.reutersagency.com/feed/?best-sectors=politics",
]

# Maximum number of concurrent network requests when scraping articles.
SCRAPE_CONCURRENCY = 15

# Cap the number of articles processed during a single cycle so memory
# usage stays reasonable on small machines.
MAX_ARTICLES_PER_CYCLE = 80
