"""Command line interface for the simplified sentiment bot."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from typing import List

from rich.console import Console
from rich.table import Table

from . import aggregate, fetcher
from .analyzer import Analyzer
from .config import WINDOWS


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="News sentiment and volatility bot")
    parser.add_argument("--window", choices=WINDOWS.keys(), default="day")
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--keywords", type=str, default="")
    parser.add_argument("--topic", action="append", default=[])
    parser.add_argument("--region", action="append", default=[])
    parser.add_argument("--conflict", action="store_true")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--newsapi-query")
    parser.add_argument("--output", choices=["json", "table"], default="table")
    parser.add_argument("--match", choices=["any", "all"], default="any")
    return parser


def filter_articles(articles: List[fetcher.Article], args) -> List[fetcher.Article]:
    """Filter articles by keywords/topics/region/conflict settings."""

    kws = [k.strip().lower() for k in args.keywords.replace(",", " ").split() if k.strip()]
    expanded_topics = [t.lower() for t in args.topic]

    filtered = []
    for art in articles:
        text = f"{art.title} {art.text}".lower()
        conds = []
        if kws:
            conds.append(any(k in text for k in kws))
        if expanded_topics:
            from .config import TOPIC_MAP

            topic_words = []
            for t in expanded_topics:
                topic_words.extend(TOPIC_MAP.get(t, []))
            conds.append(any(w in text for w in topic_words))
        if args.conflict:
            from .config import CONFLICT_KEYWORDS

            conds.append(any(w in text for w in CONFLICT_KEYWORDS))
        if args.region:
            regions = aggregate.assign_regions(text)
            conds.append(any(r.lower() in [x.lower() for x in args.region] for r in regions))

        if not conds:
            filtered.append(art)
        else:
            if args.match == "any" and any(conds):
                filtered.append(art)
            elif args.match == "all" and all(conds):
                filtered.append(art)
    return filtered


async def run(args) -> dict:
    until = _parse_iso(args.until) if args.until else datetime.now(timezone.utc)
    since = _parse_iso(args.since) if args.since else until - WINDOWS[args.window]

    if args.limit <= 0:
        articles: List[fetcher.Article] = []
    else:
        articles = await fetcher.fetch_all(since, until, args.limit, args.newsapi_query)
    articles = filter_articles(articles, args)

    analyzer = Analyzer()
    for art in articles:
        result = analyzer.analyze(f"{art.title} {art.text}")
        art.volatility = result.volatility

    keywords = [k.strip() for k in args.keywords.replace(",", " ").split() if k.strip()]
    summary = aggregate.aggregate(articles, keywords, args.topic, args.conflict)
    meta = {
        "analyzed": len(articles),
        "low_quality": analyzer.low_quality,
    }
    return {"meta": meta, **summary}


def output_table(result: dict) -> None:
    console = Console()
    meta = result.get("meta", {})
    console.print(
        f"Analyzed: {meta.get('analyzed', 0)} articles | low_quality={meta.get('low_quality')}"
    )

    table = Table("Region", "Articles", "Volatility")
    for region, stats in result["regions"].items():
        table.add_row(region, str(stats["count"]), f"{stats['volatility']:.3f}")
    console.print(table)

    for region, stats in result["regions"].items():
        if stats["keywords"]:
            console.print(f"Top keywords/topics for {region}")
            t = Table("Name", "Count", "Volatility")
            for kw in stats["keywords"]:
                t.add_row(kw["name"], str(kw["count"]), f"{kw['volatility']:.3f}")
            console.print(t)

    if result["articles"]:
        console.print("Top contributing articles")
        t = Table("Volatility", "Source", "Title")
        for art in result["articles"]:
            t.add_row(f"{art['volatility']:.3f}", art["source"], art["title"])
        console.print(t)


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = asyncio.run(run(args))
    if args.output == "json":
        json.dump(result, sys.stdout)
    else:
        output_table(result)


if __name__ == "__main__":  # pragma: no cover
    main()

