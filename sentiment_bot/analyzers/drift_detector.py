"""
Population Stability Index (PSI) drift detector for sentiment scans.

Tracks the distribution of sentiment scores across runs and flags when a
new run's distribution diverges materially from a rolling baseline. PSI is
the standard metric in credit risk + AML for distribution drift, and is a
better fit here than KL-divergence because it is symmetric, bounded in
practice, and easy to interpret.

Interpretation (industry convention):
    PSI < 0.10     no significant change
    0.10 - 0.25    moderate shift (investigate)
    > 0.25         significant shift (alert)

Usage:
    detector = DriftDetector()
    detector.update_baseline(score_history)         # list[float] from prior runs
    psi = detector.psi(current_scores)              # PSI for current scan
    bands = detector.bin_distribution(scores)       # to plot

The detector is stateless across runs — it is recomputed each call from the
prior runs JSONL, which is cheap because we cap baseline to ~10k samples.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


# Bin edges for sentiment scores: capture concentration around neutral
DEFAULT_BINS: List[Tuple[float, float]] = [
    (-1.001, -0.50),
    (-0.50,  -0.20),
    (-0.20,  -0.05),
    (-0.05,   0.05),
    ( 0.05,   0.20),
    ( 0.20,   0.50),
    ( 0.50,   1.001),
]
BIN_LABELS = ["Strong-", "Moderate-", "Mild-", "Neutral", "Mild+", "Moderate+", "Strong+"]


@dataclass
class DriftReport:
    psi: float
    severity: str  # "stable" | "moderate" | "significant"
    baseline_pct: List[float]
    current_pct: List[float]
    bin_labels: List[str]
    n_baseline: int
    n_current: int


class DriftDetector:
    def __init__(self, bins: Optional[Sequence[Tuple[float, float]]] = None):
        self.bins = list(bins) if bins is not None else DEFAULT_BINS
        self.labels = BIN_LABELS if not bins else [f"bin_{i}" for i in range(len(self.bins))]

    def bin_distribution(self, scores: Sequence[float]) -> List[float]:
        """Return percentage of scores falling in each bin (sums to 1.0)."""
        if not scores:
            return [0.0] * len(self.bins)
        counts = [0] * len(self.bins)
        for s in scores:
            for i, (lo, hi) in enumerate(self.bins):
                if lo < s <= hi:
                    counts[i] += 1
                    break
        total = sum(counts) or 1
        return [c / total for c in counts]

    def psi(
        self,
        current: Sequence[float],
        baseline: Sequence[float],
        epsilon: float = 1e-4,
    ) -> DriftReport:
        """Compute PSI between current and baseline score distributions."""
        cur_pct = self.bin_distribution(current)
        base_pct = self.bin_distribution(baseline)

        # Smooth zeros so log() is finite
        cur_s  = [max(p, epsilon) for p in cur_pct]
        base_s = [max(p, epsilon) for p in base_pct]

        import math
        psi_value = sum(
            (c - b) * math.log(c / b)
            for c, b in zip(cur_s, base_s)
        )

        if psi_value < 0.10:
            severity = "stable"
        elif psi_value < 0.25:
            severity = "moderate"
        else:
            severity = "significant"

        return DriftReport(
            psi=round(psi_value, 4),
            severity=severity,
            baseline_pct=base_pct,
            current_pct=cur_pct,
            bin_labels=self.labels,
            n_baseline=len(baseline),
            n_current=len(current),
        )
