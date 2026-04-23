"""
Comprehensive Data Connectors - EVERYTHING
Scrapes: Financial Reports, Property Data, Weather, Earnings, Filings, Crisis Data, etc.
"""

import aiohttp
import feedparser
import asyncio
from typing import AsyncGenerator, Dict, Any, List
from datetime import datetime, timedelta
import re
import json
from bs4 import BeautifulSoup


class SECFilingsConnector:
    """SEC EDGAR - Corporate filings, 10-K, 10-Q, 8-K, earnings reports"""

    def __init__(self, ticker: str = None, form_types: List[str] = None):
        self.ticker = ticker
        self.form_types = form_types or ['10-K', '10-Q', '8-K', 'DEF 14A']
        self.base_url = "https://www.sec.gov"
        self.headers = {
            'User-Agent': 'BRG Research Bot research@brg.com',
            'Accept-Encoding': 'gzip, deflate',
            'Host': 'www.sec.gov'
        }

    async def fetch(self) -> AsyncGenerator[Dict[str, Any], None]:
        """Fetch SEC filings"""
        async with aiohttp.ClientSession(headers=self.headers) as session:
            if self.ticker:
                # Company-specific filings
                url = f"{self.base_url}/cgi-bin/browse-edgar?action=getcompany&CIK={self.ticker}&type=&dateb=&owner=exclude&count=100&output=atom"
            else:
                # Recent filings across all companies
                url = f"{self.base_url}/cgi-bin/browse-edgar?action=getcurrent&CIK=&type=&company=&dateb=&owner=exclude&start=0&count=100&output=atom"

            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        content = await response.text()
                        feed = feedparser.parse(content)

                        for entry in feed.entries:
                            filing_type = entry.get('filing-type', 'Unknown')
                            if self.form_types and filing_type not in self.form_types:
                                continue

                            yield {
                                'source': 'SEC EDGAR',
                                'type': 'financial_filing',
                                'filing_type': filing_type,
                                'company': entry.get('filing-name', 'Unknown'),
                                'title': entry.get('title', ''),
                                'link': entry.get('filing-href', entry.get('link', '')),
                                'date': entry.get('updated', entry.get('published', '')),
                                'summary': entry.get('summary', ''),
                                'timestamp': datetime.now().isoformat()
                            }
            except Exception as e:
                print(f"SEC filings error: {e}")


class EarningsCallsConnector:
    """Earnings calls transcripts and schedules"""

    def __init__(self, ticker: str = None):
        self.ticker = ticker

    async def fetch(self) -> AsyncGenerator[Dict[str, Any], None]:
        """Fetch earnings call information"""
        # Seeking Alpha earnings calendar
        urls = [
            "https://seekingalpha.com/earnings/earnings-calendar",
            "https://www.earningswhispers.com/calendar"
        ]

        async with aiohttp.ClientSession() as session:
            for url in urls:
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status == 200:
                            html = await response.text()
                            soup = BeautifulSoup(html, 'html.parser')

                            # Parse earnings calendar
                            yield {
                                'source': 'Earnings Calendar',
                                'type': 'earnings_call',
                                'title': f'Earnings Calendar Update - {datetime.now().date()}',
                                'link': url,
                                'date': datetime.now().isoformat(),
                                'summary': 'Latest earnings calls and schedules',
                                'timestamp': datetime.now().isoformat()
                            }
                except Exception as e:
                    print(f"Earnings calendar error: {e}")


class PropertyDataConnector:
    """Property market data - prices, listings, market trends"""

    def __init__(self, location: str = "national"):
        self.location = location

    async def fetch(self) -> AsyncGenerator[Dict[str, Any], None]:
        """Fetch property market data"""
        # RSS feeds for property data
        feeds = [
            ("Zillow Research", "https://www.zillow.com/research/feed/"),
            ("Redfin Data", "https://www.redfin.com/blog/feed/"),
            ("Realtor.com News", "https://www.realtor.com/research/feed/"),
            ("HousingWire", "https://www.housingwire.com/feed/"),
            ("Apartment List", "https://www.apartmentlist.com/renter-life/feed"),
        ]

        async with aiohttp.ClientSession() as session:
            for source, url in feeds:
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status == 200:
                            content = await response.text()
                            feed = feedparser.parse(content)

                            for entry in feed.entries[:20]:
                                yield {
                                    'source': source,
                                    'type': 'property_market',
                                    'title': entry.get('title', ''),
                                    'link': entry.get('link', ''),
                                    'date': entry.get('published', ''),
                                    'summary': entry.get('summary', ''),
                                    'location': self.location,
                                    'timestamp': datetime.now().isoformat()
                                }
                except Exception as e:
                    print(f"Property data error for {source}: {e}")


class WeatherCrisisConnector:
    """Weather alerts, natural disasters, crisis information"""

    def __init__(self, region: str = "US"):
        self.region = region

    async def fetch(self) -> AsyncGenerator[Dict[str, Any], None]:
        """Fetch weather and crisis data"""
        feeds = [
            ("NOAA Alerts", "https://alerts.weather.gov/cap/us.php?x=1"),
            ("USGS Earthquakes", "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.atom"),
            ("NASA Earth", "https://www.nasa.gov/rss/dyn/breaking_news.rss"),
            ("FEMA News", "https://www.fema.gov/about/news-multimedia/news/rss.xml"),
            ("CDC Emergency", "https://tools.cdc.gov/podcasts/rss.asp?c=19"),
            ("WHO Outbreaks", "https://www.who.int/rss-feeds/news-english.xml"),
            ("ReliefWeb Disasters", "https://reliefweb.int/disasters/feed"),
        ]

        async with aiohttp.ClientSession() as session:
            for source, url in feeds:
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status == 200:
                            content = await response.text()
                            feed = feedparser.parse(content)

                            for entry in feed.entries[:30]:
                                # Determine severity
                                title_lower = entry.get('title', '').lower()
                                severity = 'HIGH' if any(word in title_lower for word in
                                    ['emergency', 'alert', 'warning', 'disaster', 'earthquake', 'tsunami', 'hurricane']) else 'MEDIUM'

                                yield {
                                    'source': source,
                                    'type': 'crisis_alert',
                                    'severity': severity,
                                    'title': entry.get('title', ''),
                                    'link': entry.get('link', ''),
                                    'date': entry.get('published', ''),
                                    'summary': entry.get('summary', '')[:500],
                                    'region': self.region,
                                    'timestamp': datetime.now().isoformat()
                                }
                except Exception as e:
                    print(f"Crisis data error for {source}: {e}")


class FinancialNewsConnector:
    """Financial news from major outlets"""

    def __init__(self, topic: str = "markets"):
        self.topic = topic

    async def fetch(self) -> AsyncGenerator[Dict[str, Any], None]:
        """Fetch financial news"""
        feeds = [
            ("Bloomberg Markets", "https://feeds.bloomberg.com/markets/news.rss"),
            ("Bloomberg Politics", "https://feeds.bloomberg.com/politics/news.rss"),
            ("Bloomberg Technology", "https://feeds.bloomberg.com/technology/news.rss"),
            ("Reuters Business", "https://www.reuters.com/rssFeed/businessNews"),
            ("Reuters Markets", "https://www.reuters.com/rssFeed/marketsNews"),
            ("WSJ Markets", "https://feeds.wsj.com/wsj/xml/rss/3_7041.xml"),
            ("FT Companies", "https://www.ft.com/companies?format=rss"),
            ("FT Markets", "https://www.ft.com/markets?format=rss"),
            ("MarketWatch", "http://feeds.marketwatch.com/marketwatch/topstories/"),
            ("Barron's", "https://www.barrons.com/rss"),
            ("Seeking Alpha", "https://seekingalpha.com/feed.xml"),
            ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
        ]

        async with aiohttp.ClientSession() as session:
            for source, url in feeds:
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status == 200:
                            content = await response.text()
                            feed = feedparser.parse(content)

                            for entry in feed.entries[:25]:
                                yield {
                                    'source': source,
                                    'type': 'financial_news',
                                    'title': entry.get('title', ''),
                                    'link': entry.get('link', ''),
                                    'date': entry.get('published', ''),
                                    'summary': entry.get('summary', ''),
                                    'topic': self.topic,
                                    'timestamp': datetime.now().isoformat()
                                }
                except Exception as e:
                    print(f"Financial news error for {source}: {e}")


class CryptoDataConnector:
    """Cryptocurrency data, news, prices, blockchain updates"""

    def __init__(self):
        pass

    async def fetch(self) -> AsyncGenerator[Dict[str, Any], None]:
        """Fetch crypto data"""
        feeds = [
            ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
            ("CoinTelegraph", "https://cointelegraph.com/rss"),
            ("Bitcoin Magazine", "https://bitcoinmagazine.com/feed"),
            ("Decrypt", "https://decrypt.co/feed"),
            ("The Block", "https://www.theblockcrypto.com/rss.xml"),
            ("CryptoSlate", "https://cryptoslate.com/feed/"),
        ]

        async with aiohttp.ClientSession() as session:
            for source, url in feeds:
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status == 200:
                            content = await response.text()
                            feed = feedparser.parse(content)

                            for entry in feed.entries[:20]:
                                yield {
                                    'source': source,
                                    'type': 'crypto_news',
                                    'title': entry.get('title', ''),
                                    'link': entry.get('link', ''),
                                    'date': entry.get('published', ''),
                                    'summary': entry.get('summary', ''),
                                    'timestamp': datetime.now().isoformat()
                                }
                except Exception as e:
                    print(f"Crypto data error for {source}: {e}")


class CommoditiesDataConnector:
    """Commodities prices, energy, agriculture, metals"""

    def __init__(self):
        pass

    async def fetch(self) -> AsyncGenerator[Dict[str, Any], None]:
        """Fetch commodities data"""
        feeds = [
            ("Oil Price", "https://oilprice.com/rss/main"),
            ("Kitco Gold", "https://www.kitco.com/rss/"),
            ("Agri Business", "https://www.agribusinessglobal.com/feed/"),
            ("Mining.com", "https://www.mining.com/feed/"),
            ("Metals Daily", "https://www.metalsdaily.com/live-prices/feed/"),
        ]

        async with aiohttp.ClientSession() as session:
            for source, url in feeds:
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status == 200:
                            content = await response.text()
                            feed = feedparser.parse(content)

                            for entry in feed.entries[:15]:
                                yield {
                                    'source': source,
                                    'type': 'commodities',
                                    'title': entry.get('title', ''),
                                    'link': entry.get('link', ''),
                                    'date': entry.get('published', ''),
                                    'summary': entry.get('summary', ''),
                                    'timestamp': datetime.now().isoformat()
                                }
                except Exception as e:
                    print(f"Commodities error for {source}: {e}")


class GovernmentDataConnector:
    """Government announcements, policy updates, regulations"""

    def __init__(self, country: str = "US"):
        self.country = country

    async def fetch(self) -> AsyncGenerator[Dict[str, Any], None]:
        """Fetch government data"""
        feeds = [
            ("Federal Reserve", "https://www.federalreserve.gov/feeds/press_all.xml"),
            ("Treasury", "https://home.treasury.gov/rss/press-releases"),
            ("White House", "https://www.whitehouse.gov/feed/"),
            ("Federal Register", "https://www.federalregister.gov/documents/search.rss"),
            ("SEC News", "https://www.sec.gov/news/pressreleases.rss"),
            ("FDIC News", "https://www.fdic.gov/news/feed/"),
            ("Congress.gov", "https://www.congress.gov/rss/most-viewed-bills.xml"),
        ]

        async with aiohttp.ClientSession() as session:
            for source, url in feeds:
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status == 200:
                            content = await response.text()
                            feed = feedparser.parse(content)

                            for entry in feed.entries[:20]:
                                yield {
                                    'source': source,
                                    'type': 'government_update',
                                    'title': entry.get('title', ''),
                                    'link': entry.get('link', ''),
                                    'date': entry.get('published', ''),
                                    'summary': entry.get('summary', ''),
                                    'country': self.country,
                                    'timestamp': datetime.now().isoformat()
                                }
                except Exception as e:
                    print(f"Government data error for {source}: {e}")


class CorporateFilingsConnector:
    """Corporate press releases, announcements, updates"""

    def __init__(self):
        pass

    async def fetch(self) -> AsyncGenerator[Dict[str, Any], None]:
        """Fetch corporate announcements"""
        feeds = [
            ("PR Newswire", "https://www.prnewswire.com/rss/news-releases-list.rss"),
            ("Business Wire", "https://www.businesswire.com/portal/site/home/news/"),
            ("GlobeNewswire", "https://www.globenewswire.com/RssFeed/subjectcode/10-0/feedTitle/GlobeNewswire%20-%20Financial%20Services"),
        ]

        async with aiohttp.ClientSession() as session:
            for source, url in feeds:
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status == 200:
                            content = await response.text()
                            feed = feedparser.parse(content)

                            for entry in feed.entries[:25]:
                                yield {
                                    'source': source,
                                    'type': 'corporate_announcement',
                                    'title': entry.get('title', ''),
                                    'link': entry.get('link', ''),
                                    'date': entry.get('published', ''),
                                    'summary': entry.get('summary', ''),
                                    'timestamp': datetime.now().isoformat()
                                }
                except Exception as e:
                    print(f"Corporate filings error for {source}: {e}")


class ResearchReportsConnector:
    """Academic research, think tanks, economic reports"""

    def __init__(self):
        pass

    async def fetch(self) -> AsyncGenerator[Dict[str, Any], None]:
        """Fetch research reports"""
        feeds = [
            ("IMF Publications", "https://www.imf.org/en/Publications/rss"),
            ("World Bank", "https://www.worldbank.org/en/news/rss"),
            ("OECD", "https://www.oecd.org/rss/publicationrss.xml"),
            ("BIS", "https://www.bis.org/rss/speeches.rss"),
            ("NBER", "https://www.nber.org/rss/new.xml"),
            ("Brookings", "https://www.brookings.edu/feed/"),
            ("Peterson Institute", "https://www.piie.com/rss/xml"),
        ]

        async with aiohttp.ClientSession() as session:
            for source, url in feeds:
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status == 200:
                            content = await response.text()
                            feed = feedparser.parse(content)

                            for entry in feed.entries[:15]:
                                yield {
                                    'source': source,
                                    'type': 'research_report',
                                    'title': entry.get('title', ''),
                                    'link': entry.get('link', ''),
                                    'date': entry.get('published', ''),
                                    'summary': entry.get('summary', ''),
                                    'timestamp': datetime.now().isoformat()
                                }
                except Exception as e:
                    print(f"Research reports error for {source}: {e}")


# Comprehensive aggregator
class ComprehensiveDataAggregator:
    """Aggregates ALL data types from all connectors"""

    def __init__(self):
        self.connectors = [
            ('SEC Filings', SECFilingsConnector()),
            ('Earnings', EarningsCallsConnector()),
            ('Property', PropertyDataConnector()),
            ('Weather/Crisis', WeatherCrisisConnector()),
            ('Financial News', FinancialNewsConnector()),
            ('Crypto', CryptoDataConnector()),
            ('Commodities', CommoditiesDataConnector()),
            ('Government', GovernmentDataConnector()),
            ('Corporate', CorporateFilingsConnector()),
            ('Research', ResearchReportsConnector()),
        ]

    async def fetch_all(self) -> Dict[str, List[Dict[str, Any]]]:
        """Fetch from all connectors simultaneously"""
        results = {
            'financial_filings': [],
            'earnings': [],
            'property': [],
            'crisis': [],
            'financial_news': [],
            'crypto': [],
            'commodities': [],
            'government': [],
            'corporate': [],
            'research': [],
        }

        tasks = []
        for name, connector in self.connectors:
            tasks.append(self._fetch_connector(name, connector, results))

        await asyncio.gather(*tasks)

        return results

    async def _fetch_connector(self, name: str, connector, results: dict):
        """Fetch from a single connector"""
        try:
            items = []
            async for item in connector.fetch():
                items.append(item)

            # Categorize by type
            item_type = items[0]['type'] if items else 'unknown'
            if 'financial_filing' in item_type or 'sec' in name.lower():
                results['financial_filings'].extend(items)
            elif 'earnings' in item_type:
                results['earnings'].extend(items)
            elif 'property' in item_type:
                results['property'].extend(items)
            elif 'crisis' in item_type or 'weather' in name.lower():
                results['crisis'].extend(items)
            elif 'financial_news' in item_type:
                results['financial_news'].extend(items)
            elif 'crypto' in item_type:
                results['crypto'].extend(items)
            elif 'commodities' in item_type:
                results['commodities'].extend(items)
            elif 'government' in item_type:
                results['government'].extend(items)
            elif 'corporate' in item_type:
                results['corporate'].extend(items)
            elif 'research' in item_type:
                results['research'].extend(items)

            print(f"[{name}] Fetched {len(items)} items")

        except Exception as e:
            print(f"Error fetching {name}: {e}")
