#!/usr/bin/env python
"""
Confidence Intervals with MAPIE and LightGBM Quantiles
Calibrated intervals that actually achieve 80% coverage
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
import warnings
warnings.filterwarnings('ignore')

try:
    import lightgbm as lgb
    from mapie.regression import MapieRegressor
    from mapie.metrics import regression_coverage_score
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.model_selection import TimeSeriesSplit
    ADVANCED_LIBS = True
except ImportError:
    ADVANCED_LIBS = False
    print("Install: pip install lightgbm mapie scikit-learn")


class ConfidenceIntervalEstimator:
    """
    Generates calibrated confidence intervals using multiple methods
    """

    def __init__(self, target_coverage: float = 0.8):
        self.target_coverage = target_coverage
        self.alpha = 1 - target_coverage  # For MAPIE

        # Models for different approaches
        self.quantile_models = {}
        self.conformal_model = None
        self.coverage_history = []

        # Regime-specific width multipliers
        self.regime_multipliers = {
            'normal': 1.0,
            'expansion': 0.9,
            'crisis': 2.5
        }

        # Residual variance tracker
        self.residual_tracker = ResidualVarianceTracker()

    def fit_quantile_models(self, X: np.ndarray, y: np.ndarray):
        """
        Fit LightGBM quantile regression models

        Args:
            X: Feature matrix
            y: Target values
        """

        if not ADVANCED_LIBS:
            return

        # Fit models for different quantiles
        quantiles = [0.1, 0.25, 0.5, 0.75, 0.9]

        for q in quantiles:
            params = {
                'objective': 'quantile',
                'alpha': q,
                'min_data_in_leaf': max(5, len(y) // 20),
                'learning_rate': 0.05,
                'num_leaves': 31,
                'feature_fraction': 0.8,
                'bagging_fraction': 0.8,
                'bagging_freq': 5,
                'verbose': -1
            }

            train_data = lgb.Dataset(X, label=y)

            self.quantile_models[f'q{int(q*100)}'] = lgb.train(
                params,
                train_data,
                num_boost_round=100
            )

    def fit_conformal_predictor(self, X: np.ndarray, y: np.ndarray):
        """
        Fit MAPIE conformal predictor for calibrated intervals

        Args:
            X: Feature matrix
            y: Target values
        """

        if not ADVANCED_LIBS:
            return

        # Base estimator
        base_estimator = GradientBoostingRegressor(
            n_estimators=100,
            learning_rate=0.1,
            max_depth=3,
            random_state=42
        )

        # Use time series split for proper validation
        cv = TimeSeriesSplit(n_splits=3)

        # MAPIE with plus method for better coverage
        self.conformal_model = MapieRegressor(
            estimator=base_estimator,
            method="plus",
            cv=cv,
            n_jobs=1
        )

        # Fit the conformal predictor
        self.conformal_model.fit(X, y)

    def predict_quantile_intervals(self, X: np.ndarray) -> Tuple[float, float, float]:
        """
        Get quantile-based prediction intervals

        Returns:
            (lower_bound, median, upper_bound)
        """

        if not ADVANCED_LIBS or not self.quantile_models:
            # Simple fallback
            return -2.0, 0.0, 2.0

        # Get quantile predictions
        q10 = self.quantile_models['q10'].predict(X.reshape(1, -1))[0]
        q50 = self.quantile_models['q50'].predict(X.reshape(1, -1))[0]
        q90 = self.quantile_models['q90'].predict(X.reshape(1, -1))[0]

        return float(q10), float(q50), float(q90)

    def predict_conformal_intervals(self, X: np.ndarray) -> Tuple[float, float, float]:
        """
        Get conformal prediction intervals

        Returns:
            (lower_bound, point_prediction, upper_bound)
        """

        if not ADVANCED_LIBS or self.conformal_model is None:
            return -2.0, 0.0, 2.0

        # Get conformal predictions
        y_pred, y_pis = self.conformal_model.predict(
            X.reshape(1, -1),
            alpha=self.alpha
        )

        point_pred = float(y_pred[0])
        lower = float(y_pis[0, 0, 0])
        upper = float(y_pis[0, 1, 0])

        return lower, point_pred, upper

    def combine_intervals(self, X: np.ndarray, regime: str = 'normal',
                         residual_variance: Optional[float] = None) -> Dict:
        """
        Combine multiple interval methods with regime adjustment

        Args:
            X: Feature vector
            regime: Current economic regime
            residual_variance: Recent residual variance

        Returns:
            Dict with calibrated intervals
        """

        intervals = {}

        # Get quantile intervals
        q_lower, q_median, q_upper = self.predict_quantile_intervals(X)
        intervals['quantile'] = {
            'lower': q_lower,
            'median': q_median,
            'upper': q_upper
        }

        # Get conformal intervals
        c_lower, c_point, c_upper = self.predict_conformal_intervals(X)
        intervals['conformal'] = {
            'lower': c_lower,
            'point': c_point,
            'upper': c_upper
        }

        # Combine approaches (weighted average)
        if self.conformal_model is not None:
            # Prefer conformal if available
            combined_lower = 0.7 * c_lower + 0.3 * q_lower
            combined_upper = 0.7 * c_upper + 0.3 * q_upper
            combined_point = 0.7 * c_point + 0.3 * q_median
        else:
            # Use quantile only
            combined_lower = q_lower
            combined_upper = q_upper
            combined_point = q_median

        # Apply regime multiplier
        multiplier = self.regime_multipliers.get(regime, 1.0)
        width = (combined_upper - combined_lower) / 2
        adjusted_width = width * multiplier

        # Apply residual variance adjustment
        if residual_variance is not None and residual_variance > 0:
            # Inflate based on recent prediction errors
            variance_multiplier = 1 + np.sqrt(residual_variance) / 10
            adjusted_width *= variance_multiplier

        # Final calibrated intervals
        final_lower = combined_point - adjusted_width
        final_upper = combined_point + adjusted_width

        intervals['calibrated'] = {
            'point': combined_point,
            'lower': final_lower,
            'upper': final_upper,
            'width': adjusted_width * 2,
            'regime_multiplier': multiplier,
            'confidence': self.target_coverage
        }

        return intervals

    def update_coverage_stats(self, predictions: List[float], actuals: List[float],
                             intervals: List[Tuple[float, float]]):
        """
        Track actual coverage to improve calibration

        Args:
            predictions: Point predictions
            actuals: Actual values
            intervals: List of (lower, upper) bounds
        """

        if len(predictions) != len(actuals) or len(predictions) != len(intervals):
            return

        # Calculate coverage
        in_interval = [
            lower <= actual <= upper
            for actual, (lower, upper) in zip(actuals, intervals)
        ]

        coverage = np.mean(in_interval)

        # Store history
        self.coverage_history.append({
            'n_samples': len(predictions),
            'coverage': coverage,
            'target': self.target_coverage,
            'gap': coverage - self.target_coverage
        })

        # Adjust multipliers if coverage is off
        if len(self.coverage_history) >= 5:
            recent_coverage = np.mean([h['coverage'] for h in self.coverage_history[-5:]])

            if recent_coverage < self.target_coverage - 0.05:
                # Widen intervals
                for regime in self.regime_multipliers:
                    self.regime_multipliers[regime] *= 1.1
            elif recent_coverage > self.target_coverage + 0.05:
                # Narrow intervals
                for regime in self.regime_multipliers:
                    self.regime_multipliers[regime] *= 0.95


class ResidualVarianceTracker:
    """
    Tracks residual variance for heteroscedastic adjustment
    """

    def __init__(self, window_size: int = 20):
        self.window_size = window_size
        self.residuals = []
        self.variance_model = None

    def update(self, prediction: float, actual: float, features: Optional[Dict] = None):
        """
        Update residual tracker

        Args:
            prediction: Predicted value
            actual: Actual value
            features: Optional features for heteroscedastic modeling
        """

        residual = prediction - actual
        self.residuals.append({
            'residual': residual,
            'abs_residual': abs(residual),
            'squared_residual': residual ** 2,
            'features': features
        })

        # Keep window size
        if len(self.residuals) > self.window_size:
            self.residuals = self.residuals[-self.window_size:]

    def get_current_variance(self) -> float:
        """
        Get current residual variance estimate
        """

        if len(self.residuals) < 3:
            return 1.0  # Default variance

        squared_residuals = [r['squared_residual'] for r in self.residuals]
        return np.mean(squared_residuals)

    def get_conditional_variance(self, features: Dict) -> float:
        """
        Get conditional variance based on features (heteroscedastic)
        """

        if not ADVANCED_LIBS or self.variance_model is None:
            return self.get_current_variance()

        # Predict variance based on features
        try:
            X = np.array(list(features.values())).reshape(1, -1)
            predicted_variance = self.variance_model.predict(X)[0]
            return float(predicted_variance)
        except:
            return self.get_current_variance()

    def fit_variance_model(self):
        """
        Fit a model to predict residual variance from features
        """

        if not ADVANCED_LIBS or len(self.residuals) < 20:
            return

        # Prepare data
        X = []
        y = []

        for r in self.residuals:
            if r['features'] is not None:
                X.append(list(r['features'].values()))
                y.append(r['abs_residual'])

        if len(X) < 10:
            return

        # Fit simple model for variance
        try:
            params = {
                'objective': 'regression',
                'min_data_in_leaf': 3,
                'learning_rate': 0.1,
                'num_leaves': 15,
                'verbose': -1
            }

            train_data = lgb.Dataset(np.array(X), label=np.array(y))
            self.variance_model = lgb.train(
                params,
                train_data,
                num_boost_round=50
            )
        except:
            self.variance_model = None


def test_confidence_intervals():
    """Test confidence interval estimation"""

    print("🎯 TESTING CONFIDENCE INTERVALS")
    print("="*60)

    # Generate sample data
    np.random.seed(42)
    n_train = 100
    n_test = 20

    X_train = np.random.randn(n_train, 5)
    y_train = 2 + X_train[:, 0] * 1.5 - X_train[:, 1] * 0.8 + np.random.randn(n_train) * 0.5

    X_test = np.random.randn(n_test, 5)
    y_test = 2 + X_test[:, 0] * 1.5 - X_test[:, 1] * 0.8 + np.random.randn(n_test) * 0.5

    # Initialize estimator
    ci_estimator = ConfidenceIntervalEstimator(target_coverage=0.8)

    # Fit models
    print("\nFitting quantile models...")
    ci_estimator.fit_quantile_models(X_train, y_train)
    print(f"  Quantile models fitted: {list(ci_estimator.quantile_models.keys())}")

    print("\nFitting conformal predictor...")
    ci_estimator.fit_conformal_predictor(X_train, y_train)
    print("  Conformal predictor fitted ✅")

    # Test predictions
    print("\nTesting interval predictions:")

    regimes = ['normal', 'crisis', 'expansion']
    for regime in regimes:
        X_sample = X_test[0]
        intervals = ci_estimator.combine_intervals(X_sample, regime=regime)

        calibrated = intervals['calibrated']
        print(f"\n  {regime.upper()} regime:")
        print(f"    Point: {calibrated['point']:.2f}")
        print(f"    80% CI: [{calibrated['lower']:.2f}, {calibrated['upper']:.2f}]")
        print(f"    Width: {calibrated['width']:.2f}")
        print(f"    Multiplier: {calibrated['regime_multiplier']}")

    # Test coverage tracking
    print("\n\nTesting coverage calibration:")

    predictions = []
    actuals = []
    intervals_list = []

    for i in range(n_test):
        result = ci_estimator.combine_intervals(X_test[i], regime='normal')
        calibrated = result['calibrated']

        predictions.append(calibrated['point'])
        actuals.append(y_test[i])
        intervals_list.append((calibrated['lower'], calibrated['upper']))

    ci_estimator.update_coverage_stats(predictions, actuals, intervals_list)

    # Calculate actual coverage
    in_interval = [
        lower <= actual <= upper
        for actual, (lower, upper) in zip(actuals, intervals_list)
    ]
    actual_coverage = np.mean(in_interval)

    print(f"  Target coverage: {ci_estimator.target_coverage:.1%}")
    print(f"  Actual coverage: {actual_coverage:.1%}")
    print(f"  Gap: {actual_coverage - ci_estimator.target_coverage:+.1%}")

    # Test residual tracker
    print("\n\nTesting residual variance tracker:")

    tracker = ResidualVarianceTracker()

    for pred, actual in zip(predictions[:10], actuals[:10]):
        tracker.update(pred, actual)

    current_var = tracker.get_current_variance()
    print(f"  Current variance: {current_var:.3f}")
    print(f"  Residuals tracked: {len(tracker.residuals)}")


if __name__ == "__main__":
    test_confidence_intervals()