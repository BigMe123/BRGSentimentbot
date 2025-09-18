#!/usr/bin/env python3
"""Quick GPI run for top/bottom countries."""

import json
from sentiment_bot.gpi_production import GPIPipeline

def main():
    # Top 20 countries
    countries = [
        'USA', 'CHN', 'JPN', 'DEU', 'GBR', 'FRA', 'ITA', 'CAN', 'KOR', 'ESP',
        'AUS', 'MEX', 'IDN', 'NLD', 'SAU', 'TUR', 'CHE', 'POL', 'BEL', 'SWE'
    ]

    # Initialize pipeline
    pipeline = GPIPipeline()

    # Process each country
    results = []
    for country in countries:
        print(f"Processing {country}...")
        try:
            result = pipeline.process_country(country)
            results.append({
                'iso3': country,
                'name': result['country']['name'],
                'gpi': result['headline_gpi'],
                'confidence': result['confidence'],
                'n_eff': result['coverage']['n_eff']
            })
            print(f"  GPI: {result['headline_gpi']:.1f}, N_eff: {result['coverage']['n_eff']}")
        except Exception as e:
            print(f"  Error: {e}")
            results.append({
                'iso3': country,
                'name': country,
                'gpi': 0.0,
                'confidence': 'Error',
                'n_eff': 0
            })

    # Sort by GPI score
    results_sorted = sorted(results, key=lambda x: x['gpi'], reverse=True)

    # Print top 5 and bottom 5
    print("\n" + "="*60)
    print("TOP 5 COUNTRIES BY GPI SCORE")
    print("="*60)
    for i, country in enumerate(results_sorted[:5], 1):
        print(f"{i}. {country['name']:20} GPI: {country['gpi']:6.1f}  N_eff: {country['n_eff']:3d}  ({country['confidence']})")

    print("\n" + "="*60)
    print("BOTTOM 5 COUNTRIES BY GPI SCORE")
    print("="*60)
    for i, country in enumerate(results_sorted[-5:], 1):
        print(f"{i}. {country['name']:20} GPI: {country['gpi']:6.1f}  N_eff: {country['n_eff']:3d}  ({country['confidence']})")

    # Save full results
    with open('gpi_quick_results.json', 'w') as f:
        json.dump(results_sorted, f, indent=2)

    print(f"\nFull results saved to gpi_quick_results.json")

if __name__ == "__main__":
    main()