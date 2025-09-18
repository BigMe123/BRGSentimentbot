# 🌍 Global Perception Index (GPI) - User Guide

## Overview

The **Global Perception Index (GPI)** is a sophisticated system that measures how countries perceive each other on a **1-100 scale** based on real-time analysis of:

- 📰 **News sentiment** from country-specific media sources
- 💰 **Economic indicators** and trade relationships
- 🤝 **Diplomatic signals** and international cooperation

## ✨ Key Features

### 🎯 Core Capabilities
- **Real-time perception measurement** between any two countries
- **Global rankings** showing which countries are most positively perceived
- **Perception matrix** displaying relationships between multiple countries
- **Trend analysis** tracking perception changes over time
- **Comprehensive reports** with detailed breakdowns

### 🗄️ Data Sources
- **News Sentiment**: Analysis of country-specific media coverage
- **Economic Relations**: Trade flows, investment patterns, cooperation levels
- **Diplomatic Signals**: UN voting alignment, official statements, embassy activity

### 🎨 User Interfaces
- **Interactive CLI** through `run.py`
- **Direct CLI commands** via `sentiment_bot.cli_unified`
- **Python API** for programmatic access

## 🚀 Getting Started

### Option 1: Interactive Menu (Recommended)

```bash
python run.py
```

Then select **Option 18: 🌍 Global Perception Index**

This gives you a user-friendly menu with these options:
1. **🔍 Measure Perception** - How does one country perceive another?
2. **🏆 Global Rankings** - See which countries are most positively perceived
3. **📊 Perception Matrix** - View relationships between multiple countries
4. **📈 Trends Analysis** - See how perception has changed over time
5. **📋 Comprehensive Report** - Generate detailed perception reports

### Option 2: Direct CLI Commands

```bash
# Measure specific country perception
python -m sentiment_bot.cli_unified perception-measure USA CHN

# View global rankings
python -m sentiment_bot.cli_unified perception-rank

# Show trends for a country
python -m sentiment_bot.cli_unified perception-trends USA --days 30

# Generate comprehensive reports
python -m sentiment_bot.cli_unified perception-report USA

# View perception matrix
python -m sentiment_bot.cli_unified perception-matrix --countries USA,CHN,GBR,DEU
```

### Option 3: Python API

```python
from sentiment_bot.global_perception_index import GlobalPerceptionIndex

# Initialize the system
gpi = GlobalPerceptionIndex()

# Measure perception between countries
reading = gpi.measure_perception("USA", "CHN")
print(f"USA perceives CHN: {reading.perception_score:.1f}/100")
print(f"Confidence: {reading.confidence:.2f}")

# Get global rankings
rankings = gpi.calculate_global_rankings()
for country, (score, rank) in rankings.items():
    print(f"{rank}. {country}: {score:.1f}/100")

# Generate perception matrix
countries = ["USA", "CHN", "GBR", "DEU"]
matrix = gpi.get_perception_matrix(countries)

# Analyze trends
trends = gpi.get_perception_trends("USA", days=30)
print(f"Trend: {trends['trend']}")
```

## 📊 Understanding the Results

### Perception Scores (1-100)
- **80-100**: Very Positive perception
- **60-79**: Positive perception
- **40-59**: Neutral perception
- **20-39**: Negative perception
- **1-19**: Very Negative perception

### Confidence Levels (0-1)
- **0.8-1.0**: High confidence (lots of data)
- **0.6-0.79**: Medium confidence
- **0.4-0.59**: Low confidence
- **0-0.39**: Very low confidence (limited data)

### Component Breakdown
Each perception measurement includes:
- **News Sentiment**: Media coverage analysis
- **Economic Relations**: Trade and investment factors
- **Diplomatic Relations**: Official relationship indicators

## 🌍 Sample Use Cases

### 1. Bilateral Relationship Analysis
```bash
# How does the US perceive China?
python -m sentiment_bot.cli_unified perception-measure USA CHN

# How does China perceive the US?
python -m sentiment_bot.cli_unified perception-measure CHN USA
```

### 2. Global Soft Power Rankings
```bash
# See which countries are most positively perceived globally
python -m sentiment_bot.cli_unified perception-rank
```

### 3. Regional Dynamics
```bash
# European relationship matrix
python -m sentiment_bot.cli_unified perception-matrix --countries GBR,DEU,FRA,ITA,ESP

# Asian relationship matrix
python -m sentiment_bot.cli_unified perception-matrix --countries CHN,JPN,KOR,IND,IDN
```

### 4. Trend Monitoring
```bash
# Track how China's global perception has changed
python -m sentiment_bot.cli_unified perception-trends CHN --days 90

# Monitor US perception trends
python -m sentiment_bot.cli_unified perception-trends USA --days 30
```

### 5. Country Deep Dive
```bash
# Comprehensive report on how the world perceives Germany
python -m sentiment_bot.cli_unified perception-report DEU

# Global overview report
python -m sentiment_bot.cli_unified perception-report
```

## 📈 Output Examples

### Perception Measurement
```
Measuring Perception: USA → CHN
┏━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Metric                 ┃ Value    ┃ Details                                 ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ Perception Score       │ 44.7/100 │ Overall perception rating               │
│ Confidence             │ 0.43     │ Reliability of measurement              │
│ Data Sources           │ 2        │ economic_indicators, diplomatic_signals │
│   News Sentiment       │ 50.0     │ Component score                         │
│   Economic Relations   │ 50.1     │ Component score                         │
│   Diplomatic Relations │ 28.6     │ Component score                         │
└────────────────────────┴──────────┴─────────────────────────────────────────┘
```

### Global Rankings
```
Global Perception Rankings
┏━━━━━━┳━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ Rank ┃ Country ┃ Score    ┃ Perception Level ┃
┡━━━━━━╇━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ 1    │ CHE     │ 71.2/100 │ Positive         │
│ 2    │ AUS     │ 68.9/100 │ Positive         │
│ 3    │ CAN     │ 65.4/100 │ Positive         │
│ 4    │ NLD     │ 63.1/100 │ Positive         │
│ 5    │ DEU     │ 61.8/100 │ Positive         │
└──────┴─────────┴──────────┴──────────────────┘
```

## 🔧 Technical Details

### Data Storage
- **SQLite database**: `state/global_perception_index.sqlite`
- **Persistent storage** of all perception readings
- **Historical tracking** for trend analysis

### Performance
- **Real-time analysis**: Results in seconds
- **Batch processing**: Multiple countries efficiently
- **Caching**: Intelligent caching for frequently requested data

### Accuracy
- **Multi-source validation**: Cross-references multiple data types
- **Confidence scoring**: Indicates reliability of each measurement
- **Error handling**: Graceful fallbacks for missing data

## 🎯 Integration Points

The Global Perception Index integrates seamlessly with:

- **✅ BSG Sentiment Analysis**: Uses existing sentiment infrastructure
- **✅ Source Management**: Leverages country-specific news sources
- **✅ CLI Framework**: Full integration with existing command structure
- **✅ Test Framework**: Comprehensive unit, integration, and E2E tests

## 🔄 Future Enhancements

The GPI system is designed for extensibility:

- **📡 Real-time feeds**: Integration with live news streams
- **🤖 ML improvements**: Enhanced prediction algorithms
- **🌐 More data sources**: Social media, polling data, economic indicators
- **📊 Visualization**: Web dashboard and charts
- **🔔 Alerting**: Notifications for significant perception changes

## 📞 Support

For questions, issues, or feature requests:

1. **Check the test suite**: `python -m pytest tests/unit/test_global_perception_index.py -v`
2. **Run system health check**: `python -m pytest tests/e2e/test_smoke_tests.py::test_system_health_check -v`
3. **View CLI help**: `python -m sentiment_bot.cli_unified --help`

---

**The Global Perception Index provides unprecedented insights into international relations through real-time sentiment analysis and data integration. Start exploring global perceptions today!** 🌍✨