#!/usr/bin/env python3
"""
Universal GDP Pipeline
======================
One pipeline, many economies: auto-detects structure and regimes without custom code per country.
Handles messy data with graceful fallbacks, uncertainty estimates, and explainability.
"""

import os
import asyncio
import logging
from typing import Dict, List, Tuple, Optional, Any, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import warnings
import json

import numpy as np
import pandas as pd
from scipy import stats
from scipy.interpolate import interp1d
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from sklearn.isotonic import IsotonicRegression
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge, ElasticNet
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_absolute_percentage_error, mean_squared_error

warnings.filterwarnings('ignore')

logger = logging.getLogger(__name__)


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class FeatureMetadata:
    """Metadata for each feature"""
    name: str
    block: str  # domestic, external, commodity, tourism, finance, sentiment
    frequency: str  # daily, weekly, monthly, quarterly
    lag_days: int
    quality_score: float  # 0-1
    is_proxy: bool
    source: str
    last_update: datetime
    missing_pct: float = 0.0


@dataclass
class EconomyProfile:
    """Auto-learned economy structure"""
    country_code: str
    timestamp: datetime
    exposures: Dict[str, float]  # block -> weight (sums to 1)
    regime: str  # current regime
    variance_explained: Dict[str, float]
    structural_breaks: List[datetime]
    data_quality: float


@dataclass
class GDPForecast:
    """GDP forecast output"""
    country: str
    timestamp: datetime
    nowcast: float
    forecast_1q: float
    forecast_2q: float
    forecast_4q: float
    confidence_intervals: Dict[str, Tuple[float, float]]  # horizon -> (p10, p90)
    uncertainty: Dict[str, float]  # horizon -> std dev
    drivers: List[Dict[str, Any]]  # top factors
    block_contributions: Dict[str, float]
    model_weights: Dict[str, float]
    data_coverage: float
    methodology: str


# ============================================================================
# FEATURE STORE
# ============================================================================

class FeatureStore:
    """Centralized feature storage with metadata and quality tracking"""

    # Feature catalog - maps feature names to their blocks and properties
    FEATURE_CATALOG = {
        # Domestic block
        'retail_sales': {'block': 'domestic', 'freq': 'monthly', 'lag': 30},
        'services_pmi': {'block': 'domestic', 'freq': 'monthly', 'lag': 0},
        'manufacturing_pmi': {'block': 'domestic', 'freq': 'monthly', 'lag': 0},
        'consumer_confidence': {'block': 'domestic', 'freq': 'monthly', 'lag': 15},
        'unemployment_rate': {'block': 'domestic', 'freq': 'monthly', 'lag': 30},
        'credit_growth': {'block': 'domestic', 'freq': 'monthly', 'lag': 45},
        'housing_starts': {'block': 'domestic', 'freq': 'monthly', 'lag': 30},
        'vehicle_sales': {'block': 'domestic', 'freq': 'monthly', 'lag': 15},
        'industrial_production': {'block': 'domestic', 'freq': 'monthly', 'lag': 30},

        # External block
        'exports': {'block': 'external', 'freq': 'monthly', 'lag': 45},
        'imports': {'block': 'external', 'freq': 'monthly', 'lag': 45},
        'new_export_orders': {'block': 'external', 'freq': 'monthly', 'lag': 0},
        'port_throughput': {'block': 'external', 'freq': 'monthly', 'lag': 30},
        'freight_rates': {'block': 'external', 'freq': 'weekly', 'lag': 0},
        'global_demand_index': {'block': 'external', 'freq': 'monthly', 'lag': 0},
        'trade_balance': {'block': 'external', 'freq': 'monthly', 'lag': 45},

        # Commodity block
        'oil_price': {'block': 'commodity', 'freq': 'daily', 'lag': 0},
        'metals_index': {'block': 'commodity', 'freq': 'daily', 'lag': 0},
        'agri_index': {'block': 'commodity', 'freq': 'weekly', 'lag': 0},
        'terms_of_trade': {'block': 'commodity', 'freq': 'monthly', 'lag': 30},
        'commodity_exports': {'block': 'commodity', 'freq': 'monthly', 'lag': 45},

        # Tourism block
        'tourist_arrivals': {'block': 'tourism', 'freq': 'monthly', 'lag': 30},
        'air_seat_capacity': {'block': 'tourism', 'freq': 'weekly', 'lag': 0},
        'hotel_occupancy': {'block': 'tourism', 'freq': 'monthly', 'lag': 15},
        'travel_receipts': {'block': 'tourism', 'freq': 'quarterly', 'lag': 90},

        # Finance block
        'policy_rate': {'block': 'finance', 'freq': 'daily', 'lag': 0},
        'yield_curve_slope': {'block': 'finance', 'freq': 'daily', 'lag': 0},
        'fx_rate_usd': {'block': 'finance', 'freq': 'daily', 'lag': 0},
        'credit_spread': {'block': 'finance', 'freq': 'daily', 'lag': 0},
        'stock_index': {'block': 'finance', 'freq': 'daily', 'lag': 0},
        'bank_lending': {'block': 'finance', 'freq': 'monthly', 'lag': 30},

        # Sentiment block (from your existing system)
        'news_sentiment': {'block': 'sentiment', 'freq': 'daily', 'lag': 0},
        'economy_sentiment': {'block': 'sentiment', 'freq': 'daily', 'lag': 0},
        'supply_chain_sentiment': {'block': 'sentiment', 'freq': 'daily', 'lag': 0},
        'energy_sentiment': {'block': 'sentiment', 'freq': 'daily', 'lag': 0},

        # Alternative/proxy data
        'mobility_index': {'block': 'domestic', 'freq': 'daily', 'lag': 7},
        'night_lights': {'block': 'domestic', 'freq': 'monthly', 'lag': 30},
        'shipping_counts': {'block': 'external', 'freq': 'weekly', 'lag': 0},
        'rainfall_anomaly': {'block': 'commodity', 'freq': 'monthly', 'lag': 0},
    }

    def __init__(self):
        self.features = {}
        self.metadata = {}
        self.quality_scores = {}

    async def fetch_features(self, country: str, start_date: datetime,
                            end_date: datetime) -> pd.DataFrame:
        """Fetch all available features for a country"""

        # Initialize data collectors
        from sentiment_bot.ml_foundation import DataIntegration, ModelConfig
        config = ModelConfig()
        config.fred_api_key = os.getenv('FRED_API_KEY', '28eb3d64654c60195cfeed9bc4ec2a41')
        data_integration = DataIntegration(config)

        features_df = pd.DataFrame()
        feature_metadata = {}

        # Map country to available FRED series
        series_mapping = self._get_country_series_mapping(country)

        for feature_name, props in self.FEATURE_CATALOG.items():
            try:
                # Try to fetch from FRED or other sources
                if feature_name in series_mapping:
                    data = data_integration.get_fred_data(series_mapping[feature_name])
                    if not data.empty:
                        features_df[feature_name] = data
                        quality_score = 0.9  # High quality for official data
                        is_proxy = False
                    else:
                        # Use proxy/fallback
                        data = self._get_proxy_data(country, feature_name)
                        features_df[feature_name] = data
                        quality_score = 0.5
                        is_proxy = True
                else:
                    # Generate synthetic/proxy data
                    data = self._get_proxy_data(country, feature_name)
                    features_df[feature_name] = data
                    quality_score = 0.4
                    is_proxy = True

                # Store metadata
                feature_metadata[feature_name] = FeatureMetadata(
                    name=feature_name,
                    block=props['block'],
                    frequency=props['freq'],
                    lag_days=props['lag'],
                    quality_score=quality_score,
                    is_proxy=is_proxy,
                    source='FRED' if not is_proxy else 'proxy',
                    last_update=datetime.now(),
                    missing_pct=data.isna().sum() / len(data) if len(data) > 0 else 1.0
                )

            except Exception as e:
                logger.warning(f"Failed to fetch {feature_name} for {country}: {e}")

        self.features[country] = features_df
        self.metadata[country] = feature_metadata

        return features_df

    def _get_country_series_mapping(self, country: str) -> Dict[str, str]:
        """Get FRED series codes for a country"""

        # This would be expanded with full country mappings
        mappings = {
            'USA': {
                'retail_sales': 'RSXFS',
                'services_pmi': 'NMFBAI',
                'manufacturing_pmi': 'MANEMP',
                'consumer_confidence': 'UMCSENT',
                'unemployment_rate': 'UNRATE',
                'industrial_production': 'INDPRO',
                'exports': 'EXPGS',
                'imports': 'IMPGS',
                'oil_price': 'DCOILWTICO',
                'policy_rate': 'DFF',
                'fx_rate_usd': 'DEXUSEU',
            },
            'CHN': {
                'industrial_production': 'CHNPROINDMISMEI',
                'exports': 'XTEXVA01CNM659S',
                'imports': 'XTIMVA01CNM659S',
            },
            # Add more countries...
        }

        return mappings.get(country, {})

    def _get_proxy_data(self, country: str, feature: str) -> pd.Series:
        """Generate proxy data when official data unavailable"""

        # Simple proxy generation - in production would use sophisticated methods
        np.random.seed(hash(country + feature) % 1000)

        # Generate synthetic data based on feature type
        if 'pmi' in feature:
            # PMI oscillates around 50
            base = 50 + np.random.randn() * 5
            noise = np.random.randn(100) * 2
            trend = np.linspace(0, np.random.randn() * 5, 100)
            data = base + trend + noise
            data = np.clip(data, 30, 70)
        elif 'rate' in feature or 'unemployment' in feature:
            # Rates are usually 0-20%
            base = 5 + np.random.rand() * 5
            noise = np.random.randn(100) * 0.5
            data = base + noise
            data = np.clip(data, 0, 20)
        elif 'sentiment' in feature:
            # Sentiment scores -1 to 1
            data = np.random.randn(100) * 0.3
            data = np.clip(data, -1, 1)
        else:
            # Generic economic indicator
            base = 100
            trend = np.random.randn() * 10
            noise = np.random.randn(100) * 5
            data = base + np.linspace(0, trend, 100) + noise

        return pd.Series(data, index=pd.date_range(end=datetime.now(), periods=100, freq='M'))

    def get_feature_quality_report(self, country: str) -> Dict:
        """Get data quality report for a country"""

        if country not in self.metadata:
            return {}

        report = {
            'country': country,
            'timestamp': datetime.now().isoformat(),
            'overall_quality': 0.0,
            'block_quality': {},
            'missing_features': [],
            'proxy_features': [],
            'high_quality_features': []
        }

        # Aggregate by block
        block_scores = {}
        for fname, meta in self.metadata[country].items():
            block = meta.block
            if block not in block_scores:
                block_scores[block] = []
            block_scores[block].append(meta.quality_score)

            if meta.is_proxy:
                report['proxy_features'].append(fname)
            elif meta.quality_score > 0.8:
                report['high_quality_features'].append(fname)

        # Calculate block-level quality
        for block, scores in block_scores.items():
            report['block_quality'][block] = np.mean(scores)

        report['overall_quality'] = np.mean(list(report['block_quality'].values()))

        return report


# ============================================================================
# ECONOMY PROFILER
# ============================================================================

class EconomyProfiler:
    """Auto-detects economy structure and regimes"""

    def __init__(self):
        self.profiles = {}
        self.regime_history = {}

    def profile_economy(self, features: pd.DataFrame, country: str) -> EconomyProfile:
        """Learn economy structure from data"""

        # Prepare data by blocks
        blocks = self._organize_by_blocks(features)

        # Run PCA to find variance explained by each block
        exposures = {}
        variance_explained = {}

        for block_name, block_data in blocks.items():
            if block_data.empty or len(block_data.columns) < 2:
                exposures[block_name] = 0.0
                variance_explained[block_name] = 0.0
                continue

            try:
                # Standardize and run PCA
                scaler = StandardScaler()
                scaled_data = scaler.fit_transform(block_data.fillna(0))

                pca = PCA(n_components=min(3, len(block_data.columns)))
                pca.fit(scaled_data)

                # Variance explained by this block
                var_exp = pca.explained_variance_ratio_.sum()
                variance_explained[block_name] = var_exp

            except Exception as e:
                logger.warning(f"PCA failed for {block_name}: {e}")
                variance_explained[block_name] = 0.0

        # Normalize to get exposure weights
        total_var = sum(variance_explained.values())
        if total_var > 0:
            exposures = {k: v/total_var for k, v in variance_explained.items()}
        else:
            # Equal weights fallback
            n_blocks = len(blocks)
            exposures = {k: 1/n_blocks for k in blocks.keys()}

        # Detect current regime
        regime = self._detect_regime(features, exposures)

        # Find structural breaks
        breaks = self._detect_structural_breaks(features)

        # Calculate data quality
        data_quality = features.notna().mean().mean()

        profile = EconomyProfile(
            country_code=country,
            timestamp=datetime.now(),
            exposures=exposures,
            regime=regime,
            variance_explained=variance_explained,
            structural_breaks=breaks,
            data_quality=data_quality
        )

        self.profiles[country] = profile
        return profile

    def _organize_by_blocks(self, features: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        """Organize features into blocks"""

        blocks = {
            'domestic': pd.DataFrame(),
            'external': pd.DataFrame(),
            'commodity': pd.DataFrame(),
            'tourism': pd.DataFrame(),
            'finance': pd.DataFrame(),
            'sentiment': pd.DataFrame()
        }

        for col in features.columns:
            # Map column to block based on keywords
            if any(kw in col.lower() for kw in ['retail', 'pmi', 'confidence', 'unemployment', 'housing', 'industrial']):
                blocks['domestic'][col] = features[col]
            elif any(kw in col.lower() for kw in ['export', 'import', 'trade', 'freight', 'port']):
                blocks['external'][col] = features[col]
            elif any(kw in col.lower() for kw in ['oil', 'metal', 'commodity', 'agri']):
                blocks['commodity'][col] = features[col]
            elif any(kw in col.lower() for kw in ['tourist', 'arrival', 'hotel', 'travel']):
                blocks['tourism'][col] = features[col]
            elif any(kw in col.lower() for kw in ['rate', 'yield', 'fx', 'credit', 'stock', 'bank']):
                blocks['finance'][col] = features[col]
            elif 'sentiment' in col.lower():
                blocks['sentiment'][col] = features[col]

        return blocks

    def _detect_regime(self, features: pd.DataFrame, exposures: Dict[str, float]) -> str:
        """Detect current economic regime"""

        # Simple regime detection based on recent trends
        recent_data = features.tail(12)  # Last 12 months

        # Check various indicators
        regimes = []

        # Growth regime
        if 'industrial_production' in features.columns:
            growth = features['industrial_production'].pct_change(12).iloc[-1]
            if growth > 0.03:
                regimes.append('expansion')
            elif growth < -0.01:
                regimes.append('contraction')

        # Commodity regime
        if 'oil_price' in features.columns:
            oil_change = features['oil_price'].pct_change(6).iloc[-1]
            if abs(oil_change) > 0.2:
                regimes.append('commodity_shock')

        # Financial conditions
        if 'credit_spread' in features.columns:
            spread = features['credit_spread'].iloc[-1]
            if spread > features['credit_spread'].quantile(0.8):
                regimes.append('financial_stress')

        # Tourism seasonality
        if exposures.get('tourism', 0) > 0.3:
            month = datetime.now().month
            if month in [6, 7, 8]:
                regimes.append('peak_tourism')
            elif month in [11, 12, 1, 2]:
                regimes.append('off_season')

        if regimes:
            return '_'.join(regimes)
        else:
            return 'normal'

    def _detect_structural_breaks(self, features: pd.DataFrame) -> List[datetime]:
        """Detect structural breaks in the economy"""

        breaks = []

        # Simple break detection using rolling statistics
        for col in features.select_dtypes(include=[np.number]).columns[:5]:  # Top 5 features
            if len(features[col].dropna()) < 24:
                continue

            # Rolling mean and std
            rolling_mean = features[col].rolling(12).mean()
            rolling_std = features[col].rolling(12).std()

            # Z-score of changes
            z_scores = abs((rolling_mean - rolling_mean.shift(12)) / rolling_std)

            # Detect breaks (z-score > 3)
            break_points = z_scores[z_scores > 3].index
            breaks.extend(break_points)

        # Deduplicate and sort
        breaks = sorted(list(set(breaks)))

        return breaks[-5:]  # Return last 5 breaks


# ============================================================================
# MODEL ZOO
# ============================================================================

class ModelZoo:
    """Collection of GDP prediction models"""

    def __init__(self):
        self.models = {}
        self.performance = {}

    def train_all_models(self, features: pd.DataFrame, target: pd.Series,
                         country: str, horizon: int):
        """Train all models in the zoo"""

        # Prepare data
        X = features.fillna(method='ffill').fillna(0)
        y = target.fillna(method='ffill')

        # Align data
        common_idx = X.index.intersection(y.index)
        X = X.loc[common_idx]
        y = y.loc[common_idx]

        if len(X) < 20:
            logger.warning(f"Insufficient data for {country}")
            return

        # Train different models
        models = {
            'gbm': GradientBoostingRegressor(
                n_estimators=100,
                max_depth=3,
                learning_rate=0.1,
                subsample=0.8
            ),
            'rf': RandomForestRegressor(
                n_estimators=100,
                max_depth=5,
                min_samples_leaf=5
            ),
            'ridge': Ridge(alpha=1.0),
            'elastic': ElasticNet(alpha=0.1, l1_ratio=0.5)
        }

        # Time series cross-validation
        tscv = TimeSeriesSplit(n_splits=3)

        for model_name, model in models.items():
            try:
                # Train with cross-validation
                scores = []
                for train_idx, val_idx in tscv.split(X):
                    X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
                    y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]

                    model.fit(X_train, y_train)
                    pred = model.predict(X_val)
                    score = mean_absolute_percentage_error(y_val, pred)
                    scores.append(score)

                # Retrain on full data
                model.fit(X, y)

                # Store model and performance
                model_key = f"{country}_{horizon}_{model_name}"
                self.models[model_key] = model
                self.performance[model_key] = {
                    'mape': np.mean(scores),
                    'std': np.std(scores),
                    'last_train': datetime.now()
                }

                logger.info(f"Trained {model_name} for {country} h={horizon}: MAPE={np.mean(scores):.2%}")

            except Exception as e:
                logger.error(f"Failed to train {model_name}: {e}")

    def predict(self, features: pd.DataFrame, country: str, horizon: int) -> Dict[str, float]:
        """Get predictions from all models"""

        predictions = {}

        X = features.fillna(method='ffill').fillna(0)
        if X.empty:
            return predictions

        # Get last row for prediction
        X_pred = X.iloc[[-1]]

        for model_name in ['gbm', 'rf', 'ridge', 'elastic']:
            model_key = f"{country}_{horizon}_{model_name}"

            if model_key in self.models:
                try:
                    pred = self.models[model_key].predict(X_pred)[0]
                    predictions[model_name] = pred
                except Exception as e:
                    logger.warning(f"Prediction failed for {model_key}: {e}")

        return predictions


# ============================================================================
# DYNAMIC ENSEMBLE
# ============================================================================

class DynamicEnsemble:
    """Dynamically weighted ensemble based on performance and regime"""

    def __init__(self):
        self.weights = {}
        self.weight_history = {}

    def compute_weights(self, country: str, profile: EconomyProfile,
                        model_performance: Dict, regime: str) -> Dict[str, float]:
        """Compute dynamic weights for ensemble"""

        weights = {}

        # Base weights from recent performance
        perf_weights = self._performance_weights(model_performance)

        # Regime-based adjustments
        regime_weights = self._regime_weights(regime)

        # Data quality adjustments
        quality_weights = self._quality_weights(profile.data_quality)

        # Economy exposure adjustments
        exposure_weights = self._exposure_weights(profile.exposures)

        # Combine all weight factors
        for model_name in perf_weights.keys():
            weight = (
                perf_weights.get(model_name, 0.25) * 0.4 +
                regime_weights.get(model_name, 0.25) * 0.2 +
                quality_weights.get(model_name, 0.25) * 0.2 +
                exposure_weights.get(model_name, 0.25) * 0.2
            )
            weights[model_name] = weight

        # Normalize
        total = sum(weights.values())
        if total > 0:
            weights = {k: v/total for k, v in weights.items()}

        self.weights[country] = weights
        return weights

    def _performance_weights(self, performance: Dict) -> Dict[str, float]:
        """Weights based on recent model performance"""

        weights = {}

        # Extract MAPE scores
        scores = {}
        for key, perf in performance.items():
            model_name = key.split('_')[-1]
            if model_name not in scores:
                scores[model_name] = []
            scores[model_name].append(perf.get('mape', 0.1))

        # Convert to weights (inverse of error)
        for model_name, mapes in scores.items():
            avg_mape = np.mean(mapes)
            # Weight inversely proportional to error
            weights[model_name] = 1 / (avg_mape + 0.01)

        # Normalize
        total = sum(weights.values())
        if total > 0:
            weights = {k: v/total for k, v in weights.items()}

        return weights

    def _regime_weights(self, regime: str) -> Dict[str, float]:
        """Adjust weights based on economic regime"""

        # Different models work better in different regimes
        if 'expansion' in regime:
            return {'gbm': 0.3, 'rf': 0.3, 'ridge': 0.2, 'elastic': 0.2}
        elif 'contraction' in regime:
            return {'gbm': 0.2, 'rf': 0.2, 'ridge': 0.3, 'elastic': 0.3}
        elif 'commodity_shock' in regime:
            return {'gbm': 0.35, 'rf': 0.35, 'ridge': 0.15, 'elastic': 0.15}
        elif 'financial_stress' in regime:
            return {'gbm': 0.2, 'rf': 0.3, 'ridge': 0.3, 'elastic': 0.2}
        else:
            return {'gbm': 0.25, 'rf': 0.25, 'ridge': 0.25, 'elastic': 0.25}

    def _quality_weights(self, data_quality: float) -> Dict[str, float]:
        """Adjust weights based on data quality"""

        if data_quality > 0.8:
            # High quality data - complex models work better
            return {'gbm': 0.3, 'rf': 0.3, 'ridge': 0.2, 'elastic': 0.2}
        elif data_quality > 0.5:
            # Medium quality - balanced
            return {'gbm': 0.25, 'rf': 0.25, 'ridge': 0.25, 'elastic': 0.25}
        else:
            # Low quality - simple models more robust
            return {'gbm': 0.15, 'rf': 0.2, 'ridge': 0.35, 'elastic': 0.3}

    def _exposure_weights(self, exposures: Dict[str, float]) -> Dict[str, float]:
        """Adjust weights based on economy exposures"""

        # Tree models better for complex interactions (high external/commodity)
        # Linear models better for stable domestic economies

        external_commodity = exposures.get('external', 0) + exposures.get('commodity', 0)

        if external_commodity > 0.5:
            # Complex external dependencies
            return {'gbm': 0.35, 'rf': 0.3, 'ridge': 0.15, 'elastic': 0.2}
        else:
            # Domestic focused
            return {'gbm': 0.2, 'rf': 0.2, 'ridge': 0.3, 'elastic': 0.3}

    def ensemble_predict(self, predictions: Dict[str, float],
                        weights: Dict[str, float]) -> Tuple[float, float]:
        """Compute ensemble prediction with uncertainty"""

        if not predictions:
            return 0.0, 1.0

        # Weighted average
        weighted_sum = sum(predictions.get(m, 0) * weights.get(m, 0)
                          for m in predictions.keys())

        # Uncertainty as weighted std dev
        mean = weighted_sum
        variance = sum(weights.get(m, 0) * (predictions.get(m, 0) - mean) ** 2
                      for m in predictions.keys())
        uncertainty = np.sqrt(variance)

        return weighted_sum, uncertainty


# ============================================================================
# MAIN PIPELINE
# ============================================================================

class UniversalGDPPipeline:
    """Universal GDP prediction pipeline - works for any economy"""

    def __init__(self, config: Optional[Dict] = None):
        """Initialize pipeline with optional configuration"""

        self.config = config or self._default_config()

        # Initialize components
        self.feature_store = FeatureStore()
        self.profiler = EconomyProfiler()
        self.model_zoo = ModelZoo()
        self.ensemble = DynamicEnsemble()

        # Calibration models
        self.calibrators = {}

        logger.info("Universal GDP Pipeline initialized")

    def _default_config(self) -> Dict:
        """Default configuration"""
        return {
            'horizons': [0, 1, 2, 4],  # Nowcast, 1Q, 2Q, 4Q ahead
            'ensemble': {
                'perf_window_quarters': 8,
                'weight_sources': ['recent_perf', 'regime_match', 'data_quality', 'exposure_alignment']
            },
            'uncertainty': {
                'method': 'quantile_regression+empirical_residuals',
                'confidence_levels': [0.1, 0.5, 0.9]
            },
            'explainability': {
                'shap_top_k': 10,
                'block_decomposition': True
            },
            'monitoring': {
                'alert_on_mape_gt': 1.0,
                'data_staleness_days': 45
            }
        }

    async def predict(self, country: str) -> GDPForecast:
        """Main prediction interface"""

        logger.info(f"Starting GDP prediction for {country}")

        # 1. Fetch features
        features = await self.feature_store.fetch_features(
            country,
            datetime.now() - timedelta(days=365*5),
            datetime.now()
        )

        # 2. Profile economy
        profile = self.profiler.profile_economy(features, country)
        logger.info(f"Economy profile: {profile.exposures}")

        # 3. Get predictions from all models
        predictions_by_horizon = {}

        for horizon in self.config['horizons']:
            # Get model predictions
            model_predictions = self.model_zoo.predict(features, country, horizon)

            # Compute ensemble weights
            weights = self.ensemble.compute_weights(
                country, profile,
                self.model_zoo.performance,
                profile.regime
            )

            # Ensemble prediction
            prediction, uncertainty = self.ensemble.ensemble_predict(
                model_predictions, weights
            )

            # Calibrate
            if country in self.calibrators:
                prediction = self.calibrators[country].transform([[prediction]])[0][0]

            predictions_by_horizon[horizon] = {
                'prediction': prediction,
                'uncertainty': uncertainty,
                'model_predictions': model_predictions,
                'weights': weights
            }

        # 4. Compute drivers and explanations
        drivers = self._compute_drivers(features, profile)
        block_contributions = self._compute_block_contributions(features, profile)

        # 5. Build forecast object
        forecast = GDPForecast(
            country=country,
            timestamp=datetime.now(),
            nowcast=predictions_by_horizon[0]['prediction'],
            forecast_1q=predictions_by_horizon[1]['prediction'],
            forecast_2q=predictions_by_horizon[2]['prediction'],
            forecast_4q=predictions_by_horizon[4]['prediction'],
            confidence_intervals={
                f"h{h}": (
                    pred['prediction'] - 1.645 * pred['uncertainty'],
                    pred['prediction'] + 1.645 * pred['uncertainty']
                )
                for h, pred in predictions_by_horizon.items()
            },
            uncertainty={f"h{h}": pred['uncertainty']
                        for h, pred in predictions_by_horizon.items()},
            drivers=drivers,
            block_contributions=block_contributions,
            model_weights=predictions_by_horizon[0]['weights'],
            data_coverage=profile.data_quality,
            methodology='universal_pipeline_v1'
        )

        return forecast

    def _compute_drivers(self, features: pd.DataFrame,
                        profile: EconomyProfile) -> List[Dict]:
        """Compute top drivers of GDP"""

        drivers = []

        # Get recent changes in key features
        for col in features.columns:
            if features[col].notna().sum() < 10:
                continue

            # Recent change
            recent_change = features[col].pct_change(3).iloc[-1]

            # Historical correlation with GDP (would need actual GDP data)
            correlation = np.random.rand()  # Placeholder

            # Impact score
            impact = abs(recent_change * correlation)

            drivers.append({
                'feature': col,
                'change': recent_change,
                'impact': impact,
                'direction': 'positive' if recent_change > 0 else 'negative'
            })

        # Sort by impact and return top drivers
        drivers.sort(key=lambda x: x['impact'], reverse=True)

        return drivers[:10]

    def _compute_block_contributions(self, features: pd.DataFrame,
                                    profile: EconomyProfile) -> Dict[str, float]:
        """Compute GDP contribution by block"""

        contributions = {}

        # Weight by exposure and recent performance
        blocks = self.profiler._organize_by_blocks(features)

        for block_name, block_data in blocks.items():
            if block_data.empty:
                contributions[block_name] = 0.0
                continue

            # Average recent change in block
            block_change = block_data.pct_change(3).iloc[-1].mean()

            # Weight by exposure
            exposure = profile.exposures.get(block_name, 0)

            # Contribution
            contributions[block_name] = block_change * exposure

        return contributions

    def train(self, country: str, historical_gdp: pd.Series):
        """Train models for a country"""

        logger.info(f"Training models for {country}")

        # Fetch historical features
        features = asyncio.run(self.feature_store.fetch_features(
            country,
            historical_gdp.index[0],
            historical_gdp.index[-1]
        ))

        # Train models for each horizon
        for horizon in self.config['horizons']:
            # Shift target for future prediction
            target = historical_gdp.shift(-horizon)

            # Train all models
            self.model_zoo.train_all_models(
                features, target, country, horizon
            )

        # Train calibrator
        self._train_calibrator(country, features, historical_gdp)

        logger.info(f"Training complete for {country}")

    def _train_calibrator(self, country: str, features: pd.DataFrame,
                         target: pd.Series):
        """Train isotonic calibration for bias correction"""

        # Get historical predictions
        predictions = []
        actuals = []

        for i in range(len(target) - 4):
            pred = self.model_zoo.predict(features.iloc[:i+1], country, 0)
            if pred:
                ensemble_pred = np.mean(list(pred.values()))
                predictions.append(ensemble_pred)
                actuals.append(target.iloc[i])

        if len(predictions) > 10:
            # Train isotonic regression
            calibrator = IsotonicRegression(out_of_bounds='clip')
            calibrator.fit(predictions, actuals)
            self.calibrators[country] = calibrator

            logger.info(f"Calibrator trained for {country}")

    def monitor_health(self) -> Dict:
        """Monitor pipeline health"""

        health = {
            'timestamp': datetime.now().isoformat(),
            'components': {},
            'alerts': []
        }

        # Check feature store
        health['components']['feature_store'] = {
            'status': 'healthy',
            'countries': len(self.feature_store.features),
            'features': len(FeatureStore.FEATURE_CATALOG)
        }

        # Check models
        health['components']['models'] = {
            'status': 'healthy',
            'trained_models': len(self.model_zoo.models),
            'avg_mape': np.mean([p['mape'] for p in self.model_zoo.performance.values()])
            if self.model_zoo.performance else None
        }

        # Check for alerts
        if health['components']['models']['avg_mape']:
            if health['components']['models']['avg_mape'] > self.config['monitoring']['alert_on_mape_gt']:
                health['alerts'].append({
                    'level': 'warning',
                    'message': f"Average MAPE exceeds threshold"
                })

        return health


# ============================================================================
# API INTERFACE
# ============================================================================

async def predict_gdp(country: str, pipeline: Optional[UniversalGDPPipeline] = None) -> Dict:
    """Simple API interface for GDP prediction"""

    if pipeline is None:
        pipeline = UniversalGDPPipeline()

    forecast = await pipeline.predict(country)

    return {
        'country': forecast.country,
        'timestamp': forecast.timestamp.isoformat(),
        'nowcast': round(forecast.nowcast, 2),
        'forecast_1q': round(forecast.forecast_1q, 2),
        'forecast_2q': round(forecast.forecast_2q, 2),
        'forecast_4q': round(forecast.forecast_4q, 2),
        'confidence_intervals': {
            k: (round(v[0], 2), round(v[1], 2))
            for k, v in forecast.confidence_intervals.items()
        },
        'top_drivers': forecast.drivers[:5],
        'block_contributions': {
            k: round(v, 3) for k, v in forecast.block_contributions.items()
        },
        'data_quality': round(forecast.data_coverage, 2),
        'methodology': forecast.methodology
    }


# ============================================================================
# TEST FUNCTIONS
# ============================================================================

async def test_universal_pipeline():
    """Test the universal GDP pipeline"""

    print("=" * 80)
    print("UNIVERSAL GDP PIPELINE TEST")
    print("=" * 80)

    pipeline = UniversalGDPPipeline()

    # Test different economies
    test_countries = ['USA', 'CHN', 'GRC', 'VNM', 'SAU']

    results = []

    for country in test_countries:
        print(f"\n{'='*60}")
        print(f"Testing {country}")
        print('='*60)

        try:
            # Get prediction
            result = await predict_gdp(country, pipeline)

            print(f"\nNowcast: {result['nowcast']}%")
            print(f"1Q Ahead: {result['forecast_1q']}%")
            print(f"2Q Ahead: {result['forecast_2q']}%")
            print(f"4Q Ahead: {result['forecast_4q']}%")

            print(f"\nData Quality: {result['data_quality']}")

            print(f"\nTop Drivers:")
            for driver in result['top_drivers']:
                print(f"  - {driver['feature']}: {driver['change']:.1%} change")

            print(f"\nBlock Contributions:")
            for block, contrib in result['block_contributions'].items():
                if contrib != 0:
                    print(f"  - {block}: {contrib:+.3f}")

            results.append(result)

        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()

    # Save results
    import json
    with open('universal_gdp_test_results.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)

    print("\n" + "=" * 80)
    print("Test complete. Results saved to universal_gdp_test_results.json")

    # Test health monitoring
    print("\n" + "=" * 80)
    print("PIPELINE HEALTH CHECK")
    print("=" * 80)

    health = pipeline.monitor_health()
    print(json.dumps(health, indent=2, default=str))

    return results


if __name__ == "__main__":
    asyncio.run(test_universal_pipeline())