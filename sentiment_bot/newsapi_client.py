"""Simple asynchronous client for NewsAPI with SQLite caching."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import List

import aiosqlite

from .config import settings
from .fetcher import ArticleData

CACHE_PATH = Path("newsapi_cache.db")
TTL = 60 * 60  # one hour


async def _fetch_remote(topic: str) -> List[ArticleData]:  # pragma: no cover - network
    from newsapi import NewsApiClient

    client = NewsApiClient(api_key=settings.NEWSAPI_KEY)
    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(None, client.get_top_headlines, None, "en", topic)
    articles = []
    for a in data.get("articles", []):
        articles.append(
            ArticleData(
                url=a.get("url", ""),
                title=a.get("title", ""),
                text=a.get("description", ""),
            )
        )
    return articles


async def fetch_top_headlines(topics: List[str]) -> List[ArticleData]:
    """Fetch headlines for ``topics`` using a TTL cache."""

    CACHE_PATH.touch(exist_ok=True)
    async with aiosqlite.connect(CACHE_PATH) as db:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS cache (topic TEXT PRIMARY KEY, ts REAL, data TEXT)"
        )
        await db.commit()
        results: list[ArticleData] = []
        for topic in topics:
            cur = await db.execute("SELECT ts, data FROM cache WHERE topic=?", (topic,))
            row = await cur.fetchone()
            if row and time.time() - row[0] < TTL:
                payload = json.loads(row[1])
                for a in payload:
                    results.append(ArticleData(**a))
                continue
            try:
                fresh = await _fetch_remote(topic)
            except Exception:
                fresh = []
            await db.execute(
                "REPLACE INTO cache(topic, ts, data) VALUES(?,?,?)",
                (topic, time.time(), json.dumps([a.__dict__ for a in fresh])),
            )
            await db.commit()
            results.extend(fresh)
        return results
