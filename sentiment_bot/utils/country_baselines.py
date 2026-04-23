"""
Baseline-relative country risk scoring.

Accumulates per-country sentiment history across scans. Risk becomes
a z-score against the rolling mean, solving:
  - "Afghanistan is always Critical" (baseline adjusts)
  - "Small country with 3 articles triggers alerts" (Bayesian smoothing)
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from collections import defaultdict

STATE_FILE = Path(__file__).parent.parent / "state" / "country_baselines.jsonl"


def _load_history() -> Dict[str, List[Dict]]:
    """Load country sentiment history from state file."""
    history = defaultdict(list)
    if not STATE_FILE.exists():
        return history
    with open(STATE_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                country = record.get("country", "")
                if country:
                    history[country].append(record)
            except json.JSONDecodeError:
                continue
    return history


def record_scan(country_sentiments: List[Dict]):
    """
    Append current scan's country sentiments to the history file.

    Args:
        country_sentiments: List of {country, sentiment, article_count} dicts
    """
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().isoformat()
    with open(STATE_FILE, "a") as f:
        for cs in country_sentiments:
            record = {
                "country": cs["country"],
                "sentiment": cs["sentiment"],
                "article_count": cs.get("article_count", 1),
                "timestamp": ts,
            }
            f.write(json.dumps(record) + "\n")


def compute_risk_levels(
    current_sentiments: Dict[str, Dict],
    smoothing_k: int = 5,
    history_days: int = 90,
) -> Dict[str, Dict]:
    """
    Compute baseline-relative risk levels for countries.

    Args:
        current_sentiments: {country: {sentiment: float, article_count: int}}
        smoothing_k: Bayesian smoothing strength (higher = more pull toward global mean)
        history_days: Rolling window in days

    Returns:
        {country: {risk_level, z_score, smoothed_sentiment, raw_sentiment, article_count, baseline_mean, baseline_std}}
    """
    import numpy as np

    history = _load_history()

    # Cutoff for rolling window
    cutoff = datetime.now().timestamp() - (history_days * 86400)

    # Global mean across all current sentiments (for Bayesian smoothing)
    all_sentiments = [v["sentiment"] for v in current_sentiments.values() if v.get("sentiment") is not None]
    global_mean = np.mean(all_sentiments) if all_sentiments else 0.0

    results = {}
    for country, data in current_sentiments.items():
        raw_sentiment = data["sentiment"]
        n = data.get("article_count", 1)

        # Bayesian smoothing: pull low-volume countries toward global mean
        smoothed = (n * raw_sentiment + smoothing_k * global_mean) / (n + smoothing_k)

        # Get historical data for this country
        country_history = history.get(country, [])
        historical_sentiments = []
        for record in country_history:
            try:
                ts = datetime.fromisoformat(record["timestamp"]).timestamp()
                if ts >= cutoff:
                    historical_sentiments.append(record["sentiment"])
            except (ValueError, KeyError):
                continue

        # Compute z-score against baseline
        if len(historical_sentiments) >= 3:
            baseline_mean = np.mean(historical_sentiments)
            baseline_std = np.std(historical_sentiments)
            if baseline_std > 0.01:
                z = (smoothed - baseline_mean) / baseline_std
            else:
                z = 0.0
        else:
            # Not enough history — use absolute thresholds
            baseline_mean = 0.0
            baseline_std = 0.0
            z = smoothed * 3  # rough scaling to match z-score range

        # Map z-score to risk bands
        if z <= -2.0:
            risk_level = "critical"
        elif z <= -1.0:
            risk_level = "high"
        elif z <= -0.5:
            risk_level = "elevated"
        elif z >= 1.0:
            risk_level = "improving"
        else:
            risk_level = "normal"

        results[country] = {
            "risk_level": risk_level,
            "z_score": round(float(z), 2),
            "smoothed_sentiment": round(float(smoothed), 3),
            "raw_sentiment": round(float(raw_sentiment), 3),
            "article_count": n,
            "baseline_mean": round(float(baseline_mean), 3),
            "baseline_std": round(float(baseline_std), 3),
            "history_points": len(historical_sentiments),
        }

    return results
