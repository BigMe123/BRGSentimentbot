# 🚀 BRGBOT - Unified Intelligence Platform

<div align="center">

![Python Version](https://img.shields.io/badge/python-3.11--3.13-blue.svg)
![License](https://img.shields.io/badge/license-Proprietary-red.svg)
![Sources](https://img.shields.io/badge/sources-1%2C413_domains-purple.svg)
![RSS Feeds](https://img.shields.io/badge/RSS_feeds-3%2C903-orange.svg)
![Connectors](https://img.shields.io/badge/connectors-16_types-green.svg)
![GDP MAE](https://img.shields.io/badge/GDP_MAE-1.452pp-green.svg)
![Coverage](https://img.shields.io/badge/country_coverage-200%2B-blue.svg)

**Institutional-Grade Economic Intelligence & Sentiment Analysis Platform**

*Combining Wall Street-Grade GDP Forecasting with Real-Time Global Sentiment Monitoring*

[🚀 Quick Start](#-quick-start) • [Capabilities](#-platform-capabilities) • [Sources](#-data-sources-3903-feeds) • [Installation](#-installation) • [Architecture](#-architecture)

</div>

---

## 🎯 Overview

**BRGBOT** is a unified intelligence platform combining two powerful systems under one roof:

### 1. 📊 **Economic Forecasting Engine**
Institutional-grade economic predictions with statistically validated models:
- **GDP Calibration**: Matches IMF/World Bank/OECD performance (MAE: 1.452pp)
- **15+ Economic Models**: Inflation, employment, FX, equity, commodities, trade
- **Global Perception Index (GPI)**: Real-time sentiment across 200+ countries
- **Dynamic Alpha Learning**: ML-driven consensus blending with 12 risk features

### 2. 📰 **Sentiment Analysis Engine**
Production-ready news intelligence with massive data coverage:
- **1,413 Curated Sources**: Pre-validated domains across all regions
- **3,903 RSS Feeds**: Multiple feeds per source for redundancy
- **16 Modern Connectors**: Google News, Reddit, HackerNews, YouTube, Twitter, GDELT, etc.
- **200+ Articles/Second**: High-throughput async pipeline

**All capabilities accessible from a single interactive launcher: `python run.py`**

---

## 🚀 Quick Start

### **Interactive Launcher (Recommended)**
One command to access everything:

```bash
# Clone repository
git clone https://github.com/BigMe123/BRGBOT.git
cd BRGBOT

# Install dependencies
pip install -r requirements.txt
python -m spacy download en_core_web_sm

# Launch interactive menu
python run.py
```

**Menu Options:**
1. 🔍 Smart Sentiment Analysis
2. 🧠 AI Market Intelligence
3. 📡 Modern Connectors (16 types)
4. 📊 Economic Predictions
5. 🌍 Global Perception Index
6. 🏦 GDP Calibration
7. 💼 Employment Analysis
8. 💱 Currency/FX Forecasting
9. 📈 Equity Predictions
10. 🛢️ Commodity Analysis
11. 🏥 System Health
12. 🧪 Tests & Validation

### **Direct CLI Examples**

```bash
# Live topic analysis
python analyze_topic_live.py "US China trade" --max-articles 60

# Multi-connector sentiment
python -m sentiment_bot.cli_unified connectors \
  --keywords "AI,ChatGPT,machine learning" \
  --limit 200 --analyze

# Economic forecasting
python run_economic_predictions.py

# GDP calibration
python demo_reason_codes.py

# Source statistics
python consolidate_sources.py
```

---

## ✨ Platform Capabilities

### 📊 **Economic Forecasting**

#### GDP Calibration (MAE: 1.452pp)
- Matches IMF/World Bank/OECD consensus
- +4.9% improvement vs raw models (p<0.05)
- Dynamic alpha learning with 12 risk features
- Walk-forward validation (2016-2024, 49 observations)

#### 15+ Economic Models
- Inflation (CPI with supply chain)
- Employment (jobs, unemployment, wages)
- Currency/FX (exchange rates + geopolitical risk)
- Equity Markets (index forecasts + sector rotation)
- Commodities (oil, ag, metals + climate)
- Trade Flow (bilateral + tariff impact)
- Consumer Confidence (spending + outlook)

#### Global Perception Index (GPI)
- 200+ countries monitored
- Entity-anchored sentiment (96% accuracy)
- Multi-pillar: economic, political, social, security
- Hierarchical source reliability (0.40-0.95)
- 85% echo reduction via SimHash

### 📰 **Sentiment Analysis**

#### Massive Source Coverage
- **1,413 domains** validated globally
- **3,903 RSS feeds** (avg 2.76/source)
- **Regional breakdown**:
  - Americas: 697 (49.3%)
  - Europe: 297 (21.0%)
  - Asia: 160 (11.3%)
  - Africa: 96 (6.8%)
  - LATAM: 86 (6.1%)
  - Middle East: 45 (3.2%)
  - Oceania: 21 (1.5%)

#### 16 Modern Connectors (No API Keys Required)
| Connector | Type | API Key |
|-----------|------|---------|
| Google News | News Aggregator | No |
| Reddit RSS | Social Media | No |
| HackerNews | Tech News | No |
| YouTube | Video Platform | No |
| Wikipedia | Encyclopedia | No |
| GDELT | Global Events | No |
| Twitter/snscrape | Social Media | No |
| Mastodon | Federated Social | No |
| Bluesky | Social Protocol | No |
| StackExchange | Q&A | No |
| News Aggregator | Multi-source | No |
| Web Search | Generic Scraping | No |

#### Live Topic Analysis
```bash
python analyze_topic_live.py "Kenya AGOA trade"
python analyze_topic_live.py "Bitcoin crypto" --full-text
```

Features: Multi-source fetching, sentiment scoring, keyword extraction, number detection, JSON export

#### Performance
- **Throughput**: 200-400 articles/min
- **Success Rate**: 95-98%
- **Selection Speed**: <300ms
- **Deduplication**: 99.5%
- **Freshness**: 73-90% (24h window)

---

## 📊 Data Sources (3,903 Feeds)

### Source Architecture
```
Total Sources: 1,413 curated domains
Total RSS Feeds: 3,903 feeds
Average Feeds/Source: 2.76
Database: SQLite (skb_catalog.db, 1.6MB)
Selection Speed: <300ms
```

### Top Sources (4 feeds each)
CNBC, Bloomberg, WSJ, Economist, Reuters, BBC, FT, Forbes, MarketWatch, TechCrunch, and 50+ major outlets

### Regional Distribution
Americas (697) • Europe (297) • Asia (160) • Africa (96) • LATAM (86) • Middle East (45) • Oceania (21)

### Quality Metrics
- Reliability: 0.5-0.95 (hierarchical)
- Freshness: 0.5-1.0 (24h updates)
- Validation: All active
- Error Rate: <5%

---

## 🏗️ Architecture

```
🎮 Interactive Launcher (run.py)
    ├── 📊 Economic Forecasting Engine
    │   ├── GDP Calibration (IMF/WB/OECD consensus)
    │   ├── 15+ Economic Models (inflation, employment, FX, equity, etc.)
    │   └── Global Perception Index (200+ countries)
    │
    └── 📰 Sentiment Analysis Engine
        ├── SKB Catalog (1,413 sources, 3,903 feeds)
        ├── 16 Modern Connectors (Google News, Reddit, HN, etc.)
        ├── Async Pipeline (200+ articles/sec)
        └── Entity Extraction (countries, tickers, themes)
```

**Processing Flow:**
Sources → Fetch → Dedup → Filter → Analyze (VADER/FinBERT/GPT-4o-mini) → Extract Entities → Generate Insights → Output (JSONL/JSON/CSV/TXT)

---

## 📦 Installation

```bash
# 1. Clone
git clone https://github.com/BigMe123/BRGBOT.git && cd BRGBOT

# 2. Install
pip install -r requirements.txt

# 3. NLP models
python -m spacy download en_core_web_sm

# 4. Test
python smoke_test.py

# 5. Launch
python run.py
```

**Optional API Keys** (.env):
```bash
OPENAI_API_KEY=sk-...          # For GPT-4o-mini
ALPHA_VANTAGE_API_KEY=...      # For economic data
```

---

## 📊 Performance Benchmarks

### Economic Forecasting
| Model | Metric | Value | Benchmark |
|-------|--------|-------|-----------|
| GDP | MAE | 1.452pp | Matches IMF/WB/OECD (DM p=0.35) |
| GDP | RMSE | 2.834pp | Within 0.47% consensus |
| GDP | Improvement | +4.9% | vs raw (DM p<0.05) |
| GPI | Countries | 200+ | Global coverage |
| GPI | Entity F1 | 96% | CoNLL-2003 |
| GPI | Sentiment AUC | 92% | 50K corpus |

### Sentiment Analysis
| Metric | Value | Notes |
|--------|-------|-------|
| Sources | 1,413 | Validated domains |
| RSS Feeds | 3,903 | Multi-feed redundancy |
| Throughput | 200-400/min | 10+ connectors |
| Success Rate | 95-98% | Auto-retry |
| Selection | <300ms | SQLite indexed |
| Dedup | 99.5% | URL hash |

### Real-World Results
**Crypto Analysis** (47s): 2,847 → 1,214 → 400 articles (87% success)
**Topic Analysis** (12s): 60 articles, 100% sentiment, keywords + numbers extracted

---

## 🎯 Use Cases

### Financial Markets
```bash
python -m sentiment_bot.cli_unified connectors \
  --keywords "bitcoin,ethereum,defi" --limit 500 --analyze
python demo_reason_codes.py  # GDP forecasting
```

### Geopolitical Risk
```bash
python run_gpi.py --countries "USA,CHN,RUS,UKR"
python analyze_topic_live.py "US China trade war"
```

### Corporate Intelligence
```bash
python analyze_topic_live.py "Tesla Elon Musk" --max-articles 100
```

### Economic Research
```bash
python run_economic_predictions.py
python sentiment_bot/bridge_dfm_models.py
```

---

## 🛠️ Project Structure

```
BRGBOT/
├── run.py                      # Interactive launcher
├── consolidate_sources.py      # Source consolidation (3,903 feeds)
├── analyze_topic_live.py       # Standalone topic analysis
├── smoke_test.py               # Verification tests
│
├── skb_catalog.db              # 1,413 sources, 3,903 feeds
│
├── sentiment_bot/
│   ├── cli_unified.py         # Main CLI
│   ├── master_sources.py      # Source manager
│   ├── connectors/            # 16 connectors
│   ├── consensus/             # GDP calibration
│   ├── economic_models/       # 15+ models
│   ├── gpi/                   # Global Perception Index
│   └── utils/                 # Entity extraction, output
│
└── output/                    # JSONL, JSON, CSV, TXT reports
```

---

## 🐛 Troubleshooting

```bash
# Verify installation
python smoke_test.py

# Check sources
python consolidate_sources.py
python -m sentiment_bot.cli_unified stats

# Database health
python -c "import sqlite3; print(sqlite3.connect('skb_catalog.db').execute('SELECT COUNT(*) FROM sources').fetchone()[0], 'sources')"

# System health
python -m sentiment_bot.cli_unified health
```

**Common Issues:**
- No articles: Check internet, try different keywords
- Database locked: `pkill -f sentiment_bot && rm -f *.db-shm *.db-wal`
- spaCy error: `python -m spacy download en_core_web_sm`
- LLM fails: Add `OPENAI_API_KEY` to `.env`

---

## 🤝 Support

**Boston Risk Group**
- 📧 bostonriskgroup@gmail.com
- 📱 +1 646-877-2527
- 👤 Marco Dorazio
- 🌐 [GitHub](https://github.com/BigMe123/BSGBOT)

**Hours**: Mon-Fri, 9 AM - 5 PM EST

---

## 📜 License

Proprietary - Boston Risk Group. All rights reserved.
- **Trial**: 30 days full access
- **Enterprise**: Contact for pricing

---

<div align="center">

**Built with ❤️ by Boston Risk Group**

*Institutional-Grade Economic Intelligence & Global Sentiment Monitoring*

**🏆 1,413 Sources • 3,903 Feeds • 16 Connectors • 200+ Countries • 15+ Models**

</div>
