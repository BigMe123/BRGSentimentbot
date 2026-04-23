"""
Cross-scan entity tracking.

Tracks per-entity metrics across scans: mention count, sentiment, stance
distribution. Computes z-scores to flag "movers" — entities with significant
volume or sentiment changes.
"""

import json
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from collections import defaultdict

STATE_FILE = Path(__file__).parent.parent / "state" / "entity_history.jsonl"


def _load_history() -> Dict[str, List[Dict]]:
    """Load entity history."""
    history = defaultdict(list)
    if not STATE_FILE.exists():
        return history
    with open(STATE_FILE) as f:
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
    return history


def record_entities(entity_data: List[Dict]):
    """
    Append current scan's entity data to history.

    Args:
        entity_data: List of {entity, type, mentions, mean_sentiment, stances}
    """
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().isoformat()
    with open(STATE_FILE, "a") as f:
        for ed in entity_data:
            record = {
                "entity": ed["entity"],
                "type": ed.get("type", "UNKNOWN"),
                "mentions": ed["mentions"],
                "mean_sentiment": ed.get("mean_sentiment", 0.0),
                "stances": ed.get("stances", {}),
                "timestamp": ts,
            }
            f.write(json.dumps(record) + "\n")


def compute_movers(
    current_entities: Dict[str, Dict],
    window_days: int = 30,
    z_threshold: float = 2.0,
) -> List[Dict]:
    """
    Identify entities with significant movement vs historical baseline.

    Args:
        current_entities: {entity: {mentions, mean_sentiment, stances, type}}
        window_days: Rolling window for baseline
        z_threshold: Z-score threshold for flagging

    Returns:
        List of mover dicts, sorted by highest absolute z-score.
        Each: {entity, type, volume_z, sentiment_z, direction, current, baseline}
    """
    history = _load_history()
    cutoff = datetime.now().timestamp() - (window_days * 86400)

    movers = []
    for entity, data in current_entities.items():
        records = history.get(entity, [])
        historical = []
        for r in records:
            try:
                ts = datetime.fromisoformat(r["timestamp"]).timestamp()
                if ts >= cutoff:
                    historical.append(r)
            except (ValueError, KeyError):
                continue

        if len(historical) < 2:
            continue

        # Volume z-score
        hist_mentions = [r["mentions"] for r in historical]
        vol_mean = np.mean(hist_mentions)
        vol_std = np.std(hist_mentions)
        vol_z = (data["mentions"] - vol_mean) / vol_std if vol_std > 0.5 else 0.0

        # Sentiment z-score
        hist_sent = [r.get("mean_sentiment", 0) for r in historical]
        sent_mean = np.mean(hist_sent)
        sent_std = np.std(hist_sent)
        sent_z = (data["mean_sentiment"] - sent_mean) / sent_std if sent_std > 0.01 else 0.0

        max_z = max(abs(vol_z), abs(sent_z))
        if max_z >= z_threshold:
            if sent_z < -z_threshold:
                direction = "worsening"
            elif sent_z > z_threshold:
                direction = "improving"
            elif vol_z > z_threshold:
                direction = "surging"
            elif vol_z < -z_threshold:
                direction = "fading"
            else:
                direction = "shifting"

            movers.append({
                "entity": entity,
                "type": data.get("type", "UNKNOWN"),
                "volume_z": round(float(vol_z), 2),
                "sentiment_z": round(float(sent_z), 2),
                "direction": direction,
                "current_mentions": data["mentions"],
                "current_sentiment": round(data["mean_sentiment"], 3),
                "baseline_mentions": round(float(vol_mean), 1),
                "baseline_sentiment": round(float(sent_mean), 3),
                "history_points": len(historical),
            })

    movers.sort(key=lambda x: max(abs(x["volume_z"]), abs(x["sentiment_z"])), reverse=True)
    return movers


def build_entity_summary(article_records) -> Dict[str, Dict]:
    """
    Build per-entity summary from article records.

    Args:
        article_records: List of ArticleRecord objects

    Returns:
        {entity_name: {mentions, mean_sentiment, stances, type}}
    """
    entity_data = defaultdict(lambda: {"mentions": 0, "sentiments": [], "stances": defaultdict(int), "type": "UNKNOWN"})

    for record in article_records:
        score = record.sentiment.score

        # Count entity mentions
        for ent in record.entities:
            name = ent["text"]
            entity_data[name]["mentions"] += 1
            entity_data[name]["sentiments"].append(score)
            entity_data[name]["type"] = ent.get("type", "UNKNOWN")

        # Count entity stances
        for stance in record.entity_stances:
            name = stance["entity"]
            entity_data[name]["stances"][stance["stance"]] += 1
            if name not in entity_data:
                entity_data[name]["mentions"] += 1
            entity_data[name]["type"] = stance.get("type", entity_data[name]["type"])

    # Compute means
    result = {}
    for entity, data in entity_data.items():
        result[entity] = {
            "mentions": data["mentions"],
            "mean_sentiment": np.mean(data["sentiments"]) if data["sentiments"] else 0.0,
            "stances": dict(data["stances"]),
            "type": data["type"],
        }

    return result
