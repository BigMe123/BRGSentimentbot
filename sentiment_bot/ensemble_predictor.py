#!/usr/bin/env python
"""
Soft-Gated Ensemble Predictor
=============================
Combines crisis and normal models with calibrated probability weighting
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
import logging

# Import existing components
from .comprehensive_economic_predictors import PredictionResult
from .production_economic_predictor import (
    CrisisDetector,
    DualRegimePredictor,
    ProductionEconomicPredictor
)

logger = logging.getLogger(__name__)


@dataclass
class EnsembleResult:
    """Enhanced prediction result with ensemble metadata"""
    prediction: PredictionResult
    crisis_probability: float
    normal_weight: float
    crisis_weight: float
    component_predictions: Dict[str, float]
    ensemble_confidence: float
    regime_stability: float


class CalibratedCrisisClassifier:
    """Crisis classifier with probability calibration"""

    def __init__(self):
        self.base_detector = CrisisDetector()
        self.calibration_curve = self._build_calibration_curve()
        self.regime_persistence = 0.7  # Regime sticky factor

    def _build_calibration_curve(self) -> Dict[str, float]:
        """Build probability calibration curve from historical data"""

        # Historical calibration points (crisis_score -> actual_crisis_probability)
        # These would be fitted from backtest data in production
        calibration_points = {
            0.0: 0.02,   # Very low score -> 2% crisis probability
            0.1: 0.05,   # Low score -> 5% crisis probability
            0.2: 0.10,   # Borderline -> 10% crisis probability
            0.3: 0.25,   # Threshold -> 25% crisis probability
            0.4: 0.45,   # Moderate -> 45% crisis probability
            0.5: 0.65,   # High -> 65% crisis probability
            0.6: 0.80,   # Very high -> 80% crisis probability
            0.7: 0.90,   # Extreme -> 90% crisis probability
            0.8: 0.95,   # Crisis -> 95% crisis probability
            1.0: 0.98    # Maximum -> 98% crisis probability
        }

        return calibration_points

    def _interpolate_probability(self, raw_score: float) -> float:
        """Interpolate calibrated probability from raw score"""

        # Clamp score to valid range
        raw_score = np.clip(raw_score, 0.0, 1.0)

        # Find bracketing points
        scores = sorted(self.calibration_curve.keys())

        if raw_score <= scores[0]:
            return self.calibration_curve[scores[0]]
        if raw_score >= scores[-1]:
            return self.calibration_curve[scores[-1]]

        # Linear interpolation
        for i in range(len(scores) - 1):
            if scores[i] <= raw_score <= scores[i + 1]:
                x0, x1 = scores[i], scores[i + 1]
                y0, y1 = self.calibration_curve[x0], self.calibration_curve[x1]

                # Linear interpolation
                alpha = (raw_score - x0) / (x1 - x0)
                return y0 + alpha * (y1 - y0)

        return 0.5  # Fallback

    def detect_with_calibration(self,
                              sentiment_score: float,
                              context_text: str,
                              topic_factors: Dict,
                              previous_regime: str = 'normal') -> Tuple[float, str]:
        """Detect crisis with calibrated probability"""

        # Get raw detection
        raw_is_crisis, raw_prob = self.base_detector.detect_crisis(
            sentiment_score, context_text, topic_factors
        )

        # Apply calibration
        calibrated_prob = self._interpolate_probability(raw_prob)

        # Apply regime persistence (regimes tend to persist)
        if previous_regime == 'crisis':
            # Increase probability if previously in crisis
            calibrated_prob = calibrated_prob * (1 + self.regime_persistence * 0.3)
        elif previous_regime == 'normal':
            # Slight decrease if previously normal
            calibrated_prob = calibrated_prob * (1 - self.regime_persistence * 0.1)

        # Final probability bounds
        calibrated_prob = np.clip(calibrated_prob, 0.01, 0.99)

        # Determine regime
        regime = 'crisis' if calibrated_prob > 0.3 else 'normal'

        return calibrated_prob, regime


class SoftGatedEnsemble:
    """Soft-gated ensemble combining crisis and normal models"""

    def __init__(self):
        self.crisis_classifier = CalibratedCrisisClassifier()
        self.dual_predictor = DualRegimePredictor()
        self.previous_regime = 'normal'
        self.regime_history = []

        # Ensemble parameters
        self.min_weight = 0.05  # Minimum weight for any model
        self.confidence_boost = 0.1  # Confidence boost for ensemble

    def _calculate_regime_stability(self, window: int = 5) -> float:
        """Calculate regime stability score"""

        if len(self.regime_history) < window:
            return 0.5  # Neutral stability

        recent_regimes = self.regime_history[-window:]
        regime_changes = sum(1 for i in range(1, len(recent_regimes))
                           if recent_regimes[i] != recent_regimes[i-1])

        # Stability = 1 - (changes / possible_changes)
        max_changes = len(recent_regimes) - 1
        stability = 1 - (regime_changes / max_changes) if max_changes > 0 else 1

        return stability

    def _soft_gate_weights(self, crisis_prob: float) -> Tuple[float, float]:
        """Calculate soft gating weights"""

        # Base weights from probability
        crisis_weight = crisis_prob
        normal_weight = 1 - crisis_prob

        # Apply minimum weights to avoid complete shutoff
        crisis_weight = max(self.min_weight, crisis_weight)
        normal_weight = max(self.min_weight, normal_weight)

        # Renormalize
        total_weight = crisis_weight + normal_weight
        crisis_weight /= total_weight
        normal_weight /= total_weight

        return normal_weight, crisis_weight

    def _combine_predictions(self,
                           normal_pred: float,
                           crisis_pred: float,
                           normal_uncertainty: float,
                           crisis_uncertainty: float,
                           normal_weight: float,
                           crisis_weight: float) -> Tuple[float, float]:
        """Combine predictions with uncertainty weighting"""

        # Weighted prediction
        ensemble_pred = normal_weight * normal_pred + crisis_weight * crisis_pred

        # Combined uncertainty (uncertainty propagation)
        combined_uncertainty = np.sqrt(
            (normal_weight ** 2) * (normal_uncertainty ** 2) +
            (crisis_weight ** 2) * (crisis_uncertainty ** 2) +
            2 * normal_weight * crisis_weight * 0.3 * normal_uncertainty * crisis_uncertainty  # Correlation term
        )

        return ensemble_pred, combined_uncertainty

    def _assess_ensemble_confidence(self,
                                  normal_weight: float,
                                  crisis_weight: float,
                                  crisis_prob: float,
                                  regime_stability: float) -> float:
        """Assess confidence in ensemble prediction"""

        # Base confidence from weight balance
        weight_entropy = -(normal_weight * np.log(normal_weight + 1e-8) +
                          crisis_weight * np.log(crisis_weight + 1e-8))
        max_entropy = -2 * 0.5 * np.log(0.5)  # Maximum entropy for 2 components
        weight_confidence = 1 - (weight_entropy / max_entropy)

        # Regime clarity confidence (clear regime = higher confidence)
        regime_clarity = 2 * abs(crisis_prob - 0.5)  # Distance from 50/50

        # Stability confidence
        stability_confidence = regime_stability

        # Combined confidence
        ensemble_confidence = (
            0.4 * weight_confidence +
            0.3 * regime_clarity +
            0.3 * stability_confidence
        ) + self.confidence_boost

        return np.clip(ensemble_confidence, 0.1, 0.95)

    def predict_ensemble(self,
                        sentiment_score: float,
                        topic_factors: Dict,
                        context_text: str = "") -> EnsembleResult:
        """Generate ensemble prediction"""

        # Step 1: Crisis detection with calibration
        crisis_prob, current_regime = self.crisis_classifier.detect_with_calibration(
            sentiment_score, context_text, topic_factors, self.previous_regime
        )

        # Update regime history
        self.regime_history.append(current_regime)
        if len(self.regime_history) > 20:  # Keep last 20 observations
            self.regime_history = self.regime_history[-20:]

        # Step 2: Calculate regime stability
        regime_stability = self._calculate_regime_stability()

        # Step 3: Get predictions from both models
        normal_pred = self.dual_predictor.predict_normal(sentiment_score, topic_factors)
        crisis_pred, crisis_uncertainty = self.dual_predictor.predict_crisis(sentiment_score, topic_factors)
        normal_uncertainty = 1.5  # Normal model uncertainty

        # Step 4: Calculate soft gating weights
        normal_weight, crisis_weight = self._soft_gate_weights(crisis_prob)

        # Step 5: Combine predictions
        ensemble_pred, ensemble_uncertainty = self._combine_predictions(
            normal_pred, crisis_pred,
            normal_uncertainty, crisis_uncertainty,
            normal_weight, crisis_weight
        )

        # Step 6: Assess ensemble confidence
        ensemble_confidence = self._assess_ensemble_confidence(
            normal_weight, crisis_weight, crisis_prob, regime_stability
        )

        # Step 7: Generate confidence intervals
        ci_multiplier = 1.96  # 95% confidence
        ci_lower = ensemble_pred - ci_multiplier * ensemble_uncertainty
        ci_upper = ensemble_pred + ci_multiplier * ensemble_uncertainty

        # Step 8: Determine direction and magnitude
        direction = 'positive' if ensemble_pred > 2.5 else 'negative'
        magnitude = 'extreme' if abs(ensemble_pred) > 5.0 else \
                   'significant' if abs(ensemble_pred - 2.5) > 2.0 else 'moderate'

        # Step 9: Key drivers (weighted by model contribution)
        drivers = []
        if normal_weight > 0.6:
            drivers.append("Normal economic conditions dominate")
        elif crisis_weight > 0.6:
            drivers.append("Crisis conditions detected")
        else:
            drivers.append("Mixed regime signals")

        if sentiment_score < 0.3:
            drivers.append("Negative sentiment")
        elif sentiment_score > 0.7:
            drivers.append("Positive sentiment")

        # Most influential factors
        top_factors = sorted(topic_factors.items(), key=lambda x: abs(x[1]), reverse=True)[:2]
        for factor, value in top_factors:
            if abs(value) > 0.5:
                direction_str = 'positive' if value > 0 else 'negative'
                drivers.append(f"{direction_str.title()} {factor} impact")

        # Create prediction result
        prediction_result = PredictionResult(
            indicator="GDP_ensemble",
            prediction=ensemble_pred,
            confidence=ensemble_confidence,
            timeframe="next_quarter",
            direction=direction,
            drivers=drivers,
            range_low=ci_lower,
            range_high=ci_upper,
            metadata={
                "ensemble_method": "soft_gated",
                "crisis_probability": crisis_prob,
                "normal_weight": normal_weight,
                "crisis_weight": crisis_weight,
                "regime_stability": regime_stability,
                "component_predictions": {
                    "normal": normal_pred,
                    "crisis": crisis_pred
                },
                "component_uncertainties": {
                    "normal": normal_uncertainty,
                    "crisis": crisis_uncertainty,
                    "ensemble": ensemble_uncertainty
                },
                "regime_history": self.regime_history[-5:],  # Last 5 regimes
                "calibrated_classifier": True
            }
        )

        # Update state
        self.previous_regime = current_regime

        return EnsembleResult(
            prediction=prediction_result,
            crisis_probability=crisis_prob,
            normal_weight=normal_weight,
            crisis_weight=crisis_weight,
            component_predictions={
                "normal": normal_pred,
                "crisis": crisis_pred,
                "ensemble": ensemble_pred
            },
            ensemble_confidence=ensemble_confidence,
            regime_stability=regime_stability
        )


class EnhancedEconomicPredictor:
    """Enhanced predictor using soft-gated ensemble"""

    def __init__(self):
        self.ensemble = SoftGatedEnsemble()

    def predict_with_ensemble(self,
                            sentiment_score: float,
                            topic_factors: Dict,
                            context_text: str = "") -> Dict:
        """Main prediction interface with ensemble"""

        # Generate ensemble prediction
        ensemble_result = self.ensemble.predict_ensemble(
            sentiment_score, topic_factors, context_text
        )

        # Create comprehensive result
        result = {
            'prediction': {
                'gdp_forecast': round(ensemble_result.prediction.prediction, 1),
                'direction': ensemble_result.prediction.direction,
                'magnitude': ensemble_result.prediction.metadata.get('magnitude', 'moderate'),
                'confidence_intervals': {
                    '95_percent': [
                        round(ensemble_result.prediction.range_low, 1),
                        round(ensemble_result.prediction.range_high, 1)
                    ]
                }
            },
            'ensemble_details': {
                'crisis_probability': round(ensemble_result.crisis_probability, 3),
                'normal_model_weight': round(ensemble_result.normal_weight, 3),
                'crisis_model_weight': round(ensemble_result.crisis_weight, 3),
                'regime_stability': round(ensemble_result.regime_stability, 3),
                'ensemble_confidence': round(ensemble_result.ensemble_confidence, 3)
            },
            'component_predictions': {
                'normal_model': round(ensemble_result.component_predictions['normal'], 1),
                'crisis_model': round(ensemble_result.component_predictions['crisis'], 1),
                'ensemble_result': round(ensemble_result.component_predictions['ensemble'], 1)
            },
            'regime_indicators': {
                'current_regime': 'crisis' if ensemble_result.crisis_probability > 0.3 else 'normal',
                'regime_certainty': 'HIGH' if abs(ensemble_result.crisis_probability - 0.5) > 0.3 else 'MEDIUM',
                'stability_indicator': 'STABLE' if ensemble_result.regime_stability > 0.7 else
                                    'VOLATILE' if ensemble_result.regime_stability < 0.3 else 'MIXED'
            },
            'key_drivers': ensemble_result.prediction.drivers,
            'metadata': {
                'model_type': 'soft_gated_ensemble',
                'timestamp': datetime.now().isoformat(),
                'regime_history': ensemble_result.prediction.metadata['regime_history'],
                'calibrated': True
            }
        }

        return result

    def get_model_diagnostics(self) -> Dict:
        """Get diagnostic information about the ensemble"""

        return {
            'ensemble_state': {
                'previous_regime': self.ensemble.previous_regime,
                'regime_history_length': len(self.ensemble.regime_history),
                'recent_regimes': self.ensemble.regime_history[-5:] if self.ensemble.regime_history else []
            },
            'calibration_info': {
                'calibration_points': len(self.ensemble.crisis_classifier.calibration_curve),
                'regime_persistence': self.ensemble.crisis_classifier.regime_persistence
            },
            'ensemble_parameters': {
                'min_weight': self.ensemble.min_weight,
                'confidence_boost': self.ensemble.confidence_boost
            }
        }


# Example usage and testing
def test_ensemble_predictor():
    """Test the ensemble predictor"""

    print("🔬 TESTING SOFT-GATED ENSEMBLE PREDICTOR")
    print("="*60)

    predictor = EnhancedEconomicPredictor()

    # Test scenarios
    test_cases = [
        {
            'name': 'Normal Growth',
            'sentiment': 0.6,
            'context': 'steady economic growth consumer confidence stable employment',
            'factors': {'fiscal': 0.2, 'monetary': 0.0, 'trade': 0.1, 'geopolitical': 0.0, 'supply_chain': 0.0}
        },
        {
            'name': 'Crisis Conditions',
            'sentiment': 0.15,
            'context': 'economic crisis recession unemployment surge market crash',
            'factors': {'fiscal': 0.5, 'monetary': 0.8, 'trade': -0.5, 'geopolitical': -1.5, 'supply_chain': -2.0}
        },
        {
            'name': 'Mixed Signals',
            'sentiment': 0.4,
            'context': 'economic uncertainty mixed signals inflation concerns growth',
            'factors': {'fiscal': -0.2, 'monetary': 0.3, 'trade': -0.1, 'geopolitical': -0.5, 'supply_chain': 0.2}
        }
    ]

    for case in test_cases:
        print(f"\n🧪 Testing: {case['name']}")
        print("-" * 40)

        result = predictor.predict_with_ensemble(
            case['sentiment'], case['factors'], case['context']
        )

        print(f"Context:           {case['context'][:50]}...")
        print(f"Crisis Probability: {result['ensemble_details']['crisis_probability']:.1%}")
        print(f"Normal Weight:     {result['ensemble_details']['normal_model_weight']:.1%}")
        print(f"Crisis Weight:     {result['ensemble_details']['crisis_model_weight']:.1%}")
        print(f"Ensemble Result:   {result['prediction']['gdp_forecast']}%")
        print(f"Components:        Normal={result['component_predictions']['normal_model']}%, " +
              f"Crisis={result['component_predictions']['crisis_model']}%")
        print(f"Ensemble Conf:     {result['ensemble_details']['ensemble_confidence']:.1%}")
        print(f"Regime:           {result['regime_indicators']['current_regime'].upper()}")
        print(f"Stability:        {result['regime_indicators']['stability_indicator']}")


if __name__ == "__main__":
    test_ensemble_predictor()


# Export main classes
__all__ = [
    'SoftGatedEnsemble',
    'EnhancedEconomicPredictor',
    'EnsembleResult',
    'CalibratedCrisisClassifier'
]