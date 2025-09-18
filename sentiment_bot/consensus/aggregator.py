"""
Consensus Aggregator
Combines forecasts from multiple sources to create consensus
"""

import statistics
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from ..utils.offline_banner import generate_offline_banner, get_cache_summary, format_api_cache_status

logger = logging.getLogger(__name__)


class ConsensusAggregator:
    """Aggregates forecasts from multiple sources"""

    def __init__(self):
        self.sources = ['World Bank', 'IMF WEO', 'OECD EO']

    def aggregate(self, forecasts: Dict[str, Optional[Dict]]) -> Dict:
        """
        Aggregate forecasts from multiple sources

        Args:
            forecasts: Dict mapping source names to forecast data

        Returns:
            Dict with consensus forecast and metadata
        """
        valid_forecasts = {}
        values_by_year = {}

        # Extract valid forecasts
        for source, forecast in forecasts.items():
            if forecast and 'data' in forecast:
                valid_forecasts[source] = forecast

                # Group by year
                for year, value in forecast['data'].items():
                    if value is not None:
                        if year not in values_by_year:
                            values_by_year[year] = {}
                        values_by_year[year][source] = value

        if not valid_forecasts:
            return {
                'consensus': None,
                'sources_used': [],
                'error': 'No valid forecasts available'
            }

        # Calculate consensus for each year
        consensus_data = {}
        for year, source_values in values_by_year.items():
            if len(source_values) >= 1:  # At least one source
                values = list(source_values.values())
                consensus_data[year] = {
                    'median': statistics.median(values),
                    'mean': statistics.mean(values),
                    'min': min(values),
                    'max': max(values),
                    'std': statistics.stdev(values) if len(values) > 1 else 0.0,
                    'sources_count': len(values),
                    'individual_values': source_values
                }

        # Get most recent year for main consensus
        if consensus_data:
            latest_year = max(consensus_data.keys())
            latest_consensus = consensus_data[latest_year]

            # Prepare data sources for cache analysis
            data_sources = [forecast for forecast in valid_forecasts.values() if forecast]

            # Generate cache status information
            cache_status = format_api_cache_status(data_sources)

            # Log offline mode status
            if cache_status['cache_summary']['offline_mode']:
                logger.info("📦 Operating in OFFLINE mode - all data from cache")
            elif cache_status['cache_summary']['mixed_mode']:
                logger.info(f"⚠️ Operating in MIXED mode - {cache_status['cache_summary']['cache_percentage']}% cached")
            else:
                logger.info("🌐 Operating in LIVE mode - all data fresh from APIs")

            return {
                'consensus': latest_consensus['median'],
                'mean': latest_consensus['mean'],
                'dispersion': latest_consensus['std'],
                'range': [latest_consensus['min'], latest_consensus['max']],
                'sources_used': list(latest_consensus['individual_values'].keys()),
                'individual': latest_consensus['individual_values'],
                'year': latest_year,
                'all_years': consensus_data,
                'timestamp': datetime.now().isoformat(),
                'cache_status': cache_status
            }
        else:
            return {
                'consensus': None,
                'sources_used': list(valid_forecasts.keys()),
                'error': 'No consensus could be calculated'
            }

    def get_consensus_for_year(self, forecasts: Dict[str, Optional[Dict]],
                              target_year: int) -> Dict:
        """
        Get consensus for specific year

        Args:
            forecasts: Dict mapping source names to forecast data
            target_year: Year to get consensus for

        Returns:
            Dict with consensus for target year
        """
        values = {}

        for source, forecast in forecasts.items():
            if forecast and 'data' in forecast:
                year_value = forecast['data'].get(target_year)
                if year_value is not None:
                    values[source] = year_value

        if not values:
            return {
                'consensus': None,
                'year': target_year,
                'sources_used': [],
                'error': f'No data available for {target_year}'
            }

        value_list = list(values.values())

        return {
            'consensus': statistics.median(value_list),
            'mean': statistics.mean(value_list),
            'dispersion': statistics.stdev(value_list) if len(value_list) > 1 else 0.0,
            'range': [min(value_list), max(value_list)],
            'sources_used': list(values.keys()),
            'individual': values,
            'year': target_year,
            'sources_count': len(values)
        }

    def calculate_source_weights(self, historical_performance: Dict[str, float]) -> Dict[str, float]:
        """
        Calculate weights for sources based on historical performance

        Args:
            historical_performance: Dict mapping source to MAE

        Returns:
            Dict mapping source to weight
        """
        if not historical_performance:
            # Equal weights if no performance data
            n_sources = len(self.sources)
            return {source: 1.0 / n_sources for source in self.sources}

        # Inverse of MAE for weights (lower error = higher weight)
        weights = {}
        total_inverse_mae = 0

        for source, mae in historical_performance.items():
            if mae > 0:
                inverse_mae = 1.0 / mae
                weights[source] = inverse_mae
                total_inverse_mae += inverse_mae

        # Normalize weights
        if total_inverse_mae > 0:
            for source in weights:
                weights[source] /= total_inverse_mae

        return weights

    def weighted_consensus(self, forecasts: Dict[str, Optional[Dict]],
                          weights: Dict[str, float], target_year: int) -> Dict:
        """
        Calculate weighted consensus

        Args:
            forecasts: Dict mapping source names to forecast data
            weights: Dict mapping source names to weights
            target_year: Year to get consensus for

        Returns:
            Dict with weighted consensus
        """
        values = {}
        used_weights = {}

        for source, forecast in forecasts.items():
            if forecast and 'data' in forecast:
                year_value = forecast['data'].get(target_year)
                if year_value is not None and source in weights:
                    values[source] = year_value
                    used_weights[source] = weights[source]

        if not values:
            return {
                'consensus': None,
                'year': target_year,
                'sources_used': [],
                'error': f'No data available for {target_year}'
            }

        # Normalize weights for used sources
        total_weight = sum(used_weights.values())
        if total_weight > 0:
            normalized_weights = {s: w / total_weight for s, w in used_weights.items()}
        else:
            normalized_weights = {s: 1.0 / len(values) for s in values}

        # Calculate weighted average
        weighted_sum = sum(values[source] * normalized_weights[source]
                          for source in values)

        return {
            'consensus': weighted_sum,
            'year': target_year,
            'sources_used': list(values.keys()),
            'individual': values,
            'weights_used': normalized_weights,
            'method': 'weighted_average'
        }