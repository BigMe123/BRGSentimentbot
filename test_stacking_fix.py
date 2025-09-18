#!/usr/bin/env python3
"""
Test Stacking Ensemble Fix
"""

import sys
import logging
sys.path.append('.')

logging.basicConfig(level=logging.INFO)

def test_stacking_fix():
    """Test if stacking ensemble fix works"""

    print("Testing Stacking Ensemble Index Fix")
    print("=" * 50)

    try:
        from sentiment_bot.gdp_model_trainer import GDPModelTrainer

        trainer = GDPModelTrainer()

        print("\nTesting GBR training with stacking fix...")
        performance = trainer.train_models('GBR')

        if performance:
            maes = [perf['mae'] for perf in performance.values()]
            avg_mae = sum(maes) / len(maes)

            print(f"✅ Training successful")
            print(f"   Average MAE: {avg_mae:.2f}pp")

            # Check if stacking worked
            if 'GBR' in trainer.stacking_ensembles:
                print(f"   ✅ Stacking ensemble trained successfully!")
                weights = trainer.stacking_ensembles['GBR'].get_weights()
                print(f"   Learned weights: {weights}")
                return True, avg_mae
            else:
                print(f"   ❌ Stacking still failed")
                return False, avg_mae
        else:
            print("❌ Training failed")
            return False, None

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False, None

if __name__ == "__main__":
    success, mae = test_stacking_fix()

    # Performance threshold
    baseline_mae = 3.08

    if mae is not None:
        if mae <= baseline_mae + 0.05:
            print(f"\n✅ Performance maintained: {mae:.2f}pp vs {baseline_mae:.2f}pp baseline")
        else:
            print(f"\n❌ Performance degraded: {mae:.2f}pp vs {baseline_mae:.2f}pp baseline")

    print(f"\nStacking working: {success}")