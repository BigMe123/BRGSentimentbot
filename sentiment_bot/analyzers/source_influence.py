"""
Source influence scoring via lead-time analysis.

For each narrative cluster, identifies which sources published first
(leaders) vs. last (followers). Accumulates lead-time stats across
scans to build source authority rankings.
"""

import json
import logging
from pathlib import Path
from typing import List, Dict
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger(__name__)

STATE_FILE = Path(__file__).parent.parent / "state" / "source_influence.json"


class SourceInfluenceTracker:
    """
    Track which sources break stories first across narrative clusters.

    For each cluster of articles covering the same story, the source
    that published earliest gets a "lead" credit. Accumulates over scans.
    """

    def __init__(self):
        self._stats = self._load()

    def _load(self) -> Dict[str, Dict]:
        """Load accumulated source stats."""
        if STATE_FILE.exists():
            try:
                return json.loads(STATE_FILE.read_text())
            except Exception:
                pass
        return {}

    def _save(self):
        """Save accumulated source stats."""
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(self._stats, indent=2))

    def analyze_narratives(self, article_records, narratives) -> Dict[str, Dict]:
        """
        Analyze source lead-times within narrative clusters.

        Args:
            article_records: List of ArticleRecord objects
            narratives: List of Narrative objects

        Returns:
            {source: {leads, follows, avg_lead_hours, influence_score}}
        """
        by_id = {r.id: r for r in article_records}

        for narrative in narratives:
            records = [by_id[aid] for aid in narrative.article_ids if aid in by_id]
            if len(records) < 2:
                continue

            # Parse publication times and sort
            timed = []
            for r in records:
                try:
                    pub = datetime.fromisoformat(r.published_at.replace("Z", "+00:00"))
                    timed.append((pub, r.source))
                except (ValueError, AttributeError):
                    continue

            if len(timed) < 2:
                continue

            timed.sort(key=lambda x: x[0])
            leader_time, leader_source = timed[0]

            # Credit leader
            if leader_source not in self._stats:
                self._stats[leader_source] = {"leads": 0, "follows": 0, "lead_hours": []}
            self._stats[leader_source]["leads"] += 1

            # Credit followers with their lag
            for pub_time, source in timed[1:]:
                if source not in self._stats:
                    self._stats[source] = {"leads": 0, "follows": 0, "lead_hours": []}
                self._stats[source]["follows"] += 1

                lag_hours = (pub_time - leader_time).total_seconds() / 3600
                self._stats[leader_source]["lead_hours"].append(round(lag_hours, 2))

        self._save()
        return self.get_rankings()

    def get_rankings(self, min_stories: int = 2) -> Dict[str, Dict]:
        """
        Get source influence rankings.

        Returns:
            {source: {leads, follows, total, lead_ratio, avg_lead_hours, influence_score}}
        """
        rankings = {}
        for source, stats in self._stats.items():
            total = stats["leads"] + stats["follows"]
            if total < min_stories:
                continue

            lead_hours = stats.get("lead_hours", [])
            avg_lead = sum(lead_hours) / len(lead_hours) if lead_hours else 0

            lead_ratio = stats["leads"] / total if total > 0 else 0
            # Influence: high lead ratio + consistent early publishing
            influence = lead_ratio * 0.7 + min(1.0, total / 20) * 0.3

            rankings[source] = {
                "leads": stats["leads"],
                "follows": stats["follows"],
                "total": total,
                "lead_ratio": round(lead_ratio, 3),
                "avg_lead_hours": round(avg_lead, 1),
                "influence_score": round(influence, 3),
            }

        return dict(sorted(rankings.items(), key=lambda x: -x[1]["influence_score"]))
