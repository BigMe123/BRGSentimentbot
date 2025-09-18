#!/usr/bin/env python3
"""Test the integrated GPI ranking system."""

from generate_top30_ranking import generate_top30_ranking
import json
from datetime import datetime

def test_integration():
    """Test the GPI ranking integration."""

    print("Testing GPI Ranking Integration")
    print("="*70)

    # Generate rankings
    results = generate_top30_ranking()

    # Test different configurations
    configurations = [
        {"top": 3, "bottom": 3, "detail": "summary"},
        {"top": 5, "bottom": 5, "detail": "detailed"},
        {"top": 10, "bottom": 5, "detail": "full"},
    ]

    for config in configurations:
        top = config["top"]
        bottom = config["bottom"]
        detail = config["detail"]

        print(f"\n{'='*70}")
        print(f"Configuration: Top {top}, Bottom {bottom}, Detail: {detail}")
        print("="*70)

        # Display top countries
        print(f"\n📈 TOP {top} COUNTRIES")
        print("-"*50)

        for i, r in enumerate(results[:top], 1):
            conf_badge = "🟢" if r['confidence'] == 'High' else "🟡" if r['confidence'] == 'Medium' else "🔴"

            print(f"\n{i}. {r['country']} ({r['iso3']})")
            print(f"   GPI: {r['headline_gpi']:+6.1f} {conf_badge} n_eff={r['n_eff']}")

            if detail in ["detailed", "full"]:
                print(f"   Why: {r['why'][:80]}...")
                print(f"   Drivers: {' | '.join(r['top_drivers'])}")

            if detail == "full":
                print(f"   Headlines:")
                for headline in r['headlines'][:2]:
                    print(f"      • {headline}")

        # Display bottom countries
        print(f"\n📉 BOTTOM {bottom} COUNTRIES")
        print("-"*50)

        bottom_results = results[-bottom:]
        bottom_results.reverse()

        for i, r in enumerate(bottom_results, 1):
            conf_badge = "🟢" if r['confidence'] == 'High' else "🟡" if r['confidence'] == 'Medium' else "🔴"

            print(f"\n{i}. {r['country']} ({r['iso3']})")
            print(f"   GPI: {r['headline_gpi']:+6.1f} {conf_badge} n_eff={r['n_eff']}")

            if detail in ["detailed", "full"]:
                print(f"   Why: {r['why'][:80]}...")
                print(f"   Drivers: {' | '.join(r['top_drivers'])}")

            if detail == "full":
                print(f"   Headlines:")
                for headline in r['headlines'][:2]:
                    print(f"      • {headline}")

    # Test save functionality
    output_data = {
        'timestamp': datetime.now().isoformat(),
        'test_config': "top_5_bottom_5",
        'top_5': results[:5],
        'bottom_5': bottom_results,
    }

    with open('test_gpi_ranking.json', 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"\n✅ Test complete! Results saved to test_gpi_ranking.json")
    print(f"Total countries ranked: {len(results)}")

    # Verify statistics
    avg_neff = sum(r['n_eff'] for r in results) / len(results)
    print(f"Average n_eff: {avg_neff:.0f}")

    if avg_neff >= 300:
        print("✅ Target n_eff ≥ 300 achieved!")
    else:
        print("⚠️ Average n_eff below target")

if __name__ == "__main__":
    test_integration()