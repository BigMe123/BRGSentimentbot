#!/usr/bin/env python
"""
UK-specific adapters for economic indicators
Standardizes UK data into common schema without US bias
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional, List, Tuple
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')


class UKIndicatorAdapter:
    """UK-specific economic indicator adapter"""

    def __init__(self):
        self.country = 'UK'
        self.baseline_gdp = 1.5  # UK baseline growth ~1.5%
        self.services_weight = 0.8  # UK is 80% services

        # UK-specific indicator weights
        self.indicator_weights = {
            'pmi_services': 0.35,      # Most important for UK
            'pmi_manufacturing': 0.15,  # Less important than US
            'retail_sales': 0.20,
            'construction': 0.10,
            'consumer_confidence': 0.15,
            'gbp_neer': 0.05          # FX sensitivity
        }

        # Historical volatility for scaling
        self.historical_volatility = {
            'gdp': 2.8,           # UK GDP volatility
            'pmi': 5.2,           # PMI volatility
            'retail': 3.5,        # Retail volatility
            'fx': 8.0,            # FX volatility
            'confidence': 12.0     # Consumer confidence volatility
        }

        # Load cached UK data (in production, fetch from ONS/PMI/BoE APIs)
        self.indicators = self._load_uk_indicators()

    def _load_uk_indicators(self) -> pd.DataFrame:
        """Load/simulate UK-specific indicators"""
        # In production: fetch from ONS, S&P Global, BoE
        # For now, create realistic UK economic data

        dates = pd.date_range(start='2016-01-01', end='2023-12-31', freq='M')
        n = len(dates)

        # Base trends
        trend = np.linspace(0, 1, n)
        seasonal = np.sin(np.arange(n) * 2 * np.pi / 12) * 0.3

        # UK-specific patterns
        brexit_impact = np.zeros(n)
        brexit_start = pd.Timestamp('2016-06-01')
        brexit_end = pd.Timestamp('2020-01-31')
        brexit_mask = (dates >= brexit_start) & (dates <= brexit_end)
        brexit_impact[brexit_mask] = -0.5  # Brexit drag

        covid_impact = np.zeros(n)
        covid_mask = (dates >= '2020-03-01') & (dates <= '2021-06-01')
        covid_impact[covid_mask] = np.array([-5, -20, -15, -8, -3, -2, -1, 0, 2, 5, 8, 10, 12, 8, 5, 3])[:sum(covid_mask)]

        # Generate indicators
        data = pd.DataFrame({
            'date': dates,
            'pmi_services': 52 + trend * 2 + seasonal * 3 + brexit_impact * 5 + covid_impact * 2 + np.random.normal(0, 2, n),
            'pmi_manufacturing': 50 + trend * 1 + seasonal * 2 + brexit_impact * 8 + covid_impact * 3 + np.random.normal(0, 3, n),
            'retail_sales': 100 + trend * 5 + seasonal * 4 + brexit_impact * 3 + covid_impact * 5 + np.random.normal(0, 2, n),
            'construction_output': 100 + trend * 3 + seasonal * 2 + brexit_impact * 4 + covid_impact * 8 + np.random.normal(0, 3, n),
            'consumer_confidence': -10 + trend * 2 + seasonal * 5 + brexit_impact * 15 + covid_impact * 4 + np.random.normal(0, 5, n),
            'gbp_neer': 100 + trend * -5 + brexit_impact * 10 + covid_impact * 2 + np.random.normal(0, 3, n),
            'unemployment_rate': 4.5 + trend * -0.5 + brexit_impact * 0.5 + covid_impact * 0.3 + np.random.normal(0, 0.2, n),
            'inflation_cpih': 2.0 + trend * 0.5 + brexit_impact * 0.3 + covid_impact * -0.5 + np.random.normal(0, 0.3, n),
            'yield_curve_10y_3m': 1.5 + trend * -0.3 + brexit_impact * -0.2 + covid_impact * -0.8 + np.random.normal(0, 0.2, n),
            'mortgage_approvals': 65000 + trend * 5000 + seasonal * 3000 + brexit_impact * -10000 + covid_impact * -20000 + np.random.normal(0, 5000, n),
            'stringency_index': np.where(covid_mask, np.where(covid_mask, np.random.uniform(40, 90, n), 0), 0)
        })

        # Clip to realistic ranges
        data['pmi_services'] = np.clip(data['pmi_services'], 20, 70)
        data['pmi_manufacturing'] = np.clip(data['pmi_manufacturing'], 20, 70)
        data['consumer_confidence'] = np.clip(data['consumer_confidence'], -50, 10)
        data['unemployment_rate'] = np.clip(data['unemployment_rate'], 3, 10)
        data['inflation_cpih'] = np.clip(data['inflation_cpih'], -1, 10)

        return data

    def prepare_features(self, date: datetime, sentiment_score: float,
                        topic_factors: Dict, lookback_months: int = 3) -> Dict:
        """
        Prepare UK-specific features for model input

        Args:
            date: Prediction date
            sentiment_score: Sentiment from text analysis
            topic_factors: Topic-based economic factors
            lookback_months: Months of data to average

        Returns:
            Dictionary of standardized features
        """

        # Get relevant indicator data
        end_date = pd.Timestamp(date)
        start_date = end_date - pd.DateOffset(months=lookback_months)

        mask = (self.indicators['date'] >= start_date) & (self.indicators['date'] <= end_date)
        recent_data = self.indicators[mask].mean()

        # Calculate UK-specific transformations
        features = {}

        # 1. PMI composite (services-weighted for UK)
        features['pmi_composite'] = (
            recent_data['pmi_services'] * self.services_weight +
            recent_data['pmi_manufacturing'] * (1 - self.services_weight)
        )

        # 2. PMI momentum (3m change)
        if len(self.indicators) > lookback_months + 3:
            prev_mask = mask.shift(3)
            prev_data = self.indicators[prev_mask].mean()
            features['pmi_momentum'] = features['pmi_composite'] - (
                prev_data['pmi_services'] * self.services_weight +
                prev_data['pmi_manufacturing'] * (1 - self.services_weight)
            )
        else:
            features['pmi_momentum'] = 0

        # 3. Retail strength
        features['retail_strength'] = (recent_data['retail_sales'] - 100) / 10

        # 4. Construction activity
        features['construction_activity'] = (recent_data['construction_output'] - 100) / 10

        # 5. Consumer sentiment
        features['consumer_sentiment'] = recent_data['consumer_confidence'] / 10

        # 6. FX impact (GBP weakness = inflation pressure)
        features['fx_impact'] = -(recent_data['gbp_neer'] - 100) / 10

        # 7. Labor market
        features['labor_tightness'] = -recent_data['unemployment_rate'] + 5  # Inverted

        # 8. Inflation pressure
        features['inflation_pressure'] = recent_data['inflation_cpih'] - 2  # vs target

        # 9. Yield curve
        features['yield_curve'] = recent_data['yield_curve_10y_3m']

        # 10. Housing (UK-specific)
        features['housing_activity'] = (recent_data['mortgage_approvals'] - 65000) / 10000

        # 11. Policy stringency (COVID)
        features['stringency'] = recent_data['stringency_index'] / 100

        # 12. Brexit/EU trade impact (post-2021)
        features['brexit_friction'] = 1.0 if date >= datetime(2021, 1, 1) else 0.0

        # Add sentiment and topic factors
        features['sentiment'] = sentiment_score
        for factor, value in topic_factors.items():
            features[f'topic_{factor}'] = value

        # Country-specific z-score normalization (5-year rolling window)
        features = self._normalize_features(features, date)

        return features

    def _normalize_features(self, features: Dict, date: datetime) -> Dict:
        """
        Normalize features using UK-specific rolling statistics
        Prevents US-centric bias in coefficients
        """

        normalized = {}

        for key, value in features.items():
            if key.startswith('topic_') or key == 'sentiment':
                # Don't normalize sentiment/topics
                normalized[key] = value
            elif key in ['pmi_composite', 'pmi_momentum']:
                # PMI has known scale
                normalized[key] = (value - 50) / self.historical_volatility['pmi']
            elif key in ['fx_impact', 'gbp_neer']:
                normalized[key] = value / self.historical_volatility['fx']
            elif key == 'consumer_sentiment':
                normalized[key] = value / self.historical_volatility['confidence']
            else:
                # Generic normalization
                normalized[key] = value / self.historical_volatility.get('gdp', 2.8)

        return normalized

    def bridge_to_quarterly(self, monthly_features: List[Dict]) -> Dict:
        """
        Bridge monthly indicators to quarterly GDP
        Uses UK-specific aggregation rules
        """

        if len(monthly_features) != 3:
            raise ValueError("Need exactly 3 months for quarterly bridging")

        quarterly = {}

        # Different aggregation rules for different indicators
        for key in monthly_features[0].keys():
            if key in ['pmi_composite', 'pmi_momentum', 'consumer_sentiment']:
                # Average for sentiment/survey data
                quarterly[key] = np.mean([m[key] for m in monthly_features])
            elif key in ['retail_strength', 'construction_activity']:
                # Sum for activity data (cumulative effect)
                quarterly[key] = np.sum([m[key] for m in monthly_features]) / 3
            elif key in ['yield_curve', 'fx_impact', 'inflation_pressure']:
                # End-of-period for financial data
                quarterly[key] = monthly_features[-1][key]
            elif key == 'stringency':
                # Maximum for policy restrictions
                quarterly[key] = np.max([m[key] for m in monthly_features])
            else:
                # Default to average
                quarterly[key] = np.mean([m[key] for m in monthly_features])

        return quarterly

    def get_crisis_features(self, features: Dict) -> Dict:
        """
        Extract UK-specific crisis detection features
        """

        crisis_features = {
            'pmi_shock': 1 if features.get('pmi_composite', 50) < 45 else 0,
            'pmi_services_collapse': 1 if features.get('pmi_services', 50) < 40 else 0,
            'fx_crisis': 1 if abs(features.get('fx_impact', 0)) > 2 else 0,
            'yield_inversion': 1 if features.get('yield_curve', 0) < 0 else 0,
            'stringency_high': 1 if features.get('stringency', 0) > 0.5 else 0,
            'confidence_collapse': 1 if features.get('consumer_sentiment', 0) < -2 else 0,
            'brexit_stress': features.get('brexit_friction', 0) * (1 if features.get('pmi_composite', 50) < 48 else 0)
        }

        return crisis_features

    def apply_country_prior(self, prediction: float, volatility_regime: str = 'normal') -> float:
        """
        Apply UK-specific priors to scale predictions appropriately
        """

        # UK has lower baseline growth and different volatility
        uk_scaling = {
            'normal': 0.6,     # UK growth typically 60% of US
            'expansion': 0.7,  # UK expansions more modest
            'crisis': 1.2      # UK crises can be severe (Brexit, COVID)
        }

        scaled = prediction * uk_scaling.get(volatility_regime, 0.6)

        # Apply UK baseline
        if abs(scaled) < 0.5:  # Near zero
            scaled = scaled * 0.5 + self.baseline_gdp * 0.5  # Blend toward UK baseline

        return scaled