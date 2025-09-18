#!/usr/bin/env python3
"""
Shock Detection and Robust Loss Functions for GDP Forecasting
==============================================================
Implements structural break detection, crisis handling, and robust
estimation techniques for improved performance during economic shocks.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import ruptures as rpt
from scipy import stats
from sklearn.linear_model import HuberRegressor
import warnings
import logging

warnings.filterwarnings('ignore')
logger = logging.getLogger(__name__)


@dataclass
class ShockEvent:
    """Represents a detected economic shock"""
    start_date: pd.Timestamp
    end_date: Optional[pd.Timestamp]
    severity: float  # 0-1 scale
    type: str  # 'financial', 'pandemic', 'geopolitical', 'energy', 'unknown'
    confidence: float


class StructuralBreakDetector:
    """
    Detects structural breaks and economic shocks using multiple methods
    """

    def __init__(self):
        self.known_shocks = self._load_known_shocks()
        self.detected_breaks = []

    def _load_known_shocks(self) -> List[ShockEvent]:
        """Load database of known economic shocks"""
        return [
            ShockEvent(
                start_date=pd.Timestamp('2008-09-01'),
                end_date=pd.Timestamp('2009-06-30'),
                severity=0.9,
                type='financial',
                confidence=1.0
            ),
            ShockEvent(
                start_date=pd.Timestamp('2020-03-01'),
                end_date=pd.Timestamp('2021-06-30'),
                severity=1.0,
                type='pandemic',
                confidence=1.0
            ),
            ShockEvent(
                start_date=pd.Timestamp('2022-02-24'),
                end_date=pd.Timestamp('2023-12-31'),
                severity=0.7,
                type='geopolitical',
                confidence=1.0
            ),
            ShockEvent(
                start_date=pd.Timestamp('2022-06-01'),
                end_date=pd.Timestamp('2023-06-30'),
                severity=0.6,
                type='energy',
                confidence=0.9
            ),
            # Banking crisis 2023
            ShockEvent(
                start_date=pd.Timestamp('2023-03-01'),
                end_date=pd.Timestamp('2023-05-31'),
                severity=0.4,
                type='financial',
                confidence=0.8
            )
        ]

    def detect_breaks(self, residuals: np.ndarray, dates: pd.DatetimeIndex) -> List[pd.Timestamp]:
        """
        Detect structural breaks using PELT algorithm
        """
        if len(residuals) < 10:
            return []

        # Normalize residuals
        residuals_norm = (residuals - np.mean(residuals)) / (np.std(residuals) + 1e-8)

        # PELT changepoint detection
        algo = rpt.Pelt(model="rbf", min_size=3, jump=1)
        algo.fit(residuals_norm.reshape(-1, 1))

        # Penalty parameter (lower = more breaks)
        pen = np.log(len(residuals)) * np.std(residuals_norm)
        breakpoints = algo.predict(pen=pen)

        # Remove last breakpoint (end of series)
        if breakpoints and breakpoints[-1] == len(residuals):
            breakpoints = breakpoints[:-1]

        # Convert indices to dates
        break_dates = [dates[bp-1] for bp in breakpoints if bp < len(dates)]

        logger.info(f"Detected {len(break_dates)} structural breaks")
        return break_dates

    def cusum_test(self, residuals: np.ndarray, threshold: float = 0.95) -> bool:
        """
        CUSUM test for parameter stability
        Returns True if break detected
        """
        n = len(residuals)
        cumsum = np.cumsum(residuals) / np.std(residuals)

        # Normalize by sqrt(n)
        cumsum_normalized = cumsum / np.sqrt(n)

        # Critical value from Brownian bridge
        critical_value = stats.kstwobign.ppf(threshold)

        # Test statistic
        test_stat = np.max(np.abs(cumsum_normalized))

        return test_stat > critical_value

    def classify_shock(self, date: pd.Timestamp, features: pd.DataFrame) -> str:
        """
        Classify the type of shock based on feature patterns
        """
        # Check known shocks first
        for shock in self.known_shocks:
            if shock.start_date <= date <= (shock.end_date or date):
                return shock.type

        # Analyze feature patterns
        if 'vix' in features.columns:
            vix_spike = features['vix'].iloc[-1] > features['vix'].quantile(0.9)
            if vix_spike:
                return 'financial'

        if 'oil_price_change' in features.columns:
            oil_shock = abs(features['oil_price_change'].iloc[-1]) > 50
            if oil_shock:
                return 'energy'

        if 'global_uncertainty' in features.columns:
            uncertainty = features['global_uncertainty'].iloc[-1] > features['global_uncertainty'].quantile(0.9)
            if uncertainty:
                return 'geopolitical'

        return 'unknown'

    def get_shock_indicator(self, date: pd.Timestamp) -> Tuple[bool, Optional[ShockEvent]]:
        """
        Check if a date is within a shock period
        """
        for shock in self.known_shocks:
            if shock.start_date <= date <= (shock.end_date or date):
                return True, shock
        return False, None


class RobustGDPEstimator:
    """
    Robust estimation techniques for GDP forecasting
    """

    def __init__(self):
        self.break_detector = StructuralBreakDetector()
        self.huber_delta = 1.35  # Huber loss threshold

    def huber_loss(self, y_true: np.ndarray, y_pred: np.ndarray,
                   delta: float = None) -> np.ndarray:
        """
        Huber loss - robust to outliers
        Less sensitive to large errors than squared loss
        """
        if delta is None:
            delta = self.huber_delta

        error = y_true - y_pred
        is_small_error = np.abs(error) <= delta

        small_error_loss = 0.5 * error ** 2
        large_error_loss = delta * (np.abs(error) - 0.5 * delta)

        return np.where(is_small_error, small_error_loss, large_error_loss)

    def tukey_biweight(self, residuals: np.ndarray, c: float = 4.685) -> np.ndarray:
        """
        Tukey's biweight function for robust estimation
        Completely ignores outliers beyond threshold
        """
        # Median absolute deviation
        mad = np.median(np.abs(residuals - np.median(residuals)))
        scaled = residuals / (mad * c + 1e-8)

        # Weight function
        weights = np.where(
            np.abs(scaled) <= 1,
            (1 - scaled**2)**2,
            0
        )

        return weights

    def detect_and_adapt(self, y_true: np.ndarray, y_pred: np.ndarray,
                        dates: pd.DatetimeIndex, features: pd.DataFrame) -> Dict:
        """
        Detect shocks and adapt predictions
        """
        residuals = y_true - y_pred

        # Detect breaks
        break_dates = self.break_detector.detect_breaks(residuals, dates)

        # Check CUSUM
        has_instability = self.break_detector.cusum_test(residuals)

        # Identify shock periods
        shock_mask = np.zeros(len(dates), dtype=bool)
        shock_types = []

        for date in dates:
            is_shock, shock = self.break_detector.get_shock_indicator(date)
            idx = dates.get_loc(date)
            shock_mask[idx] = is_shock
            if is_shock:
                shock_types.append(shock.type)

        # Calculate regime-specific errors
        normal_mae = np.mean(np.abs(residuals[~shock_mask])) if np.any(~shock_mask) else np.nan
        shock_mae = np.mean(np.abs(residuals[shock_mask])) if np.any(shock_mask) else np.nan

        return {
            'break_dates': break_dates,
            'has_instability': has_instability,
            'shock_periods': shock_mask,
            'shock_types': list(set(shock_types)),
            'normal_mae': normal_mae,
            'shock_mae': shock_mae,
            'requires_robust': has_instability or len(break_dates) > 0
        }

    def robust_ensemble_weights(self, predictions: np.ndarray, y_true: np.ndarray,
                              regime: str = 'normal') -> np.ndarray:
        """
        Calculate robust ensemble weights using Huber regression
        More stable during shocks
        """
        n_models = predictions.shape[1]

        if regime in ['stress', 'crisis']:
            # Use robust regression for weight estimation
            huber = HuberRegressor(epsilon=self.huber_delta, alpha=0.001)
            huber.fit(predictions, y_true)

            # Extract and normalize weights
            weights = huber.coef_
            weights = np.maximum(weights, 0)  # Non-negative
            weights = weights / weights.sum() if weights.sum() > 0 else np.ones(n_models) / n_models

        else:
            # Standard OLS for normal periods
            from scipy.optimize import nnls
            weights, _ = nnls(predictions, y_true)
            weights = weights / weights.sum() if weights.sum() > 0 else np.ones(n_models) / n_models

        return weights

    def regime_specific_prediction_intervals(self, point_forecast: float,
                                            residuals: np.ndarray,
                                            regime: str,
                                            shock_type: str = None) -> Tuple[float, float]:
        """
        Generate prediction intervals adapted to regime
        Wider intervals during shocks
        """
        # Base quantiles
        alpha = 0.1  # 90% CI

        if regime in ['stress', 'crisis'] or shock_type:
            # Use robust quantiles
            q_lo = np.percentile(residuals, alpha * 100 / 2)
            q_hi = np.percentile(residuals, (1 - alpha/2) * 100)

            # Inflate intervals during known shock types
            inflation_factors = {
                'pandemic': 3.0,
                'financial': 2.0,
                'geopolitical': 1.5,
                'energy': 1.3,
                'unknown': 1.5
            }
            factor = inflation_factors.get(shock_type, 1.0)

            q_lo *= factor
            q_hi *= factor

        else:
            # Standard quantiles for normal regime
            q_lo = np.quantile(residuals, alpha/2)
            q_hi = np.quantile(residuals, 1 - alpha/2)

        ci_lower = point_forecast + q_lo
        ci_upper = point_forecast + q_hi

        return ci_lower, ci_upper

    def adaptive_forecast(self, models: Dict, features: pd.DataFrame,
                         date: pd.Timestamp, historical_errors: Dict) -> Dict:
        """
        Generate adaptive forecast that responds to detected shocks
        """
        # Check if in shock period
        is_shock, shock = self.break_detector.get_shock_indicator(date)

        # Get base predictions from all models
        predictions = {}
        for name, model in models.items():
            predictions[name] = model.predict(features.iloc[-1:].values)[0]

        if is_shock:
            logger.info(f"Shock detected: {shock.type} (severity: {shock.severity})")

            # Adjust predictions based on shock type
            adjustments = self._get_shock_adjustments(shock.type, shock.severity)

            # Apply adjustments
            for model_name in predictions:
                base_pred = predictions[model_name]

                # Dampen optimistic predictions during shocks
                if base_pred > 3 and shock.severity > 0.5:
                    predictions[model_name] = base_pred * (1 - shock.severity * 0.3)

                # Apply shock-specific adjustment
                predictions[model_name] += adjustments.get(model_name, 0)

            # Use robust weighting
            weights = self.robust_ensemble_weights(
                np.array(list(predictions.values())).reshape(1, -1),
                np.array([0]),  # Placeholder
                regime='stress'
            )
        else:
            # Normal regime - equal weights or learned weights
            weights = np.ones(len(predictions)) / len(predictions)

        # Calculate ensemble
        ensemble_pred = sum(w * p for w, p in zip(weights, predictions.values()))

        # Get prediction intervals
        residuals = historical_errors.get('residuals', np.array([-2, 2]))
        ci_lower, ci_upper = self.regime_specific_prediction_intervals(
            ensemble_pred, residuals,
            'stress' if is_shock else 'normal',
            shock.type if is_shock else None
        )

        return {
            'prediction': ensemble_pred,
            'ci_lower': ci_lower,
            'ci_upper': ci_upper,
            'is_shock': is_shock,
            'shock_type': shock.type if is_shock else None,
            'model_predictions': predictions,
            'weights': dict(zip(predictions.keys(), weights))
        }

    def _get_shock_adjustments(self, shock_type: str, severity: float) -> Dict[str, float]:
        """
        Get model-specific adjustments for different shock types
        Based on historical performance during similar shocks
        """
        adjustments = {
            'pandemic': {
                'gbm': -severity * 5.0,
                'rf': -severity * 4.5,
                'ridge': -severity * 3.0,
                'elastic': -severity * 3.5,
                'dfm': -severity * 4.0
            },
            'financial': {
                'gbm': -severity * 2.5,
                'rf': -severity * 2.0,
                'ridge': -severity * 1.5,
                'elastic': -severity * 1.8,
                'dfm': -severity * 2.2
            },
            'geopolitical': {
                'gbm': -severity * 1.5,
                'rf': -severity * 1.2,
                'ridge': -severity * 1.0,
                'elastic': -severity * 1.1,
                'dfm': -severity * 1.3
            },
            'energy': {
                'gbm': -severity * 1.2,
                'rf': -severity * 1.0,
                'ridge': -severity * 0.8,
                'elastic': -severity * 0.9,
                'dfm': -severity * 1.0
            }
        }

        return adjustments.get(shock_type, {})


# Testing
if __name__ == "__main__":
    print("Shock Detection and Robust Estimation")
    print("=" * 60)

    # Generate test data with shock
    np.random.seed(42)
    n_samples = 100
    dates = pd.date_range('2019-01-01', periods=n_samples, freq='Q')

    # Normal growth with shock
    y_true = np.random.normal(2.0, 0.5, n_samples)

    # Add COVID shock
    covid_start = 60  # 2020 Q1
    covid_end = 65
    y_true[covid_start:covid_end] = np.array([-5, -31, 33, 6, 7])  # Actual COVID pattern

    # Model predictions (poor during shock)
    y_pred = y_true + np.random.normal(0, 0.5, n_samples)
    y_pred[covid_start:covid_end] += np.array([8, 35, -28, -4, -5])  # Big errors

    # Features (simplified)
    features = pd.DataFrame({
        'vix': np.random.normal(15, 5, n_samples),
        'global_uncertainty': np.random.normal(100, 10, n_samples)
    }, index=dates)

    # Spike features during shock
    features.loc[dates[covid_start:covid_end], 'vix'] = [30, 45, 35, 25, 20]

    # Test robust estimator
    robust_est = RobustGDPEstimator()

    # Detect and adapt
    analysis = robust_est.detect_and_adapt(y_true, y_pred, dates, features)

    print(f"\nStructural breaks detected: {len(analysis['break_dates'])}")
    if analysis['break_dates']:
        for date in analysis['break_dates']:
            print(f"  - {date.strftime('%Y-%m-%d')}")

    print(f"\nParameter instability (CUSUM): {analysis['has_instability']}")
    print(f"Shock types identified: {analysis['shock_types']}")
    print(f"Normal period MAE: {analysis['normal_mae']:.2f}")
    print(f"Shock period MAE: {analysis['shock_mae']:.2f}")

    # Test adaptive forecast
    test_date = pd.Timestamp('2020-04-01')  # During COVID
    mock_models = {
        'gbm': type('Model', (), {'predict': lambda self, x: np.array([3.0])})(),
        'rf': type('Model', (), {'predict': lambda self, x: np.array([2.5])})(),
        'ridge': type('Model', (), {'predict': lambda self, x: np.array([2.0])})(),
    }

    historical_errors = {'residuals': y_true - y_pred}

    forecast = robust_est.adaptive_forecast(
        mock_models, features, test_date, historical_errors
    )

    print(f"\nAdaptive Forecast for {test_date.strftime('%Y-%m-%d')}:")
    print(f"Prediction: {forecast['prediction']:.2f}%")
    print(f"90% CI: [{forecast['ci_lower']:.2f}, {forecast['ci_upper']:.2f}]")
    print(f"Shock detected: {forecast['is_shock']}")
    if forecast['is_shock']:
        print(f"Shock type: {forecast['shock_type']}")
    print(f"Model weights: {forecast['weights']}")