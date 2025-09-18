#!/usr/bin/env python3
"""
Economic Predictions Runner Script
Runs economic predictions using various predictor models
"""

import sys
import json
import logging
from datetime import datetime
from sentiment_bot.enhanced_economic_predictors import EnhancedEconomicPredictor
from sentiment_bot.comprehensive_economic_predictors import ComprehensiveEconomicPredictor
from sentiment_bot.production_economic_predictor import ProductionEconomicPredictor
from sentiment_bot.advanced_economic_predictors import AdvancedEconomicPredictor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_economic_predictions(countries=None, predictor_type="enhanced"):
    """Run economic predictions for specified countries"""

    if countries is None:
        countries = ["USA", "CHN", "GBR", "DEU", "JPN"]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    try:
        # Initialize predictor based on type
        if predictor_type == "comprehensive":
            predictor = ComprehensiveEconomicPredictor()
        elif predictor_type == "production":
            predictor = ProductionEconomicPredictor()
        elif predictor_type == "advanced":
            predictor = AdvancedEconomicPredictor()
        else:
            predictor = EnhancedEconomicPredictor()

        logger.info(f"Starting economic predictions for countries: {countries}")

        results = {}
        for country in countries:
            logger.info(f"Predicting for {country}...")
            country_result = predictor.predict_country(country)
            results[country] = country_result

        # Save results
        output_file = f"economic_predictions_{timestamp}.json"
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)

        logger.info(f"Results saved to {output_file}")
        return results

    except Exception as e:
        logger.error(f"Error in economic predictions: {e}")
        raise

def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Run Economic Predictions')
    parser.add_argument('--countries', nargs='+', default=["USA", "CHN"],
                       help='Countries to analyze')
    parser.add_argument('--predictor', choices=['enhanced', 'comprehensive', 'production', 'advanced'],
                       default='enhanced', help='Predictor type to use')

    args = parser.parse_args()

    results = run_economic_predictions(args.countries, args.predictor)
    print(f"Predictions complete for {len(results)} countries")

if __name__ == "__main__":
    main()