#!/usr/bin/env python3
"""
Regime-Aware Stacking Ensemble for GDP Forecasting
===================================================
Implements learned ensemble weights with regime-specific optimization
instead of simple averaging.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from scipy.optimize import minimize
from sklearn.model_selection import KFold
import logging
import pickle
import os

logger = logging.getLogger(__name__)


@dataclass
class StackingConfig:
    """Configuration for stacking ensemble"""
    n_folds: int = 5
    min_samples_per_regime: int = 10
    regularization_alpha: float = 0.001
    weight_bounds: Tuple[float, float] = (0.0, 1.0)


class RegimeAwareStackingEnsemble:
    """
    Learns optimal model weights per economic regime
    Replaces simple averaging with constrained optimization
    """

    def __init__(self, config: StackingConfig = None):
        self.config = config or StackingConfig()
        self.regime_weights = {}
        self.global_weights = None
        self.performance_history = []

    def fit(self, X_meta: pd.DataFrame, y_true: pd.Series,
            regimes: pd.Series, countries: pd.Series = None) -> 'RegimeAwareStackingEnsemble':
        """
        Learn optimal weights for each regime

        Args:
            X_meta: Out-of-fold predictions from base models (n_samples x n_models)
            y_true: True target values
            regimes: Economic regime for each sample
            countries: Optional country labels for country-specific adjustments
        """
        logger.info("Training regime-aware stacking ensemble")

        # Store model names
        self.model_names = X_meta.columns.tolist()
        n_models = len(self.model_names)

        # Learn global weights first (fallback)
        self.global_weights = self._optimize_weights(X_meta.values, y_true.values)
        logger.info(f"Global weights: {dict(zip(self.model_names, self.global_weights))}")

        # Learn regime-specific weights
        unique_regimes = regimes.unique()

        for regime in unique_regimes:
            regime_mask = (regimes == regime)
            n_samples = regime_mask.sum()

            if n_samples >= self.config.min_samples_per_regime:
                X_regime = X_meta[regime_mask].values
                y_regime = y_true[regime_mask].values

                # Optimize weights for this regime
                weights = self._optimize_weights(X_regime, y_regime)
                self.regime_weights[regime] = weights

                logger.info(f"Regime '{regime}' weights ({n_samples} samples): "
                          f"{dict(zip(self.model_names, weights))}")
            else:
                logger.warning(f"Regime '{regime}' has only {n_samples} samples, "
                             f"using global weights")
                self.regime_weights[regime] = self.global_weights

        # Country-specific adjustments if provided
        if countries is not None:
            self._learn_country_adjustments(X_meta, y_true, countries)

        return self

    def _optimize_weights(self, X: np.ndarray, y: np.ndarray) -> np.ndarray:
        """
        Optimize ensemble weights using constrained optimization
        Weights are non-negative and sum to 1
        """
        n_models = X.shape[1]

        def objective(weights):
            """MAE loss with L2 regularization"""
            predictions = X @ weights
            mae = np.mean(np.abs(y - predictions))
            # Add small L2 penalty to prevent extreme weights
            l2_penalty = self.config.regularization_alpha * np.sum(weights ** 2)
            return mae + l2_penalty

        # Constraints: weights sum to 1
        constraints = {'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0}

        # Bounds: each weight between 0 and 1
        bounds = [self.config.weight_bounds] * n_models

        # Initial guess: equal weights
        x0 = np.ones(n_models) / n_models

        # Optimize
        result = minimize(
            objective,
            x0=x0,
            method='SLSQP',
            bounds=bounds,
            constraints=constraints,
            options={'maxiter': 1000}
        )

        if not result.success:
            logger.warning(f"Optimization failed: {result.message}, using equal weights")
            return x0

        # Ensure weights sum to 1 (numerical precision)
        weights = result.x
        weights = weights / weights.sum()

        return weights

    def _learn_country_adjustments(self, X_meta: pd.DataFrame, y_true: pd.Series,
                                  countries: pd.Series):
        """
        Learn country-specific weight adjustments
        """
        self.country_adjustments = {}

        for country in countries.unique():
            country_mask = (countries == country)
            n_samples = country_mask.sum()

            if n_samples >= 20:  # Need sufficient data
                X_country = X_meta[country_mask].values
                y_country = y_true[country_mask].values

                # Calculate performance of each model
                model_errors = {}
                for i, model in enumerate(self.model_names):
                    mae = np.mean(np.abs(X_country[:, i] - y_country))
                    model_errors[model] = mae

                # Identify best and worst models
                best_model = min(model_errors, key=model_errors.get)
                worst_model = max(model_errors, key=model_errors.get)

                # Store adjustment factors
                self.country_adjustments[country] = {
                    'boost': best_model,
                    'penalize': worst_model,
                    'factor': 0.2  # Adjustment strength
                }

                logger.info(f"Country '{country}': boost {best_model}, "
                          f"penalize {worst_model}")

    def predict(self, X_meta: pd.DataFrame, regime: str = None,
                country: str = None) -> np.ndarray:
        """
        Generate predictions using learned weights

        Args:
            X_meta: Predictions from base models (n_samples x n_models)
            regime: Current economic regime
            country: Country code for adjustments
        """
        # Get base weights for regime
        if regime and regime in self.regime_weights:
            weights = self.regime_weights[regime].copy()
        else:
            weights = self.global_weights.copy()

        # Apply country-specific adjustments
        if country and country in self.country_adjustments:
            adj = self.country_adjustments[country]
            boost_idx = self.model_names.index(adj['boost'])
            penalize_idx = self.model_names.index(adj['penalize'])

            # Adjust weights
            boost_amount = adj['factor'] * weights[penalize_idx] * 0.5
            weights[boost_idx] += boost_amount
            weights[penalize_idx] -= boost_amount

            # Renormalize
            weights = weights / weights.sum()

        # Generate ensemble prediction
        predictions = X_meta.values @ weights

        return predictions

    def get_weights(self, regime: str = None, country: str = None) -> Dict[str, float]:
        """Get the weights that would be used for given regime/country"""
        if regime and regime in self.regime_weights:
            weights = self.regime_weights[regime].copy()
        else:
            weights = self.global_weights.copy()

        # Apply country adjustments
        if country and country in self.country_adjustments:
            adj = self.country_adjustments[country]
            boost_idx = self.model_names.index(adj['boost'])
            penalize_idx = self.model_names.index(adj['penalize'])

            boost_amount = adj['factor'] * weights[penalize_idx] * 0.5
            weights[boost_idx] += boost_amount
            weights[penalize_idx] -= boost_amount
            weights = weights / weights.sum()

        return dict(zip(self.model_names, weights))

    def cross_validate(self, X_meta: pd.DataFrame, y_true: pd.Series,
                      regimes: pd.Series) -> Dict:
        """
        Cross-validate the stacking ensemble
        """
        kf = KFold(n_splits=self.config.n_folds, shuffle=False)
        cv_results = []

        for fold, (train_idx, val_idx) in enumerate(kf.split(X_meta)):
            # Split data
            X_train = X_meta.iloc[train_idx]
            y_train = y_true.iloc[train_idx]
            regimes_train = regimes.iloc[train_idx]

            X_val = X_meta.iloc[val_idx]
            y_val = y_true.iloc[val_idx]
            regimes_val = regimes.iloc[val_idx]

            # Train on fold
            fold_ensemble = RegimeAwareStackingEnsemble(self.config)
            fold_ensemble.fit(X_train, y_train, regimes_train)

            # Predict on validation
            predictions = []
            for i in range(len(X_val)):
                regime = regimes_val.iloc[i]
                pred = fold_ensemble.predict(X_val.iloc[i:i+1], regime=regime)
                predictions.append(pred[0])

            predictions = np.array(predictions)

            # Calculate metrics
            mae = np.mean(np.abs(y_val - predictions))
            rmse = np.sqrt(np.mean((y_val - predictions) ** 2))

            cv_results.append({
                'fold': fold,
                'mae': mae,
                'rmse': rmse
            })

        return {
            'mean_mae': np.mean([r['mae'] for r in cv_results]),
            'std_mae': np.std([r['mae'] for r in cv_results]),
            'mean_rmse': np.mean([r['rmse'] for r in cv_results]),
            'fold_results': cv_results
        }

    def save(self, filepath: str):
        """Save the trained ensemble"""
        with open(filepath, 'wb') as f:
            pickle.dump({
                'regime_weights': self.regime_weights,
                'global_weights': self.global_weights,
                'model_names': self.model_names,
                'country_adjustments': getattr(self, 'country_adjustments', {}),
                'config': self.config
            }, f)

    @classmethod
    def load(cls, filepath: str) -> 'RegimeAwareStackingEnsemble':
        """Load a trained ensemble"""
        with open(filepath, 'rb') as f:
            data = pickle.load(f)

        ensemble = cls(data['config'])
        ensemble.regime_weights = data['regime_weights']
        ensemble.global_weights = data['global_weights']
        ensemble.model_names = data['model_names']
        ensemble.country_adjustments = data.get('country_adjustments', {})

        return ensemble


def generate_oof_predictions(models: Dict, X: pd.DataFrame, y: pd.Series,
                            n_folds: int = 5) -> pd.DataFrame:
    """
    Generate out-of-fold predictions for stacking
    """
    kf = KFold(n_splits=n_folds, shuffle=False)
    oof_preds = pd.DataFrame(index=X.index, columns=list(models.keys()))

    for fold, (train_idx, val_idx) in enumerate(kf.split(X)):
        X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]

        # Train each model on fold and predict
        for model_name, model_class in models.items():
            # Clone model
            model = model_class.__class__(**model_class.get_params())

            # Train
            model.fit(X_train, y_train)

            # Predict on validation - use iloc for integer indexing
            val_predictions = model.predict(X_val)
            oof_preds.iloc[val_idx, oof_preds.columns.get_loc(model_name)] = val_predictions

    return oof_preds


def compare_stacking_vs_average(X_meta: pd.DataFrame, y_true: pd.Series,
                               regimes: pd.Series) -> Dict:
    """
    Compare stacking ensemble vs simple averaging
    """
    # Simple average
    simple_pred = X_meta.mean(axis=1)
    simple_mae = np.mean(np.abs(y_true - simple_pred))

    # Stacking ensemble
    stacking = RegimeAwareStackingEnsemble()
    stacking.fit(X_meta, y_true, regimes)

    stacking_pred = []
    for i in range(len(X_meta)):
        regime = regimes.iloc[i]
        pred = stacking.predict(X_meta.iloc[i:i+1], regime=regime)
        stacking_pred.append(pred[0])

    stacking_pred = np.array(stacking_pred)
    stacking_mae = np.mean(np.abs(y_true - stacking_pred))

    # Results
    improvement = (simple_mae - stacking_mae) / simple_mae * 100

    return {
        'simple_mae': simple_mae,
        'stacking_mae': stacking_mae,
        'improvement_pct': improvement,
        'regime_weights': stacking.regime_weights,
        'global_weights': dict(zip(stacking.model_names, stacking.global_weights))
    }


# Testing
if __name__ == "__main__":
    print("Regime-Aware Stacking Ensemble")
    print("=" * 60)

    # Generate synthetic data
    np.random.seed(42)
    n_samples = 200
    n_models = 5

    # True target
    y_true = pd.Series(np.random.normal(2.0, 1.5, n_samples))

    # Generate model predictions (with different error patterns)
    X_meta = pd.DataFrame()
    X_meta['gbm'] = y_true + np.random.normal(0, 0.8, n_samples)
    X_meta['rf'] = y_true + np.random.normal(0.2, 1.0, n_samples)
    X_meta['ridge'] = y_true + np.random.normal(-0.1, 0.6, n_samples)
    X_meta['elastic'] = y_true + np.random.normal(0.1, 0.7, n_samples)
    X_meta['dfm'] = y_true + np.random.normal(0, 0.5, n_samples)  # DFM is best

    # Generate regimes
    regimes = pd.Series(np.random.choice(
        ['expansion', 'normal', 'contraction', 'stress'],
        n_samples,
        p=[0.3, 0.4, 0.2, 0.1]
    ))

    # Fit stacking ensemble
    ensemble = RegimeAwareStackingEnsemble()
    ensemble.fit(X_meta, y_true, regimes)

    # Display results
    print("\nGlobal Weights:")
    for model, weight in zip(ensemble.model_names, ensemble.global_weights):
        print(f"  {model}: {weight:.3f}")

    print("\nRegime-Specific Weights:")
    for regime, weights in ensemble.regime_weights.items():
        print(f"\n{regime}:")
        for model, weight in zip(ensemble.model_names, weights):
            print(f"  {model}: {weight:.3f}")

    # Compare performance
    print("\n" + "=" * 60)
    comparison = compare_stacking_vs_average(X_meta, y_true, regimes)
    print(f"Simple Average MAE: {comparison['simple_mae']:.3f}")
    print(f"Stacking MAE: {comparison['stacking_mae']:.3f}")
    print(f"Improvement: {comparison['improvement_pct']:.1f}%")

    # Cross-validation
    cv_results = ensemble.cross_validate(X_meta, y_true, regimes)
    print(f"\nCross-Validation MAE: {cv_results['mean_mae']:.3f} ± {cv_results['std_mae']:.3f}")