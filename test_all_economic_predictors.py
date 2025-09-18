#!/usr/bin/env python3
"""
Comprehensive Economic Predictor Testing
Tests all GDP, inflation, CPI, investor confidence, and currency predictors
"""

import sys
import json
import logging
import asyncio
import traceback
from datetime import datetime
from typing import Dict, Any, List

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_imports():
    """Test if all predictor modules can be imported"""
    results = {
        'imports': {},
        'classes_found': {},
        'methods_available': {}
    }

    modules_to_test = [
        'sentiment_bot.comprehensive_economic_predictors',
        'sentiment_bot.enhanced_economic_predictors',
        'sentiment_bot.advanced_economic_predictors',
        'sentiment_bot.production_economic_predictor',
        'sentiment_bot.economic_predictor',
        'sentiment_bot.improved_economic_predictor',
        'sentiment_bot.country_aware_predictor'
    ]

    for module_name in modules_to_test:
        try:
            module = __import__(module_name, fromlist=[''])
            results['imports'][module_name] = 'SUCCESS'

            # Find predictor classes
            classes = []
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and 'predictor' in attr_name.lower():
                    classes.append(attr_name)

                    # Check for specific prediction methods
                    methods = []
                    for method_name in dir(attr):
                        if any(keyword in method_name.lower() for keyword in
                               ['gdp', 'inflation', 'cpi', 'currency', 'confidence', 'predict']):
                            methods.append(method_name)

                    results['methods_available'][f"{module_name}.{attr_name}"] = methods

            results['classes_found'][module_name] = classes

        except Exception as e:
            results['imports'][module_name] = f'FAILED: {str(e)}'
            logger.error(f"Failed to import {module_name}: {e}")

    return results

async def test_comprehensive_predictors():
    """Test the comprehensive economic predictors module"""
    try:
        from sentiment_bot.comprehensive_economic_predictors import (
            ComprehensiveEconomicPredictor,
            AlphaVantageClient,
            GDPPredictor,
            InflationPredictor,
            CurrencyPredictor,
            InvestorConfidencePredictor
        )

        results = {
            'module_import': 'SUCCESS',
            'gdp_predictor': {},
            'inflation_predictor': {},
            'currency_predictor': {},
            'investor_confidence': {},
            'alpha_vantage': {}
        }

        # Test AlphaVantage client
        try:
            async with AlphaVantageClient() as av_client:
                # Test API connection with a simple call
                forex_data = await av_client.get_forex_rate('USD', 'EUR')
                if forex_data:
                    results['alpha_vantage']['connection'] = 'SUCCESS'
                    results['alpha_vantage']['sample_data'] = forex_data
                else:
                    results['alpha_vantage']['connection'] = 'NO DATA RETURNED'
        except Exception as e:
            results['alpha_vantage']['connection'] = f'FAILED: {str(e)}'

        # Test individual predictors
        try:
            async with AlphaVantageClient() as av_client:

                # Test GDP Predictor
                try:
                    gdp_predictor = GDPPredictor(av_client)

                    # Test with mock data
                    mock_sentiment = {
                        'economic_sentiment': 0.2,
                        'growth_sentiment': 0.15,
                        'recession_sentiment': -0.1
                    }
                    mock_market = {
                        'sp500_performance': 0.05,
                        'bond_yields': 0.04,
                        'dollar_strength': 0.02
                    }

                    gdp_result = await gdp_predictor.predict_gdp_growth(
                        'USA', mock_sentiment, mock_market
                    )

                    results['gdp_predictor']['test'] = 'SUCCESS'
                    results['gdp_predictor']['prediction'] = {
                        'value': gdp_result.prediction,
                        'confidence': gdp_result.confidence,
                        'direction': gdp_result.direction,
                        'drivers': gdp_result.drivers
                    }

                except Exception as e:
                    results['gdp_predictor']['test'] = f'FAILED: {str(e)}'

                # Test Inflation Predictor
                try:
                    inflation_predictor = InflationPredictor(av_client)

                    mock_sentiment = {
                        'inflation_sentiment': 0.3,
                        'price_sentiment': 0.25,
                        'wage_sentiment': 0.1
                    }
                    mock_market = {
                        'commodity_prices': 0.08,
                        'energy_prices': 0.12,
                        'housing_prices': 0.06
                    }

                    inflation_result = await inflation_predictor.predict_inflation(
                        'USA', mock_sentiment, mock_market
                    )

                    results['inflation_predictor']['test'] = 'SUCCESS'
                    results['inflation_predictor']['prediction'] = {
                        'value': inflation_result.prediction,
                        'confidence': inflation_result.confidence,
                        'direction': inflation_result.direction,
                        'drivers': inflation_result.drivers
                    }

                except Exception as e:
                    results['inflation_predictor']['test'] = f'FAILED: {str(e)}'

                # Test Currency Predictor
                try:
                    currency_predictor = CurrencyPredictor(av_client)

                    mock_sentiment = {
                        'dollar_sentiment': 0.1,
                        'fed_sentiment': 0.05,
                        'trade_sentiment': -0.02
                    }
                    mock_market = {
                        'interest_rate_diff': 0.02,
                        'trade_balance': -0.01,
                        'inflation_diff': 0.005
                    }

                    currency_result = await currency_predictor.predict_exchange_rate(
                        'USD', 'EUR', mock_sentiment, mock_market
                    )

                    results['currency_predictor']['test'] = 'SUCCESS'
                    results['currency_predictor']['prediction'] = {
                        'value': currency_result.prediction,
                        'confidence': currency_result.confidence,
                        'direction': currency_result.direction,
                        'drivers': currency_result.drivers
                    }

                except Exception as e:
                    results['currency_predictor']['test'] = f'FAILED: {str(e)}'

                # Test Investor Confidence Predictor
                try:
                    confidence_predictor = InvestorConfidencePredictor(av_client)

                    mock_sentiment = {
                        'market_sentiment': 0.15,
                        'volatility_sentiment': -0.1,
                        'earnings_sentiment': 0.2
                    }
                    mock_market = {
                        'vix_level': 18.5,
                        'earnings_growth': 0.08,
                        'credit_spreads': 0.02
                    }

                    confidence_result = await confidence_predictor.predict_investor_confidence(
                        'USA', mock_sentiment, mock_market
                    )

                    results['investor_confidence']['test'] = 'SUCCESS'
                    results['investor_confidence']['prediction'] = {
                        'value': confidence_result.prediction,
                        'confidence': confidence_result.confidence,
                        'direction': confidence_result.direction,
                        'drivers': confidence_result.drivers
                    }

                except Exception as e:
                    results['investor_confidence']['test'] = f'FAILED: {str(e)}'

        except Exception as e:
            results['predictor_tests'] = f'FAILED TO INITIALIZE: {str(e)}'

        return results

    except Exception as e:
        return {
            'module_import': f'FAILED: {str(e)}',
            'error_details': traceback.format_exc()
        }

def test_other_predictors():
    """Test other predictor modules"""
    results = {}

    # Test enhanced economic predictors
    try:
        from sentiment_bot.enhanced_economic_predictors import EnhancedEconomicPredictor

        predictor = EnhancedEconomicPredictor()

        # Test if it has the expected methods
        methods = [method for method in dir(predictor) if 'predict' in method.lower()]

        results['enhanced_economic_predictors'] = {
            'import': 'SUCCESS',
            'methods': methods,
            'has_gdp_method': any('gdp' in m.lower() for m in methods),
            'has_inflation_method': any('inflation' in m.lower() for m in methods),
            'has_currency_method': any('currency' in m.lower() for m in methods)
        }

        # Try to run a prediction test
        try:
            test_result = predictor.predict_country('USA')
            results['enhanced_economic_predictors']['test_prediction'] = 'SUCCESS'
            results['enhanced_economic_predictors']['sample_output'] = str(test_result)[:200]
        except Exception as e:
            results['enhanced_economic_predictors']['test_prediction'] = f'FAILED: {str(e)}'

    except Exception as e:
        results['enhanced_economic_predictors'] = {
            'import': f'FAILED: {str(e)}'
        }

    # Test advanced economic predictors
    try:
        from sentiment_bot.advanced_economic_predictors import AdvancedEconomicPredictor

        predictor = AdvancedEconomicPredictor()
        methods = [method for method in dir(predictor) if 'predict' in method.lower()]

        results['advanced_economic_predictors'] = {
            'import': 'SUCCESS',
            'methods': methods
        }

        # Try to run a prediction test
        try:
            test_result = predictor.predict_country('USA')
            results['advanced_economic_predictors']['test_prediction'] = 'SUCCESS'
            results['advanced_economic_predictors']['sample_output'] = str(test_result)[:200]
        except Exception as e:
            results['advanced_economic_predictors']['test_prediction'] = f'FAILED: {str(e)}'

    except Exception as e:
        results['advanced_economic_predictors'] = {
            'import': f'FAILED: {str(e)}'
        }

    return results

async def main():
    """Main test function"""
    print("🧪 Testing Economic Predictors - Comprehensive Analysis")
    print("=" * 60)

    # Test imports
    print("📦 Testing imports...")
    import_results = test_imports()

    # Test comprehensive predictors
    print("🔬 Testing comprehensive predictors...")
    comprehensive_results = await test_comprehensive_predictors()

    # Test other predictors
    print("🧮 Testing other predictor modules...")
    other_results = test_other_predictors()

    # Compile final results
    final_results = {
        'timestamp': datetime.now().isoformat(),
        'test_summary': {
            'imports': import_results,
            'comprehensive_predictors': comprehensive_results,
            'other_predictors': other_results
        }
    }

    # Save results
    output_file = f"economic_predictor_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump(final_results, f, indent=2)

    # Print summary
    print("\n📊 TEST RESULTS SUMMARY")
    print("=" * 40)

    # Import status
    successful_imports = sum(1 for result in import_results['imports'].values() if result == 'SUCCESS')
    total_imports = len(import_results['imports'])
    print(f"📦 Module Imports: {successful_imports}/{total_imports} successful")

    # Comprehensive predictors status
    if comprehensive_results.get('module_import') == 'SUCCESS':
        print("✅ Comprehensive Predictors: Module loaded successfully")

        predictors = ['gdp_predictor', 'inflation_predictor', 'currency_predictor', 'investor_confidence']
        for predictor in predictors:
            if predictor in comprehensive_results:
                status = comprehensive_results[predictor].get('test', 'NOT TESTED')
                icon = "✅" if status == 'SUCCESS' else "❌"
                print(f"{icon} {predictor.replace('_', ' ').title()}: {status}")
    else:
        print(f"❌ Comprehensive Predictors: {comprehensive_results.get('module_import', 'UNKNOWN ERROR')}")

    # Alpha Vantage status
    if 'alpha_vantage' in comprehensive_results:
        av_status = comprehensive_results['alpha_vantage'].get('connection', 'NOT TESTED')
        icon = "✅" if av_status == 'SUCCESS' else "⚠️"
        print(f"{icon} Alpha Vantage API: {av_status}")

    # Other predictors status
    for predictor_name, result in other_results.items():
        import_status = result.get('import', 'UNKNOWN')
        test_status = result.get('test_prediction', 'NOT TESTED')
        icon = "✅" if import_status == 'SUCCESS' and test_status == 'SUCCESS' else "❌"
        print(f"{icon} {predictor_name.replace('_', ' ').title()}: Import={import_status}, Test={test_status}")

    print(f"\n📄 Detailed results saved to: {output_file}")

    return final_results

if __name__ == "__main__":
    results = asyncio.run(main())