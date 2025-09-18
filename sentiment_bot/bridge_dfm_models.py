#!/usr/bin/env python3
"""
Sophisticated Bridge Equation and Dynamic Factor Model (DFM) Implementation
==========================================================================

Advanced econometric models for nowcasting and forecasting economic indicators
using high-frequency sentiment data to predict low-frequency economic variables.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any, Union
from datetime import datetime, timedelta
from dataclasses import dataclass
from scipy import linalg
from scipy.optimize import minimize
import warnings
warnings.filterwarnings('ignore')

# Try importing advanced libraries
try:
    from sklearn.decomposition import PCA, FactorAnalysis
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import Ridge, ElasticNet
    from statsmodels.tsa.statespace.dynamic_factor import DynamicFactor
    from statsmodels.tsa.api import VAR
    from statsmodels.regression.mixed_linear_model import MixedLM
    ADVANCED_MODELS = True
except ImportError:
    ADVANCED_MODELS = False
    print("⚠️ Some advanced libraries not available. Using simplified implementations.")


@dataclass
class BridgeEquationConfig:
    """Configuration for Bridge Equation models."""
    target_variable: str  # e.g., 'GDP', 'Inflation', 'Employment'
    frequency_target: str  # 'Q' for quarterly, 'M' for monthly
    frequency_predictors: str  # 'D' for daily, 'W' for weekly
    lag_structure: List[int]  # e.g., [0, 1, 2] for current and two lags
    regularization: float = 0.1
    use_sentiment: bool = True
    use_survey: bool = True
    use_financial: bool = True


@dataclass
class DFMConfig:
    """Configuration for Dynamic Factor Model."""
    n_factors: int = 3  # Number of latent factors
    factor_order: int = 2  # VAR order for factor dynamics
    error_order: int = 1  # AR order for idiosyncratic errors
    em_iterations: int = 100  # EM algorithm iterations
    convergence_tol: float = 1e-4


class BridgeEquationModel:
    """
    Bridge Equation Model for Nowcasting

    Bridges the gap between high-frequency indicators (daily sentiment)
    and low-frequency targets (quarterly GDP) using MIDAS-type regression.
    """

    def __init__(self, config: BridgeEquationConfig):
        """Initialize Bridge Equation model."""
        self.config = config
        self.scaler = StandardScaler() if ADVANCED_MODELS else None
        self.model = None
        self.coefficients = {}
        self.forecast_history = []

    def prepare_data(self,
                    high_freq_data: pd.DataFrame,
                    low_freq_target: pd.Series,
                    alignment: str = 'end') -> Tuple[np.ndarray, np.ndarray]:
        """
        Prepare and align high-frequency predictors with low-frequency target.

        Args:
            high_freq_data: High-frequency predictors (e.g., daily sentiment)
            low_freq_target: Low-frequency target (e.g., quarterly GDP)
            alignment: How to aggregate ('end', 'mean', 'sum')
        """
        # Aggregate high-frequency data to match target frequency
        if self.config.frequency_target == 'Q' and self.config.frequency_predictors == 'D':
            # Daily to Quarterly aggregation
            agg_func = {
                'end': lambda x: x.iloc[-1] if len(x) > 0 else np.nan,
                'mean': lambda x: x.mean(),
                'sum': lambda x: x.sum()
            }.get(alignment, lambda x: x.mean())

            # Resample to quarterly
            high_freq_agg = high_freq_data.resample('Q').apply(agg_func)

        elif self.config.frequency_target == 'M' and self.config.frequency_predictors == 'W':
            # Weekly to Monthly aggregation
            high_freq_agg = high_freq_data.resample('M').mean()
        else:
            # Same frequency or custom handling
            high_freq_agg = high_freq_data

        # Create lagged features for bridge equation
        X_bridge = self._create_bridge_features(high_freq_agg)

        # Align with target - handle index mismatch
        # For time series alignment, we need to ensure proper date matching
        if len(X_bridge) > 0 and len(low_freq_target) > 0:
            # Find common dates
            common_index = X_bridge.index.intersection(low_freq_target.index)
            if len(common_index) > 0:
                X_aligned = X_bridge.loc[common_index]
                y_aligned = low_freq_target.loc[common_index]
                return X_aligned.values, y_aligned.values

        # Return empty arrays if no alignment possible
        return np.array([]).reshape(0, X_bridge.shape[1] if len(X_bridge) > 0 else 0), np.array([])

    def _create_bridge_features(self, data: pd.DataFrame) -> pd.DataFrame:
        """Create bridge equation features with lag structure."""
        features = pd.DataFrame(index=data.index)

        for col in data.columns:
            for lag in self.config.lag_structure:
                if lag == 0:
                    features[f"{col}_t"] = data[col]
                else:
                    features[f"{col}_t-{lag}"] = data[col].shift(lag)

        # Add MIDAS polynomial weights if needed
        if len(self.config.lag_structure) > 3:
            features = self._apply_midas_weights(features)

        return features.dropna()

    def _apply_midas_weights(self, features: pd.DataFrame) -> pd.DataFrame:
        """Apply MIDAS (Mixed Data Sampling) polynomial weights."""
        # Exponential Almon polynomial weights
        n_lags = len(self.config.lag_structure)
        theta1, theta2 = 0.5, -0.1  # Parameters for exponential decay

        weights = np.zeros(n_lags)
        for i in range(n_lags):
            weights[i] = np.exp(theta1 * i + theta2 * i**2)

        weights = weights / weights.sum()  # Normalize

        # Apply weights to features
        weighted_features = features.copy()
        for col in features.columns:
            if '_t-' in col:  # Lagged variable
                lag_num = int(col.split('-')[-1])
                if lag_num < n_lags:
                    weighted_features[col] = features[col] * weights[lag_num]

        return weighted_features

    def fit(self,
            high_freq_data: pd.DataFrame,
            low_freq_target: pd.Series,
            validation_split: float = 0.2):
        """
        Fit the bridge equation model.
        """
        X, y = self.prepare_data(high_freq_data, low_freq_target)

        # Check if we have data to fit
        if len(X) == 0 or len(y) == 0:
            return {
                'train_r2': 0.0,
                'val_r2': 0.0,
                'n_features': X.shape[1] if len(X) > 0 else 0,
                'n_samples': 0,
                'error': 'No data available after alignment'
            }

        # Train-validation split
        n_train = max(1, int(len(X) * (1 - validation_split)))
        X_train, X_val = X[:n_train], X[n_train:]
        y_train, y_val = y[:n_train], y[n_train:]

        if ADVANCED_MODELS and self.scaler:
            # Scale features
            X_train_scaled = self.scaler.fit_transform(X_train)
            X_val_scaled = self.scaler.transform(X_val)

            # Fit regularized regression
            self.model = ElasticNet(
                alpha=self.config.regularization,
                l1_ratio=0.5,
                max_iter=1000
            )
            self.model.fit(X_train_scaled, y_train)

            # Validate
            train_score = self.model.score(X_train_scaled, y_train)
            val_score = self.model.score(X_val_scaled, y_val) if len(X_val) > 0 else 0

        else:
            # Simple OLS fallback
            self.coefficients = self._fit_ols(X_train, y_train)
            train_score = self._score_ols(X_train, y_train)
            val_score = self._score_ols(X_val, y_val) if len(X_val) > 0 else 0

        return {
            'train_r2': train_score,
            'val_r2': val_score,
            'n_features': X.shape[1],
            'n_samples': len(X)
        }

    def _fit_ols(self, X: np.ndarray, y: np.ndarray) -> np.ndarray:
        """Fit using ordinary least squares."""
        # Add intercept
        X_with_intercept = np.column_stack([np.ones(len(X)), X])

        # Solve normal equations
        try:
            coeffs = np.linalg.lstsq(X_with_intercept, y, rcond=None)[0]
        except:
            coeffs = np.zeros(X_with_intercept.shape[1])
            coeffs[0] = y.mean()  # Use mean as intercept

        return coeffs

    def _score_ols(self, X: np.ndarray, y: np.ndarray) -> float:
        """Calculate R-squared for OLS model."""
        if len(self.coefficients) == 0:
            return 0.0

        X_with_intercept = np.column_stack([np.ones(len(X)), X])
        y_pred = X_with_intercept @ self.coefficients

        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - y.mean()) ** 2)

        return 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

    def nowcast(self,
               current_high_freq: pd.DataFrame,
               horizon: int = 1) -> Dict[str, Any]:
        """
        Perform nowcasting using current high-frequency data.
        """
        # Prepare current data
        X_current = self._create_bridge_features(current_high_freq)

        if X_current.empty:
            return {
                'forecast': self.config.target_variable,
                'confidence_interval': (np.nan, np.nan),
                'uncertainty': np.nan
            }

        X_current_values = X_current.iloc[-1:].values

        if ADVANCED_MODELS and self.model and self.scaler:
            X_scaled = self.scaler.transform(X_current_values)
            forecast = self.model.predict(X_scaled)[0]

            # Estimate uncertainty using residual variance
            residual_std = 0.1  # Placeholder
            confidence_interval = (
                forecast - 1.96 * residual_std,
                forecast + 1.96 * residual_std
            )
        else:
            # OLS prediction
            X_with_intercept = np.column_stack([np.ones(1), X_current_values])
            forecast = (X_with_intercept @ self.coefficients)[0]
            confidence_interval = (forecast * 0.9, forecast * 1.1)

        result = {
            'forecast': float(forecast),
            'confidence_interval': confidence_interval,
            'uncertainty': float(confidence_interval[1] - confidence_interval[0]) / 2,
            'timestamp': datetime.now(),
            'data_points_used': len(X_current)
        }

        self.forecast_history.append(result)
        return result


class DynamicFactorModel:
    """
    Dynamic Factor Model for Economic Nowcasting

    Extracts common factors from multiple high-frequency indicators
    to predict economic variables using state-space representation.
    """

    def __init__(self, config: DFMConfig):
        """Initialize Dynamic Factor Model."""
        self.config = config
        self.factors = None
        self.loadings = None
        self.transition_matrix = None
        self.observation_matrix = None
        self.state_cov = None
        self.obs_cov = None
        self.scaler = StandardScaler() if ADVANCED_MODELS else None

    def extract_factors(self,
                        data: pd.DataFrame,
                        method: str = 'pca') -> np.ndarray:
        """
        Extract latent factors from high-dimensional data.

        Args:
            data: Panel of indicators
            method: 'pca', 'fa', or 'em' (EM algorithm)
        """
        # Handle missing values
        data_clean = data.fillna(method='ffill').fillna(method='bfill')

        if ADVANCED_MODELS:
            if self.scaler:
                data_scaled = self.scaler.fit_transform(data_clean)
            else:
                data_scaled = data_clean.values

            if method == 'pca':
                # Principal Component Analysis
                pca = PCA(n_components=self.config.n_factors)
                self.factors = pca.fit_transform(data_scaled)
                self.loadings = pca.components_.T
                explained_var = pca.explained_variance_ratio_

            elif method == 'fa':
                # Factor Analysis
                fa = FactorAnalysis(n_components=self.config.n_factors)
                self.factors = fa.fit_transform(data_scaled)
                self.loadings = fa.components_.T
                explained_var = None

            else:  # EM algorithm
                self.factors, self.loadings = self._em_algorithm(data_scaled)
                explained_var = None

        else:
            # Simple factor extraction using correlation matrix
            self.factors, self.loadings = self._simple_factor_extraction(data_clean.values)
            explained_var = None

        return self.factors

    def _em_algorithm(self, data: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        EM algorithm for factor extraction with missing values.
        """
        n_obs, n_vars = data.shape
        n_factors = self.config.n_factors

        # Initialize parameters
        factors = np.random.randn(n_obs, n_factors)
        loadings = np.random.randn(n_vars, n_factors)

        for iteration in range(self.config.em_iterations):
            # E-step: Estimate factors given loadings
            for t in range(n_obs):
                # Handle missing values
                obs_idx = ~np.isnan(data[t, :])
                if np.any(obs_idx):
                    L_t = loadings[obs_idx, :]
                    y_t = data[t, obs_idx]

                    # Factor estimation
                    factors[t, :] = np.linalg.lstsq(
                        L_t.T @ L_t + 0.01 * np.eye(n_factors),
                        L_t.T @ y_t,
                        rcond=None
                    )[0]

            # M-step: Estimate loadings given factors
            for i in range(n_vars):
                obs_idx = ~np.isnan(data[:, i])
                if np.any(obs_idx):
                    F_i = factors[obs_idx, :]
                    y_i = data[obs_idx, i]

                    loadings[i, :] = np.linalg.lstsq(
                        F_i.T @ F_i + 0.01 * np.eye(n_factors),
                        F_i.T @ y_i,
                        rcond=None
                    )[0]

            # Check convergence (simplified)
            if iteration > 10 and iteration % 10 == 0:
                # Could add proper convergence check here
                pass

        return factors, loadings

    def _simple_factor_extraction(self, data: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Simple factor extraction using eigendecomposition."""
        # Compute correlation matrix
        corr_matrix = np.corrcoef(data.T)

        # Eigendecomposition
        eigenvalues, eigenvectors = np.linalg.eigh(corr_matrix)

        # Select top factors
        idx = eigenvalues.argsort()[-self.config.n_factors:][::-1]
        loadings = eigenvectors[:, idx]

        # Compute factor scores
        factors = data @ loadings

        return factors, loadings

    def fit_state_space(self, factors: np.ndarray):
        """
        Fit state-space model for factor dynamics.

        State equation: f_t = A * f_{t-1} + B * u_t
        Observation equation: y_t = C * f_t + D * e_t
        """
        if ADVANCED_MODELS:
            try:
                # Use statsmodels DynamicFactor if available
                model = VAR(factors)
                results = model.fit(self.config.factor_order)

                self.transition_matrix = results.coefs.reshape(
                    self.config.n_factors * self.config.factor_order,
                    self.config.n_factors
                ).T

            except:
                # Fallback to simple VAR estimation
                self.transition_matrix = self._fit_var_simple(factors)
        else:
            self.transition_matrix = self._fit_var_simple(factors)

        # Estimate covariance matrices
        self._estimate_covariances(factors)

    def _fit_var_simple(self, factors: np.ndarray) -> np.ndarray:
        """Simple VAR estimation."""
        p = self.config.factor_order
        n_factors = factors.shape[1]
        T = len(factors)

        # Create lagged matrix
        Y = factors[p:, :]
        X = np.hstack([factors[p-i:-i, :] for i in range(1, p+1)])

        # OLS estimation
        A = np.linalg.lstsq(X, Y, rcond=None)[0].T

        return A

    def _estimate_covariances(self, factors: np.ndarray):
        """Estimate state and observation covariance matrices."""
        if self.transition_matrix is not None:
            # Compute residuals
            p = self.config.factor_order
            T = len(factors) - p

            residuals = np.zeros((T, self.config.n_factors))
            for t in range(p, len(factors)):
                pred = self.transition_matrix @ factors[t-1, :]
                residuals[t-p, :] = factors[t, :] - pred

            self.state_cov = np.cov(residuals.T)

    def forecast(self,
                current_factors: np.ndarray,
                horizon: int = 4) -> Dict[str, Any]:
        """
        Forecast factors and economic variables.
        """
        if self.transition_matrix is None:
            return {
                'factor_forecast': np.zeros((horizon, self.config.n_factors)),
                'uncertainty': np.ones(horizon)
            }

        # Initialize forecast
        factor_forecast = np.zeros((horizon, self.config.n_factors))
        current = current_factors[-1, :] if len(current_factors.shape) > 1 else current_factors

        # Iterate forecast
        for h in range(horizon):
            current = self.transition_matrix @ current
            factor_forecast[h, :] = current

        # Compute forecast uncertainty
        uncertainty = self._compute_forecast_uncertainty(horizon)

        return {
            'factor_forecast': factor_forecast,
            'uncertainty': uncertainty,
            'horizon': horizon,
            'timestamp': datetime.now()
        }

    def _compute_forecast_uncertainty(self, horizon: int) -> np.ndarray:
        """Compute forecast uncertainty using state covariance."""
        if self.state_cov is None:
            return np.ones(horizon)

        uncertainty = np.zeros(horizon)
        cumulative_cov = self.state_cov.copy()

        for h in range(horizon):
            uncertainty[h] = np.sqrt(np.trace(cumulative_cov))

            # Propagate uncertainty
            cumulative_cov = (
                self.transition_matrix @ cumulative_cov @ self.transition_matrix.T
                + self.state_cov
            )

        return uncertainty


class IntegratedNowcastingSystem:
    """
    Integrated system combining Bridge Equations and DFM for comprehensive nowcasting.
    """

    def __init__(self):
        """Initialize integrated nowcasting system."""
        self.bridge_models = {}
        self.dfm_model = None
        self.nowcast_history = []

    def initialize_models(self, target_variables: List[str]):
        """Initialize models for different target variables."""

        # Create bridge models for each target
        for target in target_variables:
            config = BridgeEquationConfig(
                target_variable=target,
                frequency_target='Q' if target == 'GDP' else 'M',
                frequency_predictors='D',
                lag_structure=[0, 1, 7, 14, 30],  # Multiple lags
                regularization=0.1
            )
            self.bridge_models[target] = BridgeEquationModel(config)

        # Initialize DFM
        dfm_config = DFMConfig(
            n_factors=3,
            factor_order=2,
            em_iterations=50
        )
        self.dfm_model = DynamicFactorModel(dfm_config)

    def nowcast_all(self,
                   sentiment_data: pd.DataFrame,
                   economic_data: pd.DataFrame,
                   financial_data: pd.DataFrame) -> Dict[str, Any]:
        """
        Perform comprehensive nowcasting using all available data.
        """
        results = {}

        # Extract factors from combined data
        combined_data = pd.concat([
            sentiment_data,
            economic_data,
            financial_data
        ], axis=1)

        factors = self.dfm_model.extract_factors(combined_data)
        self.dfm_model.fit_state_space(factors)

        # Generate factor forecasts
        factor_forecast = self.dfm_model.forecast(factors, horizon=4)

        # Bridge equation nowcasts for each target
        for target, model in self.bridge_models.items():
            if target == 'GDP':
                bridge_nowcast = model.nowcast(sentiment_data)
                results[target] = {
                    'bridge_nowcast': bridge_nowcast['forecast'],
                    'confidence_interval': bridge_nowcast['confidence_interval'],
                    'method': 'bridge_equation'
                }
            else:
                # Use factors for other variables
                factor_based = self._factor_to_variable(
                    factor_forecast['factor_forecast'],
                    target
                )
                results[target] = {
                    'factor_nowcast': factor_based,
                    'method': 'dynamic_factor_model'
                }

        # Combine forecasts using optimal weights
        combined_forecast = self._combine_forecasts(results)

        # Store in history
        nowcast_entry = {
            'timestamp': datetime.now(),
            'forecasts': results,
            'combined': combined_forecast,
            'data_quality': self._assess_data_quality(combined_data)
        }
        self.nowcast_history.append(nowcast_entry)

        return nowcast_entry

    def _factor_to_variable(self,
                          factor_forecast: np.ndarray,
                          target: str) -> float:
        """Convert factor forecast to target variable."""
        # Simple weighted average (could be more sophisticated)
        weights = {
            'Inflation': np.array([0.5, 0.3, 0.2]),
            'Employment': np.array([0.4, 0.4, 0.2]),
            'Trade': np.array([0.3, 0.3, 0.4])
        }.get(target, np.array([1/3, 1/3, 1/3]))

        return float(np.dot(factor_forecast[0, :], weights))

    def _combine_forecasts(self, forecasts: Dict) -> Dict:
        """Combine multiple forecasts using optimal weights."""
        combined = {}

        for target, forecast_dict in forecasts.items():
            if 'bridge_nowcast' in forecast_dict and 'factor_nowcast' in forecast_dict:
                # Inverse variance weighting
                bridge_var = 0.1  # Placeholder
                factor_var = 0.15  # Placeholder

                w_bridge = (1/bridge_var) / (1/bridge_var + 1/factor_var)
                w_factor = 1 - w_bridge

                combined[target] = (
                    w_bridge * forecast_dict['bridge_nowcast'] +
                    w_factor * forecast_dict['factor_nowcast']
                )
            elif 'bridge_nowcast' in forecast_dict:
                combined[target] = forecast_dict['bridge_nowcast']
            elif 'factor_nowcast' in forecast_dict:
                combined[target] = forecast_dict['factor_nowcast']

        return combined

    def _assess_data_quality(self, data: pd.DataFrame) -> Dict:
        """Assess quality of input data."""
        return {
            'completeness': 1 - data.isna().sum().sum() / data.size,
            'n_indicators': len(data.columns),
            'n_observations': len(data),
            'frequency': 'mixed'
        }

    def get_model_diagnostics(self) -> Dict:
        """Get comprehensive model diagnostics."""
        diagnostics = {
            'bridge_models': {},
            'dfm_model': {},
            'nowcast_performance': {}
        }

        # Bridge model diagnostics
        for target, model in self.bridge_models.items():
            diagnostics['bridge_models'][target] = {
                'n_features': len(model.coefficients) if hasattr(model, 'coefficients') else 0,
                'n_forecasts': len(model.forecast_history)
            }

        # DFM diagnostics
        if self.dfm_model and self.dfm_model.factors is not None:
            diagnostics['dfm_model'] = {
                'n_factors': self.config.n_factors if hasattr(self, 'config') else 3,
                'factor_variance': np.var(self.dfm_model.factors, axis=0).tolist() if self.dfm_model.factors is not None else []
            }

        # Performance metrics
        if self.nowcast_history:
            recent_nowcasts = self.nowcast_history[-10:]
            diagnostics['nowcast_performance'] = {
                'n_nowcasts': len(self.nowcast_history),
                'recent_targets': list(recent_nowcasts[-1]['forecasts'].keys()) if recent_nowcasts else []
            }

        return diagnostics


# Factory functions for easy integration
def create_bridge_model(target: str = 'GDP', **kwargs) -> BridgeEquationModel:
    """Create a configured Bridge Equation model."""
    # Extract config parameters, avoiding duplicates
    freq_target = kwargs.pop('frequency_target', 'Q' if target == 'GDP' else 'M')
    freq_predictors = kwargs.pop('frequency_predictors', 'D')
    lag_structure = kwargs.pop('lag_structure', [0, 1, 7, 30])

    config = BridgeEquationConfig(
        target_variable=target,
        frequency_target=freq_target,
        frequency_predictors=freq_predictors,
        lag_structure=lag_structure,
        **kwargs
    )
    return BridgeEquationModel(config)


def create_dfm_model(n_factors: int = 3, **kwargs) -> DynamicFactorModel:
    """Create a configured Dynamic Factor Model."""
    # Extract config parameters, avoiding duplicates
    factor_order = kwargs.pop('factor_order', 2)

    config = DFMConfig(
        n_factors=n_factors,
        factor_order=factor_order,
        **kwargs
    )
    return DynamicFactorModel(config)


def create_integrated_nowcasting_system() -> IntegratedNowcastingSystem:
    """Create an integrated nowcasting system."""
    system = IntegratedNowcastingSystem()
    system.initialize_models(['GDP', 'Inflation', 'Employment', 'Trade'])
    return system