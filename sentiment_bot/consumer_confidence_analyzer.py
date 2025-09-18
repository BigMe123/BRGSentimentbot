#!/usr/bin/env python3
"""
Sophisticated Consumer Confidence Analyzer
==========================================

Advanced consumer confidence analysis combining sentiment, economic indicators,
and behavioral signals using state-of-the-art econometric techniques.

Author: BSG Team
Created: 2025-01-15
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import logging
from scipy import stats, signal
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestRegressor
import warnings

warnings.filterwarnings('ignore')
logger = logging.getLogger(__name__)


class ConfidenceComponent(Enum):
    """Components of consumer confidence."""
    CURRENT_CONDITIONS = "current_conditions"
    FUTURE_EXPECTATIONS = "future_expectations"
    PURCHASE_INTENTIONS = "purchase_intentions"
    EMPLOYMENT_OUTLOOK = "employment_outlook"
    INCOME_EXPECTATIONS = "income_expectations"


@dataclass
class ConfidenceIndicators:
    """Consumer confidence indicators."""
    overall_index: float
    current_index: float
    expectations_index: float
    components: Dict[str, float]
    sentiment_contribution: float
    economic_contribution: float
    behavioral_contribution: float
    confidence_interval: Tuple[float, float]
    trend: str  # 'improving', 'stable', 'declining'
    momentum: float
    volatility: float
    timestamp: datetime = field(default_factory=datetime.now)


class SentimentConfidenceModel:
    """Maps sentiment to consumer confidence."""

    def __init__(self):
        self.weights = {
            'overall': 0.3,
            'economic': 0.25,
            'employment': 0.2,
            'inflation': 0.15,
            'market': 0.1
        }
        self.scaler = StandardScaler()
        self.history = []

    def calculate_confidence(self, sentiment_data: Dict[str, float]) -> float:
        """Calculate confidence from sentiment."""
        # Weighted average of sentiment components
        confidence = 0
        total_weight = 0

        for component, weight in self.weights.items():
            if component in sentiment_data:
                # Transform sentiment (-1 to 1) to confidence (0 to 100)
                value = (sentiment_data[component] + 1) * 50
                confidence += value * weight
                total_weight += weight

        if total_weight > 0:
            confidence /= total_weight

        # Apply non-linear transformation for realism
        confidence = self._apply_behavioral_adjustment(confidence)

        # Store in history
        self.history.append(confidence)
        if len(self.history) > 100:
            self.history.pop(0)

        return confidence

    def _apply_behavioral_adjustment(self, confidence: float) -> float:
        """Apply behavioral economics adjustments."""
        # Loss aversion: negative sentiment has stronger impact
        if confidence < 50:
            confidence = 50 - 1.5 * (50 - confidence)

        # Bounded rationality: extreme values are moderated
        if confidence > 80:
            confidence = 80 + 0.5 * (confidence - 80)
        elif confidence < 20:
            confidence = 20 - 0.5 * (20 - confidence)

        # Ensure bounds
        return np.clip(confidence, 0, 100)

    def get_trend(self) -> str:
        """Determine confidence trend."""
        if len(self.history) < 3:
            return 'stable'

        recent = np.mean(self.history[-3:])
        previous = np.mean(self.history[-6:-3]) if len(self.history) >= 6 else self.history[0]

        if recent > previous + 2:
            return 'improving'
        elif recent < previous - 2:
            return 'declining'
        else:
            return 'stable'


class EconomicConfidenceModel:
    """Economic indicators to confidence mapping."""

    def __init__(self):
        self.indicators = {
            'gdp_growth': {'weight': 0.25, 'optimal': 2.5},
            'unemployment': {'weight': 0.3, 'optimal': 3.5, 'inverse': True},
            'inflation': {'weight': 0.2, 'optimal': 2.0, 'inverse': True},
            'wage_growth': {'weight': 0.15, 'optimal': 3.0},
            'retail_sales': {'weight': 0.1, 'optimal': 3.5}
        }

    def calculate_confidence(self, economic_data: Dict[str, float]) -> float:
        """Calculate confidence from economic indicators."""
        confidence = 0
        total_weight = 0

        for indicator, config in self.indicators.items():
            if indicator in economic_data:
                value = economic_data[indicator]
                optimal = config['optimal']
                weight = config['weight']

                # Calculate distance from optimal
                if config.get('inverse', False):
                    # Lower is better (e.g., unemployment)
                    if value <= optimal:
                        score = 100
                    else:
                        score = max(0, 100 - 10 * (value - optimal))
                else:
                    # Higher is better (e.g., GDP growth)
                    if value >= optimal:
                        score = 100
                    else:
                        score = max(0, 100 - 20 * (optimal - value))

                confidence += score * weight
                total_weight += weight

        if total_weight > 0:
            confidence /= total_weight

        return confidence


class BehavioralSignalAnalyzer:
    """Analyzes behavioral signals for confidence."""

    def __init__(self):
        self.signals = {
            'search_volume': {'weight': 0.2},
            'social_sentiment': {'weight': 0.3},
            'news_tone': {'weight': 0.25},
            'market_volatility': {'weight': 0.25, 'inverse': True}
        }

    def analyze_signals(self, behavioral_data: Dict[str, Any]) -> float:
        """Analyze behavioral signals."""
        confidence = 50  # Neutral baseline

        # Search trends analysis
        if 'search_trends' in behavioral_data:
            trends = behavioral_data['search_trends']
            positive_searches = trends.get('positive_terms', 0)
            negative_searches = trends.get('negative_terms', 0)

            if positive_searches + negative_searches > 0:
                search_sentiment = positive_searches / (positive_searches + negative_searches)
                confidence += (search_sentiment - 0.5) * 20

        # Social media momentum
        if 'social_momentum' in behavioral_data:
            momentum = behavioral_data['social_momentum']
            confidence += momentum * 10

        # News coverage tone
        if 'news_tone' in behavioral_data:
            tone = behavioral_data['news_tone']
            confidence += tone * 15

        # Market behavior (inverse relationship with volatility)
        if 'market_volatility' in behavioral_data:
            volatility = behavioral_data['market_volatility']
            # High volatility reduces confidence
            confidence -= min(volatility * 100, 20)

        return np.clip(confidence, 0, 100)


class AdvancedConfidencePredictor:
    """Advanced ML-based confidence predictor."""

    def __init__(self):
        self.model = RandomForestRegressor(
            n_estimators=100,
            max_depth=10,
            random_state=42
        )
        self.pca = PCA(n_components=5)
        self.scaler = StandardScaler()
        self.is_trained = False

    def train(self, historical_data: pd.DataFrame, confidence_values: pd.Series):
        """Train the predictor."""
        # Prepare features
        X = self.scaler.fit_transform(historical_data)

        if X.shape[1] > 5:
            X = self.pca.fit_transform(X)

        # Train model
        self.model.fit(X, confidence_values)
        self.is_trained = True

        # Calculate feature importance
        if hasattr(self.model, 'feature_importances_'):
            importances = self.model.feature_importances_
            logger.info(f"Feature importances: {importances}")

    def predict(self, current_data: pd.DataFrame) -> Tuple[float, Tuple[float, float]]:
        """Predict confidence with uncertainty."""
        if not self.is_trained:
            return 50.0, (40.0, 60.0)  # Return neutral if not trained

        # Prepare features
        X = self.scaler.transform(current_data)

        if hasattr(self.pca, 'components_'):
            X = self.pca.transform(X)

        # Get predictions from all trees for uncertainty
        predictions = []
        for estimator in self.model.estimators_:
            pred = estimator.predict(X)[0]
            predictions.append(pred)

        mean_pred = np.mean(predictions)
        std_pred = np.std(predictions)

        # 95% confidence interval
        ci_lower = mean_pred - 1.96 * std_pred
        ci_upper = mean_pred + 1.96 * std_pred

        return mean_pred, (ci_lower, ci_upper)


class ConsumerConfidenceAnalyzer:
    """Main consumer confidence analyzer."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.sentiment_model = SentimentConfidenceModel()
        self.economic_model = EconomicConfidenceModel()
        self.behavioral_analyzer = BehavioralSignalAnalyzer()
        self.predictor = AdvancedConfidencePredictor()
        self.history: List[ConfidenceIndicators] = []

    def analyze(
        self,
        sentiment_data: Dict[str, float],
        economic_data: Optional[Dict[str, float]] = None,
        behavioral_data: Optional[Dict[str, Any]] = None
    ) -> ConfidenceIndicators:
        """Perform comprehensive confidence analysis."""

        # Calculate component scores
        sentiment_confidence = self.sentiment_model.calculate_confidence(sentiment_data)

        economic_confidence = 50  # Default neutral
        if economic_data:
            economic_confidence = self.economic_model.calculate_confidence(economic_data)

        behavioral_confidence = 50  # Default neutral
        if behavioral_data:
            behavioral_confidence = self.behavioral_analyzer.analyze_signals(behavioral_data)

        # Weighted combination
        weights = self.config.get('weights', {
            'sentiment': 0.4,
            'economic': 0.35,
            'behavioral': 0.25
        })

        overall_index = (
            sentiment_confidence * weights['sentiment'] +
            economic_confidence * weights['economic'] +
            behavioral_confidence * weights['behavioral']
        )

        # Calculate sub-indices
        current_index = self._calculate_current_conditions(
            sentiment_confidence, economic_confidence
        )
        expectations_index = self._calculate_future_expectations(
            sentiment_confidence, behavioral_confidence
        )

        # Component breakdown
        components = self._calculate_components(
            sentiment_data, economic_data, behavioral_data
        )

        # Calculate trend and momentum
        trend = self.sentiment_model.get_trend()
        momentum = self._calculate_momentum()
        volatility = self._calculate_volatility()

        # Confidence interval
        ci_lower = max(0, overall_index - volatility * 10)
        ci_upper = min(100, overall_index + volatility * 10)

        # Create indicators
        indicators = ConfidenceIndicators(
            overall_index=overall_index,
            current_index=current_index,
            expectations_index=expectations_index,
            components=components,
            sentiment_contribution=sentiment_confidence,
            economic_contribution=economic_confidence,
            behavioral_contribution=behavioral_confidence,
            confidence_interval=(ci_lower, ci_upper),
            trend=trend,
            momentum=momentum,
            volatility=volatility
        )

        # Store in history
        self.history.append(indicators)
        if len(self.history) > 100:
            self.history.pop(0)

        return indicators

    def _calculate_current_conditions(
        self, sentiment: float, economic: float
    ) -> float:
        """Calculate current conditions index."""
        # Current conditions weighted more toward economic indicators
        return sentiment * 0.3 + economic * 0.7

    def _calculate_future_expectations(
        self, sentiment: float, behavioral: float
    ) -> float:
        """Calculate future expectations index."""
        # Future expectations weighted more toward sentiment and behavioral
        return sentiment * 0.6 + behavioral * 0.4

    def _calculate_components(self,
        sentiment_data: Optional[Dict[str, float]],
        economic_data: Optional[Dict[str, float]],
        behavioral_data: Optional[Dict[str, Any]]
    ) -> Dict[str, float]:
        """Calculate detailed components."""
        components = {}

        # Current conditions component
        if economic_data:
            if 'unemployment' in economic_data:
                employment_score = max(0, 100 - economic_data['unemployment'] * 10)
                components[ConfidenceComponent.EMPLOYMENT_OUTLOOK.value] = employment_score

            if 'wage_growth' in economic_data:
                income_score = min(100, economic_data['wage_growth'] * 25)
                components[ConfidenceComponent.INCOME_EXPECTATIONS.value] = income_score

        # Purchase intentions from behavioral data
        if behavioral_data and 'purchase_intent' in behavioral_data:
            components[ConfidenceComponent.PURCHASE_INTENTIONS.value] = \
                behavioral_data['purchase_intent'] * 100
        else:
            # Derive from sentiment
            if sentiment_data and 'consumer' in sentiment_data:
                components[ConfidenceComponent.PURCHASE_INTENTIONS.value] = \
                    (sentiment_data['consumer'] + 1) * 50

        # Add current and future components
        if sentiment_data:
            overall_sent = sentiment_data.get('overall', 0)
            components[ConfidenceComponent.CURRENT_CONDITIONS.value] = \
                (overall_sent + 1) * 40 + 20  # Scale to 20-100
            components[ConfidenceComponent.FUTURE_EXPECTATIONS.value] = \
                (overall_sent + 1) * 50 + 25  # Slightly more optimistic

        return components

    def _calculate_momentum(self) -> float:
        """Calculate confidence momentum."""
        if len(self.history) < 2:
            return 0

        current = self.history[-1].overall_index
        previous = self.history[-2].overall_index

        return (current - previous) / max(previous, 1)

    def _calculate_volatility(self) -> float:
        """Calculate confidence volatility."""
        if len(self.history) < 5:
            return 1.0

        recent_values = [h.overall_index for h in self.history[-10:]]
        return np.std(recent_values) / 10  # Normalize

    def get_historical_trend(self, periods: int = 10) -> Dict[str, Any]:
        """Get historical trend analysis."""
        if len(self.history) < periods:
            return {"error": "Insufficient history"}

        recent = self.history[-periods:]

        trend_data = {
            'overall': [h.overall_index for h in recent],
            'current': [h.current_index for h in recent],
            'expectations': [h.expectations_index for h in recent],
            'timestamps': [h.timestamp for h in recent]
        }

        # Calculate statistics
        overall_values = trend_data['overall']
        trend_data['statistics'] = {
            'mean': np.mean(overall_values),
            'std': np.std(overall_values),
            'min': np.min(overall_values),
            'max': np.max(overall_values),
            'trend': 'up' if overall_values[-1] > overall_values[0] else 'down'
        }

        return trend_data

    def generate_narrative(self, indicators: ConfidenceIndicators) -> str:
        """Generate narrative description of confidence."""
        narrative = []

        # Overall assessment
        if indicators.overall_index >= 70:
            narrative.append("Consumer confidence is strong")
        elif indicators.overall_index >= 50:
            narrative.append("Consumer confidence is moderate")
        else:
            narrative.append("Consumer confidence is weak")

        # Trend
        if indicators.trend == 'improving':
            narrative.append("and improving")
        elif indicators.trend == 'declining':
            narrative.append("and declining")
        else:
            narrative.append("and stable")

        # Current vs expectations
        if indicators.expectations_index > indicators.current_index + 5:
            narrative.append("with optimistic future outlook")
        elif indicators.current_index > indicators.expectations_index + 5:
            narrative.append("but with cautious future outlook")

        # Volatility
        if indicators.volatility > 0.5:
            narrative.append("(high uncertainty)")

        return " ".join(narrative) + "."


# Factory function
def create_confidence_analyzer(**kwargs) -> ConsumerConfidenceAnalyzer:
    """Create configured confidence analyzer."""
    config = {
        'weights': kwargs.get('weights', {
            'sentiment': 0.4,
            'economic': 0.35,
            'behavioral': 0.25
        }),
        **kwargs
    }
    return ConsumerConfidenceAnalyzer(config)