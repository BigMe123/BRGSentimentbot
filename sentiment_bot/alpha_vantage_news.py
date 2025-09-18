#!/usr/bin/env python3
"""
Alpha Vantage News API Connector
High-quality news and sentiment data for all BSG Bot systems
"""

import requests
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import logging
import time

logger = logging.getLogger(__name__)


@dataclass
class AlphaVantageArticle:
    """Structured article data from Alpha Vantage News API."""
    title: str
    summary: str
    url: str
    source: str
    time_published: str
    overall_sentiment_score: float
    overall_sentiment_label: str
    topics: List[str]
    ticker_sentiments: Dict[str, Dict[str, float]]  # ticker -> {sentiment_score, relevance_score, sentiment_label}


class AlphaVantageNewsConnector:
    """Connector for Alpha Vantage News and Sentiment API."""

    def __init__(self, api_key: str = "YILWUFW6VO1RA561"):
        self.api_key = api_key
        self.base_url = "https://www.alphavantage.co/query"
        self.request_delay = 2  # Seconds between requests to respect rate limits

    def get_news_sentiment(self,
                          tickers: Optional[List[str]] = None,
                          topics: Optional[List[str]] = None,
                          time_from: Optional[str] = None,
                          time_to: Optional[str] = None,
                          limit: int = 50) -> List[AlphaVantageArticle]:
        """
        Get news with sentiment analysis from Alpha Vantage.

        Args:
            tickers: List of stock tickers to filter by (e.g., ['AAPL', 'MSFT'])
            topics: List of topics to filter by (e.g., ['technology', 'earnings'])
            time_from: Start time in YYYYMMDDTHHMM format
            time_to: End time in YYYYMMDDTHHMM format
            limit: Maximum number of articles (max 1000)
        """
        try:
            params = {
                'function': 'NEWS_SENTIMENT',
                'apikey': self.api_key,
                'limit': min(limit, 1000)
            }

            # Add optional filters
            if tickers:
                params['tickers'] = ','.join(tickers)
            if topics:
                params['topics'] = ','.join(topics)
            if time_from:
                params['time_from'] = time_from
            if time_to:
                params['time_to'] = time_to

            print(f"📡 Fetching news from Alpha Vantage...")
            response = requests.get(self.base_url, params=params, timeout=20)

            if response.status_code == 200:
                data = response.json()

                if 'feed' in data:
                    articles = []
                    for article_data in data['feed']:
                        article = self._parse_article(article_data)
                        if article:
                            articles.append(article)

                    print(f"✅ Retrieved {len(articles)} articles with sentiment data")
                    return articles
                else:
                    error_msg = data.get('Information', 'Unknown error')
                    logger.warning(f"Alpha Vantage API response: {error_msg}")
                    return []
            else:
                logger.error(f"Alpha Vantage API request failed: {response.status_code}")
                return []

        except Exception as e:
            logger.error(f"Error fetching Alpha Vantage news: {e}")
            return []

    def get_economic_news(self, limit: int = 100) -> List[AlphaVantageArticle]:
        """Get news specifically related to economic topics."""
        # Get general news first, then filter by content
        all_articles = self.get_news_sentiment(limit=limit)

        # Filter for economic-related content
        economic_keywords = [
            'economy', 'economic', 'inflation', 'fed', 'federal reserve', 'interest rate',
            'gdp', 'unemployment', 'jobs', 'employment', 'market', 'finance', 'financial',
            'earnings', 'revenue', 'profit', 'trading', 'investment', 'stocks', 'bonds',
            'commodity', 'oil', 'gold', 'currency', 'dollar', 'euro', 'trade'
        ]

        economic_articles = []
        for article in all_articles:
            content = (article.title + " " + article.summary).lower()
            if any(keyword in content for keyword in economic_keywords):
                economic_articles.append(article)

        print(f"📈 Filtered to {len(economic_articles)} economic articles from {len(all_articles)} total")
        return economic_articles

    def get_country_perception_news(self,
                                   perceiver_country: str,
                                   target_country: str,
                                   limit: int = 50) -> List[AlphaVantageArticle]:
        """
        Get news for Global Perception Index analysis.
        Search for news from perceiver country about target country.
        """
        # Create search terms for international perception
        country_keywords = {
            'USA': ['United States', 'America', 'US', 'American'],
            'CHN': ['China', 'Chinese', 'Beijing'],
            'GBR': ['United Kingdom', 'Britain', 'British', 'UK'],
            'DEU': ['Germany', 'German', 'Berlin'],
            'FRA': ['France', 'French', 'Paris'],
            'JPN': ['Japan', 'Japanese', 'Tokyo'],
            'RUS': ['Russia', 'Russian', 'Moscow'],
            'IND': ['India', 'Indian', 'Delhi'],
        }

        # Try to get news mentioning both countries
        # Note: Alpha Vantage doesn't have country-specific filtering,
        # so we'll get general news and filter by content
        articles = self.get_news_sentiment(limit=limit)

        # Filter articles for international relations
        perceiver_terms = country_keywords.get(perceiver_country, [perceiver_country])
        target_terms = country_keywords.get(target_country, [target_country])

        relevant_articles = []
        for article in articles:
            content = (article.title + " " + article.summary).lower()

            # Check if article mentions both countries or international relations
            has_perceiver = any(term.lower() in content for term in perceiver_terms)
            has_target = any(term.lower() in content for term in target_terms)
            has_international = any(term in content for term in [
                'international', 'diplomatic', 'trade', 'relations', 'cooperation',
                'agreement', 'sanctions', 'treaty', 'alliance', 'partnership'
            ])

            if (has_perceiver and has_target) or (has_international and (has_perceiver or has_target)):
                relevant_articles.append(article)

        print(f"🌍 Found {len(relevant_articles)} articles relevant to {perceiver_country}-{target_country} relations")
        return relevant_articles

    def get_sp500_news(self, limit: int = 50) -> List[AlphaVantageArticle]:
        """Get news specifically about S&P 500 and major market indices."""
        sp500_tickers = ['SPY', 'QQQ', 'DIA', 'IWM', 'VTI']
        return self.get_news_sentiment(tickers=sp500_tickers, limit=limit)

    def get_forex_news(self, currency_pairs: List[str] = None, limit: int = 50) -> List[AlphaVantageArticle]:
        """Get news relevant to forex markets."""
        if not currency_pairs:
            currency_pairs = ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCAD', 'AUDUSD']

        # Get general financial news since forex-specific tickers aren't well supported
        return self.get_news_sentiment(topics=['economy', 'finance'], limit=limit)

    def get_commodity_news(self, commodities: List[str] = None, limit: int = 50) -> List[AlphaVantageArticle]:
        """Get news about commodities."""
        if not commodities:
            # Major commodity ETFs and related tickers
            commodities = ['GLD', 'SLV', 'USO', 'UNG', 'DBA', 'DBC']

        return self.get_news_sentiment(tickers=commodities, limit=limit)

    def calculate_sentiment_metrics(self, articles: List[AlphaVantageArticle]) -> Dict[str, Any]:
        """Calculate aggregate sentiment metrics from articles."""
        if not articles:
            return {
                'avg_sentiment': 0.0,
                'sentiment_distribution': {'bullish': 0, 'bearish': 0, 'neutral': 0},
                'total_articles': 0,
                'top_sources': [],
                'recent_sentiment_trend': 0.0
            }

        # Calculate average sentiment
        sentiments = [article.overall_sentiment_score for article in articles]
        avg_sentiment = sum(sentiments) / len(sentiments)

        # Count sentiment labels
        sentiment_dist = {'bullish': 0, 'bearish': 0, 'neutral': 0}
        for article in articles:
            label = article.overall_sentiment_label.lower()
            if 'bullish' in label:
                sentiment_dist['bullish'] += 1
            elif 'bearish' in label:
                sentiment_dist['bearish'] += 1
            else:
                sentiment_dist['neutral'] += 1

        # Top sources
        sources = {}
        for article in articles:
            sources[article.source] = sources.get(article.source, 0) + 1
        top_sources = sorted(sources.items(), key=lambda x: x[1], reverse=True)[:5]

        # Recent trend (last 24h vs older)
        now = datetime.now()
        recent_articles = []
        older_articles = []

        for article in articles:
            try:
                pub_time = datetime.strptime(article.time_published, '%Y%m%dT%H%M%S')
                if (now - pub_time).total_seconds() < 86400:  # 24 hours
                    recent_articles.append(article.overall_sentiment_score)
                else:
                    older_articles.append(article.overall_sentiment_score)
            except:
                continue

        recent_sentiment = sum(recent_articles) / len(recent_articles) if recent_articles else avg_sentiment
        older_sentiment = sum(older_articles) / len(older_articles) if older_articles else avg_sentiment
        trend = recent_sentiment - older_sentiment

        return {
            'avg_sentiment': avg_sentiment,
            'sentiment_distribution': sentiment_dist,
            'total_articles': len(articles),
            'top_sources': top_sources,
            'recent_sentiment_trend': trend,
            'recent_sentiment': recent_sentiment,
            'older_sentiment': older_sentiment
        }

    def _parse_article(self, article_data: Dict) -> Optional[AlphaVantageArticle]:
        """Parse raw article data from Alpha Vantage API."""
        try:
            # Extract topics
            topics = []
            if 'topics' in article_data:
                topics = [topic.get('topic', '') for topic in article_data['topics']]

            # Extract ticker sentiments
            ticker_sentiments = {}
            if 'ticker_sentiment' in article_data:
                for ticker_data in article_data['ticker_sentiment']:
                    ticker = ticker_data.get('ticker', '')
                    if ticker:
                        ticker_sentiments[ticker] = {
                            'sentiment_score': float(ticker_data.get('ticker_sentiment_score', 0)),
                            'relevance_score': float(ticker_data.get('relevance_score', 0)),
                            'sentiment_label': ticker_data.get('ticker_sentiment_label', 'Neutral')
                        }

            return AlphaVantageArticle(
                title=article_data.get('title', ''),
                summary=article_data.get('summary', ''),
                url=article_data.get('url', ''),
                source=article_data.get('source', ''),
                time_published=article_data.get('time_published', ''),
                overall_sentiment_score=float(article_data.get('overall_sentiment_score', 0)),
                overall_sentiment_label=article_data.get('overall_sentiment_label', 'Neutral'),
                topics=topics,
                ticker_sentiments=ticker_sentiments
            )

        except Exception as e:
            logger.warning(f"Error parsing article: {e}")
            return None


# Helper functions for integration with existing systems
def get_alpha_vantage_sentiment_data(topic: str = "general", limit: int = 50) -> List[Dict[str, Any]]:
    """
    Get sentiment data in format compatible with existing predictors.
    Returns list of articles in the format expected by current systems.
    """
    connector = AlphaVantageNewsConnector()

    if topic == "economic":
        articles = connector.get_economic_news(limit=limit)
    elif topic == "sp500":
        articles = connector.get_sp500_news(limit=limit)
    elif topic == "forex":
        articles = connector.get_forex_news(limit=limit)
    elif topic == "commodities":
        articles = connector.get_commodity_news(limit=limit)
    else:
        articles = connector.get_news_sentiment(limit=limit)

    # Convert to format expected by existing systems
    formatted_articles = []
    for article in articles:
        formatted_articles.append({
            'title': article.title,
            'content': article.summary,
            'sentiment': article.overall_sentiment_score,
            'source': article.source,
            'url': article.url,
            'published': article.time_published,
            'topics': article.topics,
            'sentiment_label': article.overall_sentiment_label
        })

    return formatted_articles


if __name__ == "__main__":
    # Test the connector
    connector = AlphaVantageNewsConnector()

    print("🧪 Testing Alpha Vantage News Connector...")

    # Test economic news
    articles = connector.get_economic_news(limit=10)
    metrics = connector.calculate_sentiment_metrics(articles)

    print(f"\n📊 Economic News Sentiment Analysis:")
    print(f"   Total Articles: {metrics['total_articles']}")
    print(f"   Average Sentiment: {metrics['avg_sentiment']:.3f}")
    print(f"   Distribution: {metrics['sentiment_distribution']}")
    print(f"   Recent Trend: {metrics['recent_sentiment_trend']:+.3f}")
    print(f"   Top Sources: {[source for source, count in metrics['top_sources'][:3]]}")