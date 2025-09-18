#!/usr/bin/env python3
"""
GPI Alpha Vantage Integration
Combines GPI analysis with Alpha Vantage economic data
"""

import sys
import json
import logging
from datetime import datetime
from sentiment_bot.gpi_enhanced import GPIEnhanced
from sentiment_bot.alpha_vantage_news import AlphaVantageNews

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_gpi_alpha_vantage_analysis(countries=None):
    """Run combined GPI and Alpha Vantage analysis"""

    if countries is None:
        countries = ["USA", "CHN"]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    try:
        gpi = GPIEnhanced()
        alpha_vantage = AlphaVantageNews()

        logger.info(f"Starting GPI + Alpha Vantage analysis for countries: {countries}")

        results = {}
        for country in countries:
            logger.info(f"Analyzing {country}...")

            # Get GPI analysis
            gpi_result = gpi.analyze_country(country)

            # Get Alpha Vantage data
            av_result = alpha_vantage.get_country_data(country)

            # Combine results
            results[country] = {
                "gpi_analysis": gpi_result,
                "alpha_vantage_data": av_result,
                "timestamp": timestamp
            }

        # Save results
        output_file = f"gpi_alpha_vantage_{countries[0]}_{countries[1] if len(countries) > 1 else 'single'}_{timestamp}.json"
        with open(f"output/{output_file}", 'w') as f:
            json.dump(results, f, indent=2, default=str)

        logger.info(f"Results saved to output/{output_file}")
        return results

    except Exception as e:
        logger.error(f"Error in GPI + Alpha Vantage analysis: {e}")
        raise

def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Run GPI + Alpha Vantage Analysis')
    parser.add_argument('--countries', nargs='+', default=["USA", "CHN"],
                       help='Countries to analyze')

    args = parser.parse_args()

    results = run_gpi_alpha_vantage_analysis(args.countries)
    print(f"Combined analysis complete for {len(results)} countries")

if __name__ == "__main__":
    main()