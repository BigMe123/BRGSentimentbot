#!/usr/bin/env python3
"""
RSS Validator - Tests RSS feeds for 404/SSL errors and removes broken ones
==========================================================================
Validates RSS endpoints and automatically removes broken feeds from master sources.
"""

import requests
import feedparser
import yaml
import logging
import ssl
from typing import Dict, List, Tuple, Any
from pathlib import Path
from urllib3.exceptions import SSLError
from requests.exceptions import SSLError as RequestsSSLError, ConnectionError, Timeout, HTTPError
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


class RSSValidator:
    """Validates RSS feeds and removes broken ones from master sources."""

    def __init__(self, config_path: str = "config/master_sources.yaml"):
        self.config_path = Path(config_path)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'BSG-RSS-Validator/1.0 (Mozilla/5.0 compatible)'
        })
        # Set shorter timeouts for validation
        self.timeout = 10

    def test_rss_feed(self, url: str, domain: str = None) -> Tuple[bool, str]:
        """
        Test a single RSS feed for accessibility.

        Returns:
            Tuple[bool, str]: (is_working, error_message)
        """
        try:
            # First try with requests
            response = self.session.get(url, timeout=self.timeout, verify=False)

            if response.status_code == 404:
                return False, "HTTP 404 Not Found"
            elif response.status_code == 403:
                return False, "HTTP 403 Forbidden"
            elif response.status_code >= 400:
                return False, f"HTTP {response.status_code}"
            elif response.status_code == 200:
                # Try to parse with feedparser to ensure it's valid RSS
                feed = feedparser.parse(response.content)
                if hasattr(feed, 'bozo') and feed.bozo:
                    # Check if it's a critical error
                    if 'not well-formed' in str(feed.bozo_exception).lower():
                        return False, "Invalid RSS format"

                # Check if feed has entries or at least basic structure
                if hasattr(feed, 'feed') and (feed.entries or feed.feed):
                    return True, "OK"
                else:
                    return False, "Empty or invalid RSS feed"
            else:
                return False, f"HTTP {response.status_code}"

        except (RequestsSSLError, SSLError, ssl.SSLError) as e:
            if "certificate verify failed" in str(e).lower():
                return False, "SSL certificate expired/invalid"
            elif "ssl" in str(e).lower():
                return False, "SSL connection failed"
            else:
                return False, f"SSL Error: {str(e)[:50]}"

        except (ConnectionError, Timeout) as e:
            return False, f"Connection failed: {str(e)[:50]}"

        except Exception as e:
            return False, f"Error: {str(e)[:50]}"

    def validate_country_sources(self, country: str, remove_broken: bool = False) -> Dict[str, Any]:
        """
        Validate RSS sources for a specific country.

        Args:
            country: Country name to filter sources
            remove_broken: If True, remove broken feeds from config

        Returns:
            Dict with validation results
        """
        print(f"🔍 Loading sources for {country}...")

        # Load current sources
        sources_data = self._load_sources()
        if not sources_data:
            return {"working": 0, "broken": 0, "total": 0, "removed": 0, "broken_details": {}}

        # Find country-specific sources
        country_sources = []
        for source in sources_data.get('sources', []):
            if source.get('country', '').lower() == country.lower():
                country_sources.append(source)

        print(f"📊 Found {len(country_sources)} sources for {country}")

        # Validate RSS endpoints
        working = 0
        broken = 0
        broken_details = {}
        sources_to_remove = []

        for source in country_sources:
            domain = source.get('domain', 'unknown')
            rss_endpoints = source.get('rss_endpoints', [])

            if not rss_endpoints:
                continue

            print(f"\n📡 Testing {domain}...")

            working_endpoints = []
            for endpoint in rss_endpoints:
                is_working, error = self.test_rss_feed(endpoint, domain)

                if is_working:
                    print(f"  ✅ {endpoint}")
                    working += 1
                    working_endpoints.append(endpoint)
                else:
                    print(f"  ❌ {endpoint}: {error}")
                    broken += 1
                    broken_details[endpoint] = error

            # If no endpoints work, mark source for removal
            if not working_endpoints and remove_broken:
                sources_to_remove.append(source)
            elif working_endpoints != rss_endpoints and remove_broken:
                # Update source with only working endpoints
                source['rss_endpoints'] = working_endpoints

        # Remove broken sources if requested
        removed_count = 0
        if remove_broken and sources_to_remove:
            removed_count = len(sources_to_remove)
            sources_data['sources'] = [
                s for s in sources_data['sources']
                if s not in sources_to_remove
            ]

            # Update total source count
            sources_data['total_sources'] = len(sources_data['sources'])

            # Save updated config
            self._save_sources(sources_data)
            print(f"\n🗑️  Removed {removed_count} broken sources from config")

        return {
            "working": working,
            "broken": broken,
            "total": working + broken,
            "removed": removed_count,
            "broken_details": broken_details
        }

    def validate_all_sources(self, remove_broken: bool = False, max_workers: int = 10) -> Dict[str, Any]:
        """
        Validate all RSS sources in the config.

        Args:
            remove_broken: If True, remove broken feeds from config
            max_workers: Number of concurrent validation threads

        Returns:
            Dict with validation results
        """
        print("🔍 Loading all sources...")

        # Load current sources
        sources_data = self._load_sources()
        if not sources_data:
            return {"working": 0, "broken": 0, "total": 0, "removed": 0, "broken_details": {}}

        # Collect all RSS endpoints
        all_endpoints = []
        source_map = {}  # endpoint -> source mapping

        for source in sources_data.get('sources', []):
            domain = source.get('domain', 'unknown')
            rss_endpoints = source.get('rss_endpoints', [])

            for endpoint in rss_endpoints:
                all_endpoints.append((endpoint, domain, source))
                source_map[endpoint] = source

        print(f"📊 Found {len(all_endpoints)} RSS endpoints across {len(sources_data.get('sources', []))} sources")

        if not all_endpoints:
            return {"working": 0, "broken": 0, "total": 0, "removed": 0, "broken_details": {}}

        # Validate endpoints in parallel
        working = 0
        broken = 0
        broken_details = {}
        broken_endpoints = set()

        print(f"🚀 Starting validation with {max_workers} workers...")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all validation tasks
            future_to_endpoint = {
                executor.submit(self.test_rss_feed, endpoint, domain): (endpoint, domain, source)
                for endpoint, domain, source in all_endpoints
            }

            # Process results as they complete
            for i, future in enumerate(as_completed(future_to_endpoint), 1):
                endpoint, domain, source = future_to_endpoint[future]

                try:
                    is_working, error = future.result()

                    if is_working:
                        working += 1
                        if i % 50 == 0:  # Progress update every 50 feeds
                            print(f"✅ Progress: {i}/{len(all_endpoints)} ({working} working, {broken} broken)")
                    else:
                        broken += 1
                        broken_details[endpoint] = error
                        broken_endpoints.add(endpoint)
                        if i % 10 == 0:  # Show broken feeds more frequently
                            print(f"❌ {domain}: {endpoint} - {error}")

                except Exception as e:
                    broken += 1
                    broken_details[endpoint] = f"Validation error: {str(e)[:50]}"
                    broken_endpoints.add(endpoint)

        # Remove broken sources if requested
        removed_count = 0
        if remove_broken and broken_endpoints:
            print(f"\n🗑️  Removing broken RSS feeds...")

            sources_to_remove = []
            for source in sources_data.get('sources', []):
                rss_endpoints = source.get('rss_endpoints', [])
                if not rss_endpoints:
                    continue

                # Filter out broken endpoints
                working_endpoints = [ep for ep in rss_endpoints if ep not in broken_endpoints]

                if not working_endpoints:
                    # No working endpoints, remove entire source
                    sources_to_remove.append(source)
                    removed_count += 1
                elif len(working_endpoints) != len(rss_endpoints):
                    # Some endpoints broken, update source
                    source['rss_endpoints'] = working_endpoints

            # Remove sources with no working endpoints
            if sources_to_remove:
                sources_data['sources'] = [
                    s for s in sources_data['sources']
                    if s not in sources_to_remove
                ]

                # Update total source count
                sources_data['total_sources'] = len(sources_data['sources'])

                # Save updated config
                self._save_sources(sources_data)
                print(f"🗑️  Removed {removed_count} sources with no working RSS feeds")

        return {
            "working": working,
            "broken": broken,
            "total": working + broken,
            "removed": removed_count,
            "broken_details": broken_details
        }

    def _load_sources(self) -> Dict[str, Any]:
        """Load sources from YAML config."""
        if not self.config_path.exists():
            logger.error(f"Config file not found: {self.config_path}")
            return {}

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return {}

    def _save_sources(self, sources_data: Dict[str, Any]) -> bool:
        """Save sources to YAML config."""
        try:
            # Create backup
            backup_path = self.config_path.with_suffix('.yaml.backup')
            if self.config_path.exists():
                import shutil
                shutil.copy2(self.config_path, backup_path)
                print(f"📄 Backup saved to: {backup_path}")

            # Save updated config
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(sources_data, f, default_flow_style=False, sort_keys=False)

            print(f"💾 Updated config saved to: {self.config_path}")
            return True

        except Exception as e:
            logger.error(f"Error saving config: {e}")
            return False


def main():
    """Test the RSS validator."""
    print("🔍 RSS VALIDATOR TEST")
    print("=" * 40)

    validator = RSSValidator()

    # Test Liechtenstein sources
    print("\n🇱🇮 Testing Liechtenstein sources...")
    results = validator.validate_country_sources("Liechtenstein", remove_broken=False)

    print(f"\n📊 Results:")
    print(f"Working: {results['working']}")
    print(f"Broken: {results['broken']}")
    print(f"Total: {results['total']}")

    if results["broken_details"]:
        print(f"\n❌ Broken feeds:")
        for feed, error in results["broken_details"].items():
            print(f"  {feed}: {error}")


if __name__ == "__main__":
    main()