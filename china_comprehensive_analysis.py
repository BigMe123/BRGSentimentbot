#!/usr/bin/env python3
"""
China Comprehensive Analysis Script
Runs comprehensive analysis for China using GPI and economic predictors
"""

import sys
import json
import logging
from datetime import datetime
from sentiment_bot.gpi_enhanced import GPIEnhanced
from sentiment_bot.comprehensive_economic_predictors import ComprehensiveEconomicPredictor
from sentiment_bot.country_aware_predictor import CountryAwarePredictor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_china_analysis():
    """Run comprehensive analysis for China"""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    country = "CHN"

    try:
        logger.info("Starting comprehensive China analysis...")

        # Initialize analyzers
        gpi = GPIEnhanced()
        economic_predictor = ComprehensiveEconomicPredictor()
        country_predictor = CountryAwarePredictor()

        # Run analyses
        logger.info("Running GPI analysis...")
        gpi_result = gpi.analyze_country(country)

        logger.info("Running economic predictions...")
        economic_result = economic_predictor.predict_country(country)

        logger.info("Running country-aware analysis...")
        country_result = country_predictor.analyze_country(country)

        # Combine results
        results = {
            "country": country,
            "timestamp": timestamp,
            "gpi_analysis": gpi_result,
            "economic_predictions": economic_result,
            "country_analysis": country_result,
            "summary": {
                "analysis_type": "comprehensive",
                "components": ["gpi", "economic", "country_aware"]
            }
        }

        # Save results
        output_file = f"china_data_{timestamp}.json"
        with open(f"output/{output_file}", 'w') as f:
            json.dump(results, f, indent=2, default=str)

        # Create report
        report_file = f"china_report_{timestamp}.txt"
        with open(f"output/{report_file}", 'w') as f:
            f.write(f"China Comprehensive Analysis Report - {timestamp}\n")
            f.write("=" * 50 + "\n\n")
            f.write("GPI Analysis Summary:\n")
            f.write(f"- Sentiment Score: {gpi_result.get('sentiment_score', 'N/A')}\n")
            f.write(f"- Perception Index: {gpi_result.get('perception_index', 'N/A')}\n\n")
            f.write("Economic Predictions:\n")
            f.write(f"- GDP Growth: {economic_result.get('gdp_growth', 'N/A')}\n")
            f.write(f"- Economic Outlook: {economic_result.get('outlook', 'N/A')}\n\n")

        logger.info(f"Analysis complete. Results saved to output/{output_file}")
        logger.info(f"Report saved to output/{report_file}")

        return results

    except Exception as e:
        logger.error(f"Error in China analysis: {e}")
        raise

def main():
    """Main entry point"""
    results = run_china_analysis()
    print("China comprehensive analysis complete!")

if __name__ == "__main__":
    main()