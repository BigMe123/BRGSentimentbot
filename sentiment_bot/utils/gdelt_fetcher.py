"""
GDELT integration — free, unlimited global event data.
Uses the GDELT DOC 2.0 API for article search.
"""

import requests
import hashlib
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"


def fetch_gdelt_articles(
    query: Optional[str] = None,
    days_back: int = 1,
    max_articles: int = 250,
    language: str = "english",
) -> List[Dict]:
    """
    Fetch articles from GDELT DOC 2.0 API.
    Free, no API key needed, global coverage.

    Returns list of article dicts in the same format as TheNewsAPI/RSS fetchers.
    """
    params = {
        "query": query or "",
        "mode": "ArtList",
        "maxrecords": str(min(max_articles, 250)),  # GDELT caps at 250
        "format": "json",
        "sort": "DateDesc",
        "timespan": f"{days_back * 24 * 60}min",  # timespan in minutes
    }

    if language:
        params["sourcelang"] = language[:2]  # "en" for english

    try:
        resp = requests.get(GDELT_DOC_API, params=params, timeout=15)
        if resp.status_code != 200:
            logger.warning(f"GDELT API returned {resp.status_code}")
            return []

        data = resp.json()
        raw_articles = data.get("articles", [])

        articles = []
        seen_urls = set()
        for art in raw_articles:
            url = art.get("url", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            # Extract domain from URL
            from urllib.parse import urlparse
            domain = urlparse(url).netloc.replace("www.", "")

            articles.append({
                "title": art.get("title", ""),
                "link": url,
                "description": art.get("seendate", ""),
                "content": "",  # GDELT doesn't provide full text — scraped later
                "domain": domain,
                "published": _parse_gdelt_date(art.get("seendate", "")),
                "published_date": None,
                "url_hash": hashlib.md5(url.encode()).hexdigest(),
                "authors": [],
                "summary": art.get("title", ""),
                "gdelt_tone": art.get("tone", 0),
                "gdelt_source_country": art.get("sourcecountry", ""),
                "gdelt_language": art.get("language", ""),
                "_source_api": "gdelt",
            })

        return articles

    except Exception as e:
        logger.warning(f"GDELT fetch failed: {e}")
        return []


def _parse_gdelt_date(date_str: str) -> str:
    """Parse GDELT date format (YYYYMMDDTHHmmSSZ) to ISO."""
    if not date_str:
        return ""
    try:
        dt = datetime.strptime(date_str[:15], "%Y%m%dT%H%M%S")
        return dt.isoformat()
    except Exception:
        return date_str
