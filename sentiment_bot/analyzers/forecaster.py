"""
Sentiment forecasting using exponential smoothing.

Reads historical country/entity baselines and projects short-term sentiment
trends. Uses simple exponential smoothing (no ARIMA dependency) with
adaptive alpha.
"""

import json
import logging
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)

BASELINE_FILE = Path(__file__).parent.parent / "state" / "country_baselines.jsonl"
ENTITY_FILE = Path(__file__).parent.parent / "state" / "entity_history.jsonl"


def _exponential_smooth(values: List[float], alpha: float = 0.3) -> List[float]:
    """Apply simple exponential smoothing."""
    if not values:
        return []
    smoothed = [values[0]]
    for v in values[1:]:
        smoothed.append(alpha * v + (1 - alpha) * smoothed[-1])
    return smoothed


def _forecast_next(smoothed: List[float], periods: int = 3) -> List[float]:
    """Forecast next N periods from smoothed series (flat forecast)."""
    if not smoothed:
        return [0.0] * periods
    last = smoothed[-1]
    # Simple trend: average of last 3 deltas
    if len(smoothed) >= 4:
        deltas = [smoothed[i] - smoothed[i - 1] for i in range(-3, 0)]
        trend = sum(deltas) / len(deltas)
    else:
        trend = 0.0
    return [round(last + trend * (i + 1), 4) for i in range(periods)]


class SentimentForecaster:
    """
    Forecast country/entity sentiment trends.

    Reads historical scan data and projects forward using
    exponential smoothing with optional trend.
    """

    def __init__(self, alpha: float = 0.3, min_history: int = 5):
        self.alpha = alpha
        self.min_history = min_history

    def forecast_countries(self, periods: int = 3) -> Dict[str, Dict]:
        """
        Forecast sentiment for countries with enough history.

        Returns:
            {country: {history, smoothed, forecast, trend, current}}
        """
        history = self._load_country_history()
        results = {}

        for country, records in history.items():
            if len(records) < self.min_history:
                continue

            values = [r["avg_sentiment"] for r in records]
            smoothed = _exponential_smooth(values, self.alpha)
            forecast = _forecast_next(smoothed, periods)

            # Trend direction
            if len(smoothed) >= 2:
                recent_trend = smoothed[-1] - smoothed[-2]
            else:
                recent_trend = 0.0

            if recent_trend > 0.02:
                direction = "improving"
            elif recent_trend < -0.02:
                direction = "deteriorating"
            else:
                direction = "stable"

            results[country] = {
                "current": round(values[-1], 4),
                "smoothed_current": round(smoothed[-1], 4),
                "forecast": forecast,
                "trend": round(recent_trend, 4),
                "direction": direction,
                "history_points": len(records),
            }

        return results

    def forecast_entities(self, periods: int = 3, top_n: int = 20) -> Dict[str, Dict]:
        """
        Forecast sentiment for top entities by mention count.

        Returns:
            {entity: {current, forecast, trend, direction, history_points}}
        """
        history = self._load_entity_history()

        # Rank by total mentions
        entity_totals = {
            e: sum(r["mentions"] for r in recs)
            for e, recs in history.items()
        }
        top_entities = sorted(entity_totals, key=entity_totals.get, reverse=True)[:top_n]

        results = {}
        for entity in top_entities:
            records = history[entity]
            if len(records) < self.min_history:
                continue

            values = [r.get("mean_sentiment", 0.0) for r in records]
            smoothed = _exponential_smooth(values, self.alpha)
            forecast = _forecast_next(smoothed, periods)

            recent_trend = smoothed[-1] - smoothed[-2] if len(smoothed) >= 2 else 0.0
            direction = "improving" if recent_trend > 0.02 else ("deteriorating" if recent_trend < -0.02 else "stable")

            results[entity] = {
                "current": round(values[-1], 4),
                "forecast": forecast,
                "trend": round(recent_trend, 4),
                "direction": direction,
                "history_points": len(records),
            }

        return results

    def _load_country_history(self) -> Dict[str, List[Dict]]:
        """Load country baselines from state file."""
        history = defaultdict(list)
        if not BASELINE_FILE.exists():
            return history

        with open(BASELINE_FILE) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                    country = r.get("country", "")
                    if country:
                        history[country].append(r)
                except json.JSONDecodeError:
                    continue

        # Sort each country's records by timestamp
        for country in history:
            history[country].sort(key=lambda r: r.get("timestamp", ""))

        return dict(history)

    def _load_entity_history(self) -> Dict[str, List[Dict]]:
        """Load entity history from state file."""
        history = defaultdict(list)
        if not ENTITY_FILE.exists():
            return history

        with open(ENTITY_FILE) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                    entity = r.get("entity", "")
                    if entity:
                        history[entity].append(r)
                except json.JSONDecodeError:
                    continue

        for entity in history:
            history[entity].sort(key=lambda r: r.get("timestamp", ""))

        return dict(history)
