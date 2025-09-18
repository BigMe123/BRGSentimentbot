#!/usr/bin/env python3
"""
USA Comprehensive Analysis Script
Runs comprehensive analysis for USA using GPI and economic predictors
"""

import sys
import json
import logging
from datetime import datetime
from sentiment_bot.gpi_enhanced import GPIEnhanced
from sentiment_bot.comprehensive_economic_predictors import ComprehensiveEconomicPredictor
from sentiment_bot.alpha_vantage_news import AlphaVantageNews

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_usa_analysis():
    """Run comprehensive analysis for USA"""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    country = "USA"

    try:
        logger.info("Starting comprehensive USA analysis...")

        # Initialize analyzers
        gpi = GPIEnhanced()
        economic_predictor = ComprehensiveEconomicPredictor()
        alpha_vantage = AlphaVantageNews()

        # Run analyses
        logger.info("Running GPI analysis...")
        gpi_result = gpi.analyze_country(country)

        logger.info("Running economic predictions...")
        economic_result = economic_predictor.predict_country(country)

        logger.info("Getting Alpha Vantage data...")
        av_result = alpha_vantage.get_country_data(country)

        # Combine results
        results = {
            "country": country,
            "timestamp": timestamp,
            "gpi_analysis": gpi_result,
            "economic_predictions": economic_result,
            "alpha_vantage_data": av_result,
            "summary": {
                "analysis_type": "comprehensive_usa",
                "components": ["gpi", "economic", "alpha_vantage"]
            }
        }

        # Save results
        output_file = f"usa_economic_data_{timestamp}.json"
        with open(f"output/{output_file}", 'w') as f:
            json.dump(results, f, indent=2, default=str)

        # Create report
        report_file = f"usa_economic_report_{timestamp}.txt"
        with open(f"output/{report_file}", 'w') as f:
            f.write(f"USA Comprehensive Economic Analysis Report - {timestamp}\n")
            f.write("=" * 50 + "\n\n")
            f.write("GPI Analysis Summary:\n")
            f.write(f"- Sentiment Score: {gpi_result.get('sentiment_score', 'N/A')}\n")
            f.write(f"- Perception Index: {gpi_result.get('perception_index', 'N/A')}\n\n")
            f.write("Economic Predictions:\n")
            f.write(f"- GDP Growth: {economic_result.get('gdp_growth', 'N/A')}\n")
            f.write(f"- Economic Outlook: {economic_result.get('outlook', 'N/A')}\n\n")
            f.write("Alpha Vantage Data:\n")
            f.write(f"- Market Data: {len(av_result.get('market_data', []))} entries\n")

        logger.info(f"Analysis complete. Results saved to output/{output_file}")
        logger.info(f"Report saved to output/{report_file}")

        return results

    except Exception as e:
        logger.error(f"Error in USA analysis: {e}")
        raise

def main():
    """Main entry point"""
    results = run_usa_analysis()
    print("USA comprehensive analysis complete!")

if __name__ == "__main__":
    main()