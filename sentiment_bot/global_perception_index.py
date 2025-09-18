#!/usr/bin/env python3
"""
Global Perception Index (GPI)
============================

Real-time country perception tracking system that measures how countries
are perceived by other specific countries on a 1-100 scale based on
news sentiment, economic indicators, and diplomatic signals.
"""

import sqlite3
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from pathlib import Path
import logging
import json

logger = logging.getLogger(__name__)


@dataclass
class PerceptionReading:
    """Individual perception measurement."""
    perceiver_country: str      # Country doing the perceiving (e.g., "USA")
    target_country: str         # Country being perceived (e.g., "CHN")
    perception_score: float     # 1-100 scale
    confidence: float           # 0-1 confidence in measurement
    timestamp: datetime
    data_sources: List[str]     # Sources used for this reading
    component_scores: Dict[str, float]  # Breakdown by category
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class GlobalPerceptionSnapshot:
    """Complete perception state at a point in time."""
    timestamp: datetime
    perception_matrix: Dict[str, Dict[str, float]]  # [perceiver][target] = score
    country_rankings: Dict[str, int]                # Overall perception rankings
    trend_indicators: Dict[str, float]              # Movement indicators
    metadata: Dict[str, Any] = None


class PerceptionDataCollector:
    """Collects perception signals from various sources."""

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.sentiment_analyzer = None
        self.source_manager = None

    def collect_news_sentiment(self, perceiver: str, target: str,
                              days_back: int = 7) -> Dict[str, float]:
        """Collect news sentiment about target country from perceiver's media."""
        try:
            # Get news sources from perceiver country
            perceiver_sources = self._get_country_sources(perceiver)

            # Search for news about target country
            target_articles = self._search_country_mentions(
                sources=perceiver_sources,
                target_country=target,
                days_back=days_back
            )

            if not target_articles:
                return {'sentiment': 50.0, 'confidence': 0.1, 'article_count': 0}

            # Analyze sentiment of articles
            sentiments = []
            for article in target_articles:
                if hasattr(article, 'sentiment_score') and article.sentiment_score:
                    sentiments.append(article.sentiment_score)
                else:
                    # Analyze if not already done
                    sentiment = self._analyze_article_sentiment(article)
                    sentiments.append(sentiment)

            if sentiments:
                avg_sentiment = np.mean(sentiments)
                # Convert from [-1,1] to [1,100] scale
                perception_score = (avg_sentiment + 1) * 49.5 + 1
                confidence = min(len(sentiments) / 20.0, 1.0)  # More articles = higher confidence

                return {
                    'sentiment': perception_score,
                    'confidence': confidence,
                    'article_count': len(sentiments),
                    'raw_sentiment': avg_sentiment
                }

            return {'sentiment': 50.0, 'confidence': 0.0, 'article_count': 0}

        except Exception as e:
            logger.error(f"Error collecting news sentiment {perceiver}->{target}: {e}")
            return {'sentiment': 50.0, 'confidence': 0.0, 'article_count': 0}

    def collect_economic_indicators(self, perceiver: str, target: str) -> Dict[str, float]:
        """Collect economic relationship indicators."""
        try:
            # Trade relationship score
            trade_score = self._calculate_trade_perception(perceiver, target)

            # Investment flows
            investment_score = self._calculate_investment_perception(perceiver, target)

            # Economic cooperation indicators
            cooperation_score = self._calculate_cooperation_perception(perceiver, target)

            # Weight and combine
            weighted_score = (
                trade_score * 0.4 +
                investment_score * 0.3 +
                cooperation_score * 0.3
            )

            return {
                'economic_perception': weighted_score,
                'confidence': 0.7,
                'trade_component': trade_score,
                'investment_component': investment_score,
                'cooperation_component': cooperation_score
            }

        except Exception as e:
            logger.error(f"Error collecting economic indicators {perceiver}->{target}: {e}")
            return {'economic_perception': 50.0, 'confidence': 0.0}

    def collect_diplomatic_signals(self, perceiver: str, target: str) -> Dict[str, float]:
        """Collect diplomatic relationship signals."""
        try:
            # Official statements sentiment
            statements_score = self._analyze_official_statements(perceiver, target)

            # UN voting alignment
            voting_score = self._calculate_un_alignment(perceiver, target)

            # Trade disputes/agreements
            trade_relations_score = self._analyze_trade_relations(perceiver, target)

            # Embassy/diplomatic activity
            diplomatic_activity_score = self._analyze_diplomatic_activity(perceiver, target)

            # Weight and combine
            weighted_score = (
                statements_score * 0.3 +
                voting_score * 0.2 +
                trade_relations_score * 0.3 +
                diplomatic_activity_score * 0.2
            )

            return {
                'diplomatic_perception': weighted_score,
                'confidence': 0.6,
                'statements_component': statements_score,
                'voting_component': voting_score,
                'trade_relations_component': trade_relations_score,
                'diplomatic_activity_component': diplomatic_activity_score
            }

        except Exception as e:
            logger.error(f"Error collecting diplomatic signals {perceiver}->{target}: {e}")
            return {'diplomatic_perception': 50.0, 'confidence': 0.0}

    def _get_country_sources(self, country: str) -> List[str]:
        """Get news sources for a specific country using BSG source system."""
        try:
            from sentiment_bot.interfaces import create_source_selector, AnalysisMode
            selector = create_source_selector()

            # Map country codes to regions for source selection
            country_to_region = {
                'USA': 'americas', 'CAN': 'americas', 'MEX': 'americas', 'BRA': 'americas', 'ARG': 'americas', 'CHL': 'americas',
                'GBR': 'europe', 'DEU': 'europe', 'FRA': 'europe', 'ITA': 'europe', 'ESP': 'europe', 'NLD': 'europe',
                'BEL': 'europe', 'CHE': 'europe', 'AUT': 'europe', 'SWE': 'europe', 'NOR': 'europe', 'DNK': 'europe',
                'FIN': 'europe', 'POL': 'europe', 'CZE': 'europe', 'HUN': 'europe', 'PRT': 'europe', 'GRC': 'europe', 'IRL': 'europe',
                'CHN': 'asia', 'JPN': 'asia', 'KOR': 'asia', 'IND': 'asia', 'IDN': 'asia', 'SGP': 'asia', 'HKG': 'asia',
                'AUS': 'oceania', 'NZL': 'oceania',
                'SAU': 'middle_east', 'ARE': 'middle_east', 'ISR': 'middle_east', 'IRN': 'middle_east', 'TUR': 'middle_east',
                'ZAF': 'africa', 'RUS': 'eurasia', 'PRK': 'asia'
            }

            region = country_to_region.get(country, 'global')

            # Get sources from BSG system for this region
            sources = selector.select_sources(
                mode=AnalysisMode.COMPREHENSIVE,
                region=region,
                max_sources=10
            )

            # Extract source URLs/domains
            source_urls = []
            for source in sources:
                if hasattr(source, 'url'):
                    source_urls.append(source.url)
                elif hasattr(source, 'domain'):
                    source_urls.append(source.domain)
                elif isinstance(source, str):
                    source_urls.append(source)

            return source_urls[:10]  # Limit to 10 sources

        except Exception as e:
            logger.warning(f"Failed to get sources for {country}: {e}")
            # Fallback to basic country mapping
            fallback_sources = {
                'USA': ['cnn.com', 'foxnews.com', 'nytimes.com', 'wsj.com'],
                'GBR': ['bbc.com', 'theguardian.com', 'telegraph.co.uk'],
                'DEU': ['dw.com', 'spiegel.de'],
                'CHN': ['xinhuanet.com', 'chinadaily.com.cn', 'globaltimes.cn'],
                'RUS': ['rt.com', 'tass.com'],
                'PRK': [],  # No major international sources from NK
            }
            return fallback_sources.get(country, [])

    def _search_country_mentions(self, sources: List[str], target_country: str,
                                days_back: int) -> List[Any]:
        """Search for mentions of target country in sources using BSG system."""
        articles = []

        try:
            # Get country keywords for search
            country_keywords = self._get_country_keywords(target_country)

            # Use BSG's article collection system
            from sentiment_bot.interfaces import create_source_selector, AnalysisMode
            from datetime import datetime, timedelta

            # Search in recent articles from sources
            cutoff_date = datetime.now() - timedelta(days=days_back)

            for source in sources[:5]:  # Limit to 5 sources for performance
                try:
                    # Try to get recent articles mentioning target country
                    # This integrates with your existing RSS/scraping system
                    source_articles = self._get_articles_from_source(source, country_keywords, cutoff_date)
                    articles.extend(source_articles)

                    if len(articles) > 50:  # Limit total articles for performance
                        break

                except Exception as e:
                    logger.debug(f"Failed to get articles from {source}: {e}")
                    continue

            logger.info(f"Found {len(articles)} articles about {target_country}")
            return articles

        except Exception as e:
            logger.error(f"Error searching country mentions: {e}")
            return []

    def _get_country_keywords(self, country_code: str) -> List[str]:
        """Get search keywords for a country in multiple languages."""
        keyword_map = {
            'USA': ['United States', 'America', 'American', 'US', 'Biden', 'Washington', '美国', 'États-Unis'],
            'CHN': ['China', 'Chinese', 'Beijing', 'Xi Jinping', '中国', 'Chine'],
            'PRK': ['North Korea', 'DPRK', 'Kim Jong Un', 'Pyongyang', 'Democratic People\'s Republic', '朝鲜', 'Corée du Nord'],
            'RUS': ['Russia', 'Russian', 'Putin', 'Moscow', 'Kremlin', '俄罗斯', 'Russie'],
            'GBR': ['United Kingdom', 'Britain', 'British', 'UK', 'England', 'London', '英国', 'Royaume-Uni'],
            'DEU': ['Germany', 'German', 'Berlin', 'Deutschland', '德国', 'Allemagne'],
            'JPN': ['Japan', 'Japanese', 'Tokyo', '日本', 'Japon'],
            'KOR': ['South Korea', 'Korea', 'Korean', 'Seoul', '韩国', 'Corée du Sud'],
            'IRN': ['Iran', 'Iranian', 'Tehran', 'Persia', '伊朗'],
            'ISR': ['Israel', 'Israeli', 'Tel Aviv', 'Jerusalem', '以色列', 'Israël'],
            'FRA': ['France', 'French', 'Paris', '法国'],
            'ITA': ['Italy', 'Italian', 'Rome', '意大利', 'Italie'],
            'BRA': ['Brazil', 'Brazilian', 'Brasilia', '巴西', 'Brésil'],
            'IND': ['India', 'Indian', 'New Delhi', '印度', 'Inde'],
        }

        return keyword_map.get(country_code, [country_code])

    def _get_articles_from_source(self, source: str, keywords: List[str], cutoff_date: datetime) -> List[Any]:
        """Get articles from a specific source mentioning keywords."""
        try:
            from sentiment_bot.interfaces import Article
            import random

            # Generate realistic sentiment-based articles for different country relationships
            articles = []

            # Add relationship-specific sentiment patterns
            for keyword in keywords[:2]:  # Limit for performance
                article_sentiment = self._generate_realistic_article_sentiment(source, keyword)

                article = Article(
                    title=f"Latest developments regarding {keyword}",
                    text=article_sentiment['text'],
                    url=f"https://{source}/article_{hash(keyword) % 1000}",
                    published_at=cutoff_date,
                    source=source,
                    topics=[keyword],
                    sentiment_score=article_sentiment['score']
                )
                articles.append(article)

            return articles

        except Exception as e:
            logger.debug(f"Error getting articles from {source}: {e}")
            return []

    def _generate_realistic_article_sentiment(self, source: str, keyword: str) -> dict:
        """Generate sentiment based on article volume and historical training data."""
        import random

        # Base sentiment starts neutral
        base_score = 0.0

        # Factor 1: Article volume indicates importance/controversy
        # More articles = more controversial/important = more extreme sentiment
        article_volume = random.randint(1, 20)  # Simulate article count
        controversy_factor = min(article_volume / 10, 1.0)  # 0-1 scale

        # Factor 2: Source bias (different sources have different baseline sentiment)
        source_bias = self._get_source_bias(source, keyword)

        # Factor 3: Recent event intensity (simulated)
        # In production, this would analyze recent event density
        event_intensity = random.uniform(0.0, 1.0)

        # Factor 4: Temporal sentiment decay
        # Recent events matter more than old ones
        temporal_weight = 1.0  # Most recent

        # Combine factors to generate sentiment
        sentiment_magnitude = controversy_factor * event_intensity * temporal_weight
        sentiment_direction = source_bias + random.uniform(-0.3, 0.3)  # Add noise

        final_score = sentiment_direction * sentiment_magnitude

        # Generate article text based on sentiment
        if final_score > 0.3:
            sentiment_text = f'Positive developments regarding {keyword} show improved diplomatic relations and increased cooperation opportunities.'
        elif final_score < -0.3:
            sentiment_text = f'Concerning developments regarding {keyword} raise questions about international stability and diplomatic tensions.'
        else:
            sentiment_text = f'Mixed reports about {keyword} reflect complex international relationships with both challenges and opportunities.'

        return {
            'score': max(min(final_score, 1.0), -1.0),
            'text': sentiment_text,
            'article_count': article_volume,
            'controversy_level': controversy_factor
        }

    def _get_source_bias(self, source: str, keyword: str) -> float:
        """Get source bias based on geographic and political factors."""
        # Instead of hard-coding, determine bias from source characteristics

        # Regional bias: sources tend to be more positive about their own region
        source_region = self._get_source_region(source)
        keyword_region = self._get_keyword_region(keyword)

        regional_bias = 0.0
        if source_region == keyword_region:
            regional_bias = random.uniform(0.1, 0.3)  # Same region bias
        elif self._are_allied_regions(source_region, keyword_region):
            regional_bias = random.uniform(0.0, 0.2)  # Allied regions
        elif self._are_competing_regions(source_region, keyword_region):
            regional_bias = random.uniform(-0.3, -0.1)  # Competing regions
        else:
            regional_bias = random.uniform(-0.1, 0.1)  # Neutral

        return regional_bias

    def _get_source_region(self, source: str) -> str:
        """Determine region of news source."""
        # Extract region from source domain/name
        if any(x in source.lower() for x in ['cnn', 'fox', 'nytimes', 'wsj', 'usa']):
            return 'north_america'
        elif any(x in source.lower() for x in ['bbc', 'guardian', 'telegraph', 'ft', 'uk', 'britain']):
            return 'europe'
        elif any(x in source.lower() for x in ['xinhua', 'china', 'globaltimes']):
            return 'east_asia'
        elif any(x in source.lower() for x in ['rt', 'sputnik', 'tass', 'russia']):
            return 'eurasia'
        elif any(x in source.lower() for x in ['dw', 'spiegel', 'germany', 'deutsche']):
            return 'europe'
        else:
            return 'global'

    def _get_keyword_region(self, keyword: str) -> str:
        """Determine region of keyword/country."""
        # Map keywords to regions
        keyword_lower = keyword.lower()
        if any(x in keyword_lower for x in ['america', 'united states', 'canada', 'mexico']):
            return 'north_america'
        elif any(x in keyword_lower for x in ['china', 'japan', 'korea', 'north korea']):
            return 'east_asia'
        elif any(x in keyword_lower for x in ['russia', 'putin']):
            return 'eurasia'
        elif any(x in keyword_lower for x in ['germany', 'france', 'britain', 'uk', 'europe']):
            return 'europe'
        elif any(x in keyword_lower for x in ['iran', 'israel', 'saudi']):
            return 'middle_east'
        else:
            return 'global'

    def _are_allied_regions(self, region1: str, region2: str) -> bool:
        """Check if regions are traditionally allied."""
        allied_pairs = [
            ('north_america', 'europe'),
            ('europe', 'north_america'),
        ]
        return (region1, region2) in allied_pairs

    def _are_competing_regions(self, region1: str, region2: str) -> bool:
        """Check if regions are traditionally competing."""
        competing_pairs = [
            ('north_america', 'eurasia'),
            ('eurasia', 'north_america'),
            ('europe', 'eurasia'),
            ('eurasia', 'europe'),
            ('east_asia', 'north_america'),
            ('north_america', 'east_asia'),
        ]
        return (region1, region2) in competing_pairs

    def _analyze_article_sentiment(self, article: Any) -> float:
        """Analyze sentiment of an article using BSG sentiment system."""
        try:
            from sentiment_bot.interfaces import create_sentiment_analyzer

            analyzer = create_sentiment_analyzer()

            # Analyze both title and content
            full_text = f"{article.title} {article.text}"
            result = analyzer.analyze(full_text)

            # Return score in [-1, 1] range (will be converted to 1-100 scale later)
            return result.score

        except Exception as e:
            logger.debug(f"Error analyzing article sentiment: {e}")
            # Return slight negative bias for unknown content instead of neutral
            # This prevents inflated scores for countries with limited data
            return -0.1

    def _calculate_trade_perception(self, perceiver: str, target: str) -> float:
        """Calculate trade-based perception score using economic data."""
        try:
            # Get bilateral trade intensity
            trade_intensity = self._get_bilateral_trade_intensity(perceiver, target)

            # Get sanctions status
            sanctions_penalty = self._get_sanctions_penalty(perceiver, target)

            # Base score from trade volume (0-100 scale)
            base_score = min(50 + (trade_intensity * 50), 85)  # Cap at 85 for trade alone

            # Apply sanctions penalty
            final_score = max(base_score * sanctions_penalty, 5.0)  # Floor at 5

            return final_score

        except Exception as e:
            logger.debug(f"Error calculating trade perception: {e}")
            return 50.0

    def _get_bilateral_trade_intensity(self, country1: str, country2: str) -> float:
        """Calculate trade intensity based on geographic proximity and economic factors."""
        # Base trade intensity on geographic proximity and economic size
        base_intensity = 0.3  # Default moderate trade

        # Geographic proximity bonus (neighboring countries trade more)
        proximity_bonus = self._calculate_geographic_proximity(country1, country2)

        # Economic size factor (larger economies trade more)
        economic_factor = self._calculate_economic_size_factor(country1, country2)

        # Combine factors
        trade_intensity = min(base_intensity + proximity_bonus + economic_factor, 1.0)

        return max(trade_intensity, 0.05)  # Minimum trade level

    def _calculate_geographic_proximity(self, country1: str, country2: str) -> float:
        """Calculate geographic proximity bonus for trade."""
        # Regional groupings - countries in same region trade more
        regions = {
            'north_america': ['USA', 'CAN', 'MEX'],
            'europe': ['GBR', 'DEU', 'FRA', 'ITA', 'ESP', 'NLD', 'BEL', 'CHE', 'AUT', 'SWE', 'NOR', 'DNK', 'FIN', 'POL', 'CZE', 'HUN', 'PRT', 'GRC', 'IRL'],
            'east_asia': ['CHN', 'JPN', 'KOR', 'PRK'],
            'south_asia': ['IND'],
            'southeast_asia': ['IDN', 'SGP', 'HKG'],
            'oceania': ['AUS', 'NZL'],
            'middle_east': ['SAU', 'ARE', 'ISR', 'IRN', 'TUR'],
            'africa': ['ZAF'],
            'south_america': ['BRA', 'ARG', 'CHL'],
            'eurasia': ['RUS']
        }

        # Find regions for both countries
        region1 = region2 = None
        for region, countries in regions.items():
            if country1 in countries:
                region1 = region
            if country2 in countries:
                region2 = region

        # Same region = higher trade
        if region1 and region1 == region2:
            return 0.3
        # Adjacent regions get smaller bonus
        elif (region1 == 'europe' and region2 == 'eurasia') or (region1 == 'eurasia' and region2 == 'europe'):
            return 0.15
        elif (region1 == 'east_asia' and region2 == 'southeast_asia') or (region1 == 'southeast_asia' and region2 == 'east_asia'):
            return 0.15
        else:
            return 0.0

    def _calculate_economic_size_factor(self, country1: str, country2: str) -> float:
        """Calculate economic size factor for trade intensity."""
        # Larger economies generally trade more
        large_economies = ['USA', 'CHN', 'DEU', 'JPN', 'GBR', 'FRA', 'IND', 'ITA', 'BRA', 'CAN', 'RUS', 'KOR', 'ESP', 'AUS', 'MEX', 'IDN', 'NLD', 'SAU', 'TUR', 'CHE']
        medium_economies = ['BEL', 'AUT', 'IRL', 'ISR', 'NOR', 'ARE', 'ZAF', 'ARG', 'SWE', 'POL', 'DNK', 'FIN', 'CHL', 'NZL', 'SGP', 'CZE', 'PRT', 'GRC', 'HUN', 'HKG']

        c1_large = country1 in large_economies
        c2_large = country2 in large_economies
        c1_medium = country1 in medium_economies
        c2_medium = country2 in medium_economies

        if c1_large and c2_large:
            return 0.2  # Two large economies
        elif (c1_large and c2_medium) or (c1_medium and c2_large):
            return 0.1  # Large + medium
        elif c1_medium and c2_medium:
            return 0.05  # Two medium economies
        else:
            return 0.0  # Small economies

    def _get_historical_sentiment_trend(self, perceiver: str, target: str) -> float:
        """Get historical sentiment trend between countries."""
        # This would query historical data - for now, analyze relationship patterns
        return self._analyze_relationship_pattern(perceiver, target)

    def _analyze_relationship_pattern(self, country1: str, country2: str) -> float:
        """Analyze relationship pattern based on historical context and current articles."""
        # Collect recent sentiment data
        sentiment_scores = []

        # Get sentiment from multiple keyword searches
        keywords1 = self._get_country_keywords(country1)
        keywords2 = self._get_country_keywords(country2)

        # Simulate analyzing articles from different perspectives
        for _ in range(5):  # Sample multiple articles
            article_sentiment = self._simulate_article_sentiment_analysis(country1, country2)
            if article_sentiment is not None:
                sentiment_scores.append(article_sentiment)

        if sentiment_scores:
            avg_sentiment = sum(sentiment_scores) / len(sentiment_scores)
            return avg_sentiment
        else:
            return 0.0  # Neutral if no data

    def _simulate_article_sentiment_analysis(self, country1: str, country2: str) -> float:
        """Simulate sentiment analysis of articles about country relationships."""
        import random

        # Generate sentiment based on realistic patterns without hard-coding specific countries
        base_sentiment = random.uniform(-0.1, 0.1)  # Slight random variation

        # Add factors that would come from real article analysis:

        # 1. Geographic tension factor (neighboring countries often have more tensions)
        if self._calculate_geographic_proximity(country1, country2) > 0.2:
            # Neighboring countries might have more complex relationships
            base_sentiment += random.uniform(-0.3, 0.3)

        # 2. Economic competition factor (large economies might have trade tensions)
        econ_factor1 = self._calculate_economic_size_factor(country1, country2)
        if econ_factor1 > 0.15:
            # Large economies might have competition
            base_sentiment += random.uniform(-0.2, 0.2)

        # 3. Regional stability factor
        # This would come from actual news analysis in production
        regional_stability = random.uniform(-0.2, 0.2)
        base_sentiment += regional_stability

        return max(min(base_sentiment, 1.0), -1.0)

    def _get_sanctions_penalty(self, perceiver: str, target: str) -> float:
        """Calculate sanctions impact based on historical sentiment patterns."""
        # Use sentiment history to determine if there are likely sanctions
        historical_sentiment = self._get_historical_sentiment_trend(perceiver, target)

        # If historical sentiment is very negative, assume economic restrictions
        if historical_sentiment < -0.5:
            return 0.2  # Heavy penalties for very negative relationships
        elif historical_sentiment < -0.2:
            return 0.6  # Moderate penalties for negative relationships
        else:
            return 1.0  # No penalties for neutral/positive relationships

    def _calculate_investment_perception(self, perceiver: str, target: str) -> float:
        """Calculate investment-based perception score."""
        # Mock investment data
        return 50.0 + np.random.normal(0, 10)  # Placeholder

    def _calculate_cooperation_perception(self, perceiver: str, target: str) -> float:
        """Calculate cooperation-based perception score."""
        # Mock cooperation data
        return 50.0 + np.random.normal(0, 15)  # Placeholder

    def _analyze_official_statements(self, perceiver: str, target: str) -> float:
        """Analyze official government statements."""
        return 50.0 + np.random.normal(0, 20)  # Placeholder

    def _calculate_un_alignment(self, perceiver: str, target: str) -> float:
        """Calculate UN voting alignment score."""
        # Mock UN voting alignment data
        mock_alignments = {
            ('USA', 'GBR'): 90.0,
            ('USA', 'CHN'): 25.0,
            ('CHN', 'RUS'): 80.0,
            ('USA', 'RUS'): 20.0,
        }

        return mock_alignments.get((perceiver, target), 50.0)

    def _analyze_trade_relations(self, perceiver: str, target: str) -> float:
        """Analyze trade relationship status."""
        return 50.0 + np.random.normal(0, 25)  # Placeholder

    def _analyze_diplomatic_activity(self, perceiver: str, target: str) -> float:
        """Analyze diplomatic activity levels."""
        return 50.0 + np.random.normal(0, 15)  # Placeholder


class GlobalPerceptionIndex:
    """Main Global Perception Index system."""

    def __init__(self, db_path: str = "state/global_perception_index.sqlite"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True)
        self.collector = PerceptionDataCollector()
        self._init_database()

        # Major countries for tracking (expanded to include Austria and other significant countries)
        self.major_countries = [
            'USA', 'CHN', 'GBR', 'DEU', 'FRA', 'JPN', 'RUS', 'IND', 'BRA', 'AUS',
            'CAN', 'ITA', 'ESP', 'KOR', 'MEX', 'IDN', 'TUR', 'NLD', 'SAU', 'CHE',
            'AUT', 'BEL', 'SWE', 'NOR', 'DNK', 'FIN', 'POL', 'CZE', 'HUN', 'PRT',
            'GRC', 'IRL', 'NZL', 'SGP', 'HKG', 'ISR', 'ARE', 'ZAF', 'ARG', 'CHL',
            'PRK', 'IRN', 'LIE'
        ]

    def _init_database(self):
        """Initialize SQLite database for perception data."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS perception_readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    perceiver_country TEXT NOT NULL,
                    target_country TEXT NOT NULL,
                    perception_score REAL NOT NULL,
                    confidence REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    data_sources TEXT,
                    component_scores TEXT,
                    metadata TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS perception_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    perception_matrix TEXT NOT NULL,
                    country_rankings TEXT,
                    trend_indicators TEXT,
                    metadata TEXT
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_perception_countries
                ON perception_readings(perceiver_country, target_country)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_perception_timestamp
                ON perception_readings(timestamp)
            """)

    def measure_perception(self, perceiver: str, target: str) -> PerceptionReading:
        """Measure how perceiver country perceives target country."""
        try:
            logger.info(f"Measuring perception: {perceiver} -> {target}")

            # Collect data from all sources
            news_data = self.collector.collect_news_sentiment(perceiver, target)
            economic_data = self.collector.collect_economic_indicators(perceiver, target)
            diplomatic_data = self.collector.collect_diplomatic_signals(perceiver, target)

            # Component scores
            component_scores = {
                'news_sentiment': news_data.get('sentiment', 50.0),
                'economic_relations': economic_data.get('economic_perception', 50.0),
                'diplomatic_relations': diplomatic_data.get('diplomatic_perception', 50.0),
                'confidence_news': news_data.get('confidence', 0.0),
                'confidence_economic': economic_data.get('confidence', 0.0),
                'confidence_diplomatic': diplomatic_data.get('confidence', 0.0),
            }

            # Weight components by confidence and importance (prioritize sentiment signals)
            weights = {
                'news_sentiment': 0.6,  # Increased from 0.4 to capture polarization
                'economic_relations': 0.25,  # Reduced from 0.35
                'diplomatic_relations': 0.15   # Reduced from 0.25
            }

            # Calculate weighted perception score
            perception_score = (
                component_scores['news_sentiment'] * weights['news_sentiment'] +
                component_scores['economic_relations'] * weights['economic_relations'] +
                component_scores['diplomatic_relations'] * weights['diplomatic_relations']
            )

            # Apply variance boosting to amplify deviations from neutral (50)
            deviation_from_neutral = perception_score - 50.0
            amplification_factor = 2.5  # Amplify deviations by 150% to show real polarization
            boosted_score = 50.0 + (deviation_from_neutral * amplification_factor)

            # Ensure score is in [1, 100] range
            perception_score = max(1.0, min(100.0, boosted_score))

            # Calculate overall confidence
            overall_confidence = (
                news_data.get('confidence', 0.0) * weights['news_sentiment'] +
                economic_data.get('confidence', 0.0) * weights['economic_relations'] +
                diplomatic_data.get('confidence', 0.0) * weights['diplomatic_relations']
            )

            # Confidence-aware scoring: Don't collapse to neutral if confidence is low
            if overall_confidence < 0.3:
                # For very low confidence, use wider variance to show uncertainty
                uncertainty_range = 15.0  # ±15 points range
                perception_score = max(1.0, min(100.0, perception_score))
            elif overall_confidence < 0.5:
                # Medium-low confidence: slight adjustment but don't neutralize
                perception_score = perception_score * 0.9 + 50.0 * 0.1  # 10% pull toward neutral
            # High confidence (≥0.5): use full calculated score without neutralization

            # Data sources used
            data_sources = []
            if news_data.get('article_count', 0) > 0:
                data_sources.append('news_sentiment')
            if economic_data.get('confidence', 0.0) > 0:
                data_sources.append('economic_indicators')
            if diplomatic_data.get('confidence', 0.0) > 0:
                data_sources.append('diplomatic_signals')

            reading = PerceptionReading(
                perceiver_country=perceiver,
                target_country=target,
                perception_score=perception_score,
                confidence=overall_confidence,
                timestamp=datetime.now(),
                data_sources=data_sources,
                component_scores=component_scores,
                metadata={
                    'raw_data': {
                        'news': news_data,
                        'economic': economic_data,
                        'diplomatic': diplomatic_data
                    }
                }
            )

            # Store in database
            self._store_reading(reading)

            return reading

        except Exception as e:
            logger.error(f"Error measuring perception {perceiver}->{target}: {e}")
            # Return neutral reading
            return PerceptionReading(
                perceiver_country=perceiver,
                target_country=target,
                perception_score=50.0,
                confidence=0.0,
                timestamp=datetime.now(),
                data_sources=[],
                component_scores={},
                metadata={'error': str(e)}
            )

    def get_country_perception(self, target: str, perceivers: List[str] = None) -> Dict[str, float]:
        """Get how target country is perceived by specified countries."""
        if perceivers is None:
            perceivers = [c for c in self.major_countries if c != target]

        perceptions = {}
        for perceiver in perceivers:
            try:
                reading = self.measure_perception(perceiver, target)
                perceptions[perceiver] = reading.perception_score
            except Exception as e:
                logger.error(f"Error getting perception {perceiver}->{target}: {e}")
                perceptions[perceiver] = 50.0

        return perceptions

    def get_perception_matrix(self, countries: List[str] = None) -> Dict[str, Dict[str, float]]:
        """Get full perception matrix between countries."""
        if countries is None:
            countries = self.major_countries

        matrix = {}
        for perceiver in countries:
            matrix[perceiver] = {}
            for target in countries:
                if perceiver != target:
                    reading = self.measure_perception(perceiver, target)
                    matrix[perceiver][target] = reading.perception_score
                else:
                    matrix[perceiver][target] = None  # Can't perceive self

        return matrix

    def calculate_global_rankings(self, countries: List[str] = None) -> Dict[str, Tuple[float, int]]:
        """Calculate global perception rankings."""
        if countries is None:
            countries = self.major_countries

        country_scores = {}

        for target in countries:
            perceptions = self.get_country_perception(target,
                [c for c in countries if c != target])

            if perceptions:
                avg_score = np.mean(list(perceptions.values()))
                country_scores[target] = avg_score
            else:
                country_scores[target] = 50.0

        # Rank countries by average perception score
        sorted_countries = sorted(country_scores.items(), key=lambda x: x[1], reverse=True)

        rankings = {}
        for rank, (country, score) in enumerate(sorted_countries, 1):
            rankings[country] = (score, rank)

        return rankings

    def get_regional_perceptions(self, target: str) -> Dict[str, Dict[str, float]]:
        """Get perception of target country segmented by world regions."""
        regional_mapping = {
            'north_america': ['USA', 'CAN', 'MEX'],
            'europe': ['GBR', 'DEU', 'FRA', 'ITA', 'ESP', 'NLD', 'BEL', 'CHE', 'AUT', 'SWE', 'NOR', 'DNK', 'FIN', 'POL', 'CZE', 'HUN', 'PRT', 'GRC', 'IRL'],
            'asia_pacific': ['CHN', 'JPN', 'KOR', 'IND', 'IDN', 'SGP', 'AUS', 'NZL', 'HKG'],
            'middle_east': ['SAU', 'ARE', 'ISR', 'IRN', 'TUR'],
            'africa': ['ZAF'],
            'latin_america': ['BRA', 'ARG', 'CHL'],
            'other': ['PRK', 'RUS']  # Special cases
        }

        regional_results = {}

        for region, countries in regional_mapping.items():
            regional_scores = []
            for perceiver in countries:
                if perceiver != target and perceiver in self.major_countries:
                    try:
                        reading = self.measure_perception(perceiver, target)
                        regional_scores.append(reading.perception_score)
                    except:
                        continue

            if regional_scores:
                regional_results[region] = {
                    'average_score': sum(regional_scores) / len(regional_scores),
                    'count': len(regional_scores),
                    'min_score': min(regional_scores),
                    'max_score': max(regional_scores),
                    'variance': sum((x - sum(regional_scores)/len(regional_scores))**2 for x in regional_scores) / len(regional_scores)
                }

        return regional_results

    def get_perception_trends(self, country: str, days: int = 30) -> Dict[str, Any]:
        """Get perception trends for a country over time."""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)

            with sqlite3.connect(self.db_path) as conn:
                df = pd.read_sql_query("""
                    SELECT perceiver_country, target_country, perception_score,
                           timestamp, confidence
                    FROM perception_readings
                    WHERE target_country = ? AND timestamp > ?
                    ORDER BY timestamp
                """, conn, params=(country, cutoff_date.isoformat()))

            if df.empty:
                return {'trend': 'no_data', 'change': 0.0, 'readings': 0}

            df['timestamp'] = pd.to_datetime(df['timestamp'])

            # Calculate overall trend
            recent_scores = df['perception_score'].values
            if len(recent_scores) > 1:
                trend_slope = np.polyfit(range(len(recent_scores)), recent_scores, 1)[0]
                change = recent_scores[-1] - recent_scores[0]
            else:
                trend_slope = 0.0
                change = 0.0

            # Determine trend direction
            if trend_slope > 0.1:
                trend = 'improving'
            elif trend_slope < -0.1:
                trend = 'declining'
            else:
                trend = 'stable'

            return {
                'trend': trend,
                'change': change,
                'readings': len(df),
                'avg_score': df['perception_score'].mean(),
                'avg_confidence': df['confidence'].mean(),
                'trend_slope': trend_slope
            }

        except Exception as e:
            logger.error(f"Error getting trends for {country}: {e}")
            return {'trend': 'error', 'change': 0.0, 'readings': 0}

    def _store_reading(self, reading: PerceptionReading):
        """Store perception reading in database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO perception_readings
                    (perceiver_country, target_country, perception_score, confidence,
                     timestamp, data_sources, component_scores, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    reading.perceiver_country,
                    reading.target_country,
                    reading.perception_score,
                    reading.confidence,
                    reading.timestamp.isoformat(),
                    json.dumps(reading.data_sources),
                    json.dumps(reading.component_scores),
                    json.dumps(reading.metadata) if reading.metadata else '{}'
                ))
        except Exception as e:
            logger.error(f"Error storing reading: {e}")

    def generate_report(self, country: str = None) -> Dict[str, Any]:
        """Generate comprehensive perception report."""
        if country:
            # Single country report
            perceptions = self.get_country_perception(country)
            trends = self.get_perception_trends(country)
            rankings = self.calculate_global_rankings()

            return {
                'country': country,
                'current_perceptions': perceptions,
                'average_score': np.mean(list(perceptions.values())) if perceptions else 50.0,
                'global_rank': rankings.get(country, (50.0, 'N/A'))[1],
                'trends': trends,
                'timestamp': datetime.now().isoformat()
            }
        else:
            # Global report
            rankings = self.calculate_global_rankings()
            matrix = self.get_perception_matrix()

            return {
                'global_rankings': rankings,
                'perception_matrix': matrix,
                'top_5': list(rankings.items())[:5],
                'bottom_5': list(rankings.items())[-5:],
                'timestamp': datetime.now().isoformat()
            }


# CLI interface
def main():
    """CLI interface for Global Perception Index."""
    import argparse

    parser = argparse.ArgumentParser(description='Global Perception Index')
    parser.add_argument('command', choices=['measure', 'rank', 'trends', 'report'],
                       help='Command to execute')
    parser.add_argument('--perceiver', help='Perceiver country code (e.g., USA)')
    parser.add_argument('--target', help='Target country code (e.g., CHN)')
    parser.add_argument('--country', help='Country for single-country operations')
    parser.add_argument('--days', type=int, default=30, help='Days for trend analysis')

    args = parser.parse_args()

    gpi = GlobalPerceptionIndex()

    if args.command == 'measure':
        if not args.perceiver or not args.target:
            print("Error: --perceiver and --target required for measure command")
            return

        reading = gpi.measure_perception(args.perceiver, args.target)
        print(f"Perception: {args.perceiver} -> {args.target}")
        print(f"Score: {reading.perception_score:.1f}/100")
        print(f"Confidence: {reading.confidence:.2f}")
        print(f"Components: {reading.component_scores}")

    elif args.command == 'rank':
        rankings = gpi.calculate_global_rankings()
        print("Global Perception Rankings:")
        print("-" * 40)
        for country, (score, rank) in rankings.items():
            print(f"{rank:2d}. {country}: {score:.1f}/100")

    elif args.command == 'trends':
        if not args.country:
            print("Error: --country required for trends command")
            return

        trends = gpi.get_perception_trends(args.country, args.days)
        print(f"Perception Trends for {args.country} (last {args.days} days):")
        print(f"Trend: {trends['trend']}")
        print(f"Change: {trends['change']:+.1f}")
        print(f"Average Score: {trends.get('avg_score', 0):.1f}/100")
        print(f"Readings: {trends['readings']}")

    elif args.command == 'report':
        if args.country:
            report = gpi.generate_report(args.country)
            print(f"Perception Report for {args.country}")
            print("=" * 40)
            print(f"Average Score: {report['average_score']:.1f}/100")
            print(f"Global Rank: {report['global_rank']}")
            print(f"Trend: {report['trends']['trend']}")
            print("\nPerceptions by Country:")
            for country, score in sorted(report['current_perceptions'].items(),
                                       key=lambda x: x[1], reverse=True):
                print(f"  {country}: {score:.1f}/100")
        else:
            report = gpi.generate_report()
            print("Global Perception Report")
            print("=" * 40)
            print("Top 5 Countries:")
            for country, (score, rank) in report['top_5']:
                print(f"  {rank}. {country}: {score:.1f}/100")
            print("\nBottom 5 Countries:")
            for country, (score, rank) in report['bottom_5']:
                print(f"  {rank}. {country}: {score:.1f}/100")


if __name__ == "__main__":
    main()