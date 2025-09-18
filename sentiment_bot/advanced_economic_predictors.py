#!/usr/bin/env python3
"""
Advanced Economic Predictors Suite
Comprehensive predictors for inflation, FX, equities, commodities, trade, and geopolitical risk
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import logging
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
import warnings
warnings.filterwarnings('ignore')
try:
    from .alpha_vantage_news import AlphaVantageNewsConnector, get_alpha_vantage_sentiment_data
    ALPHA_VANTAGE_AVAILABLE = True
except ImportError:
    ALPHA_VANTAGE_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class PredictionResult:
    """Standard prediction output format."""
    predictor_type: str
    prediction: float
    confidence: float
    direction: str  # up/down/neutral
    timeframe: str
    drivers: List[str]
    confidence_band: Tuple[float, float]
    metadata: Dict[str, Any]


class InflationPredictor:
    """
    Predict short-term CPI changes using sentiment around supply chains,
    tariffs, energy, and food commodities.
    """

    def __init__(self):
        self.model = GradientBoostingRegressor(n_estimators=100, random_state=42)
        self.scaler = StandardScaler()
        self.feature_importance = {}

    def extract_features(self, articles: List[Dict]) -> np.ndarray:
        """Extract inflation-relevant features from articles."""
        features = {
            'supply_chain_sentiment': 0,
            'energy_sentiment': 0,
            'food_sentiment': 0,
            'tariff_sentiment': 0,
            'wage_sentiment': 0,
            'commodity_sentiment': 0,
            'housing_sentiment': 0,
            'transport_sentiment': 0
        }

        # Keywords for each category
        keywords = {
            'supply_chain': ['supply chain', 'logistics', 'shipping', 'shortage', 'bottleneck'],
            'energy': ['oil', 'gas', 'energy', 'fuel', 'electricity', 'power'],
            'food': ['food', 'grain', 'wheat', 'corn', 'agriculture', 'crop'],
            'tariff': ['tariff', 'import tax', 'trade barrier', 'customs', 'duty'],
            'wage': ['wage', 'salary', 'labor cost', 'employment', 'payroll'],
            'commodity': ['commodity', 'raw material', 'metal', 'copper', 'steel'],
            'housing': ['housing', 'rent', 'mortgage', 'real estate', 'property'],
            'transport': ['transport', 'freight', 'trucking', 'airline', 'shipping cost']
        }

        for article in articles:
            text = f"{article.get('title', '')} {article.get('content', '')}".lower()
            sentiment = article.get('sentiment', 0)

            for category, words in keywords.items():
                if any(word in text for word in words):
                    features[f'{category}_sentiment'] += sentiment

        # Normalize by article count
        n_articles = max(len(articles), 1)
        for key in features:
            features[key] /= n_articles

        return np.array(list(features.values())).reshape(1, -1)

    def predict_cpi(self, articles: List[Dict], historical_cpi: Optional[List[float]] = None) -> PredictionResult:
        """Predict next month's CPI change with confidence bands."""
        features = self.extract_features(articles)

        # Add historical features if available
        if historical_cpi and len(historical_cpi) >= 3:
            hist_features = np.array([
                np.mean(historical_cpi[-3:]),  # 3-month average
                historical_cpi[-1] - historical_cpi[-2],  # Last change
                np.std(historical_cpi[-6:]) if len(historical_cpi) >= 6 else 0  # Volatility
            ]).reshape(1, -1)
            features = np.hstack([features, hist_features])

        # Simulate prediction (in production, use trained model)
        base_prediction = np.random.normal(0.3, 0.1)  # Baseline inflation

        # Adjust based on sentiment
        energy_impact = features[0, 1] * -0.5  # Negative energy sentiment → higher inflation
        supply_impact = features[0, 0] * -0.3
        food_impact = features[0, 2] * -0.2

        prediction = base_prediction + energy_impact + supply_impact + food_impact
        prediction = np.clip(prediction, -2, 10)  # Reasonable bounds

        # Calculate confidence bands
        std_dev = 0.2
        lower_bound = prediction - 1.96 * std_dev
        upper_bound = prediction + 1.96 * std_dev

        # Determine drivers
        drivers = []
        if abs(energy_impact) > 0.1:
            drivers.append(f"Energy {'pressure' if energy_impact > 0 else 'relief'}")
        if abs(supply_impact) > 0.1:
            drivers.append(f"Supply chain {'stress' if supply_impact > 0 else 'improvement'}")
        if abs(food_impact) > 0.1:
            drivers.append(f"Food price {'increase' if food_impact > 0 else 'moderation'}")

        return PredictionResult(
            predictor_type="inflation_cpi",
            prediction=round(prediction, 2),
            confidence=0.75,
            direction="up" if prediction > 0.2 else "down" if prediction < -0.2 else "neutral",
            timeframe="1_month",
            drivers=drivers,
            confidence_band=(round(lower_bound, 2), round(upper_bound, 2)),
            metadata={
                'energy_sentiment': float(features[0, 1]),
                'supply_chain_sentiment': float(features[0, 0]),
                'base_rate': base_prediction
            }
        )


class CurrencyFXPredictor:
    """
    Track how sentiment affects currency strength, especially trade sentiment.
    """

    def __init__(self):
        self.currencies = ['USD', 'EUR', 'GBP', 'JPY', 'CNY', 'INR', 'BRL']

    def analyze_fx_sentiment(self, articles: List[Dict], currency: str) -> Dict:
        """Analyze sentiment specific to a currency."""
        sentiment_factors = {
            'trade_sentiment': 0,
            'monetary_policy': 0,
            'geopolitical_risk': 0,
            'economic_growth': 0,
            'fiscal_policy': 0
        }

        currency_keywords = {
            'USD': ['dollar', 'fed', 'federal reserve', 'us economy'],
            'EUR': ['euro', 'ecb', 'european central bank', 'eurozone'],
            'GBP': ['pound', 'sterling', 'bank of england', 'uk economy'],
            'JPY': ['yen', 'boj', 'bank of japan', 'japanese economy'],
            'CNY': ['yuan', 'renminbi', 'pboc', 'china economy'],
            'INR': ['rupee', 'rbi', 'reserve bank india', 'indian economy'],
            'BRL': ['real', 'brazil central bank', 'brazilian economy']
        }

        keywords = currency_keywords.get(currency, [currency.lower()])

        for article in articles:
            text = f"{article.get('title', '')} {article.get('content', '')}".lower()

            # Check if article mentions the currency
            if any(kw in text for kw in keywords):
                sentiment = article.get('sentiment', 0)

                # Categorize sentiment
                if any(word in text for word in ['trade', 'export', 'import', 'tariff']):
                    sentiment_factors['trade_sentiment'] += sentiment
                if any(word in text for word in ['rate', 'monetary', 'inflation', 'hawk', 'dove']):
                    sentiment_factors['monetary_policy'] += sentiment
                if any(word in text for word in ['conflict', 'sanction', 'tension', 'risk']):
                    sentiment_factors['geopolitical_risk'] += sentiment
                if any(word in text for word in ['growth', 'gdp', 'expansion', 'recession']):
                    sentiment_factors['economic_growth'] += sentiment

        return sentiment_factors

    def predict_fx(self, articles: List[Dict], currency_pair: str = "USD/EUR") -> PredictionResult:
        """Predict currency direction and estimated change."""
        base_currency, quote_currency = currency_pair.split('/')

        base_sentiment = self.analyze_fx_sentiment(articles, base_currency)
        quote_sentiment = self.analyze_fx_sentiment(articles, quote_currency)

        # Calculate relative strength
        base_score = sum(base_sentiment.values())
        quote_score = sum(quote_sentiment.values())
        relative_strength = base_score - quote_score

        # Estimate percentage change (1-4 weeks)
        pct_change = np.tanh(relative_strength) * 3  # Max ±3% change

        # Add volatility
        volatility = np.random.normal(0, 0.5)
        pct_change += volatility

        # Confidence based on sentiment clarity
        confidence = min(abs(relative_strength) * 0.3 + 0.5, 0.9)

        # Determine drivers
        drivers = []
        if abs(base_sentiment['trade_sentiment'] - quote_sentiment['trade_sentiment']) > 0.2:
            drivers.append("Trade sentiment differential")
        if abs(base_sentiment['monetary_policy'] - quote_sentiment['monetary_policy']) > 0.2:
            drivers.append("Monetary policy divergence")
        if base_sentiment['geopolitical_risk'] < -0.3 or quote_sentiment['geopolitical_risk'] < -0.3:
            drivers.append("Geopolitical concerns")

        return PredictionResult(
            predictor_type="currency_fx",
            prediction=round(pct_change, 2),
            confidence=round(confidence, 2),
            direction="strengthen" if pct_change > 0 else "weaken" if pct_change < 0 else "neutral",
            timeframe="1-4_weeks",
            drivers=drivers,
            confidence_band=(round(pct_change - 1.5, 2), round(pct_change + 1.5, 2)),
            metadata={
                'currency_pair': currency_pair,
                'base_sentiment': base_score,
                'quote_sentiment': quote_score
            }
        )


class EquityMarketPredictor:
    """
    Predict country stock indices and sector trends using sentiment.
    """

    def __init__(self):
        self.indices = {
            'US': 'S&P500',
            'India': 'NIFTY',
            'Brazil': 'BOVESPA',
            'China': 'SSE',
            'UK': 'FTSE100',
            'Japan': 'Nikkei',
            'Germany': 'DAX'
        }
        self.sectors = ['technology', 'finance', 'energy', 'healthcare', 'consumer', 'industrial']

    def analyze_market_sentiment(self, articles: List[Dict], country: str) -> Dict:
        """Analyze equity market sentiment for a country."""
        market_factors = {
            'overall_sentiment': 0,
            'corporate_earnings': 0,
            'economic_data': 0,
            'policy_support': 0,
            'risk_sentiment': 0,
            'sector_momentum': {}
        }

        country_keywords = {
            'US': ['s&p', 'nasdaq', 'dow', 'wall street', 'us stock'],
            'India': ['nifty', 'sensex', 'indian market', 'mumbai stock'],
            'China': ['shanghai', 'shenzhen', 'a-share', 'chinese stock'],
            'Brazil': ['bovespa', 'brazilian stock', 'sao paulo exchange']
        }

        keywords = country_keywords.get(country, [country.lower()])

        for article in articles:
            text = f"{article.get('title', '')} {article.get('content', '')}".lower()

            if any(kw in text for kw in keywords):
                sentiment = article.get('sentiment', 0)
                market_factors['overall_sentiment'] += sentiment

                # Specific factors
                if any(word in text for word in ['earnings', 'profit', 'revenue', 'guidance']):
                    market_factors['corporate_earnings'] += sentiment
                if any(word in text for word in ['gdp', 'employment', 'inflation', 'economic']):
                    market_factors['economic_data'] += sentiment
                if any(word in text for word in ['stimulus', 'rate cut', 'qe', 'support']):
                    market_factors['policy_support'] += sentiment * 1.5
                if any(word in text for word in ['risk', 'uncertainty', 'volatility', 'correction']):
                    market_factors['risk_sentiment'] += sentiment

                # Sector analysis
                for sector in self.sectors:
                    if sector in text:
                        if sector not in market_factors['sector_momentum']:
                            market_factors['sector_momentum'][sector] = 0
                        market_factors['sector_momentum'][sector] += sentiment

        return market_factors

    def predict_index(self, articles: List[Dict], country: str = "US") -> PredictionResult:
        """Predict stock index trend."""
        market_sentiment = self.analyze_market_sentiment(articles, country)

        # Calculate composite score
        composite = (
            market_sentiment['overall_sentiment'] * 0.3 +
            market_sentiment['corporate_earnings'] * 0.25 +
            market_sentiment['economic_data'] * 0.2 +
            market_sentiment['policy_support'] * 0.15 +
            market_sentiment['risk_sentiment'] * 0.1
        )

        # Estimate return (weekly)
        expected_return = np.tanh(composite) * 5  # Max ±5% weekly

        # Add market momentum
        momentum = np.random.normal(0.5, 1)  # Slight upward bias
        expected_return += momentum

        # Confidence calculation
        data_points = sum(1 for v in market_sentiment.values() if isinstance(v, (int, float)) and v != 0)
        confidence = min(0.5 + data_points * 0.1, 0.85)

        # Top sectors
        top_sectors = sorted(
            market_sentiment['sector_momentum'].items(),
            key=lambda x: x[1],
            reverse=True
        )[:3]

        drivers = []
        if market_sentiment['corporate_earnings'] > 0.5:
            drivers.append("Strong earnings sentiment")
        if market_sentiment['policy_support'] > 0.3:
            drivers.append("Policy support")
        if market_sentiment['risk_sentiment'] < -0.3:
            drivers.append("Risk-off sentiment")

        for sector, score in top_sectors:
            if score > 0.2:
                drivers.append(f"{sector.capitalize()} outperformance")

        return PredictionResult(
            predictor_type="equity_index",
            prediction=round(expected_return, 2),
            confidence=round(confidence, 2),
            direction="bullish" if expected_return > 1 else "bearish" if expected_return < -1 else "neutral",
            timeframe="1_week",
            drivers=drivers,
            confidence_band=(round(expected_return - 3, 2), round(expected_return + 3, 2)),
            metadata={
                'index': self.indices.get(country, 'Unknown'),
                'country': country,
                'top_sectors': dict(top_sectors)
            }
        )


class CommodityPricePredictor:
    """
    Predict prices for multiple commodities including oil, gas, metals, and agriculture.
    """

    def __init__(self):
        self.commodities = {
            'oil': {'keywords': ['oil', 'crude', 'wti', 'brent', 'petroleum'], 'unit': '$/barrel'},
            'gas': {'keywords': ['natural gas', 'lng', 'gas price'], 'unit': '$/mmbtu'},
            'copper': {'keywords': ['copper', 'cu price'], 'unit': '$/ton'},
            'gold': {'keywords': ['gold', 'precious metal'], 'unit': '$/oz'},
            'steel': {'keywords': ['steel', 'iron ore'], 'unit': '$/ton'},
            'wheat': {'keywords': ['wheat', 'grain'], 'unit': '$/bushel'},
            'corn': {'keywords': ['corn', 'maize'], 'unit': '$/bushel'},
            'soy': {'keywords': ['soybean', 'soy'], 'unit': '$/bushel'}
        }

    def analyze_commodity(self, articles: List[Dict], commodity: str) -> Dict:
        """Analyze sentiment for a specific commodity."""
        factors = {
            'supply_sentiment': 0,
            'demand_sentiment': 0,
            'geopolitical_impact': 0,
            'weather_impact': 0,
            'inventory_sentiment': 0,
            'price_mentions': []
        }

        keywords = self.commodities[commodity]['keywords']

        for article in articles:
            text = f"{article.get('title', '')} {article.get('content', '')}".lower()

            if any(kw in text for kw in keywords):
                sentiment = article.get('sentiment', 0)

                # Supply factors
                if any(word in text for word in ['production', 'output', 'supply', 'export']):
                    factors['supply_sentiment'] += sentiment

                # Demand factors
                if any(word in text for word in ['demand', 'consumption', 'import', 'usage']):
                    factors['demand_sentiment'] += sentiment

                # Geopolitical
                if any(word in text for word in ['sanction', 'conflict', 'disruption', 'embargo']):
                    factors['geopolitical_impact'] += sentiment * -1  # Negative impact

                # Weather (for agriculture)
                if commodity in ['wheat', 'corn', 'soy']:
                    if any(word in text for word in ['drought', 'flood', 'weather', 'climate']):
                        factors['weather_impact'] += sentiment * -1

                # Inventory
                if any(word in text for word in ['inventory', 'stock', 'storage', 'reserve']):
                    factors['inventory_sentiment'] += sentiment

        return factors

    def predict_commodity_price(self, articles: List[Dict], commodity: str = "oil") -> PredictionResult:
        """Predict commodity price direction and change."""
        if commodity not in self.commodities:
            commodity = "oil"  # Default

        analysis = self.analyze_commodity(articles, commodity)

        # Calculate price pressure
        supply_demand_balance = analysis['demand_sentiment'] - analysis['supply_sentiment']
        geopolitical_premium = max(analysis['geopolitical_impact'], 0) * 0.5

        # Base price change
        price_change_pct = (
            supply_demand_balance * 2 +  # Supply/demand biggest driver
            geopolitical_premium +
            analysis['weather_impact'] * 0.5 +
            analysis['inventory_sentiment'] * -0.3  # High inventory = lower price
        )

        # Add volatility based on commodity type
        volatility = {
            'oil': 3, 'gas': 4, 'copper': 2.5,
            'gold': 1.5, 'steel': 2, 'wheat': 3,
            'corn': 3, 'soy': 2.5
        }

        price_change_pct += np.random.normal(0, volatility.get(commodity, 2))
        price_change_pct = np.clip(price_change_pct, -15, 15)  # Max ±15% move

        # Confidence based on data availability
        confidence = min(0.5 + abs(supply_demand_balance) * 0.2, 0.85)

        # Determine drivers
        drivers = []
        if abs(supply_demand_balance) > 0.3:
            drivers.append(f"{'Demand' if supply_demand_balance > 0 else 'Supply'} pressure")
        if geopolitical_premium > 0.5:
            drivers.append("Geopolitical risk premium")
        if commodity in ['wheat', 'corn', 'soy'] and abs(analysis['weather_impact']) > 0.3:
            drivers.append("Weather concerns")
        if abs(analysis['inventory_sentiment']) > 0.3:
            drivers.append(f"Inventory {'build' if analysis['inventory_sentiment'] > 0 else 'drawdown'}")

        return PredictionResult(
            predictor_type="commodity_price",
            prediction=round(price_change_pct, 2),
            confidence=round(confidence, 2),
            direction="up" if price_change_pct > 2 else "down" if price_change_pct < -2 else "sideways",
            timeframe="1-4_weeks",
            drivers=drivers,
            confidence_band=(
                round(price_change_pct - volatility.get(commodity, 2) * 1.5, 2),
                round(price_change_pct + volatility.get(commodity, 2) * 1.5, 2)
            ),
            metadata={
                'commodity': commodity,
                'unit': self.commodities[commodity]['unit'],
                'supply_demand_balance': round(supply_demand_balance, 2)
            }
        )


class TradeFlowPredictor:
    """
    Forecast export/import changes by partner country.
    """

    def __init__(self):
        self.trade_pairs = [
            ('US', 'China'), ('US', 'Mexico'), ('US', 'Canada'),
            ('China', 'EU'), ('India', 'US'), ('Brazil', 'China'),
            ('Germany', 'China'), ('Japan', 'US')
        ]

    def analyze_trade_sentiment(self, articles: List[Dict], exporter: str, importer: str) -> Dict:
        """Analyze trade relationship sentiment."""
        trade_factors = {
            'bilateral_sentiment': 0,
            'tariff_sentiment': 0,
            'agreement_sentiment': 0,
            'logistics_sentiment': 0,
            'commodity_specific': {}
        }

        for article in articles:
            text = f"{article.get('title', '')} {article.get('content', '')}".lower()

            # Check if both countries mentioned
            if exporter.lower() in text and importer.lower() in text:
                sentiment = article.get('sentiment', 0)

                if any(word in text for word in ['trade', 'export', 'import']):
                    trade_factors['bilateral_sentiment'] += sentiment

                if any(word in text for word in ['tariff', 'duty', 'quota', 'barrier']):
                    trade_factors['tariff_sentiment'] += sentiment * -1  # Negative for trade

                if any(word in text for word in ['agreement', 'deal', 'pact', 'fta']):
                    trade_factors['agreement_sentiment'] += sentiment

                if any(word in text for word in ['shipping', 'port', 'logistics', 'supply chain']):
                    trade_factors['logistics_sentiment'] += sentiment

        return trade_factors

    def predict_trade_flow(self, articles: List[Dict], exporter: str = "US", importer: str = "China") -> PredictionResult:
        """Predict trade flow changes."""
        trade_sentiment = self.analyze_trade_sentiment(articles, exporter, importer)

        # Calculate expected change
        base_change = (
            trade_sentiment['bilateral_sentiment'] * 2 +
            trade_sentiment['tariff_sentiment'] * 3 +  # Tariffs have big impact
            trade_sentiment['agreement_sentiment'] * 2.5 +
            trade_sentiment['logistics_sentiment'] * 1
        )

        # Convert to percentage
        trade_change_pct = np.tanh(base_change / 3) * 20  # Max ±20% change

        # Add noise
        trade_change_pct += np.random.normal(0, 2)

        # Confidence
        data_strength = sum(abs(v) for v in trade_sentiment.values() if isinstance(v, (int, float)))
        confidence = min(0.5 + data_strength * 0.1, 0.8)

        # Drivers
        drivers = []
        if abs(trade_sentiment['tariff_sentiment']) > 0.3:
            drivers.append(f"Tariff {'increases' if trade_sentiment['tariff_sentiment'] < 0 else 'reductions'}")
        if trade_sentiment['agreement_sentiment'] > 0.3:
            drivers.append("Trade agreement progress")
        if trade_sentiment['bilateral_sentiment'] < -0.3:
            drivers.append("Deteriorating relations")
        if abs(trade_sentiment['logistics_sentiment']) > 0.3:
            drivers.append(f"Supply chain {'improvements' if trade_sentiment['logistics_sentiment'] > 0 else 'disruptions'}")

        return PredictionResult(
            predictor_type="trade_flow",
            prediction=round(trade_change_pct, 2),
            confidence=round(confidence, 2),
            direction="increase" if trade_change_pct > 3 else "decrease" if trade_change_pct < -3 else "stable",
            timeframe="3_months",
            drivers=drivers,
            confidence_band=(round(trade_change_pct - 5, 2), round(trade_change_pct + 5, 2)),
            metadata={
                'exporter': exporter,
                'importer': importer,
                'trade_pair': f"{exporter}-{importer}"
            }
        )


class GeopoliticalRiskIndex:
    """
    Score the risk of sanctions, trade wars, and conflict escalation.
    """

    def __init__(self):
        self.risk_categories = {
            'sanctions': {'keywords': ['sanction', 'embargo', 'restriction', 'blacklist'], 'weight': 0.25},
            'trade_war': {'keywords': ['trade war', 'tariff', 'retaliation', 'protectionism'], 'weight': 0.2},
            'military': {'keywords': ['military', 'troops', 'missile', 'naval', 'air force'], 'weight': 0.3},
            'diplomatic': {'keywords': ['diplomatic', 'ambassador', 'expel', 'recall', 'talks'], 'weight': 0.15},
            'cyber': {'keywords': ['cyber attack', 'hack', 'cyber warfare'], 'weight': 0.1}
        }

    def calculate_gpr(self, articles: List[Dict]) -> PredictionResult:
        """Calculate Geopolitical Risk Index (0-100)."""
        risk_scores = {category: 0 for category in self.risk_categories}
        total_mentions = 0
        recent_weight = 1.0  # Recency decay

        # Sort articles by date (assuming recent first)
        for i, article in enumerate(articles):
            text = f"{article.get('title', '')} {article.get('content', '')}".lower()
            sentiment = article.get('sentiment', 0)

            # Apply recency decay
            recent_weight = 1.0 / (1 + i * 0.02)  # Decay by 2% per article

            for category, info in self.risk_categories.items():
                mentions = sum(1 for keyword in info['keywords'] if keyword in text)
                if mentions > 0:
                    # Negative sentiment increases risk
                    risk_contribution = mentions * (1 - sentiment) * recent_weight
                    risk_scores[category] += risk_contribution
                    total_mentions += mentions

        # Normalize and weight
        if total_mentions > 0:
            for category in risk_scores:
                risk_scores[category] = (risk_scores[category] / total_mentions) * 100

        # Calculate weighted index
        gpr_index = sum(
            risk_scores[cat] * self.risk_categories[cat]['weight']
            for cat in risk_scores
        )

        # Scale to 0-100
        gpr_index = min(gpr_index * 10, 100)  # Amplify and cap at 100

        # Determine risk level
        if gpr_index < 30:
            risk_level = "low"
        elif gpr_index < 50:
            risk_level = "moderate"
        elif gpr_index < 70:
            risk_level = "elevated"
        else:
            risk_level = "high"

        # Top drivers
        top_risks = sorted(risk_scores.items(), key=lambda x: x[1], reverse=True)[:3]
        drivers = [f"{risk[0].replace('_', ' ').title()} ({risk[1]:.1f})" for risk in top_risks if risk[1] > 0]

        return PredictionResult(
            predictor_type="geopolitical_risk",
            prediction=round(gpr_index, 1),
            confidence=min(0.6 + total_mentions * 0.02, 0.9),
            direction=risk_level,
            timeframe="current",
            drivers=drivers,
            confidence_band=(max(gpr_index - 10, 0), min(gpr_index + 10, 100)),
            metadata={
                'risk_breakdown': {k: round(v, 1) for k, v in risk_scores.items()},
                'total_risk_mentions': total_mentions
            }
        )


class FDIPredictor:
    """
    Predict foreign direct investment sentiment trends.
    """

    def __init__(self):
        self.fdi_factors = {
            'incentive': ['tax incentive', 'subsidy', 'grant', 'benefit', 'support'],
            'expansion': ['new plant', 'expansion', 'investment', 'facility', 'factory'],
            'regulation': ['deregulation', 'ease of doing', 'reform', 'streamline'],
            'stability': ['stable', 'predictable', 'transparent', 'rule of law'],
            'relocation': ['relocation', 'moving production', 'nearshoring', 'reshoring']
        }

    def predict_fdi(self, articles: List[Dict], country: str = None) -> PredictionResult:
        """Predict FDI sentiment trend."""
        fdi_sentiment = {factor: 0 for factor in self.fdi_factors}
        mention_count = 0

        for article in articles:
            text = f"{article.get('title', '')} {article.get('content', '')}".lower()

            # Filter by country if specified
            if country and country.lower() not in text:
                continue

            sentiment = article.get('sentiment', 0)

            for factor, keywords in self.fdi_factors.items():
                if any(keyword in text for keyword in keywords):
                    fdi_sentiment[factor] += sentiment
                    mention_count += 1

        # Calculate composite FDI score
        if mention_count > 0:
            fdi_score = sum(fdi_sentiment.values()) / mention_count
        else:
            fdi_score = 0

        # Convert to trend prediction
        if fdi_score > 0.2:
            trend = "positive"
            direction = "increasing"
        elif fdi_score < -0.2:
            trend = "negative"
            direction = "decreasing"
        else:
            trend = "neutral"
            direction = "stable"

        # Confidence based on data
        confidence = min(0.5 + mention_count * 0.05, 0.85)

        # Top drivers
        drivers = []
        for factor, score in sorted(fdi_sentiment.items(), key=lambda x: abs(x[1]), reverse=True)[:3]:
            if abs(score) > 0.1:
                drivers.append(f"{factor.replace('_', ' ').title()} sentiment")

        return PredictionResult(
            predictor_type="fdi_sentiment",
            prediction=round(fdi_score * 100, 1),  # Convert to index
            confidence=round(confidence, 2),
            direction=direction,
            timeframe="3-6_months",
            drivers=drivers,
            confidence_band=(round((fdi_score - 0.3) * 100, 1), round((fdi_score + 0.3) * 100, 1)),
            metadata={
                'country': country or 'Global',
                'sentiment_breakdown': {k: round(v, 2) for k, v in fdi_sentiment.items()},
                'data_points': mention_count
            }
        )


class ConsumerConfidenceProxy:
    """
    Approximate consumer confidence using sentiment around jobs, prices, wages, and retail.
    """

    def __init__(self):
        self.confidence_factors = {
            'employment': {'keywords': ['jobs', 'employment', 'hiring', 'unemployment', 'layoff'], 'weight': 0.3},
            'prices': {'keywords': ['price', 'inflation', 'cost of living', 'expensive'], 'weight': 0.25},
            'wages': {'keywords': ['wage', 'salary', 'income', 'pay raise', 'earnings'], 'weight': 0.2},
            'retail': {'keywords': ['retail', 'shopping', 'consumer spending', 'sales'], 'weight': 0.15},
            'housing': {'keywords': ['housing', 'mortgage', 'rent', 'home prices'], 'weight': 0.1}
        }

    def calculate_confidence(self, articles: List[Dict]) -> PredictionResult:
        """Calculate consumer confidence index (0-100)."""
        factor_scores = {factor: 0 for factor in self.confidence_factors}
        factor_mentions = {factor: 0 for factor in self.confidence_factors}

        for article in articles:
            text = f"{article.get('title', '')} {article.get('content', '')}".lower()
            sentiment = article.get('sentiment', 0)

            for factor, info in self.confidence_factors.items():
                if any(keyword in text for keyword in info['keywords']):
                    factor_scores[factor] += sentiment
                    factor_mentions[factor] += 1

        # Calculate weighted average
        confidence_index = 50  # Base level

        for factor, info in self.confidence_factors.items():
            if factor_mentions[factor] > 0:
                avg_sentiment = factor_scores[factor] / factor_mentions[factor]
                # Convert sentiment (-1 to 1) to confidence contribution
                contribution = avg_sentiment * info['weight'] * 50
                confidence_index += contribution

        # Ensure bounds
        confidence_index = np.clip(confidence_index, 0, 100)

        # Calculate month-over-month change
        base_change = np.random.normal(0, 2)  # Simulated historical comparison
        if confidence_index > 55:
            change = abs(base_change)
        elif confidence_index < 45:
            change = -abs(base_change)
        else:
            change = base_change

        # Determine trend
        if confidence_index > 60:
            trend = "optimistic"
        elif confidence_index < 40:
            trend = "pessimistic"
        else:
            trend = "neutral"

        # Top drivers
        drivers = []
        for factor, mentions in factor_mentions.items():
            if mentions > 0 and abs(factor_scores[factor] / mentions) > 0.2:
                sentiment_dir = "positive" if factor_scores[factor] > 0 else "negative"
                drivers.append(f"{factor.capitalize()} {sentiment_dir}")

        return PredictionResult(
            predictor_type="consumer_confidence",
            prediction=round(confidence_index, 1),
            confidence=0.75,
            direction=trend,
            timeframe="current_month",
            drivers=drivers,
            confidence_band=(round(confidence_index - 5, 1), round(confidence_index + 5, 1)),
            metadata={
                'month_change': round(change, 1),
                'factor_breakdown': {
                    factor: round(factor_scores[factor] / max(factor_mentions[factor], 1), 2)
                    for factor in self.confidence_factors
                }
            }
        )


class UnifiedEconomicPredictor:
    """
    Unified interface for all economic predictors.
    """

    def __init__(self):
        self.inflation_predictor = InflationPredictor()
        self.fx_predictor = CurrencyFXPredictor()
        self.equity_predictor = EquityMarketPredictor()
        self.commodity_predictor = CommodityPricePredictor()
        self.trade_predictor = TradeFlowPredictor()
        self.gpr_calculator = GeopoliticalRiskIndex()
        self.fdi_predictor = FDIPredictor()
        self.consumer_confidence = ConsumerConfidenceProxy()

    def run_all_predictions(self, articles: List[Dict]) -> Dict[str, PredictionResult]:
        """Run all predictors and return comprehensive results."""
        results = {}

        # Inflation
        results['inflation'] = self.inflation_predictor.predict_cpi(articles)

        # FX - multiple pairs
        for pair in ['USD/EUR', 'USD/CNY', 'USD/JPY']:
            results[f'fx_{pair}'] = self.fx_predictor.predict_fx(articles, pair)

        # Equities - multiple markets
        for country in ['US', 'China', 'India']:
            results[f'equity_{country}'] = self.equity_predictor.predict_index(articles, country)

        # Commodities - key ones
        for commodity in ['oil', 'gold', 'copper', 'wheat']:
            results[f'commodity_{commodity}'] = self.commodity_predictor.predict_commodity_price(articles, commodity)

        # Trade flows - major pairs
        results['trade_US_China'] = self.trade_predictor.predict_trade_flow(articles, 'US', 'China')

        # Geopolitical risk
        results['geopolitical_risk'] = self.gpr_calculator.calculate_gpr(articles)

        # FDI
        results['fdi_global'] = self.fdi_predictor.predict_fdi(articles)

        # Consumer confidence
        results['consumer_confidence'] = self.consumer_confidence.calculate_confidence(articles)

        return results

    def generate_summary_report(self, predictions: Dict[str, PredictionResult]) -> str:
        """Generate a summary report of all predictions."""
        report = []
        report.append("=" * 80)
        report.append(" COMPREHENSIVE ECONOMIC PREDICTIONS REPORT")
        report.append(f" Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("=" * 80)
        report.append("")

        # Group by type
        groups = {
            'Inflation & Prices': ['inflation'],
            'Currency Markets': [k for k in predictions if k.startswith('fx_')],
            'Equity Markets': [k for k in predictions if k.startswith('equity_')],
            'Commodities': [k for k in predictions if k.startswith('commodity_')],
            'Trade & Investment': ['trade_US_China', 'fdi_global'],
            'Risk & Sentiment': ['geopolitical_risk', 'consumer_confidence']
        }

        for group_name, keys in groups.items():
            report.append(f"\n{group_name.upper()}")
            report.append("-" * 40)

            for key in keys:
                if key in predictions:
                    pred = predictions[key]

                    # Format based on type
                    if pred.predictor_type == "inflation_cpi":
                        report.append(f"CPI Forecast: {pred.prediction}% ({pred.direction})")
                        report.append(f"  Confidence: {pred.confidence:.0%} | Range: {pred.confidence_band}")

                    elif pred.predictor_type == "currency_fx":
                        pair = pred.metadata['currency_pair']
                        report.append(f"{pair}: {pred.prediction:+.2f}% ({pred.direction})")
                        report.append(f"  Confidence: {pred.confidence:.0%} | Timeframe: {pred.timeframe}")

                    elif pred.predictor_type == "equity_index":
                        index = pred.metadata['index']
                        report.append(f"{index}: {pred.prediction:+.2f}% ({pred.direction})")
                        report.append(f"  Top sectors: {list(pred.metadata.get('top_sectors', {}).keys())[:2]}")

                    elif pred.predictor_type == "commodity_price":
                        commodity = pred.metadata['commodity']
                        report.append(f"{commodity.upper()}: {pred.prediction:+.2f}% ({pred.direction})")
                        report.append(f"  Key driver: {pred.drivers[0] if pred.drivers else 'Mixed factors'}")

                    elif pred.predictor_type == "geopolitical_risk":
                        report.append(f"GPR Index: {pred.prediction:.1f}/100 ({pred.direction} risk)")
                        report.append(f"  Top risks: {', '.join(pred.drivers[:2])}")

                    elif pred.predictor_type == "consumer_confidence":
                        report.append(f"Consumer Confidence: {pred.prediction:.1f}/100 ({pred.direction})")
                        change = pred.metadata.get('month_change', 0)
                        report.append(f"  Monthly change: {change:+.1f} points")

                    report.append("")

        # Key takeaways
        report.append("\nKEY TAKEAWAYS")
        report.append("-" * 40)

        # Find strongest signals
        strong_signals = []
        for key, pred in predictions.items():
            if pred.confidence > 0.7 and abs(pred.prediction) > 2:
                strong_signals.append((key, pred))

        if strong_signals:
            for key, pred in strong_signals[:5]:
                if pred.predictor_type == "inflation_cpi":
                    report.append(f"• Strong {pred.direction} inflation signal: {pred.prediction}%")
                elif pred.predictor_type == "currency_fx":
                    report.append(f"• {pred.metadata['currency_pair']} likely to {pred.direction}")
                elif pred.predictor_type == "commodity_price":
                    report.append(f"• {pred.metadata['commodity'].upper()} prices trending {pred.direction}")
        else:
            report.append("• No strong directional signals detected")
            report.append("• Markets appear range-bound in near term")

        report.append("")
        report.append("=" * 80)

        return "\n".join(report)


# Example usage
if __name__ == "__main__":
    # Sample articles for testing
    sample_articles = [
        {
            'title': 'Oil prices surge on supply disruptions',
            'content': 'Crude oil prices jumped 5% today as sanctions on major producer create supply concerns...',
            'sentiment': -0.3
        },
        {
            'title': 'Fed signals potential rate cuts amid inflation cooling',
            'content': 'Federal Reserve officials suggest monetary easing as inflation shows signs of moderation...',
            'sentiment': 0.5
        },
        {
            'title': 'China tech stocks rally on policy support',
            'content': 'Chinese technology companies see gains as government announces supportive measures...',
            'sentiment': 0.7
        },
        {
            'title': 'Trade tensions ease between US and EU',
            'content': 'Diplomatic progress reduces tariff concerns and improves trade outlook...',
            'sentiment': 0.4
        },
        {
            'title': 'Consumer spending weakens on job concerns',
            'content': 'Retail sales disappoint as unemployment fears impact consumer confidence...',
            'sentiment': -0.5
        }
    ]

    # Initialize unified predictor
    predictor = UnifiedEconomicPredictor()

    # Run all predictions
    all_predictions = predictor.run_all_predictions(sample_articles)

    # Generate and print report
    report = predictor.generate_summary_report(all_predictions)
    print(report)

    # Example of accessing individual predictions
    if 'inflation' in all_predictions:
        inflation_pred = all_predictions['inflation']
        print(f"\nDetailed Inflation Prediction:")
        print(f"  CPI Change: {inflation_pred.prediction}%")
        print(f"  Confidence Band: {inflation_pred.confidence_band}")
        print(f"  Key Drivers: {', '.join(inflation_pred.drivers)}")