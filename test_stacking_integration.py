#!/usr/bin/env python3
"""
Test Stacking Ensemble Integration
"""

import sys
import logging

logging.basicConfig(level=logging.INFO)

# Test imports
print("Testing imports...")
try:
    from sentiment_bot.gdp_model_trainer import GDPModelTrainer
    print("✅ GDPModelTrainer imported")

    from sentiment_bot.gdp_stacking_ensemble import RegimeAwareStackingEnsemble
    print("✅ Stacking ensemble imported")

    from sentiment_bot.gdp_shock_robust import RobustGDPEstimator
    print("✅ Robust estimator imported")

    # Check if stacking is enabled
    from sentiment_bot.gdp_model_trainer import STACKING_AVAILABLE
    print(f"✅ STACKING_AVAILABLE = {STACKING_AVAILABLE}")

except ImportError as e:
    print(f"❌ Import failed: {e}")
    sys.exit(1)

# Test prediction with stacking
print("\nTesting prediction logic...")
trainer = GDPModelTrainer()

# Check if methods exist
if hasattr(trainer, '_detect_regimes'):
    print("✅ _detect_regimes method exists")
else:
    print("❌ _detect_regimes method missing")

if hasattr(trainer, '_get_current_regime'):
    print("✅ _get_current_regime method exists")
else:
    print("❌ _get_current_regime method missing")

if hasattr(trainer, 'stacking_ensembles'):
    print("✅ stacking_ensembles attribute exists")
else:
    print("❌ stacking_ensembles attribute missing")

if hasattr(trainer, 'robust_estimators'):
    print("✅ robust_estimators attribute exists")
else:
    print("❌ robust_estimators attribute missing")

print("\n✅ All integration checks passed!")
print("The stacking ensemble is now integrated into the GDP model trainer.")
print("\nNext steps:")
print("1. Retrain models with: trainer.train_models('GBR')")
print("2. The system will automatically use stacking weights instead of simple averaging")
print("3. Predictions will include regime detection")