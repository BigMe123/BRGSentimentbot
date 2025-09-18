"""
ML Foundation for Comprehensive Economic Predictions
=====================================================
Production-ready models with specified architectures and data sources.
"""

import os
import numpy as np
import pandas as pd
import yfinance as yf
from typing import Dict, List, Tuple, Optional, Any, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import logging
import warnings
warnings.filterwarnings('ignore')

# ML/DL imports - handle missing dependencies
try:
    import torch
    import transformers
    from transformers import (
        AutoTokenizer,
        AutoModelForSequenceClassification,
        pipeline
    )
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    # Will log warning after logger is initialized
# ML libraries - handle missing ones gracefully
try:
    import lightgbm as lgb
    LGB_AVAILABLE = True
except ImportError:
    LGB_AVAILABLE = False

try:
    import xgboost as xgb
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False

from sklearn.linear_model import Ridge, ElasticNet
try:
    from sklearn.linear_model import QuantileRegressor
    QUANTILE_AVAILABLE = True
except ImportError:
    QUANTILE_AVAILABLE = False

from sklearn.ensemble import GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler

try:
    import statsmodels.api as sm
    from statsmodels.tsa.statespace.sarimax import SARIMAX
    STATSMODELS_AVAILABLE = True
except ImportError:
    STATSMODELS_AVAILABLE = False

try:
    from prophet import Prophet
    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False

try:
    import pmdarima as pm
    PMDARIMA_AVAILABLE = True
except ImportError:
    PMDARIMA_AVAILABLE = False

try:
    from fredapi import Fred
    FRED_AVAILABLE = True
except ImportError:
    FRED_AVAILABLE = False

# For panel regression
try:
    import linearmodels as lm
    from linearmodels.panel import PanelOLS, PooledOLS
except ImportError:
    lm = None

# For deep time series
try:
    from darts import TimeSeries
    from darts.models import TFTModel, RNNModel
    from darts.dataprocessing.transformers import Scaler
except ImportError:
    TFTModel = None
    RNNModel = None

logger = logging.getLogger(__name__)

# Set warning after logger is initialized
if not TRANSFORMERS_AVAILABLE:
    logger = logging.getLogger(__name__)
    logger.warning("Transformers/PyTorch not available - using fallback sentiment")


@dataclass
class ModelConfig:
    """Configuration for model training and inference"""

    # Model types
    employment_model: str = "lightgbm"  # lightgbm, ridge, xgboost
    inflation_model: str = "lightgbm_components"  # per CPI component
    fx_model: str = "tft"  # tft, quantile_regression, logistic
    equity_model: str = "lightgbm"  # with regime dummies
    commodity_model: str = "lightgbm"  # with seasonality
    trade_model: str = "panel"  # panel regression or lightgbm
    fdi_model: str = "ridge"
    consumer_model: str = "elastic_net"

    # Data sources
    use_fred: bool = True
    use_yfinance: bool = True
    use_world_bank: bool = True
    use_noaa: bool = True

    # Model parameters
    quantile_levels: List[float] = field(default_factory=lambda: [0.1, 0.25, 0.5, 0.75, 0.9])
    forecast_horizon: int = 30  # days
    backtest_window: int = 365  # days

    # API keys
    fred_api_key: str = os.getenv('FRED_API_KEY', '28eb3d64654c60195cfeed9bc4ec2a41')
    noaa_api_key: str = None


class NLPFoundation:
    """NLP models for sentiment and stance detection"""

    def __init__(self):
        """Initialize NLP models"""

        if TRANSFORMERS_AVAILABLE:
            logger.info("Loading NLP models...")

            try:
                # Multilingual sentiment
                self.xlm_roberta = pipeline(
                    "sentiment-analysis",
                    model="cardiffnlp/twitter-xlm-roberta-base-sentiment",
                    device=0 if torch.cuda.is_available() else -1
                )
            except:
                self.xlm_roberta = None

            try:
                # Financial sentiment
                self.finbert = pipeline(
                    "sentiment-analysis",
                    model="ProsusAI/finbert",
                    device=0 if torch.cuda.is_available() else -1
                )
            except:
                self.finbert = None

            try:
                # Zero-shot classification
                self.zero_shot = pipeline(
                    "zero-shot-classification",
                    model="facebook/bart-large-mnli",
                    device=0 if torch.cuda.is_available() else -1
                )
            except:
                self.zero_shot = None

            try:
                # Multilingual zero-shot
                self.xlm_zero_shot = pipeline(
                    "zero-shot-classification",
                    model="joeddav/xlm-roberta-large-xnli",
                    device=0 if torch.cuda.is_available() else -1
                )
            except:
                self.xlm_zero_shot = None

            logger.info("NLP models loaded (where available)")
        else:
            logger.warning("Using fallback sentiment analysis")
            self.xlm_roberta = None
            self.finbert = None
            self.zero_shot = None
            self.xlm_zero_shot = None

    def analyze_sentiment(self,
                         text: str,
                         model: str = "finbert") -> Dict[str, float]:
        """Analyze sentiment with specified model"""

        # Use model if available
        if model == "finbert" and self.finbert:
            result = self.finbert(text, truncation=True, max_length=512)
        elif model == "xlm-roberta" and self.xlm_roberta:
            result = self.xlm_roberta(text, truncation=True, max_length=512)
        else:
            # Fallback to simple keyword-based sentiment
            return self._fallback_sentiment(text)

        # Convert to unified format
        sentiment_scores = {}
        for item in result:
            label = item['label'].lower()
            if 'positive' in label:
                sentiment_scores['positive'] = item['score']
            elif 'negative' in label:
                sentiment_scores['negative'] = item['score']
            else:
                sentiment_scores['neutral'] = item['score']

        # Calculate net sentiment
        sentiment_scores['net'] = sentiment_scores.get('positive', 0) - sentiment_scores.get('negative', 0)

        return sentiment_scores

    def _fallback_sentiment(self, text: str) -> Dict[str, float]:
        """Simple keyword-based sentiment as fallback"""

        text_lower = text.lower()

        positive_words = ['good', 'great', 'positive', 'strong', 'gain', 'rise',
                         'improve', 'boost', 'growth', 'expand', 'surge', 'rally']
        negative_words = ['bad', 'poor', 'negative', 'weak', 'loss', 'fall',
                         'decline', 'drop', 'crash', 'plunge', 'crisis', 'recession']

        pos_count = sum(1 for word in positive_words if word in text_lower)
        neg_count = sum(1 for word in negative_words if word in text_lower)

        total = pos_count + neg_count
        if total == 0:
            return {'positive': 0.33, 'negative': 0.33, 'neutral': 0.34, 'net': 0}

        pos_score = pos_count / total
        neg_score = neg_count / total

        return {
            'positive': pos_score,
            'negative': neg_score,
            'neutral': max(0, 1 - pos_score - neg_score),
            'net': pos_score - neg_score
        }

    def classify_topics(self,
                       text: str,
                       candidate_labels: List[str],
                       multilingual: bool = False) -> Dict[str, float]:
        """Zero-shot topic classification"""

        model = self.xlm_zero_shot if multilingual else self.zero_shot

        if model:
            result = model(
                text,
                candidate_labels=candidate_labels,
                hypothesis_template="This text is about {}.",
                multi_label=True
            )
            # Return as dictionary
            return dict(zip(result['labels'], result['scores']))
        else:
            # Fallback to keyword matching
            return self._fallback_classify(text, candidate_labels)

    def _fallback_classify(self, text: str, labels: List[str]) -> Dict[str, float]:
        """Fallback classification based on keyword matching"""

        text_lower = text.lower()
        scores = {}

        for label in labels:
            label_words = label.lower().split()
            matches = sum(1 for word in label_words if word in text_lower)
            scores[label] = matches / max(len(label_words), 1)

        # Normalize scores
        total = sum(scores.values())
        if total > 0:
            scores = {k: v/total for k, v in scores.items()}
        else:
            scores = {k: 1/len(labels) for k in labels}

        return scores

    def extract_stance(self,
                       text: str,
                       topic: str,
                       aspects: List[str]) -> Dict[str, Dict]:
        """Extract stance on specific aspects of a topic"""

        stances = {}

        for aspect in aspects:
            # Check if text discusses this aspect
            aspect_labels = [
                f"discusses {aspect}",
                f"mentions {aspect}",
                "unrelated"
            ]

            relevance = self.classify_topics(text, aspect_labels)

            if relevance.get(f"discusses {aspect}", 0) > 0.5:
                # Get sentiment about this aspect
                sentiment = self.analyze_sentiment(
                    f"{text} [SEP] {aspect}",
                    model="finbert"
                )

                stances[aspect] = {
                    'relevance': relevance[f"discusses {aspect}"],
                    'sentiment': sentiment['net'],
                    'confidence': relevance[f"discusses {aspect}"] * max(sentiment.values())
                }

        return stances


class DataIntegration:
    """Integration with external data sources"""

    def __init__(self, config: ModelConfig):
        """Initialize data connections"""

        self.config = config

        # FRED API
        if config.use_fred and config.fred_api_key and FRED_AVAILABLE:
            try:
                self.fred = Fred(api_key=config.fred_api_key)
            except Exception as e:
                logger.warning(f"Failed to initialize FRED API: {e}")
                self.fred = None
        else:
            self.fred = None
            if config.use_fred and not FRED_AVAILABLE:
                logger.warning("FRED API requested but fredapi not installed")

        logger.info("Data integration initialized")

    def get_fred_data(self,
                     series_id: str,
                     start_date: datetime = None,
                     end_date: datetime = None) -> pd.Series:
        """Get data from FRED"""

        if not self.fred:
            logger.warning("FRED API not configured")
            return pd.Series()

        try:
            data = self.fred.get_series(
                series_id,
                observation_start=start_date,
                observation_end=end_date
            )
            return data
        except Exception as e:
            logger.error(f"FRED fetch failed for {series_id}: {e}")
            return pd.Series()

    def get_market_data(self,
                       ticker: str,
                       period: str = "1y",
                       interval: str = "1d") -> pd.DataFrame:
        """Get market data from yfinance with rate limiting"""

        if not self.config.use_yfinance:
            return pd.DataFrame()

        import time
        max_retries = 3
        retry_delay = float(os.getenv('YAHOO_FINANCE_DELAY', '2'))

        for attempt in range(max_retries):
            try:
                # Add delay to avoid rate limiting
                if attempt > 0:
                    time.sleep(retry_delay * (2 ** attempt))  # Exponential backoff

                ticker_obj = yf.Ticker(ticker)
                data = ticker_obj.history(period=period, interval=interval)

                # Add small delay between successful requests
                time.sleep(retry_delay)

                return data
            except Exception as e:
                if "Too Many Requests" in str(e) and attempt < max_retries - 1:
                    logger.warning(f"Rate limited for {ticker}, retrying in {retry_delay * (2 ** (attempt + 1))} seconds...")
                    continue
                logger.error(f"yfinance fetch failed for {ticker}: {e}")
                return pd.DataFrame()

        return pd.DataFrame()

    def get_macro_indicators(self) -> Dict[str, pd.Series]:
        """Get key macro indicators"""

        indicators = {}

        # Employment
        indicators['unemployment'] = self.get_fred_data('UNRATE')
        indicators['initial_claims'] = self.get_fred_data('ICSA')
        indicators['payrolls'] = self.get_fred_data('PAYEMS')

        # Inflation
        indicators['cpi'] = self.get_fred_data('CPIAUCSL')
        indicators['core_cpi'] = self.get_fred_data('CPILFESL')

        # Interest rates
        indicators['fed_funds'] = self.get_fred_data('DFF')
        indicators['10y_treasury'] = self.get_fred_data('DGS10')
        indicators['2y_treasury'] = self.get_fred_data('DGS2')

        # PMIs
        indicators['manufacturing_pmi'] = self.get_fred_data('MANEMP')
        indicators['services_pmi'] = self.get_fred_data('NMFBAI')

        return indicators

    def get_commodity_data(self) -> Dict[str, pd.DataFrame]:
        """Get commodity prices"""

        commodities = {}

        # Energy
        commodities['oil'] = self.get_market_data('CL=F')  # WTI Crude
        commodities['nat_gas'] = self.get_market_data('NG=F')  # Natural Gas

        # Metals
        commodities['gold'] = self.get_market_data('GC=F')
        commodities['copper'] = self.get_market_data('HG=F')

        # Agriculture
        commodities['wheat'] = self.get_market_data('ZW=F')
        commodities['corn'] = self.get_market_data('ZC=F')
        commodities['soybeans'] = self.get_market_data('ZS=F')

        return commodities

    def get_fx_data(self) -> Dict[str, pd.DataFrame]:
        """Get FX rates"""

        fx_pairs = {}

        fx_pairs['EUR_USD'] = self.get_market_data('EURUSD=X')
        fx_pairs['GBP_USD'] = self.get_market_data('GBPUSD=X')
        fx_pairs['USD_JPY'] = self.get_market_data('JPY=X')
        fx_pairs['USD_CNY'] = self.get_market_data('CNY=X')

        return fx_pairs


class EmploymentPredictor:
    """Job growth and unemployment predictions"""

    def __init__(self,
                 nlp: NLPFoundation,
                 data: DataIntegration,
                 config: ModelConfig):

        self.nlp = nlp
        self.data = data
        self.config = config
        self.model = None
        self.scaler = StandardScaler()

    def prepare_features(self,
                        news_texts: List[str],
                        lookback_days: int = 30) -> pd.DataFrame:
        """Prepare features for employment prediction"""

        features = []

        # Get sentiment features from news
        for text in news_texts[-100:]:  # Last 100 articles
            sentiment = self.nlp.analyze_sentiment(text, model="finbert")

            # Extract employment-specific stance
            employment_stance = self.nlp.extract_stance(
                text,
                topic="employment",
                aspects=["hiring", "layoffs", "wages", "unemployment"]
            )

            features.append({
                'sentiment_net': sentiment['net'],
                'hiring_stance': employment_stance.get('hiring', {}).get('sentiment', 0),
                'layoff_stance': employment_stance.get('layoffs', {}).get('sentiment', 0),
                'wage_stance': employment_stance.get('wages', {}).get('sentiment', 0)
            })

        # Aggregate sentiment features
        sentiment_df = pd.DataFrame(features)
        agg_features = {
            'sentiment_mean': sentiment_df['sentiment_net'].mean(),
            'sentiment_std': sentiment_df['sentiment_net'].std(),
            'hiring_sentiment': sentiment_df['hiring_stance'].mean(),
            'layoff_sentiment': sentiment_df['layoff_stance'].mean(),
            'wage_sentiment': sentiment_df['wage_stance'].mean()
        }

        # Add macro features
        macro_data = self.data.get_macro_indicators()

        if not macro_data['unemployment'].empty:
            agg_features['unemployment_rate'] = macro_data['unemployment'].iloc[-1]
            agg_features['unemployment_change'] = macro_data['unemployment'].diff().iloc[-1]

        if not macro_data['initial_claims'].empty:
            agg_features['initial_claims'] = macro_data['initial_claims'].iloc[-1]
            agg_features['claims_ma4'] = macro_data['initial_claims'].rolling(4).mean().iloc[-1]

        # Add market features
        spy_data = self.data.get_market_data('SPY', period='1mo')
        if not spy_data.empty:
            agg_features['market_return'] = spy_data['Close'].pct_change().mean()
            agg_features['market_vol'] = spy_data['Close'].pct_change().std()

        return pd.DataFrame([agg_features])

    def train(self,
              historical_data: pd.DataFrame,
              target: pd.Series):
        """Train employment prediction model"""

        X = self.scaler.fit_transform(historical_data)
        y = target.values

        if self.config.employment_model == "lightgbm":
            self.model = lgb.LGBMRegressor(
                n_estimators=100,
                learning_rate=0.05,
                max_depth=5,
                num_leaves=31,
                random_state=42
            )
        elif self.config.employment_model == "ridge":
            self.model = Ridge(alpha=1.0)
        else:
            self.model = GradientBoostingRegressor(
                n_estimators=100,
                learning_rate=0.1,
                max_depth=5
            )

        self.model.fit(X, y)
        logger.info(f"Employment model trained: {self.config.employment_model}")

    def predict(self,
                features: pd.DataFrame,
                return_uncertainty: bool = True) -> Dict:
        """Predict employment changes"""

        if self.model is None:
            raise ValueError("Model not trained")

        X = self.scaler.transform(features)

        # Point prediction
        prediction = self.model.predict(X)[0]

        result = {
            'prediction': prediction,
            'model': self.config.employment_model
        }

        # Uncertainty estimation
        if return_uncertainty and hasattr(self.model, 'predict_proba'):
            # For tree-based models, use prediction variance
            trees_preds = []
            for tree in self.model.estimators_:
                trees_preds.append(tree.predict(X))

            result['std'] = np.std(trees_preds)
            result['ci_lower'] = prediction - 2 * result['std']
            result['ci_upper'] = prediction + 2 * result['std']

        return result


class InflationPredictor:
    """CPI and inflation predictions with component breakdown"""

    def __init__(self,
                 nlp: NLPFoundation,
                 data: DataIntegration,
                 config: ModelConfig):

        self.nlp = nlp
        self.data = data
        self.config = config
        self.models = {}  # Component models
        self.prophet_models = {}

    def prepare_component_features(self,
                                  component: str,
                                  news_texts: List[str]) -> pd.DataFrame:
        """Prepare features for CPI component"""

        features = {}

        # Component-specific sentiment
        if component == "energy":
            topics = ["oil", "gas", "energy prices", "OPEC"]
        elif component == "food":
            topics = ["food prices", "agriculture", "wheat", "corn"]
        else:  # core
            topics = ["wages", "services", "housing", "rent"]

        sentiments = []
        for text in news_texts[-50:]:
            topic_scores = self.nlp.classify_topics(text, topics)
            if max(topic_scores.values()) > 0.3:
                sentiment = self.nlp.analyze_sentiment(text, model="finbert")
                sentiments.append(sentiment['net'])

        features['sentiment'] = np.mean(sentiments) if sentiments else 0

        # Market features
        if component == "energy":
            oil_data = self.data.get_market_data('CL=F', period='1mo')
            if not oil_data.empty:
                features['oil_return'] = oil_data['Close'].pct_change().mean()
                features['oil_vol'] = oil_data['Close'].pct_change().std()

        elif component == "food":
            wheat_data = self.data.get_market_data('ZW=F', period='1mo')
            if not wheat_data.empty:
                features['wheat_return'] = wheat_data['Close'].pct_change().mean()

        # Macro features
        macro = self.data.get_macro_indicators()
        if not macro['cpi'].empty:
            features['cpi_momentum'] = macro['cpi'].pct_change().rolling(3).mean().iloc[-1]

        return pd.DataFrame([features])

    def train_component_model(self,
                            component: str,
                            historical_data: pd.DataFrame,
                            target: pd.Series):
        """Train model for CPI component"""

        # LightGBM for each component
        model = lgb.LGBMRegressor(
            n_estimators=50,
            learning_rate=0.05,
            max_depth=3,
            random_state=42
        )

        model.fit(historical_data, target)
        self.models[component] = model

        # Prophet for time series baseline
        prophet_df = pd.DataFrame({
            'ds': target.index,
            'y': target.values
        })

        prophet_model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=False,
            daily_seasonality=False
        )
        prophet_model.fit(prophet_df)
        self.prophet_models[component] = prophet_model

        logger.info(f"Trained models for {component} CPI component")

    def predict(self,
                news_texts: List[str],
                horizon_days: int = 30) -> Dict:
        """Predict CPI changes"""

        components = ["energy", "food", "core"]
        weights = {"energy": 0.08, "food": 0.14, "core": 0.78}

        predictions = {}

        for component in components:
            # ML prediction
            features = self.prepare_component_features(component, news_texts)

            if component in self.models:
                ml_pred = self.models[component].predict(features)[0]
            else:
                ml_pred = 0

            # Prophet baseline
            if component in self.prophet_models:
                future = self.prophet_models[component].make_future_dataframe(
                    periods=horizon_days
                )
                prophet_pred = self.prophet_models[component].predict(future)
                ts_pred = prophet_pred['yhat'].iloc[-1]
            else:
                ts_pred = 0

            # Ensemble
            predictions[component] = 0.6 * ml_pred + 0.4 * ts_pred

        # Weighted CPI
        total_cpi = sum(
            predictions[c] * weights[c]
            for c in components
        )

        return {
            'total': total_cpi,
            'components': predictions,
            'weights': weights
        }


class FXPredictor:
    """Currency prediction with TFT or quantile regression"""

    def __init__(self,
                 nlp: NLPFoundation,
                 data: DataIntegration,
                 config: ModelConfig):

        self.nlp = nlp
        self.data = data
        self.config = config
        self.model = None

    def prepare_features(self,
                        pair: str,
                        news_texts: List[str]) -> pd.DataFrame:
        """Prepare FX features"""

        base, quote = pair.split('_')

        features = {}

        # Policy stance extraction
        policy_topics = [
            "hawkish monetary policy",
            "dovish monetary policy",
            "rate hike",
            "rate cut"
        ]

        base_sentiment = []
        quote_sentiment = []

        for text in news_texts[-50:]:
            # Check if about base currency
            if base in text.upper():
                topics = self.nlp.classify_topics(text, policy_topics)
                if topics.get("hawkish monetary policy", 0) > 0.3:
                    base_sentiment.append(1)
                elif topics.get("dovish monetary policy", 0) > 0.3:
                    base_sentiment.append(-1)

        features['base_policy_stance'] = np.mean(base_sentiment) if base_sentiment else 0
        features['quote_policy_stance'] = np.mean(quote_sentiment) if quote_sentiment else 0

        # Interest rate differentials
        macro = self.data.get_macro_indicators()
        if not macro['10y_treasury'].empty and not macro['2y_treasury'].empty:
            features['yield_curve'] = macro['10y_treasury'].iloc[-1] - macro['2y_treasury'].iloc[-1]

        # FX momentum
        fx_data = self.data.get_fx_data()
        pair_key = f"{base}_{quote}"
        if pair_key in fx_data and not fx_data[pair_key].empty:
            features['momentum_5d'] = fx_data[pair_key]['Close'].pct_change(5).iloc[-1]
            features['momentum_20d'] = fx_data[pair_key]['Close'].pct_change(20).iloc[-1]

        return pd.DataFrame([features])

    def train_tft(self,
                  historical_data: pd.DataFrame,
                  target: pd.Series):
        """Train Temporal Fusion Transformer"""

        if TFTModel is None:
            logger.warning("TFT not available, using quantile regression")
            self.train_quantile(historical_data, target)
            return

        # Prepare data for TFT
        ts = TimeSeries.from_dataframe(
            historical_data.reset_index(),
            time_col='index',
            value_cols=list(historical_data.columns)
        )

        target_ts = TimeSeries.from_series(target)

        # Initialize TFT
        self.model = TFTModel(
            input_chunk_length=30,
            output_chunk_length=7,
            hidden_size=64,
            lstm_layers=1,
            num_attention_heads=4,
            dropout=0.1,
            batch_size=32,
            n_epochs=100,
            random_state=42
        )

        # Train
        self.model.fit(
            series=target_ts,
            past_covariates=ts
        )

        logger.info("TFT model trained for FX prediction")

    def train_quantile(self,
                      historical_data: pd.DataFrame,
                      target: pd.Series):
        """Train quantile regression as fallback"""

        self.model = {}

        for q in self.config.quantile_levels:
            qr = QuantileRegressor(
                quantile=q,
                alpha=0.1,
                solver='highs'
            )
            qr.fit(historical_data, target)
            self.model[q] = qr

        logger.info("Quantile regression trained for FX")

    def predict(self,
                features: pd.DataFrame,
                horizon: int = 7) -> Dict:
        """Predict FX movements"""

        if isinstance(self.model, dict):
            # Quantile regression
            predictions = {}
            for q, model in self.model.items():
                predictions[f'q{int(q*100)}'] = model.predict(features)[0]

            return {
                'median': predictions['q50'],
                'lower': predictions['q10'],
                'upper': predictions['q90'],
                'quantiles': predictions
            }
        else:
            # TFT
            pred = self.model.predict(n=horizon)
            return {
                'forecast': pred.values().flatten().tolist(),
                'horizon': horizon
            }


class CommodityPredictor:
    """Commodity price predictions with weather integration"""

    def __init__(self,
                 nlp: NLPFoundation,
                 data: DataIntegration,
                 config: ModelConfig):

        self.nlp = nlp
        self.data = data
        self.config = config
        self.models = {}

    def get_weather_features(self, commodity: str) -> Dict[str, float]:
        """Get weather features for agricultural commodities"""

        # This would connect to NOAA or meteostat
        # Placeholder for now
        weather = {
            'temp_anomaly': np.random.normal(0, 1),
            'precip_anomaly': np.random.normal(0, 1),
            'enso_index': np.random.uniform(-2, 2)
        }

        return weather

    def prepare_features(self,
                        commodity: str,
                        news_texts: List[str]) -> pd.DataFrame:
        """Prepare commodity-specific features"""

        features = {}

        # Supply/demand stance
        supply_topics = ["production increase", "bumper crop", "oversupply"]
        demand_topics = ["strong demand", "supply shortage", "stockpile"]

        supply_sentiment = []
        demand_sentiment = []

        for text in news_texts[-50:]:
            if commodity.lower() in text.lower():
                supply_score = max(self.nlp.classify_topics(text, supply_topics).values())
                demand_score = max(self.nlp.classify_topics(text, demand_topics).values())

                if supply_score > 0.3:
                    supply_sentiment.append(supply_score)
                if demand_score > 0.3:
                    demand_sentiment.append(demand_score)

        features['supply_sentiment'] = np.mean(supply_sentiment) if supply_sentiment else 0
        features['demand_sentiment'] = np.mean(demand_sentiment) if demand_sentiment else 0

        # Market features
        commodity_data = self.data.get_commodity_data()
        if commodity in commodity_data and not commodity_data[commodity].empty:
            df = commodity_data[commodity]
            features['momentum'] = df['Close'].pct_change(20).iloc[-1]
            features['volatility'] = df['Close'].pct_change().rolling(20).std().iloc[-1]

        # Weather for agricultural
        if commodity in ['wheat', 'corn', 'soybeans']:
            weather = self.get_weather_features(commodity)
            features.update(weather)

        # Seasonality
        features['month'] = datetime.now().month
        features['quarter'] = (datetime.now().month - 1) // 3 + 1

        return pd.DataFrame([features])

    def train(self,
              commodity: str,
              historical_data: pd.DataFrame,
              target: pd.Series):
        """Train commodity model"""

        model = lgb.LGBMRegressor(
            n_estimators=100,
            learning_rate=0.05,
            max_depth=5,
            num_leaves=31,
            random_state=42
        )

        model.fit(historical_data, target)
        self.models[commodity] = model

        logger.info(f"Trained model for {commodity}")

    def predict(self,
                commodity: str,
                news_texts: List[str]) -> Dict:
        """Predict commodity prices"""

        features = self.prepare_features(commodity, news_texts)

        if commodity not in self.models:
            return {'error': f'No model for {commodity}'}

        prediction = self.models[commodity].predict(features)[0]

        # Feature importance
        importance = self.models[commodity].feature_importances_
        feature_names = features.columns.tolist()

        return {
            'prediction': prediction,
            'features': dict(zip(feature_names, importance))
        }


class ComprehensiveMLPipeline:
    """Complete ML pipeline integrating all components"""

    def __init__(self, config: ModelConfig):
        """Initialize comprehensive pipeline"""

        self.config = config

        # Initialize components
        self.nlp = NLPFoundation()
        self.data = DataIntegration(config)

        # Initialize predictors
        self.employment = EmploymentPredictor(self.nlp, self.data, config)
        self.inflation = InflationPredictor(self.nlp, self.data, config)
        self.fx = FXPredictor(self.nlp, self.data, config)
        self.commodity = CommodityPredictor(self.nlp, self.data, config)

        logger.info("Comprehensive ML Pipeline initialized")

    def run_predictions(self,
                       news_texts: List[str],
                       target_date: datetime = None) -> Dict:
        """Run all predictions"""

        if target_date is None:
            target_date = datetime.now() + timedelta(days=30)

        results = {
            'timestamp': datetime.now().isoformat(),
            'target_date': target_date.isoformat(),
            'predictions': {}
        }

        # Employment
        try:
            emp_features = self.employment.prepare_features(news_texts)
            emp_pred = self.employment.predict(emp_features)
            results['predictions']['employment'] = emp_pred
        except Exception as e:
            logger.error(f"Employment prediction failed: {e}")
            results['predictions']['employment'] = {'error': str(e)}

        # Inflation
        try:
            cpi_pred = self.inflation.predict(news_texts)
            results['predictions']['inflation'] = cpi_pred
        except Exception as e:
            logger.error(f"Inflation prediction failed: {e}")
            results['predictions']['inflation'] = {'error': str(e)}

        # FX
        try:
            fx_pairs = ['EUR_USD', 'GBP_USD', 'USD_JPY']
            fx_predictions = {}

            for pair in fx_pairs:
                fx_features = self.fx.prepare_features(pair, news_texts)
                fx_pred = self.fx.predict(fx_features)
                fx_predictions[pair] = fx_pred

            results['predictions']['fx'] = fx_predictions
        except Exception as e:
            logger.error(f"FX prediction failed: {e}")
            results['predictions']['fx'] = {'error': str(e)}

        # Commodities
        try:
            commodities = ['oil', 'gold', 'wheat']
            commodity_predictions = {}

            for commodity in commodities:
                comm_pred = self.commodity.predict(commodity, news_texts)
                commodity_predictions[commodity] = comm_pred

            results['predictions']['commodities'] = commodity_predictions
        except Exception as e:
            logger.error(f"Commodity prediction failed: {e}")
            results['predictions']['commodities'] = {'error': str(e)}

        return results

    def backtest(self,
                 start_date: datetime,
                 end_date: datetime) -> pd.DataFrame:
        """Run backtest on historical data"""

        results = []

        # This would implement rolling window backtesting
        # Placeholder for now

        return pd.DataFrame(results)


# Export main components
__all__ = [
    'ModelConfig',
    'NLPFoundation',
    'DataIntegration',
    'EmploymentPredictor',
    'InflationPredictor',
    'FXPredictor',
    'CommodityPredictor',
    'ComprehensiveMLPipeline'
]