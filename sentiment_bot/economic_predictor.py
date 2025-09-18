#!/usr/bin/env python
"""
Economic GDP Prediction Model
Combines quantitative econometric models with LLM sentiment analysis
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
import json
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# Try importing advanced libraries, fall back to basic if not available
try:
    from statsmodels.tsa.arima.model import ARIMA
    from statsmodels.tsa.vector_ar.var_model import VAR
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.linear_model import LinearRegression
    ADVANCED_MODELS = True
except ImportError:
    ADVANCED_MODELS = False
    print("⚠️ Advanced models not available. Using simplified predictions.")


class EconomicPredictor:
    """Quantitative economic prediction model"""
    
    def __init__(self):
        self.baseline_gdp = 2.5  # Baseline GDP growth %
        self.baseline_unemployment = 3.5  # Baseline unemployment %
        self.baseline_inflation = 2.0  # Baseline inflation %
        
        # Economic multipliers based on research
        self.multipliers = {
            'fiscal_stimulus': 1.5,  # Fiscal multiplier
            'monetary_policy': 0.8,  # Monetary policy impact
            'trade_balance': 0.3,  # Trade impact on GDP
            'consumer_confidence': 0.6,  # Consumer sentiment impact
            'investment': 1.2,  # Investment multiplier
            'geopolitical_risk': -0.4,  # Risk impact (negative)
        }
        
        # Historical data for time series (simulated if real data unavailable)
        self.historical_data = self._load_historical_data()
    
    def _load_historical_data(self) -> pd.DataFrame:
        """Load or simulate historical economic data"""
        # In production, load real data from FRED, World Bank, etc.
        # For now, simulate realistic economic data
        dates = pd.date_range(end=datetime.now(), periods=60, freq='M')
        
        np.random.seed(42)
        data = pd.DataFrame({
            'date': dates,
            'gdp_growth': np.random.normal(2.5, 0.5, 60),
            'unemployment': np.random.normal(3.5, 0.3, 60),
            'inflation': np.random.normal(2.0, 0.4, 60),
            'consumer_confidence': np.random.normal(100, 10, 60),
            'trade_balance': np.random.normal(-500, 100, 60),  # Billions
            'investment_growth': np.random.normal(3.0, 1.0, 60),
        })
        
        # Add some trend and seasonality
        data['gdp_growth'] += np.sin(np.arange(60) * 2 * np.pi / 12) * 0.3
        data['unemployment'] -= np.arange(60) * 0.01  # Improving trend
        
        return data
    
    def predict_gdp_arima(self, periods: int = 4) -> List[float]:
        """Predict GDP using ARIMA model"""
        if not ADVANCED_MODELS:
            # Simple moving average fallback
            recent = self.historical_data['gdp_growth'].tail(12).mean()
            return [recent + np.random.normal(0, 0.2) for _ in range(periods)]
        
        try:
            # Fit ARIMA model
            model = ARIMA(self.historical_data['gdp_growth'], order=(2, 1, 2))
            fitted = model.fit()
            
            # Make predictions
            forecast = fitted.forecast(steps=periods)
            return forecast.tolist()
        except:
            # Fallback to simple prediction
            return [self.baseline_gdp] * periods
    
    def predict_gdp_ml(self, features: Dict) -> float:
        """Predict GDP using machine learning model"""
        if not ADVANCED_MODELS:
            # Simple weighted average fallback
            base = self.baseline_gdp
            for factor, value in features.items():
                if factor in self.multipliers:
                    base += self.multipliers[factor] * value
            return max(-10, min(10, base))  # Cap predictions
        
        try:
            # Prepare features
            X = self.historical_data[['unemployment', 'inflation', 
                                     'consumer_confidence', 'investment_growth']].values
            y = self.historical_data['gdp_growth'].values
            
            # Train model
            model = RandomForestRegressor(n_estimators=100, random_state=42)
            model.fit(X[:-1], y[1:])  # Predict next period
            
            # Make prediction
            current_features = np.array([[
                features.get('unemployment', self.baseline_unemployment),
                features.get('inflation', self.baseline_inflation),
                features.get('consumer_confidence', 100),
                features.get('investment_growth', 3.0)
            ]])
            
            prediction = model.predict(current_features)[0]
            return prediction
        except:
            return self.baseline_gdp
    
    def calculate_economic_impact(self, sentiment_score: float, 
                                 topic_factors: Dict) -> Dict:
        """Calculate economic impact from sentiment and topic factors"""
        
        # Base predictions
        gdp_impact = 0.0
        employment_impact = 0.0
        inflation_impact = 0.0
        
        # Sentiment impact (scaled -1 to 1)
        sentiment_factor = (sentiment_score - 0.5) * 2
        
        # Calculate GDP impact
        if 'trade' in topic_factors:
            gdp_impact += self.multipliers['trade_balance'] * topic_factors['trade']
        if 'fiscal' in topic_factors:
            gdp_impact += self.multipliers['fiscal_stimulus'] * topic_factors['fiscal']
        if 'geopolitical' in topic_factors:
            gdp_impact += self.multipliers['geopolitical_risk'] * topic_factors['geopolitical']
        
        # Add sentiment adjustment
        gdp_impact += sentiment_factor * self.multipliers['consumer_confidence']
        
        # Calculate employment impact (inverse relationship with GDP in short term)
        if gdp_impact > 0:
            employment_impact = gdp_impact * 0.3  # Positive GDP -> job growth
        else:
            employment_impact = gdp_impact * 0.5  # Negative GDP -> more job losses
        
        # Calculate inflation impact
        if 'monetary' in topic_factors:
            inflation_impact += topic_factors['monetary'] * 0.5
        if 'supply_chain' in topic_factors:
            inflation_impact += topic_factors['supply_chain'] * 0.8
        inflation_impact += sentiment_factor * 0.3
        
        # Time series predictions
        gdp_forecast = self.predict_gdp_arima(4)  # Next 4 quarters
        
        # ML-based prediction with current features
        ml_features = {
            'unemployment': self.baseline_unemployment - employment_impact,
            'inflation': self.baseline_inflation + inflation_impact,
            'consumer_confidence': 100 + sentiment_factor * 20,
            'investment_growth': 3.0 + gdp_impact * 0.4
        }
        ml_gdp = self.predict_gdp_ml(ml_features)
        
        # Combine predictions (ensemble)
        combined_gdp = (gdp_forecast[0] * 0.3 + ml_gdp * 0.3 + 
                       (self.baseline_gdp + gdp_impact) * 0.4)
        
        return {
            'gdp': {
                'baseline': self.baseline_gdp,
                'impact': round(gdp_impact, 2),
                'forecast_1q': round(combined_gdp, 2),
                'forecast_1y': round(np.mean(gdp_forecast), 2),
                'forecast_quarters': [round(x, 2) for x in gdp_forecast],
                'confidence_interval': [
                    round(combined_gdp - 1.0, 2),
                    round(combined_gdp + 1.0, 2)
                ]
            },
            'employment': {
                'baseline_unemployment': self.baseline_unemployment,
                'impact': round(employment_impact, 2),
                'forecast_rate': round(self.baseline_unemployment - employment_impact, 2),
                'jobs_created': int(employment_impact * 150000),  # Rough conversion
                'confidence': 'medium' if abs(employment_impact) < 1 else 'low'
            },
            'inflation': {
                'baseline': self.baseline_inflation,
                'impact': round(inflation_impact, 2),
                'forecast': round(self.baseline_inflation + inflation_impact, 2),
                'risk_level': 'high' if inflation_impact > 1 else 'moderate'
            },
            'model_metadata': {
                'arima_available': ADVANCED_MODELS,
                'ml_model': 'RandomForest' if ADVANCED_MODELS else 'LinearWeighted',
                'data_points': len(self.historical_data),
                'sentiment_weight': 0.4,
                'quantitative_weight': 0.6
            }
        }
    
    def generate_scenario_analysis(self, base_sentiment: float) -> Dict:
        """Generate multiple scenario predictions"""
        scenarios = {}
        
        # Bull case (high sentiment)
        bull_factors = {
            'trade': 1.0,
            'fiscal': 1.5,
            'monetary': 0.5,
            'geopolitical': 0.2
        }
        scenarios['bull'] = self.calculate_economic_impact(
            min(1.0, base_sentiment + 0.3), bull_factors
        )
        
        # Base case
        base_factors = {
            'trade': 0.0,
            'fiscal': 0.5,
            'monetary': 0.0,
            'geopolitical': -0.3
        }
        scenarios['base'] = self.calculate_economic_impact(
            base_sentiment, base_factors
        )
        
        # Bear case (low sentiment)
        bear_factors = {
            'trade': -1.5,
            'fiscal': -0.5,
            'monetary': -0.5,
            'geopolitical': -1.0
        }
        scenarios['bear'] = self.calculate_economic_impact(
            max(0.0, base_sentiment - 0.3), bear_factors
        )
        
        return scenarios


class IntegratedEconomicAnalyzer:
    """Combines LLM sentiment with quantitative economic models"""
    
    def __init__(self):
        self.predictor = EconomicPredictor()
    
    def analyze_with_sentiment(self, sentiment_results: Dict, 
                              topic: str = None) -> Dict:
        """Integrate sentiment analysis with economic predictions"""
        
        # Extract sentiment score
        sentiment_score = self._calculate_weighted_sentiment(sentiment_results)
        
        # Extract topic factors from sentiment analysis
        topic_factors = self._extract_topic_factors(sentiment_results, topic)
        
        # Generate economic predictions
        economic_impact = self.predictor.calculate_economic_impact(
            sentiment_score, topic_factors
        )
        
        # Generate scenarios
        scenarios = self.predictor.generate_scenario_analysis(sentiment_score)
        
        # Combine results
        integrated_analysis = {
            'timestamp': datetime.now().isoformat(),
            'topic': topic,
            'sentiment': {
                'overall_score': round(sentiment_score, 3),
                'confidence': sentiment_results.get('confidence', 0.5),
                'sentiment_label': self._get_sentiment_label(sentiment_score)
            },
            'economic_predictions': economic_impact,
            'scenario_analysis': scenarios,
            'trading_implications': self._generate_trading_implications(
                economic_impact, sentiment_score
            ),
            'risk_assessment': self._assess_risks(economic_impact, scenarios),
            'policy_recommendations': self._generate_policy_recommendations(
                economic_impact, topic_factors
            )
        }
        
        return integrated_analysis
    
    def _calculate_weighted_sentiment(self, results: Dict) -> float:
        """Calculate weighted sentiment score from results"""
        if 'sentiment' in results:
            sentiment_map = {'positive': 0.8, 'neutral': 0.5, 'negative': 0.2}
            return sentiment_map.get(results['sentiment'], 0.5)
        
        # Average if multiple sentiments
        if 'sentiments' in results:
            scores = []
            for item in results.get('sentiments', []):
                if 'score' in item:
                    scores.append(item['score'])
            return np.mean(scores) if scores else 0.5
        
        return 0.5  # Neutral default
    
    def _extract_topic_factors(self, results: Dict, topic: str) -> Dict:
        """Extract economic factors from sentiment analysis"""
        factors = {}
        
        # Parse topic for keywords
        if topic:
            topic_lower = topic.lower()
            if 'tariff' in topic_lower or 'trade' in topic_lower:
                factors['trade'] = -1.0 if 'war' in topic_lower else -0.5
            if 'stimulus' in topic_lower or 'spending' in topic_lower:
                factors['fiscal'] = 1.0
            if 'rate' in topic_lower or 'inflation' in topic_lower:
                factors['monetary'] = -0.5 if 'hike' in topic_lower else 0.5
            if 'conflict' in topic_lower or 'sanction' in topic_lower:
                factors['geopolitical'] = -1.0
            if 'supply' in topic_lower or 'chain' in topic_lower:
                factors['supply_chain'] = -0.8
        
        # Extract from signals if available
        if 'signals' in results:
            signals = results['signals']
            if signals.get('policy_risk') == 'high':
                factors['geopolitical'] = -0.8
            if signals.get('earnings_guidance') == 'down':
                factors['trade'] = -0.5
        
        return factors
    
    def _get_sentiment_label(self, score: float) -> str:
        """Convert sentiment score to label"""
        if score >= 0.7:
            return 'strongly_positive'
        elif score >= 0.55:
            return 'positive'
        elif score >= 0.45:
            return 'neutral'
        elif score >= 0.3:
            return 'negative'
        else:
            return 'strongly_negative'
    
    def _generate_trading_implications(self, economic: Dict, 
                                      sentiment: float) -> Dict:
        """Generate trading recommendations based on predictions"""
        gdp_forecast = economic['gdp']['forecast_1q']
        
        implications = {
            'market_direction': 'bullish' if gdp_forecast > 3.0 else 
                              'bearish' if gdp_forecast < 1.0 else 'neutral',
            'recommended_sectors': [],
            'avoid_sectors': [],
            'volatility_expectation': 'high' if abs(gdp_forecast - 2.5) > 1.5 else 'moderate',
            'time_horizon': '3-6 months',
            'confidence': 'high' if sentiment > 0.7 or sentiment < 0.3 else 'medium'
        }
        
        # Sector recommendations
        if gdp_forecast > 3.0:
            implications['recommended_sectors'] = ['technology', 'consumer_discretionary', 'financials']
            implications['avoid_sectors'] = ['utilities', 'consumer_staples']
        elif gdp_forecast < 1.0:
            implications['recommended_sectors'] = ['utilities', 'healthcare', 'consumer_staples']
            implications['avoid_sectors'] = ['technology', 'industrials', 'energy']
        else:
            implications['recommended_sectors'] = ['healthcare', 'financials']
            implications['avoid_sectors'] = ['real_estate']
        
        return implications
    
    def _assess_risks(self, economic: Dict, scenarios: Dict) -> Dict:
        """Assess economic risks"""
        bull_gdp = scenarios['bull']['gdp']['forecast_1q']
        bear_gdp = scenarios['bear']['gdp']['forecast_1q']
        spread = bull_gdp - bear_gdp
        
        return {
            'uncertainty_level': 'high' if spread > 3.0 else 'moderate' if spread > 1.5 else 'low',
            'gdp_spread': round(spread, 2),
            'inflation_risk': economic['inflation']['risk_level'],
            'employment_confidence': economic['employment']['confidence'],
            'key_risks': self._identify_key_risks(economic, scenarios),
            'hedging_recommended': spread > 2.0
        }
    
    def _identify_key_risks(self, economic: Dict, scenarios: Dict) -> List[str]:
        """Identify key economic risks"""
        risks = []
        
        if economic['inflation']['forecast'] > 3.0:
            risks.append('High inflation risk requiring monetary intervention')
        
        if economic['employment']['forecast_rate'] > 4.5:
            risks.append('Rising unemployment threatening consumer spending')
        
        if scenarios['bear']['gdp']['forecast_1q'] < 0:
            risks.append('Recession risk in bear scenario')
        
        if economic['gdp']['impact'] < -1.0:
            risks.append('Significant negative GDP impact from current conditions')
        
        return risks if risks else ['No major risks identified']
    
    def _generate_policy_recommendations(self, economic: Dict, 
                                        factors: Dict) -> List[str]:
        """Generate policy recommendations"""
        recommendations = []
        
        if economic['gdp']['forecast_1q'] < 1.5:
            recommendations.append('Consider fiscal stimulus measures')
        
        if economic['inflation']['forecast'] > 3.0:
            recommendations.append('Monetary tightening may be necessary')
        
        if economic['employment']['forecast_rate'] > 4.0:
            recommendations.append('Job creation programs recommended')
        
        if factors.get('trade', 0) < -0.5:
            recommendations.append('Trade policy review needed')
        
        return recommendations if recommendations else ['Maintain current policy stance']
    
    def save_analysis(self, analysis: Dict, filename: str = None):
        """Save analysis to JSON file"""
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'economic_analysis_{timestamp}.json'
        
        with open(filename, 'w') as f:
            json.dump(analysis, f, indent=2, default=str)
        
        print(f"✅ Economic analysis saved to {filename}")
        return filename


def test_integrated_predictor():
    """Test the integrated economic predictor"""
    analyzer = IntegratedEconomicAnalyzer()
    
    # Sample sentiment results (from LLM)
    sample_sentiment = {
        'sentiment': 'negative',
        'confidence': 0.75,
        'signals': {
            'policy_risk': 'high',
            'earnings_guidance': 'down',
            'market_impact_hours': '0-6'
        },
        'trading_recommendation': {
            'action': 'hedge',
            'risk_level': 'high'
        }
    }
    
    # Run integrated analysis
    results = analyzer.analyze_with_sentiment(
        sample_sentiment,
        topic="Trump tariffs trade war manufacturing"
    )
    
    # Display results
    print("\n📊 INTEGRATED ECONOMIC ANALYSIS")
    print("="*60)
    print(f"Topic: {results['topic']}")
    print(f"Sentiment: {results['sentiment']['sentiment_label']} "
          f"(score: {results['sentiment']['overall_score']})")
    
    print("\n📈 Economic Predictions:")
    gdp = results['economic_predictions']['gdp']
    print(f"  GDP Growth: {gdp['forecast_1q']}% (Q1)")
    print(f"  GDP Range: {gdp['confidence_interval'][0]}% - {gdp['confidence_interval'][1]}%")
    print(f"  Annual Forecast: {gdp['forecast_1y']}%")
    
    emp = results['economic_predictions']['employment']
    print(f"  Unemployment: {emp['forecast_rate']}%")
    print(f"  Jobs Impact: {emp['jobs_created']:,} jobs")
    
    inf = results['economic_predictions']['inflation']
    print(f"  Inflation: {inf['forecast']}% (risk: {inf['risk_level']})")
    
    print("\n📊 Scenario Analysis:")
    for scenario, data in results['scenario_analysis'].items():
        print(f"  {scenario.upper()}: GDP {data['gdp']['forecast_1q']}%, "
              f"Unemployment {data['employment']['forecast_rate']}%")
    
    print("\n💹 Trading Implications:")
    trade = results['trading_implications']
    print(f"  Direction: {trade['market_direction']}")
    print(f"  Buy Sectors: {', '.join(trade['recommended_sectors'])}")
    print(f"  Avoid Sectors: {', '.join(trade['avoid_sectors'])}")
    
    print("\n⚠️ Risk Assessment:")
    risk = results['risk_assessment']
    print(f"  Uncertainty: {risk['uncertainty_level']}")
    print(f"  Key Risks: {risk['key_risks'][0]}")
    
    print("\n📋 Policy Recommendations:")
    for rec in results['policy_recommendations']:
        print(f"  • {rec}")
    
    return results


if __name__ == "__main__":
    test_integrated_predictor()