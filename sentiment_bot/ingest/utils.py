"""Shared utilities for data ingestion."""

import re
import hashlib
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from dateutil import parser as dateutil_parser
import logging

logger = logging.getLogger(__name__)


def strip_html(html: str) -> str:
    """Remove HTML tags and return clean text."""
    if not html:
        return ""
    try:
        soup = BeautifulSoup(html, "lxml")
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        return soup.get_text(" ", strip=True)
    except Exception as e:
        logger.warning(f"Failed to strip HTML: {e}")
        # Fallback to regex
        return re.sub("<[^<]+?>", " ", html)


def make_id(*parts: str) -> str:
    """Generate a stable ID from parts."""
    base = "||".join([str(p) for p in parts if p])
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:40]


def parse_date(s: str) -> Optional[datetime]:
    """Parse date string to timezone-aware datetime."""
    if not s:
        return datetime.now(timezone.utc)
    try:
        if isinstance(s, (int, float)):
            # Unix timestamp
            return datetime.fromtimestamp(s, timezone.utc)
        dt = dateutil_parser.parse(s)
        if dt is None:
            return datetime.now(timezone.utc)
        return dt
    except Exception as e:
        logger.warning(f"Failed to parse date '{s}': {e}")
        return datetime.now(timezone.utc)


def norm(item: dict) -> dict:
    """Normalize item to ensure required keys exist."""
    # Ensure all required keys
    normalized = {
        "id": item.get("id", ""),
        "source": item.get("source", "unknown"),
        "subsource": item.get("subsource"),
        "author": item.get("author"),
        "title": item.get("title"),
        "text": item.get("text", ""),
        "url": item.get("url", ""),
        "published_at": item.get("published_at"),
        "lang": item.get("lang"),
        "raw": item.get("raw"),
    }

    # Ensure published_at is datetime
    if not isinstance(normalized["published_at"], datetime):
        normalized["published_at"] = parse_date(normalized["published_at"])

    # Truncate extremely long text
    if normalized["text"] and len(normalized["text"]) > 50000:
        normalized["text"] = normalized["text"][:50000] + "..."

    return normalized


def clean_text(text: str) -> str:
    """Clean text by normalizing whitespace."""
    if not text:
        return ""

    # Strip HTML if present
    text = strip_html(text)

    # Normalize whitespace - preserve line breaks but remove excess
    # Replace multiple spaces with single space
    text = re.sub(r"[ \t]+", " ", text)
    # Replace multiple newlines with maximum 2 newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Remove leading/trailing whitespace
    return text.strip()


def parse_since_window(s: str) -> Optional[datetime]:
    """Parse since window string to timezone-aware datetime."""
    if not s:
        return None

    # Handle relative time formats (24h, 7d, etc.)
    if re.match(r"^\d+[hdwmy]$", s.lower()):
        num = int(s[:-1])
        unit = s[-1].lower()

        if unit == "h":
            delta = timedelta(hours=num)
        elif unit == "d":
            delta = timedelta(days=num)
        elif unit == "w":
            delta = timedelta(weeks=num)
        elif unit == "m":
            delta = timedelta(days=num * 30)  # Approximate
        elif unit == "y":
            delta = timedelta(days=num * 365)  # Approximate
        else:
            logger.warning(f"Unknown time unit in since: {s}")
            return None

        return datetime.now(timezone.utc) - delta

    # Try parsing as absolute date
    try:
        dt = dateutil_parser.parse(s)
        # Make timezone-aware if naive
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception as e:
        logger.warning(f"Failed to parse since window '{s}': {e}")
        return None


def keyword_match(rec: dict, keywords: List[str]) -> bool:
    """Check if record matches any of the keywords (case-insensitive)."""
    if not keywords:
        return True

    # Combine title and text for searching
    haystack = f"{rec.get('title', '')} {rec.get('text', '')}".lower()

    # Check if any keyword matches
    return any(keyword.lower() in haystack for keyword in keywords)


def normalize_url(url: str) -> str:
    """Normalize URL for deduplication (remove fragments, etc.)."""
    if not url:
        return ""

    # Remove fragment identifier
    if "#" in url:
        url = url.split("#")[0]

    # Remove common tracking parameters
    if "?" in url:
        base_url, params = url.split("?", 1)
        # Keep only essential params, remove tracking
        essential_params = []
        for param in params.split("&"):
            if "=" not in param:
                continue
            key, value = param.split("=", 1)
            # Skip common tracking parameters
            if key.lower() in [
                "utm_source",
                "utm_medium",
                "utm_campaign",
                "utm_content",
                "utm_term",
                "fbclid",
                "gclid",
                "_ga",
                "_gl",
                "ref",
                "source",
            ]:
                continue
            essential_params.append(param)

        if essential_params:
            url = f"{base_url}?{'&'.join(essential_params)}"
        else:
            url = base_url

    return url.rstrip("/")
