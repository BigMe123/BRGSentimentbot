"""
Unified CLI for BRG Sentiment Analysis Bot.
Uses NewsAPI as the primary article source, with RSS as fallback.
"""

import asyncio
import typer
import time
import json
import hashlib
import logging
import re
from pathlib import Path
from typing import Optional, List, Dict
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import rich.box
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from datetime import datetime, timedelta
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from .config import settings
from .utils.run_id import make_run_id
from .utils.output_writer import OutputWriter
from .utils.output_models import (
    ArticleRecord,
    RunSummary,
    Sentiment,
    SignalData,
    EntityCount,
    SourceCount,
    AnalysisBlock,
    DiversityBlock,
    CollectionBlock,
    ConfigBlock,
)
from .utils.entity_extractor import EntityExtractor
from .utils.source_tiers import get_tier, get_weight, tier_label

app = typer.Typer(
    name="bsgbot",
    help="BRG Sentiment Bot - NewsAPI-powered sentiment analysis",
)
console = Console()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Source name mapping — maps domains/feed titles to clean outlet names
# ---------------------------------------------------------------------------

SOURCE_NAME_MAP = {
    # TheNewsAPI domains + RSS feed domains
    "bbc.co.uk": "BBC News", "bbc.com": "BBC News", "feeds.bbci.co.uk": "BBC News",
    "cnn.com": "CNN", "edition.cnn.com": "CNN",
    "nytimes.com": "New York Times", "rss.nytimes.com": "New York Times",
    "washingtonpost.com": "Washington Post",
    "theguardian.com": "The Guardian",
    "aljazeera.com": "Al Jazeera",
    "reuters.com": "Reuters",
    "apnews.com": "Associated Press",
    "cnbc.com": "CNBC",
    "wsj.com": "Wall Street Journal",
    "bloomberg.com": "Bloomberg",
    "ft.com": "Financial Times",
    "economist.com": "The Economist",
    "politico.com": "Politico",
    "thehill.com": "The Hill",
    "npr.org": "NPR",
    "foxnews.com": "Fox News",
    "nbcnews.com": "NBC News",
    "cbsnews.com": "CBS News",
    "abcnews.go.com": "ABC News",
    "france24.com": "France 24",
    "dw.com": "Deutsche Welle",
    "euronews.com": "Euronews",
    "spiegel.de": "Der Spiegel",
    "japantimes.co.jp": "Japan Times",
    "scmp.com": "South China Morning Post",
    "straitstimes.com": "Straits Times",
    "abc.net.au": "ABC Australia",
    "arstechnica.com": "Ars Technica",
    "wired.com": "Wired",
    "techcrunch.com": "TechCrunch",
    "theverge.com": "The Verge",
    "zdnet.com": "ZDNet",
    "nature.com": "Nature",
    "sciencedaily.com": "Science Daily",
    "defensenews.com": "Defense News",
    "janes.com": "Janes",
    "military.com": "Military.com",
    "defenseone.com": "Defense One",
    "breakingdefense.com": "Breaking Defense",
    "foreignaffairs.com": "Foreign Affairs",
    "cfr.org": "CFR",
    "csis.org": "CSIS",
    "brookings.edu": "Brookings",
    "rand.org": "RAND",
    "atlanticcouncil.org": "Atlantic Council",
    "bellingcat.com": "Bellingcat",
    "theintercept.com": "The Intercept",
    "foreignpolicy.com": "Foreign Policy",
    "lawfareblog.com": "Lawfare",
    "warontherocks.com": "War on the Rocks",
    "mei.edu": "Middle East Institute",
    "nato.int": "NATO",
    "spacenews.com": "SpaceNews",
    "space.com": "Space.com",
    "nasa.gov": "NASA",
    "marketwatch.com": "MarketWatch",
    "forbes.com": "Forbes",
    "axios.com": "Axios",
    "theconversation.com": "The Conversation",
    "livemint.com": "Mint",
    "economictimes.indiatimes.com": "Economic Times",
    "indiatoday.intoday.in": "India Today",
    "bangkokpost.com": "Bangkok Post",
    "dailymaverick.co.za": "Daily Maverick",
    "nzherald.co.nz": "NZ Herald",
    # RSS feed titles (feedparser returns these)
    "BBC News": "BBC News",
    "BBC News - World": "BBC News",
    "BBC News - Home": "BBC News",
    "Al Jazeera English": "Al Jazeera",
    "Al Jazeera – Breaking News": "Al Jazeera",
    "Al Jazeera – Breaking News, World News and Video from Al Jazeera": "Al Jazeera",
    "CNN.com - RSS Channel - App International Edition": "CNN",
    "CNN.com - Top Stories": "CNN",
    "CNN.com": "CNN",
    "NYT > World": "New York Times",
    "NYT > World News": "New York Times",
    "NYT > Home Page": "New York Times",
    "NYT > Top Stories": "New York Times",
    "NYT > Business": "New York Times",
    "NYT > Technology": "New York Times",
    "NYT > Science": "New York Times",
    "NYT > Politics": "New York Times",
    "NYT > U.S. > Politics": "New York Times",
    "NYT > Health": "New York Times",
    "Washington Post": "Washington Post",
    "The Guardian": "The Guardian",
    "CNBC": "CNBC",
    "The Hill": "The Hill",
    "NPR Topics: News": "NPR",
    "Defense News": "Defense News",
    "Defense One": "Defense One",
    "War on the Rocks": "War on the Rocks",
    "Brookings": "Brookings",
    "RAND Blog": "RAND",
    "Lawfare": "Lawfare",
    "Ars Technica": "Ars Technica",
    "TechCrunch": "TechCrunch",
    "The Verge": "The Verge",
    "Wired": "Wired",
    "Nature - Issue": "Nature",
    "SpaceNews": "SpaceNews",
}


def _normalize_source_name(raw: str) -> str:
    """Map a domain or feed title to a clean, recognizable outlet name."""
    if not raw or raw == "Unknown" or raw == "unknown":
        return "Unknown"

    # Direct match
    if raw in SOURCE_NAME_MAP:
        return SOURCE_NAME_MAP[raw]

    # Strip www. and try domain match
    clean = raw.lower().replace("www.", "").strip()
    for domain, name in SOURCE_NAME_MAP.items():
        if clean == domain.lower() or clean.endswith("." + domain.lower()):
            return name

    # Prefix match for RSS feed titles (e.g. "NYT > World News - ..." matches "NYT > World News")
    raw_lower = raw.lower()
    for key, name in SOURCE_NAME_MAP.items():
        if raw_lower.startswith(key.lower()):
            return name

    # Keyword match for known outlets in long feed titles
    _KEYWORD_MAP = {
        "al jazeera": "Al Jazeera", "bbc": "BBC News", "cnn": "CNN",
        "new york times": "New York Times", "nyt": "New York Times",
        "washington post": "Washington Post", "guardian": "The Guardian",
        "cnbc": "CNBC", "reuters": "Reuters", "france 24": "France 24",
        "deutsche welle": "Deutsche Welle", "euronews": "Euronews",
        "npr": "NPR", "politico": "Politico",
        "us top news and analysis": "CNBC",
        "japan times": "Japan Times", "straits times": "Straits Times",
        "south china morning post": "South China Morning Post",
        "sciencedaily": "Science Daily", "le monde": "Le Monde",
        "daily maverick": "Daily Maverick", "realcleardefense": "RealClearDefense",
        "new scientist": "New Scientist", "der spiegel": "Der Spiegel",
        "american enterprise": "AEI", "begin-sadat": "BESA Center",
    }
    for kw, name in _KEYWORD_MAP.items():
        if kw in raw_lower:
            return name

    # If it looks like a domain, clean it up
    if "." in raw and "/" not in raw:
        return raw.replace("www.", "")

    return raw


# ---------------------------------------------------------------------------
# NewsAPI fetching
# ---------------------------------------------------------------------------

def _parse_thenewsapi_article(art: Dict) -> Dict:
    """Normalise a single TheNewsAPI article dict."""
    from dateutil import parser as dp

    published_date = None
    published_str = art.get("published_at", "")
    if published_str:
        try:
            published_date = dp.parse(published_str)
        except Exception:
            pass

    return {
        "title": art.get("title", ""),
        "link": art.get("url", ""),
        "description": art.get("description", "") or "",
        "content": art.get("description", "") or "",  # full text fetched later via newspaper3k
        "domain": _normalize_source_name(art.get("source", "Unknown")),
        "published": published_str,
        "published_date": published_date,
        "url_hash": hashlib.md5((art.get("url") or "").encode()).hexdigest(),
        "authors": [],
        "summary": art.get("snippet", "") or art.get("description", "") or "",
        "categories": art.get("categories", []),
        "uuid": art.get("uuid", ""),
    }


def _fetch_thenewsapi(
    query: Optional[str] = None,
    category: Optional[str] = None,
    language: str = "en",
    days_back: int = 1,
    target_articles: int = 300,
) -> List[Dict]:
    """Fetch articles from TheNewsAPI (paid). Paginates to hit target."""
    import requests as req

    api_key = settings.THENEWSAPI_KEY
    if not api_key:
        console.print("[red]THENEWSAPI_KEY not set in .env[/red]")
        return []

    base_url = "https://api.thenewsapi.com/v1/news"
    all_articles: List[Dict] = []
    seen_urls: set = set()

    # Build params
    published_after = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%dT00:00:00")
    params: Dict = {
        "api_token": api_key,
        "language": language,
        "published_after": published_after,
        "limit": 25,  # max per page on TheNewsAPI
    }

    if query:
        params["search"] = query
        params["search_fields"] = "title,description,keywords,main_text"
        endpoint = f"{base_url}/all"
    elif category:
        params["categories"] = category
        endpoint = f"{base_url}/top"
    else:
        endpoint = f"{base_url}/top"

    # Paginate until we hit target
    page = 1
    max_pages = (target_articles // 25) + 2  # safety cap

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"[cyan]Fetching articles (target: {target_articles})...",
            total=target_articles,
        )

        while len(all_articles) < target_articles and page <= max_pages:
            params["page"] = page
            try:
                resp = req.get(endpoint, params=params, timeout=15)
                if resp.status_code == 402:
                    console.print("[yellow]Usage limit reached for this month[/yellow]")
                    break
                if resp.status_code == 429:
                    console.print("[yellow]Rate limit hit, waiting...[/yellow]")
                    import time as _time
                    _time.sleep(2)
                    continue
                if resp.status_code != 200:
                    console.print(f"[yellow]API error {resp.status_code}: {resp.text[:100]}[/yellow]")
                    break

                data = resp.json()
                articles = data.get("data", [])
                if not articles:
                    break

                for art in articles:
                    url = art.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_articles.append(_parse_thenewsapi_article(art))

                progress.update(task, completed=min(len(all_articles), target_articles))
                page += 1

                # Check if we've exhausted results
                meta = data.get("meta", {})
                total_found = meta.get("found", 0)
                if page * 25 > total_found:
                    break

            except Exception as e:
                logger.warning(f"TheNewsAPI page {page} failed: {e}")
                break

    # Show usage info from last response headers if available
    try:
        remaining = resp.headers.get("x-usagelimit-remaining", "?")
        limit = resp.headers.get("x-usagelimit-limit", "?")
        console.print(f"[dim]Credits used: {len(all_articles)} | Remaining: {remaining}/{limit}[/dim]")
    except Exception:
        pass

    console.print(f"[green]TheNewsAPI returned {len(all_articles)} unique articles[/green]")
    return all_articles[:target_articles]


# Legacy NewsAPI fetcher (kept as fallback)
def _fetch_newsapi_legacy(
    query: Optional[str] = None,
    category: Optional[str] = None,
    country: Optional[str] = None,
    page_size: int = 100,
    days_back: int = 1,
) -> List[Dict]:
    """Fetch from NewsAPI.org (free tier fallback)."""
    from dateutil import parser as dp

    try:
        from newsapi import NewsApiClient
    except ImportError:
        console.print("[yellow]newsapi-python not installed[/yellow]")
        return []

    api_key = settings.NEWSAPI_KEY
    if not api_key:
        return []

    api = NewsApiClient(api_key=api_key)
    articles: List[Dict] = []

    try:
        if query:
            from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
            resp = api.get_everything(
                q=query, from_param=from_date, language="en",
                sort_by="publishedAt", page_size=min(page_size, 100),
            )
        else:
            kwargs: Dict = {"language": "en", "page_size": min(page_size, 100)}
            if category:
                kwargs["category"] = category
            if country:
                kwargs["country"] = country
            else:
                kwargs["country"] = "us"
            resp = api.get_top_headlines(**kwargs)

        if resp.get("status") == "ok":
            for art in resp.get("articles", []):
                published_date = None
                published_str = art.get("publishedAt", "")
                if published_str:
                    try:
                        published_date = dp.parse(published_str)
                    except Exception:
                        pass
                articles.append({
                    "title": art.get("title", ""),
                    "link": art.get("url", ""),
                    "description": art.get("description", "") or "",
                    "content": art.get("content", "") or "",
                    "domain": (art.get("source") or {}).get("name", "Unknown"),
                    "published": published_str,
                    "published_date": published_date,
                    "url_hash": hashlib.md5((art.get("url") or "").encode()).hexdigest(),
                    "authors": [art["author"]] if art.get("author") else [],
                    "summary": art.get("description", "") or "",
                })
    except Exception as e:
        logger.warning(f"NewsAPI fallback failed: {e}")

    return articles


# ---------------------------------------------------------------------------
# RSS fetching (supplemental)
# ---------------------------------------------------------------------------

async def _fetch_single_rss(session, url):
    try:
        import aiohttp
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
            if response.status == 200:
                import feedparser
                content = await response.text()
                feed = feedparser.parse(content)
                return (feed, url, True)
    except Exception as e:
        logger.debug(f"Error fetching RSS {url}: {e}")
    return (None, url, False)


async def _fetch_rss_articles(rss_urls: List[str]) -> List[Dict]:
    import aiohttp
    from dateutil import parser as date_parser

    articles = []

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        BarColumn(), TimeElapsedColumn(), console=console,
    ) as progress:
        task = progress.add_task("[cyan]Fetching RSS feeds...", total=len(rss_urls))

        async with aiohttp.ClientSession() as session:
            tasks = [_fetch_single_rss(session, url) for url in rss_urls]
            for coro in asyncio.as_completed(tasks):
                feed, url, success = await coro
                progress.advance(task)

                if feed and feed.entries:
                    raw_title = feed.feed.get("title", "Unknown") if hasattr(feed, "feed") else "Unknown"
                    domain = _normalize_source_name(raw_title)

                    for entry in feed.entries[:25]:
                        published_str = entry.get("published", entry.get("updated", ""))
                        published_date = None
                        if published_str:
                            try:
                                published_date = date_parser.parse(published_str)
                            except Exception:
                                pass

                        article = {
                            "title": entry.get("title", ""),
                            "link": entry.get("link", ""),
                            "description": entry.get("summary", entry.get("description", "")),
                            "domain": domain,
                            "published": published_str,
                            "published_date": published_date,
                            "content": (
                                entry.get("content", [{}])[0].get("value", "")
                                if "content" in entry else ""
                            ),
                            "url_hash": hashlib.md5(entry.get("link", "").encode()).hexdigest(),
                        }
                        articles.append(article)

    return articles


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

@app.command()
def run(
    query: Optional[str] = typer.Argument(
        None, help="Search query for NewsAPI (e.g., 'AI regulation', 'oil prices')"
    ),
    output_dir: str = typer.Option(
        "./output", "--output-dir", help="Directory for output files"
    ),
    run_id_seed: Optional[str] = typer.Option(
        None, "--run-id", help="Optional seed for run ID generation"
    ),
    export_csv: bool = typer.Option(
        False, "--export-csv", help="Also export results as CSV"
    ),
    freshness: str = typer.Option(
        "7d", "--freshness", help="Freshness window: 1h, 6h, 24h, 7d, 30d"
    ),
    category: Optional[str] = typer.Option(
        None, "--category", "-c",
        help="NewsAPI category: business, technology, science, health, sports, entertainment, general",
    ),
    country: Optional[str] = typer.Option(
        None, "--country",
        help="2-letter country code for top headlines (e.g., us, gb, de)",
    ),
    region: Optional[str] = typer.Option(
        None, "--region", "-r", help="Post-fetch keyword filter by region (e.g., asia, europe)"
    ),
    topic: Optional[str] = typer.Option(
        None, "--topic", "-t", help="Post-fetch keyword filter by topic (e.g., energy, elections)"
    ),
    page_size: int = typer.Option(
        100, "--page-size", help="Articles per API call (max 100)"
    ),
    target_articles: int = typer.Option(
        300, "--target", "-n", help="Target number of articles (runs multiple queries to reach this)"
    ),
    also_rss: bool = typer.Option(
        True, "--also-rss/--no-rss", help="Fetch from 100+ RSS feeds (BBC, CNN, NYT, etc). On by default."
    ),
    max_feeds: int = typer.Option(
        0, "--max-feeds", help="Limit number of RSS feeds (0 = all)"
    ),
    llm_analysis: bool = typer.Option(
        False, "--llm", help="Use LLM-based analysis (requires OPENAI_API_KEY)"
    ),
    extract_events: bool = typer.Option(
        False, "--extract-events", help="Extract structured events using LLM (requires OPENAI_API_KEY)"
    ),
    summarize: bool = typer.Option(
        False, "--summarize", help="Generate AI summaries (slow — adds ~1s/article)"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-f", help="Output file for results (JSON)"
    ),
    fast: bool = typer.Option(False, "--fast", help="Use VADER for sentiment (dev only, lower quality)"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
):
    """
    Fetch news via NewsAPI, analyze sentiment, and produce structured output.

    Examples:
        bsgbot run                                  # top headlines + 100+ RSS feeds
        bsgbot run "AI regulation"                  # search for a topic
        bsgbot run --category business              # business headlines
        bsgbot run "climate change" --freshness 30d # last 30 days
        bsgbot run --country gb --category technology
        bsgbot run "trade war" --no-rss             # API only, skip RSS
        bsgbot run "trade war" --llm                # use LLM analysis
    """
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Build display label
    source_label = "TheNewsAPI" if settings.THENEWSAPI_KEY else "NewsAPI"
    if also_rss:
        source_label += " + RSS"

    # Header
    console.print()
    if llm_analysis:
        mode_label = "LLM (GPT-4o-mini)"
    elif fast:
        mode_label = "VADER (fast)"
    else:
        mode_label = "RAMME (FinBERT-Tone + FLS + ESG + RoBERTa)"
    # Check HF API status for header
    hf_status = ""
    if not fast and not llm_analysis:
        try:
            from .analyzers import hf_inference as hf
            hf_status = "[green]HF API[/green]" if hf.is_available() else "[yellow]local[/yellow]"
        except Exception:
            hf_status = "[yellow]local[/yellow]"
    query_display = query or "top headlines"
    header_text = (
        f"[bold white]BRG Sentiment Intelligence[/bold white]\n"
        f"[dim]{query_display}  |  {freshness}  |  {mode_label}[/dim]"
    )
    if hf_status:
        header_text += f"  [dim]|[/dim]  {hf_status}"
    if extract_events:
        header_text += f"  [dim]|  events[/dim]"
    if category:
        header_text += f"  [dim]|  {category}[/dim]"
    console.print(Panel(header_text, border_style="blue", padding=(0, 1)))
    console.print()

    asyncio.run(
        _run_async(
            query=query,
            category=category,
            country=country,
            region=region,
            topic=topic,
            page_size=page_size,
            target_articles=target_articles,
            also_rss=also_rss,
            max_feeds=max_feeds,
            freshness=freshness,
            llm_analysis=llm_analysis,
            fast=fast,
            extract_events=extract_events,
            summarize=summarize,
            output=output,
            output_dir=output_dir,
            run_id_seed=run_id_seed,
            export_csv=export_csv,
        )
    )


async def _run_async(
    query: Optional[str],
    category: Optional[str],
    country: Optional[str],
    region: Optional[str],
    topic: Optional[str],
    page_size: int,
    target_articles: int,
    also_rss: bool,
    max_feeds: int,
    freshness: str,
    llm_analysis: bool,
    fast: bool,
    extract_events: bool,
    summarize: bool,
    output: Optional[str],
    output_dir: str,
    run_id_seed: Optional[str],
    export_csv: bool,
):
    start_time = time.time()
    started_at = datetime.now()

    run_id = make_run_id(region=region, topic=query or topic, started_at=started_at, seed=run_id_seed)
    writer = OutputWriter(output_dir=output_dir, run_id=run_id)
    entity_extractor = EntityExtractor()

    console.print(f"[dim]run {run_id}[/dim]")

    # Step 1: Fetch
    max_age_hours = _parse_freshness(freshness)
    days_back = (max_age_hours // 24) if max_age_hours else 30

    if settings.THENEWSAPI_KEY:
        articles = _fetch_thenewsapi(
            query=query,
            category=category,
            days_back=max(days_back, 1),
            target_articles=target_articles,
        )
    else:
        with console.status("[dim]Fetching articles...[/dim]", spinner="dots"):
            articles = _fetch_newsapi_legacy(
                query=query,
                category=category,
                country=country,
                page_size=page_size,
                days_back=max(days_back, 1),
            )

    rss_count = 0
    if also_rss:
        rss_urls = list(settings.RSS_FEEDS)
        if max_feeds > 0:
            rss_urls = rss_urls[:max_feeds]
        rss_articles = await _fetch_rss_articles(rss_urls)
        rss_count = len(rss_articles)
        articles.extend(rss_articles)

    gdelt_count = 0
    try:
        with console.status("[dim]Fetching GDELT...[/dim]", spinner="dots"):
            from .utils.gdelt_fetcher import fetch_gdelt_articles
            gdelt_articles = fetch_gdelt_articles(
                query=query,
                days_back=max(days_back, 1),
                max_articles=250,
            )
            gdelt_count = len(gdelt_articles)
            for ga in gdelt_articles:
                ga["domain"] = _normalize_source_name(ga.get("domain", "Unknown"))
            articles.extend(gdelt_articles)
    except Exception as e:
        logger.debug(f"GDELT fetch skipped: {e}")

    total_raw = len(articles)
    if not articles:
        console.print("[yellow]No articles fetched. Check API keys in .env[/yellow]")
        return

    # Step 2-4: Filter pipeline
    unique_articles = _deduplicate_articles(articles)
    fresh_articles, stale_count, freshness_rate = _filter_by_freshness(unique_articles, max_age_hours)
    if region or topic:
        fresh_articles = _keyword_filter(fresh_articles, region=region, topic=topic)

    # Cap at target to avoid MPS/NLI hangs on large batches
    if len(fresh_articles) > target_articles:
        fresh_articles = fresh_articles[:target_articles]

    # Pipeline summary — one line
    console.print(f"  [dim]fetched {total_raw} | unique {len(unique_articles)} | fresh {len(fresh_articles)}[/dim]")

    if not fresh_articles:
        console.print("[yellow]No articles match your filters.[/yellow]")
        return

    # Step 4b: Full text
    fresh_articles = _fetch_full_text(fresh_articles)

    # Step 5: Analyze sentiment
    if llm_analysis:
        results = await _analyze_articles_llm(fresh_articles)
    elif fast:
        results = await _analyze_articles(fresh_articles)
    else:
        # Ensemble router: HF Inference API (remote GPU) -> local -> VADER fallback
        results = _analyze_articles_ensemble(fresh_articles)

    # Step 5b: AI summaries
    if summarize:
        fresh_articles = _summarize_articles(fresh_articles)
    else:
        for a in fresh_articles:
            a["ai_summary"] = ""

    # Batch theme extraction via remote API (much faster than per-article NLI)
    if not fast:
        try:
            from .analyzers import hf_inference as hf
            if hf.is_available():
                theme_labels = list(entity_extractor.THEME_NLI_LABELS.values())
                theme_keys = list(entity_extractor.THEME_NLI_LABELS.keys())
                batch_texts = [
                    (a.get("content", "") or a.get("description", "") or a.get("title", ""))[:1500]
                    for a in fresh_articles
                ]
                with console.status(f"[dim]Classifying themes ({len(batch_texts)} articles via HF API)...[/dim]", spinner="dots"):
                    theme_results = hf.classify_batch(batch_texts, theme_labels, multi_label=True)
                for article, scores in zip(fresh_articles, theme_results):
                    if scores:
                        themes = [theme_keys[theme_labels.index(lbl)] for lbl, s in scores.items() if s > 0.3]
                        article["_themes"] = themes[:5]
                    else:
                        article["_themes"] = None
                console.print(f"  [dim]themes: classified via HF API[/dim]")
        except Exception as e:
            logger.debug(f"Remote theme classification skipped: {e}")

    # Build article records
    article_records = []
    all_country_sentiments = []
    for article in fresh_articles:
        text = article.get("content", "") or article.get("description", "") or article.get("title", "")
        entities = entity_extractor.extract_entities(text)
        tickers = entity_extractor.extract_tickers(text)
        volatility = entity_extractor.detect_volatility(text)

        sentiment_score = article.get("_sentiment_score", 0)
        sentiment_label = "pos" if sentiment_score > 0.05 else ("neg" if sentiment_score < -0.05 else "neu")

        risk_level = entity_extractor.detect_risk_level(text, sentiment_score)
        # Use pre-computed remote themes if available, else fall back to local
        themes = article.get("_themes") or entity_extractor.extract_themes(text, query or topic)

        country_mentions = entity_extractor.extract_country_mentions(text)
        country_sentiments = entity_extractor.analyze_country_sentiment(country_mentions, sentiment_score, text)
        all_country_sentiments.append(country_sentiments)

        record = ArticleRecord(
            run_id=run_id,
            id=entity_extractor.generate_article_id(
                source=article.get("domain", "unknown"),
                title=article.get("title", ""),
                published_at=article.get("published", ""),
            ),
            title=article.get("title", "Untitled"),
            url=article.get("link", ""),
            published_at=article.get("published", datetime.now().isoformat()),
            source=article.get("domain", "unknown"),
            region=region or "global",
            topic=query or topic or "general",
            language="en",
            authors=article.get("authors", []),
            tickers=tickers,
            entities=[{"text": e["text"], "type": e["type"]} for e in entities],
            summary=article.get("summary", "")[:500],
            ai_summary=article.get("ai_summary", ""),
            text_chars=len(text),
            hash=entity_extractor.calculate_text_hash(text),
            source_tier=get_tier(article.get("domain", "unknown")),
            relevance=0.5,
            sentiment=Sentiment(
                label=sentiment_label,
                score=sentiment_score,
                confidence=article.get("_sentiment_confidence", get_weight(article.get("domain", "unknown"))),
            ),
            signals=SignalData(volatility=volatility, risk_level=risk_level, themes=themes),
            ramme=article.get("_ramme"),
        )
        article_records.append(record)

    # Step 6a: Stance detection (per-entity sentiment via NLI)
    try:
        from .analyzers.stance_analyzer import StanceAnalyzer
        stance_analyzer = StanceAnalyzer()
        if stance_analyzer._ensure_ready():
            with console.status("[dim]Detecting entity stances...[/dim]", spinner="dots"):
                for record in article_records:
                    text = ""
                    for art in fresh_articles:
                        if art.get("link", "") == record.url:
                            text = art.get("content", "") or art.get("description", "") or art.get("title", "")
                            break
                    if not text:
                        text = record.summary or record.title
                    record.entity_stances = stance_analyzer.analyze(text, record.title)
                total_stances = sum(len(r.entity_stances) for r in article_records)
                console.print(f"  [dim]entity stances: {total_stances}[/dim]")
    except Exception as e:
        logger.debug(f"Stance detection skipped: {e}")

    # Step 6b: Event extraction (optional)
    if extract_events:
        with console.status("[dim]Extracting events...[/dim]", spinner="dots"):
            try:
                from .analyzers.event_extractor import EventExtractor
                event_extractor_llm = EventExtractor()

                docs = []
                for record in article_records:
                    text = ""
                    for art in fresh_articles:
                        if art.get("link", "") == record.url:
                            text = art.get("content", "") or art.get("description", "") or art.get("title", "")
                            break
                    if not text:
                        text = record.summary or record.title
                    docs.append({"id": record.id, "text": text})

                event_results = await event_extractor_llm.extract_batch(docs)

                total_events = 0
                for record in article_records:
                    record.events = event_results.get(record.id, [])
                    total_events += len(record.events)

                console.print(f"  [dim]events extracted: {total_events}[/dim]")
            except Exception as e:
                console.print(f"[red]Event extraction failed: {e}[/red]")

    # Baseline-relative risk scoring + record history
    try:
        from .utils.country_baselines import record_scan, compute_risk_levels
        # Build per-country sentiment summary
        country_sent_agg = {}
        for cs_list in all_country_sentiments:
            for cs in cs_list:
                c = cs.get("country", "")
                if c:
                    if c not in country_sent_agg:
                        country_sent_agg[c] = {"sentiments": [], "count": 0}
                    country_sent_agg[c]["sentiments"].append(cs.get("sentiment", 0))
                    country_sent_agg[c]["count"] += 1

        current = {}
        record_data = []
        for c, data in country_sent_agg.items():
            avg = sum(data["sentiments"]) / len(data["sentiments"]) if data["sentiments"] else 0
            current[c] = {"sentiment": avg, "article_count": data["count"]}
            record_data.append({"country": c, "sentiment": avg, "article_count": data["count"]})

        baseline_risks = compute_risk_levels(current)
        record_scan(record_data)
    except Exception:
        baseline_risks = {}

    # Cross-scan entity tracking
    entity_movers = []
    try:
        from .utils.entity_tracker import build_entity_summary, record_entities, compute_movers
        entity_summary = build_entity_summary(article_records)
        entity_movers = compute_movers(entity_summary)
        record_entities([
            {"entity": e, "type": d["type"], "mentions": d["mentions"],
             "mean_sentiment": float(d["mean_sentiment"]), "stances": d["stances"]}
            for e, d in entity_summary.items()
        ])
    except Exception as e:
        logger.debug(f"Entity tracking skipped: {e}")

    # Narrative clustering
    narratives = []
    try:
        from .analyzers.narrative_builder import NarrativeBuilder
        if len(article_records) >= 4:
            with console.status("[dim]Clustering narratives...[/dim]", spinner="dots"):
                nb = NarrativeBuilder()
                narratives = nb.build_narratives(article_records)
            if narratives:
                console.print(f"  [dim]narratives: {len(narratives)} threads[/dim]")
    except Exception as e:
        logger.debug(f"Narrative clustering skipped: {e}")

    # Contradiction detection (requires narratives)
    contradictions = []
    if narratives:
        try:
            from .analyzers.contradiction_detector import ContradictionDetector
            cd = ContradictionDetector()
            contradictions = cd.detect(article_records, narratives)
            if contradictions:
                console.print(f"  [dim]contradictions: {len(contradictions)} detected[/dim]")
        except Exception as e:
            logger.debug(f"Contradiction detection skipped: {e}")

    # Display
    country_insights = entity_extractor.generate_country_insights(all_country_sentiments)
    _display_results(results, article_records, country_insights, baseline_risks=baseline_risks, movers=entity_movers, narratives=narratives, contradictions=contradictions)

    if extract_events:
        _display_event_summary(article_records)
        # Event graph
        try:
            from .analyzers.event_graph import EventGraph
            eg = EventGraph()
            eg.add_from_records(article_records)
            _display_event_graph(eg)
        except ImportError:
            logger.debug("networkx not installed, skipping event graph")
        except Exception as e:
            logger.debug(f"Event graph skipped: {e}")

    # Source influence tracking
    if narratives:
        try:
            from .analyzers.source_influence import SourceInfluenceTracker
            sit = SourceInfluenceTracker()
            sit.analyze_narratives(article_records, narratives)
        except Exception as e:
            logger.debug(f"Source influence skipped: {e}")

    # Write outputs

    sentiment_breakdown = results.get("sentiment", {})
    avg_sentiment = (
        sum(r.sentiment.score for r in article_records) / len(article_records)
        if article_records else 0
    )

    entity_counter = Counter()
    for record in article_records:
        for entity in record.entities:
            entity_counter[(entity["text"], entity["type"])] += 1

    top_entities = [
        EntityCount(text=text, type=etype, count=count)
        for (text, etype), count in entity_counter.most_common(10)
    ]

    source_counter = Counter(r.source for r in article_records)
    source_counts = [
        SourceCount(domain=domain, articles=count)
        for domain, count in source_counter.most_common()
    ]

    all_themes = []
    for record in article_records:
        if record.signals:
            all_themes.extend(record.signals.themes)
    theme_counter = Counter(all_themes)
    top_triggers = [theme for theme, _ in theme_counter.most_common(5)]

    volatility_scores = [r.signals.volatility for r in article_records if r.signals]
    volatility_index = sum(volatility_scores) / len(volatility_scores) if volatility_scores else 0

    attempted = page_size
    if also_rss:
        rss_urls = list(settings.RSS_FEEDS)
        if max_feeds > 0:
            rss_urls = rss_urls[:max_feeds]
        attempted += len(rss_urls)

    run_summary = RunSummary(
        run_id=run_id,
        started_at=started_at.isoformat(),
        finished_at=datetime.now().isoformat(),
        config=ConfigBlock(
            region=region,
            topic=query or topic,
            max_age_hours=max_age_hours or 24,
        ),
        collection=CollectionBlock(
            attempted_feeds=attempted,
            articles_raw=total_raw,
            unique_after_dedupe=len(unique_articles),
            fresh_window_h=max_age_hours or 24,
            fresh_count=len(fresh_articles),
            relevant_count=len(fresh_articles),
        ),
        analysis=AnalysisBlock(
            sentiment_total=int(avg_sentiment * 100),
            breakdown=sentiment_breakdown,
            avg_sentiment=avg_sentiment,
            top_triggers=top_triggers,
            top_entities=top_entities,
            volatility_index=volatility_index,
        ),
        sources=source_counts,
        diversity=DiversityBlock(
            sources=len(source_counter),
            languages=1,
            regions=1,
            editorial_families=len(source_counter),
            score=min(len(source_counter) / 20, 1.0),
        ),
        errors=[],
        schema_version="1.0.0",
    )

    jsonl_path = writer.write_articles_jsonl(article_records)
    json_path = writer.write_run_summary_json(run_summary)

    highlights = []
    for record in sorted(article_records, key=lambda r: abs(r.sentiment.score), reverse=True)[:5]:
        highlights.append(f"{'+'if record.sentiment.label=='pos' else '-' if record.sentiment.label=='neg' else '~'} {record.title[:80]}")

    txt_path = writer.write_dashboard_txt(run_summary, highlights)

    output_files = [jsonl_path, json_path, txt_path]

    if extract_events:
        events_path = writer.write_events_jsonl(article_records)
        output_files.append(events_path)

    if export_csv:
        csv_path = writer.write_csv(article_records)
        output_files.append(csv_path)

    if output:
        output_data = {
            "timestamp": datetime.now().isoformat(),
            "config": {"query": query, "category": category, "country": country, "freshness": freshness},
            "results": results,
        }
        with open(output, "w") as f:
            json.dump(output_data, f, indent=2, default=str)
        output_files.append(output)

    # Footer
    total_time = time.time() - start_time
    console.print()
    console.print(f"[dim]{'=' * 40}[/dim]")
    console.print(f"[dim]{len(output_files)} files written to {output_dir}/[/dim]")
    console.print(f"[dim]completed in {total_time:.1f}s[/dim]")


# ---------------------------------------------------------------------------
# Full-text fetching and AI summary
# ---------------------------------------------------------------------------

_SCRAPE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


def _fetch_single_fulltext(article: Dict) -> bool:
    """Fetch full text for one article.

    Extraction order: trafilatura > newspaper3k > raw <p> tag scrape.
    Tracks which extractor succeeded in article["_extractor"].
    """
    import requests as req

    url = article.get("link", "")
    if not url:
        return False

    existing_len = len(article.get("content", "") or "")

    # Method 1: trafilatura (best extraction quality)
    try:
        import trafilatura
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
            if text and len(text) > existing_len:
                article["content"] = text
                article["_extractor"] = "trafilatura"
                return True
    except Exception:
        pass

    # Method 2: newspaper3k
    try:
        from newspaper import Article as NewsArticle
        na = NewsArticle(url, request_timeout=8)
        na.set_headers(_SCRAPE_HEADERS)
        na.download()
        na.parse()
        if na.text and len(na.text) > existing_len:
            article["content"] = na.text
            article["_extractor"] = "newspaper3k"
            if na.authors and not article.get("authors"):
                article["authors"] = na.authors
            return True
    except Exception:
        pass

    # Method 3: raw requests + <p> tag extraction
    try:
        resp = req.get(url, headers=_SCRAPE_HEADERS, timeout=8, allow_redirects=True)
        if resp.status_code == 200 and len(resp.text) > 500:
            import re
            paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', resp.text, re.DOTALL | re.IGNORECASE)
            if paragraphs:
                clean_text = " ".join(
                    re.sub(r'<[^>]+>', '', p).strip()
                    for p in paragraphs if len(re.sub(r'<[^>]+>', '', p).strip()) > 40
                )
                if len(clean_text) > existing_len:
                    article["content"] = clean_text
                    article["_extractor"] = "bs4_fallback"
                    return True
    except Exception:
        pass

    return False


def _fetch_full_text(articles: List[Dict]) -> List[Dict]:
    """Fetch full article text with concurrent workers, proper headers, and fallback scraping."""
    success = 0
    failed = 0
    total = len(articles)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TextColumn("[green]{task.fields[success]} scraped[/green]"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            "[cyan]Fetching full text...", total=total, success=0
        )

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = {}
            for i, article in enumerate(articles):
                future = executor.submit(_fetch_single_fulltext, article)
                futures[future] = i

            for future in futures:
                try:
                    result = future.result(timeout=15)
                    if result:
                        success += 1
                    else:
                        failed += 1
                except (TimeoutError, FuturesTimeoutError):
                    failed += 1
                except Exception:
                    failed += 1
                progress.update(task, advance=1, success=success)

    console.print(
        f"[green]Full text: {success} scraped, {failed} failed, {total} total[/green]"
    )
    return articles


def _summarize_articles(articles: List[Dict]) -> List[Dict]:
    """Generate AI summaries using a small local model (distilbart-cnn). Batched for speed."""
    try:
        from transformers import pipeline as hf_pipeline
        import transformers
        transformers.logging.set_verbosity_error()
        summarizer = hf_pipeline(
            "summarization",
            model="sshleifer/distilbart-cnn-12-6",
            device="mps:0" if __import__("torch").backends.mps.is_available() else -1,
        )
    except Exception as e:
        console.print(f"[yellow]Summarizer not available: {e}[/yellow]")
        return articles

    # Prepare batch inputs — only articles with enough text
    batch_indices = []
    batch_texts = []
    for i, article in enumerate(articles):
        text = article.get("content", "") or article.get("description", "")
        if text and len(text) > 200:
            batch_indices.append(i)
            batch_texts.append(text[:2000])
        else:
            article["ai_summary"] = ""

    if not batch_texts:
        return articles

    # Process in batches of 16 for GPU efficiency
    BATCH_SIZE = 16
    count = 0
    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        BarColumn(), TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(), console=console,
    ) as progress:
        task = progress.add_task("[cyan]AI summaries...", total=len(batch_texts))

        for start in range(0, len(batch_texts), BATCH_SIZE):
            chunk = batch_texts[start:start + BATCH_SIZE]
            chunk_indices = batch_indices[start:start + BATCH_SIZE]
            try:
                max_len = 60
                results = summarizer(
                    chunk,
                    max_length=max_len,
                    min_length=20,
                    do_sample=False,
                    truncation=True,
                    batch_size=BATCH_SIZE,
                )
                for idx, result in zip(chunk_indices, results):
                    articles[idx]["ai_summary"] = result["summary_text"]
                    count += 1
            except Exception:
                for idx in chunk_indices:
                    articles[idx]["ai_summary"] = ""
            progress.update(task, completed=min(start + BATCH_SIZE, len(batch_texts)))

    console.print(f"[green]AI summaries: {count}/{len(articles)}[/green]")
    return articles


# ---------------------------------------------------------------------------
# Filtering helpers
# ---------------------------------------------------------------------------

def _deduplicate_articles(articles: List[Dict]) -> List[Dict]:
    """Two-pass dedup: exact URL hash, then MinHash near-duplicate detection."""
    # Pass 1: Exact URL dedup
    seen = set()
    unique = []
    for article in articles:
        h = article.get("url_hash") or hashlib.md5(article.get("link", "").encode()).hexdigest()
        if h not in seen:
            seen.add(h)
            unique.append(article)

    # Pass 2: MinHash near-duplicate detection (catches AP/Reuters syndication)
    try:
        from datasketch import MinHash, MinHashLSH

        lsh = MinHashLSH(threshold=0.85, num_perm=128)
        minhashes = []

        for i, article in enumerate(unique):
            text = (article.get("title", "") + " " + article.get("description", "")).lower()
            tokens = text.split()
            # 5-shingle
            shingles = set()
            for j in range(len(tokens) - 4):
                shingles.add(" ".join(tokens[j:j+5]))
            if not shingles:
                shingles.add(text)

            mh = MinHash(num_perm=128)
            for s in shingles:
                mh.update(s.encode("utf-8"))
            minhashes.append(mh)

            try:
                lsh.insert(str(i), mh)
            except ValueError:
                pass  # duplicate key, already inserted

        # Find clusters and keep the canonical (first seen) per cluster
        dropped = set()
        for i, mh in enumerate(minhashes):
            if i in dropped:
                continue
            neighbors = lsh.query(mh)
            for n in neighbors:
                n_idx = int(n)
                if n_idx != i and n_idx not in dropped:
                    dropped.add(n_idx)
                    # Track syndication count on the canonical
                    unique[i].setdefault("syndication_count", 1)
                    unique[i]["syndication_count"] += 1

        if dropped:
            logger.info(f"MinHash dedup removed {len(dropped)} near-duplicates")
            unique = [a for j, a in enumerate(unique) if j not in dropped]

    except ImportError:
        pass  # datasketch not installed, skip semantic dedup

    return unique


def _parse_freshness(freshness: str) -> Optional[int]:
    if freshness == "forever":
        return None
    elif freshness.endswith("h"):
        return int(freshness[:-1])
    elif freshness.endswith("d"):
        return int(freshness[:-1]) * 24
    return 24


def _filter_by_freshness(articles: List[Dict], max_age_hours: Optional[int] = 24) -> tuple:
    if max_age_hours is None:
        return articles, 0, 1.0

    cutoff = datetime.now() - timedelta(hours=max_age_hours)
    fresh = []
    stale = 0

    for article in articles:
        pub_date = article.get("published_date")
        if pub_date:
            if hasattr(pub_date, "tzinfo") and pub_date.tzinfo:
                pub_date = pub_date.replace(tzinfo=None)
            if pub_date >= cutoff:
                fresh.append(article)
            else:
                stale += 1
        else:
            # NewsAPI always has dates, so keep articles without dates (likely RSS)
            fresh.append(article)

    rate = len(fresh) / len(articles) if articles else 0
    return fresh, stale, rate


_AMBIGUOUS_TOPICS: Dict[str, Dict[str, tuple]] = {
    # Words that look like a topic but match unrelated content unless context confirms.
    # core_any:    title must contain at least one of these (kills incidental body matches).
    # require_any: at least one must co-occur in title+body (context proof).
    # exclude_any: any of these in title alone disqualifies the article.
    "oil": {
        "core_any": ("oil", "crude", "brent", "wti", "petroleum", "refinery",
                     "refining", "opec", "barrel", "drilling", "pipeline",
                     "shale", "lng", "tanker", "exxon", "chevron", "aramco",
                     "rosneft", "hormuz"),
        "require_any": ("crude", "barrel", "opec", "brent", "wti", "petroleum",
                        "refinery", "refining", "drilling", "pipeline", "shale",
                        "lng", "exxon", "chevron", "saudi aramco", "rosneft",
                        "exporter", "embargo", "hormuz", "tanker", "iran",
                        "russia", "saudi", "energy market", "futures"),
        "exclude_any": ("cooking oil", "olive oil", "vegetable oil", "fish oil",
                        "essential oil", "coconut oil", "anointing", "anointed",
                        "salad", "skincare", "snake oil", "recipe",
                        "pumpkin seed oil", "hair oil", "hair", "scalp",
                        "beauty", "noodle", "stain", "scrub", "wine",
                        "movie", "box office", "shoe", "hashish", "drug cartel",
                        "medal", "museum", "podcast", "memecoin", "deer",
                        "correspondents dinner", "fragrance", "perfume",
                        "massage", "lotion", "diffuser", "cbd"),
    },
    "fuel": {
        "core_any": ("fuel", "gasoline", "diesel", "petrol", "biofuel",
                     "refinery", "lng", "kerosene", "ethanol"),
        "require_any": ("gasoline", "diesel", "petrol", "jet fuel", "biofuel",
                        "ethanol", "lng", "natural gas", "coal", "kerosene",
                        "refinery", "shortage", "subsidy", "subsidies", "price"),
        "exclude_any": ("rocket fuel", "nasa", "spacex", "starship", "satellite",
                        "deep space", "hypersonic", "mars mission", "lunar",
                        "fuel for thought", "fueled by", "fuels speculation",
                        "fuels debate", "fuels rumors", "fuels concerns",
                        "fueling speculation", "fueled the"),
    },
    "gas": {
        "core_any": ("gas", "lng", "pipeline", "gazprom", "petrol",
                     "gasoline", "henry hub", "nord stream"),
        "require_any": ("natural gas", "lng", "pipeline", "gazprom", "nord stream",
                        "petrol", "gasoline", "exporter", "import", "energy",
                        "europe", "shortage", "futures", "henry hub"),
        "exclude_any": ("tear gas", "laughing gas", "gastric", "gas station fire",
                        "asthma", "anesthesia", "gas mask", "gaslighting",
                        "gas giant", "gas chamber"),
    },
    "gold": {
        "core_any": ("gold", "bullion", "comex", "ounce"),
        "require_any": ("ounce", "spot gold", "bullion", "futures", "etf",
                        "central bank", "reserve", "comex", "precious metal"),
        "exclude_any": ("gold medal", "olympics", "world cup", "academy award",
                        "gold cup", "golden globe", "goldfinger",
                        "goldman sachs", "old gold", "gold star", "gold rush movie"),
    },
}


def _word_re(term: str) -> "re.Pattern":
    """Compile a word-boundary regex for an exact term (case-insensitive)."""
    # Multi-word phrases get loose whitespace tolerance.
    pat = r"\b" + r"\s+".join(re.escape(w) for w in term.split()) + r"\b"
    return re.compile(pat, re.IGNORECASE)


def _keyword_filter(articles: List[Dict], region: Optional[str] = None, topic: Optional[str] = None) -> List[Dict]:
    from .config import REGION_MAP, TOPIC_MAP

    keywords: List[str] = []
    if region and region in REGION_MAP:
        keywords.extend(REGION_MAP[region])
    elif region:
        keywords.append(region.replace("_", " "))

    # Topic input may be free-form ("Iran, Hormuz, Oil"). Split on commas.
    raw_topics: List[str] = []
    if topic:
        raw_topics = [t.strip() for t in topic.split(",") if t.strip()]

    for t in raw_topics:
        if t in TOPIC_MAP:
            keywords.extend(TOPIC_MAP[t])
        else:
            keywords.append(t.replace("_", " "))

    if not keywords and not raw_topics:
        return articles

    # Pre-compile word-boundary regexes
    kw_patterns = [(kw, _word_re(kw)) for kw in keywords if kw]

    # Disambiguation rules for any ambiguous topic the user typed
    ambig: List[Dict[str, tuple]] = []
    for t in raw_topics:
        rule = _AMBIGUOUS_TOPICS.get(t.lower())
        if rule:
            ambig.append({
                "term": t.lower(),
                "core": [_word_re(w) for w in rule.get("core_any", ())],
                "require": [_word_re(w) for w in rule["require_any"]],
                "exclude": [_word_re(w) for w in rule["exclude_any"]],
            })

    filtered = []
    for article in articles:
        title = (article.get("title") or "").lower()
        body = (article.get("description") or "") + " " + (article.get("content") or "")
        body_lower = body.lower()
        full = (title + " " + body_lower).lower()

        # Core keyword test — word-boundary, not substring
        if kw_patterns and not any(p.search(full) for _, p in kw_patterns):
            continue

        # Disambiguation: if user typed an ambiguous term, the title must
        # contain at least one core topic word, must not contain any
        # exclusion phrase, and the body must mention at least one context
        # word. This kills "oil" articles about cooking/hair/movies/etc.
        if ambig:
            ok = True
            for rule in ambig:
                if rule["core"] and not any(c.search(title) for c in rule["core"]):
                    ok = False; break
                if any(ex.search(title) for ex in rule["exclude"]):
                    ok = False; break
                if rule["require"] and not any(rq.search(full) for rq in rule["require"]):
                    ok = False; break
            if not ok:
                continue

        filtered.append(article)

    return filtered


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def _analyze_articles_ensemble(articles: List[Dict]) -> Dict:
    """Ensemble sentiment via HF Inference API (remote GPU) or local fallback."""
    from .analyzers.sentiment_router import analyze_batch

    if not articles:
        return {"total_articles": 0, "sentiment": {"positive": 0, "negative": 0, "neutral": 0}, "sentiment_score": 0}

    texts = [a.get("content", "") or a.get("description", "") or a.get("title", "") for a in articles]
    titles = [a.get("title", "") for a in articles]
    themes_per = [a.get("_themes") for a in articles]

    with console.status(f"[dim]Sentiment ({len(articles)} articles via ensemble)...[/dim]", spinner="dots"):
        results = analyze_batch(texts, themes_per, titles=titles)

    pos = neg = neu = 0
    scores = []
    insights = []
    for article, result in zip(articles, results):
        article["_sentiment_score"] = result.score
        article["_sentiment_confidence"] = result.confidence
        article["_sentiment_model"] = result.model
        # Stash the rich RAMME payload (fls/esg/aspects/components/stance)
        # on the article so it survives into ArticleRecord and the dashboard.
        if getattr(result, "ramme", None):
            article["_ramme"] = result.ramme
        scores.append(result.score)
        if result.label == "positive":
            pos += 1
        elif result.label == "negative":
            neg += 1
        else:
            neu += 1
        if abs(result.score) > 0.6:
            insights.append({"title": article.get("title", ""), "sentiment": result.label.upper(), "score": result.score})

    avg = sum(scores) / len(scores) if scores else 0
    console.print(f"  [dim]sentiment: +{pos} ~{neu} -{neg}  model={results[0].model if results else 'unknown'}[/dim]")
    return {
        "total_articles": len(articles),
        "sentiment_score": round(avg * 100),
        "sentiment": {"positive": pos, "negative": neg, "neutral": neu},
        "key_insights": insights,
    }


async def _analyze_articles(articles: List[Dict]) -> Dict:
    """Fast VADER-only sentiment on all articles (--fast mode)."""
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    vader = SentimentIntensityAnalyzer()

    if not articles:
        return {"total_articles": 0, "sentiment": {"positive": 0, "negative": 0, "neutral": 0}, "sentiment_score": 0}

    scores = []
    pos = neg = neu = 0
    insights = []

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        BarColumn(), TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(), console=console,
    ) as progress:
        task = progress.add_task("[cyan]Sentiment (VADER)...", total=len(articles))

        for article in articles:
            text = article.get("content", "") or article.get("description", "") or article.get("title", "")
            if text:
                score = vader.polarity_scores(text[:1000])["compound"]
                article["_sentiment_score"] = score
                scores.append(score)
                if score > 0.05:
                    pos += 1
                    label = "POSITIVE"
                elif score < -0.05:
                    neg += 1
                    label = "NEGATIVE"
                else:
                    neu += 1
                    label = "NEUTRAL"
                if abs(score) > 0.8:
                    insights.append({"title": article.get("title", ""), "sentiment": label, "score": score})
            else:
                article["_sentiment_score"] = 0
            progress.advance(task)

    avg = sum(scores) / len(scores) if scores else 0
    return {
        "total_articles": len(articles),
        "sentiment_score": round(avg * 100),
        "sentiment": {"positive": pos, "negative": neg, "neutral": neu},
        "key_insights": insights,
    }


async def _analyze_articles_llm(articles: List[Dict]) -> Dict:
    if not articles:
        return {"total_articles": 0, "sentiment": {"positive": 0, "negative": 0, "neutral": 0}, "sentiment_score": 0}

    try:
        from .analyzers.llm_analyzer import LLMAnalyzer
        analyzer_llm = LLMAnalyzer()

        docs = []
        for i, article in enumerate(articles):
            text = article.get("content", "") or article.get("description", "") or article.get("title", "")
            if text:
                docs.append({"id": f"article_{i}", "text": text})

        if not docs:
            return await _analyze_articles(articles)

        llm_results = await analyzer_llm.analyze_batch(docs)

        analysis_results = []
        scores = []
        for i, llm_result in enumerate(llm_results):
            label = llm_result.get("sentiment", "neutral").upper()
            if label not in ("POSITIVE", "NEGATIVE", "NEUTRAL"):
                label = "NEUTRAL"

            confidence = float(llm_result.get("confidence", 0.5))
            score = confidence if label == "POSITIVE" else (-confidence if label == "NEGATIVE" else 0.0)

            analysis_results.append({
                "title": articles[i].get("title", "Untitled"),
                "sentiment_label": label,
                "sentiment_score": score,
            })
            scores.append(score)

        aggregate = round(sum(scores) / len(scores) * 100) if scores else 0

        return {
            "total_articles": len(articles),
            "sentiment_score": aggregate,
            "sentiment": {
                "positive": sum(1 for r in analysis_results if r["sentiment_label"] == "POSITIVE"),
                "negative": sum(1 for r in analysis_results if r["sentiment_label"] == "NEGATIVE"),
                "neutral": sum(1 for r in analysis_results if r["sentiment_label"] == "NEUTRAL"),
            },
            "key_insights": [],
        }

    except ImportError:
        console.print("[red]LLM analysis requires OPENAI_API_KEY in .env[/red]")
        return await _analyze_articles(articles)
    except Exception as e:
        console.print(f"[red]LLM analysis failed: {e}[/red]")
        console.print("[yellow]Falling back to VADER analysis...[/yellow]")
        return await _analyze_articles(articles)


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def _display_results(results: Dict, article_records=None, country_insights=None, baseline_risks=None, movers=None, narratives=None, contradictions=None):
    console.print()
    pos = results["sentiment"]["positive"]
    neg = results["sentiment"]["negative"]
    neu = results["sentiment"]["neutral"]
    total = pos + neg + neu
    score = results.get("sentiment_score", 0)

    # --- Sentiment gauge ---
    if total > 0:
        bar_width = 40
        pos_w = round(pos / total * bar_width)
        neg_w = round(neg / total * bar_width)
        neu_w = bar_width - pos_w - neg_w
        bar = f"[green]{'#' * pos_w}[/green][dim]{'.' * neu_w}[/dim][red]{'#' * neg_w}[/red]"
    else:
        bar = "[dim]no data[/dim]"

    if score > 20:
        score_color = "green"
        sentiment_word = "Bullish"
    elif score < -20:
        score_color = "red"
        sentiment_word = "Bearish"
    else:
        score_color = "yellow"
        sentiment_word = "Mixed"

    sentiment_panel = (
        f"[{score_color} bold]{score:+d}[/{score_color} bold]  "
        f"[{score_color}]{sentiment_word}[/{score_color}]  "
        f"{bar}\n"
        f"[green]+{pos}[/green] positive  "
        f"[dim]{neu} neutral[/dim]  "
        f"[red]{neg} negative[/red]  "
        f"[dim]|  {total} articles[/dim]"
    )
    console.print(Panel(sentiment_panel, title="[bold]Sentiment[/bold]", border_style="dim", padding=(0, 1)))

    if not article_records:
        return

    # --- Top Signals (most extreme articles) ---
    sorted_records = sorted(article_records, key=lambda x: x.sentiment.score)
    most_neg = sorted_records[0]
    most_pos = sorted_records[-1]

    if most_pos.sentiment.score > 0.3 or most_neg.sentiment.score < -0.3:
        signal_table = Table(box=None, show_header=False, show_edge=False, pad_edge=False, padding=(0, 1))
        signal_table.add_column("Score", width=7, justify="right")
        signal_table.add_column("Headline", ratio=1)
        if most_pos.sentiment.score > 0.3:
            signal_table.add_row(
                f"[green]+{most_pos.sentiment.score:.2f}[/green]",
                f"{most_pos.title[:70]}",
            )
        if most_neg.sentiment.score < -0.3:
            signal_table.add_row(
                f"[red]{most_neg.sentiment.score:.2f}[/red]",
                f"{most_neg.title[:70]}",
            )
        console.print(Panel(signal_table, title="[bold]Top Signals[/bold]", border_style="dim", padding=(0, 1)))

    # --- Intelligence grid: themes, regions/risk, sources ---
    grid = Table(box=None, show_header=False, show_edge=False, pad_edge=False, padding=(0, 0))
    grid.add_column("Label", width=10, style="bold")
    grid.add_column("Content", ratio=1)

    # Themes
    all_themes = []
    for record in article_records:
        if record.signals and record.signals.themes:
            all_themes.extend(record.signals.themes)
    top_themes = Counter(all_themes).most_common(5)
    if top_themes:
        theme_parts = []
        for t, c in top_themes:
            if c >= 10:
                theme_parts.append(f"[bold]{t}[/bold]({c})")
            else:
                theme_parts.append(f"{t}({c})")
        grid.add_row("Themes", "  ".join(theme_parts))

    # Countries/Risk
    if baseline_risks:
        risk_style = {"critical": "red bold", "high": "red", "elevated": "yellow", "normal": "dim", "improving": "green"}
        flagged = [(c, d) for c, d in baseline_risks.items() if d["risk_level"] != "normal" and d["article_count"] >= 2]
        flagged.sort(key=lambda x: x[1]["z_score"])
        if flagged:
            risk_parts = []
            for c, d in flagged[:6]:
                style = risk_style.get(d["risk_level"], "dim")
                risk_parts.append(f"[{style}]{c}[/{style}] ({d['risk_level']}, z={d['z_score']:+.1f})")
            grid.add_row("Risk", "  ".join(risk_parts))
    if country_insights and country_insights.get("most_mentioned"):
        top_countries = country_insights["most_mentioned"][:5]
        c_str = "  ".join(f"{cd['country']}({cd['mentions']})" for cd in top_countries)
        grid.add_row("Regions", c_str)

    # Sources with tier
    source_counter = Counter(r.source for r in article_records)
    top_sources = source_counter.most_common(5)
    if top_sources:
        src_parts = []
        for s, c in top_sources:
            tier = get_tier(s)
            tier_style = {"tier1": "green", "tier2": "cyan", "tier3": "dim"}.get(tier, "dim")
            src_parts.append(f"[{tier_style}]{s}[/{tier_style}]({c})")
        grid.add_row("Sources", "  ".join(src_parts))

    console.print(Panel(grid, title="[bold]Intelligence[/bold]", border_style="dim", padding=(0, 1)))

    # --- Movers ---
    if movers:
        mover_table = Table(box=None, show_header=True, show_edge=False, pad_edge=False, padding=(0, 1))
        mover_table.add_column("Entity", style="white", no_wrap=True)
        mover_table.add_column("Direction", width=12)
        mover_table.add_column("Volume", justify="right", width=8)
        mover_table.add_column("Sentiment", justify="right", width=10)
        dir_style = {"worsening": "red", "improving": "green", "surging": "yellow", "fading": "dim", "shifting": "cyan"}
        for m in movers[:5]:
            style = dir_style.get(m["direction"], "dim")
            mover_table.add_row(
                m["entity"],
                f"[{style}]{m['direction']}[/{style}]",
                f"z={m['volume_z']:+.1f}",
                f"{m['current_sentiment']:+.3f}",
            )
        console.print(Panel(mover_table, title="[bold]Movers[/bold]", border_style="dim", padding=(0, 1)))

    # --- Narratives ---
    if narratives:
        narr_table = Table(box=None, show_header=True, show_edge=False, pad_edge=False, padding=(0, 1))
        narr_table.add_column("Thread", ratio=1)
        narr_table.add_column("N", justify="right", width=3)
        narr_table.add_column("Sent", justify="right", width=7)
        narr_table.add_column("Sources", style="dim", width=30)
        narr_table.add_column("Themes", style="dim", width=24)
        sent_color = {"negative": "red", "positive": "green", "neutral": "dim"}
        for n in narratives[:6]:
            color = sent_color.get(n.sentiment_direction, "dim")
            sources_str = ", ".join(list(n.sources.keys())[:3])
            theme_str = " ".join(n.themes[:2]) if n.themes else ""
            narr_table.add_row(
                f"[{color}]{n.headline[:55]}[/{color}]",
                str(n.article_count),
                f"[{color}]{n.mean_sentiment:+.2f}[/{color}]",
                sources_str,
                theme_str,
            )
        console.print(Panel(narr_table, title=f"[bold]Narratives[/bold]  [dim]{len(narratives)} threads[/dim]", border_style="dim", padding=(0, 1)))

    # --- Contradictions ---
    if contradictions:
        type_style = {"sentiment": "yellow", "stance": "red", "both": "red bold"}
        contra_lines = []
        for c in contradictions[:3]:
            style = type_style.get(c.contradiction_type, "yellow")
            contra_lines.append(
                f"[{style}]{c.contradiction_type}[/{style}] [dim](severity {c.severity:.2f})[/dim]\n"
                f"  A: [dim]{c.article_a_title[:60]}[/dim]\n"
                f"  B: [dim]{c.article_b_title[:60]}[/dim]\n"
                f"  [dim]{c.details}[/dim]"
            )
        console.print(Panel(
            "\n".join(contra_lines),
            title=f"[bold]Contradictions[/bold]  [dim]{len(contradictions)} found[/dim]",
            border_style="yellow",
            padding=(0, 1),
        ))


def _display_event_summary(article_records):
    """Display event extraction summary."""
    all_events = []
    for record in article_records:
        for event in record.events:
            all_events.append(event)

    if not all_events:
        return

    console.print(f"\n  [bold]Events[/bold]   {len(all_events)} extracted")

    # Key relationships — the most useful view
    relationship_data = {}
    for event in all_events:
        if event.receiver:
            key = (event.actor.name, event.receiver.name)
            if key not in relationship_data:
                relationship_data[key] = {"count": 0, "tones": [], "actions": []}
            relationship_data[key]["count"] += 1
            relationship_data[key]["tones"].append(event.tone)
            relationship_data[key]["actions"].append(event.action.category)

    if relationship_data:
        console.print()
        table = Table(box=rich.box.SIMPLE_HEAD, show_edge=False, pad_edge=False, padding=(0, 2))
        table.add_column("Actor", style="white", no_wrap=True)
        table.add_column("", style="dim", width=3)
        table.add_column("Receiver", style="white", no_wrap=True)
        table.add_column("Tone", justify="right", width=6)
        table.add_column("Type", style="dim")

        sorted_rels = sorted(relationship_data.items(), key=lambda x: x[1]["count"], reverse=True)
        for (actor, receiver), data in sorted_rels[:8]:
            avg_tone = sum(data["tones"]) / len(data["tones"])
            tone_str = f"{avg_tone:+.1f}"
            if avg_tone > 2:
                tone_str = f"[green]{tone_str}[/green]"
            elif avg_tone < -2:
                tone_str = f"[red]{tone_str}[/red]"
            top_action = Counter(data["actions"]).most_common(1)[0][0]
            arrow = "-->" if avg_tone >= 0 else "--|"
            table.add_row(actor[:25], arrow, receiver[:25], tone_str, top_action)
        console.print(table)

    # Compact breakdown
    categories = Counter(e.action.category for e in all_events).most_common()
    if categories:
        cat_str = "  ".join(f"{c}({n})" for c, n in categories)
        console.print(f"\n  [bold]Actions[/bold]  {cat_str}")


def _display_event_graph(eg):
    """Display event graph summary."""
    top = eg.top_actors(5)
    if top:
        console.print(f"\n  [bold]Actor Network[/bold]  {len(eg.graph.nodes)} actors, {len(eg.graph.edges)} links")
        for a in top:
            tone = a["avg_tone_received"]
            tone_style = "green" if tone > 1 else ("red" if tone < -1 else "dim")
            console.print(
                f"  {a['actor']}  [{tone_style}]tone={tone:+.1f}[/{tone_style}]  "
                f"[dim]in={a['in_degree']} out={a['out_degree']}[/dim]"
            )

    hostile = eg.hostile_pairs()
    if hostile:
        console.print(f"\n  [bold]Hostile[/bold]")
        for p in hostile[:3]:
            console.print(f"  [red]{p['actor']} -> {p['receiver']}[/red]  [dim]tone={p['avg_tone']:+.1f}  {', '.join(p['actions'][:3])}[/dim]")

    coop = eg.cooperative_pairs()
    if coop:
        console.print(f"\n  [bold]Cooperative[/bold]")
        for p in coop[:3]:
            console.print(f"  [green]{p['actor']} -> {p['receiver']}[/green]  [dim]tone={p['avg_tone']:+.1f}  {', '.join(p['actions'][:3])}[/dim]")

    domains = eg.domain_breakdown()
    if domains:
        d_str = "  ".join(f"{d}({c})" for d, c in list(domains.items())[:5])
        console.print(f"\n  [bold]Domains[/bold]  {d_str}")


@app.command()
def events(
    jsonl_file: str = typer.Argument(..., help="Path to an events JSONL file"),
    actor: Optional[str] = typer.Option(None, "--actor", "-a", help="Filter by actor name"),
    domain: Optional[str] = typer.Option(None, "--domain", "-d", help="Filter by domain"),
    min_tone: Optional[int] = typer.Option(None, "--min-tone", help="Minimum tone value"),
    max_tone: Optional[int] = typer.Option(None, "--max-tone", help="Maximum tone value"),
    limit: int = typer.Option(50, "--limit", "-n", help="Max events to display"),
):
    """
    View events from a previously generated events JSONL file.

    Examples:
        bsgbot events output/events_abc123.jsonl
        bsgbot events output/events_abc123.jsonl --actor "United States"
        bsgbot events output/events_abc123.jsonl --domain economic --min-tone -5
    """
    filepath = Path(jsonl_file)
    if not filepath.exists():
        console.print(f"[red]File not found: {jsonl_file}[/red]")
        raise typer.Exit(1)

    events_list = []
    with filepath.open("r") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events_list.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    if not events_list:
        console.print("[yellow]No events found in file.[/yellow]")
        return

    # Apply filters
    filtered = events_list
    if actor:
        actor_lower = actor.lower()
        filtered = [
            e for e in filtered
            if actor_lower in e.get("actor", {}).get("name", "").lower()
            or actor_lower in (e.get("receiver") or {}).get("name", "").lower()
        ]
    if domain:
        filtered = [e for e in filtered if e.get("domain") == domain]
    if min_tone is not None:
        filtered = [e for e in filtered if e.get("tone", 0) >= min_tone]
    if max_tone is not None:
        filtered = [e for e in filtered if e.get("tone", 0) <= max_tone]

    console.print(f"[bold]Events: {len(filtered)}/{len(events_list)}[/bold]")

    table = Table(box=rich.box.SIMPLE)
    table.add_column("Actor", style="cyan", max_width=20)
    table.add_column("Action", max_width=15)
    table.add_column("Receiver", style="green", max_width=20)
    table.add_column("Tone", justify="right", width=5)
    table.add_column("Domain", width=10)
    table.add_column("Article", style="dim", max_width=40)

    for event in filtered[:limit]:
        actor_name = event.get("actor", {}).get("name", "?")
        action_verb = event.get("action", {}).get("verb", "?")
        category = event.get("action", {}).get("category", "")
        receiver_name = (event.get("receiver") or {}).get("name", "-")
        tone = event.get("tone", 0)
        tone_str = f"{tone:+d}"
        if tone > 2:
            tone_str = f"[green]{tone_str}[/green]"
        elif tone < -2:
            tone_str = f"[red]{tone_str}[/red]"
        dom = event.get("domain", "")
        title = event.get("article_title", "")[:40]

        table.add_row(actor_name, f"{action_verb} ({category})", receiver_name, tone_str, dom, title)

    console.print(table)


@app.command()
def compare(
    scan_a: str = typer.Argument(..., help="Path to older scan articles JSONL"),
    scan_b: str = typer.Argument(..., help="Path to newer scan articles JSONL"),
    min_articles: int = typer.Option(3, "--min-articles", help="Min articles per country"),
):
    """
    Compare two scans with bootstrap confidence intervals.

    Only flags Worsening/Improving when the 95% CI excludes zero.

    Examples:
        bsgbot compare output/articles_old.jsonl output/articles_new.jsonl
    """
    from .utils.scan_compare import compare_scans

    results = compare_scans(scan_a, scan_b, min_articles=min_articles)

    if not results:
        console.print("[yellow]No countries with enough articles in both scans.[/yellow]")
        return

    table = Table(box=rich.box.SIMPLE_HEAD, show_edge=False, pad_edge=False, padding=(0, 2))
    table.add_column("Country", style="white")
    table.add_column("Delta", justify="right", width=8)
    table.add_column("95% CI", width=18)
    table.add_column("Direction", width=12)
    table.add_column("N", style="dim", justify="right", width=8)

    # Sort: significant changes first, then by absolute delta
    sorted_results = sorted(
        results.items(),
        key=lambda x: (not x[1]["significant"], -abs(x[1]["delta"])),
    )

    for country, data in sorted_results:
        delta_str = f"{data['delta']:+.3f}"
        ci_str = f"[{data['ci_lower']:+.3f}, {data['ci_upper']:+.3f}]"
        n_str = f"{data['n_a']}/{data['n_b']}"

        if data["direction"] == "worsening":
            dir_str = "[red]worsening[/red]"
            delta_str = f"[red]{delta_str}[/red]"
        elif data["direction"] == "improving":
            dir_str = "[green]improving[/green]"
            delta_str = f"[green]{delta_str}[/green]"
        else:
            dir_str = "[dim]stable[/dim]"
            delta_str = f"[dim]{delta_str}[/dim]"

        table.add_row(country, delta_str, ci_str, dir_str, n_str)

    console.print(table)

    sig_count = sum(1 for d in results.values() if d["significant"])
    console.print(f"\n[dim]{sig_count}/{len(results)} countries show significant change (95% CI excludes zero)[/dim]")


@app.command()
def narratives(
    jsonl_file: str = typer.Argument(..., help="Path to articles JSONL file"),
    threshold: float = typer.Option(0.72, "--threshold", "-t", help="Cosine similarity threshold"),
    min_size: int = typer.Option(2, "--min-size", help="Minimum articles per narrative"),
):
    """Cluster articles from a JSONL file into narrative threads."""
    from .analyzers.narrative_builder import NarrativeBuilder
    from .utils.output_models import ArticleRecord

    path = Path(jsonl_file)
    if not path.exists():
        console.print(f"[red]File not found:[/red] {jsonl_file}")
        raise typer.Exit(1)

    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(ArticleRecord(**json.loads(line)))
                except Exception:
                    continue

    if len(records) < 2:
        console.print("[dim]Not enough articles to cluster.[/dim]")
        raise typer.Exit(0)

    console.print(f"[dim]Loaded {len(records)} articles[/dim]")

    nb = NarrativeBuilder(cosine_threshold=threshold, min_cluster_articles=min_size)
    threads = nb.build_narratives(records)

    if not threads:
        console.print("[dim]No narrative threads found.[/dim]")
        raise typer.Exit(0)

    console.print(f"\n[bold]{len(threads)} Narrative Threads[/bold]\n")

    sent_style = {"negative": "red", "positive": "green", "neutral": "dim"}
    for i, n in enumerate(threads, 1):
        style = sent_style.get(n.sentiment_direction, "dim")
        console.print(f"  [bold]{i}.[/bold] [{style}]{n.headline}[/{style}]")
        sources_str = ", ".join(f"{s}({c})" for s, c in sorted(n.sources.items(), key=lambda x: -x[1])[:5])
        regions_str = ", ".join(f"{r}({c})" for r, c in sorted(n.regions.items(), key=lambda x: -x[1])[:5])
        console.print(f"     [dim]{n.article_count} articles  sent={n.mean_sentiment:+.3f} ({n.sentiment_direction})  salience={n.salience:.2f}[/dim]")
        if sources_str:
            console.print(f"     [dim]Sources: {sources_str}[/dim]")
        if regions_str:
            console.print(f"     [dim]Regions: {regions_str}[/dim]")
        if n.themes:
            console.print(f"     [dim]Themes: {', '.join(n.themes)}[/dim]")
        console.print()


@app.command()
def forecast(
    periods: int = typer.Option(3, "--periods", "-p", help="Forecast periods ahead"),
    entities: bool = typer.Option(False, "--entities", "-e", help="Forecast entity sentiment"),
):
    """Forecast sentiment trends from historical scan data."""
    from .analyzers.forecaster import SentimentForecaster
    fc = SentimentForecaster()

    if entities:
        results = fc.forecast_entities(periods=periods)
        if not results:
            console.print("[dim]Not enough entity history for forecasting.[/dim]")
            raise typer.Exit(0)
        console.print(f"\n[bold]Entity Sentiment Forecast[/bold]  ({periods} periods ahead)\n")
        dir_style = {"improving": "green", "deteriorating": "red", "stable": "dim"}
        for entity, data in list(results.items())[:15]:
            style = dir_style.get(data["direction"], "dim")
            fc_str = " -> ".join(f"{v:+.3f}" for v in data["forecast"])
            console.print(
                f"  [{style}]{entity}[/{style}]  "
                f"current={data['current']:+.3f}  "
                f"[dim]{fc_str}  ({data['direction']})[/dim]"
            )
    else:
        results = fc.forecast_countries(periods=periods)
        if not results:
            console.print("[dim]Not enough country history for forecasting.[/dim]")
            raise typer.Exit(0)
        console.print(f"\n[bold]Country Sentiment Forecast[/bold]  ({periods} periods ahead)\n")
        dir_style = {"improving": "green", "deteriorating": "red", "stable": "dim"}
        for country, data in results.items():
            style = dir_style.get(data["direction"], "dim")
            fc_str = " -> ".join(f"{v:+.3f}" for v in data["forecast"])
            console.print(
                f"  [{style}]{country}[/{style}]  "
                f"current={data['current']:+.3f}  "
                f"[dim]{fc_str}  ({data['direction']}, {data['history_points']} pts)[/dim]"
            )


@app.command()
def judge(
    jsonl_file: str = typer.Argument(..., help="Path to articles JSONL file"),
    sample_size: int = typer.Option(20, "--sample", "-n", help="Number of articles to judge"),
):
    """Use LLM to evaluate analysis quality (requires OPENAI_API_KEY)."""
    from .analyzers.llm_judge import LLMJudge
    from .utils.output_models import ArticleRecord

    path = Path(jsonl_file)
    if not path.exists():
        console.print(f"[red]File not found:[/red] {jsonl_file}")
        raise typer.Exit(1)

    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(ArticleRecord(**json.loads(line)))
                except Exception:
                    continue

    if not records:
        console.print("[dim]No articles loaded.[/dim]")
        raise typer.Exit(0)

    console.print(f"[dim]Judging {min(sample_size, len(records))} of {len(records)} articles...[/dim]")

    jdg = LLMJudge(sample_size=sample_size)
    with console.status("[dim]LLM evaluating analysis quality...[/dim]", spinner="dots"):
        result = jdg.evaluate(records, sample_size)

    if "error" in result:
        console.print(f"[red]{result['error']}[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold]Quality Assessment[/bold]  (n={result['judged']})\n")
    console.print(f"  Sentiment accuracy:  {result['sentiment_accuracy']:.0%}")
    console.print(f"  Theme accuracy:      {result['theme_accuracy']:.0%}")
    console.print(f"  Entity accuracy:     {result['entity_accuracy']:.0%}")
    console.print(f"  [bold]Overall:             {result['overall_accuracy']:.0%}[/bold]")

    if result.get("issues"):
        console.print(f"\n  [bold]Issues[/bold]")
        for issue in result["issues"][:5]:
            console.print(f"  [dim]- {issue}[/dim]")


@app.command()
def suggest_labels(
    jsonl_file: str = typer.Argument(..., help="Path to articles JSONL file"),
    n: int = typer.Option(20, "--count", "-n", help="Number of candidates"),
    strategy: str = typer.Option("mixed", "--strategy", "-s", help="uncertainty, boundary, or mixed"),
):
    """Surface low-confidence articles for human labeling."""
    from .analyzers.active_learner import ActiveLearner
    from .utils.output_models import ArticleRecord

    path = Path(jsonl_file)
    if not path.exists():
        console.print(f"[red]File not found:[/red] {jsonl_file}")
        raise typer.Exit(1)

    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(ArticleRecord(**json.loads(line)))
                except Exception:
                    continue

    if not records:
        console.print("[dim]No articles loaded.[/dim]")
        raise typer.Exit(0)

    al = ActiveLearner(strategy=strategy)
    candidates = al.select_candidates(records, n=n)

    console.print(f"\n[bold]Label Candidates[/bold]  (strategy={strategy}, n={len(candidates)})\n")
    for i, c in enumerate(candidates, 1):
        console.print(
            f"  {i:2d}. [{c['sentiment_label']}] {c['title'][:60]}"
        )
        console.print(
            f"      [dim]priority={c['priority']:.3f}  conf={c['confidence']:.3f}  {c['reason']}[/dim]"
        )

    # Export
    export_path = al.export_candidates(candidates)
    console.print(f"\n  [dim]Exported to {export_path}[/dim]")


@app.command()
def sources():
    """Show source influence rankings from historical scans."""
    from .analyzers.source_influence import SourceInfluenceTracker
    sit = SourceInfluenceTracker()
    rankings = sit.get_rankings()

    if not rankings:
        console.print("[dim]No source influence data yet. Run scans first.[/dim]")
        raise typer.Exit(0)

    console.print(f"\n[bold]Source Influence Rankings[/bold]\n")
    table = Table(box=rich.box.SIMPLE_HEAD, show_edge=False)
    table.add_column("Source", style="cyan")
    table.add_column("Leads", justify="right")
    table.add_column("Follows", justify="right")
    table.add_column("Lead %", justify="right")
    table.add_column("Avg Lead (h)", justify="right")
    table.add_column("Influence", justify="right", style="bold")

    for source, data in list(rankings.items())[:20]:
        table.add_row(
            source,
            str(data["leads"]),
            str(data["follows"]),
            f"{data['lead_ratio']:.0%}",
            f"{data['avg_lead_hours']:.1f}",
            f"{data['influence_score']:.3f}",
        )

    console.print(table)


@app.command("download-models")
def download_models():
    """Pre-download sentiment models (~1GB). Run once after install."""
    from .analyzers.sentiment_router import FINBERT_MODEL, NEWS_MODEL
    from transformers import pipeline as hf_pipeline
    console.print("[dim]Downloading FinBERT...[/dim]")
    hf_pipeline("sentiment-analysis", model=FINBERT_MODEL, top_k=None)
    console.print("[dim]Downloading news-RoBERTa...[/dim]")
    hf_pipeline("sentiment-analysis", model=NEWS_MODEL, top_k=None)
    console.print("[green]Done. Models cached in ~/.cache/huggingface/[/green]")


@app.command()
def feeds():
    """List configured RSS feeds (used with --also-rss)."""
    table = Table(title=f"Configured RSS Feeds ({len(settings.RSS_FEEDS)})")
    table.add_column("#", style="dim", width=4)
    table.add_column("URL", style="cyan")

    for i, url in enumerate(settings.RSS_FEEDS, 1):
        table.add_row(str(i), url)

    console.print(table)


if __name__ == "__main__":
    app()
