#!/usr/bin/env python
"""
Recovery Scaler and Residual Smoothing
Handles extreme event magnitudes and smooths predictions
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from collections import deque
import warnings
warnings.filterwarnings('ignore')


class RecoveryScaler:
    """
    Scales predictions based on regime and recovery patterns
    Addresses COVID magnitude misses and other extreme events
    """

    def __init__(self):
        # Asymmetric scaling for crisis vs recovery
        self.crisis_multipliers = {
            'normal': 1.0,
            'expansion': 1.2,
            'crisis': 3.0,  # Amplify negative predictions in crisis
            'recovery': 2.0  # Amplify positive predictions in recovery
        }

        # Track regime transitions
        self.regime_history = deque(maxlen=6)  # 6 months history
        self.transition_patterns = {
            ('crisis', 'normal'): 'recovery_early',
            ('crisis', 'expansion'): 'recovery_strong',
            ('normal', 'crisis'): 'crisis_onset',
            ('expansion', 'crisis'): 'crisis_sudden'
        }

        # Magnitude calibration based on historical extremes
        self.historical_extremes = {
            'US': {'min': -31.4, 'max': 33.4},  # COVID crash and recovery
            'UK': {'min': -19.4, 'max': 17.6},
            'DE': {'min': -10.1, 'max': 7.2},
            'FR': {'min': -13.8, 'max': 18.5},
            'BR': {'min': -9.1, 'max': 7.7},
            'DEFAULT': {'min': -15.0, 'max': 15.0}
        }

    def scale_prediction(self, prediction: float, regime: str,
                        country: str = 'DEFAULT',
                        features: Optional[Dict] = None) -> float:
        """
        Scale prediction based on regime and context

        Args:
            prediction: Base model prediction
            regime: Current regime (crisis/normal/expansion)
            country: Country code for calibration
            features: Optional features for context

        Returns:
            Scaled prediction
        """

        # Get base multiplier
        multiplier = self.crisis_multipliers.get(regime, 1.0)

        # Check for recovery pattern
        if len(self.regime_history) >= 2:
            prev_regime = self.regime_history[-1]
            transition = (prev_regime, regime)

            if transition in self.transition_patterns:
                pattern = self.transition_patterns[transition]

                if pattern == 'recovery_early' and prediction > 0:
                    multiplier *= 1.5  # Boost early recovery
                elif pattern == 'recovery_strong' and prediction > 0:
                    multiplier *= 2.0  # Strong V-shaped recovery
                elif pattern == 'crisis_onset' and prediction < 0:
                    multiplier *= 1.8  # Initial crisis shock
                elif pattern == 'crisis_sudden' and prediction < 0:
                    multiplier *= 2.5  # Sudden crash from expansion

        # Apply asymmetric scaling
        if regime == 'crisis' and prediction < 0:
            # Amplify negative predictions in crisis
            scaled = prediction * multiplier
        elif regime in ['crisis', 'recovery'] and prediction > 0:
            # Also amplify rebounds
            scaled = prediction * (multiplier * 0.7)  # Slightly less for positive
        else:
            scaled = prediction * multiplier

        # Apply extremes calibration
        extremes = self.historical_extremes.get(country, self.historical_extremes['DEFAULT'])

        # Check if we're predicting an extreme event
        if features:
            # Look for extreme indicators
            pmi_shock = features.get('pmi_shock', 0)
            vix_level = features.get('vix_level', 20)
            article_volume = features.get('article_volume_zscore', 0)

            # Extreme negative event detection
            if pmi_shock < -10 and vix_level > 40 and article_volume > 3:
                # Ensure prediction is sufficiently negative
                if scaled > -5:
                    scaled = min(-5, scaled * 2.0)
                # But cap at historical minimum
                scaled = max(extremes['min'] * 0.8, scaled)

            # Extreme positive event (recovery)
            elif pmi_shock > 10 and prev_regime == 'crisis':
                # Ensure prediction is sufficiently positive
                if scaled < 5:
                    scaled = max(5, scaled * 1.5)
                # But cap at historical maximum
                scaled = min(extremes['max'] * 0.8, scaled)

        # Update regime history
        self.regime_history.append(regime)

        return scaled

    def calibrate_to_country(self, country: str, historical_gdp: pd.Series):
        """
        Calibrate scaler to country-specific patterns

        Args:
            country: Country code
            historical_gdp: Historical GDP series for calibration
        """

        if len(historical_gdp) < 4:
            return

        # Update historical extremes
        self.historical_extremes[country] = {
            'min': historical_gdp.min(),
            'max': historical_gdp.max()
        }

        # Calculate typical volatility
        gdp_changes = historical_gdp.diff().dropna()
        typical_vol = gdp_changes.std()

        # Adjust multipliers based on country volatility
        if typical_vol > 5:  # High volatility country
            self.crisis_multipliers['crisis'] = 2.5
        elif typical_vol < 2:  # Low volatility country
            self.crisis_multipliers['crisis'] = 3.5


class ResidualSmoother:
    """
    Smooths predictions using residual patterns and momentum
    Reduces noise while preserving turning points
    """

    def __init__(self, smoothing_window: int = 3):
        self.smoothing_window = smoothing_window
        self.residual_history = deque(maxlen=12)  # Track 12 periods
        self.prediction_history = deque(maxlen=6)
        self.momentum_tracker = MomentumTracker()

    def smooth_prediction(self, raw_prediction: float,
                         features: Optional[Dict] = None,
                         confidence: Optional[Tuple[float, float]] = None) -> float:
        """
        Apply residual-based smoothing

        Args:
            raw_prediction: Unsmoothed prediction
            features: Optional features for context
            confidence: Optional (lower, upper) confidence bounds

        Returns:
            Smoothed prediction
        """

        # If we have history, apply smoothing
        if len(self.prediction_history) >= 2:
            # Calculate momentum
            momentum = self.momentum_tracker.calculate_momentum(
                list(self.prediction_history)
            )

            # Recent average
            recent_avg = np.mean(list(self.prediction_history)[-self.smoothing_window:])

            # Weighted smoothing based on confidence
            if confidence:
                ci_width = confidence[1] - confidence[0]
                # Wide CI = less confidence = more smoothing
                smoothing_weight = min(0.7, ci_width / 10)
            else:
                smoothing_weight = 0.3

            # Check for turning points
            is_turning_point = self._detect_turning_point(raw_prediction, momentum)

            if is_turning_point:
                # Preserve turning points with less smoothing
                smoothed = 0.7 * raw_prediction + 0.3 * recent_avg
            else:
                # Normal smoothing
                smoothed = (1 - smoothing_weight) * raw_prediction + smoothing_weight * recent_avg

            # Apply momentum adjustment
            if abs(momentum) > 0.5:
                # Strong momentum - adjust in direction
                smoothed += momentum * 0.2

        else:
            # No history - return raw
            smoothed = raw_prediction

        # Update history
        self.prediction_history.append(smoothed)

        return smoothed

    def _detect_turning_point(self, current: float, momentum: float) -> bool:
        """
        Detect potential turning points in predictions
        """

        if len(self.prediction_history) < 2:
            return False

        prev = self.prediction_history[-1]
        prev_prev = self.prediction_history[-2] if len(self.prediction_history) > 2 else prev

        # Sign change
        sign_change = (current * prev) < 0

        # Momentum reversal
        momentum_reversal = abs(momentum) > 0.5 and (
            (momentum > 0 and current < prev) or
            (momentum < 0 and current > prev)
        )

        # Large deviation
        large_deviation = abs(current - prev) > 2 * abs(prev - prev_prev) if prev != prev_prev else False

        return sign_change or momentum_reversal or large_deviation

    def update_residuals(self, prediction: float, actual: float):
        """
        Update residual history for learning

        Args:
            prediction: Predicted value
            actual: Actual value
        """

        residual = prediction - actual
        self.residual_history.append(residual)

        # Learn bias pattern
        if len(self.residual_history) >= 6:
            recent_bias = np.mean(list(self.residual_history)[-6:])
            # Will be used in future predictions to correct systematic bias
            self.bias_correction = -recent_bias * 0.5


class MomentumTracker:
    """
    Tracks momentum in prediction series
    """

    def calculate_momentum(self, series: List[float]) -> float:
        """
        Calculate momentum (trend strength)

        Args:
            series: List of recent predictions

        Returns:
            Momentum value (positive = uptrend, negative = downtrend)
        """

        if len(series) < 2:
            return 0.0

        # Simple momentum: weighted average of changes
        changes = np.diff(series)
        if len(changes) == 0:
            return 0.0

        # Recent changes weighted more
        weights = np.exp(np.linspace(-2, 0, len(changes)))
        weights /= weights.sum()

        momentum = np.dot(changes, weights)

        return momentum


class IntegratedScaler:
    """
    Integrates recovery scaling and residual smoothing
    """

    def __init__(self):
        self.recovery_scaler = RecoveryScaler()
        self.residual_smoother = ResidualSmoother()
        self.country_calibrated = {}

    def process_prediction(self, prediction: float, regime: str,
                          country: str, features: Optional[Dict] = None,
                          confidence: Optional[Tuple[float, float]] = None) -> Dict:
        """
        Full processing pipeline for predictions

        Args:
            prediction: Raw model prediction
            regime: Current regime
            country: Country code
            features: Optional features
            confidence: Optional confidence bounds

        Returns:
            Dict with processed prediction and metadata
        """

        # Step 1: Recovery scaling
        scaled_prediction = self.recovery_scaler.scale_prediction(
            prediction, regime, country, features
        )

        # Step 2: Residual smoothing
        smoothed_prediction = self.residual_smoother.smooth_prediction(
            scaled_prediction, features, confidence
        )

        # Step 3: Adjust confidence intervals if provided
        if confidence:
            # Scale confidence bounds similarly
            scaled_lower = self.recovery_scaler.scale_prediction(
                confidence[0], regime, country, features
            )
            scaled_upper = self.recovery_scaler.scale_prediction(
                confidence[1], regime, country, features
            )

            # Ensure smoothed prediction is within bounds
            smoothed_prediction = np.clip(
                smoothed_prediction,
                min(scaled_lower, scaled_upper),
                max(scaled_lower, scaled_upper)
            )

            adjusted_confidence = (scaled_lower, scaled_upper)
        else:
            adjusted_confidence = None

        return {
            'raw_prediction': prediction,
            'scaled_prediction': scaled_prediction,
            'final_prediction': smoothed_prediction,
            'regime': regime,
            'confidence': adjusted_confidence,
            'scaling_applied': abs(scaled_prediction - prediction) > 0.1,
            'smoothing_applied': abs(smoothed_prediction - scaled_prediction) > 0.1
        }

    def calibrate(self, country: str, historical_gdp: pd.Series):
        """
        Calibrate for a specific country
        """

        self.recovery_scaler.calibrate_to_country(country, historical_gdp)
        self.country_calibrated[country] = True

    def update_with_actual(self, prediction: float, actual: float):
        """
        Update with actual values for learning
        """

        self.residual_smoother.update_residuals(prediction, actual)


def test_recovery_scaler():
    """Test recovery scaling and smoothing"""

    print("🎯 TESTING RECOVERY SCALER & SMOOTHING")
    print("="*60)

    # Initialize integrated scaler
    scaler = IntegratedScaler()

    # Test 1: Normal prediction
    print("\n1. Normal Period:")
    result = scaler.process_prediction(
        prediction=2.0,
        regime='normal',
        country='US',
        confidence=(1.0, 3.0)
    )
    print(f"   Raw: {result['raw_prediction']:.1f}")
    print(f"   Scaled: {result['scaled_prediction']:.1f}")
    print(f"   Final: {result['final_prediction']:.1f}")

    # Test 2: Crisis prediction (should amplify)
    print("\n2. Crisis Period (negative):")
    result = scaler.process_prediction(
        prediction=-5.0,
        regime='crisis',
        country='US',
        features={'pmi_shock': -15, 'vix_level': 50},
        confidence=(-7.0, -3.0)
    )
    print(f"   Raw: {result['raw_prediction']:.1f}")
    print(f"   Scaled: {result['scaled_prediction']:.1f} (3x multiplier)")
    print(f"   Final: {result['final_prediction']:.1f}")

    # Test 3: Recovery prediction (should amplify positive)
    print("\n3. Recovery Period (positive):")
    # Simulate regime transition
    scaler.recovery_scaler.regime_history.append('crisis')
    result = scaler.process_prediction(
        prediction=8.0,
        regime='normal',  # Transitioning from crisis to normal
        country='US',
        features={'pmi_shock': 10},
        confidence=(5.0, 11.0)
    )
    print(f"   Raw: {result['raw_prediction']:.1f}")
    print(f"   Scaled: {result['scaled_prediction']:.1f} (recovery boost)")
    print(f"   Final: {result['final_prediction']:.1f}")

    # Test 4: Extreme event (COVID-like)
    print("\n4. Extreme Event Detection:")
    result = scaler.process_prediction(
        prediction=-8.0,
        regime='crisis',
        country='US',
        features={
            'pmi_shock': -20,
            'vix_level': 65,
            'article_volume_zscore': 4.0
        },
        confidence=(-12.0, -4.0)
    )
    print(f"   Raw: {result['raw_prediction']:.1f}")
    print(f"   Scaled: {result['scaled_prediction']:.1f} (extreme amplification)")
    print(f"   Final: {result['final_prediction']:.1f}")
    print(f"   Should capture COVID-like magnitude")

    # Test 5: Smoothing over time
    print("\n5. Smoothing Test (sequence):")
    predictions = [2.0, 2.5, -1.0, 3.0, 2.8]  # Note the outlier
    smoothed = []

    for pred in predictions:
        result = scaler.process_prediction(
            prediction=pred,
            regime='normal',
            country='US'
        )
        smoothed.append(result['final_prediction'])

    print(f"   Raw sequence: {[f'{p:.1f}' for p in predictions]}")
    print(f"   Smoothed:     {[f'{s:.1f}' for s in smoothed]}")
    print(f"   Outlier (-1.0) smoothed to preserve trend")

    # Test 6: Country calibration
    print("\n6. Country Calibration:")
    # Simulate UK historical data (lower volatility)
    uk_historical = pd.Series([-19.4, 17.6, 1.3, -1.3, 5.5, 1.0, 1.3])
    scaler.calibrate('UK', uk_historical)

    result_uk = scaler.process_prediction(
        prediction=-5.0,
        regime='crisis',
        country='UK'
    )
    print(f"   UK crisis prediction: {result_uk['final_prediction']:.1f}")
    print(f"   (Calibrated to UK historical extremes)")


if __name__ == "__main__":
    test_recovery_scaler()