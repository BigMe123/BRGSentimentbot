# Connector System Upgrades - Yield & Relevance Enhancement

## 🚀 New Features Overview

The connector system has been upgraded with **keyword fan-out**, **enhanced pagination**, and **comprehensive filtering** to maximize yield and relevance.

### Key Enhancements

1. **Keyword Fan-out**: Each query/hashtag gets separate API requests instead of merged queries
2. **Enhanced Pagination**: True pagination with per-query/per-source limits
3. **Date Window Support**: `--since` parameter for temporal filtering
4. **Post-fetch Filtering**: Defensive keyword matching after retrieval
5. **Comprehensive Metrics**: Detailed fetch/filter/save statistics
6. **Rate Limiting**: Configurable delays to prevent API abuse
7. **New Connectors**: HackerNews search via Algolia API

## 🎯 Acceptance Criteria Met

```bash
# Target command that now works perfectly:
bsgbot connectors --keywords "crypto,blockchain,bitcoin,ethereum,web3,defi" --limit 400 --since 7d

# Expected: Dozens+ results across all sources with comprehensive metrics
```

## 📋 Updated Connector Parameters

### Reddit (`reddit`)
```yaml
- type: reddit
  queries:  # NEW: Search mode with fan-out
    - "cryptocurrency"
    - "blockchain"  
  # OR traditional subreddit mode:
  # subreddits: ["CryptoCurrency", "bitcoin"]
  sort: new  # new, hot, top, rising
  time: week  # hour, day, week, month (for search)
  limit_per_sub: 200  # Enhanced per-query limit
  delay_ms: 300  # NEW: Rate limiting
```

### Google News (`google_news`) 
```yaml
- type: google_news
  queries:  # Fan-out across editions
    - "(crypto OR blockchain)"
    - "bitcoin"
  editions:  # Each query × each edition = separate request
    - "en-US"
    - "en-GB"
  per_query_cap: 200  # Per query per edition
  delay_ms: 300  # NEW: Rate limiting
```

### Twitter/X (`twitter`)
```yaml
- type: twitter
  queries:  # Enhanced snscrape integration
    - '"crypto" since:2025-08-20'
    - '"blockchain" lang:en'
  max_per_query: 400  # Per query limit
  delay_ms: 0  # Usually no delay needed
  # Automatically checks snscrape availability
```

### HackerNews Search (`hackernews_search`) - **NEW!**
```yaml
- type: hackernews_search  # Via Algolia API
  queries:
    - "cryptocurrency"
    - "blockchain"
  hits_per_page: 100
  pages: 3  # Pages per query
  tags: "story"  # story, comment, poll, job
  delay_ms: 100
```

### StackExchange (`stackexchange`)
```yaml
- type: stackexchange
  sites:
    - stackoverflow
    - bitcoin
  queries:  # NEW: Search mode instead of tags
    - "blockchain"
    - "cryptocurrency"
  pages: 3  # Pages per site per query
  pagesize: 50
  delay_ms: 200
```

### Mastodon (`mastodon`)
```yaml
- type: mastodon
  instance: mastodon.social
  hashtags:  # Fan-out per hashtag
    - "crypto"
    - "blockchain"
  limit_per_tag: 100  # Per hashtag limit
  delay_ms: 500
```

### Bluesky (`bluesky`)
```yaml
- type: bluesky  # No auth needed for public search
  queries:
    - "crypto"
    - "blockchain"
  limit_per_query: 100
  delay_ms: 1000  # Stricter rate limiting
```

### YouTube (`youtube`)
```yaml
- type: youtube
  channels:  # Fan-out per channel
    - "UCrYxSrpsJkqUxHbFHfWuNLq"  # Coin Bureau
  max_per_channel: 50
  delay_ms: 500
```

### Wikipedia (`wikipedia`)
```yaml
- type: wikipedia
  queries:  # Fan-out per query
    - "cryptocurrency"  
    - "blockchain"
  max_per_query: 10
  delay_ms: 200
```

### GDELT (`gdelt`)
```yaml
- type: gdelt
  queries:  # Fan-out support
    - "cryptocurrency"
    - ""  # Empty = latest articles
  max_per_query: 250
  delay_ms: 500
```

## 🔧 CLI Enhancements

### New `--since` Parameter
```bash
# Relative time windows
bsgbot connectors --since 24h   # Last 24 hours
bsgbot connectors --since 7d    # Last 7 days  
bsgbot connectors --since 1w    # Last week
bsgbot connectors --since 1m    # Last month

# Absolute dates
bsgbot connectors --since 2025-01-01
bsgbot connectors --since "2025-01-15 12:00:00"
```

### Enhanced Metrics Output
```
📊 Connector Metrics Summary

Overall Metrics:
┌─────────────────┬───────┬───────┐
│ Metric          │ Count │ Rate  │
├─────────────────┼───────┼───────┤
│ Raw Fetched     │ 2,450 │ 100%  │
│ After Keywords  │ 1,890 │ 77.1% │
│ After Since     │ 1,234 │ 65.3% │
│ Final Saved     │ 1,234 │       │
└─────────────────┴───────┴───────┘

Per-Connector Breakdown:
┌─────────────┬─────────┬──────────┬───────┬───────┬────────┐
│ Connector   │ Fetched │ Keywords │ Since │ Saved │ Time   │
├─────────────┼─────────┼──────────┼───────┼───────┼────────┤
│ google_news │ 800     │ 620      │ 400   │ 400   │ 2.1s   │
│ reddit      │ 600     │ 480      │ 350   │ 350   │ 1.8s   │
│ twitter     │ 500     │ 450      │ 284   │ 284   │ 3.2s   │
│ hackernews  │ 300     │ 200      │ 120   │ 120   │ 1.5s   │
└─────────────┴─────────┴──────────┴───────┴───────┴────────┘
```

## 🧪 Testing Examples

### Basic Crypto Collection
```bash
bsgbot connectors \
  --keywords "crypto,blockchain,bitcoin,ethereum" \
  --limit 400 \
  --since 7d
```

### Targeted Source Testing  
```bash
bsgbot connectors \
  --type google_news \
  --keywords "bitcoin" \
  --limit 100 \
  --since 24h
```

### Full Analysis Pipeline
```bash
bsgbot connectors \
  --keywords "web3,defi" \
  --limit 500 \
  --since 3d \
  --analyze \
  --config config/sources.crypto.yaml
```

### New HackerNews Search
```bash
bsgbot connectors \
  --type hackernews_search \
  --keywords "cryptocurrency,blockchain" \
  --limit 200
```

## 📁 Configuration Files

- `config/sources.example.yaml` - Updated with all new parameters
- `config/sources.crypto.yaml` - Crypto-focused example configuration
- `config/sources.yaml` - Your customized configuration

## 🎛️ Advanced Features

### Availability Checking
- **Twitter**: Automatically detects if `snscrape` is installed
- **Graceful Degradation**: Skips unavailable connectors with warnings

### Smart Rate Limiting
- **Per-connector delays**: Prevents API abuse
- **Domain-aware**: Respects different API limits
- **Configurable**: Adjust `delay_ms` per connector

### Post-fetch Filtering
- **Defensive**: Keywords matched after fetch for reliability
- **Temporal**: Since filtering applied to `published_at` timestamps
- **Comprehensive**: Tracks filter effectiveness in metrics

### Error Resilience
- **Per-query isolation**: One failed query doesn't break the connector
- **Detailed logging**: Shows exactly what succeeded/failed
- **Metrics preservation**: Errors tracked but don't stop collection

## ⚡ Performance Optimizations

1. **Concurrent Execution**: Multiple connectors run in parallel
2. **Async Architecture**: Non-blocking HTTP requests
3. **Smart Pagination**: Only fetches needed pages
4. **Rate Limiting**: Prevents unnecessary delays from hitting limits
5. **Memory Efficient**: Streaming results instead of bulk loading

## 🚨 Migration Notes

### Breaking Changes
- **StackExchange**: `tags` parameter deprecated, use `queries` for search
- **Mastodon**: `instances` array replaced with single `instance`
- **Parameter Names**: Some limits renamed for consistency

### Backward Compatibility
- Old configurations still work with warnings
- Graceful parameter mapping where possible
- Clear error messages for required updates

---

**Result**: The system now reliably delivers dozens of relevant articles with the target command, meeting all acceptance criteria with comprehensive metrics and filtering capabilities.