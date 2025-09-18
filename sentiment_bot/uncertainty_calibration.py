#!/usr/bin/env python
"""
Uncertainty Calibration and Error Tracking
==========================================
Rolling MAE/SMAPE reporting and confidence interval calibration
"""

import os
import json
import numpy as np
import pandas as pd
import sqlite3
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


@dataclass
class PredictionRecord:
    """Historical prediction record for calibration"""
    timestamp: datetime
    indicator: str
    prediction: float
    actual: Optional[float] = None
    confidence_interval_lower: float = None
    confidence_interval_upper: float = None
    confidence_level: float = 0.8  # 80% CI by default
    model_confidence: float = None
    model_type: str = None
    regime: str = None
    horizon_days: int = 30
    metadata: Dict = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for storage"""
        result = asdict(self)
        result['timestamp'] = self.timestamp.isoformat()
        return result

    @classmethod
    def from_dict(cls, data: Dict) -> 'PredictionRecord':
        """Create from dictionary"""
        data = data.copy()
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


class UncertaintyDatabase:
    """Database for storing prediction history and tracking accuracy"""

    def __init__(self, db_path: str = "state/uncertainty_calibration.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _init_database(self):
        """Initialize database tables"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    indicator TEXT NOT NULL,
                    prediction REAL NOT NULL,
                    actual REAL,
                    ci_lower REAL,
                    ci_upper REAL,
                    confidence_level REAL,
                    model_confidence REAL,
                    model_type TEXT,
                    regime TEXT,
                    horizon_days INTEGER,
                    metadata TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_predictions_timestamp
                ON predictions(timestamp)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_predictions_indicator
                ON predictions(indicator)
            """)

    def store_prediction(self, record: PredictionRecord):
        """Store prediction record"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO predictions (
                    timestamp, indicator, prediction, actual, ci_lower, ci_upper,
                    confidence_level, model_confidence, model_type, regime,
                    horizon_days, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.timestamp.isoformat(),
                record.indicator,
                record.prediction,
                record.actual,
                record.confidence_interval_lower,
                record.confidence_interval_upper,
                record.confidence_level,
                record.model_confidence,
                record.model_type,
                record.regime,
                record.horizon_days,
                json.dumps(record.metadata) if record.metadata else None
            ))

    def update_actual(self, timestamp: datetime, indicator: str, actual: float):
        """Update actual value for a prediction"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE predictions
                SET actual = ?
                WHERE timestamp = ? AND indicator = ?
            """, (actual, timestamp.isoformat(), indicator))

    def get_predictions(self,
                       indicator: str = None,
                       start_date: datetime = None,
                       end_date: datetime = None,
                       model_type: str = None,
                       regime: str = None) -> List[PredictionRecord]:
        """Get prediction records with filters"""

        query = "SELECT * FROM predictions WHERE 1=1"
        params = []

        if indicator:
            query += " AND indicator = ?"
            params.append(indicator)

        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date.isoformat())

        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date.isoformat())

        if model_type:
            query += " AND model_type = ?"
            params.append(model_type)

        if regime:
            query += " AND regime = ?"
            params.append(regime)

        query += " ORDER BY timestamp DESC"

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)
            records = []

            for row in cursor:
                record_dict = dict(row)
                # Convert back from database
                record_dict['timestamp'] = datetime.fromisoformat(record_dict['timestamp'])
                if record_dict['metadata']:
                    record_dict['metadata'] = json.loads(record_dict['metadata'])

                # Remove database-specific fields
                record_dict.pop('id', None)
                record_dict.pop('created_at', None)

                records.append(PredictionRecord(**record_dict))

        return records


class AccuracyMetrics:
    """Calculate various accuracy metrics"""

    @staticmethod
    def mae(predictions: np.ndarray, actuals: np.ndarray) -> float:
        """Mean Absolute Error"""
        return np.mean(np.abs(predictions - actuals))

    @staticmethod
    def rmse(predictions: np.ndarray, actuals: np.ndarray) -> float:
        """Root Mean Square Error"""
        return np.sqrt(np.mean((predictions - actuals) ** 2))

    @staticmethod
    def smape(predictions: np.ndarray, actuals: np.ndarray) -> float:
        """Symmetric Mean Absolute Percentage Error"""
        denominator = (np.abs(predictions) + np.abs(actuals)) / 2
        # Avoid division by zero
        mask = denominator != 0
        if not np.any(mask):
            return 0.0

        return np.mean(np.abs(predictions[mask] - actuals[mask]) / denominator[mask]) * 100

    @staticmethod
    def mape(predictions: np.ndarray, actuals: np.ndarray) -> float:
        """Mean Absolute Percentage Error"""
        mask = actuals != 0
        if not np.any(mask):
            return 0.0

        return np.mean(np.abs((predictions[mask] - actuals[mask]) / actuals[mask])) * 100

    @staticmethod
    def directional_accuracy(predictions: np.ndarray, actuals: np.ndarray, threshold: float = 0) -> float:
        """Fraction of predictions with correct direction"""
        pred_direction = predictions > threshold
        actual_direction = actuals > threshold
        return np.mean(pred_direction == actual_direction)

    @staticmethod
    def confidence_interval_coverage(predictions: np.ndarray,
                                   actuals: np.ndarray,
                                   ci_lower: np.ndarray,
                                   ci_upper: np.ndarray) -> float:
        """Calculate confidence interval coverage rate"""
        coverage = (actuals >= ci_lower) & (actuals <= ci_upper)
        return np.mean(coverage)

    @staticmethod
    def confidence_interval_width(ci_lower: np.ndarray, ci_upper: np.ndarray) -> float:
        """Average confidence interval width"""
        return np.mean(ci_upper - ci_lower)


class RollingMetricsTracker:
    """Track rolling accuracy metrics"""

    def __init__(self, db: UncertaintyDatabase, window_days: int = 180):
        self.db = db
        self.window_days = window_days
        self.metrics = AccuracyMetrics()

    def calculate_rolling_metrics(self,
                                indicator: str,
                                as_of_date: datetime = None) -> Dict:
        """Calculate rolling metrics for an indicator"""

        if as_of_date is None:
            as_of_date = datetime.now()

        start_date = as_of_date - timedelta(days=self.window_days)

        # Get predictions with actuals
        records = self.db.get_predictions(
            indicator=indicator,
            start_date=start_date,
            end_date=as_of_date
        )

        # Filter records with both prediction and actual
        complete_records = [r for r in records if r.actual is not None]

        if len(complete_records) < 5:  # Need minimum observations
            return {
                'indicator': indicator,
                'window_days': self.window_days,
                'observation_count': len(complete_records),
                'sufficient_data': False,
                'message': 'Insufficient data for reliable metrics'
            }

        # Extract arrays
        predictions = np.array([r.prediction for r in complete_records])
        actuals = np.array([r.actual for r in complete_records])

        # Basic metrics
        metrics_result = {
            'indicator': indicator,
            'window_days': self.window_days,
            'observation_count': len(complete_records),
            'sufficient_data': True,
            'as_of_date': as_of_date.isoformat(),
            'metrics': {
                'mae': self.metrics.mae(predictions, actuals),
                'rmse': self.metrics.rmse(predictions, actuals),
                'smape': self.metrics.smape(predictions, actuals),
                'mape': self.metrics.mape(predictions, actuals),
                'directional_accuracy': self.metrics.directional_accuracy(predictions, actuals)
            }
        }

        # Confidence interval metrics (if available)
        ci_records = [r for r in complete_records
                     if r.confidence_interval_lower is not None and r.confidence_interval_upper is not None]

        if ci_records:
            ci_lower = np.array([r.confidence_interval_lower for r in ci_records])
            ci_upper = np.array([r.confidence_interval_upper for r in ci_records])
            ci_actuals = np.array([r.actual for r in ci_records])

            metrics_result['confidence_intervals'] = {
                'coverage_rate': self.metrics.confidence_interval_coverage(
                    np.array([r.prediction for r in ci_records]), ci_actuals, ci_lower, ci_upper
                ),
                'average_width': self.metrics.confidence_interval_width(ci_lower, ci_upper),
                'target_coverage': ci_records[0].confidence_level,  # Assume consistent
                'sample_size': len(ci_records)
            }

        # Regime-specific metrics
        regime_metrics = {}
        for regime in ['normal', 'crisis']:
            regime_records = [r for r in complete_records if r.regime == regime]
            if len(regime_records) >= 3:
                regime_preds = np.array([r.prediction for r in regime_records])
                regime_actuals = np.array([r.actual for r in regime_records])

                regime_metrics[regime] = {
                    'count': len(regime_records),
                    'mae': self.metrics.mae(regime_preds, regime_actuals),
                    'smape': self.metrics.smape(regime_preds, regime_actuals),
                    'directional_accuracy': self.metrics.directional_accuracy(regime_preds, regime_actuals)
                }

        if regime_metrics:
            metrics_result['regime_breakdown'] = regime_metrics

        return metrics_result

    def get_model_performance_comparison(self, indicator: str) -> Dict:
        """Compare performance across model types"""

        end_date = datetime.now()
        start_date = end_date - timedelta(days=self.window_days)

        records = self.db.get_predictions(
            indicator=indicator,
            start_date=start_date,
            end_date=end_date
        )

        complete_records = [r for r in records if r.actual is not None and r.model_type is not None]

        if len(complete_records) < 5:
            return {'insufficient_data': True}

        # Group by model type
        model_performance = {}
        for model_type in set(r.model_type for r in complete_records):
            model_records = [r for r in complete_records if r.model_type == model_type]

            if len(model_records) >= 3:
                predictions = np.array([r.prediction for r in model_records])
                actuals = np.array([r.actual for r in model_records])

                model_performance[model_type] = {
                    'count': len(model_records),
                    'mae': self.metrics.mae(predictions, actuals),
                    'smape': self.metrics.smape(predictions, actuals),
                    'directional_accuracy': self.metrics.directional_accuracy(predictions, actuals)
                }

        return {
            'indicator': indicator,
            'model_comparison': model_performance,
            'best_model_mae': min(model_performance.items(), key=lambda x: x[1]['mae'])[0] if model_performance else None,
            'best_model_smape': min(model_performance.items(), key=lambda x: x[1]['smape'])[0] if model_performance else None
        }


class UncertaintyCalibrator:
    """Calibrate prediction uncertainties based on historical performance"""

    def __init__(self, db: UncertaintyDatabase):
        self.db = db
        self.tracker = RollingMetricsTracker(db)

    def calibrate_confidence_intervals(self,
                                     indicator: str,
                                     current_prediction: float,
                                     model_uncertainty: float,
                                     model_confidence: float,
                                     regime: str = 'normal',
                                     confidence_level: float = 0.8) -> Tuple[float, float]:
        """Calibrate confidence intervals based on historical performance"""

        # Get historical performance
        metrics = self.tracker.calculate_rolling_metrics(indicator)

        if not metrics.get('sufficient_data', False):
            # Use model uncertainty as-is if no historical data
            z_score = 1.28 if confidence_level == 0.8 else 1.96  # 80% or 95%
            margin = z_score * model_uncertainty
            return current_prediction - margin, current_prediction + margin

        # Base calibration on historical MAE
        historical_mae = metrics['metrics']['mae']

        # Regime-specific adjustment
        regime_adjustment = 1.0
        if 'regime_breakdown' in metrics and regime in metrics['regime_breakdown']:
            regime_mae = metrics['regime_breakdown'][regime]['mae']
            overall_mae = metrics['metrics']['mae']
            if overall_mae > 0:
                regime_adjustment = regime_mae / overall_mae

        # Confidence interval coverage adjustment
        coverage_adjustment = 1.0
        if 'confidence_intervals' in metrics:
            target_coverage = confidence_level
            actual_coverage = metrics['confidence_intervals']['coverage_rate']

            if actual_coverage > 0:
                # If actual coverage is too low, widen intervals
                # If actual coverage is too high, narrow intervals
                coverage_adjustment = target_coverage / actual_coverage

        # Model confidence adjustment
        confidence_adjustment = 2.0 - model_confidence  # Lower confidence = wider intervals

        # Combined calibrated uncertainty
        calibrated_uncertainty = (historical_mae * regime_adjustment *
                                coverage_adjustment * confidence_adjustment)

        # Generate intervals
        if confidence_level == 0.8:
            z_score = 1.28
        elif confidence_level == 0.95:
            z_score = 1.96
        else:
            # Approximate for other levels
            z_score = -np.log(1 - confidence_level) * 1.5

        margin = z_score * calibrated_uncertainty

        # Asymmetric intervals for crisis regime
        if regime == 'crisis':
            # Heavier downside tail
            lower_margin = margin * 1.3
            upper_margin = margin * 0.8
        else:
            lower_margin = upper_margin = margin

        return (current_prediction - lower_margin,
                current_prediction + upper_margin)

    def get_prediction_reliability_score(self,
                                       indicator: str,
                                       model_type: str = None,
                                       regime: str = None) -> float:
        """Get reliability score for predictions"""

        metrics = self.tracker.calculate_rolling_metrics(indicator)

        if not metrics.get('sufficient_data', False):
            return 0.5  # Neutral reliability

        # Base reliability on directional accuracy and SMAPE
        directional_acc = metrics['metrics']['directional_accuracy']
        smape = metrics['metrics']['smape']

        # Convert SMAPE to reliability (lower SMAPE = higher reliability)
        smape_reliability = max(0, 1 - smape / 100)  # Assuming SMAPE < 100% is reasonable

        # Combined reliability
        base_reliability = 0.6 * directional_acc + 0.4 * smape_reliability

        # Regime-specific adjustment
        if regime and 'regime_breakdown' in metrics and regime in metrics['regime_breakdown']:
            regime_directional = metrics['regime_breakdown'][regime]['directional_accuracy']
            regime_smape = metrics['regime_breakdown'][regime]['smape']
            regime_smape_rel = max(0, 1 - regime_smape / 100)

            regime_reliability = 0.6 * regime_directional + 0.4 * regime_smape_rel
            base_reliability = 0.7 * base_reliability + 0.3 * regime_reliability

        # Sample size adjustment (more data = higher confidence in reliability)
        sample_adjustment = min(1.0, metrics['observation_count'] / 20)  # Full confidence at 20+ observations
        adjusted_reliability = base_reliability * sample_adjustment + 0.5 * (1 - sample_adjustment)

        return np.clip(adjusted_reliability, 0.1, 0.95)


class UncertaintyReporter:
    """Generate uncertainty and accuracy reports"""

    def __init__(self, db: UncertaintyDatabase):
        self.db = db
        self.tracker = RollingMetricsTracker(db)
        self.calibrator = UncertaintyCalibrator(db)

    def generate_accuracy_dashboard(self, indicators: List[str] = None) -> Dict:
        """Generate comprehensive accuracy dashboard"""

        if indicators is None:
            # Get all indicators with recent data
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            recent_records = self.db.get_predictions(start_date=start_date, end_date=end_date)
            indicators = list(set(r.indicator for r in recent_records))

        dashboard = {
            'generated_at': datetime.now().isoformat(),
            'indicators': {},
            'summary': {
                'total_indicators': len(indicators),
                'indicators_with_sufficient_data': 0,
                'overall_performance': {}
            }
        }

        # Aggregate metrics
        all_maes = []
        all_smapes = []
        all_directional_accs = []

        for indicator in indicators:
            metrics = self.tracker.calculate_rolling_metrics(indicator)
            reliability = self.calibrator.get_prediction_reliability_score(indicator)

            dashboard['indicators'][indicator] = {
                'metrics': metrics,
                'reliability_score': reliability,
                'grade': self._get_performance_grade(metrics)
            }

            if metrics.get('sufficient_data', False):
                dashboard['summary']['indicators_with_sufficient_data'] += 1
                all_maes.append(metrics['metrics']['mae'])
                all_smapes.append(metrics['metrics']['smape'])
                all_directional_accs.append(metrics['metrics']['directional_accuracy'])

        # Overall summary statistics
        if all_maes:
            dashboard['summary']['overall_performance'] = {
                'average_mae': np.mean(all_maes),
                'average_smape': np.mean(all_smapes),
                'average_directional_accuracy': np.mean(all_directional_accs),
                'best_indicator_mae': indicators[np.argmin(all_maes)],
                'worst_indicator_mae': indicators[np.argmax(all_maes)]
            }

        return dashboard

    def _get_performance_grade(self, metrics: Dict) -> str:
        """Assign performance grade based on metrics"""

        if not metrics.get('sufficient_data', False):
            return 'Insufficient Data'

        directional_acc = metrics['metrics']['directional_accuracy']
        smape = metrics['metrics']['smape']

        # Grade based on directional accuracy and SMAPE
        if directional_acc >= 0.8 and smape <= 15:
            return 'A'
        elif directional_acc >= 0.7 and smape <= 25:
            return 'B'
        elif directional_acc >= 0.6 and smape <= 35:
            return 'C'
        elif directional_acc >= 0.5 and smape <= 50:
            return 'D'
        else:
            return 'F'

    def export_metrics_to_json(self, filepath: str, indicators: List[str] = None):
        """Export metrics to JSON file"""

        dashboard = self.generate_accuracy_dashboard(indicators)

        with open(filepath, 'w') as f:
            json.dump(dashboard, f, indent=2, default=str)

        logger.info(f"Metrics exported to {filepath}")


# Export main classes
__all__ = [
    'UncertaintyDatabase',
    'PredictionRecord',
    'AccuracyMetrics',
    'RollingMetricsTracker',
    'UncertaintyCalibrator',
    'UncertaintyReporter'
]