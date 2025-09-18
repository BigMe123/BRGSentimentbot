"""
News Data Collector with TheNewsAPI Integration
================================================
Collects and processes news data for economic sentiment analysis.
"""

import os
import json
import logging
import aiohttp
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import hashlib

logger = logging.getLogger(__name__)


@dataclass
class NewsArticle:
    """Structured news article data"""
    title: str
    description: str
    content: str
    url: str
    published_at: datetime
    source: str
    country: Optional[str] = None
    categories: List[str] = None
    sentiment_score: Optional[float] = None
    entities: List[str] = None
    topics: List[str] = None


class TheNewsAPIClient:
    """Client for TheNewsAPI with economic focus"""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv('THENEWS_API_KEY', 'BAV2J2VwecIEtxHVm1zOMGERfU52TA88zmW43Fbw')
        self.base_url = 'https://api.thenewsapi.com/v1/news'
        self.session = None
        self.cache = {}

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    def _cache_key(self, params: Dict) -> str:
        """Generate cache key from parameters"""
        param_str = json.dumps(params, sort_keys=True)
        return hashlib.md5(param_str.encode()).hexdigest()

    async def search_news(self,
                         query: str = None,
                         categories: List[str] = None,
                         countries: List[str] = None,
                         domains: List[str] = None,
                         exclude_domains: List[str] = None,
                         language: str = 'en',
                         published_after: datetime = None,
                         published_before: datetime = None,
                         sort: str = 'relevance_score',
                         limit: int = 100) -> List[NewsArticle]:
        """
        Search news with various filters

        Categories: business, entertainment, general, health, politics, science, sports, tech
        Countries: us, gb, ca, au, in, de, fr, cn, jp, etc.
        """

        params = {
            'api_token': self.api_key,
            'language': language,
            'sort': sort,
            'limit': min(limit, 100),  # API max is 100
            'page': 1
        }

        if query:
            params['search'] = query

        if categories:
            params['categories'] = ','.join(categories)

        if countries:
            params['countries'] = ','.join(countries)

        if domains:
            params['domains'] = ','.join(domains)

        if exclude_domains:
            params['exclude_domains'] = ','.join(exclude_domains)

        if published_after:
            params['published_after'] = published_after.strftime('%Y-%m-%dT%H:%M:%S')

        if published_before:
            params['published_before'] = published_before.strftime('%Y-%m-%dT%H:%M:%S')

        # Check cache
        cache_key = self._cache_key(params)
        if cache_key in self.cache:
            cache_entry = self.cache[cache_key]
            if (datetime.now() - cache_entry['timestamp']).seconds < 900:  # 15 min cache
                logger.info(f"Using cached results for query: {query}")
                return cache_entry['data']

        try:
            async with self.session.get(f"{self.base_url}/all", params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    articles = []
                    for item in data.get('data', []):
                        # Parse published date handling timezone
                        published_str = item.get('published_at', '')
                        if published_str:
                            try:
                                # Remove timezone info for consistency
                                published_date = datetime.fromisoformat(published_str.replace('Z', '+00:00')).replace(tzinfo=None)
                            except:
                                published_date = datetime.now()
                        else:
                            published_date = datetime.now()

                        article = NewsArticle(
                            title=item.get('title', ''),
                            description=item.get('description', ''),
                            content=item.get('snippet', ''),
                            url=item.get('url', ''),
                            published_at=published_date,
                            source=item.get('source', ''),
                            country=item.get('country'),
                            categories=item.get('categories', []),
                            entities=item.get('entities', []),
                            topics=item.get('keywords', [])
                        )
                        articles.append(article)

                    # Update cache
                    self.cache[cache_key] = {
                        'timestamp': datetime.now(),
                        'data': articles
                    }

                    logger.info(f"Retrieved {len(articles)} articles for query: {query}")
                    return articles

                else:
                    logger.error(f"API Error: {response.status} - {await response.text()}")
                    return []

        except Exception as e:
            logger.error(f"Failed to fetch news: {e}")
            return []

    async def get_economic_news(self,
                               countries: List[str] = None,
                               hours_back: int = 24) -> Dict[str, List[NewsArticle]]:
        """Get economic-focused news by category"""

        if not countries:
            countries = ['us', 'gb', 'de', 'jp', 'cn', 'in']

        published_after = datetime.now() - timedelta(hours=hours_back)

        economic_queries = {
            'employment': 'jobs unemployment payrolls hiring layoffs wages',
            'inflation': 'inflation CPI prices "consumer prices" "price index"',
            'monetary_policy': '"federal reserve" "central bank" "interest rates" "monetary policy"',
            'trade': 'trade tariffs exports imports "trade war" sanctions',
            'gdp': 'GDP "economic growth" recession economy',
            'markets': '"stock market" equities bonds forex commodities',
            'energy': 'oil gas energy prices OPEC "crude oil"',
            'housing': 'housing "real estate" mortgage "home sales"',
            'manufacturing': 'manufacturing PMI "industrial production" factories',
            'retail': 'retail sales "consumer spending" "consumer confidence"'
        }

        results = {}

        for category, query in economic_queries.items():
            articles = await self.search_news(
                query=query,
                categories=['business', 'politics'],
                countries=countries,
                published_after=published_after,
                limit=50
            )

            results[category] = articles
            logger.info(f"Collected {len(articles)} articles for {category}")

            # Rate limiting
            await asyncio.sleep(0.5)

        return results

    async def get_country_sentiment_data(self, country_code: str) -> Dict[str, Any]:
        """Get news for country-specific sentiment analysis"""

        # Country-specific queries
        queries = {
            'economic': f'{country_code} economy GDP growth inflation',
            'political': f'{country_code} government policy election politics',
            'trade': f'{country_code} trade exports imports tariffs',
            'currency': f'{country_code} currency exchange rate forex',
            'business': f'{country_code} business companies corporate earnings'
        }

        sentiment_data = {
            'country': country_code,
            'timestamp': datetime.now().isoformat(),
            'categories': {}
        }

        for category, query in queries.items():
            articles = await self.search_news(
                query=query,
                countries=[country_code],
                published_after=datetime.now() - timedelta(days=7),
                limit=30
            )

            sentiment_data['categories'][category] = {
                'article_count': len(articles),
                'articles': [asdict(a) for a in articles[:10]]  # Sample
            }

            await asyncio.sleep(0.3)  # Rate limiting

        return sentiment_data

    async def get_commodity_news(self, commodities: List[str] = None) -> Dict[str, List[NewsArticle]]:
        """Get commodity-specific news"""

        if not commodities:
            commodities = ['oil', 'gold', 'copper', 'wheat', 'corn', 'natural gas']

        results = {}

        for commodity in commodities:
            # Build commodity-specific query
            query = f'{commodity} prices supply demand forecast'

            if commodity in ['oil', 'gas']:
                query += ' OPEC energy'
            elif commodity in ['wheat', 'corn', 'soy']:
                query += ' agriculture harvest weather'
            elif commodity in ['gold', 'silver', 'copper']:
                query += ' mining metals'

            articles = await self.search_news(
                query=query,
                categories=['business'],
                published_after=datetime.now() - timedelta(days=3),
                limit=25
            )

            results[commodity] = articles
            await asyncio.sleep(0.3)

        return results

    async def get_geopolitical_risk_news(self) -> List[NewsArticle]:
        """Get news related to geopolitical risks"""

        risk_queries = [
            'sanctions trade war tariffs embargo',
            'military conflict tension escalation',
            'geopolitical risk uncertainty crisis',
            'supply chain disruption blockade'
        ]

        all_articles = []

        for query in risk_queries:
            articles = await self.search_news(
                query=query,
                categories=['politics', 'general'],
                published_after=datetime.now() - timedelta(days=2),
                sort='published_date',
                limit=30
            )

            all_articles.extend(articles)
            await asyncio.sleep(0.3)

        # Deduplicate by URL
        seen_urls = set()
        unique_articles = []
        for article in all_articles:
            if article.url not in seen_urls:
                seen_urls.add(article.url)
                unique_articles.append(article)

        return unique_articles

    async def monitor_market_moving_news(self,
                                        keywords: List[str],
                                        interval_minutes: int = 15) -> List[NewsArticle]:
        """Monitor for market-moving news in near real-time"""

        published_after = datetime.now() - timedelta(minutes=interval_minutes)

        # High-priority market-moving keywords
        query = ' OR '.join([f'"{kw}"' for kw in keywords])

        articles = await self.search_news(
            query=query,
            categories=['business'],
            published_after=published_after,
            sort='published_date',
            limit=50
        )

        # Filter for high relevance
        high_relevance = []
        for article in articles:
            # Simple relevance scoring
            relevance_score = 0
            title_lower = article.title.lower()
            desc_lower = (article.description or '').lower()

            for keyword in keywords:
                if keyword.lower() in title_lower:
                    relevance_score += 2
                if keyword.lower() in desc_lower:
                    relevance_score += 1

            if relevance_score >= 2:
                article.sentiment_score = relevance_score
                high_relevance.append(article)

        return high_relevance


class SentimentExtractor:
    """Extract sentiment signals from news articles"""

    def __init__(self):
        self.sentiment_keywords = {
            'positive': [
                'surge', 'soar', 'rally', 'gain', 'rise', 'improve', 'boost',
                'strong', 'robust', 'growth', 'expand', 'accelerate', 'recover',
                'optimistic', 'bullish', 'upgrade', 'exceed', 'outperform'
            ],
            'negative': [
                'plunge', 'crash', 'fall', 'decline', 'drop', 'weaken', 'slow',
                'concern', 'worry', 'fear', 'risk', 'threat', 'warning', 'crisis',
                'pessimistic', 'bearish', 'downgrade', 'miss', 'disappoint'
            ],
            'uncertainty': [
                'volatile', 'uncertain', 'unclear', 'mixed', 'choppy', 'diverge',
                'question', 'doubt', 'speculation', 'rumor', 'possibility'
            ]
        }

    def extract_sentiment_signals(self, articles: List[NewsArticle]) -> Dict[str, float]:
        """Extract aggregated sentiment signals from articles"""

        if not articles:
            return {
                'overall_sentiment': 0,
                'positive_ratio': 0,
                'negative_ratio': 0,
                'uncertainty_level': 0
            }

        sentiment_scores = []
        uncertainty_scores = []

        for article in articles:
            text = f"{article.title} {article.description or ''} {article.content or ''}".lower()

            # Count sentiment keywords
            positive_count = sum(1 for kw in self.sentiment_keywords['positive'] if kw in text)
            negative_count = sum(1 for kw in self.sentiment_keywords['negative'] if kw in text)
            uncertainty_count = sum(1 for kw in self.sentiment_keywords['uncertainty'] if kw in text)

            # Calculate article sentiment
            if positive_count + negative_count > 0:
                sentiment = (positive_count - negative_count) / (positive_count + negative_count)
            else:
                sentiment = 0

            sentiment_scores.append(sentiment)
            uncertainty_scores.append(uncertainty_count / max(len(text.split()), 1) * 100)

        # Aggregate scores
        avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0
        positive_ratio = sum(1 for s in sentiment_scores if s > 0.2) / len(sentiment_scores) if sentiment_scores else 0
        negative_ratio = sum(1 for s in sentiment_scores if s < -0.2) / len(sentiment_scores) if sentiment_scores else 0
        avg_uncertainty = sum(uncertainty_scores) / len(uncertainty_scores) if uncertainty_scores else 0

        return {
            'overall_sentiment': avg_sentiment,
            'positive_ratio': positive_ratio,
            'negative_ratio': negative_ratio,
            'uncertainty_level': avg_uncertainty,
            'article_count': len(articles)
        }

    def extract_topic_sentiment(self,
                               articles: List[NewsArticle],
                               topics: Dict[str, List[str]]) -> Dict[str, Dict]:
        """Extract sentiment for specific topics"""

        topic_sentiments = {}

        for topic_name, keywords in topics.items():
            topic_articles = []

            # Filter articles relevant to topic
            for article in articles:
                text = f"{article.title} {article.description or ''}".lower()
                if any(kw.lower() in text for kw in keywords):
                    topic_articles.append(article)

            # Calculate topic-specific sentiment
            if topic_articles:
                sentiment = self.extract_sentiment_signals(topic_articles)
                topic_sentiments[topic_name] = sentiment
            else:
                topic_sentiments[topic_name] = {
                    'overall_sentiment': 0,
                    'positive_ratio': 0,
                    'negative_ratio': 0,
                    'uncertainty_level': 0,
                    'article_count': 0
                }

        return topic_sentiments


async def collect_comprehensive_news_data(countries: List[str] = None,
                                         commodities: List[str] = None) -> Dict:
    """Collect comprehensive news data for economic analysis"""

    async with TheNewsAPIClient() as client:
        # Initialize sentiment extractor
        extractor = SentimentExtractor()

        logger.info("Starting comprehensive news data collection...")

        # Collect various news categories
        economic_news = await client.get_economic_news(countries=countries)
        commodity_news = await client.get_commodity_news(commodities=commodities)
        geopolitical_news = await client.get_geopolitical_risk_news()

        # Process sentiment for economic categories
        economic_sentiment = {}
        for category, articles in economic_news.items():
            economic_sentiment[category] = extractor.extract_sentiment_signals(articles)

        # Process commodity sentiment
        commodity_sentiment = {}
        for commodity, articles in commodity_news.items():
            commodity_sentiment[commodity] = extractor.extract_sentiment_signals(articles)

        # Calculate geopolitical risk metrics
        geo_sentiment = extractor.extract_sentiment_signals(geopolitical_news)

        # Define topic groups for analysis
        topics = {
            'layoff_sentiment': ['layoff', 'job cuts', 'downsizing', 'restructuring'],
            'hiring_sentiment': ['hiring', 'recruitment', 'job openings', 'employment growth'],
            'wage_sentiment': ['wages', 'salary', 'compensation', 'pay raise'],
            'supply_chain': ['supply chain', 'logistics', 'shipping', 'shortage'],
            'tariffs': ['tariff', 'trade war', 'duties', 'protectionism'],
            'energy': ['oil', 'gas', 'energy prices', 'fuel costs'],
            'food_commodities': ['wheat', 'corn', 'food prices', 'agriculture']
        }

        # Extract topic-specific sentiment
        all_articles = []
        for articles_list in economic_news.values():
            all_articles.extend(articles_list)

        topic_sentiment = extractor.extract_topic_sentiment(all_articles, topics)

        # Compile comprehensive sentiment data
        sentiment_data = {
            'timestamp': datetime.now().isoformat(),
            'economic_categories': economic_sentiment,
            'commodities': commodity_sentiment,
            'geopolitical': geo_sentiment,
            'topics': topic_sentiment,

            # Map to expected predictor inputs
            'layoff_sentiment': topic_sentiment.get('layoff_sentiment', {}).get('overall_sentiment', 0),
            'hiring_sentiment': topic_sentiment.get('hiring_sentiment', {}).get('overall_sentiment', 0),
            'wage_sentiment': topic_sentiment.get('wage_sentiment', {}).get('overall_sentiment', 0),
            'supply_chain': topic_sentiment.get('supply_chain', {}).get('overall_sentiment', 0),
            'tariffs': topic_sentiment.get('tariffs', {}).get('overall_sentiment', 0),
            'energy': topic_sentiment.get('energy', {}).get('overall_sentiment', 0),
            'food_commodities': topic_sentiment.get('food_commodities', {}).get('overall_sentiment', 0),

            # Sector performance (derived from market news)
            'sector_performance': {
                'technology': economic_sentiment.get('markets', {}).get('overall_sentiment', 0),
                'manufacturing': economic_sentiment.get('manufacturing', {}).get('overall_sentiment', 0),
                'services': economic_sentiment.get('retail', {}).get('overall_sentiment', 0)
            },

            # Other required fields
            'macro_sentiment': economic_sentiment.get('gdp', {}).get('overall_sentiment', 0),
            'employment': economic_sentiment.get('employment', {}).get('overall_sentiment', 0),
            'prices': economic_sentiment.get('inflation', {}).get('overall_sentiment', 0),
            'wages': topic_sentiment.get('wage_sentiment', {}).get('overall_sentiment', 0),
            'retail_sales': economic_sentiment.get('retail', {}).get('overall_sentiment', 0),
            'housing': economic_sentiment.get('housing', {}).get('overall_sentiment', 0),

            # Policy and trade
            'trade_sentiment': economic_sentiment.get('trade', {}).get('overall_sentiment', 0),
            'monetary_policy': economic_sentiment.get('monetary_policy', {}).get('overall_sentiment', 0),
            'regulatory_stability': 0,  # Would need more specific analysis
            'investment_incentives': 0,
            'plant_relocations': 0,
            'business_environment': economic_sentiment.get('markets', {}).get('overall_sentiment', 0),

            # Geopolitical risk (0-100 scale)
            'geopolitical_risk': max(0, min(100, 50 + geo_sentiment.get('negative_ratio', 0) * 100 - geo_sentiment.get('positive_ratio', 0) * 50))
        }

        # Prepare news data for GPR calculation
        news_data = []
        for article in geopolitical_news[:50]:  # Limit to recent 50
            news_data.append({
                'date': article.published_at,
                'text': f"{article.title} {article.description or ''}"
            })

        logger.info(f"Collected sentiment data from {sum(len(v) for v in economic_news.values())} economic articles")
        logger.info(f"Collected sentiment data from {sum(len(v) for v in commodity_news.values())} commodity articles")
        logger.info(f"Collected {len(geopolitical_news)} geopolitical risk articles")

        return {
            'sentiment_data': sentiment_data,
            'news_data': news_data,
            'raw_articles': {
                'economic': economic_news,
                'commodities': commodity_news,
                'geopolitical': geopolitical_news
            }
        }


# Export classes
__all__ = ['TheNewsAPIClient', 'NewsArticle', 'SentimentExtractor', 'collect_comprehensive_news_data']