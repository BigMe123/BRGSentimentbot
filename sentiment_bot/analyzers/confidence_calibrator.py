"""
Calibrated confidence via isotonic regression.

Takes raw model confidence scores and maps them to calibrated probabilities
using isotonic regression fitted on a gold set. When no gold set is available,
falls back to a simple bin-based heuristic.
"""

import json
import logging
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

CALIBRATION_FILE = Path(__file__).parent.parent / "state" / "calibration_model.json"


class ConfidenceCalibrator:
    """
    Calibrate raw confidence scores to true probabilities.

    Uses sklearn IsotonicRegression when a gold set is available,
    otherwise applies a conservative heuristic that shrinks scores toward 0.5.
    """

    def __init__(self):
        self._isotonic = None
        self._fitted = False
        self._load_cached()

    def _load_cached(self):
        """Load previously fitted calibration model."""
        if not CALIBRATION_FILE.exists():
            return
        try:
            data = json.loads(CALIBRATION_FILE.read_text())
            from sklearn.isotonic import IsotonicRegression
            iso = IsotonicRegression(out_of_bounds="clip")
            iso.X_thresholds_ = np.array(data["X_thresholds"])
            iso.y_thresholds_ = np.array(data["y_thresholds"])
            iso.X_min_ = data["X_min"]
            iso.X_max_ = data["X_max"]
            iso.f_ = None  # Will be rebuilt on transform
            self._isotonic = iso
            self._fitted = True
            logger.debug("Loaded cached calibration model")
        except Exception as e:
            logger.debug(f"Could not load calibration: {e}")

    def fit(self, gold_path: str) -> Dict:
        """
        Fit calibration model from a labeled gold set.

        Args:
            gold_path: Path to gold JSONL with fields:
                       raw_confidence, gold_label, predicted_label

        Returns:
            Fit stats: {n_samples, brier_before, brier_after}
        """
        records = []
        with open(gold_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                    if "raw_confidence" in r and "gold_label" in r and "predicted_label" in r:
                        records.append(r)
                except json.JSONDecodeError:
                    continue

        if len(records) < 10:
            return {"error": "Need at least 10 labeled samples"}

        # Binary: 1 if prediction was correct, 0 otherwise
        raw_conf = np.array([r["raw_confidence"] for r in records])
        correct = np.array([1.0 if r["gold_label"] == r["predicted_label"] else 0.0 for r in records])

        # Brier score before calibration
        brier_before = float(np.mean((raw_conf - correct) ** 2))

        # Fit isotonic regression
        from sklearn.isotonic import IsotonicRegression
        iso = IsotonicRegression(out_of_bounds="clip")
        iso.fit(raw_conf, correct)
        self._isotonic = iso
        self._fitted = True

        # Brier score after calibration
        calibrated = iso.predict(raw_conf)
        brier_after = float(np.mean((calibrated - correct) ** 2))

        # Cache the model
        self._save_cached()

        return {
            "n_samples": len(records),
            "brier_before": round(brier_before, 4),
            "brier_after": round(brier_after, 4),
            "improvement": round((brier_before - brier_after) / max(brier_before, 1e-6) * 100, 1),
        }

    def _save_cached(self):
        """Save fitted model to disk."""
        if not self._isotonic or not self._fitted:
            return
        try:
            CALIBRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "X_thresholds": self._isotonic.X_thresholds_.tolist(),
                "y_thresholds": self._isotonic.y_thresholds_.tolist(),
                "X_min": float(self._isotonic.X_min_),
                "X_max": float(self._isotonic.X_max_),
            }
            CALIBRATION_FILE.write_text(json.dumps(data))
        except Exception as e:
            logger.debug(f"Could not save calibration: {e}")

    def calibrate(self, raw_confidence: float) -> float:
        """
        Calibrate a single confidence score.

        Args:
            raw_confidence: Model's raw confidence (0-1)

        Returns:
            Calibrated probability (0-1)
        """
        if self._fitted and self._isotonic is not None:
            try:
                return float(self._isotonic.predict([raw_confidence])[0])
            except Exception:
                pass

        # Heuristic fallback: shrink toward 0.5
        return 0.5 + (raw_confidence - 0.5) * 0.7

    def calibrate_batch(self, scores: List[float]) -> List[float]:
        """Calibrate a batch of scores."""
        if self._fitted and self._isotonic is not None:
            try:
                return self._isotonic.predict(np.array(scores)).tolist()
            except Exception:
                pass
        return [self.calibrate(s) for s in scores]

    @property
    def is_fitted(self) -> bool:
        return self._fitted
