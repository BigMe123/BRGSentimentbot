#!/usr/bin/env python
"""
Rolling Cross-Validation Evaluator
Honest evaluation without cherry-picking
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
import warnings
warnings.filterwarnings('ignore')

try:
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


@dataclass
class EvaluationMetrics:
    """Comprehensive evaluation metrics"""
    mae: float
    mape: float
    rmse: float
    direction_accuracy: float
    crisis_precision: float
    crisis_recall: float
    ci_coverage: float
    extreme_event_accuracy: float
    bias: float
    max_error: float

    def to_dict(self) -> Dict:
        return {
            'mae': round(self.mae, 2),
            'mape': round(self.mape, 1),
            'rmse': round(self.rmse, 2),
            'direction_accuracy': round(self.direction_accuracy, 3),
            'crisis_precision': round(self.crisis_precision, 3),
            'crisis_recall': round(self.crisis_recall, 3),
            'ci_coverage': round(self.ci_coverage, 3),
            'extreme_event_accuracy': round(self.extreme_event_accuracy, 3),
            'bias': round(self.bias, 2),
            'max_error': round(self.max_error, 2)
        }

    def get_summary(self) -> str:
        """Get concise summary of key metrics"""
        return (
            f"MAE: {self.mae:.2f}pp | "
            f"Direction: {self.direction_accuracy:.1%} | "
            f"Crisis Precision: {self.crisis_precision:.1%} | "
            f"CI Coverage: {self.ci_coverage:.1%}"
        )


class RollingCVEvaluator:
    """
    Rolling window cross-validation for time series
    No data leakage, proper temporal ordering
    """

    def __init__(self, min_train_size: int = 24, test_size: int = 3):
        """
        Args:
            min_train_size: Minimum training window (months)
            test_size: Test window size (months)
        """
        self.min_train_size = min_train_size
        self.test_size = test_size
        self.evaluation_history = []

    def evaluate_model(self, model: Any, X: pd.DataFrame, y: pd.Series,
                       crisis_detector: Optional[Any] = None) -> Dict:
        """
        Full rolling CV evaluation

        Args:
            model: Model with fit() and predict() methods
            X: Feature matrix
            y: Target values
            crisis_detector: Optional crisis detection model

        Returns:
            Dict with comprehensive evaluation results
        """

        results = {
            'overall': None,
            'by_period': [],
            'by_regime': {},
            'extreme_events': []
        }

        all_predictions = []
        all_actuals = []
        all_regimes = []
        all_intervals = []

        # Rolling window evaluation
        n_samples = len(X)
        n_splits = (n_samples - self.min_train_size) // self.test_size

        for i in range(n_splits):
            # Define train/test split
            train_end = self.min_train_size + i * self.test_size
            test_start = train_end
            test_end = min(test_start + self.test_size, n_samples)

            if test_end <= test_start:
                continue

            # Split data
            X_train = X.iloc[:train_end]
            y_train = y.iloc[:train_end]
            X_test = X.iloc[test_start:test_end]
            y_test = y.iloc[test_start:test_end]

            # Train model
            model.fit(X_train, y_train)

            # Make predictions
            predictions = model.predict(X_test)

            # Get confidence intervals if available
            if hasattr(model, 'predict_interval'):
                intervals = model.predict_interval(X_test, alpha=0.2)
            else:
                # Simple intervals based on historical std
                std = y_train.std()
                intervals = [(p - 1.28*std, p + 1.28*std) for p in predictions]

            # Detect regimes if detector provided
            if crisis_detector:
                regimes = []
                for j in range(len(X_test)):
                    features = X_test.iloc[j].to_dict()
                    regime, _, _ = crisis_detector.detect_regime({}, features)
                    regimes.append(regime)
            else:
                regimes = ['normal'] * len(X_test)

            # Store results
            all_predictions.extend(predictions)
            all_actuals.extend(y_test.values)
            all_regimes.extend(regimes)
            all_intervals.extend(intervals)

            # Period metrics
            period_metrics = self._calculate_metrics(
                predictions, y_test.values, intervals, regimes
            )
            period_metrics['period'] = f"Split_{i+1}"
            period_metrics['train_size'] = train_end
            period_metrics['test_period'] = f"{X_test.index[0]} to {X_test.index[-1]}"
            results['by_period'].append(period_metrics)

        # Calculate overall metrics
        results['overall'] = self._calculate_comprehensive_metrics(
            all_predictions, all_actuals, all_intervals, all_regimes
        )

        # Regime-specific evaluation
        for regime in ['normal', 'crisis', 'expansion']:
            regime_mask = [r == regime for r in all_regimes]
            if sum(regime_mask) > 0:
                regime_preds = [p for p, m in zip(all_predictions, regime_mask) if m]
                regime_acts = [a for a, m in zip(all_actuals, regime_mask) if m]
                regime_ints = [i for i, m in zip(all_intervals, regime_mask) if m]

                results['by_regime'][regime] = self._calculate_metrics(
                    regime_preds, regime_acts, regime_ints, [regime]*len(regime_preds)
                )

        # Extreme event evaluation
        results['extreme_events'] = self._evaluate_extreme_events(
            all_predictions, all_actuals, all_regimes
        )

        return results

    def _calculate_metrics(self, predictions: List[float], actuals: List[float],
                          intervals: List[Tuple[float, float]],
                          regimes: List[str]) -> Dict:
        """
        Calculate basic metrics for a set of predictions
        """

        predictions = np.array(predictions)
        actuals = np.array(actuals)

        # Basic metrics
        mae = mean_absolute_error(actuals, predictions) if SKLEARN_AVAILABLE else \
              np.mean(np.abs(predictions - actuals))

        # MAPE (avoiding division by zero)
        mape_values = np.abs((predictions - actuals) / (actuals + 1e-10)) * 100
        mape = np.mean(mape_values)

        # Direction accuracy
        if len(predictions) > 1:
            pred_direction = np.sign(predictions[1:] - predictions[:-1])
            actual_direction = np.sign(actuals[1:] - actuals[:-1])
            direction_accuracy = np.mean(pred_direction == actual_direction)
        else:
            direction_accuracy = 0.5

        # CI coverage
        if intervals:
            in_interval = [
                lower <= actual <= upper
                for actual, (lower, upper) in zip(actuals, intervals)
            ]
            ci_coverage = np.mean(in_interval)
        else:
            ci_coverage = 0.0

        # Crisis detection metrics
        crisis_mask = [r == 'crisis' for r in regimes]
        if sum(crisis_mask) > 0:
            # Simplified crisis detection based on predictions
            predicted_crisis = predictions < -2.0  # Simple threshold
            actual_crisis = actuals < -2.0

            tp = np.sum(predicted_crisis & actual_crisis)
            fp = np.sum(predicted_crisis & ~actual_crisis)
            fn = np.sum(~predicted_crisis & actual_crisis)

            precision = tp / (tp + fp) if (tp + fp) > 0 else 0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        else:
            precision = recall = 0.0

        return {
            'mae': mae,
            'mape': mape,
            'direction_accuracy': direction_accuracy,
            'ci_coverage': ci_coverage,
            'crisis_precision': precision,
            'crisis_recall': recall,
            'n_samples': len(predictions)
        }

    def _calculate_comprehensive_metrics(self, predictions: List[float],
                                        actuals: List[float],
                                        intervals: List[Tuple[float, float]],
                                        regimes: List[str]) -> EvaluationMetrics:
        """
        Calculate comprehensive metrics including bias and extreme events
        """

        base_metrics = self._calculate_metrics(predictions, actuals, intervals, regimes)

        predictions = np.array(predictions)
        actuals = np.array(actuals)

        # Additional metrics
        rmse = np.sqrt(np.mean((predictions - actuals) ** 2))
        bias = np.mean(predictions - actuals)
        max_error = np.max(np.abs(predictions - actuals))

        # Extreme event accuracy (events beyond 2 std)
        std = actuals.std()
        extreme_mask = np.abs(actuals) > 2 * std
        if extreme_mask.sum() > 0:
            extreme_preds = predictions[extreme_mask]
            extreme_acts = actuals[extreme_mask]
            # Check if we got the direction and rough magnitude
            extreme_accuracy = np.mean(
                (np.sign(extreme_preds) == np.sign(extreme_acts)) &
                (np.abs(extreme_preds) > std)
            )
        else:
            extreme_accuracy = 0.0

        return EvaluationMetrics(
            mae=base_metrics['mae'],
            mape=base_metrics['mape'],
            rmse=rmse,
            direction_accuracy=base_metrics['direction_accuracy'],
            crisis_precision=base_metrics['crisis_precision'],
            crisis_recall=base_metrics['crisis_recall'],
            ci_coverage=base_metrics['ci_coverage'],
            extreme_event_accuracy=extreme_accuracy,
            bias=bias,
            max_error=max_error
        )

    def _evaluate_extreme_events(self, predictions: List[float],
                                actuals: List[float],
                                regimes: List[str]) -> List[Dict]:
        """
        Detailed evaluation of extreme events
        """

        extreme_events = []
        predictions = np.array(predictions)
        actuals = np.array(actuals)

        # Find extreme events (beyond 2 std or absolute value > 5)
        std = actuals.std()
        mean = actuals.mean()

        for i, actual in enumerate(actuals):
            is_extreme = (abs(actual - mean) > 2 * std) or (abs(actual) > 5)

            if is_extreme:
                event = {
                    'index': i,
                    'actual': round(actual, 2),
                    'predicted': round(predictions[i], 2),
                    'error': round(predictions[i] - actual, 2),
                    'regime': regimes[i] if i < len(regimes) else 'unknown',
                    'captured': abs(predictions[i]) > std,  # Did we predict something unusual?
                    'direction_correct': np.sign(predictions[i]) == np.sign(actual)
                }
                extreme_events.append(event)

        return extreme_events

    def generate_report(self, results: Dict) -> str:
        """
        Generate human-readable evaluation report
        """

        report = []
        report.append("="*60)
        report.append("MODEL EVALUATION REPORT")
        report.append("="*60)

        # Overall metrics
        if results['overall']:
            report.append("\nOVERALL PERFORMANCE:")
            report.append("-"*40)
            metrics = results['overall']
            report.append(metrics.get_summary())
            report.append(f"\nDetailed Metrics:")
            for key, value in metrics.to_dict().items():
                report.append(f"  {key:25s}: {value}")

        # By regime
        if results['by_regime']:
            report.append("\nPERFORMANCE BY REGIME:")
            report.append("-"*40)
            for regime, metrics in results['by_regime'].items():
                report.append(f"\n{regime.upper()}:")
                report.append(f"  MAE: {metrics['mae']:.2f}pp")
                report.append(f"  Direction Accuracy: {metrics['direction_accuracy']:.1%}")
                report.append(f"  Samples: {metrics['n_samples']}")

        # Extreme events
        if results['extreme_events']:
            report.append("\nEXTREME EVENT DETECTION:")
            report.append("-"*40)
            captured = sum(1 for e in results['extreme_events'] if e['captured'])
            total = len(results['extreme_events'])
            report.append(f"Captured {captured}/{total} extreme events")

            # Show worst misses
            sorted_events = sorted(results['extreme_events'],
                                  key=lambda x: abs(x['error']), reverse=True)
            report.append("\nTop 3 Worst Predictions:")
            for event in sorted_events[:3]:
                report.append(f"  Actual: {event['actual']:+.1f}, "
                            f"Predicted: {event['predicted']:+.1f}, "
                            f"Error: {event['error']:+.1f}")

        # Rolling window performance
        if results['by_period']:
            report.append("\nROLLING WINDOW PERFORMANCE:")
            report.append("-"*40)
            maes = [p['mae'] for p in results['by_period']]
            report.append(f"MAE range: {min(maes):.2f} - {max(maes):.2f}pp")
            report.append(f"Consistency: {np.std(maes):.2f}pp std dev")

            # Check for degradation over time
            if len(maes) > 3:
                early_mae = np.mean(maes[:3])
                late_mae = np.mean(maes[-3:])
                if late_mae > early_mae * 1.2:
                    report.append("⚠️  Performance degradation detected over time")

        return "\n".join(report)


def test_evaluator():
    """Test the evaluation framework"""

    print("🧪 TESTING EVALUATION FRAMEWORK")
    print("="*60)

    # Create synthetic data
    np.random.seed(42)
    n_samples = 60  # 5 years monthly

    dates = pd.date_range(start='2019-01-01', periods=n_samples, freq='M')

    # Features
    X = pd.DataFrame({
        'pmi': 50 + np.random.normal(0, 5, n_samples),
        'sentiment': np.random.normal(0, 0.3, n_samples),
        'vix': 20 + np.random.exponential(5, n_samples)
    }, index=dates)

    # Target with some patterns
    y = pd.Series(
        2 + 0.5 * np.sin(np.arange(n_samples) / 6) +
        np.random.normal(0, 1, n_samples),
        index=dates
    )

    # Add extreme events
    y.iloc[15] = -8.0  # Crisis
    y.iloc[16] = -6.0
    y.iloc[17] = 12.0  # Recovery
    y.iloc[40] = -5.0  # Another dip

    # Simple model for testing
    class SimpleModel:
        def fit(self, X, y):
            self.mean = y.mean()
            self.std = y.std()

        def predict(self, X):
            # Simple predictions with some correlation
            n = len(X)
            base = np.full(n, self.mean)
            # Add some signal from PMI
            signal = (X['pmi'].values - 50) * 0.2
            noise = np.random.normal(0, self.std * 0.5, n)
            return base + signal + noise

        def predict_interval(self, X, alpha=0.2):
            preds = self.predict(X)
            width = 1.28 * self.std  # 80% CI
            return [(p - width, p + width) for p in preds]

    # Initialize evaluator
    evaluator = RollingCVEvaluator(min_train_size=24, test_size=3)

    # Create and evaluate model
    model = SimpleModel()
    results = evaluator.evaluate_model(model, X, y)

    # Generate report
    report = evaluator.generate_report(results)
    print(report)

    # Additional detailed checks
    print("\n" + "="*60)
    print("DETAILED CHECKS:")
    print("-"*40)

    # Check if we're honest about performance
    overall = results['overall']
    if overall:
        if overall.mae > 3.0:
            print("⚠️  High MAE detected - model needs improvement")
        if overall.direction_accuracy < 0.6:
            print("⚠️  Poor direction accuracy - below 60%")
        if overall.ci_coverage < 0.75:
            print("⚠️  CI coverage below target 80%")
        if abs(overall.bias) > 1.0:
            print("⚠️  Significant bias detected")

    # Check extreme events
    extreme_events = results['extreme_events']
    if extreme_events:
        missed = [e for e in extreme_events if not e['captured']]
        if missed:
            print(f"\n❌ Missed {len(missed)} extreme events:")
            for event in missed[:3]:
                print(f"   Actual: {event['actual']}, Predicted: {event['predicted']}")


if __name__ == "__main__":
    test_evaluator()