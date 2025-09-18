"""
World Bank Data Provider
Fetches GDP growth data from World Bank API
"""

import json
import asyncio
import aiohttp
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import logging

logger = logging.getLogger(__name__)

CACHE_DIR = Path("sentiment_bot/cache/worldbank")
CACHE_TTL_DAYS = 7


class WorldBankProvider:
    """World Bank GDP data provider with caching"""

    def __init__(self):
        self.cache_dir = CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()

    def _get_cache_path(self, country: str, start_year: int, end_year: int) -> Path:
        """Get cache file path for country and year range"""
        return self.cache_dir / f"{country}_{start_year}_{end_year}.json"

    def _is_cache_valid(self, cache_path: Path) -> bool:
        """Check if cache file is still valid (within TTL)"""
        if not cache_path.exists():
            return False

        age = datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)
        return age < timedelta(days=CACHE_TTL_DAYS)

    async def get_gdp_growth(self, country: str, start_year: int, end_year: int) -> Optional[Dict]:
        """
        Get GDP growth data from World Bank

        Args:
            country: ISO3 country code
            start_year: Start year for data
            end_year: End year for data

        Returns:
            Dict with GDP growth data and cache metadata or None if unavailable
        """
        # Check cache first
        cache_path = self._get_cache_path(country, start_year, end_year)

        if self._is_cache_valid(cache_path):
            logger.info(f"📦 Loading World Bank data from cache for {country}")
            with open(cache_path, 'r') as f:
                cached_data = json.load(f)

            # Add cache metadata
            cache_age = datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)
            cached_data['_cache_info'] = {
                'source': 'cache',
                'provider': 'worldbank',
                'cached_at': datetime.fromtimestamp(cache_path.stat().st_mtime).isoformat(),
                'age_hours': round(cache_age.total_seconds() / 3600, 1),
                'offline_mode': True
            }

            return cached_data

        # Convert ISO3 to ISO2 for World Bank API
        iso2_map = {
            'USA': 'US', 'GBR': 'GB', 'DEU': 'DE', 'FRA': 'FR',
            'ITA': 'IT', 'JPN': 'JP', 'CAN': 'CA', 'CHN': 'CN',
            'IND': 'IN', 'BRA': 'BR', 'RUS': 'RU', 'ZAF': 'ZA',
            'KOR': 'KR', 'MEX': 'MX', 'AUS': 'AU', 'ESP': 'ES'
        }

        iso2 = iso2_map.get(country, country)

        # World Bank API endpoint
        url = f"https://api.worldbank.org/v2/country/{iso2}/indicator/NY.GDP.MKTP.KD.ZG"
        params = {
            'date': f'{start_year}:{end_year}',
            'format': 'json',
            'per_page': 50
        }

        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            logger.info(f"Fetching World Bank GDP data for {country} ({start_year}-{end_year})")

            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    # Process response
                    if data and len(data) > 1 and data[1]:
                        processed = {
                            'country': country,
                            'source': 'World Bank',
                            'indicator': 'GDP growth (annual %)',
                            'data': {},
                            'fetched_at': datetime.now().isoformat(),
                            '_cache_info': {
                                'source': 'live_api',
                                'provider': 'worldbank',
                                'fetched_at': datetime.now().isoformat(),
                                'age_hours': 0.0,
                                'offline_mode': False
                            }
                        }

                        for item in data[1]:
                            if item.get('date') and item.get('value') is not None:
                                year = int(item['date'])
                                processed['data'][year] = float(item['value'])

                        # Cache the result (without cache metadata)
                        cache_data = {k: v for k, v in processed.items() if k != '_cache_info'}
                        with open(cache_path, 'w') as f:
                            json.dump(cache_data, f, indent=2)

                        logger.info(f"🌐 Fetched fresh World Bank data for {country}")
                        return processed
                    else:
                        logger.warning(f"No World Bank data available for {country}")
                        return None
                else:
                    logger.error(f"World Bank API error {response.status} for {country}")
                    return None

        except Exception as e:
            logger.error(f"Error fetching World Bank data for {country}: {e}")
            return None

    def get_gdp_growth_sync(self, country: str, start_year: int, end_year: int) -> Optional[Dict]:
        """Synchronous wrapper for get_gdp_growth"""
        async def _fetch():
            async with WorldBankProvider() as provider:
                return await provider.get_gdp_growth(country, start_year, end_year)

        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(_fetch())
        except RuntimeError:
            # Create new event loop if none exists
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(_fetch())
            finally:
                loop.close()


# Convenience functions
async def get_gdp_growth(country: str, start_year: int, end_year: int) -> Optional[Dict]:
    """Get GDP growth data from World Bank (async)"""
    async with WorldBankProvider() as provider:
        return await provider.get_gdp_growth(country, start_year, end_year)


def get_gdp_growth_sync(country: str, start_year: int, end_year: int) -> Optional[Dict]:
    """Get GDP growth data from World Bank (sync)"""
    provider = WorldBankProvider()
    return provider.get_gdp_growth_sync(country, start_year, end_year)


# For backwards compatibility
get_gdp_growth = get_gdp_growth_sync  # Default to sync version for CLI