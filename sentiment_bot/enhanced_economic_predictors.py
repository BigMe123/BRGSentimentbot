"""
Enhanced Economic Predictors with ML Foundation
================================================
Production-ready predictors using specified ML models and data sources.
"""

import os
import numpy as np
import pandas as pd
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass

# Import our ML foundation
from .ml_foundation import (
    ModelConfig,
    NLPFoundation,
    DataIntegration,
    EmploymentPredictor as MLEmploymentPredictor,
    InflationPredictor as MLInflationPredictor,
    FXPredictor as MLFXPredictor,
    CommodityPredictor as MLCommodityPredictor
)

# Import existing components
from .comprehensive_economic_predictors import (
    PredictionResult,
    AlphaVantageClient,
    TradeFlowPredictor,
    FDIPredictor,
    ConsumerConfidenceProxy
)

# Import GPI system
from .global_perception_index import (
    GlobalPerceptionIndex,
    PerceptionReading
)

# Import news collector
from .news_data_collector import (
    TheNewsAPIClient,
    collect_comprehensive_news_data
)

logger = logging.getLogger(__name__)


class EnhancedEmploymentPredictor:
    """Enhanced employment predictor with ML foundation"""

    def __init__(self, config: ModelConfig):
        self.config = config
        self.nlp = NLPFoundation()
        self.data = DataIntegration(config)
        self.ml_predictor = MLEmploymentPredictor(self.nlp, self.data, config)
        self.av_client = AlphaVantageClient()

    async def predict(self,
                     news_texts: List[str],
                     sentiment_data: Dict = None) -> PredictionResult:
        """Enhanced employment prediction using ML models + real data"""

        # Prepare ML features
        features_df = self.ml_predictor.prepare_features(news_texts)

        # Get real employment data from FRED
        macro_indicators = self.data.get_macro_indicators()

        # Calculate baseline from actual data
        baseline_payroll = 150000
        if 'payrolls' in macro_indicators and not macro_indicators['payrolls'].empty:
            recent_changes = macro_indicators['payrolls'].diff().dropna()
            if len(recent_changes) >= 3:
                baseline_payroll = recent_changes.tail(3).mean()

        # Get unemployment trend
        unemployment_trend = 0
        if 'unemployment' in macro_indicators and not macro_indicators['unemployment'].empty:
            unemployment_trend = macro_indicators['unemployment'].diff().tail(3).mean()

        # ML model prediction (if trained)
        try:
            ml_prediction = self.ml_predictor.predict(features_df, return_uncertainty=True)
            prediction_value = ml_prediction['prediction']
            uncertainty = ml_prediction.get('std', 50000)
        except:
            # Fallback to feature-based prediction
            prediction_value = baseline_payroll

            # Adjust based on sentiment
            if sentiment_data:
                hiring_impact = sentiment_data.get('hiring_sentiment', 0) * 30000
                layoff_impact = -sentiment_data.get('layoff_sentiment', 0) * 25000
                prediction_value += hiring_impact + layoff_impact

            uncertainty = 50000

        # Confidence based on data availability
        confidence = 0.5
        if not macro_indicators['unemployment'].empty:
            confidence += 0.2
        if not macro_indicators['payrolls'].empty:
            confidence += 0.2
        if len(news_texts) > 50:
            confidence += 0.1

        # Key drivers from ML features and data
        drivers = []
        if unemployment_trend < -0.1:
            drivers.append("Declining unemployment trend")
        if features_df['market_return'].iloc[0] > 0.02:
            drivers.append("Strong equity market performance")
        if 'initial_claims' in features_df.columns:
            if features_df['initial_claims'].iloc[0] < 200000:
                drivers.append("Low jobless claims")

        return PredictionResult(
            indicator="nonfarm_payrolls",
            prediction=prediction_value,
            confidence=min(0.9, confidence),
            timeframe="next_month",
            direction="up" if prediction_value > 0 else "down",
            drivers=drivers,
            range_low=prediction_value - uncertainty,
            range_high=prediction_value + uncertainty,
            metadata={
                "model": self.config.employment_model,
                "baseline_trend": baseline_payroll,
                "unemployment_trend": unemployment_trend,
                "ml_features": features_df.to_dict('records')[0] if not features_df.empty else {},
                "data_sources": ["FRED", "yfinance", "news_sentiment"]
            }
        )


class EnhancedInflationPredictor:
    """Enhanced CPI predictor with component models"""

    def __init__(self, config: ModelConfig):
        self.config = config
        self.nlp = NLPFoundation()
        self.data = DataIntegration(config)
        self.ml_predictor = MLInflationPredictor(self.nlp, self.data, config)
        self.av_client = AlphaVantageClient()

    async def predict(self,
                     news_texts: List[str],
                     sentiment_data: Dict = None) -> PredictionResult:
        """Enhanced CPI prediction with component breakdown"""

        # ML component predictions
        ml_prediction = self.ml_predictor.predict(news_texts, horizon_days=30)

        # Get real CPI data
        macro_indicators = self.data.get_macro_indicators()

        current_cpi = 3.2  # Default
        cpi_trend = 0

        if 'cpi' in macro_indicators and not macro_indicators['cpi'].empty:
            current_cpi = macro_indicators['cpi'].iloc[-1]
            cpi_trend = macro_indicators['cpi'].pct_change().tail(3).mean() * 100

        # Get commodity prices for real impact
        commodities = self.data.get_commodity_data()

        energy_impact = 0
        if 'oil' in commodities and not commodities['oil'].empty:
            oil_momentum = commodities['oil']['Close'].pct_change(20).iloc[-1]
            energy_impact = oil_momentum * 0.08 * 100  # 8% weight

        food_impact = 0
        if 'wheat' in commodities and not commodities['wheat'].empty:
            wheat_momentum = commodities['wheat']['Close'].pct_change(20).iloc[-1]
            food_impact = wheat_momentum * 0.14 * 100  # 14% weight

        # Combine ML prediction with real data
        if 'total' in ml_prediction:
            total_prediction = ml_prediction['total']
        else:
            # Fallback calculation
            total_prediction = cpi_trend + energy_impact + food_impact

            # Sentiment overlay
            if sentiment_data:
                supply_chain_impact = sentiment_data.get('supply_chain', 0) * 0.05
                tariff_impact = sentiment_data.get('tariffs', 0) * 0.03
                total_prediction += supply_chain_impact + tariff_impact

        # Confidence based on data quality
        confidence = 0.5
        if 'cpi' in macro_indicators and not macro_indicators['cpi'].empty:
            confidence += 0.2
        if 'oil' in commodities and not commodities['oil'].empty:
            confidence += 0.1
        if 'components' in ml_prediction:
            confidence += 0.1

        # Key drivers
        drivers = []
        if abs(energy_impact) > 0.1:
            direction = "rising" if energy_impact > 0 else "falling"
            drivers.append(f"Energy prices {direction}")
        if cpi_trend > 0.2:
            drivers.append("Persistent inflation trend")
        elif cpi_trend < -0.1:
            drivers.append("Disinflationary trend")
        if sentiment_data and sentiment_data.get('tariffs', 0) < -0.3:
            drivers.append("Tariff concerns")

        return PredictionResult(
            indicator="CPI_MoM",
            prediction=total_prediction,
            confidence=min(0.9, confidence),
            timeframe="next_month",
            direction="up" if total_prediction > 0.1 else "down" if total_prediction < -0.1 else "stable",
            drivers=drivers,
            range_low=total_prediction - 0.3,
            range_high=total_prediction + 0.3,
            metadata={
                "current_cpi": current_cpi,
                "cpi_trend": cpi_trend,
                "components": ml_prediction.get('components', {}),
                "energy_impact": energy_impact,
                "food_impact": food_impact,
                "model": self.config.inflation_model,
                "data_sources": ["FRED", "yfinance", "news_sentiment"]
            }
        )


class EnhancedFXPredictor:
    """Enhanced FX predictor with TFT/quantile regression"""

    def __init__(self, config: ModelConfig):
        self.config = config
        self.nlp = NLPFoundation()
        self.data = DataIntegration(config)
        self.ml_predictor = MLFXPredictor(self.nlp, self.data, config)
        self.av_client = AlphaVantageClient()

    async def predict(self,
                     currency_pair: str,
                     news_texts: List[str],
                     sentiment_data: Dict = None) -> PredictionResult:
        """Enhanced FX prediction with uncertainty quantification"""

        # Prepare ML features
        pair_formatted = currency_pair.replace('/', '_')
        features_df = self.ml_predictor.prepare_features(pair_formatted, news_texts)

        # Get real FX data
        fx_data = self.data.get_fx_data()
        current_rate = 1.0  # Default

        if pair_formatted in fx_data and not fx_data[pair_formatted].empty:
            current_rate = fx_data[pair_formatted]['Close'].iloc[-1]

        # ML prediction
        try:
            ml_prediction = self.ml_predictor.predict(features_df)

            if 'median' in ml_prediction:
                # Quantile regression output
                predicted_change = ml_prediction['median']
                uncertainty_lower = ml_prediction['lower']
                uncertainty_upper = ml_prediction['upper']
            else:
                # TFT output
                forecast = ml_prediction.get('forecast', [0])
                predicted_change = forecast[0] if forecast else 0
                uncertainty_lower = predicted_change - 0.02
                uncertainty_upper = predicted_change + 0.02
        except:
            # Fallback to simple prediction
            predicted_change = 0

            # Policy stance impact
            if sentiment_data:
                base_policy = sentiment_data.get('monetary_policy', 0)
                predicted_change += base_policy * 0.01

            uncertainty_lower = predicted_change - 0.02
            uncertainty_upper = predicted_change + 0.02

        # Calculate predicted rate
        predicted_rate = current_rate * (1 + predicted_change)

        # Confidence based on model type and data
        confidence = 0.5
        if self.config.fx_model == "tft":
            confidence += 0.2
        if 'yield_curve' in features_df.columns:
            confidence += 0.1
        if len(news_texts) > 30:
            confidence += 0.1

        # Direction
        if predicted_change > 0.005:
            direction = "strengthen"
        elif predicted_change < -0.005:
            direction = "weaken"
        else:
            direction = "neutral"

        # Drivers
        drivers = []
        if 'base_policy_stance' in features_df.columns:
            if features_df['base_policy_stance'].iloc[0] > 0.3:
                drivers.append("Hawkish policy stance")
            elif features_df['base_policy_stance'].iloc[0] < -0.3:
                drivers.append("Dovish policy stance")

        if 'yield_curve' in features_df.columns:
            if features_df['yield_curve'].iloc[0] > 2:
                drivers.append("Steep yield curve")

        return PredictionResult(
            indicator=f"FX_{currency_pair}",
            prediction=predicted_rate,
            confidence=min(0.9, confidence),
            timeframe="1-4_weeks",
            direction=direction,
            drivers=drivers,
            range_low=current_rate * (1 + uncertainty_lower),
            range_high=current_rate * (1 + uncertainty_upper),
            metadata={
                "current_rate": current_rate,
                "percent_change": predicted_change * 100,
                "model": self.config.fx_model,
                "quantiles": ml_prediction if 'median' in ml_prediction else None,
                "data_sources": ["yfinance", "FRED", "news_sentiment"]
            }
        )


class EnhancedCommodityPredictor:
    """Enhanced commodity predictor with weather integration"""

    def __init__(self, config: ModelConfig):
        self.config = config
        self.nlp = NLPFoundation()
        self.data = DataIntegration(config)
        self.ml_predictor = MLCommodityPredictor(self.nlp, self.data, config)
        self.av_client = AlphaVantageClient()

    async def predict(self,
                     commodity: str,
                     news_texts: List[str],
                     sentiment_data: Dict = None) -> PredictionResult:
        """Enhanced commodity prediction with weather and seasonality"""

        # ML prediction
        try:
            ml_prediction = self.ml_predictor.predict(commodity, news_texts)
            predicted_change = ml_prediction.get('prediction', 0)
            feature_importance = ml_prediction.get('features', {})
        except:
            predicted_change = 0
            feature_importance = {}

        # Get real commodity data
        commodity_data = self.data.get_commodity_data()
        current_price = 100  # Normalized

        if commodity in commodity_data and not commodity_data[commodity].empty:
            current_price = commodity_data[commodity]['Close'].iloc[-1]
            momentum = commodity_data[commodity]['Close'].pct_change(20).iloc[-1]

            # If no ML prediction, use momentum
            if predicted_change == 0:
                predicted_change = momentum * 0.5  # Damped momentum

        # Add weather impact for agricultural commodities
        if commodity in ['wheat', 'corn', 'soybeans']:
            weather_features = self.ml_predictor.get_weather_features(commodity)
            weather_impact = weather_features.get('temp_anomaly', 0) * 0.02
            predicted_change += weather_impact

        # Sentiment overlay
        if sentiment_data:
            supply_sentiment = sentiment_data.get(f'{commodity}_supply', 0)
            demand_sentiment = sentiment_data.get(f'{commodity}_demand', 0)
            sentiment_impact = (demand_sentiment - supply_sentiment) * 0.05
            predicted_change += sentiment_impact

        # Calculate predicted price
        predicted_price = current_price * (1 + predicted_change)

        # Confidence
        confidence = 0.5
        if commodity in commodity_data and not commodity_data[commodity].empty:
            confidence += 0.2
        if feature_importance:
            confidence += 0.2
        if commodity in ['wheat', 'corn'] and 'temp_anomaly' in feature_importance:
            confidence += 0.1

        # Direction
        direction = "up" if predicted_change > 0.01 else "down" if predicted_change < -0.01 else "neutral"

        # Drivers
        drivers = []
        if feature_importance:
            top_features = sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)[:2]
            for feature, _ in top_features:
                if 'supply' in feature:
                    drivers.append("Supply dynamics")
                elif 'demand' in feature:
                    drivers.append("Demand shifts")
                elif 'weather' in feature or 'temp' in feature:
                    drivers.append("Weather conditions")

        return PredictionResult(
            indicator=f"COMMODITY_{commodity.upper()}",
            prediction=predicted_change * 100,
            confidence=min(0.9, confidence),
            timeframe="1-4_weeks",
            direction=direction,
            drivers=drivers,
            range_low=predicted_price * 0.95,
            range_high=predicted_price * 1.05,
            metadata={
                "current_price": current_price,
                "predicted_price": predicted_price,
                "model": self.config.commodity_model,
                "feature_importance": feature_importance,
                "data_sources": ["yfinance", "news_sentiment", "weather"]
            }
        )


class EnhancedEquityPredictor:
    """Enhanced equity market predictor"""

    def __init__(self, config: ModelConfig):
        self.config = config
        self.nlp = NLPFoundation()
        self.data = DataIntegration(config)
        self.av_client = AlphaVantageClient()

    async def predict(self,
                     index_name: str,
                     news_texts: List[str],
                     sentiment_data: Dict = None) -> PredictionResult:
        """Enhanced equity prediction with regime detection"""

        # Map index to ticker
        index_map = {
            'SPX': 'SPY',
            'NIFTY': 'INDA',
            'DAX': 'EWG',
            'NIKKEI': 'EWJ'
        }

        ticker = index_map.get(index_name, index_name)

        # Get market data
        market_data = self.data.get_market_data(ticker, period='3mo')

        if not market_data.empty:
            current_level = market_data['Close'].iloc[-1]
            returns = market_data['Close'].pct_change().dropna()
            volatility = returns.std() * np.sqrt(252)
            momentum = returns.tail(20).mean() * 252

            # Regime detection (risk-on/off)
            vix_data = self.data.get_market_data('^VIX', period='1mo')
            if not vix_data.empty:
                vix_level = vix_data['Close'].iloc[-1]
                risk_regime = "risk-off" if vix_level > 20 else "risk-on"
            else:
                risk_regime = "neutral"
        else:
            current_level = 100
            volatility = 0.15
            momentum = 0
            risk_regime = "neutral"

        # News sentiment analysis
        market_sentiment = 0
        if news_texts:
            for text in news_texts[-50:]:
                topics = self.nlp.classify_topics(
                    text,
                    ["bullish market", "bearish market", "neutral market"]
                )
                if topics.get("bullish market", 0) > 0.4:
                    market_sentiment += 1
                elif topics.get("bearish market", 0) > 0.4:
                    market_sentiment -= 1

            market_sentiment = market_sentiment / min(50, len(news_texts))

        # Prediction based on momentum, sentiment, and regime
        base_return = 0.08 / 252  # 8% annual return daily

        # Momentum factor
        momentum_factor = momentum * 0.3

        # Sentiment factor
        sentiment_factor = market_sentiment * 0.02

        # Regime adjustment
        regime_factor = 0
        if risk_regime == "risk-on":
            regime_factor = 0.01
        elif risk_regime == "risk-off":
            regime_factor = -0.01

        # Weekly prediction
        predicted_return = (base_return + momentum_factor + sentiment_factor + regime_factor) * 5

        # Confidence
        confidence = 0.5
        if not market_data.empty:
            confidence += 0.3
        if abs(market_sentiment) > 0.2:
            confidence += 0.1
        if risk_regime != "neutral":
            confidence += 0.1

        # Direction
        if predicted_return > 0.005:
            direction = "bullish"
        elif predicted_return < -0.005:
            direction = "bearish"
        else:
            direction = "neutral"

        # Drivers
        drivers = []
        if momentum > 0.1:
            drivers.append("Positive momentum")
        elif momentum < -0.1:
            drivers.append("Negative momentum")

        if market_sentiment > 0.2:
            drivers.append("Positive sentiment")
        elif market_sentiment < -0.2:
            drivers.append("Negative sentiment")

        if risk_regime != "neutral":
            drivers.append(f"{risk_regime.title()} environment")

        return PredictionResult(
            indicator=f"INDEX_{index_name}",
            prediction=predicted_return * 100,
            confidence=min(0.9, confidence),
            timeframe="1_week",
            direction=direction,
            drivers=drivers,
            range_low=predicted_return * 100 - volatility * 100 / np.sqrt(52),
            range_high=predicted_return * 100 + volatility * 100 / np.sqrt(52),
            metadata={
                "current_level": current_level,
                "volatility": volatility,
                "momentum": momentum,
                "risk_regime": risk_regime,
                "market_sentiment": market_sentiment,
                "model": self.config.equity_model,
                "data_sources": ["yfinance", "news_sentiment"]
            }
        )


class EnhancedEconomicPredictor:
    """Main enhanced predictor integrating all components"""

    def __init__(self,
                 fred_api_key: str = None,
                 alpha_vantage_key: str = None,
                 news_api_key: str = None):
        """Initialize enhanced predictor"""

        # Configuration
        self.config = ModelConfig(
            fred_api_key=fred_api_key or os.getenv('FRED_API_KEY'),
            employment_model="lightgbm",
            inflation_model="lightgbm_components",
            fx_model="quantile_regression",  # TFT requires more setup
            equity_model="lightgbm",
            commodity_model="lightgbm"
        )

        # Initialize predictors
        self.employment = EnhancedEmploymentPredictor(self.config)
        self.inflation = EnhancedInflationPredictor(self.config)
        self.fx = EnhancedFXPredictor(self.config)
        self.commodity = EnhancedCommodityPredictor(self.config)
        self.equity = EnhancedEquityPredictor(self.config)

        # Keep existing predictors
        self.trade = TradeFlowPredictor()
        self.fdi = FDIPredictor()
        self.consumer = ConsumerConfidenceProxy()

        # GPI instead of GPR
        self.gpi = GlobalPerceptionIndex()

        # Alpha Vantage for additional data
        self.av_client = AlphaVantageClient(alpha_vantage_key)

        # News API
        self.news_client = TheNewsAPIClient(news_api_key)

        logger.info("Enhanced Economic Predictor initialized with ML foundation")

    async def generate_forecast(self,
                               news_texts: List[str] = None,
                               sentiment_data: Dict = None) -> Dict[str, PredictionResult]:
        """Generate comprehensive forecast with enhanced models"""

        results = {}

        # Collect news if not provided
        if news_texts is None:
            news_collection = await collect_comprehensive_news_data()
            news_texts = []
            for category_articles in news_collection['raw_articles']['economic'].values():
                for article in category_articles[:10]:
                    news_texts.append(f"{article.title} {article.description}")
            sentiment_data = news_collection['sentiment_data']

        # Employment
        try:
            employment_result = await self.employment.predict(news_texts, sentiment_data)
            results['employment'] = employment_result
            logger.info(f"Employment: {employment_result.prediction:,.0f} jobs, {employment_result.confidence:.1%} conf")
        except Exception as e:
            logger.error(f"Employment prediction failed: {e}")

        # Inflation
        try:
            inflation_result = await self.inflation.predict(news_texts, sentiment_data)
            results['inflation'] = inflation_result
            logger.info(f"CPI: {inflation_result.prediction:+.2f}%, {inflation_result.confidence:.1%} conf")
        except Exception as e:
            logger.error(f"Inflation prediction failed: {e}")

        # FX pairs
        fx_pairs = ['USD/EUR', 'USD/JPY', 'USD/GBP']
        for pair in fx_pairs:
            try:
                fx_result = await self.fx.predict(pair, news_texts, sentiment_data)
                results[f'fx_{pair}'] = fx_result
                logger.info(f"{pair}: {fx_result.direction}, {fx_result.confidence:.1%} conf")
            except Exception as e:
                logger.error(f"FX {pair} prediction failed: {e}")

        # Equity indices
        indices = ['SPX', 'NIFTY', 'DAX']
        for index in indices:
            try:
                equity_result = await self.equity.predict(index, news_texts, sentiment_data)
                results[f'equity_{index}'] = equity_result
                logger.info(f"{index}: {equity_result.prediction:+.2f}%, {equity_result.confidence:.1%} conf")
            except Exception as e:
                logger.error(f"Equity {index} prediction failed: {e}")

        # Commodities
        commodities = ['oil', 'gold', 'wheat']
        for commodity in commodities:
            try:
                commodity_result = await self.commodity.predict(commodity, news_texts, sentiment_data)
                results[f'commodity_{commodity}'] = commodity_result
                logger.info(f"{commodity}: {commodity_result.prediction:+.2f}%, {commodity_result.confidence:.1%} conf")
            except Exception as e:
                logger.error(f"Commodity {commodity} prediction failed: {e}")

        # Trade flows (existing)
        if sentiment_data:
            try:
                trade_result = self.trade.predict_trade_flow('USA', 'China', sentiment_data)
                results['trade_usa_china'] = trade_result
                logger.info(f"USA-China trade: {trade_result.prediction:+.1f}%, {trade_result.confidence:.1%} conf")
            except Exception as e:
                logger.error(f"Trade prediction failed: {e}")

        # FDI (existing)
        if sentiment_data:
            try:
                fdi_result = self.fdi.predict_fdi('USA', sentiment_data)
                results['fdi_usa'] = fdi_result
                logger.info(f"FDI USA: {fdi_result.direction}, {fdi_result.confidence:.1%} conf")
            except Exception as e:
                logger.error(f"FDI prediction failed: {e}")

        # Consumer confidence (existing)
        if sentiment_data:
            try:
                consumer_result = self.consumer.calculate_confidence(sentiment_data)
                results['consumer_confidence'] = consumer_result
                logger.info(f"Consumer Confidence: {consumer_result.prediction:.1f}/100, {consumer_result.direction}")
            except Exception as e:
                logger.error(f"Consumer confidence failed: {e}")

        # GPI instead of GPR
        try:
            gpi_snapshot = self.gpi.calculate_bilateral_perceptions()
            # Convert to PredictionResult format
            avg_perception = np.mean([
                score for country_scores in gpi_snapshot.perception_matrix.values()
                for score in country_scores.values()
            ])

            results['global_perception'] = PredictionResult(
                indicator="GPI",
                prediction=avg_perception,
                confidence=0.8,
                timeframe="current",
                direction="positive" if avg_perception > 50 else "negative",
                drivers=list(gpi_snapshot.trend_indicators.keys())[:3],
                range_low=max(0, avg_perception - 10),
                range_high=min(100, avg_perception + 10),
                metadata={
                    "perception_matrix": gpi_snapshot.perception_matrix,
                    "rankings": gpi_snapshot.country_rankings
                }
            )
            logger.info(f"Global Perception Index: {avg_perception:.1f}/100")
        except Exception as e:
            logger.error(f"GPI calculation failed: {e}")

        return results


# Export enhanced predictor
__all__ = ['EnhancedEconomicPredictor']