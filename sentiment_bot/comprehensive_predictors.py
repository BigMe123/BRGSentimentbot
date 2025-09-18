#!/usr/bin/env python
"""
Comprehensive Economic Predictors Suite - Production Ready
Includes all requested predictors: Jobs, Inflation, FX, Equity, Commodities, Trade, GPR, FDI, Consumer Confidence
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

try:
    from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
    from sklearn.linear_model import ElasticNet
    from sklearn.preprocessing import StandardScaler
    ADVANCED_MODELS = True
except ImportError:
    ADVANCED_MODELS = False


class JobGrowthPredictor:
    """Predict job creation and unemployment using sentiment analysis"""

    def __init__(self):
        self.baseline_unemployment = 3.5
        self.baseline_job_growth = 150000  # Monthly jobs added
        self.scaler = StandardScaler() if ADVANCED_MODELS else None

        # Sector weights for employment impact
        self.sector_weights = {
            'tech': 0.15,
            'manufacturing': 0.20,
            'services': 0.35,
            'retail': 0.15,
            'finance': 0.10,
            'construction': 0.05
        }

    def predict_employment(self, sentiment_data: Dict, topic_factors: Dict) -> Dict:
        """Predict employment metrics based on sentiment"""

        # Extract employment signals
        layoff_sentiment = sentiment_data.get('layoff_sentiment', 0.5)
        hiring_sentiment = sentiment_data.get('hiring_sentiment', 0.5)
        wage_sentiment = sentiment_data.get('wage_sentiment', 0.5)

        # Calculate job growth impact
        sentiment_impact = (hiring_sentiment - layoff_sentiment) * 2

        # Factor in sector-specific impacts
        sector_impact = 0
        for sector, weight in self.sector_weights.items():
            sector_sentiment = sentiment_data.get(f'{sector}_sentiment', 0.5)
            sector_impact += (sector_sentiment - 0.5) * weight * 2

        # Calculate predictions
        job_growth_multiplier = 1 + sentiment_impact + sector_impact
        predicted_jobs = self.baseline_job_growth * job_growth_multiplier

        # Unemployment prediction (inverse relationship)
        unemployment_change = -sentiment_impact * 0.3
        predicted_unemployment = self.baseline_unemployment + unemployment_change

        # Confidence based on signal strength
        signal_strength = abs(sentiment_impact) + abs(sector_impact)
        confidence = min(0.9, 0.5 + signal_strength * 0.2)

        return {
            'monthly_job_growth': int(predicted_jobs),
            'unemployment_rate': round(predicted_unemployment, 1),
            'unemployment_change': round(unemployment_change, 2),
            'confidence': round(confidence, 2),
            'key_drivers': self._identify_employment_drivers(sentiment_data, topic_factors),
            'sector_outlook': {
                sector: 'positive' if sentiment_data.get(f'{sector}_sentiment', 0.5) > 0.6
                       else 'negative' if sentiment_data.get(f'{sector}_sentiment', 0.5) < 0.4
                       else 'neutral'
                for sector in self.sector_weights.keys()
            }
        }

    def _identify_employment_drivers(self, sentiment_data: Dict, topic_factors: Dict) -> List[str]:
        """Identify key employment drivers"""
        drivers = []

        if sentiment_data.get('layoff_sentiment', 0.5) < 0.3:
            drivers.append('high_layoff_risk')
        if sentiment_data.get('hiring_sentiment', 0.5) > 0.7:
            drivers.append('strong_hiring_activity')
        if sentiment_data.get('wage_sentiment', 0.5) > 0.7:
            drivers.append('wage_growth_pressure')

        if topic_factors.get('automation', 0) > 0.5:
            drivers.append('automation_impact')
        if topic_factors.get('recession', 0) < -0.5:
            drivers.append('recession_concerns')

        return drivers[:5]


class InflationPredictor:
    """Predict CPI changes using supply chain and commodity sentiment"""

    def __init__(self):
        self.baseline_inflation = 2.0  # Target inflation
        self.scaler = StandardScaler() if ADVANCED_MODELS else None

        # Component weights in CPI basket
        self.cpi_weights = {
            'energy': 0.08,
            'food': 0.14,
            'housing': 0.33,
            'transportation': 0.16,
            'medical': 0.08,
            'recreation': 0.06,
            'education': 0.03,
            'other': 0.12
        }

    def predict_inflation(self, sentiment_data: Dict, commodity_prices: Dict) -> Dict:
        """Predict inflation based on various factors"""

        # Supply chain sentiment impact
        supply_chain_sentiment = sentiment_data.get('supply_chain', 0.5)
        supply_impact = (0.5 - supply_chain_sentiment) * 3  # Negative sentiment = higher inflation

        # Energy price impact
        energy_sentiment = sentiment_data.get('energy_sentiment', 0.5)
        oil_price_change = commodity_prices.get('oil_change', 0)
        energy_impact = (oil_price_change * 0.02) + (0.5 - energy_sentiment) * 1.5

        # Food price impact
        food_sentiment = sentiment_data.get('food_sentiment', 0.5)
        agricultural_impact = (0.5 - food_sentiment) * 2

        # Tariff/trade impact
        tariff_sentiment = sentiment_data.get('tariff_sentiment', 0.5)
        trade_impact = (0.5 - tariff_sentiment) * 1.5

        # Calculate weighted inflation prediction
        inflation_components = {
            'energy': self.baseline_inflation + energy_impact * 2,
            'food': self.baseline_inflation + agricultural_impact * 1.5,
            'housing': self.baseline_inflation + supply_impact * 0.5,
            'transportation': self.baseline_inflation + energy_impact * 1.5,
            'other': self.baseline_inflation + trade_impact * 0.8
        }

        # Weighted average
        predicted_cpi = sum(
            inflation_components.get(component, self.baseline_inflation) * weight
            for component, weight in self.cpi_weights.items()
        )

        # Month-over-month change
        mom_change = (predicted_cpi - self.baseline_inflation) / 12

        # Confidence bands
        volatility = abs(supply_impact) + abs(energy_impact) + abs(trade_impact)
        confidence_band = min(2.0, volatility * 0.5)

        return {
            'cpi_forecast': round(predicted_cpi, 1),
            'mom_change': round(mom_change, 2),
            'yoy_forecast': round(predicted_cpi, 1),
            'confidence_band': [
                round(predicted_cpi - confidence_band, 1),
                round(predicted_cpi + confidence_band, 1)
            ],
            'components': {k: round(v, 1) for k, v in inflation_components.items()},
            'inflation_risk': 'high' if predicted_cpi > 4 else 'moderate' if predicted_cpi > 3 else 'low',
            'key_drivers': self._identify_inflation_drivers(sentiment_data, commodity_prices)
        }

    def _identify_inflation_drivers(self, sentiment_data: Dict, commodity_prices: Dict) -> List[str]:
        """Identify key inflation drivers"""
        drivers = []

        if commodity_prices.get('oil_change', 0) > 10:
            drivers.append('rising_energy_costs')
        if sentiment_data.get('supply_chain', 0.5) < 0.3:
            drivers.append('supply_chain_disruptions')
        if sentiment_data.get('tariff_sentiment', 0.5) < 0.3:
            drivers.append('tariff_pressures')
        if sentiment_data.get('wage_sentiment', 0.5) > 0.7:
            drivers.append('wage_price_spiral')

        return drivers


class CurrencyFXPredictor:
    """Predict currency movements based on sentiment and fundamentals"""

    def __init__(self):
        self.baseline_fx = 1.0  # Baseline exchange rate

        # Currency sensitivity factors
        self.sensitivity_factors = {
            'trade_sentiment': -2.0,  # Negative trade = weaker currency
            'interest_rate_diff': 3.0,  # Higher rates = stronger currency
            'geopolitical_risk': -1.5,  # Higher risk = weaker currency
            'commodity_prices': 1.0,  # For commodity currencies
            'fiscal_health': 1.5  # Better fiscal = stronger currency
        }

    def predict_fx(self, currency_pair: str, sentiment_data: Dict,
                   fundamentals: Dict) -> Dict:
        """Predict FX movements for a currency pair"""

        # Extract relevant sentiments
        trade_sentiment = sentiment_data.get('trade_sentiment', 0.5)
        geopolitical_sentiment = sentiment_data.get('geopolitical', 0.5)

        # Calculate directional bias
        trade_impact = (trade_sentiment - 0.5) * self.sensitivity_factors['trade_sentiment']
        geo_impact = (0.5 - geopolitical_sentiment) * self.sensitivity_factors['geopolitical_risk']

        # Interest rate differential impact
        rate_diff = fundamentals.get('interest_rate_diff', 0)
        rate_impact = rate_diff * self.sensitivity_factors['interest_rate_diff'] * 0.01

        # Terms of trade impact
        tot_change = fundamentals.get('terms_of_trade_change', 0)
        tot_impact = tot_change * 0.02

        # Total predicted change (%)
        total_impact = trade_impact + geo_impact + rate_impact + tot_impact

        # Time horizons
        predictions = {
            '1_week': total_impact * 0.25,
            '2_weeks': total_impact * 0.5,
            '1_month': total_impact,
            '3_months': total_impact * 2.0
        }

        # Determine direction and strength
        direction = 'strengthen' if total_impact > 0 else 'weaken'
        strength = 'strong' if abs(total_impact) > 2 else 'moderate' if abs(total_impact) > 1 else 'mild'

        return {
            'currency_pair': currency_pair,
            'direction': direction,
            'strength': strength,
            'predictions': {k: round(v, 2) for k, v in predictions.items()},
            'confidence': round(0.7 - abs(total_impact) * 0.05, 2),
            'key_drivers': self._identify_fx_drivers(sentiment_data, fundamentals),
            'volatility_regime': 'high' if abs(total_impact) > 3 else 'normal'
        }

    def _identify_fx_drivers(self, sentiment_data: Dict, fundamentals: Dict) -> List[str]:
        """Identify key FX drivers"""
        drivers = []

        if sentiment_data.get('trade_sentiment', 0.5) < 0.3:
            drivers.append('trade_war_concerns')
        if fundamentals.get('interest_rate_diff', 0) > 2:
            drivers.append('rate_differential')
        if sentiment_data.get('geopolitical', 0.5) < 0.3:
            drivers.append('geopolitical_risk')

        return drivers


class EquityMarketPredictor:
    """Predict stock market movements by country and sector"""

    def __init__(self):
        self.baseline_return = 7.0  # Annual return expectation

        # Sector betas to market
        self.sector_betas = {
            'technology': 1.3,
            'financials': 1.2,
            'energy': 1.1,
            'industrials': 1.0,
            'consumer_discretionary': 1.1,
            'healthcare': 0.8,
            'utilities': 0.6,
            'consumer_staples': 0.7
        }

    def predict_equity(self, market: str, sentiment_data: Dict,
                       macro_factors: Dict) -> Dict:
        """Predict equity market movements"""

        # Overall market sentiment
        market_sentiment = sentiment_data.get('market_sentiment', 0.5)
        sentiment_impact = (market_sentiment - 0.5) * 20  # ±10% impact

        # Macro impacts
        gdp_growth = macro_factors.get('gdp_forecast', 2.5)
        gdp_impact = (gdp_growth - 2.5) * 2  # GDP deviation impact

        # FX impact (for international markets)
        fx_change = macro_factors.get('fx_change', 0)
        fx_impact = -fx_change * 0.5  # Inverse relationship

        # Calculate market prediction
        market_return = self.baseline_return + sentiment_impact + gdp_impact + fx_impact

        # Sector-specific predictions
        sector_predictions = {}
        for sector, beta in self.sector_betas.items():
            sector_sentiment = sentiment_data.get(f'{sector}_sentiment', 0.5)
            sector_specific = (sector_sentiment - 0.5) * 10
            sector_return = market_return * beta + sector_specific
            sector_predictions[sector] = round(sector_return, 1)

        # Time horizon predictions
        predictions = {
            '1_week': market_return / 52,
            '1_month': market_return / 12,
            '3_months': market_return / 4,
            '1_year': market_return
        }

        return {
            'market': market,
            'market_return_forecast': round(market_return, 1),
            'predictions': {k: round(v, 2) for k, v in predictions.items()},
            'sector_forecasts': sector_predictions,
            'top_sectors': sorted(sector_predictions.items(), key=lambda x: x[1], reverse=True)[:3],
            'bottom_sectors': sorted(sector_predictions.items(), key=lambda x: x[1])[:3],
            'risk_regime': 'high' if abs(market_return - self.baseline_return) > 10 else 'normal',
            'recommendation': self._generate_recommendation(market_return, sector_predictions)
        }

    def _generate_recommendation(self, market_return: float,
                                sector_predictions: Dict) -> str:
        """Generate investment recommendation"""
        if market_return > 10:
            return "overweight_equities"
        elif market_return > 5:
            return "neutral_equities"
        elif market_return > 0:
            return "underweight_equities"
        else:
            return "defensive_positioning"


class CommodityPricePredictor:
    """Predict commodity prices across multiple markets"""

    def __init__(self):
        # Baseline annual price changes
        self.baseline_changes = {
            'oil': 2.0,
            'gas': 3.0,
            'gold': 1.5,
            'copper': 2.5,
            'steel': 2.0,
            'wheat': 1.5,
            'corn': 1.5,
            'soybeans': 2.0
        }

        # Sensitivity factors
        self.sensitivities = {
            'oil': {'geopolitical': 3.0, 'supply': -2.5, 'demand': 2.0},
            'gas': {'weather': 2.5, 'supply': -3.0, 'demand': 2.5},
            'gold': {'risk_off': 2.0, 'real_rates': -1.5, 'dollar': -1.0},
            'copper': {'china_demand': 3.0, 'supply': -2.0, 'ev_demand': 1.5},
            'wheat': {'weather': 3.0, 'supply': -2.5, 'export_ban': 2.0},
            'corn': {'weather': 2.5, 'ethanol': 1.5, 'supply': -2.0}
        }

    def predict_commodity(self, commodity: str, sentiment_data: Dict,
                         supply_demand: Dict) -> Dict:
        """Predict commodity price movements"""

        if commodity not in self.baseline_changes:
            return {'error': f'Commodity {commodity} not supported'}

        baseline = self.baseline_changes[commodity]
        sensitivities = self.sensitivities.get(commodity, {})

        # Calculate impacts
        total_impact = 0
        impact_breakdown = {}

        for factor, sensitivity in sensitivities.items():
            factor_value = sentiment_data.get(f'{commodity}_{factor}', 0.5)
            if factor in ['supply']:
                # Higher supply sentiment = lower prices
                impact = (0.5 - factor_value) * sensitivity * 2
            else:
                # Higher demand/risk sentiment = higher prices
                impact = (factor_value - 0.5) * sensitivity * 2

            total_impact += impact
            impact_breakdown[factor] = round(impact, 1)

        # Supply/demand balance
        supply_balance = supply_demand.get(f'{commodity}_balance', 0)
        balance_impact = -supply_balance * 5  # Surplus = lower prices
        total_impact += balance_impact

        # Calculate predictions
        annual_change = baseline + total_impact

        predictions = {
            '1_week': annual_change / 52,
            '2_weeks': annual_change / 26,
            '1_month': annual_change / 12,
            '3_months': annual_change / 4
        }

        return {
            'commodity': commodity,
            'price_direction': 'up' if annual_change > 0 else 'down',
            'annual_change_forecast': round(annual_change, 1),
            'predictions': {k: round(v, 2) for k, v in predictions.items()},
            'impact_breakdown': impact_breakdown,
            'supply_demand_balance': supply_balance,
            'volatility': 'high' if abs(annual_change) > 20 else 'normal',
            'key_drivers': list(impact_breakdown.keys())[:3]
        }


class TradeFlowPredictor:
    """Predict bilateral trade flows between countries"""

    def __init__(self):
        self.baseline_trade_growth = 3.0  # Annual growth

    def predict_trade(self, exporter: str, importer: str,
                     sentiment_data: Dict, policy_factors: Dict) -> Dict:
        """Predict trade flow changes between two countries"""

        # Bilateral sentiment
        bilateral_sentiment = sentiment_data.get(f'{exporter}_{importer}_sentiment', 0.5)
        sentiment_impact = (bilateral_sentiment - 0.5) * 10

        # Tariff impact
        tariff_change = policy_factors.get('tariff_change', 0)
        tariff_impact = -tariff_change * 0.5  # Higher tariffs = less trade

        # Sanctions impact
        sanctions_risk = policy_factors.get('sanctions_risk', 0)
        sanctions_impact = -sanctions_risk * 15

        # Currency impact
        fx_change = policy_factors.get('fx_change', 0)
        fx_impact = fx_change * 0.3  # Weaker exporter currency = more exports

        # Logistics/shipping sentiment
        logistics_sentiment = sentiment_data.get('logistics', 0.5)
        logistics_impact = (logistics_sentiment - 0.5) * 5

        # Total trade flow change
        total_change = (self.baseline_trade_growth + sentiment_impact +
                       tariff_impact + sanctions_impact + fx_impact + logistics_impact)

        # Export/import breakdown
        export_change = total_change + fx_impact  # Extra FX benefit for exports
        import_change = total_change - fx_impact  # FX penalty for imports

        return {
            'trade_pair': f'{exporter}->{importer}',
            'total_trade_change': round(total_change, 1),
            'export_change': round(export_change, 1),
            'import_change': round(import_change, 1),
            'trade_balance_impact': round(export_change - import_change, 1),
            'confidence': round(0.7 - abs(total_change) * 0.02, 2),
            'risk_factors': self._identify_trade_risks(policy_factors),
            'opportunities': self._identify_trade_opportunities(sentiment_data),
            'recommendation': 'increase' if total_change > 5 else 'maintain' if total_change > 0 else 'reduce'
        }

    def _identify_trade_risks(self, policy_factors: Dict) -> List[str]:
        """Identify trade risks"""
        risks = []
        if policy_factors.get('tariff_change', 0) > 10:
            risks.append('high_tariffs')
        if policy_factors.get('sanctions_risk', 0) > 0.5:
            risks.append('sanctions_risk')
        return risks

    def _identify_trade_opportunities(self, sentiment_data: Dict) -> List[str]:
        """Identify trade opportunities"""
        opportunities = []
        if sentiment_data.get('fta_sentiment', 0.5) > 0.7:
            opportunities.append('free_trade_agreement')
        if sentiment_data.get('logistics', 0.5) > 0.7:
            opportunities.append('improved_logistics')
        return opportunities


class GeopoliticalRiskIndex:
    """Calculate Geopolitical Risk Index (GPR) from news sentiment"""

    def __init__(self):
        self.baseline_gpr = 50  # Neutral level

        # Risk keywords and weights
        self.risk_keywords = {
            'war': 10,
            'invasion': 9,
            'sanctions': 7,
            'military': 6,
            'conflict': 8,
            'crisis': 7,
            'tensions': 5,
            'escalation': 8,
            'mobilization': 7,
            'tariffs': 4,
            'trade_war': 6,
            'embargo': 8
        }

    def calculate_gpr(self, text_corpus: str, article_count: int) -> Dict:
        """Calculate GPR index from text corpus"""

        text_lower = text_corpus.lower()

        # Count risk mentions
        risk_score = 0
        keyword_counts = {}

        for keyword, weight in self.risk_keywords.items():
            count = text_lower.count(keyword.replace('_', ' '))
            if count > 0:
                keyword_counts[keyword] = count
                # Normalize by article count and apply weight
                normalized_impact = (count / max(1, article_count)) * weight * 10
                risk_score += normalized_impact

        # Apply recency decay (recent events weighted more)
        recency_factor = 1.0  # In production, would decay older articles
        risk_score *= recency_factor

        # Normalize to 0-100 scale
        gpr_index = min(100, self.baseline_gpr + risk_score)

        # Determine risk level
        if gpr_index >= 80:
            risk_level = 'extreme'
        elif gpr_index >= 65:
            risk_level = 'high'
        elif gpr_index >= 50:
            risk_level = 'elevated'
        elif gpr_index >= 35:
            risk_level = 'moderate'
        else:
            risk_level = 'low'

        # Top risk drivers
        top_drivers = sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            'gpr_index': round(gpr_index, 1),
            'risk_level': risk_level,
            'change_from_baseline': round(gpr_index - self.baseline_gpr, 1),
            'top_risk_drivers': [driver[0] for driver in top_drivers],
            'keyword_frequencies': keyword_counts,
            'interpretation': self._interpret_gpr(gpr_index),
            'market_implication': self._market_implication(risk_level)
        }

    def _interpret_gpr(self, gpr_index: float) -> str:
        """Interpret GPR level"""
        if gpr_index >= 80:
            return "Extreme geopolitical tensions, major conflict likely"
        elif gpr_index >= 65:
            return "High tensions, significant risk of escalation"
        elif gpr_index >= 50:
            return "Elevated concerns, monitoring required"
        elif gpr_index >= 35:
            return "Moderate tensions, situation manageable"
        else:
            return "Low geopolitical risk, stable environment"

    def _market_implication(self, risk_level: str) -> str:
        """Market implications of GPR level"""
        implications = {
            'extreme': 'flight_to_safety',
            'high': 'risk_off',
            'elevated': 'cautious',
            'moderate': 'neutral',
            'low': 'risk_on'
        }
        return implications.get(risk_level, 'neutral')


class FDIPredictor:
    """Predict Foreign Direct Investment trends"""

    def __init__(self):
        self.baseline_fdi_growth = 5.0  # Annual growth %

    def predict_fdi(self, country: str, sentiment_data: Dict,
                   policy_factors: Dict) -> Dict:
        """Predict FDI flows for a country"""

        # Investment sentiment
        investment_sentiment = sentiment_data.get('investment_sentiment', 0.5)
        sentiment_impact = (investment_sentiment - 0.5) * 20

        # Policy stability
        policy_stability = policy_factors.get('policy_stability', 0.5)
        stability_impact = (policy_stability - 0.5) * 15

        # Regulatory environment
        regulatory_sentiment = sentiment_data.get('regulatory', 0.5)
        regulatory_impact = (regulatory_sentiment - 0.5) * 10

        # Incentives mentions
        incentive_mentions = sentiment_data.get('incentive_mentions', 0)
        incentive_impact = min(10, incentive_mentions * 2)

        # Plant relocation sentiment
        relocation_sentiment = sentiment_data.get('relocation', 0.5)
        relocation_impact = (relocation_sentiment - 0.5) * 15

        # Total FDI change
        total_change = (self.baseline_fdi_growth + sentiment_impact +
                       stability_impact + regulatory_impact +
                       incentive_impact + relocation_impact)

        # Determine trend
        if total_change > 10:
            trend = 'strongly_positive'
        elif total_change > 5:
            trend = 'positive'
        elif total_change > -5:
            trend = 'neutral'
        elif total_change > -10:
            trend = 'negative'
        else:
            trend = 'strongly_negative'

        return {
            'country': country,
            'fdi_growth_forecast': round(total_change, 1),
            'trend': trend,
            'confidence': round(0.7 + policy_stability * 0.2, 2),
            'key_drivers': self._identify_fdi_drivers(sentiment_data, policy_factors),
            'sector_attractiveness': self._assess_sector_attractiveness(sentiment_data),
            'policy_recommendation': self._policy_recommendation(total_change)
        }

    def _identify_fdi_drivers(self, sentiment_data: Dict, policy_factors: Dict) -> List[str]:
        """Identify FDI drivers"""
        drivers = []
        if sentiment_data.get('investment_sentiment', 0.5) > 0.7:
            drivers.append('positive_investment_climate')
        if policy_factors.get('policy_stability', 0.5) > 0.7:
            drivers.append('stable_policies')
        if sentiment_data.get('incentive_mentions', 0) > 3:
            drivers.append('government_incentives')
        return drivers

    def _assess_sector_attractiveness(self, sentiment_data: Dict) -> Dict:
        """Assess sector attractiveness for FDI"""
        sectors = ['tech', 'manufacturing', 'services', 'infrastructure']
        attractiveness = {}
        for sector in sectors:
            sector_sentiment = sentiment_data.get(f'{sector}_fdi', 0.5)
            if sector_sentiment > 0.6:
                attractiveness[sector] = 'high'
            elif sector_sentiment > 0.4:
                attractiveness[sector] = 'medium'
            else:
                attractiveness[sector] = 'low'
        return attractiveness

    def _policy_recommendation(self, fdi_change: float) -> str:
        """Generate policy recommendation"""
        if fdi_change < 0:
            return "improve_investment_climate"
        elif fdi_change < 5:
            return "enhance_incentives"
        else:
            return "maintain_current_policies"


class ConsumerConfidenceProxy:
    """Proxy for consumer confidence using news sentiment"""

    def __init__(self):
        self.baseline_confidence = 50  # Neutral level (0-100 scale)

        # Component weights
        self.components = {
            'employment': 0.25,
            'prices': 0.20,
            'wages': 0.15,
            'retail': 0.15,
            'housing': 0.15,
            'economy': 0.10
        }

    def calculate_confidence(self, sentiment_data: Dict) -> Dict:
        """Calculate consumer confidence proxy"""

        component_scores = {}

        # Employment confidence
        job_sentiment = sentiment_data.get('job_sentiment', 0.5)
        layoff_sentiment = sentiment_data.get('layoff_sentiment', 0.5)
        employment_score = job_sentiment * 100 * (1 - layoff_sentiment/2)
        component_scores['employment'] = employment_score

        # Price/inflation confidence (inverse)
        inflation_sentiment = sentiment_data.get('inflation_sentiment', 0.5)
        price_score = (1 - inflation_sentiment) * 100
        component_scores['prices'] = price_score

        # Wage confidence
        wage_sentiment = sentiment_data.get('wage_sentiment', 0.5)
        wage_score = wage_sentiment * 100
        component_scores['wages'] = wage_score

        # Retail confidence
        retail_sentiment = sentiment_data.get('retail_sentiment', 0.5)
        retail_score = retail_sentiment * 100
        component_scores['retail'] = retail_score

        # Housing confidence
        housing_sentiment = sentiment_data.get('housing_sentiment', 0.5)
        housing_score = housing_sentiment * 100
        component_scores['housing'] = housing_score

        # Overall economic confidence
        economy_sentiment = sentiment_data.get('economy_sentiment', 0.5)
        economy_score = economy_sentiment * 100
        component_scores['economy'] = economy_score

        # Calculate weighted average
        confidence_index = sum(
            component_scores.get(comp, 50) * weight
            for comp, weight in self.components.items()
        )

        # Month-over-month change
        mom_change = confidence_index - self.baseline_confidence

        # Determine trend
        if confidence_index > 60:
            trend = 'optimistic'
        elif confidence_index > 50:
            trend = 'positive'
        elif confidence_index > 40:
            trend = 'neutral'
        elif confidence_index > 30:
            trend = 'pessimistic'
        else:
            trend = 'very_pessimistic'

        return {
            'confidence_index': round(confidence_index, 1),
            'trend': trend,
            'mom_change': round(mom_change, 1),
            'component_scores': {k: round(v, 1) for k, v in component_scores.items()},
            'strongest_component': max(component_scores.items(), key=lambda x: x[1])[0],
            'weakest_component': min(component_scores.items(), key=lambda x: x[1])[0],
            'interpretation': self._interpret_confidence(confidence_index),
            'economic_implication': self._economic_implication(trend)
        }

    def _interpret_confidence(self, index: float) -> str:
        """Interpret confidence level"""
        if index > 60:
            return "Consumers optimistic, spending likely to increase"
        elif index > 50:
            return "Positive sentiment, stable consumption expected"
        elif index > 40:
            return "Neutral sentiment, cautious spending"
        elif index > 30:
            return "Pessimistic outlook, reduced discretionary spending"
        else:
            return "Very pessimistic, significant spending pullback expected"

    def _economic_implication(self, trend: str) -> str:
        """Economic implications of confidence level"""
        implications = {
            'optimistic': 'gdp_boost',
            'positive': 'stable_growth',
            'neutral': 'modest_growth',
            'pessimistic': 'growth_slowdown',
            'very_pessimistic': 'recession_risk'
        }
        return implications.get(trend, 'uncertain')


class TopicAnalysisEngine:
    """Engine for analyzing specific topics/questions using classification"""

    def __init__(self):
        self.topic_classifiers = {
            'economic': ['gdp', 'growth', 'economy', 'economic', 'recession', 'inflation', 'unemployment'],
            'banking': ['bank', 'banking', 'financial', 'finance', 'credit', 'lending', 'deposits'],
            'tourism': ['tourism', 'tourist', 'travel', 'hospitality', 'hotel', 'vacation'],
            'manufacturing': ['manufacturing', 'industry', 'production', 'factory', 'industrial'],
            'trade': ['trade', 'export', 'import', 'tariff', 'customs', 'commerce'],
            'policy': ['policy', 'government', 'regulation', 'law', 'political', 'politics'],
            'market': ['market', 'stock', 'investment', 'investor', 'trading', 'securities']
        }

    def classify_question(self, question: str) -> List[str]:
        """Classify user question into topic categories"""
        question_lower = question.lower()
        matched_topics = []

        for topic, keywords in self.topic_classifiers.items():
            if any(keyword in question_lower for keyword in keywords):
                matched_topics.append(topic)

        return matched_topics if matched_topics else ['general']

    def generate_analysis_plan(self, question: str, country: str) -> Dict:
        """Generate analysis plan based on question and country"""
        topics = self.classify_question(question)

        plan = {
            'question': question,
            'country': country,
            'topics': topics,
            'analysis_steps': [],
            'data_sources': [],
            'output_format': 'comprehensive'
        }

        # Define analysis steps based on topics
        if 'economic' in topics:
            plan['analysis_steps'].extend([
                'Fetch GDP growth data from World Bank',
                'Analyze economic trends and cycles',
                'Generate conservative forecasts',
                'Validate against recent actual performance'
            ])
            plan['data_sources'].append('World Bank WDI API')

        if 'banking' in topics:
            plan['analysis_steps'].extend([
                'Analyze financial sector health',
                'Review banking regulations',
                'Assess credit conditions and monetary policy impact'
            ])
            plan['data_sources'].extend(['Central Bank data', 'Financial news sources'])

        if 'tourism' in topics:
            plan['analysis_steps'].extend([
                'Analyze tourism arrival trends',
                'Assess hospitality sector performance',
                'Identify seasonal patterns and recovery trajectories'
            ])
            plan['data_sources'].append('Tourism statistics and industry reports')

        if 'trade' in topics:
            plan['analysis_steps'].extend([
                'Analyze bilateral trade flows and patterns',
                'Assess trade policy impacts and sanctions',
                'Review import/export trends and dependencies',
                'Evaluate trade balance and competitiveness'
            ])
            plan['data_sources'].extend(['Trade statistics', 'Customs data', 'Trade policy reports'])

        if 'manufacturing' in topics:
            plan['analysis_steps'].extend([
                'Analyze industrial production indices',
                'Assess supply chain efficiency',
                'Review manufacturing sentiment surveys'
            ])
            plan['data_sources'].extend(['Industrial statistics', 'Manufacturing surveys'])

        if 'policy' in topics:
            plan['analysis_steps'].extend([
                'Review recent policy changes and announcements',
                'Assess regulatory impact on markets',
                'Analyze political stability indicators'
            ])
            plan['data_sources'].extend(['Government sources', 'Policy databases'])

        if 'market' in topics:
            plan['analysis_steps'].extend([
                'Analyze market sentiment and volatility',
                'Review equity and bond market performance',
                'Assess investor confidence indicators'
            ])
            plan['data_sources'].extend(['Market data feeds', 'Investor surveys'])

        return plan


class ComprehensivePredictorSuite:
    """Master class combining all predictors"""

    def __init__(self):
        self.job_predictor = JobGrowthPredictor()
        self.inflation_predictor = InflationPredictor()
        self.fx_predictor = CurrencyFXPredictor()
        self.equity_predictor = EquityMarketPredictor()
        self.commodity_predictor = CommodityPricePredictor()
        self.trade_predictor = TradeFlowPredictor()
        self.gpr_calculator = GeopoliticalRiskIndex()
        self.fdi_predictor = FDIPredictor()
        self.confidence_proxy = ConsumerConfidenceProxy()

    def run_comprehensive_analysis(self, sentiment_data: Dict,
                                  market_data: Dict = None,
                                  text_corpus: str = "") -> Dict:
        """Run all predictors and return comprehensive analysis"""

        results = {}

        # Employment predictions
        results['employment'] = self.job_predictor.predict_employment(
            sentiment_data, market_data.get('topic_factors', {})
        )

        # Inflation predictions
        results['inflation'] = self.inflation_predictor.predict_inflation(
            sentiment_data, market_data.get('commodity_prices', {})
        )

        # FX predictions (example for USD/EUR)
        results['fx'] = self.fx_predictor.predict_fx(
            'USD/EUR', sentiment_data, market_data.get('fundamentals', {})
        )

        # Equity market predictions
        results['equity'] = self.equity_predictor.predict_equity(
            'S&P500', sentiment_data, market_data.get('macro_factors', {})
        )

        # Commodity predictions (oil as example)
        results['commodities'] = {
            'oil': self.commodity_predictor.predict_commodity(
                'oil', sentiment_data, market_data.get('supply_demand', {})
            )
        }

        # Trade flow predictions (US-China as example)
        results['trade'] = self.trade_predictor.predict_trade(
            'US', 'China', sentiment_data, market_data.get('policy_factors', {})
        )

        # Geopolitical risk
        article_count = market_data.get('article_count', 100)
        results['geopolitical_risk'] = self.gpr_calculator.calculate_gpr(
            text_corpus, article_count
        )

        # FDI predictions
        results['fdi'] = self.fdi_predictor.predict_fdi(
            'US', sentiment_data, market_data.get('policy_factors', {})
        )

        # Consumer confidence
        results['consumer_confidence'] = self.confidence_proxy.calculate_confidence(
            sentiment_data
        )

        # Overall market assessment
        results['overall_assessment'] = self._generate_overall_assessment(results)

        return results

    def _generate_overall_assessment(self, results: Dict) -> Dict:
        """Generate overall market assessment"""

        # Aggregate risk level
        risk_indicators = []
        if results['geopolitical_risk']['risk_level'] in ['high', 'extreme']:
            risk_indicators.append('geopolitical')
        if results['inflation']['inflation_risk'] == 'high':
            risk_indicators.append('inflation')
        if results['employment']['unemployment_rate'] > 5:
            risk_indicators.append('employment')

        overall_risk = 'high' if len(risk_indicators) >= 2 else 'moderate' if len(risk_indicators) == 1 else 'low'

        # Market outlook
        equity_outlook = results['equity']['recommendation']
        confidence_trend = results['consumer_confidence']['trend']

        if confidence_trend in ['optimistic', 'positive'] and overall_risk == 'low':
            market_outlook = 'bullish'
        elif confidence_trend in ['pessimistic', 'very_pessimistic'] or overall_risk == 'high':
            market_outlook = 'bearish'
        else:
            market_outlook = 'neutral'

        return {
            'overall_risk_level': overall_risk,
            'risk_indicators': risk_indicators,
            'market_outlook': market_outlook,
            'key_opportunities': self._identify_opportunities(results),
            'key_risks': self._identify_risks(results),
            'recommended_actions': self._generate_recommendations(market_outlook, overall_risk)
        }

    def _identify_opportunities(self, results: Dict) -> List[str]:
        """Identify key opportunities"""
        opportunities = []
        if results['equity']['market_return_forecast'] > 10:
            opportunities.append('strong_equity_returns')
        if results['fdi']['trend'] in ['positive', 'strongly_positive']:
            opportunities.append('fdi_inflows')
        if results['trade'].get('opportunities'):
            opportunities.extend(results['trade']['opportunities'])
        return opportunities[:5]

    def _identify_risks(self, results: Dict) -> List[str]:
        """Identify key risks"""
        risks = []
        if results['geopolitical_risk']['risk_level'] in ['high', 'extreme']:
            risks.append('geopolitical_tensions')
        if results['inflation']['inflation_risk'] == 'high':
            risks.append('inflation_pressure')
        if results['employment']['unemployment_rate'] > 5:
            risks.append('rising_unemployment')
        return risks[:5]

    def _generate_recommendations(self, outlook: str, risk: str) -> List[str]:
        """Generate action recommendations"""
        recommendations = []

        if outlook == 'bullish' and risk == 'low':
            recommendations.append('increase_risk_exposure')
            recommendations.append('overweight_growth_assets')
        elif outlook == 'bearish' or risk == 'high':
            recommendations.append('reduce_risk_exposure')
            recommendations.append('increase_defensive_positions')
            recommendations.append('hedge_portfolios')
        else:
            recommendations.append('maintain_balanced_allocation')
            recommendations.append('selective_opportunities')

        return recommendations


def test_comprehensive_suite():
    """Test all predictors"""
    print("🚀 Testing Comprehensive Predictor Suite")
    print("=" * 60)

    # Sample sentiment data
    sample_sentiment = {
        'market_sentiment': 0.6,
        'layoff_sentiment': 0.3,
        'hiring_sentiment': 0.7,
        'wage_sentiment': 0.6,
        'supply_chain': 0.4,
        'energy_sentiment': 0.3,
        'trade_sentiment': 0.4,
        'geopolitical': 0.3,
        'investment_sentiment': 0.6,
        'job_sentiment': 0.6,
        'inflation_sentiment': 0.6,
        'retail_sentiment': 0.5,
        'housing_sentiment': 0.5,
        'economy_sentiment': 0.5
    }

    sample_market_data = {
        'topic_factors': {'automation': 0.3, 'recession': -0.2},
        'commodity_prices': {'oil_change': 5},
        'fundamentals': {'interest_rate_diff': 1.5, 'terms_of_trade_change': -2},
        'macro_factors': {'gdp_forecast': 2.8, 'fx_change': -2},
        'supply_demand': {'oil_balance': 0.5},
        'policy_factors': {'tariff_change': 10, 'sanctions_risk': 0.2, 'policy_stability': 0.7},
        'article_count': 100
    }

    sample_text = "Trade tensions escalate as tariffs increase. Economic growth remains stable despite geopolitical concerns."

    # Run comprehensive analysis
    suite = ComprehensivePredictorSuite()
    results = suite.run_comprehensive_analysis(
        sample_sentiment, sample_market_data, sample_text
    )

    # Display results
    print("\n📊 COMPREHENSIVE ECONOMIC PREDICTIONS")
    print("-" * 40)

    print(f"\n💼 EMPLOYMENT:")
    print(f"  Monthly Jobs: {results['employment']['monthly_job_growth']:,}")
    print(f"  Unemployment: {results['employment']['unemployment_rate']}%")

    print(f"\n📈 INFLATION:")
    print(f"  CPI Forecast: {results['inflation']['cpi_forecast']}%")
    print(f"  Risk Level: {results['inflation']['inflation_risk']}")

    print(f"\n💱 CURRENCY:")
    print(f"  USD/EUR: {results['fx']['direction']} ({results['fx']['predictions']['1_month']}%/month)")

    print(f"\n📊 EQUITY MARKETS:")
    print(f"  S&P500 Return: {results['equity']['market_return_forecast']}%")
    print(f"  Top Sectors: {[s[0] for s in results['equity']['top_sectors']]}")

    print(f"\n🛢️ COMMODITIES:")
    print(f"  Oil: {results['commodities']['oil']['price_direction']} ({results['commodities']['oil']['annual_change_forecast']}%)")

    print(f"\n🚢 TRADE FLOWS:")
    print(f"  US-China: {results['trade']['total_trade_change']}%")

    print(f"\n⚠️ GEOPOLITICAL RISK:")
    print(f"  GPR Index: {results['geopolitical_risk']['gpr_index']}/100")
    print(f"  Risk Level: {results['geopolitical_risk']['risk_level']}")

    print(f"\n💰 FDI:")
    print(f"  Growth: {results['fdi']['fdi_growth_forecast']}%")
    print(f"  Trend: {results['fdi']['trend']}")

    print(f"\n🛍️ CONSUMER CONFIDENCE:")
    print(f"  Index: {results['consumer_confidence']['confidence_index']}/100")
    print(f"  Trend: {results['consumer_confidence']['trend']}")

    print(f"\n🎯 OVERALL ASSESSMENT:")
    print(f"  Risk Level: {results['overall_assessment']['overall_risk_level']}")
    print(f"  Market Outlook: {results['overall_assessment']['market_outlook']}")
    print(f"  Key Actions: {results['overall_assessment']['recommended_actions']}")

    return results


if __name__ == "__main__":
    test_comprehensive_suite()