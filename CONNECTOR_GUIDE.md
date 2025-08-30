# 🚀 BSGBOT Modern Connector System Guide

## Overview

BSGBOT now includes a powerful connector system that provides access to **11 modern data sources** including social media, forums, news aggregators, and knowledge bases. Most connectors work **without API keys** and provide real-time access to diverse content.

## 🎯 Quick Start

### 1. Setup Configuration

```bash
# Copy the example configuration
cp config/sources.example.yaml config/sources.yaml

# Edit to enable desired connectors
nano config/sources.yaml
```

### 2. List Available Connectors

```bash
# See all 11 available connector types
python -m sentiment_bot.cli_unified list-connectors
```

### 3. Basic Usage

```bash
# Fetch from all configured connectors
python -m sentiment_bot.cli_unified connectors

# Fetch from specific type
python -m sentiment_bot.cli_unified connectors --type reddit

# With sentiment analysis
python -m sentiment_bot.cli_unified connectors --analyze
```

## 📊 Available Connectors

### 1. **Reddit RSS** (`reddit`)
- **Source**: Reddit subreddit RSS feeds
- **API Key**: ❌ Not required
- **Best For**: Social sentiment, news discussions, community reactions
- **Rate Limits**: None (uses RSS feeds)

```yaml
- type: reddit
  subreddits: ["worldnews", "technology", "politics"]
  sort: hot  # hot, new, rising, top
  limit: 100
```

### 2. **Twitter/X snscrape** (`twitter`)  
- **Source**: Twitter/X via snscrape tool
- **API Key**: ❌ Not required
- **Best For**: Real-time sentiment, trending topics, breaking news
- **Rate Limits**: Self-rate limited to avoid blocks

```yaml
- type: twitter
  queries:
    - "lang:en artificial intelligence"
    - "from:OpenAI"
    - "#MachineLearning"
  max_per_query: 200
```

### 3. **Hacker News** (`hackernews`)
- **Source**: Hacker News Firebase API
- **API Key**: ❌ Not required  
- **Best For**: Tech news, startup sentiment, developer discussions
- **Rate Limits**: Firebase API limits (~10 req/min)

```yaml
- type: hackernews
  categories: ["top", "new", "best", "ask", "show"]
  max_stories: 100
  fetch_comments: false  # Optional for richer content
```

### 4. **YouTube RSS** (`youtube`)
- **Source**: YouTube channel RSS feeds
- **API Key**: ❌ Not required (RSS only)
- **Best For**: Video content analysis, creator sentiment
- **Rate Limits**: None (RSS feeds)

```yaml
- type: youtube
  channels:
    - "UCddiUEpeqJcYeBxX1IVBKvQ"  # The Verge
    - "UCBJycsmduvYEL83R_U4JriQ"  # MKBHD
  fetch_transcript: false  # Requires additional setup
  max_results: 50
```

### 5. **Wikipedia** (`wikipedia`)
- **Source**: Wikipedia MediaWiki API
- **API Key**: ❌ Not required
- **Best For**: Background research, entity information, factual content
- **Rate Limits**: Self-rate limited (1 req/sec)

```yaml
- type: wikipedia
  queries: ["artificial intelligence", "quantum computing"]
  lang: en
  max_per_query: 10
```

### 6. **Google News RSS** (`google_news`)
- **Source**: Google News RSS feeds
- **API Key**: ❌ Not required
- **Best For**: Global news aggregation, multi-language content
- **Rate Limits**: None (RSS feeds)

```yaml
- type: google_news
  queries: ["artificial intelligence", "climate change"]
  editions: ["US", "UK", "CA"]  # Country codes
  max_per_query: 50
```

### 7. **Mastodon** (`mastodon`)
- **Source**: Mastodon federated social network
- **API Key**: ❌ Not required (public posts)
- **Best For**: Decentralized social media, tech community sentiment
- **Rate Limits**: Per-instance limits (usually generous)

```yaml
- type: mastodon
  instances: ["mastodon.social", "fosstodon.org"]
  hashtags: ["technology", "opensource"]
  local_only: false
  max_toots: 200
```

### 8. **Bluesky** (`bluesky`)
- **Source**: Bluesky social network (AT Protocol)
- **API Key**: 🔑 Account required (free signup)
- **Best For**: Next-generation social media, early adopter sentiment
- **Rate Limits**: Account-based limits

```yaml
- type: bluesky
  handle: "your.handle"
  password: "your_password"  # Or use environment variable
  queries: ["tech news", "ai"]
  max_posts: 100
```

### 9. **StackExchange** (`stackexchange`)
- **Source**: Stack Overflow and other StackExchange sites
- **API Key**: ❌ Not required (public API)
- **Best For**: Technical Q&A, developer sentiment, programming trends
- **Rate Limits**: 300 requests/day per IP

```yaml
- type: stackexchange
  sites: ["stackoverflow", "serverfault", "askubuntu"]
  tags: ["python", "machine-learning", "docker"]
  max_questions: 50
```

### 10. **GDELT** (`gdelt`)
- **Source**: GDELT Global Events Database
- **API Key**: ❌ Not required
- **Best For**: Global events, geopolitical analysis, crisis monitoring
- **Rate Limits**: 250 requests/hour

```yaml
- type: gdelt
  query: "artificial intelligence OR machine learning"
  max_items: 250
  mode: artlist  # artlist or timeline
```

### 11. **Generic Web Scraping** (`generic_web`)
- **Source**: Any website with CSS selectors
- **API Key**: ❌ Not required
- **Best For**: Custom websites, niche sources, specialized content
- **Rate Limits**: Self-configured delays

```yaml
- type: generic_web
  sites_yaml: "config/sites.yaml"
```

Example sites configuration:
```yaml
# config/sites.yaml
sites:
  - name: "TechCrunch"
    url: "https://techcrunch.com/"
    selector: "article"
    title: "h2.post-block__title"
    body: "div.post-block__content"
    link: "h2.post-block__title a"
    date: "time"
    limit: 20
```

## 🎮 Usage Examples

### Basic Operations

```bash
# List all available connector types
python -m sentiment_bot.cli_unified list-connectors

# Fetch from all configured connectors (limit 10 per type)
python -m sentiment_bot.cli_unified connectors --limit 10

# Fetch only from Reddit
python -m sentiment_bot.cli_unified connectors --type reddit --limit 50

# Multiple specific types
python -m sentiment_bot.cli_unified connectors --type hackernews --limit 20
```

### Advanced Features

```bash
# With sentiment analysis
python -m sentiment_bot.cli_unified connectors --analyze --limit 20

# With keyword filtering
python -m sentiment_bot.cli_unified connectors --keywords "AI,artificial intelligence,machine learning" --limit 30

# Custom output directory
python -m sentiment_bot.cli_unified connectors --output-dir ./my_results --limit 25

# Specific config file
python -m sentiment_bot.cli_unified connectors --config config/my_sources.yaml
```

## 📊 Output Format

All connectors produce consistent, normalized JSON output:

```json
{
  "id": "stable_hash_id",
  "source": "reddit",
  "subsource": "r/worldnews",
  "author": "username",
  "title": "Article headline",
  "text": "Full article text content",
  "url": "https://source.url",
  "published_at": "2024-01-15T10:30:00+00:00",
  "lang": "en",
  "raw": { /* original API response */ }
}
```

### Output Files

Each run creates timestamped output files:

```
output/
├── connector_results_20240115_103000.json  # All articles
└── (other analysis outputs if --analyze used)
```

## 🔧 Configuration Guide

### Environment Variables

For sensitive data, use environment variables:

```bash
export BLUESKY_PASSWORD="your_password"
export REDDIT_USER_AGENT="your_app_name"
```

Reference in config:
```yaml
- type: bluesky
  handle: "your.handle"  
  password: "${BLUESKY_PASSWORD}"
```

### Rate Limiting & Performance

All connectors include built-in rate limiting:
- **Automatic delays**: 1-5 seconds between requests
- **Error handling**: Graceful failure recovery
- **Timeout protection**: Request timeouts prevent hangs
- **Concurrent execution**: Multiple connectors run in parallel

### Customization

#### Reddit Subreddits
```yaml
- type: reddit
  subreddits: 
    - "worldnews"      # Global news
    - "technology"     # Tech discussions  
    - "politics"       # Political sentiment
    - "economics"      # Economic discussions
    - "cryptocurrency" # Crypto sentiment
  sort: hot            # hot, new, rising, top
  limit: 200
```

#### Twitter/X Search Queries
```yaml
- type: twitter
  queries:
    - "lang:en (AI OR \"artificial intelligence\")"
    - "from:elonmusk OR from:OpenAI"
    - "#Bitcoin OR #Ethereum"
    - "\"climate change\" min_retweets:10"
  max_per_query: 100
```

#### YouTube Channel Selection
```yaml
- type: youtube
  channels:
    - "UCddiUEpeqJcYeBxX1IVBKvQ"  # The Verge (tech news)
    - "UCBJycsmduvYEL83R_U4JriQ"  # MKBHD (tech reviews)
    - "UCsooa4yRKGN_zEE8iknghZA"  # TED-Ed (educational)
    - "UC-9-kyTW8ZkZNDHQJ6FgpwQ"  # Music channels for sentiment
```

#### Wikipedia Topics
```yaml
- type: wikipedia
  queries:
    - "artificial intelligence"
    - "quantum computing" 
    - "renewable energy"
    - "cryptocurrency"
    - "space exploration"
  max_per_query: 5  # Keep low to avoid overloading
```

## ⚡ Performance Tips

### Optimize for Speed
```bash
# Parallel execution with limits
python -m sentiment_bot.cli_unified connectors --limit 10

# Focus on fastest sources
python -m sentiment_bot.cli_unified connectors --type reddit --type hackernews
```

### Optimize for Coverage
```bash
# All sources, higher limits
python -m sentiment_bot.cli_unified connectors --limit 100

# Include slower but comprehensive sources
python -m sentiment_bot.cli_unified connectors --type gdelt --type wikipedia
```

### Memory Management
- Use `--limit` to control memory usage
- RSS-based connectors (reddit, youtube, google_news) are most memory-efficient
- API-based connectors may use more memory for JSON parsing

## 🛠️ Troubleshooting

### Common Issues

**1. No data returned**
```bash
# Check network connectivity
curl -I https://reddit.com

# Verify configuration
python -m sentiment_bot.cli_unified list-connectors
```

**2. Rate limiting errors**
```bash
# Reduce limits in config
- type: hackernews
  max_stories: 10  # Reduced from 100

# Add delays between runs
sleep 60 && python -m sentiment_bot.cli_unified connectors
```

**3. Authentication errors (Bluesky)**
```bash
# Verify credentials
export BLUESKY_PASSWORD="correct_password"

# Test with minimal config
- type: bluesky
  handle: "your.handle"
  password: "${BLUESKY_PASSWORD}"
  max_posts: 1
```

**4. Missing dependencies**
```bash
# Install required packages
pip install feedparser aiohttp beautifulsoup4 lxml pyyaml

# For Twitter support
pip install snscrape
```

### Debug Mode

Enable detailed logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Or use environment variable:
```bash
export PYTHONPATH=. 
export LOG_LEVEL=DEBUG
python -m sentiment_bot.cli_unified connectors
```

## 📈 Best Practices

### 1. **Start Small**
```yaml
# Test configuration
sources:
  - type: reddit
    subreddits: ["test"]
    limit: 5
  - type: hackernews  
    max_stories: 5
```

### 2. **Progressive Scaling**
```bash
# Test -> Development -> Production
--limit 10   # Testing
--limit 50   # Development  
--limit 200  # Production
```

### 3. **Source Diversity**
```yaml
# Mix fast and slow sources
sources:
  - type: reddit      # Fast, high volume
    limit: 100
  - type: hackernews  # Fast, tech focused
    limit: 50
  - type: wikipedia   # Slow, factual
    limit: 10
  - type: gdelt       # Slow, comprehensive
    limit: 20
```

### 4. **Monitoring**
```bash
# Regular health checks
python -m sentiment_bot.cli_unified connectors --limit 1

# Monitor output sizes
ls -lah output/connector_results_*.json

# Check for errors in logs
grep -i error logs/connector.log
```

## 🔮 Advanced Features

### Custom Filtering
```bash
# Filter by keywords
python -m sentiment_bot.cli_unified connectors \
  --keywords "artificial intelligence,machine learning,neural networks" \
  --limit 50

# Results only include articles matching keywords
```

### Sentiment Analysis Integration
```bash
# Analyze sentiment on fetched content
python -m sentiment_bot.cli_unified connectors --analyze --limit 30

# Output includes sentiment scores:
# {"sentiment": {"label": "positive", "confidence": 0.85}}
```

### Output Customization
```bash
# Custom output directory
python -m sentiment_bot.cli_unified connectors \
  --output-dir /path/to/results \
  --limit 25

# Results saved to custom location with timestamps
```

## 🚀 Integration Examples

### Python API Usage
```python
from sentiment_bot.ingest.registry import ConnectorRegistry

# Load connectors from config
registry = ConnectorRegistry("config/sources.yaml")

# Fetch from all connectors
async for item in registry.fetch_all():
    print(f"Title: {item['title']}")
    print(f"Source: {item['source']}")
    print(f"URL: {item['url']}")
```

### Pipeline Integration
```python
# Combine with existing analysis
from sentiment_bot.analyzer import analyze

registry = ConnectorRegistry("config/sources.yaml")

async for item in registry.fetch_all():
    # Analyze with existing BSGBOT pipeline
    result = analyze(item['text'])
    
    # Combine connector data with analysis
    enriched = {
        **item,
        'sentiment': result.sentiment,
        'volatility': result.volatility,
        'entities': result.entities
    }
```

## 📚 Additional Resources

- **Connector Documentation**: [docs/CONNECTORS.md](docs/CONNECTORS.md)
- **Configuration Examples**: [config/sources.example.yaml](config/sources.example.yaml)
- **Test Suite**: [tests/test_connectors.py](tests/test_connectors.py)
- **API Reference**: See inline code documentation

## 🤝 Support

For issues or questions:
- 📧 bostonriskgroup@gmail.com
- 🐛 GitHub Issues: [BigMe123/BSGBOT](https://github.com/BigMe123/BSGBOT/issues)
- 📱 Phone: +1 646-877-2527

---

**Built with ❤️ by Boston Risk Group**  
*Modern Data Intelligence Through Advanced Connectors*