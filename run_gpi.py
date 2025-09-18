#!/usr/bin/env python3
"""
GPI (Global Perception Index) Runner Script
Runs the GPI analysis system with various country configurations
"""

import sys
import json
import logging
from datetime import datetime
from sentiment_bot.gpi_enhanced import GPIEnhanced
from sentiment_bot.gpi_production import GPIProduction
from sentiment_bot.gpi_enhanced_v2 import GPIEnhancedV2

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_gpi_analysis(countries=None, version="enhanced"):
    """Run GPI analysis for specified countries"""

    if countries is None:
        countries = ["USA", "CHN", "GBR", "DEU", "JPN"]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    try:
        if version == "production":
            gpi = GPIProduction()
        elif version == "v2":
            gpi = GPIEnhancedV2()
        else:
            gpi = GPIEnhanced()

        logger.info(f"Starting GPI analysis for countries: {countries}")

        results = {}
        for country in countries:
            logger.info(f"Analyzing {country}...")
            country_result = gpi.analyze_country(country)
            results[country] = country_result

        # Save results
        output_file = f"gpi_results_{timestamp}.json"
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)

        logger.info(f"Results saved to {output_file}")
        return results

    except Exception as e:
        logger.error(f"Error in GPI analysis: {e}")
        raise

def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Run GPI Analysis')
    parser.add_argument('--countries', nargs='+', default=["USA", "CHN"],
                       help='Countries to analyze')
    parser.add_argument('--version', choices=['enhanced', 'production', 'v2'],
                       default='enhanced', help='GPI version to use')

    args = parser.parse_args()

    results = run_gpi_analysis(args.countries, args.version)
    print(f"Analysis complete for {len(results)} countries")

if __name__ == "__main__":
    main()