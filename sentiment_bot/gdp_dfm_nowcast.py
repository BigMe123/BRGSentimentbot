#!/usr/bin/env python3
"""
Dynamic Factor Model (DFM) for GDP Nowcasting
==============================================
Implements mixed-frequency nowcasting using latent factors extracted from
monthly indicators to predict quarterly GDP growth.

Mathematical Foundation:
- State equation: F_t = A*F_{t-1} + η_t
- Observation equation: X_t = Λ*F_t + ε_t
- Bridge equation: GDP_q = β*aggregate(F_t) + u_t
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
import warnings
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from scipy import linalg
from scipy.optimize import minimize
import logging

warnings.filterwarnings('ignore')
logger = logging.getLogger(__name__)


@dataclass
class DFMConfig:
    """Configuration for Dynamic Factor Model"""
    n_factors: int = 3
    n_lags: int = 1
    em_tol: float = 1e-4
    em_max_iter: int = 500
    min_variance_explained: float = 0.65


class KalmanFilter:
    """Kalman filter for state space models"""

    def __init__(self, F: np.ndarray, H: np.ndarray, Q: np.ndarray, R: np.ndarray):
        """
        Initialize Kalman filter
        F: State transition matrix
        H: Observation matrix
        Q: Process noise covariance
        R: Observation noise covariance
        """
        self.F = F  # State transition
        self.H = H  # Observation matrix
        self.Q = Q  # Process noise
        self.R = R  # Measurement noise

        self.n_states = F.shape[0]
        self.n_obs = H.shape[0]

    def filter(self, observations: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Run Kalman filter on observations"""
        T = observations.shape[0]

        # Initialize
        filtered_states = np.zeros((T, self.n_states))
        filtered_covariances = np.zeros((T, self.n_states, self.n_states))

        # Initial state
        x = np.zeros(self.n_states)
        P = np.eye(self.n_states)

        for t in range(T):
            # Prediction step
            x_pred = self.F @ x
            P_pred = self.F @ P @ self.F.T + self.Q

            # Update step
            y = observations[t]

            # Handle missing values
            obs_mask = ~np.isnan(y)
            if np.any(obs_mask):
                H_t = self.H[obs_mask]
                R_t = self.R[np.ix_(obs_mask, obs_mask)]
                y_t = y[obs_mask]

                # Innovation
                v = y_t - H_t @ x_pred
                S = H_t @ P_pred @ H_t.T + R_t

                # Kalman gain
                K = P_pred @ H_t.T @ linalg.inv(S)

                # Updated state
                x = x_pred + K @ v
                P = (np.eye(self.n_states) - K @ H_t) @ P_pred
            else:
                # No observation, use prediction
                x = x_pred
                P = P_pred

            filtered_states[t] = x
            filtered_covariances[t] = P

        return filtered_states, filtered_covariances

    def smooth(self, observations: np.ndarray) -> np.ndarray:
        """Rauch-Tung-Striebel smoother"""
        # Forward pass
        filtered_states, filtered_covs = self.filter(observations)

        T = observations.shape[0]
        smoothed_states = np.zeros_like(filtered_states)
        smoothed_states[-1] = filtered_states[-1]

        # Backward pass
        for t in range(T-2, -1, -1):
            # Prediction for next step
            x_pred = self.F @ filtered_states[t]
            P_pred = self.F @ filtered_covs[t] @ self.F.T + self.Q

            # Smoother gain
            C = filtered_covs[t] @ self.F.T @ linalg.inv(P_pred)

            # Smoothed estimate
            smoothed_states[t] = filtered_states[t] + C @ (smoothed_states[t+1] - x_pred)

        return smoothed_states


class DynamicFactorModel:
    """
    Dynamic Factor Model for mixed-frequency nowcasting
    Extracts latent factors from monthly indicators to nowcast quarterly GDP
    """

    def __init__(self, config: DFMConfig = None):
        self.config = config or DFMConfig()
        self.is_fitted = False

        # Model parameters
        self.loadings = None  # Λ: factor loadings
        self.transition = None  # A: state transition
        self.means = None
        self.stds = None
        self.scaler = StandardScaler()

        # Noise covariances
        self.Q = None  # Process noise
        self.R = None  # Observation noise

        # Bridge equation parameters
        self.bridge_coef = None
        self.bridge_intercept = None

    def fit(self, X_monthly: pd.DataFrame, y_quarterly: pd.Series,
            publication_lags: Dict[str, int] = None) -> 'DynamicFactorModel':
        """
        Fit DFM using EM algorithm

        Args:
            X_monthly: Monthly indicators (T_monthly x N_vars)
            y_quarterly: Quarterly GDP growth (T_quarterly x 1)
            publication_lags: Dict of publication delays per indicator
        """
        logger.info(f"Fitting DFM with {self.config.n_factors} factors")

        # Standardize monthly data
        X_std = self.scaler.fit_transform(X_monthly.fillna(method='ffill'))
        self.means = self.scaler.mean_
        self.stds = self.scaler.scale_

        # Initialize with PCA
        pca = PCA(n_components=self.config.n_factors)
        factors_init = pca.fit_transform(X_std)
        self.loadings = pca.components_.T

        # Check variance explained
        var_explained = np.sum(pca.explained_variance_ratio_)
        if var_explained < self.config.min_variance_explained:
            logger.warning(f"Only {var_explained:.1%} variance explained by {self.config.n_factors} factors")
        else:
            logger.info(f"{var_explained:.1%} variance explained by factors")

        # Initialize state transition (VAR(1) on factors)
        self.transition = self._estimate_var(factors_init, lags=self.config.n_lags)

        # Initialize noise covariances
        n_vars = X_monthly.shape[1]
        n_factors = self.config.n_factors

        self.Q = np.eye(n_factors) * 0.1  # Process noise
        self.R = np.eye(n_vars) * 0.5  # Observation noise

        # EM algorithm
        for iter in range(self.config.em_max_iter):
            # E-step: Extract factors using Kalman filter/smoother
            kalman = KalmanFilter(
                F=self.transition,
                H=self.loadings,
                Q=self.Q,
                R=self.R
            )

            factors_smooth = kalman.smooth(X_std)

            # M-step: Update parameters
            old_loadings = self.loadings.copy()

            # Update loadings
            self.loadings = self._update_loadings(X_std, factors_smooth)

            # Update transition matrix
            self.transition = self._estimate_var(factors_smooth, lags=self.config.n_lags)

            # Update noise covariances
            self.Q = self._estimate_process_noise(factors_smooth, self.transition)
            self.R = self._estimate_obs_noise(X_std, factors_smooth, self.loadings)

            # Check convergence
            loading_change = np.mean(np.abs(self.loadings - old_loadings))
            if loading_change < self.config.em_tol:
                logger.info(f"EM converged after {iter+1} iterations")
                break

        # Fit bridge equation: GDP_q = β*F_q + u
        self._fit_bridge_equation(factors_smooth, y_quarterly, X_monthly.index)

        self.is_fitted = True
        return self

    def _estimate_var(self, factors: np.ndarray, lags: int = 1) -> np.ndarray:
        """Estimate VAR(p) model on factors"""
        T = factors.shape[0]
        n_factors = factors.shape[1]

        # Construct lagged matrix
        Y = factors[lags:]
        X = np.hstack([factors[lags-i:-i] for i in range(1, lags+1)])

        # OLS estimation
        A = linalg.lstsq(X, Y)[0].T

        # Reshape for state space form
        if lags > 1:
            # Companion form for higher order VAR
            A_companion = np.zeros((n_factors * lags, n_factors * lags))
            A_companion[:n_factors] = A.reshape(n_factors, -1)
            A_companion[n_factors:, :n_factors*(lags-1)] = np.eye(n_factors*(lags-1))
            return A_companion
        else:
            return A

    def _update_loadings(self, X: np.ndarray, factors: np.ndarray) -> np.ndarray:
        """Update factor loadings using OLS"""
        # Λ = (X'F)(F'F)^{-1}
        return X.T @ factors @ linalg.inv(factors.T @ factors)

    def _estimate_process_noise(self, factors: np.ndarray, A: np.ndarray) -> np.ndarray:
        """Estimate process noise covariance"""
        T = factors.shape[0]
        innovations = factors[1:] - factors[:-1] @ A.T
        return np.cov(innovations.T)

    def _estimate_obs_noise(self, X: np.ndarray, factors: np.ndarray,
                           loadings: np.ndarray) -> np.ndarray:
        """Estimate observation noise covariance"""
        residuals = X - factors @ loadings.T
        return np.diag(np.var(residuals, axis=0))

    def _fit_bridge_equation(self, factors: np.ndarray, gdp: pd.Series,
                            monthly_dates: pd.DatetimeIndex):
        """
        Fit bridge equation mapping monthly factors to quarterly GDP
        Handles temporal aggregation
        """
        # Aggregate monthly factors to quarterly
        factors_df = pd.DataFrame(factors, index=monthly_dates)
        factors_quarterly = factors_df.resample('Q').mean()

        # Align with GDP data
        common_dates = factors_quarterly.index.intersection(gdp.index)

        if len(common_dates) < 10:
            logger.warning(f"Only {len(common_dates)} observations for bridge equation")

        X_bridge = factors_quarterly.loc[common_dates].values
        y_bridge = gdp.loc[common_dates].values

        # Add intercept
        X_bridge_with_intercept = np.column_stack([np.ones(len(X_bridge)), X_bridge])

        # OLS for bridge equation
        params = linalg.lstsq(X_bridge_with_intercept, y_bridge)[0]

        self.bridge_intercept = params[0]
        self.bridge_coef = params[1:]

        # Calculate bridge equation R²
        y_pred = X_bridge_with_intercept @ params
        ss_res = np.sum((y_bridge - y_pred) ** 2)
        ss_tot = np.sum((y_bridge - np.mean(y_bridge)) ** 2)
        r2 = 1 - (ss_res / ss_tot)

        logger.info(f"Bridge equation R²: {r2:.3f}")

    def nowcast(self, X_current: pd.DataFrame,
                publication_calendar: Dict[str, datetime] = None) -> Dict:
        """
        Generate GDP nowcast from current monthly indicators
        Handles ragged edges from publication delays

        Returns:
            Dict with nowcast, confidence interval, and factor decomposition
        """
        if not self.is_fitted:
            raise ValueError("Model must be fitted before nowcasting")

        # Handle missing/delayed data
        X_filled = self._handle_ragged_edge(X_current, publication_calendar)

        # Standardize
        X_std = self.scaler.transform(X_filled)

        # Extract factors using Kalman filter
        kalman = KalmanFilter(
            F=self.transition,
            H=self.loadings,
            Q=self.Q,
            R=self.R
        )

        factors, factor_variance = kalman.filter(X_std)

        # Get current quarter factors (average last 3 months)
        if len(factors) >= 3:
            current_q_factors = np.mean(factors[-3:], axis=0)
            factor_uncertainty = np.mean(factor_variance[-3:], axis=0)
        else:
            current_q_factors = factors[-1]
            factor_uncertainty = factor_variance[-1]

        # Apply bridge equation
        gdp_nowcast = self.bridge_intercept + current_q_factors @ self.bridge_coef

        # Uncertainty quantification
        # Propagate factor uncertainty through bridge equation
        gdp_variance = self.bridge_coef @ factor_uncertainty @ self.bridge_coef.T
        gdp_std = np.sqrt(gdp_variance)

        # Confidence intervals
        ci_lower = gdp_nowcast - 1.645 * gdp_std  # 90% CI
        ci_upper = gdp_nowcast + 1.645 * gdp_std

        # Factor contributions
        factor_contributions = {}
        for i, coef in enumerate(self.bridge_coef):
            factor_contributions[f'factor_{i+1}'] = coef * current_q_factors[i]

        return {
            'nowcast': float(gdp_nowcast),
            'ci_lower': float(ci_lower),
            'ci_upper': float(ci_upper),
            'uncertainty': float(gdp_std),
            'factors': current_q_factors.tolist(),
            'factor_contributions': factor_contributions,
            'n_obs': len(X_current),
            'missing_pct': X_current.isna().mean().mean()
        }

    def _handle_ragged_edge(self, X: pd.DataFrame,
                           publication_calendar: Dict = None) -> pd.DataFrame:
        """
        Handle missing data from publication delays
        Uses AR forecasts for missing recent values
        """
        X_filled = X.copy()

        for col in X.columns:
            if X[col].isna().any():
                # Get last valid index
                last_valid = X[col].last_valid_index()

                if last_valid is not None:
                    # Simple AR(1) forecast for missing values
                    last_value = X[col].loc[last_valid]

                    # Estimate AR coefficient from available data
                    valid_data = X[col].dropna()
                    if len(valid_data) > 2:
                        ar_coef = np.corrcoef(valid_data[:-1], valid_data[1:])[0, 1]

                        # Fill forward with AR forecast
                        for idx in X[col][last_valid:].index[1:]:
                            if pd.isna(X_filled.loc[idx, col]):
                                X_filled.loc[idx, col] = last_value * ar_coef
                                last_value = X_filled.loc[idx, col]
                    else:
                        # Simple forward fill if not enough data
                        X_filled[col].fillna(method='ffill', inplace=True)

        return X_filled

    def get_feature_importance(self) -> pd.DataFrame:
        """
        Calculate feature importance based on factor loadings
        """
        if self.loadings is None:
            raise ValueError("Model must be fitted first")

        # Calculate variance contribution of each variable to factors
        importance = np.abs(self.loadings).mean(axis=1)
        importance = importance / importance.sum()

        return pd.DataFrame({
            'importance': importance
        }, index=range(len(importance)))


def create_dfm_nowcaster(country: str) -> DynamicFactorModel:
    """
    Factory function to create country-specific DFM nowcaster
    """
    # Country-specific configurations
    configs = {
        'USA': DFMConfig(n_factors=3, n_lags=1),
        'GBR': DFMConfig(n_factors=2, n_lags=2),  # More lags for Brexit dynamics
        'JPN': DFMConfig(n_factors=2, n_lags=1),
        'DEU': DFMConfig(n_factors=3, n_lags=1),
        'FRA': DFMConfig(n_factors=2, n_lags=1),
        'default': DFMConfig(n_factors=2, n_lags=1)
    }

    config = configs.get(country, configs['default'])
    return DynamicFactorModel(config)


# Example usage and testing
if __name__ == "__main__":
    print("Dynamic Factor Model for GDP Nowcasting")
    print("=" * 60)

    # Generate synthetic test data
    np.random.seed(42)

    # Monthly indicators
    T_monthly = 120
    n_vars = 6
    dates_monthly = pd.date_range('2014-01-01', periods=T_monthly, freq='M')

    # Generate correlated monthly indicators
    true_factors = np.random.randn(T_monthly, 2)
    true_factors[:, 0] = np.cumsum(np.random.randn(T_monthly) * 0.1)  # Trend
    true_factors[:, 1] = np.sin(np.arange(T_monthly) * 2 * np.pi / 12)  # Seasonal

    loadings = np.random.randn(n_vars, 2)
    X_monthly = pd.DataFrame(
        true_factors @ loadings.T + np.random.randn(T_monthly, n_vars) * 0.5,
        index=dates_monthly,
        columns=[f'indicator_{i}' for i in range(n_vars)]
    )

    # Quarterly GDP (correlated with factors)
    dates_quarterly = pd.date_range('2014-01-01', periods=T_monthly//3, freq='Q')
    gdp_quarterly = pd.Series(
        true_factors[::3, 0] * 2 + np.random.randn(T_monthly//3) * 0.5,
        index=dates_quarterly
    )

    # Fit model
    dfm = DynamicFactorModel(DFMConfig(n_factors=2))
    dfm.fit(X_monthly, gdp_quarterly)

    # Generate nowcast
    current_data = X_monthly.iloc[-6:]  # Last 6 months
    nowcast = dfm.nowcast(current_data)

    print(f"\nGDP Nowcast: {nowcast['nowcast']:.2f}%")
    print(f"90% CI: [{nowcast['ci_lower']:.2f}, {nowcast['ci_upper']:.2f}]")
    print(f"Uncertainty: {nowcast['uncertainty']:.2f}pp")
    print("\nFactor Contributions:")
    for factor, contrib in nowcast['factor_contributions'].items():
        print(f"  {factor}: {contrib:+.2f}pp")