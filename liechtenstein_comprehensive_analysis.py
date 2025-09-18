#!/usr/bin/env python3
"""
Liechtenstein Comprehensive Analysis Script
Runs comprehensive analysis for Liechtenstein using specialized small-country models
"""

import sys
import json
import logging
from datetime import datetime
from sentiment_bot.gpi_enhanced import GPIEnhanced
from sentiment_bot.country_aware_predictor import CountryAwarePredictor
from sentiment_bot.liechtenstein_comprehensive_report import LiechtensteinReportGenerator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_liechtenstein_analysis():
    """Run comprehensive analysis for Liechtenstein"""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    country = "LIE"

    try:
        logger.info("Starting comprehensive Liechtenstein analysis...")

        # Initialize analyzers
        gpi = GPIEnhanced()
        country_predictor = CountryAwarePredictor()
        report_generator = LiechtensteinReportGenerator()

        # Run analyses
        logger.info("Running GPI analysis...")
        gpi_result = gpi.analyze_country(country)

        logger.info("Running country-aware analysis...")
        country_result = country_predictor.analyze_country(country)

        logger.info("Generating specialized report...")
        report_result = report_generator.generate_report(country)

        # Combine results
        results = {
            "country": country,
            "country_name": "Liechtenstein",
            "timestamp": timestamp,
            "gpi_analysis": gpi_result,
            "country_analysis": country_result,
            "specialized_report": report_result,
            "summary": {
                "analysis_type": "comprehensive_liechtenstein",
                "components": ["gpi", "country_aware", "specialized_report"],
                "focus": "small_european_economy"
            }
        }

        # Save results
        output_file = f"liechtenstein_data_{timestamp}.json"
        with open(f"output/{output_file}", 'w') as f:
            json.dump(results, f, indent=2, default=str)

        # Create comprehensive report
        report_file = f"liechtenstein_report_{timestamp}.txt"
        with open(f"output/{report_file}", 'w') as f:
            f.write(f"Liechtenstein Comprehensive Analysis Report - {timestamp}\n")
            f.write("=" * 60 + "\n\n")
            f.write("Country Overview:\n")
            f.write("- Country: Liechtenstein (LIE)\n")
            f.write("- Type: Small European Economy\n")
            f.write("- Analysis Focus: Financial services, EU relations\n\n")
            f.write("GPI Analysis Summary:\n")
            f.write(f"- Sentiment Score: {gpi_result.get('sentiment_score', 'N/A')}\n")
            f.write(f"- Perception Index: {gpi_result.get('perception_index', 'N/A')}\n\n")
            f.write("Country-Specific Analysis:\n")
            f.write(f"- Economic Outlook: {country_result.get('outlook', 'N/A')}\n")
            f.write(f"- Key Factors: {country_result.get('key_factors', 'N/A')}\n\n")
            f.write("Specialized Report:\n")
            f.write(f"- Report Type: {report_result.get('report_type', 'N/A')}\n")
            f.write(f"- Key Insights: {report_result.get('insights', 'N/A')}\n")

        logger.info(f"Analysis complete. Results saved to output/{output_file}")
        logger.info(f"Report saved to output/{report_file}")

        return results

    except Exception as e:
        logger.error(f"Error in Liechtenstein analysis: {e}")
        raise

def main():
    """Main entry point"""
    results = run_liechtenstein_analysis()
    print("Liechtenstein comprehensive analysis complete!")

if __name__ == "__main__":
    main()