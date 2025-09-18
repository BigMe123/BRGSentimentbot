#!/usr/bin/env python3
"""
GDP Model Trainer
=================
Trains GDP prediction models using historical data from FRED.
Handles data collection, model training, validation, and persistence.
"""

import os
import json
import pickle
import asyncio
import logging
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit, train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge, ElasticNet
from sklearn.preprocessing import StandardScaler
import warnings

# Import our improvements
try:
    from sentiment_bot.gdp_stacking_ensemble import RegimeAwareStackingEnsemble, generate_oof_predictions
    from sentiment_bot.gdp_shock_robust import RobustGDPEstimator
    STACKING_AVAILABLE = True
except ImportError:
    logger.warning("Stacking ensemble and robust estimator not available")
    STACKING_AVAILABLE = False

warnings.filterwarnings('ignore')

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class GDPModelTrainer:
    """Trains and validates GDP prediction models"""

    # Validated FRED series for GDP (actual working series)
    GDP_SERIES = {
        'USA': 'GDPC1',  # Real GDP USA
        'GBR': 'UKNGDP',  # Nominal GDP UK
        'JPN': 'JPNRGDPEXP',  # Real GDP Japan
        'DEU': 'CLVMNACSCAB1GQDE',  # Real GDP Germany
        'FRA': 'CLVMNACSCAB1GQFR',  # Real GDP France
        'CAN': 'NAEXKP01CAQ652S',  # Real GDP Canada
        'AUS': 'AUSGDPQDSNAQ',  # Real GDP Australia
        'KOR': 'NGDPRSAXDCKRQ',  # Real GDP Korea
        'MEX': 'MEXRGDPQDSNAQ',  # Real GDP Mexico
        'BRA': 'BRAGDPNSAQS',  # GDP Brazil
        'IND': 'INDGDPDEFAISMEI',  # GDP India
        'CHN': 'RGDPNACNA666NRUG',  # Real GDP China (Penn World Table)
        'RUS': 'RUSGDPNQDSMEI',  # GDP Russia
        'ZAF': 'ZAFRGDPQDSNAQ',  # Real GDP South Africa
        'TUR': 'CLVMNACNSAB1GQTR',  # Real GDP Turkey
        'IDN': 'IDNGDP',  # GDP Indonesia
        'ARG': 'ARGRGDPQDSNAQ',  # Real GDP Argentina
        'SAU': 'SAUGDPNQDSMEI',  # GDP Saudi Arabia
        'ITA': 'CLVMNACSCAB1GQIT',  # Real GDP Italy
        'ESP': 'CLVMNACSCAB1GQES',  # Real GDP Spain
        'NLD': 'CLVMNACSCAB1GQNL',  # Real GDP Netherlands
        'CHE': 'CLVMNACSCAB1GQCH',  # Real GDP Switzerland
        'SWE': 'CLVMNACSCAB1GQSE',  # Real GDP Sweden
        'POL': 'CLVMNACSCAB1GQPL',  # Real GDP Poland
        'BEL': 'CLVMNACSCAB1GQBE',  # Real GDP Belgium
        'NOR': 'CLVMNACSCAB1GQNO',  # Real GDP Norway
    }

    # Economic indicators for features
    FEATURE_SERIES = {
        'USA': {
            'cpi': 'CPIAUCSL',
            'unemployment': 'UNRATE',
            'industrial': 'INDPRO',
            'retail_sales': 'RSXFS',
            'consumer_conf': 'UMCSENT',
            'exports': 'EXPGS',
            'imports': 'IMPGS',
            'interest_rate': 'DFF',
            'stock_market': 'SP500',
            'housing': 'HOUST',
            'pmi_manufacturing': 'MANEMP',
            'money_supply': 'M2SL',
        },
        'GBR': {
            'cpi': 'GBRCPIALLMINMEI',
            'unemployment': 'LRHUTTTTGBM156S',
            'industrial': 'GBRPROINDMISMEI',
            'interest_rate': 'INTDSRGBM193N',
            'services_pmi': 'GBRPRMISEINDXM',  # Services PMI
            'consumer_conf': 'CSCICP03GBM460S',  # Consumer confidence
            'energy_prices': 'DHHNGSP',  # Natural gas prices (proxy)
            'exports_eu': 'XTEXVA01GBM667S',  # Exports value
            'imports': 'XTIMVA01GBM667S',  # Imports value
            'retail_sales': 'GBRSLRTTO01IXOBM',  # Retail sales
            'house_prices': 'QGBR628BIS',  # House price index
            'vacancies': 'LMJVTTUVGBM647S',  # Job vacancies
        },
        'JPN': {
            'cpi': 'JPNCPIALLMINMEI',
            'unemployment': 'JPNURHARMMDSMEI',
            'industrial': 'JPNPROINDMISMEI',
            'exports': 'JPNXTEXVA01CXMLM',
            'services_pmi': 'JPNPRMISEINDDXM',  # Services PMI
            'tourism_receipts': 'JPNRECEIPT',  # Tourism receipts
            'retail_sales': 'JPNSLRTTO01IXOBM',  # Retail sales
            'consumer_conf': 'JPNCNFCONALLM',  # Consumer confidence
            'auto_production': 'JPNAUPSA',  # Auto production
            'household_spending': 'JPNHOUSEHOLDM',  # Household spending
            'boj_balance': 'JPNASSETS',  # BoJ total assets (YCC proxy)
            'yen_trade_weighted': 'DTWEXBGS',  # Yen TWI
        },
        'DEU': {
            'cpi': 'DEUCPIALLMINMEI',
            'unemployment': 'DEUURHARMMDSMEI',
            'industrial': 'DEUPROINDMISMEI',
            'exports': 'DEUXTEXVA01CXMLM',
        },
        'CHN': {
            'cpi': 'CHNCPIALLMINMEI',
            'industrial': 'CHNPROINDQISMEI',
            'exports': 'XTEXVA01CNM659S',
            'imports': 'XTIMVA01CNM659S',
        }
    }

    def __init__(self, models_dir: str = 'models/gdp'):
        """Initialize trainer"""
        self.models_dir = models_dir
        os.makedirs(models_dir, exist_ok=True)

        # Initialize data collector
        from sentiment_bot.ml_foundation import DataIntegration, ModelConfig
        config = ModelConfig()
        config.fred_api_key = os.getenv('FRED_API_KEY', '28eb3d64654c60195cfeed9bc4ec2a41')
        self.data_integration = DataIntegration(config)

        # Initialize stacking ensembles and robust estimators
        self.stacking_ensembles = {}
        self.robust_estimators = {}
        if STACKING_AVAILABLE:
            logger.info("Stacking ensemble and robust estimation enabled")

        self.models = {}
        self.scalers = {}
        self.performance = {}

    def fetch_gdp_data(self, country: str, start_date: str = '2010-01-01') -> pd.Series:
        """Fetch historical GDP data for a country"""

        if country not in self.GDP_SERIES:
            logger.warning(f"No GDP series defined for {country}")
            return pd.Series()

        try:
            series_id = self.GDP_SERIES[country]
            logger.info(f"Fetching {series_id} for {country}")

            gdp_data = self.data_integration.get_fred_data(series_id)

            if not gdp_data.empty:
                # Convert to growth rate
                gdp_growth = gdp_data.pct_change(periods=4) * 100  # YoY growth
                gdp_growth = gdp_growth.dropna()

                # Filter by date
                gdp_growth = gdp_growth[gdp_growth.index >= pd.to_datetime(start_date)]

                logger.info(f"Retrieved {len(gdp_growth)} GDP observations for {country}")
                return gdp_growth
            else:
                logger.error(f"No data retrieved for {country}")
                return pd.Series()

        except Exception as e:
            logger.error(f"Failed to fetch GDP for {country}: {e}")
            return pd.Series()

    def fetch_features(self, country: str, start_date: str = '2010-01-01') -> pd.DataFrame:
        """Fetch economic features for a country"""

        features = pd.DataFrame()

        # Get country-specific features or use USA as default
        country_features = self.FEATURE_SERIES.get(country, self.FEATURE_SERIES.get('USA', {}))

        for feature_name, series_id in country_features.items():
            try:
                data = self.data_integration.get_fred_data(series_id)

                if not data.empty:
                    # Process based on feature type
                    if feature_name in ['cpi', 'industrial', 'exports', 'imports', 'retail_sales']:
                        # Convert to growth rates
                        data = data.pct_change(periods=12) * 100  # YoY change
                    elif feature_name in ['unemployment', 'interest_rate']:
                        # Use levels
                        pass
                    elif feature_name == 'stock_market':
                        # Convert to returns
                        data = data.pct_change(periods=252) * 100  # Annual return

                    features[feature_name] = data
                    logger.info(f"Added {feature_name} for {country}")

            except Exception as e:
                logger.warning(f"Failed to fetch {feature_name} for {country}: {e}")

        # Add lagged GDP as a feature
        gdp = self.fetch_gdp_data(country, start_date)
        if not gdp.empty:
            features['gdp_lag1'] = gdp.shift(1)
            features['gdp_lag2'] = gdp.shift(2)
            features['gdp_lag4'] = gdp.shift(4)

        # Add global indicators
        try:
            # Oil prices
            oil = self.data_integration.get_fred_data('DCOILWTICO')
            if not oil.empty:
                features['oil_price_change'] = oil.pct_change(periods=252) * 100

            # VIX
            vix = self.data_integration.get_fred_data('VIXCLS')
            if not vix.empty:
                features['global_uncertainty'] = vix

        except Exception as e:
            logger.warning(f"Failed to fetch global indicators: {e}")

        # Country-specific feature engineering
        if country == 'GBR':
            # Brexit-related features
            features['post_brexit'] = (features.index >= pd.to_datetime('2016-07-01')).astype(int)
            features['post_transition'] = (features.index >= pd.to_datetime('2021-01-01')).astype(int)

            # Brexit trade friction interactions
            if 'exports_eu' in features.columns:
                features['brexit_trade_impact'] = features['post_brexit'] * features['exports_eu']

            # Terms of trade
            if 'exports' in features.columns and 'imports' in features.columns:
                features['terms_of_trade'] = features['exports'] / (features['imports'] + 0.001)

            # Energy crisis indicator
            if 'energy_prices' in features.columns:
                features['energy_shock'] = (features['energy_prices'] > features['energy_prices'].quantile(0.75)).astype(int)

        elif country == 'JPN':
            # Tourism reopening
            features['tourism_reopening'] = (features.index >= pd.to_datetime('2022-10-01')).astype(int)

            # YCC deviation
            if 'boj_balance' in features.columns:
                features['ycc_expansion'] = features['boj_balance'].pct_change(periods=12) * 100

            # FX pass-through ladder
            if 'yen_trade_weighted' in features.columns:
                for lag in [1, 2, 3]:
                    features[f'yen_twi_lag{lag}'] = features['yen_trade_weighted'].shift(lag)

            # Auto sector impact
            if 'auto_production' in features.columns and 'exports' in features.columns:
                features['auto_export_correlation'] = features['auto_production'] * features['exports'] / 10000

        # Filter by date
        features = features[features.index >= pd.to_datetime(start_date)]

        logger.info(f"Created feature matrix with {features.shape[1]} features for {country}")
        return features

    def _detect_regimes(self, gdp_growth: pd.Series) -> pd.Series:
        """Detect economic regimes based on GDP growth"""
        # Calculate rolling mean and std
        rolling_mean = gdp_growth.rolling(window=4, min_periods=2).mean()
        rolling_std = gdp_growth.rolling(window=4, min_periods=2).std()

        # Define regime thresholds
        regimes = pd.Series(index=gdp_growth.index, dtype=str)

        for i in range(len(gdp_growth)):
            growth = gdp_growth.iloc[i]
            mean = rolling_mean.iloc[i] if i >= 1 else gdp_growth.mean()
            std = rolling_std.iloc[i] if i >= 1 else gdp_growth.std()

            if pd.isna(growth):
                regimes.iloc[i] = 'normal'
            elif growth < mean - 2 * std or growth < -2:
                regimes.iloc[i] = 'stress'
            elif growth < mean - std or growth < 0:
                regimes.iloc[i] = 'contraction'
            elif growth > mean + std and growth > 3:
                regimes.iloc[i] = 'expansion'
            else:
                regimes.iloc[i] = 'normal'

        return regimes

    def _get_current_regime(self, country: str, features: pd.DataFrame) -> str:
        """Determine current economic regime"""
        # Get recent GDP growth if available
        try:
            gdp = self.fetch_gdp_data(country)
            if not gdp.empty:
                recent_growth = gdp.pct_change(periods=4).tail(4) * 100
                if len(recent_growth) > 0:
                    avg_growth = recent_growth.mean()
                    if avg_growth < -1:
                        return 'contraction'
                    elif avg_growth < 1:
                        return 'normal'
                    elif avg_growth > 3:
                        return 'expansion'
                    else:
                        return 'normal'
        except Exception as e:
            logger.warning(f"Could not determine regime for {country}: {e}")

        # Check for shock indicators
        if 'global_uncertainty' in features.columns:
            vix = features['global_uncertainty'].iloc[-1]
            if vix > 30:  # High VIX indicates stress
                return 'stress'

        return 'normal'

    def _train_dfm_model(self, country: str, features: pd.DataFrame, gdp: pd.Series):
        """Train Dynamic Factor Model for mixed-frequency nowcasting"""
        try:
            from sentiment_bot.gdp_dfm_nowcast import create_dfm_nowcaster

            logger.info(f"Training DFM model for {country}")

            # Get monthly features (DFM needs higher frequency data)
            monthly_features = self._get_monthly_features(country)

            if monthly_features.empty or len(monthly_features) < 24:
                logger.warning(f"Insufficient monthly data for DFM in {country}")
                return None

            # Create and train DFM
            dfm = create_dfm_nowcaster(country)
            dfm.fit(monthly_features, gdp)

            logger.info(f"DFM model trained successfully for {country}")
            return dfm

        except Exception as e:
            logger.error(f"Failed to train DFM for {country}: {e}")
            return None

    def _get_monthly_features(self, country: str) -> pd.DataFrame:
        """Get monthly features for DFM training"""
        monthly_features = pd.DataFrame()

        # Core monthly indicators for DFM
        monthly_series = {
            'cpi': self.FEATURE_SERIES.get(country, {}).get('cpi'),
            'industrial': self.FEATURE_SERIES.get(country, {}).get('industrial'),
            'unemployment': self.FEATURE_SERIES.get(country, {}).get('unemployment'),
            'exports': self.FEATURE_SERIES.get(country, {}).get('exports'),
            'imports': self.FEATURE_SERIES.get(country, {}).get('imports'),
            'interest_rate': self.FEATURE_SERIES.get(country, {}).get('interest_rate'),
        }

        for feature_name, series_id in monthly_series.items():
            if series_id:
                try:
                    data = self.data_integration.get_fred_data(series_id)
                    if not data.empty:
                        # Ensure monthly frequency
                        data = data.resample('M').last()
                        monthly_features[feature_name] = data
                except Exception as e:
                    logger.debug(f"Failed to fetch monthly {feature_name} for {country}: {e}")

        return monthly_features

    def prepare_training_data(self, country: str) -> Tuple[pd.DataFrame, pd.Series]:
        """Prepare training data for a country"""

        # Fetch target (GDP growth)
        gdp = self.fetch_gdp_data(country)

        if gdp.empty:
            logger.error(f"No GDP data for {country}")
            return pd.DataFrame(), pd.Series()

        # Fetch features
        features = self.fetch_features(country)

        if features.empty:
            logger.error(f"No features for {country}")
            return pd.DataFrame(), pd.Series()

        # Align data
        common_idx = features.index.intersection(gdp.index)

        if len(common_idx) < 20:
            logger.warning(f"Insufficient data for {country}: only {len(common_idx)} observations")
            return pd.DataFrame(), pd.Series()

        features = features.loc[common_idx]
        gdp = gdp.loc[common_idx]

        # Handle missing values
        features = features.fillna(method='ffill').fillna(0)

        logger.info(f"Prepared {len(features)} training samples for {country}")

        return features, gdp

    def train_models(self, country: str) -> Dict:
        """Train all models for a country"""

        logger.info(f"Training models for {country}")

        # Prepare data
        X, y = self.prepare_training_data(country)

        if X.empty or y.empty:
            logger.error(f"Cannot train models for {country} - no data")
            return {}

        # Scale features
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        self.scalers[country] = scaler

        # Time series split for validation
        tscv = TimeSeriesSplit(n_splits=3)

        # Models to train
        models = {
            'gbm': GradientBoostingRegressor(
                n_estimators=100,
                max_depth=3,
                learning_rate=0.1,
                subsample=0.8,
                random_state=42
            ),
            'rf': RandomForestRegressor(
                n_estimators=100,
                max_depth=5,
                min_samples_leaf=5,
                random_state=42
            ),
            'ridge': Ridge(alpha=1.0),
            'elastic': ElasticNet(alpha=0.1, l1_ratio=0.5)
        }

        # Add DFM model if monthly data available
        dfm_model = self._train_dfm_model(country, X, y)
        if dfm_model is not None:
            models['dfm'] = dfm_model

        results = {}

        for model_name, model in models.items():
            try:
                # Cross-validation
                cv_scores = []

                for train_idx, val_idx in tscv.split(X_scaled):
                    X_train, X_val = X_scaled[train_idx], X_scaled[val_idx]
                    y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]

                    model.fit(X_train, y_train)
                    pred = model.predict(X_val)

                    mae = mean_absolute_error(y_val, pred)
                    cv_scores.append(mae)

                # Final training on all data
                model.fit(X_scaled, y)

                # Store model
                self.models[f"{country}_{model_name}"] = model

                # Store performance
                results[model_name] = {
                    'mae': np.mean(cv_scores),
                    'std': np.std(cv_scores),
                    'feature_importance': self._get_feature_importance(model, X.columns)
                }

                logger.info(f"Trained {model_name} for {country}: MAE={np.mean(cv_scores):.3f}")

            except Exception as e:
                logger.error(f"Failed to train {model_name} for {country}: {e}")

        self.performance[country] = results

        # Train stacking ensemble if we have enough data and STACKING_AVAILABLE
        if STACKING_AVAILABLE and len(y) >= 50:
            try:
                logger.info(f"Training stacking ensemble for {country}")

                # Generate out-of-fold predictions for stacking
                from sentiment_bot.gdp_stacking_ensemble import generate_oof_predictions

                # Prepare models dict (excluding DFM which has different interface)
                oof_models = {}
                for model_name in ['gbm', 'rf', 'ridge', 'elastic']:
                    model_key = f"{country}_{model_name}"
                    if model_key in self.models:
                        oof_models[model_name] = self.models[model_key]

                if oof_models:
                    # Generate out-of-fold predictions
                    oof_preds = generate_oof_predictions(oof_models, pd.DataFrame(X_scaled, columns=X.columns), y)

                    # Detect regimes
                    gdp_growth = y.pct_change(periods=4) * 100
                    regimes = self._detect_regimes(gdp_growth)

                    # Train stacking ensemble
                    stacking = RegimeAwareStackingEnsemble()
                    stacking.fit(oof_preds, y, regimes, pd.Series([country] * len(y)))

                    self.stacking_ensembles[country] = stacking

                    # Log the learned weights
                    logger.info(f"Stacking ensemble trained for {country}")
                    logger.info(f"Global weights: {stacking.get_weights()}")
                    for regime in stacking.regime_weights:
                        logger.info(f"Weights for {regime}: {stacking.get_weights(regime, country)}")

            except Exception as e:
                logger.warning(f"Failed to train stacking ensemble for {country}: {e}")

        # Initialize robust estimator
        if STACKING_AVAILABLE:
            self.robust_estimators[country] = RobustGDPEstimator()

        return results

    def _get_feature_importance(self, model, feature_names) -> Dict:
        """Extract feature importance from model"""

        importance = {}

        if hasattr(model, 'feature_importances_'):
            # Tree-based models
            for name, imp in zip(feature_names, model.feature_importances_):
                importance[name] = float(imp)
        elif hasattr(model, 'coef_'):
            # Linear models
            for name, coef in zip(feature_names, model.coef_):
                importance[name] = float(abs(coef))

        # Sort by importance
        importance = dict(sorted(importance.items(), key=lambda x: x[1], reverse=True)[:5])

        return importance

    def predict(self, country: str, features: pd.DataFrame = None) -> Dict:
        """Make GDP prediction for a country"""

        if features is None:
            # Get latest features
            features = self.fetch_features(country)

            if features.empty:
                logger.error(f"No features available for {country}")
                return {'error': 'No features available'}

        # Get latest row
        latest_features = features.iloc[-1:].fillna(0)

        # Scale features
        if country in self.scalers:
            X_scaled = self.scalers[country].transform(latest_features)
        else:
            logger.warning(f"No scaler for {country}, using raw features")
            X_scaled = latest_features.values

        predictions = {}

        # Get predictions from all models
        for model_name in ['gbm', 'rf', 'ridge', 'elastic', 'dfm']:
            model_key = f"{country}_{model_name}"

            if model_key in self.models:
                try:
                    if model_name == 'dfm':
                        # DFM needs monthly data
                        monthly_features = self._get_monthly_features(country)
                        if not monthly_features.empty:
                            nowcast = self.models[model_key].nowcast(monthly_features.tail(6))
                            pred = nowcast['nowcast']
                            predictions[model_name] = float(pred)
                    else:
                        pred = self.models[model_key].predict(X_scaled)[0]
                        predictions[model_name] = float(pred)
                except Exception as e:
                    logger.error(f"Prediction failed for {model_key}: {e}")

        if predictions:
            # Determine current regime
            regime = self._get_current_regime(country, features)
            predictions['regime'] = regime

            # Use stacking ensemble if available
            if STACKING_AVAILABLE and country in self.stacking_ensembles:
                try:
                    # Get stacking weights for current regime
                    weights = self.stacking_ensembles[country].get_weights(regime, country)

                    # Calculate weighted ensemble
                    ensemble = 0
                    weight_sum = 0
                    for model_name, weight in weights.items():
                        if model_name in predictions:
                            ensemble += predictions[model_name] * weight
                            weight_sum += weight

                    if weight_sum > 0:
                        ensemble = ensemble / weight_sum
                    else:
                        ensemble = np.mean(list(predictions.values()))

                    logger.info(f"Using stacking weights for {country}/{regime}: {weights}")
                except Exception as e:
                    logger.warning(f"Stacking failed, using simple average: {e}")
                    ensemble = np.mean(list(predictions.values()))
            else:
                # Fallback to simple average
                ensemble = np.mean(list(predictions.values()))

            predictions['ensemble'] = float(ensemble)

            # Add confidence based on model agreement
            std = np.std(list(predictions.values()))

            # Better confidence formula:
            # - High confidence (>80%) when std < 0.5%
            # - Medium confidence (60-80%) when std 0.5-1.5%
            # - Low confidence (<60%) when std > 1.5%

            if std < 0.5:
                confidence = 0.9 - (std * 0.2)  # 90% to 80%
            elif std < 1.0:
                confidence = 0.8 - (std - 0.5) * 0.3  # 80% to 65%
            elif std < 2.0:
                confidence = 0.65 - (std - 1.0) * 0.2  # 65% to 45%
            else:
                confidence = max(0.25, 0.45 - (std - 2.0) * 0.1)  # 45% down to 25% min

            predictions['confidence'] = float(confidence)

        return predictions

    def backtest(self, country: str, test_periods: int = 12) -> Dict:
        """Backtest models on historical data"""

        logger.info(f"Backtesting {country} for {test_periods} periods")

        # Get full data
        X, y = self.prepare_training_data(country)

        if len(y) < test_periods + 20:
            logger.warning(f"Insufficient data for backtesting {country}")
            return {}

        # Split data
        train_size = len(y) - test_periods
        X_train = X.iloc[:train_size]
        y_train = y.iloc[:train_size]
        X_test = X.iloc[train_size:]
        y_test = y.iloc[train_size:]

        # Retrain on training portion
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        results = {}
        predictions = {}

        # Test each model
        for model_name in ['gbm', 'rf', 'ridge', 'elastic']:
            model_key = f"{country}_{model_name}"

            if model_key in self.models:
                # Use existing model for prediction
                model = self.models[model_key]

                try:
                    pred = model.predict(X_test_scaled)
                    predictions[model_name] = pred

                    # Calculate metrics
                    mae = mean_absolute_error(y_test, pred)
                    rmse = np.sqrt(mean_squared_error(y_test, pred))
                    r2 = r2_score(y_test, pred)

                    results[model_name] = {
                        'mae': float(mae),
                        'rmse': float(rmse),
                        'r2': float(r2)
                    }

                except Exception as e:
                    logger.error(f"Backtest failed for {model_key}: {e}")

        # Ensemble performance
        if predictions:
            ensemble_pred = np.mean(list(predictions.values()), axis=0)

            results['ensemble'] = {
                'mae': float(mean_absolute_error(y_test, ensemble_pred)),
                'rmse': float(np.sqrt(mean_squared_error(y_test, ensemble_pred))),
                'r2': float(r2_score(y_test, ensemble_pred))
            }

            # Store actual vs predicted
            results['actual'] = y_test.tolist()
            results['predicted'] = ensemble_pred.tolist()
            results['dates'] = y_test.index.strftime('%Y-%m-%d').tolist()

        return results

    def save_models(self):
        """Save all trained models"""

        # Save models
        for model_key, model in self.models.items():
            model_path = os.path.join(self.models_dir, f"{model_key}.pkl")
            with open(model_path, 'wb') as f:
                pickle.dump(model, f)
            logger.info(f"Saved model: {model_path}")

        # Save scalers
        for country, scaler in self.scalers.items():
            scaler_path = os.path.join(self.models_dir, f"{country}_scaler.pkl")
            with open(scaler_path, 'wb') as f:
                pickle.dump(scaler, f)

        # Save performance metrics
        perf_path = os.path.join(self.models_dir, "performance.json")
        with open(perf_path, 'w') as f:
            json.dump(self.performance, f, indent=2, default=str)

        logger.info(f"Saved {len(self.models)} models to {self.models_dir}")

    def load_models(self):
        """Load saved models"""

        # Load models
        model_files = [f for f in os.listdir(self.models_dir) if f.endswith('.pkl') and 'scaler' not in f]

        for model_file in model_files:
            model_key = model_file.replace('.pkl', '')
            model_path = os.path.join(self.models_dir, model_file)

            try:
                with open(model_path, 'rb') as f:
                    self.models[model_key] = pickle.load(f)
                logger.info(f"Loaded model: {model_key}")
            except Exception as e:
                logger.error(f"Failed to load {model_key}: {e}")

        # Load scalers
        scaler_files = [f for f in os.listdir(self.models_dir) if 'scaler' in f]

        for scaler_file in scaler_files:
            country = scaler_file.replace('_scaler.pkl', '')
            scaler_path = os.path.join(self.models_dir, scaler_file)

            try:
                with open(scaler_path, 'rb') as f:
                    self.scalers[country] = pickle.load(f)
            except Exception as e:
                logger.error(f"Failed to load scaler for {country}: {e}")

        # Load performance
        perf_path = os.path.join(self.models_dir, "performance.json")
        if os.path.exists(perf_path):
            with open(perf_path, 'r') as f:
                self.performance = json.load(f)

        logger.info(f"Loaded {len(self.models)} models from {self.models_dir}")

    def train_all_countries(self, countries: List[str] = None):
        """Train models for all specified countries"""

        if countries is None:
            countries = list(self.GDP_SERIES.keys())

        results = {}

        for country in countries:
            logger.info(f"\n{'='*60}")
            logger.info(f"Training {country}")
            logger.info('='*60)

            try:
                # Train models
                perf = self.train_models(country)

                if perf:
                    # Run backtest
                    backtest = self.backtest(country)

                    results[country] = {
                        'training_performance': perf,
                        'backtest': backtest,
                        'status': 'success'
                    }

                    # Display results
                    if 'ensemble' in backtest:
                        logger.info(f"Backtest MAE: {backtest['ensemble']['mae']:.3f}")
                        logger.info(f"Backtest R²: {backtest['ensemble']['r2']:.3f}")
                else:
                    results[country] = {'status': 'no_data'}

            except Exception as e:
                logger.error(f"Failed to train {country}: {e}")
                results[country] = {'status': 'error', 'error': str(e)}

        # Save all models
        self.save_models()

        # Save training report
        report_path = os.path.join(self.models_dir, "training_report.json")
        with open(report_path, 'w') as f:
            json.dump(results, f, indent=2, default=str)

        logger.info(f"\nTraining complete. Report saved to {report_path}")

        return results


async def train_gdp_models():
    """Main training function"""

    print("="*80)
    print("GDP MODEL TRAINING SYSTEM")
    print("="*80)

    trainer = GDPModelTrainer()

    # Priority countries to train
    priority_countries = [
        'USA',  # United States
        'CHN',  # China
        'JPN',  # Japan
        'DEU',  # Germany
        'GBR',  # United Kingdom
        'IND',  # India
        'FRA',  # France
        'BRA',  # Brazil
        'CAN',  # Canada
        'KOR',  # South Korea
    ]

    print(f"\nTraining models for {len(priority_countries)} priority countries...")

    # Train models
    results = trainer.train_all_countries(priority_countries)

    # Summary
    successful = [c for c, r in results.items() if r.get('status') == 'success']

    print("\n" + "="*80)
    print("TRAINING SUMMARY")
    print("="*80)
    print(f"Successfully trained: {len(successful)}/{len(priority_countries)} countries")

    if successful:
        print("\nTrained countries:")
        for country in successful:
            backtest = results[country].get('backtest', {})
            if 'ensemble' in backtest:
                mae = backtest['ensemble']['mae']
                r2 = backtest['ensemble']['r2']
                print(f"  {country}: MAE={mae:.3f}, R²={r2:.3f}")

    # Test predictions
    print("\n" + "="*80)
    print("TESTING PREDICTIONS")
    print("="*80)

    for country in successful[:3]:  # Test first 3
        predictions = trainer.predict(country)

        if 'ensemble' in predictions:
            print(f"\n{country} GDP Forecast:")
            print(f"  Ensemble: {predictions['ensemble']:.2f}%")
            print(f"  Confidence: {predictions['confidence']:.2%}")
            print(f"  Model predictions:")
            for model, pred in predictions.items():
                if model not in ['ensemble', 'confidence']:
                    print(f"    {model}: {pred:.2f}%")

    print("\n✅ Training complete. Models saved to models/gdp/")

    return results


if __name__ == "__main__":
    asyncio.run(train_gdp_models())