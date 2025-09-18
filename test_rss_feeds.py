#!/usr/bin/env python3
"""
RSS Feed Connectivity Test
Tests if RSS feeds are working and retrieving data
"""

import requests
import feedparser
import yaml
import time
import json
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_rss_feed(url, timeout=10):
    """Test a single RSS feed"""
    try:
        # Test HTTP connectivity
        response = requests.get(url, timeout=timeout, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; RSS-Checker/1.0)'
        })

        if response.status_code != 200:
            return {
                'url': url,
                'status': 'failed',
                'error': f'HTTP {response.status_code}',
                'articles': 0
            }

        # Parse RSS feed
        feed = feedparser.parse(response.content)

        if feed.bozo:
            return {
                'url': url,
                'status': 'warning',
                'error': f'Parse error: {feed.bozo_exception}',
                'articles': len(feed.entries)
            }

        return {
            'url': url,
            'status': 'success',
            'articles': len(feed.entries),
            'title': feed.feed.get('title', 'Unknown'),
            'last_updated': feed.feed.get('updated', 'Unknown'),
            'sample_titles': [entry.title for entry in feed.entries[:3]]
        }

    except requests.exceptions.Timeout:
        return {
            'url': url,
            'status': 'failed',
            'error': 'Timeout',
            'articles': 0
        }
    except Exception as e:
        return {
            'url': url,
            'status': 'failed',
            'error': str(e),
            'articles': 0
        }

def test_rss_feeds_from_config():
    """Test RSS feeds from the master sources config"""

    # Load config
    with open('config/master_sources.yaml', 'r') as f:
        config = yaml.safe_load(f)

    results = {
        'timestamp': datetime.now().isoformat(),
        'total_sources': len(config['sources']),
        'total_feeds': 0,
        'successful_feeds': 0,
        'failed_feeds': 0,
        'sources': []
    }

    logger.info(f"Testing {len(config['sources'])} sources...")

    for source in config['sources']:
        source_result = {
            'domain': source['domain'],
            'country': source['country'],
            'region': source['region'],
            'feeds': []
        }

        for rss_url in source.get('rss_endpoints', []):
            results['total_feeds'] += 1
            logger.info(f"Testing {rss_url}...")

            feed_result = test_rss_feed(rss_url)
            source_result['feeds'].append(feed_result)

            if feed_result['status'] == 'success':
                results['successful_feeds'] += 1
            else:
                results['failed_feeds'] += 1

            # Small delay to be respectful
            time.sleep(0.5)

        results['sources'].append(source_result)

    return results

def main():
    """Main function"""
    logger.info("Starting RSS feed connectivity test...")

    results = test_rss_feeds_from_config()

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"rss_test_results_{timestamp}.json"

    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)

    # Print summary
    print(f"\n=== RSS Feed Test Results ===")
    print(f"Total Sources: {results['total_sources']}")
    print(f"Total Feeds: {results['total_feeds']}")
    print(f"Successful: {results['successful_feeds']}")
    print(f"Failed: {results['failed_feeds']}")
    print(f"Success Rate: {(results['successful_feeds']/results['total_feeds']*100):.1f}%")

    # Show some working feeds
    print(f"\n=== Working Feeds Sample ===")
    working_count = 0
    for source in results['sources']:
        for feed in source['feeds']:
            if feed['status'] == 'success' and working_count < 5:
                print(f"✓ {feed['url']}")
                print(f"  Articles: {feed['articles']}")
                print(f"  Title: {feed.get('title', 'N/A')}")
                if feed.get('sample_titles'):
                    print(f"  Sample: {feed['sample_titles'][0][:60]}...")
                print()
                working_count += 1

    # Show failed feeds
    print(f"\n=== Failed Feeds ===")
    failed_count = 0
    for source in results['sources']:
        for feed in source['feeds']:
            if feed['status'] == 'failed' and failed_count < 5:
                print(f"✗ {feed['url']}")
                print(f"  Error: {feed['error']}")
                print()
                failed_count += 1

    print(f"Results saved to: {output_file}")

if __name__ == "__main__":
    main()