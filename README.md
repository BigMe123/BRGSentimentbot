# BRG Sentiment Bot

Multi-source news intelligence platform. Fetches articles from NewsAPI/TheNewsAPI/RSS/GDELT, runs sentiment analysis (VADER or GPT-4o-mini), extracts structured geopolitical events, and outputs institutional-grade reports.

---

## Setup

```bash
git clone <repo-url> && cd BRGSentimentbot
pip install -e ".[all]"
```

Create `.env`:

```
NEWSAPI_KEY=your_key
THENEWSAPI_KEY=your_key          # optional, paid — higher volume
OPENAI_API_KEY=your_key           # required for --llm, --extract-events, --summarize
FRED_API_KEY=your_key             # optional, economic data
ALPHA_VANTAGE_API_KEY=your_key    # optional, market data
```

Get API keys:
- NewsAPI: https://newsapi.org
- TheNewsAPI: https://www.thenewsapi.com
- OpenAI: https://platform.openai.com/api-keys

---

## CLI Usage

```bash
# Top headlines (default)
bsgbot run

# Search a topic
bsgbot run "AI regulation"

# Category + country
bsgbot run --category business --country gb

# LLM-powered sentiment analysis
bsgbot run "trade war" --llm

# Extract structured geopolitical events
bsgbot run "sanctions" --extract-events

# Full pipeline: LLM sentiment + events + AI summaries + CSV
bsgbot run "oil prices" --llm --extract-events --summarize --export-csv

# Include RSS feeds alongside NewsAPI
bsgbot run --also-rss --max-feeds 50

# Set freshness window
bsgbot run --freshness 30d

# View extracted events from a previous run
bsgbot events output/events_abc123.jsonl
bsgbot events output/events_abc123.jsonl --actor "United States" --domain economic

# List configured RSS feeds
bsgbot feeds
```

### All flags

| Flag | Description |
|------|-------------|
| `query` | Search term (positional) |
| `--category` | NewsAPI category: business, technology, science, health, sports, entertainment, general |
| `--country` | 2-letter code (us, gb, de, etc.) |
| `--region` | Post-fetch keyword filter (asia, europe, middle_east, etc.) |
| `--topic` | Post-fetch keyword filter (energy, elections, sanctions, etc.) |
| `--freshness` | Age window: 1h, 6h, 24h, 7d, 30d (default: 7d) |
| `--target-articles` | Target article count (default: 300) |
| `--also-rss` | Also fetch from ~190 configured RSS feeds |
| `--max-feeds` | Limit RSS feeds (0 = all) |
| `--llm` | Use GPT-4o-mini for sentiment (requires OPENAI_API_KEY) |
| `--extract-events` | Extract actor-action-receiver events via LLM |
| `--summarize` | Generate AI article summaries |
| `--export-csv` | Also export as CSV |
| `--output-dir` | Output directory (default: ./output) |
| `--debug` | Verbose logging |

---

## Streamlit Dashboard

```bash
pip install streamlit plotly altair
streamlit run dashboard.py
```

Pages: Overview, Article Browser, AI Analyst (GPT-powered intelligence briefs), Events, Configuration, Health.

---

## How It Works

### Pipeline

```
Fetch --> Deduplicate --> Freshness Filter --> Keyword Filter --> Full Text --> Analyze --> Extract Events --> Output
```

### 1. Fetching

Three sources run in sequence:

- **TheNewsAPI** (primary, paid) or **NewsAPI** (fallback, free) — keyword search or top headlines
- **RSS feeds** (optional, ~190 feeds) — async parallel with circuit breaker
- **GDELT v2** (always on) — global event articles

Articles are normalized to a common dict: `{title, link, description, content, domain, published, published_date, url_hash}`.

### 2. Filtering

- **Dedup**: URL hash-based, preserves order
- **Freshness**: Drop articles older than `--freshness` window
- **Keywords**: Filter by region/topic mappings (config.py `REGION_MAP`, `TOPIC_MAP`)
- **Full text**: Scrapes article body via newspaper3k + requests fallback (NewsAPI truncates to ~200 chars)

### 3. Sentiment Analysis

Two modes:

**VADER (default)** — lexicon-based, no API needed, fast. Score range: -1.0 to +1.0. Labels: pos (>0.05), neg (<-0.05), neu.

**LLM (--llm)** — GPT-4o-mini via OpenAI API. Returns structured JSON with sentiment, confidence, entities, trading signals, market implications. Cached in SQLite to avoid repeat calls.

### 4. Event Extraction (--extract-events)

Uses GPT-4o-mini to decompose each article into 0-5 structured events:

```json
{
  "actor": {"name": "United States", "type": "state"},
  "action": {"verb": "imposed sanctions on", "category": "economic"},
  "receiver": {"name": "Russia", "type": "state"},
  "tone": -7,
  "domain": "economic",
  "intensity": 4,
  "stance": "oppose",
  "location": {"name": "Washington DC"},
  "event_date": "2025-04-20",
  "confidence": 0.9
}
```

Fields:
- **actor/receiver**: `{name, type}` — type: state, org, person, group, sector, public
- **action**: `{verb, category}` — category: cooperate, confront, military, economic, diplomatic, regulatory, communicate
- **tone**: -10 (hostile) to +10 (cooperative)
- **domain**: military, economic, diplomatic, legal, social, tech
- **intensity**: 1 (routine) to 5 (crisis)
- **stance**: support, oppose, neutral, threaten, request
- **location**: where the event happened (not where reported)
- **event_date**: when the event happened (not publication date)

### 5. Entity & Signal Detection

Pattern-based extraction (no API needed):
- **Countries**: 250+ with regional grouping
- **Organizations**: 40+ (ECB, Fed, IMF, major corps)
- **Tickers**: Regex [A-Z]{2,5} with stopword filter
- **Themes**: inflation, monetary_policy, geopolitical_risk, ai_disruption, etc.
- **Volatility**: 0.0-1.0 score from crisis/crash/surge keywords
- **Risk level**: high, elevated, normal, low

### 6. Source Credibility

Three tiers with sentiment weighting:
- **Tier 1** (weight 1.0): Reuters, AP, BBC, NYT, WSJ, Bloomberg, FT, etc.
- **Tier 2** (weight 0.8): CNBC, Forbes, Politico, CFR, Brookings, Defense News, etc.
- **Tier 3** (weight 0.5): Aggregators, blogs, unknown sources

---

## Output Files

All written to `./output/`:

| File | Format | Contents |
|------|--------|----------|
| `articles_<run_id>.jsonl` | JSONL | One article record per line — sentiment, entities, signals, events |
| `run_summary_<run_id>.json` | JSON | Aggregate metrics — sentiment breakdown, top entities, volatility index, diversity score |
| `dashboard_run_summary_<run_id>.txt` | TXT | Human-readable one-page brief |
| `events_<run_id>.jsonl` | JSONL | One event per line with parent article metadata |
| `articles_<run_id>.csv` | CSV | Flat table (optional, --export-csv) |

---

## Project Structure

```
BRGSentimentbot/
  run.py                    # Entry point
  dashboard.py              # Streamlit dashboard
  ai_analyst.py             # GPT-powered intelligence analysis (used by dashboard)
  pyproject.toml            # Dependencies
  .env                      # API keys (not committed)

  sentiment_bot/
    cli_unified.py          # CLI commands: run, events, feeds
    config.py               # Settings, RSS feed list, region/topic maps
    analyzer.py             # VADER sentiment
    fetcher.py              # Async RSS/web fetcher
    llm_client.py           # OpenAI/Anthropic async client with retry
    llm_cache.py            # SQLite response cache

    analyzers/
      llm_analyzer.py       # GPT-4o-mini sentiment analysis
      event_extractor.py    # Geopolitical event extraction
      sentiment_ensemble.py # Multi-model voting (DistilBERT + RoBERTa + BART)
      aspect_extraction.py  # spaCy-based aspect extraction
      topic_nli.py          # Zero-shot topic classification
      sarcasm.py            # Sarcasm detection
      cluster.py            # Document clustering

    connectors/
      gdelt.py              # GDELT v2 global events
      reddit_rss.py         # Reddit feeds
      youtube.py            # YouTube search
      bluesky.py            # Bluesky posts
      ...                   # 22 connectors total

    utils/
      output_models.py      # Pydantic schemas (ArticleRecord, RunSummary, ExtractedEvent)
      output_writer.py      # JSONL, JSON, CSV, TXT writers
      entity_extractor.py   # Country/org/ticker/theme extraction
      source_tiers.py       # Credibility tiers (1-3)
      run_id.py             # Unique run ID generation

  config/
    defaults.yaml           # ML model settings, pipeline tuning
    rss_registry.yaml       # RSS feeds by region/domain

  output/                   # Run outputs
  state/                    # LLM cache (SQLite)
  tests/                    # pytest suite
```

---

## LLM Configuration

Set in `.env`:

```
LLM_PROVIDER=openai         # openai, anthropic, or http (for local models)
LLM_MODEL=gpt-4o-mini       # any OpenAI/Anthropic model
LLM_TEMPERATURE=0           # deterministic
LLM_MAX_TOKENS=4000
LLM_CONCURRENCY=4           # parallel API calls
LLM_BASE_URL=https://api.openai.com/v1  # change for local models
```

Responses are cached in `state/llm_cache.sqlite` (SHA256 key of model + prompt). Same article won't hit the API twice.

---

## Dependencies

**Core** (always installed):
feedparser, aiohttp, vaderSentiment, typer, rich, pydantic-settings, beautifulsoup4, python-dateutil, numpy, pyyaml

**Optional extras:**
```bash
pip install -e ".[ml]"      # transformers, torch, spacy — ensemble models
pip install -e ".[llm]"     # openai — GPT analysis
pip install -e ".[newsapi]" # newsapi-python
pip install -e ".[all]"     # everything
```

---

## Tests

```bash
pytest -q --cov=sentiment_bot
```
