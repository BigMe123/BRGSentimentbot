"""Configuration helpers for the simplified sentiment bot.

This module exposes a small collection of constants and helpers used by the
CLI.  The goal is to keep configuration light weight and environment driven.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
import os

# ---------------------------------------------------------------------------
# RSS sources

ROOT = Path(__file__).resolve().parent.parent


def load_rss_sources() -> list[str]:
    """Return the list of RSS feed URLs.

    The file ``rss_sources.txt`` lives in the project root by default.  A
    different location can be provided via the ``RSS_SOURCES_FILE``
    environment variable.  Lines starting with ``#`` are ignored.
    """

    default_file = ROOT / "rss_sources.txt"
    path = Path(os.getenv("RSS_SOURCES_FILE", default_file))
    sources: list[str] = []
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                sources.append(line)
    return sources


# ---------------------------------------------------------------------------
# Time windows

WINDOWS = {
    "minute": timedelta(minutes=1),
    "half_hour": timedelta(minutes=30),
    "hour": timedelta(hours=1),
    "day": timedelta(days=1),
    "week": timedelta(weeks=1),
    "month": timedelta(days=30),
    "year": timedelta(days=365),
}


# ---------------------------------------------------------------------------
# Keyword maps

REGION_MAP = {
    "Europe": [
        "europe",
        "france",
        "germany",
        "italy",
        "spain",
        "uk",
        "britain",
        "london",
        "paris",
    ],
    "Asia": [
        "asia",
        "china",
        "beijing",
        "japan",
        "tokyo",
        "korea",
        "india",
    ],
    "Middle East": ["middle east", "iran", "iraq", "israel", "syria", "palestine"],
    "Africa": ["africa", "nigeria", "south africa", "kenya", "ethiopia"],
    "Americas": ["united states", "usa", "america", "canada", "brazil", "mexico"],
}

TOPIC_MAP = {
    "energy": ["energy", "oil", "gas", "electricity", "power"],
    "sanctions": ["sanction", "embargo"],
    "border": ["border", "boundary"],
    "elections": ["election", "vote"],
    "trade": ["trade", "tariff"],
    "cyber": ["cyber", "hacker", "ransomware"],
    "terrorism": ["terrorism", "terrorist", "bomb"],
    "protests": ["protest", "demonstration"],
}

CONFLICT_KEYWORDS = [
    "airstrike",
    "mobilization",
    "missile",
    "drone",
    "clashes",
    "shelling",
    "coup",
    "riot",
    "blockade",
    "offensive",
    "ceasefire",
]


# Optional NewsAPI configuration
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")
NEWSAPI_DOMAINS = os.getenv("NEWSAPI_DOMAINS")


@dataclass
class Meta:
    """Runtime metadata returned with results."""

    feeds_attempted: int = 0
    feeds_succeeded: int = 0
    articles_fetched: int = 0
    articles_analyzed: int = 0

