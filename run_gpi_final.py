#!/usr/bin/env python3
"""Run fixed GPI implementation with proper clamping."""

import json
import logging
from sentiment_bot.gpi_production import GPIPipeline

# Set logging to INFO to see diagnostic output
logging.basicConfig(level=logging.INFO, format='%(message)s')

def main():
    # Top 20 countries for testing
    countries = [
        'USA', 'CHN', 'JPN', 'DEU', 'GBR', 'FRA', 'ITA', 'CAN', 'KOR', 'ESP',
        'AUS', 'MEX', 'IDN', 'NLD', 'SAU', 'TUR', 'CHE', 'POL', 'BEL', 'SWE'
    ]

    print("="*70)
    print("GPI PRODUCTION RUN WITH FIXED CALIBRATION")
    print("="*70)
    print("All scores with n_eff < 300 will be clamped to ±50\n")

    # Initialize pipeline
    pipeline = GPIPipeline()

    # Process countries (limit to 5 for speed)
    test_countries = ['USA', 'CHN', 'GBR', 'MEX', 'JPN']  # Mix of expected positive/negative
    results = []

    for country in test_countries:
        print(f"\nProcessing {country}...")
        try:
            result = pipeline.process_country(country)

            # Extract key info
            gpi = result['headline_gpi']
            n_eff = result['coverage']['n_eff']
            confidence = result['confidence']
            mode = result.get('calibration_mode', 'unknown')

            results.append({
                'iso3': country,
                'name': result['country']['name'],
                'gpi': gpi,
                'n_eff': n_eff,
                'confidence': confidence,
                'mode': mode,
                'raw_gpi': result.get('debug', {}).get('raw_gpi', 0)
            })

            print(f"  ✓ GPI: {gpi:+6.1f} | N_eff: {n_eff:3d} | Mode: {mode} | Confidence: {confidence}")

            # Verify clamping
            if n_eff < 300 and abs(gpi) > 50:
                print(f"  ⚠️  ERROR: Score {gpi} exceeds ±50 despite n_eff={n_eff}")

        except Exception as e:
            print(f"  ✗ Error: {e}")
            results.append({
                'iso3': country,
                'name': country,
                'gpi': 0.0,
                'n_eff': 0,
                'confidence': 'Error',
                'mode': 'error'
            })

    # Sort by GPI score
    results_sorted = sorted(results, key=lambda x: x['gpi'], reverse=True)

    # Display rankings
    print("\n" + "="*70)
    print("TOP COUNTRIES BY GPI SCORE (Fixed)")
    print("="*70)
    for i, country in enumerate(results_sorted[:3], 1):
        conf = " (low conf)" if country['n_eff'] < 300 else ""
        print(f"{i}. {country['name']:20} GPI: {country['gpi']:+6.1f}  N_eff: {country['n_eff']:3}{conf}")

    print("\n" + "="*70)
    print("BOTTOM COUNTRIES BY GPI SCORE (Fixed)")
    print("="*70)
    bottom = sorted(results, key=lambda x: x['gpi'])[:2]
    for i, country in enumerate(bottom, 1):
        conf = " (low conf)" if country['n_eff'] < 300 else ""
        print(f"{i}. {country['name']:20} GPI: {country['gpi']:+6.1f}  N_eff: {country['n_eff']:3}{conf}")

    # Verification
    print("\n" + "="*70)
    print("CLAMPING VERIFICATION")
    print("="*70)
    violations = [r for r in results if r['n_eff'] < 300 and abs(r['gpi']) > 50]
    if violations:
        print("✗ ERRORS FOUND:")
        for v in violations:
            print(f"  - {v['name']}: GPI={v['gpi']} with n_eff={v['n_eff']}")
    else:
        print("✓ All scores correctly clamped for low coverage")

    # Save results
    with open('gpi_final_results.json', 'w') as f:
        json.dump(results_sorted, f, indent=2)

    print(f"\nResults saved to gpi_final_results.json")

if __name__ == "__main__":
    main()