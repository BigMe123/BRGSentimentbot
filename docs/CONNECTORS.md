# Connector System Documentation

## Overview

The connector system provides a unified interface for fetching data from 11 different sources without requiring API keys (mostly). All connectors follow a consistent normalization contract to ensure seamless integration with the existing pipeline.

## Available Connectors

### 1. Reddit RSS (`reddit`)
- **Description**: Fetches posts from Reddit subreddits via RSS
- **No API key required**
- **Configuration**:
  ```yaml
  - type: reddit
    subreddits: ["worldnews", "technology"]
    sort: hot  # hot, new, rising, top
    limit: 100
  ```

### 2. Google News RSS (`google_news`)
- **Description**: Fetches news from Google News RSS feeds
- **No API key required**
- **Configuration**:
  ```yaml
  - type: google_news
    queries: ["artificial intelligence", "climate change"]
    editions: ["US", "UK"]  # Country codes
    max_per_query: 50
  ```

### 3. Hacker News (`hackernews`)
- **Description**: Fetches stories from Hacker News via Firebase API
- **No API key required**
- **Configuration**:
  ```yaml
  - type: hackernews
    categories: ["top", "new", "best", "ask", "show"]
    max_stories: 100
    fetch_comments: false  # Optional, for richer content
  ```

### 4. StackExchange (`stackexchange`)
- **Description**: Fetches questions from StackExchange sites
- **No API key required** (uses public API)
- **Configuration**:
  ```yaml
  - type: stackexchange
    sites: ["stackoverflow", "serverfault"]
    tags: ["python", "machine-learning"]
    max_questions: 50
  ```

### 5. Mastodon (`mastodon`)
- **Description**: Fetches public toots from Mastodon instances
- **No API key required** for public posts
- **Configuration**:
  ```yaml
  - type: mastodon
    instances: ["mastodon.social", "fosstodon.org"]
    hashtags: ["technology", "opensource"]
    local_only: false
    max_toots: 200
  ```

### 6. Bluesky (`bluesky`)
- **Description**: Fetches posts from Bluesky (AT Protocol)
- **Requires account** (free signup)
- **Configuration**:
  ```yaml
  - type: bluesky
    handle: "your.handle"
    password: "your_password"  # Or use env var
    queries: ["tech news", "ai"]
    max_posts: 100
  ```

### 7. YouTube RSS (`youtube`)
- **Description**: Fetches video metadata from YouTube channels
- **No API key required** for RSS
- **Configuration**:
  ```yaml
  - type: youtube
    channels: ["UCddiUEpeqJcYeBxX1IVBKvQ"]  # Channel IDs
    fetch_transcript: false  # Requires youtube-transcript-api
    max_results: 50
  ```

### 8. Wikipedia (`wikipedia`)
- **Description**: Fetches articles from Wikipedia
- **No API key required**
- **Configuration**:
  ```yaml
  - type: wikipedia
    queries: ["artificial intelligence", "quantum computing"]
    lang: en
    max_per_query: 10
  ```

### 9. GDELT (`gdelt`)
- **Description**: Fetches global events from GDELT v2
- **No API key required**
- **Configuration**:
  ```yaml
  - type: gdelt
    query: "artificial intelligence OR machine learning"
    max_items: 250
    mode: artlist  # artlist or timeline
  ```

### 10. Generic Web Scraping (`generic_web`)
- **Description**: Scrapes websites using CSS selectors
- **No API key required**
- **Configuration**:
  ```yaml
  - type: generic_web
    sites_yaml: "config/sites.yaml"  # Path to sites config
  ```
  
  Sites configuration (`sites.yaml`):
  ```yaml
  sites:
    - name: "TechCrunch"
      url: "https://techcrunch.com/"
      selector: "article"
      title: "h2.post-block__title"
      body: "div.post-block__content"
      link: "h2.post-block__title a"
      date: "time"
      lang: "en"
      limit: 20
  ```

### 11. Twitter/X via snscrape (`twitter`)
- **Description**: Fetches tweets without API key using snscrape
- **No API key required**
- **Requires**: `pip install snscrape`
- **Configuration**:
  ```yaml
  - type: twitter
    queries:
      - "lang:en artificial intelligence"
      - "from:OpenAI"
      - "#MachineLearning"
    max_per_query: 200
  ```

## Data Normalization Contract

All connectors return data in this standardized format:

```python
{
    "id": str,           # Unique identifier (SHA256-based)
    "source": str,       # Connector name (e.g., "reddit")
    "subsource": str,    # Subcategory (e.g., subreddit name)
    "author": str,       # Author/username (optional)
    "title": str,        # Title/headline (optional)
    "text": str,         # Main content text (required)
    "url": str,          # Original URL (optional)
    "published_at": datetime,  # Publication date
    "lang": str,         # Language code (e.g., "en")
    "raw": dict         # Original raw data (optional)
}
```

## Usage

### Command Line Interface

1. **List available connectors**:
   ```bash
   python -m sentiment_bot.cli_unified list-connectors
   ```

2. **Fetch from all configured connectors**:
   ```bash
   python -m sentiment_bot.cli_unified connectors
   ```

3. **Fetch from specific connector**:
   ```bash
   python -m sentiment_bot.cli_unified connectors --type reddit
   ```

4. **With sentiment analysis**:
   ```bash
   python -m sentiment_bot.cli_unified connectors --analyze
   ```

5. **With keyword filtering**:
   ```bash
   python -m sentiment_bot.cli_unified connectors --keywords "AI,machine learning"
   ```

### Python API

```python
from sentiment_bot.ingest.registry import ConnectorRegistry

# Load connectors from config
registry = ConnectorRegistry("config/sources.yaml")

# Fetch from all connectors
async for item in registry.fetch_all():
    print(f"{item['title']} from {item['source']}")

# Get specific connector
reddit = registry.get_connector("reddit")
if reddit:
    async for item in reddit.fetch():
        print(item['title'])
```

### Creating Custom Connectors

To create a new connector:

1. Inherit from `Connector` base class:
```python
from sentiment_bot.connectors.base import Connector

class MyConnector(Connector):
    name = "my_source"
    
    async def fetch(self):
        # Fetch data from your source
        for item in data:
            yield {
                "id": make_id(self.name, item_id),
                "source": self.name,
                "text": item_text,
                # ... other fields
            }
```

2. Register in `ingest/registry.py`:
```python
CONNECTORS["my_source"] = MyConnector
```

## Configuration

1. Copy the example configuration:
   ```bash
   cp config/sources.example.yaml config/sources.yaml
   ```

2. Edit `config/sources.yaml` to enable/configure connectors

3. For sensitive data (passwords, API keys), use environment variables:
   ```yaml
   - type: bluesky
     handle: "your.handle"
     password: "${BLUESKY_PASSWORD}"
   ```

## Rate Limiting

All connectors implement automatic rate limiting:
- Default delays between requests (1-5 seconds)
- Configurable limits per source
- Error handling with exponential backoff

## Error Handling

- Each connector handles errors independently
- Failed connectors don't stop others
- Detailed logging for debugging
- Graceful degradation on partial failures

## Performance Considerations

- Async/await for concurrent fetching
- Connection pooling with aiohttp
- Efficient RSS parsing with feedparser
- Minimal memory footprint with generators

## Testing

Run tests:
```bash
pytest tests/test_connectors.py -v
```

Test individual connector:
```bash
python -m sentiment_bot.cli_connectors test reddit
```

## Troubleshooting

### Common Issues

1. **No data returned**: Check network connectivity and source availability
2. **Rate limiting**: Reduce `max_items` or add delays
3. **Authentication errors**: Verify credentials for Bluesky
4. **Missing dependencies**: Install required packages:
   ```bash
   pip install feedparser aiohttp beautifulsoup4 lxml pyyaml
   pip install snscrape  # For Twitter
   ```

### Debug Mode

Enable debug logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Dependencies

Required packages:
- `aiohttp`: Async HTTP client
- `feedparser`: RSS/Atom parsing
- `beautifulsoup4`: HTML parsing
- `lxml`: XML/HTML parser
- `pyyaml`: YAML configuration
- `snscrape`: Twitter scraping (optional)

Install all:
```bash
pip install aiohttp feedparser beautifulsoup4 lxml pyyaml snscrape
```