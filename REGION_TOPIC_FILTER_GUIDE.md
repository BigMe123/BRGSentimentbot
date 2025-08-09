# Region and Topic Filtering Guide

## Overview
The enhanced sentiment bot now includes intelligent filtering to ensure articles match both a specified region AND topic, avoiding false positives like "Asia Cup in London" when searching for Asia+Defense content.

## Usage

### Command Line
```bash
# Basic usage with region and topic filtering
poetry run sentiment-bot once-filtered --region asia --topic defense

# With custom RSS feeds
poetry run sentiment-bot once-filtered --region europe --topic elections --feeds custom_feeds.txt

# With debug logging to see filter decisions
poetry run sentiment-bot once-filtered --region middle_east --topic economy --log-level DEBUG
```

### Supported Regions
- `asia` - China, India, Japan, Southeast Asia, etc.
- `europe` - EU countries, UK, Russia, etc.
- `middle_east` - Israel, Iran, Saudi Arabia, UAE, etc.
- `africa` - Nigeria, Egypt, South Africa, Kenya, etc.
- `americas` - USA, Canada, Latin America
- `oceania` - Australia, New Zealand, Pacific Islands

### Supported Topics
- `elections` - Voting, campaigns, political races
- `defense` - Military, security, armed forces
- `economy` - Markets, trade, GDP, inflation
- `technology` - AI, software, internet, innovation
- `climate` - Climate change, renewable energy, environment
- `health` - Healthcare, medicine, pandemic response

## How It Works

### 1. Keyword Matching
The filter uses comprehensive keyword lists for each region and topic, checking both article titles and content.

### 2. Relevance Scoring
- **Region Score**: Keyword matches per 1000 characters
- **Topic Score**: Topic-specific term frequency
- **Combined Score**: Multiplicative score requiring both region AND topic relevance

### 3. False Positive Prevention
- Sports articles mentioning regions (e.g., "Asia Cup") require higher relevance scores
- Articles must meet minimum thresholds for both region AND topic
- Language detection ensures English-only content

### 4. Debug Output
With `--log-level DEBUG`, you'll see:
```
[FILTER] Dropped https://example.com/article - Low topic relevance (0.30 < 0.5)
         Scores: region=1.20, topic=0.30
[KEEP] https://example.com/relevant - Scores: region=2.50, topic=1.80
```

## Integration with Existing Pipeline
The filter integrates seamlessly with the existing anti-bot measures and multi-source fetching:
1. RSS feeds are fetched with anti-bot headers
2. Articles are downloaded with circuit breakers and caching
3. **NEW: Relevance filtering applied here**
4. Sentiment analysis on filtered articles
5. Results displayed with volatility scores

## Customization

### Adding Custom Keywords
```python
from sentiment_bot.filter import add_custom_keywords, add_custom_topic_keywords

# Add region-specific terms
add_custom_keywords("asia", ["asean", "apac", "indo-pacific"])

# Add topic-specific terms
add_custom_topic_keywords("defense", ["cyber warfare", "space force"])
```

### Adjusting Thresholds
The filter uses these default thresholds:
- Minimum region score: 0.5
- Minimum topic score: 0.5
- Minimum combined score: 0.25

These can be adjusted in the `is_relevant()` function call.

## Statistics
After filtering, you'll see enhanced stats:
```
Total articles attempted: 150
Successfully fetched: 120
Filtered out (irrelevant): 85
Final relevant articles: 35
```

## Example Output
```bash
$ poetry run sentiment-bot once-filtered --region asia --topic defense

Fetching articles for Region: asia, Topic: defense
════════════════════════════════════════════════════

Ingestion Summary
─────────────────
Total articles: 28
Filtered out: 92
Success rate: 80.0%
Data quality: 75.3%

Top Relevant Articles
─────────────────────
1. China announces new military exercises near Taiwan
   URL: https://example.com/china-military
   Preview: Beijing has announced comprehensive military drills...

2. Japan increases defense budget amid regional tensions
   URL: https://example.com/japan-defense
   Preview: Tokyo approved a record defense budget...
```