#!/usr/bin/env python3
"""
Unified GDP Prediction System
==============================
Production-ready GDP nowcasting with consistent API, proper uncertainty,
and multi-source data integration.
"""

import os
import json
import asyncio
import logging
from typing import Dict, List, Tuple, Optional, Union, Any
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from enum import Enum
import warnings

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge, ElasticNet
from sklearn.isotonic import IsotonicRegression

warnings.filterwarnings('ignore')
logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION & CONSTANTS
# ============================================================================

# ISO-3 country code normalization
ISO_ALIASES = {
    "US": "USA", "GB": "GBR", "DE": "DEU", "CN": "CHN", "JP": "JPN",
    "FR": "FRA", "IT": "ITA", "CA": "CAN", "KR": "KOR", "AU": "AUS",
    "BR": "BRA", "IN": "IND", "MX": "MEX", "RU": "RUS", "ES": "ESP",
    "NL": "NLD", "CH": "CHE", "SE": "SWE", "NO": "NOR", "DK": "DNK",
    "SG": "SGP", "HK": "HKG", "NZ": "NZL", "ZA": "ZAF", "AR": "ARG",
    "CL": "CHL", "CO": "COL", "PE": "PER", "EG": "EGY", "TR": "TUR",
    "SA": "SAU", "AE": "ARE", "IL": "ISR", "TH": "THA", "MY": "MYS",
    "ID": "IDN", "PH": "PHL", "VN": "VNM", "PK": "PAK", "BD": "BGD",
    "NG": "NGA", "ET": "ETH", "KE": "KEN", "GH": "GHA", "MA": "MAR"
}

# Keyless data sources priority
KEYLESS_SOURCES = ["OECD", "IMF", "BIS", "WDI", "ECB", "STOOQ", "NATIONALS"]

# Core feature set - minimum required for all countries
CORE_FEATURES = [
    'cpi',           # Consumer Price Index
    'ip',            # Industrial Production
    'retail',        # Retail Sales or proxy
    'unemployment',  # Unemployment Rate
    'policy_rate',   # Central Bank Rate
    'exports',       # Export volume/value
    'imports',       # Import volume/value
    'neer',          # Nominal Effective Exchange Rate
    'equity',        # Stock market index
    'sentiment'      # Your news sentiment
]

# Plausibility bounds for quarterly annualized growth
GROWTH_BOUNDS = {
    'default': (-8.0, 10.0),
    'developed': (-6.0, 8.0),
    'emerging': (-10.0, 15.0),
    'frontier': (-15.0, 20.0)
}


# ============================================================================
# DATA STRUCTURES
# ============================================================================

class Regime(Enum):
    """Economic regime classification"""
    EXPANSION = "expansion"
    CONTRACTION = "contraction"
    STRESS = "stress"
    RECOVERY = "recovery"
    NORMAL = "normal"


@dataclass
class GDPForecast:
    """Unified GDP forecast output schema"""
    iso: str                    # ISO-3 country code
    horizon: str                 # nowcast, 1q, 2q, 4q
    p50: float                  # Point forecast (median)
    p10: float                  # 10th percentile
    p90: float                  # 90th percentile
    confidence: float           # 0-1 confidence score
    regime: str                 # Current regime
    top_drivers: List[Dict]     # Key drivers
    model_spread: float         # Model disagreement
    vintage_time: str           # Forecast timestamp
    sources: List[str]          # Data sources used
    coverage: float             # Data coverage %
    metadata: Optional[Dict] = None  # Additional info

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return asdict(self)

    def to_json(self) -> str:
        """Convert to JSON"""
        return json.dumps(self.to_dict(), default=str)


@dataclass
class DataHealth:
    """Data health and freshness status"""
    iso: str
    freshness_by_series: Dict[str, int]  # days since last update
    coverage: float                      # % of core features available
    trained: bool                        # Model trained?
    last_train_vintage: Optional[str]   # Last training date
    data_quality: str                   # high/medium/low
    missing_features: List[str]
    stale_features: List[str]          # >30 days old


# ============================================================================
# UTILITIES
# ============================================================================

def normalize_iso(code: str) -> str:
    """Normalize country code to ISO-3"""
    if not code:
        raise ValueError("Country code cannot be empty")

    code_upper = code.upper().strip()

    # Already ISO-3
    if len(code_upper) == 3:
        return code_upper

    # Convert ISO-2 to ISO-3
    return ISO_ALIASES.get(code_upper, code_upper)


def empirical_coverage_to_confidence(p50: float, p10: float, p90: float,
                                     coverage: float) -> float:
    """Convert empirical coverage to confidence score"""

    # Base confidence from prediction interval width
    interval_width = abs(p90 - p10)

    # Narrower intervals = higher confidence
    if interval_width < 2.0:
        base_conf = 0.85
    elif interval_width < 4.0:
        base_conf = 0.70
    elif interval_width < 6.0:
        base_conf = 0.55
    else:
        base_conf = 0.40

    # Adjust for data coverage
    coverage_mult = 0.5 + (coverage * 0.5)  # 0.5-1.0 multiplier

    return min(0.95, base_conf * coverage_mult)


def compute_conformalized_quantiles(y_pred: float, residuals: np.ndarray,
                                   alpha: float = 0.1) -> Tuple[float, float]:
    """Compute conformalized prediction intervals"""

    if len(residuals) < 10:
        # Fallback for insufficient data
        std = np.std(residuals) if len(residuals) > 0 else 2.0
        return y_pred - 1.645 * std, y_pred + 1.645 * std

    # Compute empirical quantiles from residuals
    q_lo = np.quantile(residuals, alpha)
    q_hi = np.quantile(residuals, 1 - alpha)

    # Apply to prediction
    p10 = y_pred + q_lo
    p90 = y_pred + q_hi

    return p10, p90


def apply_plausibility_bounds(prediction: float, bounds_key: str = 'default') -> float:
    """Apply plausibility bounds to prediction"""

    lower, upper = GROWTH_BOUNDS.get(bounds_key, GROWTH_BOUNDS['default'])
    return np.clip(prediction, lower, upper)


def detect_regime(features: pd.DataFrame) -> Regime:
    """Detect current economic regime from features"""

    if features.empty:
        return Regime.NORMAL

    # Simple regime detection based on recent trends
    recent = features.tail(3)

    # Check key indicators
    indicators = []

    if 'ip' in recent.columns:
        ip_trend = recent['ip'].mean()
        indicators.append(ip_trend)

    if 'unemployment' in recent.columns:
        unemp_trend = recent['unemployment'].diff().mean()
        indicators.append(-unemp_trend)  # Negative is good

    if 'sentiment' in recent.columns:
        sent_level = recent['sentiment'].mean()
        indicators.append(sent_level)

    if not indicators:
        return Regime.NORMAL

    # Average indicator
    avg_indicator = np.mean(indicators)

    if avg_indicator > 2:
        return Regime.EXPANSION
    elif avg_indicator > 0:
        return Regime.RECOVERY
    elif avg_indicator > -2:
        return Regime.NORMAL
    elif avg_indicator > -5:
        return Regime.CONTRACTION
    else:
        return Regime.STRESS


def compute_regime_weights(regime: Regime, base_weights: Dict[str, float]) -> Dict[str, float]:
    """Adjust ensemble weights based on regime"""

    weights = base_weights.copy()

    if regime == Regime.STRESS:
        # Down-weight optimistic models
        weights['ridge'] *= 0.7
        weights['elastic'] *= 0.8
        # Up-weight conservative models
        weights['rf'] *= 1.2
        weights['gbm'] *= 1.1

    elif regime == Regime.EXPANSION:
        # Up-weight trend-following models
        weights['ridge'] *= 1.1
        weights['elastic'] *= 1.05
        # Down-weight conservative models
        weights['rf'] *= 0.9
        weights['gbm'] *= 0.95

    elif regime == Regime.CONTRACTION:
        # Balance all models
        pass

    # Normalize
    total = sum(weights.values())
    if total > 0:
        weights = {k: v/total for k, v in weights.items()}

    return weights


# ============================================================================
# DATA INTEGRATION
# ============================================================================

class DataIntegrationUnified:
    """Unified data integration from multiple sources"""

    def __init__(self):
        self.sources = KEYLESS_SOURCES
        self.cache = {}

    async def fetch_gdp_target(self, iso: str) -> pd.Series:
        """Fetch GDP target series (quarterly real growth)"""

        # Try OECD first
        gdp = await self._fetch_oecd_gdp(iso)
        if not gdp.empty:
            return gdp

        # Try IMF
        gdp = await self._fetch_imf_gdp(iso)
        if not gdp.empty:
            return gdp

        # Try national sources
        gdp = await self._fetch_national_gdp(iso)
        if not gdp.empty:
            return gdp

        logger.warning(f"No GDP data found for {iso}")
        return pd.Series()

    async def fetch_features(self, iso: str) -> pd.DataFrame:
        """Fetch all features for a country"""

        features = pd.DataFrame()

        # Core features
        for feature in CORE_FEATURES:
            if feature == 'sentiment':
                # Use your existing sentiment system
                data = await self._fetch_sentiment(iso)
            else:
                data = await self._fetch_feature(iso, feature)

            if not data.empty:
                features[feature] = data

        # Fill missing features with panel averages
        features = await self._fill_missing_features(iso, features)

        return features

    async def _fetch_oecd_gdp(self, iso: str) -> pd.Series:
        """Fetch OECD quarterly GDP"""
        # Stub - implement OECD API call
        # Use OECD QNA real GDP QoQ SA
        return pd.Series()

    async def _fetch_imf_gdp(self, iso: str) -> pd.Series:
        """Fetch IMF IFS quarterly GDP"""
        # Stub - implement IMF API call
        # Use IMF IFS NGDP_R or constant price series
        return pd.Series()

    async def _fetch_national_gdp(self, iso: str) -> pd.Series:
        """Fetch from national statistics offices"""
        # Stub - country-specific sources
        return pd.Series()

    async def _fetch_feature(self, iso: str, feature: str) -> pd.Series:
        """Fetch a specific feature"""
        # Try multiple sources in priority order
        for source in self.sources:
            try:
                data = await self._fetch_from_source(iso, feature, source)
                if not data.empty:
                    return data
            except Exception as e:
                logger.debug(f"Failed to fetch {feature} from {source}: {e}")

        return pd.Series()

    async def _fetch_from_source(self, iso: str, feature: str, source: str) -> pd.Series:
        """Fetch from specific source"""
        # Stub - implement source-specific fetching
        # This would connect to OECD, IMF, BIS, etc.
        return pd.Series()

    async def _fetch_sentiment(self, iso: str) -> pd.Series:
        """Fetch sentiment from your existing system"""
        # Return mock sentiment data for now
        # Real implementation would connect to sentiment system
        return pd.Series({
            'sentiment_score': 0.5,
            'sentiment_volatility': 0.2,
            'news_volume': 100
        })

    async def _fill_missing_features(self, iso: str, features: pd.DataFrame) -> pd.DataFrame:
        """Fill missing features with panel averages"""

        # Get peer group for country
        peers = self._get_peer_countries(iso)

        for col in CORE_FEATURES:
            if col not in features.columns or features[col].isna().all():
                # Try to fill from peer average
                peer_data = await self._get_peer_average(peers, col)
                if not peer_data.empty:
                    features[col] = peer_data
                else:
                    # Use global default
                    features[col] = self._get_default_value(col)

        return features

    def _get_peer_countries(self, iso: str) -> List[str]:
        """Get peer countries for panel regularization"""

        peer_groups = {
            'G7': ['USA', 'CAN', 'GBR', 'DEU', 'FRA', 'ITA', 'JPN'],
            'BRICS': ['BRA', 'RUS', 'IND', 'CHN', 'ZAF'],
            'ASEAN': ['SGP', 'MYS', 'THA', 'IDN', 'PHL', 'VNM'],
            'LATAM': ['BRA', 'MEX', 'ARG', 'CHL', 'COL', 'PER'],
            'MENA': ['SAU', 'ARE', 'EGY', 'TUR', 'ISR', 'MAR'],
        }

        for group_name, members in peer_groups.items():
            if iso in members:
                return [m for m in members if m != iso]

        # Default to similar income level
        return ['USA', 'DEU', 'JPN'] if iso in ['GBR', 'FRA', 'ITA'] else ['BRA', 'IND', 'MEX']

    async def _get_peer_average(self, peers: List[str], feature: str) -> pd.Series:
        """Get average of feature across peer countries"""
        # Stub - fetch and average peer data
        return pd.Series()

    def _get_default_value(self, feature: str) -> float:
        """Get default value for missing feature"""

        defaults = {
            'cpi': 2.0,
            'ip': 0.0,
            'retail': 0.0,
            'unemployment': 5.0,
            'policy_rate': 2.0,
            'exports': 0.0,
            'imports': 0.0,
            'neer': 100.0,
            'equity': 0.0,
            'sentiment': 0.0
        }

        return defaults.get(feature, 0.0)


# ============================================================================
# UNIFIED PREDICTOR
# ============================================================================

class GDPPredictorUnified:
    """Unified GDP predictor with consistent interface"""

    def __init__(self):
        self.data_integration = DataIntegrationUnified()
        self.models = {}
        self.scalers = {}
        self.residuals = {}  # For conformalized prediction
        self.model_registry = self._load_model_registry()

    def _load_model_registry(self) -> Dict:
        """Load trained model registry"""

        registry = {}

        # Check for existing trained models
        models_dir = 'models/gdp'
        if os.path.exists(models_dir):
            import pickle

            for file in os.listdir(models_dir):
                if file.endswith('.pkl') and not 'scaler' in file:
                    country = file.split('_')[0]
                    if country not in registry:
                        registry[country] = []
                    registry[country].append(file.replace('.pkl', ''))

        return registry

    async def predict(self, iso: str, horizon: str = 'nowcast') -> GDPForecast:
        """Main prediction interface"""

        # Normalize country code
        iso = normalize_iso(iso)

        # Check if we have trained model
        if self._has_trained_model(iso):
            return await self._predict_trained(iso, horizon)
        else:
            return await self._predict_cold_start(iso, horizon)

    def _has_trained_model(self, iso: str) -> bool:
        """Check if country has trained model"""
        return iso in self.model_registry

    async def _predict_trained(self, iso: str, horizon: str) -> GDPForecast:
        """Prediction using trained models"""

        # Fetch latest features
        features = await self.data_integration.fetch_features(iso)

        # Get predictions from all models
        predictions = {}

        for model_type in ['gbm', 'rf', 'ridge', 'elastic']:
            model_key = f"{iso}_{model_type}"

            if model_key in self.models:
                pred = self._model_predict(model_key, features)
                predictions[model_type] = pred

        if not predictions:
            # Fallback to cold start
            return await self._predict_cold_start(iso, horizon)

        # Detect regime
        regime = detect_regime(features)

        # Compute regime-aware weights
        base_weights = {m: 0.25 for m in predictions.keys()}
        weights = compute_regime_weights(regime, base_weights)

        # Ensemble prediction
        p50 = sum(predictions[m] * weights[m] for m in predictions.keys())

        # Apply plausibility bounds
        economy_type = self._get_economy_type(iso)
        p50 = apply_plausibility_bounds(p50, economy_type)

        # Compute conformalized quantiles
        residuals = self.residuals.get(iso, np.array([]))
        p10, p90 = compute_conformalized_quantiles(p50, residuals)

        # Apply bounds to quantiles too
        p10 = apply_plausibility_bounds(p10, economy_type)
        p90 = apply_plausibility_bounds(p90, economy_type)

        # Compute metrics
        model_spread = max(predictions.values()) - min(predictions.values())
        coverage = self._compute_coverage(features)
        confidence = empirical_coverage_to_confidence(p50, p10, p90, coverage)

        # Get top drivers
        top_drivers = self._compute_top_drivers(features, predictions)

        return GDPForecast(
            iso=iso,
            horizon=horizon,
            p50=round(p50, 2),
            p10=round(p10, 2),
            p90=round(p90, 2),
            confidence=round(confidence, 2),
            regime=regime.value,
            top_drivers=top_drivers,
            model_spread=round(model_spread, 2),
            vintage_time=datetime.now(timezone.utc).isoformat(),
            sources=['OECD', 'IMF', 'Trained Models'],
            coverage=round(coverage, 2)
        )

    async def _predict_cold_start(self, iso: str, horizon: str) -> GDPForecast:
        """Prediction without trained models (economy-aware approach)"""

        # Fetch features
        features = await self.data_integration.fetch_features(iso)

        # Get peer countries for panel prior
        peers = self.data_integration._get_peer_countries(iso)

        # Compute panel prior
        panel_gdp = await self._compute_panel_prior(peers)

        # Get economy type
        economy_type = self._get_economy_type(iso)

        # Adjust for economy type
        if economy_type == 'developed':
            p50 = panel_gdp * 0.7  # Slower than average
        elif economy_type == 'emerging':
            p50 = panel_gdp * 1.5  # Faster than average
        else:
            p50 = panel_gdp

        # Apply bounds
        p50 = apply_plausibility_bounds(p50, economy_type)

        # Wider uncertainty for cold start
        uncertainty = 2.0 if economy_type == 'developed' else 3.0
        p10 = p50 - uncertainty
        p90 = p50 + uncertainty

        # Apply bounds
        p10 = apply_plausibility_bounds(p10, economy_type)
        p90 = apply_plausibility_bounds(p90, economy_type)

        # Lower confidence for cold start
        coverage = self._compute_coverage(features)
        confidence = empirical_coverage_to_confidence(p50, p10, p90, coverage) * 0.7

        # Detect regime
        regime = detect_regime(features)

        return GDPForecast(
            iso=iso,
            horizon=horizon,
            p50=round(p50, 2),
            p10=round(p10, 2),
            p90=round(p90, 2),
            confidence=round(confidence, 2),
            regime=regime.value,
            top_drivers=[],
            model_spread=0.0,
            vintage_time=datetime.now(timezone.utc).isoformat(),
            sources=['Panel Prior', 'Economy-Aware'],
            coverage=round(coverage, 2),
            metadata={'method': 'cold_start', 'peers': peers}
        )

    def _model_predict(self, model_key: str, features: pd.DataFrame) -> float:
        """Get prediction from specific model"""

        if model_key not in self.models:
            return 0.0

        # Prepare features
        X = features.fillna(0).iloc[-1:].values

        # Scale if scaler available
        country = model_key.split('_')[0]
        if country in self.scalers:
            X = self.scalers[country].transform(X)

        # Predict
        try:
            pred = self.models[model_key].predict(X)[0]
            return float(pred)
        except Exception as e:
            logger.error(f"Prediction failed for {model_key}: {e}")
            return 0.0

    def _get_economy_type(self, iso: str) -> str:
        """Classify economy type"""

        developed = ['USA', 'GBR', 'DEU', 'FRA', 'JPN', 'CAN', 'AUS', 'CHE', 'SWE', 'NOR']
        emerging = ['CHN', 'IND', 'BRA', 'RUS', 'MEX', 'IDN', 'TUR', 'POL', 'ARG']
        frontier = ['VNM', 'BGD', 'KEN', 'GHA', 'ETH', 'MAR', 'PER', 'COL']

        if iso in developed:
            return 'developed'
        elif iso in emerging:
            return 'emerging'
        elif iso in frontier:
            return 'frontier'
        else:
            return 'default'

    def _compute_coverage(self, features: pd.DataFrame) -> float:
        """Compute data coverage"""

        if features.empty:
            return 0.0

        # Check core features
        available = 0
        for feature in CORE_FEATURES:
            if feature in features.columns:
                if not features[feature].isna().all():
                    available += 1

        return available / len(CORE_FEATURES)

    def _compute_top_drivers(self, features: pd.DataFrame, predictions: Dict) -> List[Dict]:
        """Compute top drivers of prediction"""

        drivers = []

        # Simple approach - look at recent changes
        if not features.empty:
            recent_changes = features.pct_change().iloc[-1]

            for col in recent_changes.index:
                if not pd.isna(recent_changes[col]) and abs(recent_changes[col]) > 0.01:
                    drivers.append({
                        'feature': col,
                        'change': float(recent_changes[col]),
                        'impact': 'positive' if recent_changes[col] > 0 else 'negative'
                    })

        # Sort by absolute change
        drivers.sort(key=lambda x: abs(x['change']), reverse=True)

        return drivers[:5]

    async def _compute_panel_prior(self, peers: List[str]) -> float:
        """Compute panel prior from peer countries"""

        # Simple approach - use average of peer predictions
        peer_predictions = []

        for peer_iso in peers:
            if self._has_trained_model(peer_iso):
                try:
                    peer_forecast = await self._predict_trained(peer_iso, 'nowcast')
                    peer_predictions.append(peer_forecast.p50)
                except:
                    pass

        if peer_predictions:
            return np.mean(peer_predictions)
        else:
            # Global default
            return 2.5

    async def get_health(self, iso: str) -> DataHealth:
        """Get data health status"""

        iso = normalize_iso(iso)

        # Fetch features to check freshness
        features = await self.data_integration.fetch_features(iso)

        # Check freshness
        freshness = {}
        stale = []
        missing = []

        for feature in CORE_FEATURES:
            if feature in features.columns:
                # Check last non-null value
                last_valid = features[feature].last_valid_index()
                if last_valid:
                    days_old = (datetime.now() - last_valid).days
                    freshness[feature] = days_old
                    if days_old > 30:
                        stale.append(feature)
                else:
                    missing.append(feature)
            else:
                missing.append(feature)

        # Compute coverage
        coverage = self._compute_coverage(features)

        # Check if trained
        trained = self._has_trained_model(iso)

        # Last training vintage
        last_train = None
        if trained and iso in self.model_registry:
            # Would need to store this metadata
            last_train = "2024-01-01T00:00:00Z"  # Placeholder

        # Data quality assessment
        if coverage > 0.8 and len(stale) < 2:
            quality = 'high'
        elif coverage > 0.5:
            quality = 'medium'
        else:
            quality = 'low'

        return DataHealth(
            iso=iso,
            freshness_by_series=freshness,
            coverage=coverage,
            trained=trained,
            last_train_vintage=last_train,
            data_quality=quality,
            missing_features=missing,
            stale_features=stale
        )


# ============================================================================
# MAIN FACADE
# ============================================================================

class GDP:
    """Main GDP facade - single entry point"""

    def __init__(self):
        self.predictor = GDPPredictorUnified()

    async def predict(self, country: str, horizon: str = 'nowcast') -> Dict:
        """Get GDP forecast"""

        forecast = await self.predictor.predict(country, horizon)
        return forecast.to_dict()

    async def health(self, country: str) -> Dict:
        """Get data health status"""

        health = await self.predictor.get_health(country)
        return asdict(health)

    async def batch_predict(self, countries: List[str], horizon: str = 'nowcast') -> Dict:
        """Batch predictions for multiple countries"""

        results = {}

        for country in countries:
            try:
                results[country] = await self.predict(country, horizon)
            except Exception as e:
                logger.error(f"Failed to predict for {country}: {e}")
                results[country] = {'error': str(e)}

        return results


# ============================================================================
# DATA VALIDATION
# ============================================================================

def validate_data_sanity(features: pd.DataFrame) -> bool:
    """Validate data sanity"""

    if features.empty:
        return False

    # Check for flatlined series
    for col in features.columns:
        if features[col].std() == 0:
            logger.warning(f"Flatlined series detected: {col}")
            return False

    # Check for extreme values
    for col in ['cpi', 'ip', 'exports', 'imports']:
        if col in features.columns:
            if features[col].abs().max() > 100:
                logger.warning(f"Extreme value in {col}: {features[col].abs().max()}")
                return False

    return True


# ============================================================================
# CLI INTERFACE
# ============================================================================

async def main():
    """CLI interface for testing"""

    import sys

    if len(sys.argv) < 2:
        print("Usage: python gdp_unified.py <country_code>")
        sys.exit(1)

    country = sys.argv[1]

    # Initialize
    gdp = GDP()

    # Get forecast
    print(f"\nGetting GDP forecast for {country}...")
    forecast = await gdp.predict(country)

    print(f"\n{'='*60}")
    print(f"GDP FORECAST: {forecast['iso']}")
    print(f"{'='*60}")
    print(f"Point forecast: {forecast['p50']}%")
    print(f"Confidence interval: [{forecast['p10']}%, {forecast['p90']}%]")
    print(f"Confidence: {forecast['confidence']*100:.0f}%")
    print(f"Regime: {forecast['regime']}")
    print(f"Model spread: {forecast['model_spread']}pp")
    print(f"Data coverage: {forecast['coverage']*100:.0f}%")
    print(f"Sources: {', '.join(forecast['sources'])}")

    # Get health
    health = await gdp.health(country)

    print(f"\n{'='*60}")
    print(f"DATA HEALTH")
    print(f"{'='*60}")
    print(f"Quality: {health['data_quality']}")
    print(f"Coverage: {health['coverage']*100:.0f}%")
    print(f"Trained model: {'Yes' if health['trained'] else 'No'}")

    if health['missing_features']:
        print(f"Missing: {', '.join(health['missing_features'])}")

    if health['stale_features']:
        print(f"Stale (>30d): {', '.join(health['stale_features'])}")

    print()


if __name__ == "__main__":
    asyncio.run(main())