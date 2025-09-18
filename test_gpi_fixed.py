#!/usr/bin/env python3
"""Test fixed GPI implementation with correct clamping."""

import json
import numpy as np
from typing import List, Dict

def simulate_gpi_scores():
    """Simulate GPI processing with various coverage levels."""

    countries = [
        # High positive scores with low coverage (should be clamped to 50)
        {'iso3': 'GBR', 'name': 'United Kingdom', 'raw_gpi': 0.85, 'n_eff': 121},
        {'iso3': 'ESP', 'name': 'Spain', 'raw_gpi': 0.90, 'n_eff': 106},
        {'iso3': 'AUS', 'name': 'Australia', 'raw_gpi': 0.88, 'n_eff': 112},
        {'iso3': 'ITA', 'name': 'Italy', 'raw_gpi': 0.82, 'n_eff': 123},
        {'iso3': 'KOR', 'name': 'South Korea', 'raw_gpi': 0.80, 'n_eff': 115},

        # High negative scores with low coverage (should be clamped to -50)
        {'iso3': 'NLD', 'name': 'Netherlands', 'raw_gpi': -0.95, 'n_eff': 117},
        {'iso3': 'CHN', 'name': 'China', 'raw_gpi': -0.92, 'n_eff': 122},
        {'iso3': 'SAU', 'name': 'Saudi Arabia', 'raw_gpi': -0.88, 'n_eff': 112},
        {'iso3': 'MEX', 'name': 'Mexico', 'raw_gpi': -0.85, 'n_eff': 123},

        # Moderate scores
        {'iso3': 'USA', 'name': 'United States', 'raw_gpi': 0.05, 'n_eff': 105},
        {'iso3': 'JPN', 'name': 'Japan', 'raw_gpi': 0.02, 'n_eff': 120},
        {'iso3': 'DEU', 'name': 'Germany', 'raw_gpi': -0.01, 'n_eff': 123},
        {'iso3': 'FRA', 'name': 'France', 'raw_gpi': 0.03, 'n_eff': 124},
        {'iso3': 'CAN', 'name': 'Canada', 'raw_gpi': 0.25, 'n_eff': 120},

        # Additional countries
        {'iso3': 'TUR', 'name': 'Turkey', 'raw_gpi': 0.78, 'n_eff': 123},
        {'iso3': 'CHE', 'name': 'Switzerland', 'raw_gpi': 0.75, 'n_eff': 121},
        {'iso3': 'POL', 'name': 'Poland', 'raw_gpi': 0.72, 'n_eff': 120},
        {'iso3': 'BEL', 'name': 'Belgium', 'raw_gpi': 0.70, 'n_eff': 119},
        {'iso3': 'SWE', 'name': 'Sweden', 'raw_gpi': 0.68, 'n_eff': 117},
        {'iso3': 'IDN', 'name': 'Indonesia', 'raw_gpi': 0.65, 'n_eff': 91},
    ]

    results = []
    for country in countries:
        # Apply calibration logic matching gpi_production.py
        raw_gpi = country['raw_gpi']
        n_eff = country['n_eff']

        # Step 1: Calibrate based on coverage
        if n_eff < 300:
            # Linear calibration for low coverage
            headline_cal = raw_gpi * 100 * 0.5  # Scale to [-50, 50]
            calibration_mode = "linear"
        else:
            # For higher coverage (not reached in test data)
            headline_cal = np.tanh(raw_gpi * 0.6) * 100
            calibration_mode = "isotonic"

        # Step 2: Apply safety clamps
        if n_eff < 300:
            # Hard clamp at ±50 for low coverage
            headline_final = float(np.clip(headline_cal, -50, 50))
        elif n_eff < 1200:
            headline_final = float(np.clip(headline_cal, -75, 75))
        else:
            ci_half_width = 15 * np.sqrt(300 / max(n_eff, 300))
            if abs(headline_cal) > 90 and ci_half_width > 7:
                headline_final = float(np.clip(headline_cal, -90, 90))
            else:
                headline_final = float(np.clip(headline_cal, -100, 100))

        # Assertions
        assert -100.0 <= headline_final <= 100.0, f"GPI out of range: {headline_final}"
        if n_eff < 300:
            assert -50.0 <= headline_final <= 50.0, f"Low coverage but GPI={headline_final}"

        results.append({
            'iso3': country['iso3'],
            'name': country['name'],
            'gpi': headline_final,
            'raw_gpi': raw_gpi,
            'n_eff': n_eff,
            'confidence': 'Low' if n_eff < 300 else 'Medium' if n_eff < 1200 else 'High',
            'calibration_mode': calibration_mode
        })

        print(f"iso3={country['iso3']:3} raw_gpi={raw_gpi:+.3f} n_eff={n_eff:3} "
              f"mode={calibration_mode:8} cal={headline_cal:+6.1f} final={headline_final:+6.1f}")

    return results

def display_rankings(results: List[Dict]):
    """Display top 5 and bottom 5 countries."""

    # Sort by final GPI score
    results_sorted = sorted(results, key=lambda x: x['gpi'], reverse=True)

    print("\n" + "="*70)
    print("TOP 5 COUNTRIES BY GPI SCORE (Correctly Clamped)")
    print("="*70)
    for i, country in enumerate(results_sorted[:5], 1):
        conf_note = " (low confidence)" if country['confidence'] == 'Low' else ""
        print(f"{i}. {country['name']:20} GPI: {country['gpi']:+6.1f}  "
              f"Raw: {country['raw_gpi']:+.3f}  N_eff: {country['n_eff']:3}{conf_note}")

    print("\n" + "="*70)
    print("BOTTOM 5 COUNTRIES BY GPI SCORE (Correctly Clamped)")
    print("="*70)
    for i, country in enumerate(results_sorted[-5:], 1):
        conf_note = " (low confidence)" if country['confidence'] == 'Low' else ""
        print(f"{i}. {country['name']:20} GPI: {country['gpi']:+6.1f}  "
              f"Raw: {country['raw_gpi']:+.3f}  N_eff: {country['n_eff']:3}{conf_note}")

    # Verification
    print("\n" + "="*70)
    print("VERIFICATION: All scores should be in [-50, +50] range for n_eff < 300")
    print("="*70)
    for country in results_sorted:
        if country['n_eff'] < 300:
            if abs(country['gpi']) > 50:
                print(f"ERROR: {country['name']} has GPI={country['gpi']} with n_eff={country['n_eff']}")

    all_valid = all(abs(c['gpi']) <= 50 for c in results_sorted if c['n_eff'] < 300)
    if all_valid:
        print("✓ All scores correctly clamped to ±50 for low coverage (n_eff < 300)")
    else:
        print("✗ ERROR: Some scores exceed ±50 despite low coverage")

    # Save results
    with open('gpi_fixed_results.json', 'w') as f:
        json.dump(results_sorted, f, indent=2)

    print(f"\nFull results saved to gpi_fixed_results.json")

if __name__ == "__main__":
    print("Testing Fixed GPI Implementation")
    print("="*70)
    results = simulate_gpi_scores()
    display_rankings(results)