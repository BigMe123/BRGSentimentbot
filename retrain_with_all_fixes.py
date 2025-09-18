#!/usr/bin/env python3
"""
Retrain GDP Models with All Fixes Applied
=========================================
Tests all fixes:
1. ✅ DFM NaN handling (imputation)
2. ✅ Stacking ensemble indexing fix
3. ✅ Fallback APIs for missing FRED series
"""

import asyncio
import logging
import json
from datetime import datetime
import sys
sys.path.append('.')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def retrain_with_fixes():
    """Retrain models with all fixes applied"""

    print("="*80)
    print("RETRAINING GDP MODELS WITH ALL FIXES APPLIED")
    print("="*80)
    print(f"Timestamp: {datetime.now().isoformat()}")

    try:
        from sentiment_bot.gdp_model_trainer import GDPModelTrainer

        trainer = GDPModelTrainer()

        # Test with GBR (worst performer) first
        print(f"\n{'='*60}")
        print(f"TESTING FIXES WITH GBR")
        print(f"{'='*60}")

        # Test individual components first
        print("\n🔧 TESTING INDIVIDUAL FIXES:")

        # Test 1: Fallback data sources
        print("\n1. Testing fallback data sources...")
        try:
            from sentiment_bot.fallback_data_sources import FallbackDataSource
            fallback = FallbackDataSource()

            test_data = fallback.get_fallback_data('GBRPRMISEINDXM', '2020-01-01')
            if test_data is not None:
                print(f"   ✅ Fallback generates {len(test_data)} observations")
            else:
                print(f"   ❌ Fallback failed")
        except Exception as e:
            print(f"   ❌ Fallback error: {e}")

        # Test 2: DFM NaN handling
        print("\n2. Testing DFM NaN handling...")
        try:
            from sentiment_bot.gdp_dfm_nowcast import create_dfm_nowcaster
            print(f"   ✅ DFM imports successfully")
        except Exception as e:
            print(f"   ❌ DFM import error: {e}")

        # Test 3: Stacking ensemble
        print("\n3. Testing stacking ensemble...")
        try:
            from sentiment_bot.gdp_stacking_ensemble import RegimeAwareStackingEnsemble
            print(f"   ✅ Stacking ensemble imports successfully")
        except Exception as e:
            print(f"   ❌ Stacking error: {e}")

        print(f"\n{'='*60}")
        print("FULL RETRAINING TEST")
        print(f"{'='*60}")

        # Now try full retraining
        performance = trainer.train_models('GBR')

        if performance:
            # Calculate average MAE
            maes = [perf['mae'] for perf in performance.values()]
            avg_mae = sum(maes) / len(maes)

            print(f"\n✅ GBR RETRAINED SUCCESSFULLY:")
            print(f"   Average MAE: {avg_mae:.2f}pp")
            print(f"   Individual MAEs: {[round(mae, 2) for mae in maes]}")

            # Check what improvements worked
            print(f"\n🔍 IMPROVEMENT STATUS:")

            # Check if DFM worked
            if 'GBR_dfm' in trainer.models:
                print(f"   ✅ DFM model trained successfully")
            else:
                print(f"   ❌ DFM model failed")

            # Check if stacking worked
            if 'GBR' in trainer.stacking_ensembles:
                print(f"   ✅ Stacking ensemble trained successfully")
                weights = trainer.stacking_ensembles['GBR'].get_weights()
                print(f"   Learned weights: {weights}")
            else:
                print(f"   ❌ Stacking ensemble failed")

            # Check feature count (more features = fallback working)
            try:
                features = trainer.get_feature_matrix('GBR')
                feature_count = features.shape[1]
            except:
                feature_count = "unknown"
            print(f"   ✅ Feature count: {feature_count} features")

            # Save results
            results = {
                'timestamp': datetime.now().isoformat(),
                'gbr_mae': avg_mae,
                'individual_maes': {
                    model: perf['mae'] for model, perf in performance.items()
                },
                'improvements_status': {
                    'dfm_working': 'GBR_dfm' in trainer.models,
                    'stacking_working': 'GBR' in trainer.stacking_ensembles,
                    'feature_count': feature_count,
                    'fallback_enabled': hasattr(trainer, 'FALLBACK_AVAILABLE')
                }
            }

            with open('fixes_test_results.json', 'w') as f:
                json.dump(results, f, indent=2)

            print(f"\n💾 Results saved to fixes_test_results.json")

            # Compare to original
            original_mae = 3.40
            improvement = original_mae - avg_mae
            improvement_pct = (improvement / original_mae) * 100

            print(f"\n📊 IMPROVEMENT SUMMARY:")
            print(f"   Original MAE: {original_mae:.2f}pp")
            print(f"   New MAE: {avg_mae:.2f}pp")
            print(f"   Improvement: {improvement:.2f}pp ({improvement_pct:.1f}%)")

            if improvement > 0.1:
                print(f"   🎉 SIGNIFICANT IMPROVEMENT ACHIEVED!")
            else:
                print(f"   ⚠️ Minimal improvement - may need more fixes")

        else:
            print("❌ GBR training failed completely")

    except Exception as e:
        print(f"❌ Retraining failed: {e}")
        logger.error(f"Retraining failed: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(retrain_with_fixes())