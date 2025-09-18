#!/usr/bin/env python
"""
Corrected Economic Predictors - Fixing Critical Issues
=====================================================
Addresses FRED series IDs, CPI calculations, FX conventions, and data hygiene
"""

import os
import json
import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import aiohttp
import asyncio
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit
import warnings
warnings.filterwarnings('ignore')

# Import existing components
from .comprehensive_economic_predictors import (
    PredictionResult,
    AlphaVantageClient
)

# Import ML foundation
from .ml_foundation import DataIntegration, ModelConfig

logger = logging.getLogger(__name__)


class FREDDataClient:
    """Enhanced FRED client with proper series IDs and vintage controls"""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv('FRED_API_KEY', '28eb3d64654c60195cfeed9bc4ec2a41')
        self.base_url = 'https://api.stlouisfed.org/fred'
        self.session = None

        # Correct FRED series IDs
        self.series_map = {
            'nonfarm_payrolls': 'PAYEMS',        # Total Nonfarm Payrolls (thousands)
            'unemployment_rate': 'UNRATE',       # Unemployment Rate (%)
            'initial_claims': 'ICSA',            # Initial Claims (weekly, thousands)
            'cpi_headline': 'CPIAUCSL',          # CPI All Urban Consumers
            'cpi_core': 'CPILFESL',             # CPI Less Food and Energy
            'fed_funds_rate': 'DFF',             # Federal Funds Rate (%)
            'treasury_10y': 'DGS10',            # 10-Year Treasury Rate (%)
            'treasury_2y': 'DGS2',              # 2-Year Treasury Rate (%)
            'real_gdp': 'GDPC1',                # Real GDP (quarterly)
            'consumer_sentiment': 'UMCSENT',     # Michigan Consumer Sentiment
            'manufacturing_pmi': 'NAPM',         # ISM Manufacturing PMI
            'retail_sales': 'RSAFS',            # Retail Sales
            'housing_starts': 'HOUST',          # Housing Starts
            'industrial_production': 'INDPRO'   # Industrial Production Index
        }

        # Release calendars (days after month end)
        self.release_lags = {
            'PAYEMS': 3,      # First Friday after month end
            'UNRATE': 3,      # Same as payrolls
            'CPIAUCSL': 15,   # Mid-month
            'CPILFESL': 15,   # Same as CPI
            'UMCSENT': 28,    # End of month
            'RSAFS': 15,      # Mid-month
            'GDPC1': 45       # Quarterly, ~45 days after quarter end
        }

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def get_series_with_vintage_control(self,
                                            indicator: str,
                                            as_of_date: datetime = None) -> pd.Series:
        """Get FRED series with proper vintage control"""

        series_id = self.series_map.get(indicator, indicator)

        # Apply release lag if as_of_date specified
        if as_of_date and series_id in self.release_lags:
            lag_days = self.release_lags[series_id]
            effective_date = as_of_date - timedelta(days=lag_days)
        else:
            effective_date = None

        params = {
            'series_id': series_id,
            'api_key': self.api_key,
            'file_type': 'json',
            'limit': 1000
        }

        if effective_date:
            params['realtime_end'] = effective_date.strftime('%Y-%m-%d')

        try:
            async with self.session.get(f"{self.base_url}/series/observations",
                                      params=params) as response:
                data = await response.json()

                if 'observations' not in data:
                    logger.warning(f"No data for {series_id}")
                    return pd.Series()

                # Parse observations
                obs_list = []
                for obs in data['observations']:
                    if obs['value'] != '.':  # FRED uses '.' for missing
                        obs_list.append({
                            'date': pd.to_datetime(obs['date']),
                            'value': float(obs['value'])
                        })

                if not obs_list:
                    return pd.Series()

                df = pd.DataFrame(obs_list)
                series = df.set_index('date')['value']
                series.name = series_id

                return series

        except Exception as e:
            logger.error(f"FRED API error for {series_id}: {e}")
            return pd.Series()


class CorrectedInflationPredictor:
    """Fixed CPI predictor with proper annualization and component weights"""

    def __init__(self, fred_client: FREDDataClient, av_client: AlphaVantageClient):
        self.fred_client = fred_client
        self.av_client = av_client

        # CPI component weights (source: BLS, updated annually)
        # These should be pulled from BLS weight tables in production
        self.cpi_weights = {
            'energy': 0.073,        # 7.3% as of 2023
            'food': 0.137,          # 13.7% as of 2023
            'core': 0.790           # 79.0% (1 - energy - food)
        }

    async def predict_cpi_corrected(self,
                                  sentiment_data: Dict,
                                  as_of_date: datetime = None) -> PredictionResult:
        """Corrected CPI prediction with proper annualization"""

        # Get CPI data with vintage control
        cpi_headline = await self.fred_client.get_series_with_vintage_control(
            'cpi_headline', as_of_date
        )
        cpi_core = await self.fred_client.get_series_with_vintage_control(
            'cpi_core', as_of_date
        )

        # Get commodity data for energy/food components
        oil_prices = await self.av_client.get_commodity_price('oil')
        wheat_prices = await self.av_client.get_commodity_price('wheat')

        # Calculate properly annualized 3-month CPI trend
        cpi_3m_annualized = 0
        current_cpi_level = 250.0  # Default baseline

        if not cpi_headline.empty and len(cpi_headline) >= 4:
            # Proper annualization: ((CPI_t / CPI_{t-3}) ** 4 - 1) * 100
            current_cpi = cpi_headline.iloc[-1]
            cpi_3m_ago = cpi_headline.iloc[-4]  # 3 months ago

            if cpi_3m_ago > 0:
                cpi_3m_annualized = ((current_cpi / cpi_3m_ago) ** 4 - 1) * 100
                current_cpi_level = current_cpi

        # Calculate component-specific momentum
        energy_momentum = 0
        food_momentum = 0

        if not oil_prices.empty and len(oil_prices) >= 2:
            oil_3m_change = (oil_prices['value'].iloc[0] / oil_prices['value'].iloc[-1] - 1)
            energy_momentum = oil_3m_change

        if not wheat_prices.empty and len(wheat_prices) >= 2:
            wheat_3m_change = (wheat_prices['value'].iloc[0] / wheat_prices['value'].iloc[-1] - 1)
            food_momentum = wheat_3m_change

        # Component contributions (properly weighted)
        energy_contribution = energy_momentum * self.cpi_weights['energy'] * 100
        food_contribution = food_momentum * self.cpi_weights['food'] * 100

        # Core inflation from trend + sentiment
        core_base = cpi_3m_annualized * self.cpi_weights['core']
        sentiment_adjustment = (
            sentiment_data.get('supply_chain_disruption', 0) * 0.2 +
            sentiment_data.get('tariff_impact', 0) * 0.15
        )
        core_contribution = core_base + sentiment_adjustment

        # Total CPI forecast (month-over-month, annualized)
        total_cpi_forecast = energy_contribution + food_contribution + core_contribution

        # Convert to month-over-month (divide by 12)
        mom_cpi_forecast = total_cpi_forecast / 12

        # Confidence based on data availability and recency
        confidence = 0.4
        if not cpi_headline.empty:
            confidence += 0.25
            # Boost confidence if data is recent
            days_since_last = (datetime.now() - cpi_headline.index[-1]).days
            if days_since_last < 45:  # Within normal release window
                confidence += 0.15

        if not oil_prices.empty and not wheat_prices.empty:
            confidence += 0.15

        # Key drivers based on component analysis
        drivers = []
        if abs(energy_momentum) > 0.05:
            direction = "rising" if energy_momentum > 0 else "falling"
            drivers.append(f"Energy prices {direction} ({energy_momentum:.1%})")

        if abs(food_momentum) > 0.03:
            direction = "rising" if food_momentum > 0 else "falling"
            drivers.append(f"Food prices {direction} ({food_momentum:.1%})")

        if cpi_3m_annualized > 4.0:
            drivers.append("Persistent inflation momentum")
        elif cpi_3m_annualized < 1.0:
            drivers.append("Disinflationary trend")

        return PredictionResult(
            indicator="CPI_MoM",
            prediction=mom_cpi_forecast,
            confidence=min(0.9, confidence),
            timeframe="next_month",
            direction="up" if mom_cpi_forecast > 0.2 else "down" if mom_cpi_forecast < -0.1 else "stable",
            drivers=drivers,
            range_low=mom_cpi_forecast - 0.3,
            range_high=mom_cpi_forecast + 0.3,
            metadata={
                "current_cpi_level": current_cpi_level,
                "cpi_3m_annualized": cpi_3m_annualized,
                "component_weights": self.cpi_weights,
                "components": {
                    "energy": energy_contribution,
                    "food": food_contribution,
                    "core": core_contribution
                },
                "data_sources": ["FRED:CPIAUCSL", "AlphaVantage:OIL", "AlphaVantage:WHEAT"],
                "methodology": "3-month annualized trend with component weighting"
            }
        )


class CorrectedFXPredictor:
    """Fixed FX predictor with standardized quote conventions"""

    def __init__(self, av_client: AlphaVantageClient):
        self.av_client = av_client

        # Standardized FX conventions (all quoted as XXX per 1 USD)
        self.quote_conventions = {
            'EUR': 'EUR_per_USD',  # How many EUR per 1 USD
            'GBP': 'GBP_per_USD',  # How many GBP per 1 USD
            'JPY': 'JPY_per_USD',  # How many JPY per 1 USD
            'CNY': 'CNY_per_USD',  # How many CNY per 1 USD
        }

    async def predict_currency_standardized(self,
                                          base_currency: str,
                                          quote_currency: str,
                                          sentiment_data: Dict,
                                          geopolitical_risk: float) -> PredictionResult:
        """Predict currency with standardized quote convention"""

        # Assert standardized convention
        if base_currency != 'USD':
            raise ValueError("Base currency must be USD for standardized quotes")

        # Get current rate from Alpha Vantage
        av_rate_data = await self.av_client.get_forex_rate(base_currency, quote_currency)

        if not av_rate_data:
            logger.warning(f"No FX data for {base_currency}/{quote_currency}")
            return None

        # Alpha Vantage returns USD/EUR format - standardize to EUR_per_USD
        current_rate = av_rate_data['rate']
        if quote_currency == 'EUR':
            # Convert USD/EUR to EUR/USD
            current_rate = 1.0 / current_rate
            pair_name = "EUR_per_USD"
        else:
            pair_name = f"{quote_currency}_per_USD"

        # Economic factors
        trade_sentiment = sentiment_data.get('trade_sentiment', 0)
        policy_sentiment = sentiment_data.get('monetary_policy', 0)
        economic_strength = sentiment_data.get('economic_strength', 0)

        # Impact calculations (bounded effects)
        terms_of_trade_impact = np.clip(trade_sentiment * 0.02, -0.03, 0.03)  # ±3% max
        rate_differential_impact = np.clip(policy_sentiment * 0.015, -0.02, 0.02)  # ±2% max
        geopolitical_impact = np.clip(-geopolitical_risk * 0.001, -0.01, 0.01)  # ±1% max
        fundamental_impact = np.clip(economic_strength * 0.01, -0.015, 0.015)  # ±1.5% max

        # Combined percentage change
        total_change = (terms_of_trade_impact + rate_differential_impact +
                       geopolitical_impact + fundamental_impact)

        # Apply decay for narrative effects (7-day half-life)
        days_factor = 0.9  # Assume 1 day forecast, adjust as needed
        narrative_decay = 0.5 ** (1/7)  # 7-day half-life
        total_change *= (1 - narrative_decay * days_factor)

        predicted_rate = current_rate * (1 + total_change)

        # Confidence assessment
        confidence = 0.65
        if abs(trade_sentiment) > 0.3:
            confidence += 0.1
        if abs(policy_sentiment) > 0.3:
            confidence += 0.1
        confidence = min(0.9, confidence)

        # Key drivers
        drivers = []
        if abs(terms_of_trade_impact) > 0.01:
            direction = "positive" if terms_of_trade_impact > 0 else "negative"
            drivers.append(f"Trade sentiment {direction}")

        if abs(rate_differential_impact) > 0.01:
            direction = "hawkish" if rate_differential_impact > 0 else "dovish"
            drivers.append(f"Policy expectations {direction}")

        if geopolitical_risk > 50:
            drivers.append("Elevated geopolitical risk")

        return PredictionResult(
            indicator=f"FX_{pair_name}",
            prediction=predicted_rate,
            confidence=confidence,
            timeframe="1_week",
            direction="strengthen" if total_change > 0.005 else "weaken" if total_change < -0.005 else "stable",
            drivers=drivers,
            range_low=predicted_rate * 0.98,  # ±2% range
            range_high=predicted_rate * 1.02,
            metadata={
                "current_rate": current_rate,
                "percent_change": total_change * 100,
                "quote_convention": pair_name,
                "components": {
                    "trade_impact": terms_of_trade_impact * 100,
                    "policy_impact": rate_differential_impact * 100,
                    "geopolitical_impact": geopolitical_impact * 100,
                    "fundamental_impact": fundamental_impact * 100
                },
                "bid_ask_spread": av_rate_data.get('ask', 0) - av_rate_data.get('bid', 0),
                "narrative_decay_applied": True
            }
        )


class CorrectedEmploymentPredictor:
    """Fixed employment predictor with proper FRED series"""

    def __init__(self, fred_client: FREDDataClient, av_client: AlphaVantageClient):
        self.fred_client = fred_client
        self.av_client = av_client

    async def predict_employment_corrected(self,
                                         sentiment_data: Dict,
                                         as_of_date: datetime = None) -> PredictionResult:
        """Corrected employment prediction using proper FRED series"""

        # Get employment data with proper series IDs and vintage control
        payrolls = await self.fred_client.get_series_with_vintage_control(
            'nonfarm_payrolls', as_of_date
        )
        unemployment_rate = await self.fred_client.get_series_with_vintage_control(
            'unemployment_rate', as_of_date
        )
        initial_claims = await self.fred_client.get_series_with_vintage_control(
            'initial_claims', as_of_date
        )

        # Calculate baseline from payrolls trend
        baseline_payroll_change = 150000  # Default
        unemployment_trend = 0
        claims_trend = 0

        if not payrolls.empty and len(payrolls) >= 4:
            # 3-month average of month-over-month changes
            monthly_changes = payrolls.diff().dropna()
            if len(monthly_changes) >= 3:
                baseline_payroll_change = monthly_changes.tail(3).mean()

        if not unemployment_rate.empty and len(unemployment_rate) >= 3:
            # 2-month change in unemployment rate
            unemployment_trend = unemployment_rate.iloc[-1] - unemployment_rate.iloc[-3]

        if not initial_claims.empty and len(initial_claims) >= 5:
            # 4-week moving average trend
            claims_ma = initial_claims.rolling(4).mean()
            if len(claims_ma) >= 2:
                claims_trend = claims_ma.iloc[-1] - claims_ma.iloc[-2]

        # Leading indicator impacts
        unemployment_impact = -unemployment_trend * 50000  # Inverse relationship
        claims_impact = -claims_trend * 0.1  # 100k claims change = 10k payroll impact

        # Sentiment overlays (smaller weight than fundamentals)
        hiring_sentiment_impact = sentiment_data.get('hiring_sentiment', 0) * 25000
        layoff_sentiment_impact = -sentiment_data.get('layoff_sentiment', 0) * 20000

        # Sector performance (from equity markets)
        sector_performance = sentiment_data.get('sector_performance', {})
        sector_impact = (
            sector_performance.get('technology', 0) * 8000 +
            sector_performance.get('manufacturing', 0) * 12000 +
            sector_performance.get('services', 0) * 15000
        )

        # Combined prediction
        predicted_payroll_change = (baseline_payroll_change + unemployment_impact +
                                  claims_impact + hiring_sentiment_impact +
                                  layoff_sentiment_impact + sector_impact)

        # Confidence based on data recency and quality
        confidence = 0.5
        if not payrolls.empty:
            confidence += 0.2
            # Recent data bonus
            days_since_payrolls = (datetime.now() - payrolls.index[-1]).days
            if days_since_payrolls < 10:  # Very recent
                confidence += 0.1

        if not unemployment_rate.empty:
            confidence += 0.15

        if not initial_claims.empty:
            # Claims are weekly, should be very recent
            days_since_claims = (datetime.now() - initial_claims.index[-1]).days
            if days_since_claims < 7:
                confidence += 0.1

        # Key drivers
        drivers = []
        if unemployment_trend < -0.2:
            drivers.append("Declining unemployment rate")
        elif unemployment_trend > 0.2:
            drivers.append("Rising unemployment concern")

        if claims_trend < -10000:
            drivers.append("Falling jobless claims")
        elif claims_trend > 10000:
            drivers.append("Rising jobless claims")

        if hiring_sentiment_impact > 20000:
            drivers.append("Positive hiring sentiment")
        elif layoff_sentiment_impact < -15000:
            drivers.append("Layoff concerns")

        return PredictionResult(
            indicator="nonfarm_payrolls_monthly_change",
            prediction=predicted_payroll_change,
            confidence=min(0.9, confidence),
            timeframe="next_month",
            direction="up" if predicted_payroll_change > 100000 else "down" if predicted_payroll_change < 50000 else "moderate",
            drivers=drivers,
            range_low=predicted_payroll_change - 75000,
            range_high=predicted_payroll_change + 75000,
            metadata={
                "baseline_trend": baseline_payroll_change,
                "unemployment_trend": unemployment_trend,
                "claims_trend": claims_trend,
                "components": {
                    "baseline": baseline_payroll_change,
                    "unemployment_impact": unemployment_impact,
                    "claims_impact": claims_impact,
                    "sentiment_impact": hiring_sentiment_impact + layoff_sentiment_impact,
                    "sector_impact": sector_impact
                },
                "data_sources": ["FRED:PAYEMS", "FRED:UNRATE", "FRED:ICSA"],
                "vintage_controlled": as_of_date is not None
            }
        )


class CorrectedConsumerConfidencePredictor:
    """Consumer confidence calibrated to Michigan Consumer Sentiment"""

    def __init__(self, fred_client: FREDDataClient):
        self.fred_client = fred_client
        self.calibration_params = {'a': 0, 'b': 1}  # Will be fitted
        self.last_calibration_date = None

    async def calibrate_to_michigan_index(self, window_months: int = 24):
        """Calibrate composite score to Michigan Consumer Sentiment"""

        michigan_data = await self.fred_client.get_series_with_vintage_control('consumer_sentiment')

        if michigan_data.empty or len(michigan_data) < window_months:
            logger.warning("Insufficient Michigan sentiment data for calibration")
            return

        # Use last 24 months for calibration
        recent_michigan = michigan_data.tail(window_months)

        # Create synthetic composite scores for calibration
        # (In production, use historical sentiment scores)
        synthetic_scores = []
        for date in recent_michigan.index:
            # Simulate composite score based on Michigan level
            # This would be replaced with actual historical sentiment composite
            michigan_val = recent_michigan[date]
            noise = np.random.normal(0, 5)  # Add some noise
            synthetic_score = (michigan_val - 65) / 30 + noise  # Rough inverse mapping
            synthetic_scores.append(synthetic_score)

        # Linear regression: michigan = a + b * composite
        X = np.array(synthetic_scores).reshape(-1, 1)
        y = recent_michigan.values

        # Simple linear regression
        X_mean = np.mean(X)
        y_mean = np.mean(y)
        b = np.sum((X.flatten() - X_mean) * (y - y_mean)) / np.sum((X.flatten() - X_mean) ** 2)
        a = y_mean - b * X_mean

        self.calibration_params = {'a': a, 'b': b}
        self.last_calibration_date = datetime.now()

        logger.info(f"Consumer confidence calibrated: michigan = {a:.1f} + {b:.1f} * composite")

    def calculate_calibrated_confidence(self, sentiment_data: Dict) -> PredictionResult:
        """Calculate confidence with Michigan calibration"""

        # Extract sentiment components
        job_sentiment = sentiment_data.get('employment_sentiment', 0)
        price_sentiment = sentiment_data.get('inflation_sentiment', 0)  # Negative is bad
        wage_sentiment = sentiment_data.get('wage_sentiment', 0)
        retail_sentiment = sentiment_data.get('retail_sentiment', 0)
        housing_sentiment = sentiment_data.get('housing_sentiment', 0)

        # Composite score (normalized -1 to 1)
        current_conditions = (job_sentiment + (1 - abs(price_sentiment)) + wage_sentiment) / 3
        expectations = (retail_sentiment + housing_sentiment + job_sentiment) / 3

        # Michigan-style weighting
        composite_score = 0.4 * current_conditions + 0.6 * expectations

        # Apply calibration
        calibrated_index = self.calibration_params['a'] + self.calibration_params['b'] * composite_score

        # Clamp to reasonable bounds
        calibrated_index = np.clip(calibrated_index, 30, 120)

        # Calculate change vs baseline
        baseline = 65  # Historical average
        mom_change = calibrated_index - baseline

        # Direction assessment
        if mom_change > 5:
            direction = "improving"
        elif mom_change < -5:
            direction = "deteriorating"
        else:
            direction = "stable"

        # Confidence in prediction
        data_points = sum(1 for v in [job_sentiment, price_sentiment, wage_sentiment,
                                    retail_sentiment, housing_sentiment] if abs(v) > 0.1)
        confidence = 0.4 + data_points * 0.1

        # Add recency bonus if calibration is recent
        if self.last_calibration_date:
            days_since_cal = (datetime.now() - self.last_calibration_date).days
            if days_since_cal < 30:
                confidence += 0.1

        # Key drivers
        drivers = []
        if job_sentiment > 0.3:
            drivers.append("Strong employment outlook")
        elif job_sentiment < -0.3:
            drivers.append("Employment concerns")

        if price_sentiment < -0.3:
            drivers.append("Inflation worries")
        elif price_sentiment > 0.3:
            drivers.append("Price stability confidence")

        if housing_sentiment > 0.3:
            drivers.append("Positive housing sentiment")
        elif housing_sentiment < -0.3:
            drivers.append("Housing affordability concerns")

        return PredictionResult(
            indicator="consumer_confidence_michigan_calibrated",
            prediction=calibrated_index,
            confidence=min(0.9, confidence),
            timeframe="current_month",
            direction=direction,
            drivers=drivers,
            range_low=calibrated_index - 8,
            range_high=calibrated_index + 8,
            metadata={
                "composite_score": composite_score,
                "month_over_month": mom_change,
                "current_conditions": current_conditions,
                "expectations": expectations,
                "calibration_params": self.calibration_params,
                "last_calibration": self.last_calibration_date.isoformat() if self.last_calibration_date else None,
                "data_sources": ["FRED:UMCSENT", "news_sentiment"],
                "methodology": "Michigan Consumer Sentiment calibration"
            }
        )


# Rate limiting and retry decorators
import time
import functools
from typing import Callable

def rate_limit_and_retry(max_calls_per_second: float = 1.0, max_retries: int = 3):
    """Decorator for rate limiting and retry with exponential backoff"""

    def decorator(func: Callable):
        last_called = [0.0]

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            for attempt in range(max_retries + 1):
                # Rate limiting
                now = time.time()
                time_since_last = now - last_called[0]
                min_interval = 1.0 / max_calls_per_second

                if time_since_last < min_interval:
                    sleep_time = min_interval - time_since_last
                    await asyncio.sleep(sleep_time)

                last_called[0] = time.time()

                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries:
                        logger.error(f"Max retries exceeded for {func.__name__}: {e}")
                        raise

                    # Exponential backoff with jitter
                    backoff_time = (2 ** attempt) + np.random.uniform(0, 1)
                    logger.warning(f"Retry {attempt + 1}/{max_retries} for {func.__name__} after {backoff_time:.1f}s")
                    await asyncio.sleep(backoff_time)

        return wrapper
    return decorator


# Enhanced clients with rate limiting
class RateLimitedFREDClient(FREDDataClient):
    """FRED client with rate limiting"""

    @rate_limit_and_retry(max_calls_per_second=1.0, max_retries=3)
    async def get_series_with_vintage_control(self, indicator: str, as_of_date: datetime = None) -> pd.Series:
        return await super().get_series_with_vintage_control(indicator, as_of_date)


class RateLimitedAlphaVantageClient(AlphaVantageClient):
    """Alpha Vantage client with rate limiting"""

    @rate_limit_and_retry(max_calls_per_second=0.2, max_retries=3)  # 5 calls per minute
    async def get_forex_rate(self, from_currency: str, to_currency: str) -> Dict:
        return await super().get_forex_rate(from_currency, to_currency)

    @rate_limit_and_retry(max_calls_per_second=0.2, max_retries=3)
    async def get_commodity_price(self, commodity: str, interval: str = 'daily') -> pd.DataFrame:
        return await super().get_commodity_price(commodity, interval)


# Export corrected predictors
__all__ = [
    'FREDDataClient',
    'CorrectedInflationPredictor',
    'CorrectedFXPredictor',
    'CorrectedEmploymentPredictor',
    'CorrectedConsumerConfidencePredictor',
    'RateLimitedFREDClient',
    'RateLimitedAlphaVantageClient'
]