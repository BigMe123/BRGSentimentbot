"""Aggregation helpers for computing regional and keyword volatility."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable, List
import re

from .config import CONFLICT_KEYWORDS, REGION_MAP, TOPIC_MAP
from .fetcher import Article


def _match(text: str, candidates: Iterable[str]) -> list[str]:
    text = text.lower()
    found = []
    for c in candidates:
        if re.search(rf"\b{re.escape(c)}s?\b", text):
            found.append(c)
    return found


def assign_regions(text: str) -> list[str]:
    matches = []
    for region, aliases in REGION_MAP.items():
        for alias in aliases:
            if re.search(rf"\b{re.escape(alias)}\b", text.lower()):
                matches.append(region)
                break
    return matches or ["Unassigned"]


def aggregate(
    articles: List[Article],
    keywords: list[str] | None = None,
    topics: list[str] | None = None,
    conflict: bool = False,
):
    """Aggregate volatility by region and keywords/topics."""

    keywords = [k.lower() for k in (keywords or [])]
    topic_keywords: list[str] = []
    if topics:
        for t in topics:
            topic_keywords.extend(TOPIC_MAP.get(t.lower(), []))
    all_keywords = keywords + topic_keywords
    if conflict:
        all_keywords += CONFLICT_KEYWORDS

    region_stats: dict[str, dict] = defaultdict(
        lambda: {"count": 0, "volatility": 0.0, "keywords": defaultdict(lambda: {"count": 0, "volatility": 0.0})}
    )

    for art in articles:
        text = f"{art.title} {art.text}".lower()
        regions = assign_regions(text)
        kw_found = _match(text, all_keywords)
        for region in regions:
            rs = region_stats[region]
            rs["count"] += 1
            rs["volatility"] += getattr(art, "volatility", 0.0)
            for kw in kw_found:
                ks = rs["keywords"][kw]
                ks["count"] += 1
                ks["volatility"] += getattr(art, "volatility", 0.0)

    for region, rs in region_stats.items():
        if rs["count"]:
            rs["volatility"] /= rs["count"]
        rs["keywords"] = sorted(
            (
                {
                    "name": k,
                    "count": v["count"],
                    "volatility": v["volatility"] / v["count"],
                }
                for k, v in rs["keywords"].items()
                if v["count"]
            ),
            key=lambda x: x["volatility"],
            reverse=True,
        )[:5]

    # top articles by volatility
    top_articles = sorted(
        (
            {
                "title": a.title,
                "source": a.source,
                "url": a.url,
                "volatility": getattr(a, "volatility", 0.0),
            }
            for a in articles
        ),
        key=lambda x: x["volatility"],
        reverse=True,
    )[:10]

    return {"regions": dict(region_stats), "articles": top_articles}

