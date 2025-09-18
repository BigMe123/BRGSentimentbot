#!/usr/bin/env python3
"""
Retrain GDP Models with All Improvements
========================================
Retrains models with:
- DFM (5th model)
- Stacking ensemble weights
- Country-specific features
- Regime detection
- Shock-robust estimation
"""

import asyncio
import logging
import json
from datetime import datetime
import sys
sys.path.append('.')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def retrain_models():
    """Retrain models with all improvements"""

    print("="*80)
    print("RETRAINING GDP MODELS WITH ALL IMPROVEMENTS")
    print("="*80)
    print(f"Timestamp: {datetime.now().isoformat()}")

    try:
        from sentiment_bot.gdp_model_trainer import GDPModelTrainer

        trainer = GDPModelTrainer()

        # Countries to retrain (starting with worst performer)
        countries = ['GBR', 'USA', 'JPN', 'DEU']

        results = {}

        for country in countries:
            print(f"\n{'='*60}")
            print(f"RETRAINING {country}")
            print(f"{'='*60}")

            try:
                # Train models with all improvements
                performance = trainer.train_models(country)

                if performance:
                    results[country] = performance

                    # Calculate average MAE
                    maes = [perf['mae'] for perf in performance.values()]
                    avg_mae = sum(maes) / len(maes)

                    print(f"\n✅ {country} RETRAINED:")
                    print(f"   Average MAE: {avg_mae:.2f}pp")
                    print(f"   Individual MAEs: {[round(mae, 2) for mae in maes]}")

                    # Check if stacking was trained
                    if country in trainer.stacking_ensembles:
                        print(f"   ✅ Stacking ensemble trained")
                        weights = trainer.stacking_ensembles[country].get_weights()
                        print(f"   Global weights: {weights}")
                    else:
                        print(f"   ⚠️ No stacking ensemble")

                else:
                    print(f"❌ {country} training failed - no performance data")

            except Exception as e:
                print(f"❌ {country} training failed: {e}")
                logger.error(f"Training failed for {country}: {e}")

        # Save results
        report = {
            'timestamp': datetime.now().isoformat(),
            'retrained_countries': list(results.keys()),
            'performance': results,
            'improvements_used': [
                'DFM (5th model)',
                'Stacking ensemble weights',
                'Country-specific features',
                'Regime detection',
                'Robust estimation'
            ]
        }

        with open('retrain_results.json', 'w') as f:
            json.dump(report, f, indent=2)

        print(f"\n{'='*80}")
        print("RETRAINING SUMMARY")
        print(f"{'='*80}")

        if results:
            print(f"✅ Successfully retrained {len(results)} countries")

            # Compare to old performance
            old_performance = {
                'USA': 1.26,
                'GBR': 3.40,
                'JPN': 1.62,
                'DEU': 1.32
            }

            print(f"\n📊 MAE COMPARISON:")
            print(f"{'Country':<8} {'Old MAE':<12} {'New MAE':<12} {'Change':<12}")
            print("-" * 50)

            for country in results:
                if country in old_performance:
                    old_mae = old_performance[country]
                    maes = [perf['mae'] for perf in results[country].values()]
                    new_mae = sum(maes) / len(maes)
                    change = new_mae - old_mae
                    change_pct = (change / old_mae) * 100

                    change_str = f"{change:+.2f}pp ({change_pct:+.0f}%)"
                    print(f"{country:<8} {old_mae:<12.2f} {new_mae:<12.2f} {change_str}")

            print(f"\n💾 Results saved to retrain_results.json")
        else:
            print("❌ No countries successfully retrained")

    except Exception as e:
        print(f"❌ Retraining failed: {e}")
        logger.error(f"Retraining failed: {e}")

if __name__ == "__main__":
    asyncio.run(retrain_models())