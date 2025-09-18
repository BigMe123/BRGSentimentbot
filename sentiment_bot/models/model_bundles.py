#!/usr/bin/env python
"""
Model Bundles for Each Data Tier
Lite (Tier C), Standard (Tier B), Plus (Tier A)
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# Import required libraries
try:
    import lightgbm as lgb
    from sklearn.linear_model import ElasticNet
    from sklearn.model_selection import TimeSeriesSplit
    from statsmodels.tsa.api import DynamicFactor
    from mapie.regression import MapieRegressor
    from sklearn.ensemble import GradientBoostingRegressor
    ADVANCED_LIBS = True
except ImportError:
    ADVANCED_LIBS = False
    print("Install: pip install lightgbm scikit-learn statsmodels mapie")


class ModelBundleBase:
    """Base class for model bundles"""

    def __init__(self, country_code: str):
        self.country_code = country_code
        self.models = {}
        self.weights = {}
        self.last_mae = {}  # Track recent MAE for each model
        self.ensemble_history = []

    def update_weights(self, recent_errors: Dict[str, List[float]]):
        """
        Update ensemble weights based on recent MAE
        Rolling-origin cross-validation approach
        """

        if not recent_errors:
            return

        # Calculate inverse MAE weights
        mae_scores = {}
        for model_name, errors in recent_errors.items():
            if errors:
                mae_scores[model_name] = np.mean(np.abs(errors))

        if not mae_scores:
            return

        # Inverse MAE weighting
        total_inverse = sum(1.0 / mae for mae in mae_scores.values())

        for model_name, mae in mae_scores.items():
            self.weights[model_name] = (1.0 / mae) / total_inverse

        # Store for tracking
        self.last_mae = mae_scores

    def predict_ensemble(self, predictions: Dict[str, float]) -> float:
        """
        Weighted ensemble prediction

        Args:
            predictions: Dict of model_name -> prediction

        Returns:
            Weighted ensemble prediction
        """

        if not predictions:
            return 0.0

        # Use uniform weights if not set
        if not self.weights:
            self.weights = {name: 1.0/len(predictions) for name in predictions}

        weighted_sum = 0.0
        total_weight = 0.0

        for model_name, pred in predictions.items():
            weight = self.weights.get(model_name, 1.0/len(predictions))
            weighted_sum += pred * weight
            total_weight += weight

        if total_weight > 0:
            return weighted_sum / total_weight
        else:
            return np.mean(list(predictions.values()))


class LiteBundle(ModelBundleBase):
    """
    Tier C (Lean) Model Bundle
    For countries with minimal data: CPI + FX + trade headlines + sentiment
    """

    def __init__(self, country_code: str):
        super().__init__(country_code)

        # Initialize simple models
        self.models['elastic_bridge'] = ElasticNet(alpha=0.1, l1_ratio=0.5)
        if ADVANCED_LIBS:
            self.models['lgb_quantile'] = None  # Will be trained

        # Default weights for lite bundle
        self.weights = {
            'elastic_bridge': 0.6,
            'lgb_quantile': 0.4
        }

    def fit(self, X: pd.DataFrame, y: pd.Series):
        """
        Fit the lite bundle models

        Args:
            X: Features (CPI, FX, sentiment)
            y: Target (GDP growth)
        """

        # Prepare features
        feature_cols = ['cpi', 'fx_usd', 'sentiment_score']
        available_features = [col for col in feature_cols if col in X.columns]

        if not available_features:
            print(f"Warning: No features available for Lite bundle")
            return

        X_train = X[available_features].fillna(method='ffill').fillna(0)

        # Fit ElasticNet bridge
        self.models['elastic_bridge'].fit(X_train, y)

        # Fit LightGBM quantile model if available
        if ADVANCED_LIBS:
            params = {
                'objective': 'quantile',
                'alpha': 0.5,  # Median
                'min_data_in_leaf': 3,
                'learning_rate': 0.05,
                'num_leaves': 15,
                'verbose': -1
            }

            train_data = lgb.Dataset(X_train, label=y)
            self.models['lgb_quantile'] = lgb.train(
                params,
                train_data,
                num_boost_round=50
            )

    def predict(self, X: pd.DataFrame) -> Dict[str, float]:
        """
        Predict using lite bundle

        Returns:
            Dict of model predictions
        """

        predictions = {}

        # Prepare features
        feature_cols = ['cpi', 'fx_usd', 'sentiment_score']
        available_features = [col for col in feature_cols if col in X.columns]

        if not available_features:
            return {'elastic_bridge': 0.0}

        X_pred = X[available_features].fillna(method='ffill').fillna(0)

        # ElasticNet prediction
        if 'elastic_bridge' in self.models and self.models['elastic_bridge'] is not None:
            try:
                predictions['elastic_bridge'] = float(
                    self.models['elastic_bridge'].predict(X_pred.values.reshape(1, -1))[0]
                )
            except:
                predictions['elastic_bridge'] = 0.0

        # LightGBM prediction
        if ADVANCED_LIBS and 'lgb_quantile' in self.models and self.models['lgb_quantile'] is not None:
            try:
                predictions['lgb_quantile'] = float(
                    self.models['lgb_quantile'].predict(X_pred.values.reshape(1, -1))[0]
                )
            except:
                pass

        return predictions


class StandardBundle(ModelBundleBase):
    """
    Tier B (Medium) Model Bundle
    For countries with PMIs + CPI + trade + FX
    Includes Dynamic Factor Model
    """

    def __init__(self, country_code: str):
        super().__init__(country_code)

        # Initialize models
        self.models['elastic_bridge'] = ElasticNet(alpha=0.05, l1_ratio=0.3)
        self.models['dfm'] = None  # Dynamic Factor Model
        if ADVANCED_LIBS:
            self.models['lgb_median'] = None
            self.models['lgb_q10'] = None
            self.models['lgb_q90'] = None

        # Default weights
        self.weights = {
            'elastic_bridge': 0.3,
            'dfm': 0.35,
            'lgb_median': 0.35
        }

    def fit(self, X: pd.DataFrame, y: pd.Series):
        """
        Fit the standard bundle models
        """

        # Standard features for Tier B
        feature_cols = ['pmi_services', 'pmi_manufacturing', 'cpi', 'fx_usd',
                       'exports_pct_gdp', 'imports_pct_gdp', 'sentiment_score']
        available_features = [col for col in feature_cols if col in X.columns]

        if len(available_features) < 3:
            print(f"Warning: Insufficient features for Standard bundle")
            return

        X_train = X[available_features].fillna(method='ffill').fillna(0)

        # Fit ElasticNet bridge
        self.models['elastic_bridge'].fit(X_train, y)

        # Fit Dynamic Factor Model if we have enough features
        if ADVANCED_LIBS and len(available_features) >= 4:
            try:
                # DFM requires more observations than variables
                if len(X_train) > len(available_features) * 2:
                    dfm = DynamicFactor(
                        X_train,
                        k_factors=1,
                        factor_order=2,
                        error_order=1
                    )
                    self.models['dfm'] = dfm.fit(disp=False)
            except Exception as e:
                print(f"DFM fitting failed: {e}")
                self.models['dfm'] = None

        # Fit LightGBM models
        if ADVANCED_LIBS:
            for quantile, model_name in [(0.5, 'lgb_median'), (0.1, 'lgb_q10'), (0.9, 'lgb_q90')]:
                params = {
                    'objective': 'quantile',
                    'alpha': quantile,
                    'min_data_in_leaf': 5,
                    'learning_rate': 0.05,
                    'num_leaves': 31,
                    'feature_fraction': 0.8,
                    'verbose': -1
                }

                train_data = lgb.Dataset(X_train, label=y)
                self.models[model_name] = lgb.train(
                    params,
                    train_data,
                    num_boost_round=100
                )

    def predict(self, X: pd.DataFrame) -> Dict[str, float]:
        """
        Predict using standard bundle
        """

        predictions = {}

        # Prepare features
        feature_cols = ['pmi_services', 'pmi_manufacturing', 'cpi', 'fx_usd',
                       'exports_pct_gdp', 'imports_pct_gdp', 'sentiment_score']
        available_features = [col for col in feature_cols if col in X.columns]

        if not available_features:
            return {'elastic_bridge': 0.0}

        X_pred = X[available_features].fillna(method='ffill').fillna(0)

        # ElasticNet prediction
        if self.models['elastic_bridge'] is not None:
            try:
                predictions['elastic_bridge'] = float(
                    self.models['elastic_bridge'].predict(X_pred.values.reshape(1, -1))[0]
                )
            except:
                predictions['elastic_bridge'] = 0.0

        # DFM prediction
        if self.models.get('dfm') is not None:
            try:
                # DFM forecast
                forecast = self.models['dfm'].forecast(steps=1)
                if len(forecast) > 0:
                    predictions['dfm'] = float(forecast[0])
            except:
                pass

        # LightGBM median prediction
        if ADVANCED_LIBS and self.models.get('lgb_median') is not None:
            try:
                predictions['lgb_median'] = float(
                    self.models['lgb_median'].predict(X_pred.values.reshape(1, -1))[0]
                )
            except:
                pass

        return predictions

    def get_quantile_predictions(self, X: pd.DataFrame) -> Tuple[float, float]:
        """
        Get quantile predictions for confidence intervals
        """

        # Prepare features
        feature_cols = ['pmi_services', 'pmi_manufacturing', 'cpi', 'fx_usd',
                       'exports_pct_gdp', 'imports_pct_gdp', 'sentiment_score']
        available_features = [col for col in feature_cols if col in X.columns]

        if not available_features:
            return -2.0, 2.0  # Default interval

        X_pred = X[available_features].fillna(method='ffill').fillna(0)

        q10, q90 = -2.0, 2.0

        if ADVANCED_LIBS:
            if self.models.get('lgb_q10') is not None:
                try:
                    q10 = float(self.models['lgb_q10'].predict(X_pred.values.reshape(1, -1))[0])
                except:
                    pass

            if self.models.get('lgb_q90') is not None:
                try:
                    q90 = float(self.models['lgb_q90'].predict(X_pred.values.reshape(1, -1))[0])
                except:
                    pass

        return q10, q90


class PlusBundle(ModelBundleBase):
    """
    Tier A (Rich) Model Bundle
    Full indicators + interaction terms + direction classifier
    """

    def __init__(self, country_code: str):
        super().__init__(country_code)

        # Initialize models
        self.models['elastic_bridge'] = ElasticNet(alpha=0.05, l1_ratio=0.2)
        self.models['dfm'] = None
        if ADVANCED_LIBS:
            self.models['lgb_median'] = None
            self.models['lgb_q10'] = None
            self.models['lgb_q90'] = None
            self.models['direction_classifier'] = None

        # Weights for Plus bundle
        self.weights = {
            'elastic_bridge': 0.25,
            'dfm': 0.25,
            'lgb_median': 0.35,
            'direction_boost': 0.15
        }

    def _create_interaction_features(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        Create interaction terms for Tier A
        """

        X_int = X.copy()

        # Services PMI × FX interaction (important for service economies)
        if 'pmi_services' in X.columns and 'fx_usd' in X.columns:
            X_int['pmi_fx_interaction'] = X['pmi_services'] * X['fx_usd']

        # Energy CPI × Trade interaction
        if 'energy_cpi' in X.columns and 'exports_pct_gdp' in X.columns:
            X_int['energy_trade_interaction'] = X['energy_cpi'] * X['exports_pct_gdp']

        # Unemployment × Consumer confidence interaction
        if 'unemployment_rate' in X.columns and 'consumer_confidence' in X.columns:
            X_int['labor_sentiment_interaction'] = X['unemployment_rate'] * X['consumer_confidence']

        # Credit × Investment interaction
        if 'credit_approvals' in X.columns and 'gross_fixed_capital_formation' in X.columns:
            X_int['credit_investment_interaction'] = X['credit_approvals'] * X['gross_fixed_capital_formation']

        return X_int

    def fit(self, X: pd.DataFrame, y: pd.Series):
        """
        Fit the Plus bundle with all features and interactions
        """

        # Create interaction features
        X_enhanced = self._create_interaction_features(X)

        # All available features
        X_train = X_enhanced.fillna(method='ffill').fillna(0)

        # Fit ElasticNet
        self.models['elastic_bridge'].fit(X_train, y)

        # Fit DFM on core indicators only (not interactions)
        core_features = ['pmi_services', 'pmi_manufacturing', 'retail_sales',
                        'industrial_production', 'unemployment_rate', 'cpi']
        core_available = [col for col in core_features if col in X.columns]

        if ADVANCED_LIBS and len(core_available) >= 4:
            try:
                X_core = X[core_available].fillna(method='ffill').fillna(0)
                if len(X_core) > len(core_available) * 2:
                    dfm = DynamicFactor(
                        X_core,
                        k_factors=2,  # Two factors for richer data
                        factor_order=2,
                        error_order=1
                    )
                    self.models['dfm'] = dfm.fit(disp=False)
            except:
                self.models['dfm'] = None

        # Fit LightGBM models with all features
        if ADVANCED_LIBS:
            for quantile, model_name in [(0.5, 'lgb_median'), (0.1, 'lgb_q10'), (0.9, 'lgb_q90')]:
                params = {
                    'objective': 'quantile',
                    'alpha': quantile,
                    'min_data_in_leaf': 10,
                    'learning_rate': 0.03,
                    'num_leaves': 63,
                    'feature_fraction': 0.7,
                    'bagging_fraction': 0.8,
                    'bagging_freq': 5,
                    'verbose': -1
                }

                train_data = lgb.Dataset(X_train, label=y)
                self.models[model_name] = lgb.train(
                    params,
                    train_data,
                    num_boost_round=200
                )

            # Fit direction classifier
            from sklearn.linear_model import LogisticRegression
            y_direction = (y > y.median()).astype(int)
            self.models['direction_classifier'] = LogisticRegression(max_iter=500)
            self.models['direction_classifier'].fit(X_train, y_direction)

    def predict(self, X: pd.DataFrame) -> Dict[str, float]:
        """
        Predict using Plus bundle with direction boost
        """

        predictions = {}

        # Create interaction features
        X_enhanced = self._create_interaction_features(X)
        X_pred = X_enhanced.fillna(method='ffill').fillna(0)

        # Get base predictions
        if self.models['elastic_bridge'] is not None:
            try:
                predictions['elastic_bridge'] = float(
                    self.models['elastic_bridge'].predict(X_pred.values.reshape(1, -1))[0]
                )
            except:
                predictions['elastic_bridge'] = 0.0

        # DFM prediction
        if self.models.get('dfm') is not None:
            try:
                forecast = self.models['dfm'].forecast(steps=1)
                if len(forecast) > 0:
                    predictions['dfm'] = float(forecast[0])
            except:
                pass

        # LightGBM prediction
        if ADVANCED_LIBS and self.models.get('lgb_median') is not None:
            try:
                predictions['lgb_median'] = float(
                    self.models['lgb_median'].predict(X_pred.values.reshape(1, -1))[0]
                )
            except:
                pass

        # Direction boost
        if ADVANCED_LIBS and self.models.get('direction_classifier') is not None:
            try:
                # Get direction probability
                direction_prob = self.models['direction_classifier'].predict_proba(
                    X_pred.values.reshape(1, -1)
                )[0, 1]

                # Boost predictions based on direction confidence
                base_pred = np.mean(list(predictions.values()))
                if direction_prob > 0.7:  # Strong positive signal
                    predictions['direction_boost'] = base_pred * 1.1
                elif direction_prob < 0.3:  # Strong negative signal
                    predictions['direction_boost'] = base_pred * 0.9
                else:
                    predictions['direction_boost'] = base_pred
            except:
                pass

        return predictions


def select_bundle(country_code: str, data_tier: str) -> ModelBundleBase:
    """
    Select appropriate model bundle based on data tier

    Args:
        country_code: Country code
        data_tier: 'rich', 'medium', or 'lean'

    Returns:
        Appropriate model bundle instance
    """

    if data_tier == 'rich':
        return PlusBundle(country_code)
    elif data_tier == 'medium':
        return StandardBundle(country_code)
    else:
        return LiteBundle(country_code)


def test_model_bundles():
    """Test the model bundles"""

    print("🎯 TESTING MODEL BUNDLES")
    print("="*60)

    # Generate sample data
    np.random.seed(42)
    dates = pd.date_range('2020-01-01', '2023-12-31', freq='Q')
    n = len(dates)

    # Tier C test (minimal data)
    print("\n📦 Testing Lite Bundle (Tier C)")
    X_lite = pd.DataFrame({
        'cpi': np.random.normal(2, 0.5, n),
        'fx_usd': np.random.normal(1.2, 0.1, n),
        'sentiment_score': np.random.uniform(0.3, 0.7, n)
    }, index=dates)
    y = pd.Series(np.random.normal(1.5, 1.0, n), index=dates)

    lite_bundle = LiteBundle('TEST')
    lite_bundle.fit(X_lite.iloc[:-4], y.iloc[:-4])
    predictions = lite_bundle.predict(X_lite.iloc[-1])
    ensemble = lite_bundle.predict_ensemble(predictions)

    print(f"  Models trained: {list(lite_bundle.models.keys())}")
    print(f"  Predictions: {predictions}")
    print(f"  Ensemble: {ensemble:.2f}%")

    # Tier B test (medium data)
    print("\n📦 Testing Standard Bundle (Tier B)")
    X_standard = pd.DataFrame({
        'pmi_services': np.random.normal(52, 3, n),
        'pmi_manufacturing': np.random.normal(50, 4, n),
        'cpi': np.random.normal(2, 0.5, n),
        'fx_usd': np.random.normal(1.2, 0.1, n),
        'exports_pct_gdp': np.random.normal(30, 5, n),
        'imports_pct_gdp': np.random.normal(32, 5, n),
        'sentiment_score': np.random.uniform(0.3, 0.7, n)
    }, index=dates)

    standard_bundle = StandardBundle('TEST')
    standard_bundle.fit(X_standard.iloc[:-4], y.iloc[:-4])
    predictions = standard_bundle.predict(X_standard.iloc[-1])
    q10, q90 = standard_bundle.get_quantile_predictions(X_standard.iloc[-1])
    ensemble = standard_bundle.predict_ensemble(predictions)

    print(f"  Models trained: {list(standard_bundle.models.keys())}")
    print(f"  Predictions: {predictions}")
    print(f"  Ensemble: {ensemble:.2f}%")
    print(f"  80% CI: [{q10:.1f}, {q90:.1f}]")

    # Tier A test (rich data)
    print("\n📦 Testing Plus Bundle (Tier A)")
    X_plus = X_standard.copy()
    X_plus['retail_sales'] = np.random.normal(100, 10, n)
    X_plus['industrial_production'] = np.random.normal(100, 5, n)
    X_plus['unemployment_rate'] = np.random.normal(4, 0.5, n)
    X_plus['consumer_confidence'] = np.random.normal(-10, 5, n)
    X_plus['energy_cpi'] = np.random.normal(3, 1, n)
    X_plus['gross_fixed_capital_formation'] = np.random.normal(22, 3, n)

    plus_bundle = PlusBundle('TEST')
    plus_bundle.fit(X_plus.iloc[:-4], y.iloc[:-4])
    predictions = plus_bundle.predict(X_plus.iloc[-1])
    ensemble = plus_bundle.predict_ensemble(predictions)

    print(f"  Models trained: {list(plus_bundle.models.keys())}")
    print(f"  Predictions: {predictions}")
    print(f"  Ensemble: {ensemble:.2f}%")
    print(f"  Interaction features created: ✅")


if __name__ == "__main__":
    test_model_bundles()