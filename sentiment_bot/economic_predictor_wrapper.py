#!/usr/bin/env python3
"""
Economic Predictor Wrapper - Fixed and Standardized Interface
=============================================================
Provides a unified interface to all economic predictors with proper
error handling, fallbacks, and corrected method signatures.
"""

import os
import sys
import asyncio
import logging
import time
from typing import Dict, List, Any, Optional
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Import the predictor modules
from sentiment_bot.comprehensive_economic_predictors import (
    ComprehensiveEconomicPredictor,
    AlphaVantageClient
)
from sentiment_bot.enhanced_economic_predictors import EnhancedEconomicPredictor
from sentiment_bot.ml_foundation import ModelConfig, DataIntegration


class UnifiedEconomicPredictor:
    """Unified wrapper for all economic predictors with fixes"""

    def __init__(self):
        """Initialize with proper configurations"""

        # Set up API keys
        os.environ['FRED_API_KEY'] = '28eb3d64654c60195cfeed9bc4ec2a41'
        os.environ['ALPHA_VANTAGE_API_KEY'] = 'YILWUFW6VO1RA561'
        os.environ['YAHOO_FINANCE_DELAY'] = '2'

        # Initialize config
        self.config = ModelConfig()
        self.config.fred_api_key = os.getenv('FRED_API_KEY')
        self.config.use_fred = True
        self.config.use_yfinance = True

        # Initialize Alpha Vantage client
        self.av_client = AlphaVantageClient()

        # Initialize predictors
        try:
            self.comprehensive = ComprehensiveEconomicPredictor()
            logger.info("✅ Comprehensive predictor initialized")
        except Exception as e:
            logger.error(f"Failed to initialize comprehensive predictor: {e}")
            self.comprehensive = None

        try:
            self.enhanced = EnhancedEconomicPredictor()
            logger.info("✅ Enhanced predictor initialized")
        except Exception as e:
            logger.error(f"Failed to initialize enhanced predictor: {e}")
            self.enhanced = None

    async def predict_gdp(self, country: str = 'USA') -> Dict:
        """Predict GDP growth with proper error handling"""

        result = {
            'indicator': 'GDP Growth',
            'country': country,
            'status': 'unknown',
            'prediction': None,
            'confidence': 0.0
        }

        try:
            # Get real GDP data from FRED
            data_integration = DataIntegration(self.config)
            gdp_series = data_integration.get_fred_data('GDPC1')

            if not gdp_series.empty:
                # Calculate growth rate
                gdp_growth = gdp_series.pct_change(periods=4).iloc[-1] * 100
                result['prediction'] = round(gdp_growth, 2)
                result['confidence'] = 0.75
                result['status'] = 'success'
                result['source'] = 'FRED'
            else:
                # Fallback prediction
                result['prediction'] = 2.5
                result['confidence'] = 0.3
                result['status'] = 'fallback'

        except Exception as e:
            logger.error(f"GDP prediction failed: {e}")
            result['prediction'] = 2.5
            result['confidence'] = 0.2
            result['status'] = 'error'
            result['error'] = str(e)

        return result

    async def predict_inflation(self, country: str = 'USA') -> Dict:
        """Predict inflation/CPI with proper error handling"""

        result = {
            'indicator': 'CPI/Inflation',
            'country': country,
            'status': 'unknown',
            'prediction': None,
            'confidence': 0.0
        }

        try:
            # Get CPI data from FRED
            data_integration = DataIntegration(self.config)
            cpi_series = data_integration.get_fred_data('CPIAUCSL')

            if not cpi_series.empty:
                # Calculate inflation rate
                inflation = cpi_series.pct_change(periods=12).iloc[-1] * 100
                result['prediction'] = round(inflation, 2)
                result['confidence'] = 0.8
                result['status'] = 'success'
                result['source'] = 'FRED'
            else:
                # Try Alpha Vantage
                async with self.av_client as client:
                    cpi_data = await client.get_economic_indicator('CPI')
                    if not cpi_data.empty:
                        result['prediction'] = cpi_data['value'].iloc[-1]
                        result['confidence'] = 0.7
                        result['status'] = 'success'
                        result['source'] = 'Alpha Vantage'
                    else:
                        # Fallback
                        result['prediction'] = 3.2
                        result['confidence'] = 0.3
                        result['status'] = 'fallback'

        except Exception as e:
            logger.error(f"Inflation prediction failed: {e}")
            result['prediction'] = 3.2
            result['confidence'] = 0.2
            result['status'] = 'error'
            result['error'] = str(e)

        return result

    async def predict_currency(self, from_currency: str = 'USD', to_currency: str = 'EUR') -> Dict:
        """Predict currency exchange rates with proper error handling"""

        result = {
            'indicator': f'{from_currency}/{to_currency}',
            'status': 'unknown',
            'prediction': None,
            'confidence': 0.0
        }

        try:
            # Get forex data from Alpha Vantage
            async with self.av_client as client:
                forex_data = await client.get_forex_rate(from_currency, to_currency)

                if forex_data and 'rate' in forex_data:
                    result['prediction'] = round(forex_data['rate'], 4)
                    result['confidence'] = 0.9
                    result['status'] = 'success'
                    result['source'] = 'Alpha Vantage'
                    result['bid'] = forex_data.get('bid')
                    result['ask'] = forex_data.get('ask')
                else:
                    # Fallback rates
                    fallback_rates = {
                        ('USD', 'EUR'): 0.85,
                        ('USD', 'GBP'): 0.73,
                        ('USD', 'JPY'): 110.0,
                        ('USD', 'CNY'): 6.45
                    }
                    result['prediction'] = fallback_rates.get((from_currency, to_currency), 1.0)
                    result['confidence'] = 0.3
                    result['status'] = 'fallback'

        except Exception as e:
            logger.error(f"Currency prediction failed: {e}")
            result['prediction'] = 1.0
            result['confidence'] = 0.1
            result['status'] = 'error'
            result['error'] = str(e)

        return result

    async def predict_investor_confidence(self, country: str = 'USA') -> Dict:
        """Predict investor confidence with proper error handling"""

        result = {
            'indicator': 'Investor Confidence',
            'country': country,
            'status': 'unknown',
            'prediction': None,
            'confidence': 0.0
        }

        try:
            # Use VIX as proxy for investor confidence
            data_integration = DataIntegration(self.config)

            # Add delay to avoid rate limiting
            time.sleep(2)
            vix_data = data_integration.get_market_data('^VIX', period='1mo')

            if not vix_data.empty:
                current_vix = vix_data['Close'].iloc[-1]
                # Convert VIX to confidence score (inverse relationship)
                confidence_score = 100 - (current_vix * 2)
                result['prediction'] = round(confidence_score, 1)
                result['confidence'] = 0.7
                result['status'] = 'success'
                result['vix_level'] = current_vix
            else:
                # Use consumer confidence as fallback
                consumer_conf = data_integration.get_fred_data('UMCSENT')
                if not consumer_conf.empty:
                    result['prediction'] = consumer_conf.iloc[-1]
                    result['confidence'] = 0.6
                    result['status'] = 'success'
                    result['source'] = 'FRED Consumer Sentiment'
                else:
                    result['prediction'] = 65.0
                    result['confidence'] = 0.3
                    result['status'] = 'fallback'

        except Exception as e:
            logger.error(f"Investor confidence prediction failed: {e}")
            result['prediction'] = 65.0
            result['confidence'] = 0.2
            result['status'] = 'error'
            result['error'] = str(e)

        return result

    async def predict_employment(self, country: str = 'USA') -> Dict:
        """Predict employment/nonfarm payrolls with proper error handling"""

        result = {
            'indicator': 'Employment/Nonfarm Payrolls',
            'country': country,
            'status': 'unknown',
            'prediction': None,
            'confidence': 0.0
        }

        try:
            # Get employment data from FRED
            data_integration = DataIntegration(self.config)

            # Nonfarm payrolls
            payrolls = data_integration.get_fred_data('PAYEMS')
            unemployment = data_integration.get_fred_data('UNRATE')

            if not payrolls.empty:
                # Calculate monthly change
                monthly_change = payrolls.diff().iloc[-1] * 1000  # Convert to thousands
                result['prediction'] = round(monthly_change, 0)
                result['confidence'] = 0.75
                result['status'] = 'success'
                result['source'] = 'FRED'

                if not unemployment.empty:
                    result['unemployment_rate'] = unemployment.iloc[-1]
            else:
                # Fallback
                result['prediction'] = 150000
                result['confidence'] = 0.3
                result['status'] = 'fallback'

        except Exception as e:
            logger.error(f"Employment prediction failed: {e}")
            result['prediction'] = 150000
            result['confidence'] = 0.2
            result['status'] = 'error'
            result['error'] = str(e)

        return result

    async def run_all_predictions(self, country: str = 'USA') -> Dict:
        """Run all economic predictions"""

        logger.info(f"Running all predictions for {country}...")

        results = {
            'timestamp': datetime.now().isoformat(),
            'country': country,
            'predictions': {}
        }

        # Run predictions in parallel where possible
        tasks = [
            self.predict_gdp(country),
            self.predict_inflation(country),
            self.predict_currency('USD', 'EUR'),
            self.predict_investor_confidence(country),
            self.predict_employment(country)
        ]

        predictions = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        indicators = ['gdp', 'inflation', 'currency', 'investor_confidence', 'employment']
        for indicator, prediction in zip(indicators, predictions):
            if isinstance(prediction, Exception):
                results['predictions'][indicator] = {
                    'status': 'error',
                    'error': str(prediction)
                }
            else:
                results['predictions'][indicator] = prediction

        # Summary statistics
        successful = sum(1 for p in results['predictions'].values()
                        if isinstance(p, dict) and p.get('status') == 'success')
        total = len(results['predictions'])

        results['summary'] = {
            'successful_predictions': successful,
            'total_predictions': total,
            'success_rate': f'{successful/total*100:.1f}%'
        }

        return results


async def test_fixed_predictors():
    """Test the fixed predictor system"""

    print("🔧 Testing Fixed Economic Predictors")
    print("=" * 50)

    predictor = UnifiedEconomicPredictor()

    # Test individual predictors
    print("\n📊 Testing Individual Predictors...")

    # GDP
    print("\n1. GDP Prediction:")
    gdp_result = await predictor.predict_gdp()
    print(f"   Status: {gdp_result['status']}")
    print(f"   Prediction: {gdp_result['prediction']}%")
    print(f"   Confidence: {gdp_result['confidence']*100:.0f}%")

    # Inflation
    print("\n2. Inflation/CPI Prediction:")
    inflation_result = await predictor.predict_inflation()
    print(f"   Status: {inflation_result['status']}")
    print(f"   Prediction: {inflation_result['prediction']}%")
    print(f"   Confidence: {inflation_result['confidence']*100:.0f}%")

    # Currency
    print("\n3. Currency (USD/EUR) Prediction:")
    currency_result = await predictor.predict_currency()
    print(f"   Status: {currency_result['status']}")
    print(f"   Prediction: {currency_result['prediction']}")
    print(f"   Confidence: {currency_result['confidence']*100:.0f}%")

    # Investor Confidence
    print("\n4. Investor Confidence Prediction:")
    confidence_result = await predictor.predict_investor_confidence()
    print(f"   Status: {confidence_result['status']}")
    print(f"   Prediction: {confidence_result['prediction']}")
    print(f"   Confidence: {confidence_result['confidence']*100:.0f}%")

    # Employment
    print("\n5. Employment Prediction:")
    employment_result = await predictor.predict_employment()
    print(f"   Status: {employment_result['status']}")
    print(f"   Prediction: {employment_result['prediction']} jobs")
    print(f"   Confidence: {employment_result['confidence']*100:.0f}%")

    # Run all predictions
    print("\n📈 Running All Predictions Together...")
    all_results = await predictor.run_all_predictions()

    print(f"\n✅ Summary:")
    print(f"   {all_results['summary']['successful_predictions']}/{all_results['summary']['total_predictions']} predictions successful")
    print(f"   Success rate: {all_results['summary']['success_rate']}")

    return all_results


if __name__ == "__main__":
    # Run the test
    results = asyncio.run(test_fixed_predictors())

    # Save results
    import json
    output_file = f"fixed_predictor_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n📄 Results saved to {output_file}")