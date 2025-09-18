"""
Comprehensive Economic Predictors with Alpha Vantage Integration
==================================================================
Advanced prediction models for multiple economic indicators using
sentiment analysis, market data, and Alpha Vantage APIs.
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

# Add FRED API client
try:
    from fredapi import Fred
    FRED_AVAILABLE = True
except ImportError:
    FRED_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class PredictionResult:
    """Standardized prediction output"""
    indicator: str
    prediction: float
    confidence: float
    timeframe: str
    direction: str  # 'up', 'down', 'neutral'
    drivers: List[str]
    range_low: float
    range_high: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class AlphaVantageClient:
    """Enhanced Alpha Vantage API client for economic data"""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv('ALPHA_VANTAGE_API_KEY', 'YILWUFW6VO1RA561')
        self.base_url = 'https://www.alphavantage.co/query'
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def get_economic_indicator(self, indicator: str, interval: str = 'monthly') -> pd.DataFrame:
        """Fetch economic indicators (GDP, CPI, unemployment, etc.)"""
        params = {
            'function': indicator,
            'interval': interval,
            'apikey': self.api_key
        }

        try:
            async with self.session.get(self.base_url, params=params) as response:
                data = await response.json()

                if 'Error Message' in data:
                    logger.error(f"API Error: {data['Error Message']}")
                    return pd.DataFrame()

                # Parse based on indicator type
                if indicator == 'REAL_GDP':
                    df = pd.DataFrame(data.get('data', []))
                elif indicator == 'CPI':
                    df = pd.DataFrame(data.get('data', []))
                elif indicator == 'UNEMPLOYMENT':
                    df = pd.DataFrame(data.get('data', []))
                elif indicator == 'NONFARM_PAYROLL':
                    df = pd.DataFrame(data.get('data', []))
                else:
                    df = pd.DataFrame(data.get('data', []))

                if not df.empty:
                    df['date'] = pd.to_datetime(df['date'])
                    df.set_index('date', inplace=True)
                    df['value'] = pd.to_numeric(df['value'], errors='coerce')

                return df

        except Exception as e:
            logger.error(f"Failed to fetch {indicator}: {e}")
            return pd.DataFrame()

    async def get_forex_rate(self, from_currency: str, to_currency: str) -> Dict:
        """Get real-time forex exchange rates"""
        params = {
            'function': 'CURRENCY_EXCHANGE_RATE',
            'from_currency': from_currency,
            'to_currency': to_currency,
            'apikey': self.api_key
        }

        try:
            async with self.session.get(self.base_url, params=params) as response:
                data = await response.json()

                if 'Realtime Currency Exchange Rate' in data:
                    forex_data = data['Realtime Currency Exchange Rate']
                    return {
                        'from': forex_data.get('1. From_Currency Code'),
                        'to': forex_data.get('3. To_Currency Code'),
                        'rate': float(forex_data.get('5. Exchange Rate', 0)),
                        'bid': float(forex_data.get('8. Bid Price', 0)),
                        'ask': float(forex_data.get('9. Ask Price', 0)),
                        'timestamp': forex_data.get('6. Last Refreshed')
                    }
                return {}

        except Exception as e:
            logger.error(f"Failed to fetch forex {from_currency}/{to_currency}: {e}")
            return {}

    async def get_commodity_price(self, commodity: str, interval: str = 'daily') -> pd.DataFrame:
        """Get commodity prices (oil, gas, metals, agriculture)"""
        # Map commodity names to Alpha Vantage functions
        commodity_map = {
            'oil': 'WTI',
            'brent': 'BRENT',
            'gas': 'NATURAL_GAS',
            'copper': 'COPPER',
            'aluminum': 'ALUMINUM',
            'wheat': 'WHEAT',
            'corn': 'CORN',
            'sugar': 'SUGAR',
            'coffee': 'COFFEE',
            'cotton': 'COTTON'
        }

        function = commodity_map.get(commodity.lower(), commodity.upper())
        params = {
            'function': function,
            'interval': interval,
            'apikey': self.api_key
        }

        try:
            async with self.session.get(self.base_url, params=params) as response:
                data = await response.json()

                if 'data' in data:
                    df = pd.DataFrame(data['data'])
                    if not df.empty and 'date' in df.columns:
                        df['date'] = pd.to_datetime(df['date'])
                        df.set_index('date', inplace=True)
                        if 'value' in df.columns:
                            df['value'] = pd.to_numeric(df['value'], errors='coerce')
                    return df

                return pd.DataFrame()

        except Exception as e:
            logger.error(f"Failed to fetch commodity {commodity}: {e}")
            return pd.DataFrame()

    async def get_global_market_status(self) -> Dict:
        """Get global market status"""
        params = {
            'function': 'MARKET_STATUS',
            'apikey': self.api_key
        }

        try:
            async with self.session.get(self.base_url, params=params) as response:
                data = await response.json()
                return data.get('markets', [])

        except Exception as e:
            logger.error(f"Failed to fetch market status: {e}")
            return {}


class FREDClient:
    """FRED API client for economic indicators"""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv('FRED_API_KEY', '28eb3d64654c60195cfeed9bc4ec2a41')
        self.fred = None
        if FRED_AVAILABLE:
            try:
                self.fred = Fred(api_key=self.api_key)
                logger.info("FRED client initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize FRED client: {e}")
                self.fred = None
        else:
            logger.warning("FRED API not available - install fredapi package")

    def get_series(self, series_id: str, limit: int = 120) -> pd.Series:
        """Get FRED time series data"""
        if not self.fred:
            logger.warning("FRED client not available")
            return pd.Series()

        try:
            # Get all recent data (fredapi limit gets FIRST N points, not last N)
            data = self.fred.get_series(series_id)

            if data is not None and not data.empty:
                # Remove missing values and get most recent data
                data = data.dropna()
                # Get the most recent 'limit' points, then sort descending
                recent_data = data.tail(limit).sort_index(ascending=False)
                logger.info(f"Retrieved {len(recent_data)} recent data points for {series_id} (latest: {recent_data.index[0].strftime('%Y-%m')})")
                return recent_data
            else:
                logger.warning(f"No data returned for {series_id}")
                return pd.Series()

        except Exception as e:
            logger.error(f"Failed to fetch FRED series {series_id}: {e}")
            return pd.Series()


class EmploymentPredictor:
    """Job growth and unemployment predictions"""

    def __init__(self, av_client: AlphaVantageClient, fred_client: FREDClient = None):
        self.av_client = av_client
        self.fred_client = fred_client or FREDClient()
        self.model = GradientBoostingRegressor(
            n_estimators=100,
            max_depth=5,
            random_state=42
        )

    async def predict_job_growth(self,
                                 sentiment_data: Dict,
                                 sector_performance: Dict) -> PredictionResult:
        """Forecast job creation and unemployment changes using real data + sentiment"""

        # Fetch historical employment data from FRED (much more reliable)
        nonfarm_payroll = self.fred_client.get_series('PAYEMS')  # Total Nonfarm Payrolls
        unemployment = self.fred_client.get_series('UNRATE')     # Unemployment Rate
        initial_claims = self.fred_client.get_series('ICSA')     # Initial Claims

        # Get current economic indicators
        gdp_data = self.fred_client.get_series('GDPC1')          # Real GDP

        # Calculate baseline from trend analysis (FRED data format)
        baseline_payroll = 150000  # Default monthly change
        unemployment_trend = 0
        claims_trend = 0

        if not nonfarm_payroll.empty and len(nonfarm_payroll) >= 4:
            # Calculate monthly changes in thousands (FRED payrolls are in thousands)
            monthly_changes = nonfarm_payroll.diff().dropna()
            if len(monthly_changes) >= 3:
                baseline_payroll = monthly_changes.head(3).mean()  # 3-month average

        if not unemployment.empty and len(unemployment) >= 3:
            # Calculate 2-month unemployment rate change
            unemployment_trend = unemployment.iloc[0] - unemployment.iloc[2]

        if not initial_claims.empty and len(initial_claims) >= 5:
            # Calculate 4-week trend in initial claims (leading indicator)
            claims_ma = initial_claims.rolling(4).mean()
            if len(claims_ma) >= 2:
                claims_trend = claims_ma.iloc[0] - claims_ma.iloc[1]

        # Economic momentum factors
        gdp_momentum = 0
        if not gdp_data.empty and len(gdp_data) >= 2:
            gdp_momentum = (gdp_data.iloc[0] - gdp_data.iloc[1]) / gdp_data.iloc[1]

        # Real market data features
        features = {
            'unemployment_trend': unemployment_trend,
            'gdp_momentum': gdp_momentum,
            'layoff_sentiment': sentiment_data.get('layoff_sentiment', 0),
            'hiring_sentiment': sentiment_data.get('hiring_sentiment', 0),
            'wage_sentiment': sentiment_data.get('wage_sentiment', 0)
        }

        # Sector equity performance (real market data)
        tech_performance = sector_performance.get('technology', 0)
        manufacturing_performance = sector_performance.get('manufacturing', 0)
        services_performance = sector_performance.get('services', 0)

        # Model prediction using economic relationships
        # Unemployment trend: negative trend = job growth
        unemployment_impact = -unemployment_trend * 50000

        # GDP growth: positive = more jobs
        gdp_impact = gdp_momentum * 200000

        # Sentiment overlay (smaller weight than fundamentals)
        sentiment_impact = (
            sentiment_data.get('hiring_sentiment', 0) * 30000 -
            sentiment_data.get('layoff_sentiment', 0) * 25000
        )

        # Sector performance impact
        sector_impact = (tech_performance + manufacturing_performance + services_performance) * 10000

        predicted_payroll = baseline_payroll + unemployment_impact + gdp_impact + sentiment_impact + sector_impact

        # Confidence based on FRED data quality (much higher than Alpha Vantage)
        confidence = 0.6  # Higher base for FRED data
        if not nonfarm_payroll.empty:
            confidence += 0.25  # FRED payrolls are very reliable
        if not unemployment.empty:
            confidence += 0.15  # FRED unemployment is official BLS data
        if not initial_claims.empty:
            confidence += 0.1   # Claims are weekly, very timely
        if not gdp_data.empty:
            confidence += 0.05  # GDP is quarterly but important

        # Reduce confidence if data is old
        if not nonfarm_payroll.empty:
            days_old = (datetime.now().date() - nonfarm_payroll.index[0].date()).days
            if days_old > 45:  # Employment data more than 45 days old
                confidence -= 0.1

        # Key drivers
        drivers = []
        if unemployment_trend < -0.1:
            drivers.append("Declining unemployment trend")
        if gdp_momentum > 0.005:
            drivers.append("Strong GDP growth momentum")
        if sentiment_data.get('layoff_sentiment', 0) < -0.3:
            drivers.append("High layoff concerns")
        if tech_performance > 0.1:
            drivers.append("Technology sector strength")

        return PredictionResult(
            indicator="nonfarm_payrolls",
            prediction=predicted_payroll,
            confidence=min(0.9, confidence),
            timeframe="next_month",
            direction="up" if predicted_payroll > 0 else "down",
            drivers=drivers,
            range_low=predicted_payroll - 50000,
            range_high=predicted_payroll + 50000,
            metadata={
                "baseline_trend": baseline_payroll,
                "unemployment_trend": unemployment_trend,
                "claims_trend": claims_trend,
                "gdp_momentum": gdp_momentum,
                "data_sources": ["FRED:PAYEMS", "FRED:UNRATE", "FRED:ICSA", "FRED:GDPC1"],
                "data_quality": "HIGH - Official Federal Reserve/BLS data"
            }
        )


class InflationPredictor:
    """CPI and inflation predictions"""

    def __init__(self, av_client: AlphaVantageClient, fred_client: FREDClient = None):
        self.av_client = av_client
        self.fred_client = fred_client or FREDClient()
        self.scaler = StandardScaler()

    async def predict_cpi(self, sentiment_data: Dict) -> PredictionResult:
        """Predict short-term CPI changes using real data + sentiment"""

        # Fetch historical CPI data from FRED (much more reliable)
        cpi_data = self.fred_client.get_series('CPIAUCSL')  # CPI All Urban Consumers

        # Get commodity prices for real market signals
        oil_prices = await self.av_client.get_commodity_price('oil')
        wheat_prices = await self.av_client.get_commodity_price('wheat')

        # Calculate baseline from CPI trend (PROPERLY ANNUALIZED)
        cpi_3m_annualized = 0
        current_cpi = 3.2  # Default

        if not cpi_data.empty and len(cpi_data) >= 4:
            # Proper 3-month annualization: ((CPI_t / CPI_{t-3}) ** 4 - 1) * 100
            # FRED data is already in index format (no 'value' column)
            current_cpi_value = cpi_data.iloc[0]
            cpi_3m_ago = cpi_data.iloc[3]  # 3 months ago

            if cpi_3m_ago > 0:
                cpi_3m_annualized = ((current_cpi_value / cpi_3m_ago) ** 4 - 1) * 100
                current_cpi = current_cpi_value

        # Real commodity price impacts
        oil_momentum = 0
        food_momentum = 0

        if not oil_prices.empty and len(oil_prices) >= 2:
            oil_momentum = (oil_prices['value'].iloc[0] - oil_prices['value'].iloc[1]) / oil_prices['value'].iloc[1]

        if not wheat_prices.empty and len(wheat_prices) >= 2:
            food_momentum = (wheat_prices['value'].iloc[0] - wheat_prices['value'].iloc[1]) / wheat_prices['value'].iloc[1]

        # Component weights (CPI methodology)
        weights = {
            'energy': 0.08,   # 8% of CPI
            'food': 0.14,     # 14% of CPI
            'core': 0.78      # 78% of CPI
        }

        # Real market-based impacts
        energy_impact = oil_momentum * weights['energy'] * 100  # Convert to percentage points
        food_impact = food_momentum * weights['food'] * 100

        # Core inflation from properly annualized trend + sentiment
        core_impact = (cpi_3m_annualized / 12) * weights['core']  # Convert annual to monthly

        # Sentiment overlay (smaller impact than real data)
        sentiment_adjustment = (
            sentiment_data.get('supply_chain', 0) * 0.05 +
            sentiment_data.get('tariffs', 0) * 0.03
        )

        # Total CPI prediction
        cpi_change = energy_impact + food_impact + core_impact + sentiment_adjustment

        # Confidence based on FRED data availability (much higher quality)
        confidence = 0.7  # Higher base for FRED CPI data
        if not cpi_data.empty:
            confidence += 0.2  # FRED CPI is official BLS data
            # Check data recency
            days_old = (datetime.now().date() - cpi_data.index[0].date()).days
            if days_old <= 30:
                confidence += 0.05  # Bonus for recent data
        if not oil_prices.empty:
            confidence += 0.1  # Alpha Vantage commodities (lower weight)
        if not wheat_prices.empty:
            confidence += 0.05

        # Key drivers based on actual data
        drivers = []
        if abs(oil_momentum) > 0.05:
            direction = "rising" if oil_momentum > 0 else "falling"
            drivers.append(f"Oil prices {direction}")

        if abs(food_momentum) > 0.03:
            direction = "rising" if food_momentum > 0 else "falling"
            drivers.append(f"Food prices {direction}")

        if cpi_3m_annualized > 4.0:  # 4% annualized is high
            drivers.append("Persistent inflation trend")
        elif cpi_3m_annualized < 1.0:  # Below 1% annualized is low
            drivers.append("Disinflationary trend")

        if sentiment_data.get('tariffs', 0) < -0.3:
            drivers.append("Tariff concerns")

        return PredictionResult(
            indicator="CPI_MoM",
            prediction=cpi_change,
            confidence=min(0.9, confidence),
            timeframe="next_month",
            direction="up" if cpi_change > 0.1 else "down" if cpi_change < -0.1 else "stable",
            drivers=drivers,
            range_low=cpi_change - 0.3,
            range_high=cpi_change + 0.3,
            metadata={
                "current_cpi": current_cpi,
                "cpi_3m_annualized": cpi_3m_annualized,
                "oil_momentum": oil_momentum,
                "food_momentum": food_momentum,
                "components": {
                    "energy": energy_impact,
                    "food": food_impact,
                    "core": core_impact
                },
                "data_sources": ["FRED:CPIAUCSL", "AlphaVantage:OIL", "AlphaVantage:WHEAT"],
                "data_quality": "HIGH - Official Bureau of Labor Statistics CPI data"
            }
        )


class ForexPredictor:
    """Currency and FX predictions"""

    def __init__(self, av_client: AlphaVantageClient):
        self.av_client = av_client

    async def predict_currency(self,
                              currency_pair: str,
                              sentiment_data: Dict,
                              geopolitical_risk: float) -> PredictionResult:
        """Predict currency movements"""

        from_currency, to_currency = currency_pair.split('/')

        # Get current FX rate (Alpha Vantage returns: how many TO_CURRENCY per 1 FROM_CURRENCY)
        # Example: USD/EUR returns 0.841 = "0.841 EUR per 1 USD"
        current_rate = await self.av_client.get_forex_rate(from_currency, to_currency)

        if not current_rate:
            return None

        # Extract relevant sentiment
        trade_sentiment = sentiment_data.get('trade_sentiment', 0)
        policy_sentiment = sentiment_data.get('monetary_policy', 0)
        economic_strength = sentiment_data.get('economic_strength', 0)

        # Terms of trade impact
        tot_impact = trade_sentiment * 0.02  # 2% max impact

        # Interest rate differential proxy
        rate_differential = policy_sentiment * 0.015

        # Geopolitical risk premium
        risk_premium = -geopolitical_risk * 0.001  # Risk weakens currency

        # Economic fundamentals
        fundamental_impact = economic_strength * 0.01

        # Combined prediction
        total_change = tot_impact + rate_differential + risk_premium + fundamental_impact
        predicted_rate = current_rate['rate'] * (1 + total_change)

        # Timeframe: 1-4 weeks
        confidence = 0.6 + min(0.3, abs(trade_sentiment) * 0.2)

        # Drivers
        drivers = []
        if trade_sentiment < -0.3:
            drivers.append("Negative trade sentiment")
        if policy_sentiment > 0.3:
            drivers.append("Hawkish policy expectations")
        if geopolitical_risk > 50:
            drivers.append("High geopolitical risk")
        if economic_strength > 0.3:
            drivers.append("Strong economic fundamentals")

        return PredictionResult(
            indicator=f"FX_{currency_pair}",
            prediction=predicted_rate,
            confidence=confidence,
            timeframe="1-4_weeks",
            direction="strengthen" if total_change > 0 else "weaken",
            drivers=drivers,
            range_low=predicted_rate * 0.97,
            range_high=predicted_rate * 1.03,
            metadata={
                "current_rate": current_rate['rate'],
                "percent_change": total_change * 100,
                "bid_ask_spread": current_rate.get('ask', 0) - current_rate.get('bid', 0)
            }
        )


class EquityMarketPredictor:
    """Stock market index predictions"""

    def __init__(self, av_client: AlphaVantageClient):
        self.av_client = av_client

    async def predict_index(self,
                           index_name: str,
                           sentiment_data: Dict,
                           fx_impact: float = 0) -> PredictionResult:
        """Predict country stock indices"""

        # Map index names to tickers
        index_map = {
            'SPX': 'SPY',
            'NIFTY': 'INDA',
            'BOVESPA': 'EWZ',
            'DAX': 'EWG',
            'FTSE': 'EWU',
            'NIKKEI': 'EWJ',
            'SHANGHAI': 'ASHR',
            'HANG_SENG': 'EWH'
        }

        ticker = index_map.get(index_name, index_name)

        # Combine macro sentiment with sector impacts
        macro_sentiment = sentiment_data.get('macro_sentiment', 0)
        sector_sentiments = sentiment_data.get('sectors', {})

        # Weight sectors by index composition (simplified)
        sector_weights = {
            'technology': 0.25,
            'financials': 0.20,
            'industrials': 0.15,
            'consumer': 0.15,
            'healthcare': 0.10,
            'energy': 0.10,
            'materials': 0.05
        }

        # Calculate weighted sector impact
        sector_impact = sum(
            sector_sentiments.get(sector, 0) * weight
            for sector, weight in sector_weights.items()
        )

        # Momentum factor (simplified)
        momentum = sentiment_data.get('price_momentum', 0)

        # FX impact for international indices
        fx_adjustment = fx_impact * 0.5  # 50% pass-through

        # Combined prediction
        base_return = 0.002  # 0.2% baseline weekly

        predicted_return = (
            base_return +
            macro_sentiment * 0.02 +
            sector_impact * 0.015 +
            momentum * 0.01 +
            fx_adjustment
        )

        # Confidence based on data quality
        confidence = 0.55 + min(0.35, abs(macro_sentiment) * 0.2)

        # Direction and drivers
        direction = "bullish" if predicted_return > 0.002 else "bearish" if predicted_return < -0.002 else "neutral"

        drivers = []
        if macro_sentiment > 0.3:
            drivers.append("Positive macro environment")
        elif macro_sentiment < -0.3:
            drivers.append("Negative macro headwinds")

        # Top performing sectors
        top_sectors = sorted(
            sector_sentiments.items(),
            key=lambda x: x[1],
            reverse=True
        )[:2]

        for sector, score in top_sectors:
            if score > 0.2:
                drivers.append(f"Strong {sector} sector")

        return PredictionResult(
            indicator=f"INDEX_{index_name}",
            prediction=predicted_return * 100,  # Convert to percentage
            confidence=confidence,
            timeframe="1_week",
            direction=direction,
            drivers=drivers,
            range_low=predicted_return * 100 - 2,
            range_high=predicted_return * 100 + 2,
            metadata={
                "sector_impacts": sector_sentiments,
                "fx_contribution": fx_adjustment * 100
            }
        )


class CommodityPredictor:
    """Commodity price predictions"""

    def __init__(self, av_client: AlphaVantageClient):
        self.av_client = av_client
        self.commodities = [
            'oil', 'gas', 'copper', 'aluminum',
            'wheat', 'corn', 'sugar', 'coffee'
        ]

    async def predict_commodity(self,
                               commodity: str,
                               sentiment_data: Dict) -> PredictionResult:
        """Predict commodity price movements"""

        # Fetch current prices
        prices = await self.av_client.get_commodity_price(commodity)

        # Extract relevant sentiment
        supply_sentiment = sentiment_data.get(f'{commodity}_supply', 0)
        demand_sentiment = sentiment_data.get(f'{commodity}_demand', 0)
        policy_sentiment = sentiment_data.get('policy_impact', 0)
        weather_impact = sentiment_data.get('weather_impact', 0) if commodity in ['wheat', 'corn', 'sugar', 'coffee'] else 0

        # Supply/demand balance
        sd_balance = demand_sentiment - supply_sentiment

        # Policy impact (tariffs, sanctions, subsidies)
        policy_impact = policy_sentiment * 0.1

        # Weather/climate for agricultural commodities
        weather_adjustment = weather_impact * 0.15 if commodity in ['wheat', 'corn'] else 0

        # Geopolitical risk premium for energy
        geo_premium = sentiment_data.get('geopolitical_risk', 0) * 0.002 if commodity in ['oil', 'gas'] else 0

        # Calculate price change prediction
        price_change = (
            sd_balance * 0.05 +  # 5% max from supply/demand
            policy_impact +
            weather_adjustment +
            geo_premium
        )

        # Current price (use last available or estimate)
        current_price = 100  # Normalized
        if not prices.empty:
            current_price = prices.iloc[0]['value']

        predicted_price = current_price * (1 + price_change)

        # Confidence based on sentiment strength
        confidence = 0.5 + min(0.4, abs(sd_balance) * 0.3)

        # Drivers
        drivers = []
        if supply_sentiment < -0.3:
            drivers.append("Supply disruption fears")
        elif supply_sentiment > 0.3:
            drivers.append("Improving supply outlook")

        if demand_sentiment > 0.3:
            drivers.append("Strong demand expectations")
        elif demand_sentiment < -0.3:
            drivers.append("Weakening demand")

        if weather_impact < -0.3:
            drivers.append("Adverse weather conditions")

        if geo_premium > 0.01:
            drivers.append("Geopolitical risk premium")

        return PredictionResult(
            indicator=f"COMMODITY_{commodity.upper()}",
            prediction=price_change * 100,  # Percentage change
            confidence=confidence,
            timeframe="1-4_weeks",
            direction="up" if price_change > 0 else "down",
            drivers=drivers,
            range_low=predicted_price * 0.95,
            range_high=predicted_price * 1.05,
            metadata={
                "current_price": current_price,
                "predicted_price": predicted_price,
                "supply_demand_balance": sd_balance
            }
        )


class TradeFlowPredictor:
    """Trade flow and export/import predictions"""

    def __init__(self):
        self.trade_pairs = [
            ('USA', 'China'),
            ('USA', 'EU'),
            ('China', 'EU'),
            ('India', 'USA'),
            ('BRICS', 'G7')
        ]

    def predict_trade_flow(self,
                          from_country: str,
                          to_country: str,
                          sentiment_data: Dict) -> PredictionResult:
        """Forecast bilateral trade changes"""

        # Extract co-mention sentiment
        pair_key = f"{from_country}_{to_country}"
        bilateral_sentiment = sentiment_data.get(pair_key, 0)

        # Tariff and sanction sentiment
        tariff_sentiment = sentiment_data.get(f'tariff_{pair_key}', 0)
        sanction_risk = sentiment_data.get(f'sanction_{from_country}', 0)

        # Shipping and logistics indicators
        shipping_sentiment = sentiment_data.get('shipping_costs', 0)
        logistics_efficiency = sentiment_data.get('port_efficiency', 0)

        # Calculate expected trade flow change
        base_change = bilateral_sentiment * 0.1  # 10% max from sentiment
        tariff_impact = tariff_sentiment * -0.15  # Tariffs reduce trade
        sanction_impact = sanction_risk * -0.25  # Sanctions severely impact
        logistics_impact = (shipping_sentiment + logistics_efficiency) * 0.05

        total_change = base_change + tariff_impact + sanction_impact + logistics_impact

        # Confidence based on data availability
        confidence = 0.6
        if abs(bilateral_sentiment) > 0.3:
            confidence += 0.15
        if tariff_sentiment != 0:
            confidence += 0.1

        # Determine drivers
        drivers = []
        if tariff_sentiment < -0.3:
            drivers.append("Increased tariff barriers")
        if sanction_risk < -0.3:
            drivers.append("Sanction concerns")
        if bilateral_sentiment > 0.3:
            drivers.append("Improving bilateral relations")
        if shipping_sentiment < -0.2:
            drivers.append("Rising shipping costs")

        return PredictionResult(
            indicator=f"TRADE_{from_country}_TO_{to_country}",
            prediction=total_change * 100,  # Percentage
            confidence=confidence,
            timeframe="3_months",
            direction="increase" if total_change > 0 else "decrease",
            drivers=drivers,
            range_low=total_change * 100 - 5,
            range_high=total_change * 100 + 5,
            metadata={
                "tariff_impact": tariff_impact * 100,
                "bilateral_sentiment": bilateral_sentiment
            }
        )




class FDIPredictor:
    """Foreign Direct Investment predictor"""

    def predict_fdi(self, country: str, sentiment_data: Dict) -> PredictionResult:
        """Predict FDI sentiment trends"""

        # Extract FDI-relevant sentiment
        regulatory_sentiment = sentiment_data.get('regulatory_stability', 0)
        incentive_sentiment = sentiment_data.get('investment_incentives', 0)
        relocation_mentions = sentiment_data.get('plant_relocations', 0)
        business_climate = sentiment_data.get('business_environment', 0)

        # Calculate FDI attractiveness score
        fdi_score = (
            regulatory_sentiment * 0.3 +
            incentive_sentiment * 0.25 +
            business_climate * 0.25 +
            relocation_mentions * 0.2
        )

        # Convert to directional prediction
        if fdi_score > 0.2:
            direction = "positive"
            prediction = fdi_score * 20  # Scale to percentage
        elif fdi_score < -0.2:
            direction = "negative"
            prediction = fdi_score * 20
        else:
            direction = "neutral"
            prediction = 0

        # Confidence based on sentiment strength
        confidence = 0.5 + min(0.4, abs(fdi_score))

        # Drivers
        drivers = []
        if regulatory_sentiment > 0.3:
            drivers.append("Improving regulatory environment")
        elif regulatory_sentiment < -0.3:
            drivers.append("Regulatory uncertainty")

        if incentive_sentiment > 0.3:
            drivers.append("Attractive investment incentives")

        if relocation_mentions > 0.2:
            drivers.append("Manufacturing relocation interest")
        elif relocation_mentions < -0.2:
            drivers.append("Capital flight concerns")

        return PredictionResult(
            indicator=f"FDI_{country}",
            prediction=prediction,
            confidence=confidence,
            timeframe="6_months",
            direction=direction,
            drivers=drivers,
            range_low=prediction - 5,
            range_high=prediction + 5,
            metadata={
                "fdi_score": fdi_score,
                "components": {
                    "regulatory": regulatory_sentiment,
                    "incentives": incentive_sentiment,
                    "relocations": relocation_mentions,
                    "business_climate": business_climate
                }
            }
        )


class ConsumerConfidenceProxy:
    """Consumer confidence approximation"""

    def calculate_confidence(self, sentiment_data: Dict) -> PredictionResult:
        """Approximate consumer confidence index (0-100)"""

        # Extract consumer-relevant sentiment
        job_sentiment = sentiment_data.get('employment', 0)
        price_sentiment = sentiment_data.get('prices', 0)  # Negative is bad
        wage_sentiment = sentiment_data.get('wages', 0)
        retail_sentiment = sentiment_data.get('retail_sales', 0)
        housing_sentiment = sentiment_data.get('housing', 0)

        # Weight components (Michigan Consumer Sentiment approximation)
        weights = {
            'current_conditions': 0.4,
            'expectations': 0.6
        }

        # Current conditions sub-index
        current = (
            (job_sentiment + 1) * 25 +  # Scale -1 to 1 -> 0 to 50
            (1 - price_sentiment) * 15 +  # Inverse for prices
            (wage_sentiment + 1) * 10
        )

        # Expectations sub-index
        expectations = (
            retail_sentiment * 20 +
            housing_sentiment * 20 +
            job_sentiment * 10
        ) + 50  # Base level

        # Combined index
        confidence_index = (
            current * weights['current_conditions'] +
            expectations * weights['expectations']
        )

        # Normalize to 0-100
        confidence_index = max(0, min(100, confidence_index))

        # Month-over-month change
        baseline = 65  # Historical average
        mom_change = confidence_index - baseline

        # Determine trend
        if mom_change > 5:
            direction = "improving"
        elif mom_change < -5:
            direction = "deteriorating"
        else:
            direction = "stable"

        # Confidence in estimate
        data_quality = sum(1 for v in [job_sentiment, price_sentiment, wage_sentiment, retail_sentiment, housing_sentiment] if v != 0)
        confidence = 0.4 + data_quality * 0.12

        # Key drivers
        drivers = []
        if job_sentiment > 0.3:
            drivers.append("Strong job market")
        elif job_sentiment < -0.3:
            drivers.append("Employment concerns")

        if price_sentiment < -0.3:
            drivers.append("Inflation worries")
        elif price_sentiment > 0.3:
            drivers.append("Price stability")

        if housing_sentiment > 0.3:
            drivers.append("Positive housing market")
        elif housing_sentiment < -0.3:
            drivers.append("Housing affordability issues")

        return PredictionResult(
            indicator="CONSUMER_CONFIDENCE",
            prediction=confidence_index,
            confidence=confidence,
            timeframe="current_month",
            direction=direction,
            drivers=drivers,
            range_low=confidence_index - 5,
            range_high=confidence_index + 5,
            metadata={
                "month_over_month": mom_change,
                "current_conditions": current,
                "expectations": expectations
            }
        )


class ComprehensiveEconomicPredictor:
    """Main orchestrator for all economic predictions"""

    def __init__(self, api_key: str = None):
        self.av_client = AlphaVantageClient(api_key)
        self.fred_client = FREDClient()

        # Initialize all predictors with both clients
        self.employment = EmploymentPredictor(self.av_client, self.fred_client)
        self.inflation = InflationPredictor(self.av_client, self.fred_client)
        self.forex = ForexPredictor(self.av_client)
        self.equity = EquityMarketPredictor(self.av_client)
        self.commodity = CommodityPredictor(self.av_client)
        self.trade = TradeFlowPredictor()
        self.fdi = FDIPredictor()
        self.consumer = ConsumerConfidenceProxy()

        logger.info("Comprehensive Economic Predictor initialized with all modules")

    async def generate_full_forecast(self,
                                    sentiment_data: Dict,
                                    news_data: List[Dict] = None) -> Dict[str, PredictionResult]:
        """Generate comprehensive economic forecast"""

        async with self.av_client:
            results = {}

            # 1. Employment forecast
            try:
                employment_result = await self.employment.predict_job_growth(
                    sentiment_data,
                    sentiment_data.get('sector_performance', {})
                )
                results['employment'] = employment_result
                logger.info(f"Employment: {employment_result.prediction:,.0f} jobs, {employment_result.confidence:.1%} confidence")
            except Exception as e:
                logger.error(f"Employment prediction failed: {e}")

            # 2. Inflation forecast
            try:
                cpi_result = await self.inflation.predict_cpi(sentiment_data)
                results['inflation'] = cpi_result
                logger.info(f"CPI: {cpi_result.prediction:+.2f}%, {cpi_result.confidence:.1%} confidence")
            except Exception as e:
                logger.error(f"Inflation prediction failed: {e}")

            # 3. Major currency pairs
            major_pairs = ['USD/EUR', 'USD/JPY', 'USD/GBP', 'USD/CNY']
            for pair in major_pairs:
                try:
                    # Use default geopolitical risk for now
                    geopolitical_risk = sentiment_data.get('geopolitical_risk', 25.0)
                    fx_result = await self.forex.predict_currency(
                        pair,
                        sentiment_data,
                        geopolitical_risk
                    )
                    if fx_result:
                        results[f'fx_{pair}'] = fx_result
                        logger.info(f"{pair}: {fx_result.direction}, {fx_result.confidence:.1%} confidence")
                except Exception as e:
                    logger.error(f"FX {pair} prediction failed: {e}")

            # 4. Major equity indices
            indices = ['SPX', 'NIFTY', 'DAX', 'NIKKEI']
            for index in indices:
                try:
                    equity_result = await self.equity.predict_index(
                        index,
                        sentiment_data
                    )
                    results[f'equity_{index}'] = equity_result
                    logger.info(f"{index}: {equity_result.prediction:+.2f}%, {equity_result.confidence:.1%} confidence")
                except Exception as e:
                    logger.error(f"Equity {index} prediction failed: {e}")

            # 5. Key commodities
            key_commodities = ['oil', 'copper', 'wheat']
            for commodity in key_commodities:
                try:
                    commodity_result = await self.commodity.predict_commodity(
                        commodity,
                        sentiment_data
                    )
                    results[f'commodity_{commodity}'] = commodity_result
                    logger.info(f"{commodity}: {commodity_result.prediction:+.2f}%, {commodity_result.confidence:.1%} confidence")
                except Exception as e:
                    logger.error(f"Commodity {commodity} prediction failed: {e}")

            # 6. Trade flows
            try:
                trade_result = self.trade.predict_trade_flow(
                    'USA',
                    'China',
                    sentiment_data
                )
                results['trade_usa_china'] = trade_result
                logger.info(f"USA-China trade: {trade_result.prediction:+.1f}%, {trade_result.confidence:.1%} confidence")
            except Exception as e:
                logger.error(f"Trade prediction failed: {e}")

            # 7. Geopolitical Risk Index (simplified for now)
            try:
                # Create simple GPR result from sentiment
                geopolitical_risk = sentiment_data.get('geopolitical_risk', 25.0)
                from sentiment_bot.comprehensive_economic_predictors import PredictionResult
                gpr_result = PredictionResult(
                    indicator="GPR_INDEX",
                    prediction=geopolitical_risk,
                    confidence=0.6,
                    timeframe="current",
                    direction="elevated" if geopolitical_risk > 50 else "moderate",
                    drivers=["Geopolitical sentiment"],
                    range_low=geopolitical_risk - 10,
                    range_high=geopolitical_risk + 10
                )
                results['gpr_index'] = gpr_result
                logger.info(f"GPR Index: {gpr_result.prediction:.1f}/100, {gpr_result.direction} risk")
            except Exception as e:
                logger.error(f"GPR calculation failed: {e}")

            # 8. FDI sentiment
            try:
                fdi_result = self.fdi.predict_fdi('USA', sentiment_data)
                results['fdi_usa'] = fdi_result
                logger.info(f"FDI USA: {fdi_result.direction}, {fdi_result.confidence:.1%} confidence")
            except Exception as e:
                logger.error(f"FDI prediction failed: {e}")

            # 9. Consumer confidence
            try:
                consumer_result = self.consumer.calculate_confidence(sentiment_data)
                results['consumer_confidence'] = consumer_result
                logger.info(f"Consumer Confidence: {consumer_result.prediction:.1f}/100, {consumer_result.direction}")
            except Exception as e:
                logger.error(f"Consumer confidence calculation failed: {e}")

            return results

    def format_forecast_report(self, results: Dict[str, PredictionResult]) -> str:
        """Format results into readable report"""

        report = [
            "=" * 80,
            "COMPREHENSIVE ECONOMIC FORECAST",
            "=" * 80,
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
        ]

        # Group by category
        categories = {
            'Labor Market': ['employment'],
            'Inflation': ['inflation'],
            'Foreign Exchange': [k for k in results if k.startswith('fx_')],
            'Equity Markets': [k for k in results if k.startswith('equity_')],
            'Commodities': [k for k in results if k.startswith('commodity_')],
            'Trade & Investment': ['trade_usa_china', 'fdi_usa'],
            'Risk & Sentiment': ['gpr_index', 'consumer_confidence']
        }

        for category, indicators in categories.items():
            if not any(ind in results for ind in indicators):
                continue

            report.append(f"\n{category}")
            report.append("-" * 40)

            for indicator in indicators:
                if indicator not in results:
                    continue

                result = results[indicator]

                # Format based on indicator type
                if indicator == 'employment':
                    report.append(f"• Payrolls: {result.prediction:+,.0f} jobs ({result.confidence:.1%} conf)")
                    report.append(f"  Direction: {result.direction} | Timeframe: {result.timeframe}")
                elif indicator == 'inflation':
                    report.append(f"• CPI Change: {result.prediction:+.2f}% ({result.confidence:.1%} conf)")
                    report.append(f"  Annualized: {result.metadata.get('annualized_rate', 'N/A'):.1f}%")
                elif indicator.startswith('fx_'):
                    pair = indicator.replace('fx_', '')
                    report.append(f"• {pair}: {result.direction} {abs(result.metadata.get('percent_change', 0)):.2f}%")
                    report.append(f"  Rate: {result.prediction:.4f} ({result.confidence:.1%} conf)")
                elif indicator.startswith('equity_'):
                    index = indicator.replace('equity_', '')
                    report.append(f"• {index}: {result.prediction:+.2f}% ({result.direction})")
                    report.append(f"  Confidence: {result.confidence:.1%} | 1-week forecast")
                elif indicator.startswith('commodity_'):
                    commodity = indicator.replace('commodity_', '').upper()
                    report.append(f"• {commodity}: {result.prediction:+.2f}% ({result.direction})")
                    report.append(f"  Confidence: {result.confidence:.1%}")
                elif indicator == 'gpr_index':
                    report.append(f"• Geopolitical Risk: {result.prediction:.1f}/100 ({result.direction})")
                elif indicator == 'consumer_confidence':
                    report.append(f"• Consumer Confidence: {result.prediction:.1f}/100")
                    report.append(f"  Trend: {result.direction} | MoM: {result.metadata.get('month_over_month', 0):+.1f}")

                # Add drivers
                if result.drivers:
                    report.append(f"  Key drivers: {', '.join(result.drivers[:2])}")

        report.extend([
            "",
            "=" * 80,
            "Note: Predictions are based on sentiment analysis and should be used alongside",
            "traditional fundamental and technical analysis for investment decisions.",
            "=" * 80
        ])

        return "\n".join(report)


# Export main class
__all__ = ['ComprehensiveEconomicPredictor', 'PredictionResult']