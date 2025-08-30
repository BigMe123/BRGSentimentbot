# ⚡ Quick Connector Setup Guide

## 🚀 5-Minute Setup

### 1. Install Dependencies
```bash
# Core packages (required)
pip install aiohttp feedparser beautifulsoup4 lxml pyyaml python-dateutil

# Optional: For Twitter support
pip install snscrape
```

### 2. Setup Configuration
```bash
# Copy example configuration
cp config/sources.example.yaml config/sources.yaml

# Edit with your preferred sources (optional)
nano config/sources.yaml
```

### 3. Test Installation
```bash
# List available connectors
python -m sentiment_bot.cli_unified list-connectors

# Test with minimal data
python -m sentiment_bot.cli_unified connectors --limit 5
```

## 🎯 Ready-to-Use Configurations

### **Minimal Setup** (Fast, No API Keys)
```yaml
# config/sources.yaml
sources:
  - type: reddit
    subreddits: ["worldnews"]
    limit: 20
    
  - type: hackernews
    max_stories: 10
```

### **Comprehensive Setup** (All Free Sources)
```yaml
# config/sources.yaml  
sources:
  # Social Media
  - type: reddit
    subreddits: ["worldnews", "technology", "politics"]
    limit: 50
    
  # Tech Community
  - type: hackernews
    categories: ["top"]
    max_stories: 30
    
  # News Aggregation
  - type: google_news
    queries: ["technology", "artificial intelligence"]
    editions: ["US"]
    max_per_query: 25
    
  # Knowledge Base
  - type: wikipedia
    queries: ["artificial intelligence"]
    max_per_query: 5
    
  # Optional: Twitter (requires snscrape)
  - type: twitter
    queries: ["lang:en AI"]
    max_per_query: 20
```

### **Production Setup** (Full Coverage)
```yaml
# config/sources.yaml
sources:
  # High-volume sources
  - type: reddit
    subreddits: ["worldnews", "technology", "politics", "economics", "cryptocurrency"]
    sort: hot
    limit: 100
    
  - type: google_news  
    queries: ["artificial intelligence", "machine learning", "technology", "politics"]
    editions: ["US", "UK", "CA"]
    max_per_query: 50
    
  # Tech-focused
  - type: hackernews
    categories: ["top", "best"]
    max_stories: 50
    
  - type: stackexchange
    sites: ["stackoverflow", "serverfault"]  
    tags: ["python", "machine-learning"]
    max_questions: 30
    
  # Social media
  - type: mastodon
    instances: ["mastodon.social", "fosstodon.org"]
    hashtags: ["technology", "AI"]
    max_toots: 100
    
  - type: twitter
    queries: ["lang:en (AI OR \"artificial intelligence\")", "#MachineLearning"]
    max_per_query: 50
    
  # Comprehensive sources  
  - type: youtube
    channels: ["UCddiUEpeqJcYeBxX1IVBKvQ", "UCBJycsmduvYEL83R_U4JriQ"]
    max_results: 25
    
  - type: wikipedia
    queries: ["artificial intelligence", "quantum computing", "renewable energy"]
    max_per_query: 10
    
  - type: gdelt
    query: "artificial intelligence OR technology"
    max_items: 50
```

## 🎮 Common Usage Patterns

### **Quick News Check** (30 seconds)
```bash
python -m sentiment_bot.cli_unified connectors --type reddit --type hackernews --limit 10
```

### **Tech Sentiment Analysis** (2 minutes)  
```bash
python -m sentiment_bot.cli_unified connectors --analyze --keywords "AI,technology" --limit 30
```

### **Comprehensive Scan** (5 minutes)
```bash
python -m sentiment_bot.cli_unified connectors --limit 50
```

### **Targeted Research** 
```bash
# Focus on specific topics
python -m sentiment_bot.cli_unified connectors --keywords "climate,renewable energy" --limit 40

# Focus on specific sources
python -m sentiment_bot.cli_unified connectors --type wikipedia --type gdelt --limit 20
```

## 🛠️ Troubleshooting

### No Results?
```bash
# Check network connectivity
curl -I https://reddit.com

# Verify config syntax
python -c "import yaml; yaml.safe_load(open('config/sources.yaml'))"

# Test individual connector
python -m sentiment_bot.cli_unified connectors --type reddit --limit 1
```

### Rate Limited?
```bash
# Reduce limits temporarily
python -m sentiment_bot.cli_unified connectors --limit 5

# Try different sources
python -m sentiment_bot.cli_unified connectors --type reddit --type google_news
```

### Dependencies Missing?
```bash
# Install all at once
pip install aiohttp feedparser beautifulsoup4 lxml pyyaml python-dateutil snscrape

# Or install individually as needed
pip install feedparser  # For RSS sources
pip install snscrape    # For Twitter
```

## 📊 Expected Results

With default configuration:
- **Sources**: 2-5 active connectors
- **Articles**: 20-100 per run  
- **Runtime**: 30-60 seconds
- **Output**: JSON file with normalized article data
- **Memory**: <100MB

## 🚀 Next Steps

1. **Verify Setup**: Run `python -m sentiment_bot.cli_unified list-connectors`
2. **Test Basic**: Run `python -m sentiment_bot.cli_unified connectors --limit 5` 
3. **Customize**: Edit `config/sources.yaml` for your needs
4. **Scale Up**: Increase `--limit` and add more sources
5. **Analyze**: Add `--analyze` flag for sentiment analysis

## 📚 Full Documentation

- **Complete Guide**: [CONNECTOR_GUIDE.md](CONNECTOR_GUIDE.md)
- **Technical Details**: [docs/CONNECTORS.md](docs/CONNECTORS.md)
- **Configuration Reference**: [config/sources.example.yaml](config/sources.example.yaml)

---

✅ **Ready to start collecting data from 11 modern sources!**