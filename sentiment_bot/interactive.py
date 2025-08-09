from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import List, Tuple

from rich.console import Console
from rich.prompt import Prompt

from .config import REGION_MAP, TOPIC_MAP, WINDOWS

# Ordered choices for regions and topics used in the interactive CLI
REGION_ORDER = [
    "africa",
    "asia",
    "europe",
    "latin_america",
    "middle_east",
    "north_america",
    "oceania",
]

TOPIC_ORDER = [
    "energy",
    "elections",
    "sanctions",
    "cybersecurity",
    "protests",
    "trade",
    "banking",
    "sovereign_risk",
    "supply_chain",
    "climate",
    "migration",
    "health",
    "conflict",
    "technology",
    "defense",
    "natural_disasters",
    "terrorism",
    "infrastructure",
    "diplomacy",
]

REGION_CHOICES: List[Tuple[str, str]] = [
    ("All Regions", "all"),
    *[(name.replace("_", " ").title(), name) for name in REGION_ORDER],
]

TOPIC_CHOICES: List[Tuple[str, str]] = [
    ("All Topics", "all"),
    *[(name.replace("_", " ").title(), name) for name in TOPIC_ORDER],
]

WINDOW_CHOICES: List[Tuple[str, str]] = [
    ("Minute", "minute"),
    ("Half Hour", "half_hour"),
    ("Hour", "hour"),
    ("Day", "day"),
    ("Week", "week"),
    ("Month", "month"),
    ("Year", "year"),
]

REGION_KEYS = [c[1] for c in REGION_CHOICES]
TOPIC_KEYS = [c[1] for c in TOPIC_CHOICES]
WINDOW_KEYS = [c[1] for c in WINDOW_CHOICES]


def parse_multi_selection(selection: str, options: List[str]) -> List[str]:
    """Parse a comma separated selection of numbers into option keys.

    Returns an empty list when ``all`` is chosen.
    Raises ``ValueError`` on invalid input.
    """

    if selection.strip().lower() in {"all", ""}:
        return []
    parts = [p.strip() for p in selection.split(",") if p.strip()]
    result = []
    for part in parts:
        if not part.isdigit():
            raise ValueError("invalid selection")
        idx = int(part) - 1
        if idx < 0 or idx >= len(options):
            raise ValueError("invalid selection")
        if idx == 0:
            return []
        result.append(options[idx])
    return result


def parse_single_selection(selection: str, options: List[str]) -> str:
    """Parse a single numeric selection into an option key."""

    if not selection.strip().isdigit():
        raise ValueError("invalid selection")
    idx = int(selection) - 1
    if idx < 0 or idx >= len(options):
        raise ValueError("invalid selection")
    return options[idx]


def run_interactive_mode() -> None:
    """Run an interactive prompt for region/topic/time selection and analysis."""

    from . import analyzer, fetcher

    console = Console()

    def _prompt(message: str, choices, keys, multi: bool):
        while True:
            for idx, (label, _) in enumerate(choices, start=1):
                console.print(f"{idx}. {label}")
            answer = Prompt.ask(message)
            try:
                if multi:
                    return parse_multi_selection(answer, keys)
                return parse_single_selection(answer, keys)
            except ValueError:
                console.print("Invalid selection, please try again.")

    regions = _prompt("Select region(s)", REGION_CHOICES, REGION_KEYS, True)
    topics = _prompt("Select topic(s)", TOPIC_CHOICES, TOPIC_KEYS, True)
    window_key = _prompt("Select time frame", WINDOW_CHOICES, WINDOW_KEYS, False)
    window = WINDOWS[window_key]

    def _try_parse_iso(dt_str: str) -> datetime | None:
        try:
            dt = datetime.fromisoformat(dt_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return None

    async def _main() -> None:
        articles, stats = await fetcher.gather_rss()
        if not articles or stats.get("total", 0) == 0:
            console.print("No articles found")
            return

        start_ts = datetime.now(timezone.utc) - window
        filtered = []
        for art in articles:
            pub = art.published
            if isinstance(pub, datetime):
                pub_dt = pub if pub.tzinfo else pub.replace(tzinfo=timezone.utc)
            else:
                pub_dt = _try_parse_iso(pub or "")
            if pub_dt and pub_dt < start_ts:
                continue
            text = f"{art.title} {art.text}".lower()
            if regions:
                region_words = [
                    w.lower() for r in regions for w in REGION_MAP.get(r, [])
                ]
                if not any(w in text for w in region_words):
                    continue
            if topics:
                topic_words = [w.lower() for t in topics for w in TOPIC_MAP.get(t, [])]
                if not any(w in text for w in topic_words):
                    continue
            filtered.append(art)

        if not filtered:
            console.print("No articles found")
            return

        analyses = [analyzer.analyze(a.text) for a in filtered]
        snapshot = analyzer.aggregate(analyses)
        results = {
            "volatility": snapshot.volatility,
            "model_confidence": snapshot.confidence,
            "articles": filtered,
        }

        analyzer.display_ingestion_summary(stats)
        analyzer.display_analysis_results(results)

        choices = ["Summary", "Articles", "Analysis", "Exit"]
        while True:
            choice = Prompt.ask(
                "What would you like to view?", choices=choices, default="Summary"
            )
            if choice == "Summary":
                analyzer.display_ingestion_summary(stats)
            elif choice == "Articles":
                console.rule("Fetched Articles")
                for art in filtered:
                    console.print(f"- {art.title}")
            elif choice == "Analysis":
                analyzer.display_analysis_results(results)
            else:
                break

    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        console.print("Interrupted. Exiting cleanly.")
