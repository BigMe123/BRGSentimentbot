"""
Output writer for institutional-style reporting.
"""

import json
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

from .output_models import (
    ArticleRecord,
    RunSummary,
    EntityCount,
    SourceCount,
    AnalysisBlock,
    DiversityBlock,
)


class OutputWriter:
    """Handles writing structured outputs to disk."""

    def __init__(self, output_dir: str = "./output", run_id: str = ""):
        """
        Initialize output writer.

        Args:
            output_dir: Directory for output files
            run_id: Unique run identifier
        """
        self.dir = Path(output_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id

    def write_articles_jsonl(self, records: List[ArticleRecord]) -> str:
        """
        Write article records to JSONL file.

        Args:
            records: List of article records

        Returns:
            Path to written file
        """
        filepath = self.dir / f"articles_{self.run_id}.jsonl"

        with filepath.open("w", encoding="utf-8") as f:
            for record in records:
                # Write each record as a single JSON line
                f.write(record.model_dump_json(exclude_none=True) + "\n")

        return str(filepath)

    def write_run_summary_json(self, summary: RunSummary) -> str:
        """
        Write run summary to JSON file.

        Args:
            summary: Run summary object

        Returns:
            Path to written file
        """
        filepath = self.dir / f"run_summary_{self.run_id}.json"

        # Write with pretty formatting
        filepath.write_text(
            summary.model_dump_json(indent=2, exclude_none=True), encoding="utf-8"
        )

        return str(filepath)

    def write_dashboard_txt(self, summary: RunSummary, highlights: List[str]) -> str:
        """
        Write human-readable dashboard summary.

        Args:
            summary: Run summary object
            highlights: Notable article highlights

        Returns:
            Path to written file
        """
        filepath = self.dir / f"dashboard_run_summary_{self.run_id}.txt"

        text = self._build_dashboard_text(summary, highlights)
        filepath.write_text(text, encoding="utf-8")

        return str(filepath)

    def _build_dashboard_text(self, summary: RunSummary, highlights: List[str]) -> str:
        """Build formatted dashboard text."""

        lines = []

        # Header line
        header = (
            f"RUN {summary.run_id} | "
            f"{summary.config.region or 'Global'} · {summary.config.topic or 'General'} | "
            f"{summary.collection.relevant_count} relevant | "
            f"Sentiment {summary.analysis.sentiment_total:+d} "
            f"(avg {summary.analysis.avg_sentiment:.2f}) | "
            f"Volatility {summary.analysis.volatility_index:.2f}"
        )
        lines.append(header)

        # Signals line
        if summary.analysis.top_triggers:
            signals = " · ".join(summary.analysis.top_triggers[:5])
            lines.append(f"Signals: {signals}")

        # Entities line
        if summary.analysis.top_entities:
            entities = ", ".join(
                f"{e.text}({e.count})" for e in summary.analysis.top_entities[:5]
            )
            lines.append(f"Entities: {entities}")

        # Sentiment breakdown
        total = sum(summary.analysis.breakdown.values())
        if total > 0:
            pos_pct = summary.analysis.breakdown.get("pos", 0) / total * 100
            neg_pct = summary.analysis.breakdown.get("neg", 0) / total * 100
            neu_pct = summary.analysis.breakdown.get("neu", 0) / total * 100
            lines.append(
                f"Skews: Pos: {pos_pct:.0f}%, Neg: {neg_pct:.0f}%, Neu: {neu_pct:.0f}%"
            )

        # Notables section
        if highlights:
            lines.append("Notables:")
            for highlight in highlights[:5]:
                lines.append(f" - {highlight}")

        # Actions section
        lines.append("Actions:")

        # Generate actions based on analysis
        actions = self._generate_actions(summary)
        for action in actions[:3]:
            lines.append(f" - {action}")

        return "\n".join(lines)

    def _generate_actions(self, summary: RunSummary) -> List[str]:
        """Generate recommended actions based on analysis."""

        actions = []

        # Risk level action
        if summary.analysis.volatility_index > 0.7:
            actions.append(
                f"Raise {summary.config.region or 'global'} {summary.config.topic or 'macro'} risk to \"elevated\""
            )
        elif summary.analysis.volatility_index > 0.5:
            actions.append(
                f"Monitor {summary.config.region or 'global'} volatility closely"
            )

        # Sentiment action
        if summary.analysis.avg_sentiment < -0.3:
            actions.append(
                f"Review negative sentiment drivers in {summary.config.topic or 'sector'}"
            )
        elif summary.analysis.avg_sentiment > 0.3:
            actions.append(
                f"Consider positive momentum in {summary.config.topic or 'sector'}"
            )

        # Coverage action
        if summary.diversity.sources < 10:
            actions.append(
                f"Expand source coverage for {summary.config.region or 'region'}"
            )

        # Freshness action
        freshness_rate = summary.collection.fresh_count / max(
            summary.collection.articles_raw, 1
        )
        if freshness_rate < 0.5:
            actions.append("Increase feed refresh frequency or add real-time sources")

        return actions if actions else ["Continue standard monitoring"]

    def write_csv(self, records: List[ArticleRecord]) -> str:
        """
        Write article records to CSV file.

        Args:
            records: List of article records

        Returns:
            Path to written file
        """
        import csv

        filepath = self.dir / f"articles_{self.run_id}.csv"

        if not records:
            return str(filepath)

        # Define CSV columns
        fieldnames = [
            "run_id",
            "id",
            "title",
            "url",
            "published_at",
            "source",
            "region",
            "topic",
            "language",
            "relevance",
            "sentiment_label",
            "sentiment_score",
            "volatility",
            "summary",
        ]

        with filepath.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for record in records:
                row = {
                    "run_id": record.run_id,
                    "id": record.id,
                    "title": record.title,
                    "url": record.url,
                    "published_at": record.published_at,
                    "source": record.source,
                    "region": record.region,
                    "topic": record.topic,
                    "language": record.language,
                    "relevance": record.relevance,
                    "sentiment_label": record.sentiment.label,
                    "sentiment_score": record.sentiment.score,
                    "volatility": record.signals.volatility if record.signals else 0,
                    "summary": record.summary[:200],  # Truncate for CSV
                }
                writer.writerow(row)

        return str(filepath)
