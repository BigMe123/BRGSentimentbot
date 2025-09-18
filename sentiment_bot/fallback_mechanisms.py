#!/usr/bin/env python
"""
Fallback Mechanisms and Data Guards
==================================
Robust handling of API failures and missing data
"""

import os
import json
import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
from dataclasses import dataclass
import asyncio
import aiofiles
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class CachedDataPoint:
    """Cached data with metadata"""
    value: Any
    timestamp: datetime
    source: str
    ttl_hours: int = 24

    @property
    def is_stale(self) -> bool:
        """Check if data is stale"""
        age_hours = (datetime.now() - self.timestamp).total_seconds() / 3600
        return age_hours > self.ttl_hours

    @property
    def age_hours(self) -> float:
        """Get age in hours"""
        return (datetime.now() - self.timestamp).total_seconds() / 3600


class DataCache:
    """Persistent cache for API data"""

    def __init__(self, cache_dir: str = "state/cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.memory_cache: Dict[str, CachedDataPoint] = {}

    def _get_cache_file(self, key: str) -> Path:
        """Get cache file path for key"""
        safe_key = key.replace('/', '_').replace(':', '_')
        return self.cache_dir / f"{safe_key}.json"

    async def get(self, key: str, max_age_hours: int = 24) -> Optional[CachedDataPoint]:
        """Get cached data"""

        # Check memory cache first
        if key in self.memory_cache:
            cached = self.memory_cache[key]
            if cached.age_hours <= max_age_hours:
                return cached
            else:
                del self.memory_cache[key]

        # Check disk cache
        cache_file = self._get_cache_file(key)
        if cache_file.exists():
            try:
                async with aiofiles.open(cache_file, 'r') as f:
                    data = json.loads(await f.read())

                cached = CachedDataPoint(
                    value=data['value'],
                    timestamp=datetime.fromisoformat(data['timestamp']),
                    source=data['source'],
                    ttl_hours=data.get('ttl_hours', 24)
                )

                if cached.age_hours <= max_age_hours:
                    self.memory_cache[key] = cached
                    return cached
                else:
                    # Remove stale file
                    cache_file.unlink()

            except Exception as e:
                logger.warning(f"Failed to load cache for {key}: {e}")

        return None

    async def set(self, key: str, value: Any, source: str, ttl_hours: int = 24):
        """Set cached data"""

        cached = CachedDataPoint(
            value=value,
            timestamp=datetime.now(),
            source=source,
            ttl_hours=ttl_hours
        )

        # Store in memory
        self.memory_cache[key] = cached

        # Store on disk
        cache_file = self._get_cache_file(key)
        try:
            data = {
                'value': value,
                'timestamp': cached.timestamp.isoformat(),
                'source': source,
                'ttl_hours': ttl_hours
            }

            async with aiofiles.open(cache_file, 'w') as f:
                await f.write(json.dumps(data, default=str))

        except Exception as e:
            logger.warning(f"Failed to cache {key}: {e}")


class FallbackDataProvider:
    """Provides fallback data when APIs fail"""

    def __init__(self):
        self.fallback_data = {
            # FRED series fallbacks (approximate recent values)
            'PAYEMS': 158000000,    # Total payrolls (thousands)
            'UNRATE': 3.8,          # Unemployment rate (%)
            'ICSA': 220000,         # Initial claims (weekly)
            'CPIAUCSL': 310.0,      # CPI level
            'CPILFESL': 305.0,      # Core CPI level
            'DFF': 5.25,            # Fed funds rate (%)
            'DGS10': 4.3,           # 10Y treasury (%)
            'DGS2': 4.8,            # 2Y treasury (%)
            'UMCSENT': 70.0,        # Consumer sentiment

            # FX rates (approximate)
            'EUR_USD': 1.08,
            'GBP_USD': 1.26,
            'USD_JPY': 150.0,
            'USD_CNY': 7.2,

            # Commodity prices
            'OIL_WTI': 80.0,        # $/barrel
            'WHEAT': 550.0,         # cents/bushel
            'COPPER': 3.8,          # $/lb
            'GOLD': 2000.0,         # $/oz
        }

        # Volatility estimates for synthetic uncertainty
        self.fallback_volatility = {
            'PAYEMS': 50000,        # Monthly change volatility
            'UNRATE': 0.1,          # Unemployment rate volatility
            'ICSA': 20000,          # Claims volatility
            'CPIAUCSL': 0.3,        # CPI monthly change %
            'EUR_USD': 0.02,        # FX daily volatility
            'OIL_WTI': 5.0,         # Oil price volatility
        }

    def get_fallback_value(self, indicator: str, add_noise: bool = True) -> float:
        """Get fallback value with optional noise"""

        if indicator not in self.fallback_data:
            logger.warning(f"No fallback data for {indicator}")
            return 0.0

        base_value = self.fallback_data[indicator]

        if not add_noise:
            return base_value

        # Add realistic noise
        volatility = self.fallback_volatility.get(indicator, base_value * 0.02)
        noise = np.random.normal(0, volatility)

        return base_value + noise

    def get_synthetic_series(self, indicator: str, periods: int = 12) -> pd.Series:
        """Generate synthetic time series for backtesting"""

        base_value = self.fallback_data.get(indicator, 100.0)
        volatility = self.fallback_volatility.get(indicator, base_value * 0.02)

        # Generate dates
        end_date = datetime.now()
        dates = pd.date_range(
            end=end_date,
            periods=periods,
            freq='MS'  # Month start
        )

        # Generate synthetic data with trend + noise
        trend = np.linspace(-0.02, 0.02, periods)  # Small trend
        noise = np.random.normal(0, volatility, periods)

        values = []
        current_value = base_value

        for i in range(periods):
            change_pct = trend[i] + noise[i] / current_value
            current_value *= (1 + change_pct)
            values.append(current_value)

        return pd.Series(values, index=dates, name=indicator)


class RobustDataClient:
    """Data client with comprehensive fallbacks"""

    def __init__(self, fred_client=None, av_client=None):
        self.fred_client = fred_client
        self.av_client = av_client
        self.cache = DataCache()
        self.fallback_provider = FallbackDataProvider()

        # API health tracking
        self.api_health = {
            'fred': {'failures': 0, 'last_success': None},
            'alpha_vantage': {'failures': 0, 'last_success': None},
            'yahoo_finance': {'failures': 0, 'last_success': None}
        }

    def _record_api_result(self, api: str, success: bool):
        """Track API health"""
        if success:
            self.api_health[api]['failures'] = 0
            self.api_health[api]['last_success'] = datetime.now()
        else:
            self.api_health[api]['failures'] += 1

    def _is_api_healthy(self, api: str, max_failures: int = 3) -> bool:
        """Check if API is healthy"""
        return self.api_health[api]['failures'] < max_failures

    async def get_fred_series_robust(self,
                                   indicator: str,
                                   as_of_date: datetime = None,
                                   fallback_to_cache: bool = True,
                                   fallback_to_synthetic: bool = True) -> pd.Series:
        """Get FRED data with comprehensive fallbacks"""

        cache_key = f"fred_{indicator}_{as_of_date or 'latest'}"

        # Try primary API if healthy
        if self._is_api_healthy('fred') and self.fred_client:
            try:
                data = await self.fred_client.get_series_with_vintage_control(indicator, as_of_date)
                if not data.empty:
                    await self.cache.set(cache_key, data.to_dict(), 'fred_api')
                    self._record_api_result('fred', True)
                    logger.info(f"FRED data retrieved for {indicator}")
                    return data
                else:
                    logger.warning(f"Empty FRED data for {indicator}")
                    self._record_api_result('fred', False)
            except Exception as e:
                logger.error(f"FRED API failed for {indicator}: {e}")
                self._record_api_result('fred', False)

        # Try cache
        if fallback_to_cache:
            cached = await self.cache.get(cache_key, max_age_hours=48)  # Extended for fallback
            if cached:
                logger.info(f"Using cached FRED data for {indicator} (age: {cached.age_hours:.1f}h)")
                if isinstance(cached.value, dict):
                    return pd.Series(cached.value)
                return cached.value

        # Generate synthetic data as last resort
        if fallback_to_synthetic:
            logger.warning(f"Using synthetic data for {indicator}")
            return self.fallback_provider.get_synthetic_series(indicator)

        logger.error(f"No data available for {indicator}")
        return pd.Series()

    async def get_fx_rate_robust(self,
                               from_currency: str,
                               to_currency: str,
                               fallback_to_cache: bool = True) -> Optional[Dict]:
        """Get FX rate with fallbacks"""

        cache_key = f"fx_{from_currency}_{to_currency}"

        # Try Alpha Vantage if healthy
        if self._is_api_healthy('alpha_vantage') and self.av_client:
            try:
                data = await self.av_client.get_forex_rate(from_currency, to_currency)
                if data:
                    await self.cache.set(cache_key, data, 'alpha_vantage', ttl_hours=6)
                    self._record_api_result('alpha_vantage', True)
                    return data
                else:
                    self._record_api_result('alpha_vantage', False)
            except Exception as e:
                logger.error(f"Alpha Vantage FX failed for {from_currency}/{to_currency}: {e}")
                self._record_api_result('alpha_vantage', False)

        # Try cache
        if fallback_to_cache:
            cached = await self.cache.get(cache_key, max_age_hours=12)
            if cached:
                logger.info(f"Using cached FX data for {from_currency}/{to_currency}")
                return cached.value

        # Use fallback rates
        fallback_key = f"{to_currency}_{from_currency}"
        if fallback_key in self.fallback_provider.fallback_data:
            rate = self.fallback_provider.get_fallback_value(fallback_key)
            logger.warning(f"Using fallback FX rate for {from_currency}/{to_currency}: {rate}")
            return {
                'from': from_currency,
                'to': to_currency,
                'rate': rate,
                'timestamp': datetime.now().isoformat(),
                'source': 'fallback'
            }

        return None

    async def get_commodity_price_robust(self,
                                       commodity: str,
                                       fallback_to_cache: bool = True) -> pd.DataFrame:
        """Get commodity price with fallbacks"""

        cache_key = f"commodity_{commodity}"

        # Try Alpha Vantage if healthy
        if self._is_api_healthy('alpha_vantage') and self.av_client:
            try:
                data = await self.av_client.get_commodity_price(commodity)
                if not data.empty:
                    await self.cache.set(cache_key, data.to_dict(), 'alpha_vantage', ttl_hours=6)
                    self._record_api_result('alpha_vantage', True)
                    return data
                else:
                    self._record_api_result('alpha_vantage', False)
            except Exception as e:
                logger.error(f"Alpha Vantage commodity failed for {commodity}: {e}")
                self._record_api_result('alpha_vantage', False)

        # Try cache
        if fallback_to_cache:
            cached = await self.cache.get(cache_key, max_age_hours=12)
            if cached:
                logger.info(f"Using cached commodity data for {commodity}")
                if isinstance(cached.value, dict):
                    return pd.DataFrame(cached.value)
                return cached.value

        # Generate synthetic commodity data
        commodity_key = f"{commodity.upper()}_WTI" if commodity == 'oil' else commodity.upper()
        if commodity_key in self.fallback_provider.fallback_data:
            logger.warning(f"Using synthetic commodity data for {commodity}")
            base_price = self.fallback_provider.get_fallback_value(commodity_key)

            # Create simple DataFrame
            dates = pd.date_range(end=datetime.now(), periods=30, freq='D')
            prices = [base_price + np.random.normal(0, base_price * 0.02) for _ in range(30)]

            return pd.DataFrame({
                'value': prices,
                'date': dates
            }).set_index('date')

        return pd.DataFrame()

    def get_health_status(self) -> Dict:
        """Get API health status"""
        status = {}
        for api, health in self.api_health.items():
            status[api] = {
                'healthy': self._is_api_healthy(api),
                'failure_count': health['failures'],
                'last_success': health['last_success'].isoformat() if health['last_success'] else None
            }
        return status


class DataQualityMonitor:
    """Monitor data quality and alert on issues"""

    def __init__(self):
        self.quality_checks = {
            'completeness': self._check_completeness,
            'timeliness': self._check_timeliness,
            'consistency': self._check_consistency,
            'outliers': self._check_outliers
        }

    def _check_completeness(self, data: pd.Series, min_points: int = 5) -> Dict:
        """Check data completeness"""
        non_null_count = data.dropna().count()
        completeness_ratio = non_null_count / len(data) if len(data) > 0 else 0

        return {
            'passed': non_null_count >= min_points and completeness_ratio >= 0.8,
            'score': completeness_ratio,
            'message': f"Data completeness: {completeness_ratio:.1%} ({non_null_count}/{len(data)} points)"
        }

    def _check_timeliness(self, data: pd.Series, max_lag_days: int = 7) -> Dict:
        """Check data timeliness"""
        if data.empty:
            return {'passed': False, 'score': 0, 'message': "No data available"}

        last_date = data.index[-1]
        days_lag = (datetime.now() - last_date).days

        return {
            'passed': days_lag <= max_lag_days,
            'score': max(0, 1 - days_lag / (max_lag_days * 2)),
            'message': f"Data lag: {days_lag} days (last: {last_date.strftime('%Y-%m-%d')})"
        }

    def _check_consistency(self, data: pd.Series) -> Dict:
        """Check for data consistency"""
        if len(data) < 3:
            return {'passed': True, 'score': 1, 'message': "Insufficient data for consistency check"}

        # Check for unrealistic jumps
        pct_changes = data.pct_change().dropna()
        extreme_changes = abs(pct_changes) > 0.5  # 50% change threshold

        consistency_score = 1 - extreme_changes.sum() / len(pct_changes)

        return {
            'passed': consistency_score >= 0.9,
            'score': consistency_score,
            'message': f"Consistency score: {consistency_score:.1%}"
        }

    def _check_outliers(self, data: pd.Series, z_threshold: float = 3.0) -> Dict:
        """Check for statistical outliers"""
        if len(data) < 10:
            return {'passed': True, 'score': 1, 'message': "Insufficient data for outlier detection"}

        z_scores = np.abs((data - data.mean()) / data.std())
        outlier_count = (z_scores > z_threshold).sum()
        outlier_ratio = outlier_count / len(data)

        return {
            'passed': outlier_ratio <= 0.05,  # Allow up to 5% outliers
            'score': 1 - outlier_ratio,
            'message': f"Outliers: {outlier_count}/{len(data)} ({outlier_ratio:.1%})"
        }

    def assess_data_quality(self, data: pd.Series, indicator: str) -> Dict:
        """Comprehensive data quality assessment"""

        results = {}
        overall_score = 0
        passed_checks = 0

        for check_name, check_func in self.quality_checks.items():
            try:
                result = check_func(data)
                results[check_name] = result
                overall_score += result['score']
                if result['passed']:
                    passed_checks += 1
            except Exception as e:
                logger.error(f"Quality check {check_name} failed for {indicator}: {e}")
                results[check_name] = {
                    'passed': False,
                    'score': 0,
                    'message': f"Check failed: {e}"
                }

        overall_score /= len(self.quality_checks)

        return {
            'indicator': indicator,
            'overall_score': overall_score,
            'passed_checks': passed_checks,
            'total_checks': len(self.quality_checks),
            'quality_grade': self._get_quality_grade(overall_score),
            'checks': results,
            'timestamp': datetime.now().isoformat()
        }

    def _get_quality_grade(self, score: float) -> str:
        """Convert score to quality grade"""
        if score >= 0.9:
            return 'A'
        elif score >= 0.8:
            return 'B'
        elif score >= 0.7:
            return 'C'
        elif score >= 0.6:
            return 'D'
        else:
            return 'F'


# Export classes
__all__ = [
    'DataCache',
    'FallbackDataProvider',
    'RobustDataClient',
    'DataQualityMonitor',
    'CachedDataPoint'
]