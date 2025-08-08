"""Configuration via environment variables using :mod:`pydantic-settings`."""

from __future__ import annotations
from typing import List
import os
from pathlib import Path
from dataclasses import dataclass, field
from datetime import timedelta


def load_rss_sources(path: str | Path | None = None) -> List[str]:
    """Load RSS source URLs from a text file.

    The file may contain comments starting with ``#`` and blank lines. The
    resulting list is deduplicated while preserving order. If *path* is not
    provided it will look for a ``RSS_SOURCES_FILE`` environment variable and
    finally fall back to ``rss_sources.txt`` in the project root.
    """

    source_path = Path(
        path
        or os.getenv("RSS_SOURCES_FILE")
        or Path(__file__).resolve().parent.parent / "rss_sources.txt"
    )
    urls: List[str] = []
    if source_path.exists():
        for line in source_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith(("http://", "https://")) and line not in urls:
                urls.append(line)
    return urls


DEFAULT_RSS_SOURCES = load_rss_sources()

# Region, topic and time window mappings used by the interactive CLI
REGION_MAP = {
    "africa": ["africa"],
    "asia": ["asia"],
    "europe": ["europe"],
    "latin_america": ["latin america", "south america"],
    "middle_east": ["middle east"],
    "north_america": ["north america"],
    "oceania": ["oceania"],
}

TOPIC_MAP = {
    "energy": ["energy", "oil", "gas"],
    "elections": ["election", "vote"],
    "sanctions": ["sanction"],
    "cybersecurity": ["cyber", "hacker"],
    "protests": ["protest", "demonstration"],
    "trade": ["trade", "tariff"],
    "banking": ["bank", "finance"],
    "sovereign_risk": ["sovereign", "default", "debt"],
    "supply_chain": ["supply chain", "logistics"],
    "climate": ["climate", "emission"],
    "migration": ["migration", "immigrant"],
    "health": ["health", "disease", "pandemic"],
    "conflict": ["conflict", "war"],
    "technology": ["technology", "tech"],
    "defense": ["defense", "military"],
    "natural_disasters": ["earthquake", "flood", "hurricane"],
    "terrorism": ["terrorism", "attack"],
    "infrastructure": ["infrastructure", "bridge", "road"],
    "diplomacy": ["diplomacy", "talks"],
}

WINDOWS = {
    "minute": timedelta(seconds=60),
    "half_hour": timedelta(minutes=30),
    "hour": timedelta(hours=1),
    "day": timedelta(days=1),
    "week": timedelta(weeks=1),
    "month": timedelta(days=30),
    "year": timedelta(days=365),
}

try:  # pragma: no cover - optional dependency
    from pydantic_settings import BaseSettings  # type: ignore

    class Settings(BaseSettings):
        """Application settings loaded from environment variables."""

        NEWSAPI_KEY: str = "027e167533f7488bb9935e9ab1874e72"
        RSS_FEEDS: List[str] = DEFAULT_RSS_SOURCES or [
            # Major International News
            "https://feeds.bbci.co.uk/news/world/rss.xml",
            "https://feeds.bbci.co.uk/news/rss.xml",
            "https://www.aljazeera.com/xml/rss/all.xml",
            "http://rss.cnn.com/rss/cnn_topstories.rss",
            "http://rss.cnn.com/rss/cnn_world.rss",
            "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
            "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
            "https://feeds.washingtonpost.com/rss/world",
            "https://feeds.washingtonpost.com/rss/national",
            "https://www.theguardian.com/world/rss",
            "https://www.theguardian.com/uk/rss",
            "https://feeds.reuters.com/reuters/topNews",
            "https://feeds.reuters.com/reuters/worldNews",
            # Business & Finance
            "https://feeds.bloomberg.com/markets/news.rss",
            "https://feeds.ft.com/rss/home",
            "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
            "https://feeds.washingtonpost.com/rss/business",
            "http://rss.cnn.com/rss/money_latest.rss",
            "https://www.wsj.com/xml/rss/3_7085.xml",
            "https://www.cnbc.com/id/100003114/device/rss/rss.html",
            "https://www.cnbc.com/id/100727362/device/rss/rss.html",
            "https://feeds.marketwatch.com/marketwatch/topstories/",
            "https://www.economist.com/feeds/print-sections/79/finance-and-economics.xml",
            # Technology
            "https://feeds.arstechnica.com/arstechnica/index",
            "https://www.wired.com/feed/rss",
            "https://techcrunch.com/feed/",
            "https://www.theverge.com/rss/index.xml",
            "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
            "https://feeds.washingtonpost.com/rss/business/technology",
            "http://feeds.feedburner.com/TechCrunch/",
            "https://www.zdnet.com/news/rss.xml",
            "https://www.cnet.com/rss/news/",
            "https://feeds.feedburner.com/venturebeat/SZYF",
            # Science
            "https://www.nature.com/nature.rss",
            "https://www.sciencedaily.com/rss/all.xml",
            "https://rss.nytimes.com/services/xml/rss/nyt/Science.xml",
            "https://www.newscientist.com/feed/home",
            "https://feeds.washingtonpost.com/rss/rss_speaking-of-science",
            "https://www.scientificamerican.com/feed/basic/",
            # Politics
            "https://rss.politico.com/politics-news.xml",
            "https://thehill.com/feed/",
            "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml",
            "https://feeds.washingtonpost.com/rss/politics",
            "https://feeds.npr.org/1014/rss.xml",
            # Defense & Military
            "https://www.defensenews.com/arc/outboundfeeds/rss/category/news/?outputType=xml",
            "https://www.janes.com/feeds/news",
            "https://www.military.com/rss-feeds/content?category=news&tags=headlines",
            "https://www.defenseone.com/rss.xml",
            "https://www.airforcetimes.com/arc/outboundfeeds/rss/?outputType=xml",
            "https://www.navytimes.com/arc/outboundfeeds/rss/?outputType=xml",
            "https://www.armytimes.com/arc/outboundfeeds/rss/?outputType=xml",
            "https://breakingdefense.com/feed/",
            "https://www.thedrive.com/the-war-zone/rss",
            "https://www.c4isrnet.com/arc/outboundfeeds/rss/?outputType=xml",
            # Geopolitics & International Relations
            "https://www.foreignaffairs.com/rss.xml",
            "https://www.cfr.org/rss.xml",
            "https://feeds.feedburner.com/stratfor/geopolitical-diary",
            "https://warontherocks.com/feed/",
            "https://www.csis.org/analysis/feed",
            "https://www.brookings.edu/feed/",
            "https://carnegieendowment.org/feed",
            "https://www.rand.org/blog.xml",
            "https://www.atlanticcouncil.org/feed/",
            "https://thediplomat.com/feed/",
            "https://www.lawfareblog.com/rss.xml",
            "https://www.realcleardefense.com/index.xml",
            "https://www.iiss.org/en/feed/",
            "https://rusi.org/rss.xml",
            # Intelligence & Security
            "https://theintercept.com/feed/?lang=en",
            "https://www.bellingcat.com/feed/",
            "https://intelnews.org/feed/",
            "https://www.janes.com/feeds/news/security",
            "https://www.hstoday.us/feed/",
            "https://www.cyberscoop.com/feed/",
            # Regional Security Focus
            "https://amwaj.media/rss",  # Middle East
            "https://www.mei.edu/rss.xml",  # Middle East Institute
            "https://besacenter.org/feed/",  # Begin-Sadat Center
            "https://www.scmp.com/rss/91/feed",  # South China Morning Post - China
            "https://www.38north.org/feed/",  # North Korea analysis
            "https://jamestown.org/feed/",  # Eurasia focus
            "https://www.fpri.org/feed/",  # Foreign Policy Research Institute
            # NATO & European Security
            "https://www.nato.int/cps/en/natohq/rss.xml",
            "https://www.euractiv.com/sections/defence-and-security/feed/",
            "https://www.europeanleadershipnetwork.org/feed/",
            # Think Tanks & Analysis
            "https://www.hudson.org/rss.xml",
            "https://www.aei.org/feed/",
            "https://www.heritage.org/rss.xml",
            "https://www.newamerica.org/rss/",
            "https://www.stimson.org/feed/",
            "https://www.usip.org/rss.xml",
            # European News
            "https://www.france24.com/en/rss",
            "https://www.dw.com/rss/en/news/rss.xml",
            "https://www.euronews.com/rss",
            "https://www.spiegel.de/international/index.rss",
            "https://www.lemonde.fr/en/rss/une.xml",
            # Asian News
            "https://asia.nikkei.com/rss/feed/nar",
            "https://www.japantimes.co.jp/feed/",
            "https://www.koreatimes.co.kr/www/rss/rss.xml",
            "https://www.taipeitimes.com/xml/rss/feat.rss",
            "https://www.straitstimes.com/news/world/rss.xml",
            "https://www.bangkokpost.com/rss/data/news.xml",
            # Latin American News
            "https://riotimesonline.com/feed/",
            "https://mexiconewsdaily.com/feed/",
            "https://www.batimes.com.ar/feed",
            # African News
            "https://africanews.com/rss/news",
            "https://www.dailymaverick.co.za/rss/",
            "https://allafrica.com/tools/headlines/rdf/latest/headlines.rdf",
            # Oceania News
            "https://www.abc.net.au/news/feed/1948/rss.xml",
            "https://www.nzherald.co.nz/arc/outboundfeeds/rss/curated/78/?outputType=xml&_ga=2.172515608.1955944642.1609809093-1604323447.1609809093",
            # Energy & Climate
            "https://www.eenews.net/api/feeds/rss/eedaily/",
            "https://www.climatechangenews.com/feed/",
            "https://insideclimatenews.org/feed/",
            # Health & Medicine
            "https://rss.nytimes.com/services/xml/rss/nyt/Health.xml",
            "https://www.statnews.com/feed/",
            "https://www.medscape.com/cx/rssfeeds/2700.xml",
            # Space & Aviation
            "https://spacenews.com/feed/",
            "https://www.space.com/feeds/all",
            "https://www.nasa.gov/rss/dyn/breaking_news.rss",
            "https://www.flightglobal.com/feed",
            "https://www.airspacemag.com/rss/latest-stories/",  # Air & Space Magazine
        ]

        TOPICS: List[str] = ["markets"]
        INTERVAL: int = 30
        DB_PATH: str = "sentiment.db"
        VECTOR_INDEX_PATH: str = "vector.index"
        RULES_PATH: str = "rules.yml"
        SIM_PATH: str = "simulations.csv"
        WEBSOCKET_PORT: int = 8765
        GRADIO_PORT: int = 7860
        OPENAI_API_KEY: str = (
            "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"
        )

        class Config:
            env_file = ".env"

    settings = Settings()

except ImportError:  # pragma: no cover - fallback without pydantic

    @dataclass
    class Settings:  # type: ignore[no-redef]
        """Fallback settings when pydantic-settings is not available."""

        NEWSAPI_KEY: str = os.getenv("NEWSAPI_KEY", "027e167533f7488bb9935e9ab1874e72")
        RSS_FEEDS: List[str] = field(
            default_factory=lambda: DEFAULT_RSS_SOURCES
            or [
                "https://feeds.bbci.co.uk/news/world/rss.xml",
                "https://www.aljazeera.com/xml/rss/all.xml",
            ]
        )
        TOPICS: List[str] = field(
            default_factory=lambda: [
                t.strip()
                for t in os.getenv("TOPICS", "markets").split(",")
                if t.strip()
            ]
        )
        INTERVAL: int = int(os.getenv("INTERVAL", "30"))
        DB_PATH: str = os.getenv("DB_PATH", "sentiment.db")
        VECTOR_INDEX_PATH: str = os.getenv("VECTOR_INDEX_PATH", "vector.index")
        RULES_PATH: str = os.getenv("RULES_PATH", "rules.yml")
        SIM_PATH: str = os.getenv("SIM_PATH", "simulations.csv")
        WEBSOCKET_PORT: int = int(os.getenv("WEBSOCKET_PORT", "8765"))
        GRADIO_PORT: int = int(os.getenv("GRADIO_PORT", "7860"))
        OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    settings = Settings()
