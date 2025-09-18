#!/usr/bin/env python
"""
Stable Scraper with Comprehensive Error Handling
Ensures failed endpoints don't crash the terminal
"""

import feedparser
import requests
import time
import logging
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
import random
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class StableScraper:
    """Robust scraping with error handling and retry logic"""
    
    def __init__(self, max_retries: int = 3, timeout: int = 10, max_workers: int = 10):
        self.max_retries = max_retries
        self.timeout = timeout
        self.max_workers = max_workers
        self.session = self._create_session()
        self.error_stats = {}
        self.success_stats = {}
        
    def _create_session(self) -> requests.Session:
        """Create a robust session with proper headers"""
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/rss+xml, application/xml, text/xml, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
        })
        return session
    
    def fetch_rss_safe(self, url: str) -> Tuple[bool, Optional[Dict], str]:
        """
        Safely fetch RSS feed with comprehensive error handling
        Returns: (success, data, error_message)
        """
        
        for attempt in range(self.max_retries):
            try:
                # Add jitter to avoid thundering herd
                if attempt > 0:
                    time.sleep(random.uniform(0.5, 2.0) * attempt)
                
                # Parse feed
                feed = feedparser.parse(
                    url, 
                    agent=self.session.headers['User-Agent'],
                    timeout=self.timeout
                )
                
                # Check for HTTP errors
                if hasattr(feed, 'status'):
                    if feed.status == 404:
                        return False, None, "Feed not found (404)"
                    elif feed.status == 403:
                        return False, None, "Access forbidden (403)"
                    elif feed.status >= 500:
                        if attempt < self.max_retries - 1:
                            continue  # Retry on server errors
                        return False, None, f"Server error ({feed.status})"
                
                # Check for parsing errors
                if feed.bozo:
                    # Some feeds have minor issues but are still usable
                    if hasattr(feed, 'entries') and feed.entries:
                        logger.warning(f"Feed has issues but is usable: {url}")
                    else:
                        return False, None, "Invalid feed format"
                
                # Extract articles
                articles = []
                for entry in feed.entries[:50]:  # Limit to 50 entries
                    try:
                        article = self._parse_entry(entry, url)
                        if article:
                            articles.append(article)
                    except Exception as e:
                        logger.debug(f"Failed to parse entry: {e}")
                        continue
                
                if articles:
                    self.success_stats[urlparse(url).netloc] = datetime.now()
                    return True, {'articles': articles, 'feed_info': feed.feed}, None
                else:
                    return False, None, "No valid articles found"
                    
            except requests.Timeout:
                if attempt < self.max_retries - 1:
                    continue
                return False, None, "Request timeout"
                
            except requests.ConnectionError:
                if attempt < self.max_retries - 1:
                    continue
                return False, None, "Connection error"
                
            except Exception as e:
                logger.debug(f"Unexpected error fetching {url}: {e}")
                if attempt < self.max_retries - 1:
                    continue
                return False, None, f"Error: {str(e)[:50]}"
        
        return False, None, "Max retries exceeded"
    
    def _parse_entry(self, entry: Dict, source_url: str) -> Optional[Dict]:
        """Parse a single RSS entry safely"""
        try:
            # Extract basic fields
            article = {
                'title': entry.get('title', ''),
                'url': entry.get('link', ''),
                'source': urlparse(source_url).netloc,
                'published_date': self._parse_date(entry),
                'description': self._extract_description(entry),
                'content': self._extract_content(entry),
            }
            
            # Validate required fields
            if not article['title'] or not article['url']:
                return None
            
            return article
            
        except Exception as e:
            logger.debug(f"Error parsing entry: {e}")
            return None
    
    def _parse_date(self, entry: Dict) -> Optional[datetime]:
        """Parse date from various formats"""
        date_fields = ['published_parsed', 'updated_parsed', 'created_parsed']
        
        for field in date_fields:
            if hasattr(entry, field) and getattr(entry, field):
                try:
                    return datetime.fromtimestamp(time.mktime(getattr(entry, field)))
                except:
                    continue
        
        # Try string parsing
        date_strings = ['published', 'updated', 'created']
        for field in date_strings:
            if field in entry and entry[field]:
                try:
                    # Simple ISO format attempt
                    return datetime.fromisoformat(entry[field].replace('Z', '+00:00'))
                except:
                    continue
        
        return datetime.now()  # Default to now if no date found
    
    def _extract_description(self, entry: Dict) -> str:
        """Extract description from various fields"""
        fields = ['summary', 'description', 'content']
        
        for field in fields:
            if field in entry:
                if isinstance(entry[field], str):
                    return entry[field][:1000]  # Limit length
                elif isinstance(entry[field], list) and entry[field]:
                    if isinstance(entry[field][0], dict):
                        return entry[field][0].get('value', '')[:1000]
                    else:
                        return str(entry[field][0])[:1000]
        
        return ""
    
    def _extract_content(self, entry: Dict) -> str:
        """Extract full content if available"""
        if 'content' in entry and isinstance(entry['content'], list):
            for content in entry['content']:
                if isinstance(content, dict) and 'value' in content:
                    return content['value'][:5000]  # Limit content length
        
        return self._extract_description(entry)  # Fall back to description
    
    def fetch_multiple_sources(self, sources: List[Dict], 
                             progress_callback=None) -> List[Dict]:
        """
        Fetch from multiple sources with parallel processing
        Won't crash if individual sources fail
        """
        all_articles = []
        total_sources = len(sources)
        completed = 0
        failed = 0
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_source = {}
            for source in sources:
                if 'rss_url' in source or 'url' in source:
                    url = source.get('rss_url', source.get('url'))
                    future = executor.submit(self.fetch_rss_safe, url)
                    future_to_source[future] = source
            
            # Process completed tasks
            for future in as_completed(future_to_source):
                source = future_to_source[future]
                completed += 1
                
                try:
                    success, data, error = future.result(timeout=self.timeout + 5)
                    
                    if success and data:
                        # Add source metadata to articles
                        for article in data.get('articles', []):
                            article['source_name'] = source.get('name', '')
                            article['source_region'] = source.get('region', '')
                            article['source_country'] = source.get('country', '')
                            all_articles.append(article)
                    else:
                        failed += 1
                        domain = source.get('domain', source.get('url', 'unknown'))
                        self.error_stats[domain] = error
                        logger.debug(f"Failed to fetch {domain}: {error}")
                    
                    # Progress callback
                    if progress_callback:
                        progress_callback(completed, total_sources, failed)
                        
                except Exception as e:
                    failed += 1
                    logger.warning(f"Task failed for source: {e}")
        
        logger.info(f"Fetched {len(all_articles)} articles from {completed-failed}/{total_sources} sources")
        return all_articles
    
    def get_error_report(self) -> Dict:
        """Get detailed error statistics"""
        return {
            'total_errors': len(self.error_stats),
            'error_types': self._categorize_errors(),
            'failed_domains': list(self.error_stats.keys())[:10],  # Top 10
            'success_rate': len(self.success_stats) / (len(self.success_stats) + len(self.error_stats))
            if (self.success_stats or self.error_stats) else 0
        }
    
    def _categorize_errors(self) -> Dict:
        """Categorize errors by type"""
        categories = {
            '404': 0,
            '403': 0,
            '5xx': 0,
            'timeout': 0,
            'connection': 0,
            'invalid_format': 0,
            'other': 0
        }
        
        for error in self.error_stats.values():
            error_lower = str(error).lower()
            if '404' in error:
                categories['404'] += 1
            elif '403' in error:
                categories['403'] += 1
            elif any(x in error for x in ['500', '502', '503', '504']):
                categories['5xx'] += 1
            elif 'timeout' in error_lower:
                categories['timeout'] += 1
            elif 'connection' in error_lower:
                categories['connection'] += 1
            elif 'invalid' in error_lower or 'format' in error_lower:
                categories['invalid_format'] += 1
            else:
                categories['other'] += 1
        
        return categories


def validate_source_before_use(source: Dict) -> bool:
    """Smoke test a source before adding to database"""
    scraper = StableScraper(max_retries=1, timeout=5)
    
    url = source.get('rss_url', source.get('url'))
    if not url:
        return False
    
    success, data, error = scraper.fetch_rss_safe(url)
    
    if success and data and data.get('articles'):
        return True
    
    logger.debug(f"Source validation failed for {url}: {error}")
    return False


# Integration with existing system
def create_stable_scraper_instance():
    """Factory function to create configured scraper"""
    return StableScraper(
        max_retries=3,
        timeout=10,
        max_workers=20  # Parallel fetching
    )