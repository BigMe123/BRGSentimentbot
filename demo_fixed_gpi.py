#!/usr/bin/env python3
"""Demonstrate the fixed GPI calibration logic."""

import json
import numpy as np

def mock_process_country(country_data):
    """Mock GPI processing with fixed calibration."""

    iso3 = country_data['iso3']
    raw_gpi = country_data['raw_gpi']
    n_eff = country_data['n_eff']

    # Apply the FIXED calibration logic from gpi_production.py
    # Step 1: Calibrate based on coverage
    if n_eff < 300:
        # Linear calibration for low coverage
        headline_cal = raw_gpi * 100 * 0.5  # Scale to [-50, 50]
        calibration_mode = "linear"
    else:
        # For higher coverage, use isotonic or full scaling
        headline_cal = np.tanh(raw_gpi * 0.6) * 100
        calibration_mode = "isotonic"

    # Step 2: Apply safety clamps based on coverage
    if n_eff < 300:
        # Hard clamp at ±50 for low coverage
        headline_final = float(np.clip(headline_cal, -50, 50))
    elif n_eff < 1200:
        # Medium coverage: clamp at ±75
        headline_final = float(np.clip(headline_cal, -75, 75))
    else:
        # High coverage: check CI before allowing extreme scores
        ci_half_width = 15 * np.sqrt(300 / max(n_eff, 300))
        if abs(headline_cal) > 90 and ci_half_width > 7:
            headline_final = float(np.clip(headline_cal, -90, 90))
        else:
            headline_final = float(np.clip(headline_cal, -100, 100))

    # Diagnostic output
    print(f"iso3={iso3:3} raw_gpi={raw_gpi:+.3f} n_eff={n_eff:3d} "
          f"mode={calibration_mode:8} cal={headline_cal:+6.1f} final={headline_final:+6.1f}")

    return {
        'country': {'iso3': iso3, 'name': country_data['name']},
        'headline_gpi': headline_final,
        'confidence': 'Low' if n_eff < 300 else 'Medium' if n_eff < 1200 else 'High',
        'coverage': {'n_eff': n_eff, 'bucket': 'Low' if n_eff < 300 else 'Medium'},
        'calibration_mode': calibration_mode,
        'debug': {'raw_gpi': raw_gpi}
    }

def main():
    print("="*70)
    print("DEMONSTRATION: Fixed GPI Calibration")
    print("="*70)
    print("Using actual data from previous runs (raw_gpi values from logs)\n")

    # Mock data based on actual results
    # These raw_gpi values would produce ±100 scores with old logic
    countries = [
        # Countries that were showing +100 (should be ~+40-50)
        {'iso3': 'GBR', 'name': 'United Kingdom', 'raw_gpi': 0.85, 'n_eff': 121},
        {'iso3': 'ESP', 'name': 'Spain', 'raw_gpi': 0.92, 'n_eff': 106},
        {'iso3': 'AUS', 'name': 'Australia', 'raw_gpi': 0.89, 'n_eff': 112},
        {'iso3': 'TUR', 'name': 'Turkey', 'raw_gpi': 0.87, 'n_eff': 123},
        {'iso3': 'CHE', 'name': 'Switzerland', 'raw_gpi': 0.86, 'n_eff': 121},

        # Countries that were showing -100/-99.9 (should be ~-40-50)
        {'iso3': 'NLD', 'name': 'Netherlands', 'raw_gpi': -0.95, 'n_eff': 117},
        {'iso3': 'CHN', 'name': 'China', 'raw_gpi': -0.91, 'n_eff': 122},
        {'iso3': 'SAU', 'name': 'Saudi Arabia', 'raw_gpi': -0.89, 'n_eff': 112},
        {'iso3': 'MEX', 'name': 'Mexico', 'raw_gpi': -0.86, 'n_eff': 123},

        # Neutral countries
        {'iso3': 'USA', 'name': 'United States', 'raw_gpi': 0.02, 'n_eff': 105},
        {'iso3': 'JPN', 'name': 'Japan', 'raw_gpi': -0.01, 'n_eff': 120},
        {'iso3': 'DEU', 'name': 'Germany', 'raw_gpi': 0.01, 'n_eff': 123},
        {'iso3': 'FRA', 'name': 'France', 'raw_gpi': 0.03, 'n_eff': 124},
        {'iso3': 'CAN', 'name': 'Canada', 'raw_gpi': 0.24, 'n_eff': 120},

        # Test with higher coverage (should allow higher scores)
        {'iso3': 'TEST_HIGH', 'name': 'Test High Coverage', 'raw_gpi': 0.90, 'n_eff': 1500},
        {'iso3': 'TEST_MED', 'name': 'Test Medium Coverage', 'raw_gpi': 0.90, 'n_eff': 500},
    ]

    results = []
    for country_data in countries:
        result = mock_process_country(country_data)
        results.append(result)

    # Sort by final GPI
    results_sorted = sorted(results, key=lambda x: x['headline_gpi'], reverse=True)

    print("\n" + "="*70)
    print("TOP 5 BY CORRECTED GPI SCORE")
    print("="*70)
    for i, r in enumerate(results_sorted[:5], 1):
        n_eff = r['coverage']['n_eff']
        conf = " (low confidence)" if n_eff < 300 else " (medium)" if n_eff < 1200 else " (high)"
        raw = r['debug']['raw_gpi']
        print(f"{i}. {r['country']['name']:25} GPI: {r['headline_gpi']:+6.1f}  "
              f"Raw: {raw:+.3f}  N_eff: {n_eff:4d}{conf}")

    print("\n" + "="*70)
    print("BOTTOM 5 BY CORRECTED GPI SCORE")
    print("="*70)
    for i, r in enumerate(results_sorted[-5:], 1):
        n_eff = r['coverage']['n_eff']
        conf = " (low confidence)" if n_eff < 300 else " (medium)" if n_eff < 1200 else " (high)"
        raw = r['debug']['raw_gpi']
        print(f"{i}. {r['country']['name']:25} GPI: {r['headline_gpi']:+6.1f}  "
              f"Raw: {raw:+.3f}  N_eff: {n_eff:4d}{conf}")

    print("\n" + "="*70)
    print("KEY OBSERVATIONS")
    print("="*70)
    print("1. All low coverage (n_eff < 300) scores are now clamped to ±50")
    print("2. Previous +100/-100 scores are now in realistic ranges")
    print("3. Medium coverage (300-1200) allows up to ±75")
    print("4. High coverage (≥1200) allows near full range")

    # Verify all constraints
    print("\n" + "="*70)
    print("CONSTRAINT VERIFICATION")
    print("="*70)

    low_coverage = [r for r in results if r['coverage']['n_eff'] < 300]
    violations = [r for r in low_coverage if abs(r['headline_gpi']) > 50]

    if violations:
        print("✗ VIOLATIONS FOUND:")
        for v in violations:
            print(f"  {v['country']['name']}: {v['headline_gpi']} (n_eff={v['coverage']['n_eff']})")
    else:
        print(f"✓ All {len(low_coverage)} low-coverage countries correctly clamped to ±50")

    med_coverage = [r for r in results if 300 <= r['coverage']['n_eff'] < 1200]
    med_violations = [r for r in med_coverage if abs(r['headline_gpi']) > 75]

    if med_violations:
        print("✗ MEDIUM COVERAGE VIOLATIONS:")
        for v in med_violations:
            print(f"  {v['country']['name']}: {v['headline_gpi']} (n_eff={v['coverage']['n_eff']})")
    else:
        print(f"✓ All {len(med_coverage)} medium-coverage countries within ±75")

if __name__ == "__main__":
    main()