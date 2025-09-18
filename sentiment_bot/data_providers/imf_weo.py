"""
IMF World Economic Outlook Data Provider
Fetches real GDP growth projections from IMF WEO DataMapper
"""

import json
import asyncio
import aiohttp
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)

CACHE_DIR = Path("sentiment_bot/cache/imf_weo")
CACHE_TTL_DAYS = 7


class IMFWEOProvider:
    """IMF WEO data provider with caching"""

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

    def _get_cache_path(self, country: str) -> Path:
        """Get cache file path for country"""
        return self.cache_dir / f"{country}_ngdp_rpch.json"

    def _is_cache_valid(self, cache_path: Path) -> bool:
        """Check if cache file is still valid (within TTL)"""
        if not cache_path.exists():
            return False

        age = datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)
        return age < timedelta(days=CACHE_TTL_DAYS)

    async def get_real_gdp_growth(self, country: str) -> Optional[Dict]:
        """
        Get real GDP growth projections from IMF WEO

        Args:
            country: ISO3 country code

        Returns:
            Dict with GDP growth projections or None if unavailable
        """
        # Check cache first
        cache_path = self._get_cache_path(country)

        if self._is_cache_valid(cache_path):
            logger.info(f"Loading IMF WEO data from cache for {country}")
            with open(cache_path, 'r') as f:
                return json.load(f)

        # IMF WEO DataMapper API endpoint
        url = f"https://www.imf.org/external/datamapper/api/v1/NGDP_RPCH/{country}"

        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            logger.info(f"Fetching IMF WEO real GDP growth for {country}")

            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()

                    # Process response
                    if 'values' in data and 'NGDP_RPCH' in data['values']:
                        country_data = data['values']['NGDP_RPCH'].get(country, {})

                        if country_data:
                            processed = {
                                'country': country,
                                'source': 'IMF WEO',
                                'indicator': 'Real GDP growth (annual %)',
                                'data': {},
                                'vintage': data.get('vintage', 'unknown'),
                                'fetched_at': datetime.now().isoformat()
                            }

                            # Convert string years to integers
                            for year_str, value in country_data.items():
                                if value is not None:
                                    try:
                                        year = int(year_str)
                                        processed['data'][year] = float(value)
                                    except (ValueError, TypeError):
                                        continue

                            # Cache the result
                            with open(cache_path, 'w') as f:
                                json.dump(processed, f, indent=2)

                            logger.info(f"Cached IMF WEO data for {country}")
                            return processed
                        else:
                            logger.warning(f"No IMF WEO data available for {country}")
                            return None
                    else:
                        logger.warning(f"Invalid IMF WEO response format for {country}")
                        return None
                else:
                    logger.error(f"IMF WEO API error {response.status} for {country}")
                    return None

        except Exception as e:
            logger.error(f"Error fetching IMF WEO data for {country}: {e}")
            return None

    def get_real_gdp_growth_sync(self, country: str) -> Optional[Dict]:
        """Synchronous wrapper for get_real_gdp_growth"""
        async def _fetch():
            async with IMFWEOProvider() as provider:
                return await provider.get_real_gdp_growth(country)

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
async def get_real_gdp_growth(country: str) -> Optional[Dict]:
    """Get real GDP growth from IMF WEO (async)"""
    async with IMFWEOProvider() as provider:
        return await provider.get_real_gdp_growth(country)


def get_real_gdp_growth_sync(country: str) -> Optional[Dict]:
    """Get real GDP growth from IMF WEO (sync)"""
    provider = IMFWEOProvider()
    return provider.get_real_gdp_growth_sync(country)


# For backwards compatibility
get_real_gdp_growth = get_real_gdp_growth_sync  # Default to sync version for CLI