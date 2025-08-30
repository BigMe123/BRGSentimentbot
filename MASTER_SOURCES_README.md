# 🌍 Master Source System Documentation

## Overview

The BSG Sentiment Bot now uses a **unified master source system** that provides a single source of truth for all news sources. This ensures consistency across all runs and components of the system.

## 📊 Current Statistics

- **Total Sources**: 768
- **Countries**: 104
- **Regions**: 7 (Americas, Europe, Asia, Middle East, Africa, Oceania, Latin America)
- **High Priority Sources**: 68 (priority ≥ 0.7)
- **Languages**: Multiple (primarily English, but includes sources in 20+ languages)

## 🚀 Quick Start

### Run with all sources:
```bash
./bsgbot_master.sh run
```

### Run with high-priority sources only:
```bash
./bsgbot_master.sh high-priority
```

### Run by region:
```bash
./bsgbot_master.sh by-region europe
./bsgbot_master.sh by-region asia
```

### Run by topic:
```bash
./bsgbot_master.sh by-topic economy
./bsgbot_master.sh by-topic tech
```

## 📁 File Structure

```
BSGBOT/
├── skb_catalog.db                    # SQLite database (single source of truth)
├── sentiment_bot/
│   └── master_sources.py             # Master source manager module
├── config/
│   ├── master_config.yaml           # Master configuration
│   ├── master_sources.yaml          # Exported source list (auto-generated)
│   └── global_news_seeds.txt        # Seed file with 660+ sources
├── bsgbot_master.sh                 # Master runner script
└── run_with_master_sources.py       # Python runner with filtering
```

## 🎯 Key Components

### 1. **Master Source Manager** (`sentiment_bot/master_sources.py`)
- Centralized source management
- Single interface to all news sources
- Automatic connector type detection
- Source filtering and prioritization
- Statistics and reporting

### 2. **SKB Catalog Database** (`skb_catalog.db`)
- SQLite database with 768 sources
- Indexed for fast queries
- Tracks metadata, priorities, and statistics
- Persistent storage

### 3. **Master Runner Script** (`bsgbot_master.sh`)
- Bash wrapper for easy usage
- Multiple command options
- Automatic filtering
- Color-coded output

## 🔧 Configuration

The system uses `config/master_config.yaml` for configuration:

```yaml
sources:
  use_master_list: true
  filters:
    regions: []        # Leave empty for all
    topics: []         # Leave empty for all
    min_priority: 0.0  # Use all sources
    max_sources: null  # No limit
```

## 📋 Available Commands

| Command | Description |
|---------|-------------|
| `run` | Run sentiment analysis with all sources |
| `stats` | Show detailed source statistics |
| `list` | List sources with optional filters |
| `export` | Export master sources to YAML |
| `harvest` | Run stealth harvester for RSS discovery |
| `update` | Update catalog from seed files |
| `high-priority` | Run on high-priority sources only |
| `by-region <region>` | Run on specific region |
| `by-topic <topic>` | Run on specific topic |

## 🎨 Source Categories

### By Region:
- **Americas**: 268 sources (US, Canada, etc.)
- **Europe**: 218 sources (UK, France, Germany, etc.)
- **Asia**: 94 sources (China, Japan, India, etc.)
- **Middle East**: 55 sources
- **Latin America**: 55 sources
- **Africa**: 54 sources
- **Oceania**: 24 sources (Australia, New Zealand)

### By Priority:
- **High (≥0.7)**: 68 sources (major outlets like Reuters, BBC, Bloomberg)
- **Medium (0.4-0.7)**: 700 sources (regional and specialized outlets)
- **Low (<0.4)**: 0 sources (all sources have at least medium priority)

### By Type:
- **News**: General news outlets
- **Business**: Financial and economic sources
- **Tech**: Technology news
- **Science**: Academic and research sources
- **Alternative**: Independent media
- **Government**: Official sources

## 🔍 Filtering Options

### Filter by Region:
```bash
python run_with_master_sources.py --regions americas europe
```

### Filter by Topic:
```bash
python run_with_master_sources.py --topics economy politics
```

### Filter by Priority:
```bash
python run_with_master_sources.py --min-priority 0.7
```

### Limit Number of Sources:
```bash
python run_with_master_sources.py --max-sources 100
```

## 📊 Python API Usage

```python
from sentiment_bot.master_sources import get_master_sources

# Get the master source manager
manager = get_master_sources()

# Get all sources
all_sources = manager.get_all_sources()

# Get high-priority sources
high_priority = manager.get_high_priority_sources(min_priority=0.7)

# Get sources by region
europe_sources = manager.get_sources_by_region('europe')

# Get sources by topic
economy_sources = manager.get_sources_by_topic('economy')

# Get sources for bot with filters
bot_sources = manager.get_sources_for_bot(
    regions=['americas', 'europe'],
    topics=['economy', 'politics'],
    min_priority=0.5,
    max_sources=100
)

# Get statistics
stats = manager.get_statistics()
print(f"Total sources: {stats['total_sources']}")
```

## 🔄 Updating Sources

### Add new sources from seed file:
```bash
python add_sources_to_skb.py
```

### Discover RSS feeds:
```bash
python harvest_global_news.py
```

### Run enhanced stealth harvester:
```bash
python -m sentiment_bot.stealth_harvester_enhanced --seeds config/global_news_seeds.txt
```

## 📈 Integration with Sentiment Bot

The master source system is automatically used by the sentiment bot when you run:

```bash
bsgbot run --config config/master_config.yaml
```

Or use the master runner:

```bash
./bsgbot_master.sh run
```

## 🎯 Best Practices

1. **Always use the master source system** - Don't create separate source lists
2. **Filter appropriately** - Use regions/topics/priority to focus analysis
3. **Update regularly** - Run the harvester periodically to discover new RSS feeds
4. **Monitor statistics** - Check source health and performance regularly
5. **Export for backup** - Periodically export the master list to YAML

## 🚨 Troubleshooting

### Database not found:
```bash
python -m sentiment_bot.master_sources  # Creates default database
```

### Sources not loading:
```bash
./bsgbot_master.sh update  # Reload from seeds
```

### Check source statistics:
```bash
./bsgbot_master.sh stats
```

## 📝 Notes

- The system supports 768 news sources from 104 countries
- Sources are automatically categorized by region, topic, and priority
- The SQLite database ensures fast queries and persistent storage
- The master source manager provides a consistent API for all components
- RSS feed discovery is handled by the stealth harvester

## 🔮 Future Enhancements

- [ ] Automatic RSS feed discovery scheduling
- [ ] Source health monitoring and auto-disable
- [ ] Machine learning-based source ranking
- [ ] Real-time source addition via web interface
- [ ] Distributed harvesting across multiple machines
- [ ] Source performance analytics dashboard

---

**Remember**: The master source system is now the ONLY way sources should be accessed in the BSG Sentiment Bot. All components should use the `master_sources.py` module for source management.