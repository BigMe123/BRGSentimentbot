#!/usr/bin/env python3
"""
Test DFM Fix - Check Performance Impact
"""

import sys
import logging
sys.path.append('.')

logging.basicConfig(level=logging.INFO)

def test_dfm_fix():
    """Test if DFM fix maintains or improves performance"""

    print("Testing DFM Broadcasting Fix")
    print("=" * 50)

    try:
        from sentiment_bot.gdp_model_trainer import GDPModelTrainer

        trainer = GDPModelTrainer()

        print("\nTesting GBR training with DFM fix...")
        performance = trainer.train_models('GBR')

        if performance:
            maes = [perf['mae'] for perf in performance.values()]
            avg_mae = sum(maes) / len(maes)

            print(f"✅ Training successful")
            print(f"   Average MAE: {avg_mae:.2f}pp")
            print(f"   Individual MAEs: {[round(mae, 2) for mae in maes]}")

            # Check if DFM worked
            if 'GBR_dfm' in trainer.models:
                print(f"   ✅ DFM model trained successfully!")
                return True, avg_mae
            else:
                print(f"   ❌ DFM still failed")
                return False, avg_mae
        else:
            print("❌ Training failed")
            return False, None

    except Exception as e:
        print(f"❌ Error: {e}")
        return False, None

if __name__ == "__main__":
    success, mae = test_dfm_fix()

    # Performance threshold
    baseline_mae = 3.08  # Previous best

    if mae is not None:
        if mae <= baseline_mae + 0.05:  # Allow 0.05pp tolerance
            print(f"\n✅ Performance maintained: {mae:.2f}pp vs {baseline_mae:.2f}pp baseline")
        else:
            print(f"\n❌ Performance degraded: {mae:.2f}pp vs {baseline_mae:.2f}pp baseline")
            print("   Should revert changes!")

    print(f"\nDFM working: {success}")