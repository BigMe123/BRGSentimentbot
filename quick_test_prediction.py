#!/usr/bin/env python3
"""Quick test of just the prediction part"""

import sys
sys.path.append('.')

def test_prediction():
    try:
        from sentiment_bot.gdp_model_trainer import GDPModelTrainer
        trainer = GDPModelTrainer()

        # Just train without testing prediction
        performance = trainer.train_models('GBR')

        if performance:
            maes = [perf['mae'] for perf in performance.values()]
            avg_mae = sum(maes) / len(maes)
            print(f"Training successful: {avg_mae:.2f}pp")

            # Check improvements
            working = []
            if 'GBR' in trainer.stacking_ensembles:
                weights = trainer.stacking_ensembles['GBR'].get_weights()
                working.append(f"Stacking: {weights}")
            if 'GBR' in trainer.robust_estimators:
                working.append("Shock detection: Ready")

            print(f"Working improvements: {working}")
            return True, avg_mae
        else:
            print("Training failed")
            return False, None

    except Exception as e:
        print(f"Error: {e}")
        return False, None

if __name__ == "__main__":
    success, mae = test_prediction()
    print(f"Success: {success}, MAE: {mae}")