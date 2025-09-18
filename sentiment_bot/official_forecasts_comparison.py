"""
Official Forecasts Comparison Module
Compare model predictions against World Bank, IMF, and OECD consensus
"""

import json
import asyncio
import aiohttp
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from pathlib import Path
import statistics
from dataclasses import dataclass
from enum import Enum


class DataSource(Enum):
    WORLD_BANK = "World Bank"
    IMF = "IMF"
    OECD = "OECD"


@dataclass
class ForecastData:
    """Container for forecast data from a single source"""
    source: DataSource
    country: str
    year: int
    growth_rate: float
    vintage: str  # Release date/version
    confidence: Optional[float] = None


class OfficialForecastsComparison:
    """
    Fetch and compare GDP forecasts from official sources
    No API keys required - uses public endpoints
    """

    def __init__(self, cache_dir: str = "data/official_forecasts"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # ISO3 country code mapping
        self.country_codes = {
            'USA': 'US', 'GBR': 'GB', 'DEU': 'DE', 'FRA': 'FR',
            'ITA': 'IT', 'JPN': 'JP', 'CAN': 'CA', 'CHN': 'CN',
            'IND': 'IN', 'BRA': 'BR', 'RUS': 'RU', 'ZAF': 'ZA',
            'KOR': 'KR', 'MEX': 'MX', 'AUS': 'AU', 'ESP': 'ES'
        }

        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()

    async def fetch_world_bank(self, country: str, year: int) -> Optional[ForecastData]:
        """
        Fetch GDP growth data from World Bank API
        API: https://api.worldbank.org/v2/country/{country}/indicator/NY.GDP.MKTP.KD.ZG
        """
        try:
            # Convert ISO3 to ISO2 for World Bank
            iso2 = self.country_codes.get(country, country)

            # World Bank API endpoint (no key needed)
            url = f"https://api.worldbank.org/v2/country/{iso2}/indicator/NY.GDP.MKTP.KD.ZG"
            params = {
                'date': f'{year-2}:{year+2}',  # Get range around target year
                'format': 'json',
                'per_page': 50
            }

            # Check cache first
            cache_file = self.cache_dir / f"wb_{country}_{year}.json"
            if cache_file.exists():
                age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
                if age < timedelta(days=7):  # Use cache if less than 7 days old
                    with open(cache_file, 'r') as f:
                        data = json.load(f)
                        if data and len(data) > 1:
                            for item in data[1]:
                                if item.get('date') == str(year) and item.get('value'):
                                    return ForecastData(
                                        source=DataSource.WORLD_BANK,
                                        country=country,
                                        year=year,
                                        growth_rate=item['value'],
                                        vintage=datetime.now().strftime('%Y-%m-%d')
                                    )

            # Fetch fresh data
            if self.session:
                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()

                        # Cache the response
                        with open(cache_file, 'w') as f:
                            json.dump(data, f)

                        # Extract growth rate
                        if data and len(data) > 1:
                            for item in data[1]:
                                if item.get('date') == str(year) and item.get('value'):
                                    return ForecastData(
                                        source=DataSource.WORLD_BANK,
                                        country=country,
                                        year=year,
                                        growth_rate=item['value'],
                                        vintage=datetime.now().strftime('%Y-%m-%d')
                                    )

        except Exception as e:
            print(f"Error fetching World Bank data for {country}: {e}")

        return None

    async def fetch_imf(self, country: str, year: int) -> Optional[ForecastData]:
        """
        Fetch GDP growth projections from IMF WEO DataMapper
        Uses IMF's public API endpoint
        """
        try:
            # IMF WEO API endpoint (public, no key needed)
            # This uses the World Economic Outlook database
            url = f"https://www.imf.org/external/datamapper/api/v1/NGDP_RPCH/{country}"

            # Check cache
            cache_file = self.cache_dir / f"imf_{country}_{year}.json"
            if cache_file.exists():
                age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
                if age < timedelta(days=7):
                    with open(cache_file, 'r') as f:
                        data = json.load(f)
                        if country in data.get('values', {}).get('NGDP_RPCH', {}):
                            country_data = data['values']['NGDP_RPCH'][country]
                            if str(year) in country_data:
                                return ForecastData(
                                    source=DataSource.IMF,
                                    country=country,
                                    year=year,
                                    growth_rate=country_data[str(year)],
                                    vintage=data.get('vintage', datetime.now().strftime('%Y-%m-%d'))
                                )

            # Fetch fresh data
            if self.session:
                async with self.session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()

                        # Cache the response
                        with open(cache_file, 'w') as f:
                            json.dump(data, f)

                        # Extract projection
                        if country in data.get('values', {}).get('NGDP_RPCH', {}):
                            country_data = data['values']['NGDP_RPCH'][country]
                            if str(year) in country_data:
                                return ForecastData(
                                    source=DataSource.IMF,
                                    country=country,
                                    year=year,
                                    growth_rate=country_data[str(year)],
                                    vintage=data.get('vintage', datetime.now().strftime('%Y-%m-%d'))
                                )

        except Exception as e:
            print(f"Error fetching IMF data for {country}: {e}")

        return None

    async def fetch_oecd(self, country: str, year: int) -> Optional[ForecastData]:
        """
        Fetch GDP growth projections from OECD Economic Outlook
        Uses OECD's SDMX API (public)
        """
        try:
            # OECD SDMX endpoint for GDP growth
            # EO = Economic Outlook, GDPVGR = GDP Volume Growth Rate
            url = f"https://stats.oecd.org/SDMX-JSON/data/EO/{country}.GDPVGR/all"

            # Check cache
            cache_file = self.cache_dir / f"oecd_{country}_{year}.json"
            if cache_file.exists():
                age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
                if age < timedelta(days=7):
                    with open(cache_file, 'r') as f:
                        data = json.load(f)
                        # Parse OECD's complex JSON structure
                        if self._parse_oecd_data(data, country, year):
                            return self._parse_oecd_data(data, country, year)

            # Fetch fresh data
            if self.session:
                async with self.session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()

                        # Cache the response
                        with open(cache_file, 'w') as f:
                            json.dump(data, f)

                        return self._parse_oecd_data(data, country, year)

        except Exception as e:
            print(f"Error fetching OECD data for {country}: {e}")

        return None

    def _parse_oecd_data(self, data: dict, country: str, year: int) -> Optional[ForecastData]:
        """Parse OECD's SDMX-JSON format"""
        try:
            # OECD data is in a complex nested structure
            series = data.get('dataSets', [{}])[0].get('series', {})

            for key, values in series.items():
                observations = values.get('observations', {})
                # Find the observation for the target year
                for obs_key, obs_value in observations.items():
                    # You'd need to map obs_key to actual year based on OECD's time dimension
                    # This is simplified - real implementation would parse time dimensions
                    if obs_value and len(obs_value) > 0:
                        return ForecastData(
                            source=DataSource.OECD,
                            country=country,
                            year=year,
                            growth_rate=obs_value[0],
                            vintage=datetime.now().strftime('%Y-%m-%d')
                        )
        except Exception as e:
            print(f"Error parsing OECD data: {e}")

        return None

    async def build_consensus(self, country: str, year: int = 2025) -> Dict:
        """
        Build consensus forecast from multiple sources
        Returns median and all individual forecasts
        """
        forecasts = []

        # Fetch from all sources in parallel
        tasks = [
            self.fetch_world_bank(country, year),
            self.fetch_imf(country, year),
            self.fetch_oecd(country, year)
        ]

        results = await asyncio.gather(*tasks)

        # Filter out None results
        valid_forecasts = [r for r in results if r is not None]

        if not valid_forecasts:
            return {
                'country': country,
                'year': year,
                'consensus': None,
                'sources': [],
                'error': 'No data available from official sources'
            }

        # Calculate consensus (median)
        growth_rates = [f.growth_rate for f in valid_forecasts]
        consensus = statistics.median(growth_rates)

        return {
            'country': country,
            'year': year,
            'consensus': consensus,
            'mean': statistics.mean(growth_rates),
            'sources': [f.source.value for f in valid_forecasts],
            'individual': {
                f.source.value: f.growth_rate for f in valid_forecasts
            },
            'vintage': datetime.now().strftime('%Y-%m-%d')
        }

    def compare_with_model(self, model_prediction: float, consensus: float,
                          confidence: float = None) -> Dict:
        """
        Compare model prediction with consensus and assign grade
        """
        delta = model_prediction - consensus
        delta_pct = (delta / abs(consensus)) * 100 if consensus != 0 else 0

        # Grading system
        abs_delta = abs(delta)
        if abs_delta < 0.3:
            grade = 'A'
            assessment = 'Excellent alignment'
        elif abs_delta < 0.5:
            grade = 'B'
            assessment = 'Good alignment'
        elif abs_delta < 0.8:
            grade = 'C'
            assessment = 'Moderate deviation'
        else:
            grade = 'D'
            assessment = 'CHECK - Large deviation'

        # Flag if difference is concerning
        flag = abs_delta > 0.8 and abs(delta_pct) > 35

        return {
            'model': model_prediction,
            'consensus': consensus,
            'delta': delta,
            'delta_pct': delta_pct,
            'grade': grade,
            'assessment': assessment,
            'flag': flag,
            'confidence': confidence
        }

    async def compare_all_countries(self, model_predictions: Dict, year: int = 2025) -> Dict:
        """
        Compare all model predictions with consensus forecasts
        """
        results = {}

        for country, pred_data in model_predictions.items():
            # Get consensus
            consensus_data = await self.build_consensus(country, year)

            if consensus_data['consensus'] is not None:
                # Compare with model
                comparison = self.compare_with_model(
                    pred_data['ensemble'],
                    consensus_data['consensus'],
                    pred_data.get('confidence')
                )

                results[country] = {
                    **comparison,
                    'sources_used': consensus_data['sources'],
                    'individual_forecasts': consensus_data['individual']
                }
            else:
                results[country] = {
                    'error': 'No consensus data available',
                    'model': pred_data['ensemble']
                }

        return results

    def format_comparison_output(self, country: str, comparison: Dict) -> str:
        """
        Format comparison for CLI output
        """
        if 'error' in comparison:
            return f"{country}: model={comparison.get('model', 'N/A'):.2f}% | {comparison['error']}"

        confidence_str = f"({comparison['confidence']*100:.0f}%)" if comparison.get('confidence') else ""
        sources = ','.join(comparison.get('sources_used', []))

        flag_str = " ⚠️ CHECK" if comparison['flag'] else ""

        return (f"{country} 2025: model={comparison['model']:.2f}% {confidence_str} | "
                f"consensus={comparison['consensus']:.2f}% [{sources}] | "
                f"Δ={comparison['delta']:+.2f} → grade {comparison['grade']}{flag_str}")


async def main():
    """Example usage"""
    # Load model predictions
    with open('trained_model_predictions.json', 'r') as f:
        model_predictions = json.load(f)

    async with OfficialForecastsComparison() as comparator:
        # Compare all countries
        print("Fetching official forecasts and comparing with model predictions...")
        print("=" * 80)

        comparisons = await comparator.compare_all_countries(model_predictions)

        # Display results
        for country, comparison in comparisons.items():
            output = comparator.format_comparison_output(country, comparison)
            print(output)

        # Summary statistics
        print("\n" + "=" * 80)
        print("SUMMARY STATISTICS")
        print("-" * 80)

        valid_comparisons = [c for c in comparisons.values() if 'grade' in c]
        if valid_comparisons:
            grades = [c['grade'] for c in valid_comparisons]
            avg_delta = sum(abs(c['delta']) for c in valid_comparisons) / len(valid_comparisons)

            print(f"Average deviation: {avg_delta:.2f} percentage points")
            print(f"Grade distribution: A={grades.count('A')}, B={grades.count('B')}, "
                  f"C={grades.count('C')}, D={grades.count('D')}")

            # Countries needing review
            flagged = [country for country, comp in comparisons.items()
                      if comp.get('flag', False)]
            if flagged:
                print(f"\nCountries needing model review: {', '.join(flagged)}")


if __name__ == "__main__":
    asyncio.run(main())