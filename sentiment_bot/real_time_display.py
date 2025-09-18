#!/usr/bin/env python3
"""
Real-Time Step-by-Step Analysis Display
======================================

Provides live, interactive feedback during sentiment analysis processes.
Shows progress through each stage with detailed status updates and metrics.
"""

import time
import asyncio
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from contextlib import contextmanager
import threading
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn, MofNCompleteColumn
from rich.layout import Layout
from rich.align import Align
from rich.text import Text
from rich.columns import Columns
import json

class AnalysisStage(Enum):
    """Analysis stages for tracking progress."""
    INITIALIZATION = "initialization"
    SOURCE_SELECTION = "source_selection"
    ARTICLE_FETCHING = "article_fetching"
    CONTENT_FILTERING = "content_filtering"
    SENTIMENT_ANALYSIS = "sentiment_analysis"
    ENTITY_EXTRACTION = "entity_extraction"
    TOPIC_CLASSIFICATION = "topic_classification"
    AGGREGATION = "aggregation"
    REPORT_GENERATION = "report_generation"
    COMPLETE = "complete"

@dataclass
class StageProgress:
    """Progress information for a single stage."""
    stage: AnalysisStage
    status: str = "pending"  # pending, running, completed, failed
    progress: float = 0.0  # 0.0 to 1.0
    total_items: int = 0
    completed_items: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    details: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    @property
    def duration(self) -> Optional[timedelta]:
        """Get stage duration if completed."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        elif self.start_time:
            return datetime.now() - self.start_time
        return None

    @property
    def eta(self) -> Optional[timedelta]:
        """Estimate time remaining for stage."""
        if self.status == "running" and self.progress > 0 and self.start_time:
            elapsed = datetime.now() - self.start_time
            if self.progress > 0:
                total_estimated = elapsed / self.progress
                return total_estimated - elapsed
        return None

class RealTimeAnalysisDisplay:
    """
    Real-time display manager for sentiment analysis.
    Provides live updates and interactive feedback during processing.
    """

    def __init__(self, console: Optional[Console] = None):
        """Initialize display manager."""
        self.console = console or Console()
        self.stages = {stage: StageProgress(stage) for stage in AnalysisStage}
        self.current_stage = AnalysisStage.INITIALIZATION
        self.start_time = datetime.now()
        self.live_display = None
        self.update_interval = 0.5  # seconds
        self.metrics = {
            "sources_selected": 0,
            "articles_fetched": 0,
            "articles_processed": 0,
            "sentiment_scores": [],
            "entities_found": 0,
            "topics_identified": 0,
            "processing_rate": 0.0,
            "memory_usage": 0,
            "errors": 0
        }
        self._stop_event = threading.Event()

    def start_analysis(self, run_id: str, config: Dict[str, Any]) -> None:
        """Start the analysis display."""
        self.run_id = run_id
        self.config = config
        self.start_time = datetime.now()

        # Initialize layout
        self.layout = self._create_layout()

        # Start live display
        self.live_display = Live(
            self.layout,
            console=self.console,
            refresh_per_second=2,
            auto_refresh=True
        )
        self.live_display.start()

        # Start first stage
        self._start_stage(AnalysisStage.INITIALIZATION)

    def _create_layout(self) -> Layout:
        """Create the main display layout."""
        layout = Layout()

        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=5)
        )

        layout["main"].split_row(
            Layout(name="progress", ratio=2),
            Layout(name="metrics", ratio=1)
        )

        return layout

    def _update_header(self) -> Panel:
        """Create header panel with run information."""
        elapsed = datetime.now() - self.start_time

        header_text = Text()
        header_text.append("🤖 BSG Sentiment Analysis ", style="bold cyan")
        header_text.append(f"[Run: {self.run_id}]", style="dim")
        header_text.append(f" | Elapsed: {str(elapsed).split('.')[0]}", style="green")

        # Show current stage
        current_stage_progress = self.stages[self.current_stage]
        if current_stage_progress.status == "running":
            if current_stage_progress.eta:
                eta_str = str(current_stage_progress.eta).split('.')[0]
                header_text.append(f" | ETA: {eta_str}", style="yellow")

        return Panel(
            Align.center(header_text),
            border_style="cyan",
            padding=(0, 1)
        )

    def _update_progress(self) -> Panel:
        """Create progress panel showing stage progression."""
        table = Table(show_header=True, header_style="bold cyan", show_lines=True)
        table.add_column("Stage", style="cyan", width=20)
        table.add_column("Status", width=12)
        table.add_column("Progress", width=20)
        table.add_column("Items", width=12)
        table.add_column("Duration", width=12)
        table.add_column("Details", width=30)

        for stage_enum in AnalysisStage:
            stage = self.stages[stage_enum]

            # Status styling
            if stage.status == "completed":
                status_text = Text("✅ Complete", style="green")
            elif stage.status == "running":
                status_text = Text("🔄 Running", style="yellow")
            elif stage.status == "failed":
                status_text = Text("❌ Failed", style="red")
            else:
                status_text = Text("⏳ Pending", style="dim")

            # Progress bar
            if stage.total_items > 0:
                progress_text = f"{stage.completed_items}/{stage.total_items}"
                progress_bar = "█" * int(stage.progress * 10) + "░" * (10 - int(stage.progress * 10))
                progress_display = f"{progress_bar} {stage.progress:.1%}"
            else:
                progress_text = f"{stage.progress:.1%}"
                progress_display = f"{stage.progress:.1%}"

            # Duration
            duration_text = ""
            if stage.duration:
                duration_text = str(stage.duration).split('.')[0]

            # Details
            details_text = ""
            if stage.details:
                key_details = []
                for key, value in list(stage.details.items())[:2]:  # Show first 2 details
                    key_details.append(f"{key}: {value}")
                details_text = " | ".join(key_details)

            table.add_row(
                stage_enum.value.replace("_", " ").title(),
                status_text,
                progress_display,
                progress_text,
                duration_text,
                details_text
            )

        return Panel(table, title="📊 Analysis Progress", border_style="blue")

    def _update_metrics(self) -> Panel:
        """Create metrics panel showing real-time statistics."""
        metrics_table = Table(show_header=False, show_lines=False, pad_edge=False)
        metrics_table.add_column("Metric", style="cyan", width=20)
        metrics_table.add_column("Value", style="white", width=15)

        # Core metrics
        metrics_table.add_row("Sources Selected", str(self.metrics["sources_selected"]))
        metrics_table.add_row("Articles Fetched", str(self.metrics["articles_fetched"]))
        metrics_table.add_row("Articles Processed", str(self.metrics["articles_processed"]))
        metrics_table.add_row("Entities Found", str(self.metrics["entities_found"]))
        metrics_table.add_row("Topics Identified", str(self.metrics["topics_identified"]))

        # Performance metrics
        if self.metrics["processing_rate"] > 0:
            metrics_table.add_row("Processing Rate", f"{self.metrics['processing_rate']:.1f}/sec")

        # Sentiment summary
        if self.metrics["sentiment_scores"]:
            avg_sentiment = sum(self.metrics["sentiment_scores"]) / len(self.metrics["sentiment_scores"])
            sentiment_emoji = "😊" if avg_sentiment > 0.1 else "😐" if avg_sentiment > -0.1 else "😞"
            metrics_table.add_row("Avg Sentiment", f"{sentiment_emoji} {avg_sentiment:.2f}")

        # Errors
        if self.metrics["errors"] > 0:
            metrics_table.add_row("Errors", f"⚠️ {self.metrics['errors']}")

        return Panel(metrics_table, title="📈 Live Metrics", border_style="green")

    def _update_footer(self) -> Panel:
        """Create footer with current activity and tips."""
        current_stage_progress = self.stages[self.current_stage]

        footer_text = Text()

        # Current activity
        if current_stage_progress.status == "running":
            activity = f"🔄 {self.current_stage.value.replace('_', ' ').title()}"
            if current_stage_progress.details.get("current_activity"):
                activity += f": {current_stage_progress.details['current_activity']}"
            footer_text.append(activity, style="yellow")
        else:
            footer_text.append("⏸️ Waiting...", style="dim")

        # Tips
        tips = [
            "💡 Press Ctrl+C to stop analysis",
            "📊 Metrics update in real-time",
            "🔍 Detailed logs saved to output directory"
        ]

        footer_text.append(" | ", style="dim")
        footer_text.append(" | ".join(tips), style="dim cyan")

        return Panel(footer_text, border_style="dim")

    def update_display(self) -> None:
        """Update the live display with current state."""
        if self.live_display:
            self.layout["header"].update(self._update_header())
            self.layout["progress"].update(self._update_progress())
            self.layout["metrics"].update(self._update_metrics())
            self.layout["footer"].update(self._update_footer())

    def _start_stage(self, stage: AnalysisStage) -> None:
        """Start a new analysis stage."""
        self.current_stage = stage
        stage_progress = self.stages[stage]
        stage_progress.status = "running"
        stage_progress.start_time = datetime.now()
        stage_progress.progress = 0.0
        self.update_display()

    def update_stage_progress(
        self,
        stage: AnalysisStage,
        progress: float = None,
        completed_items: int = None,
        total_items: int = None,
        details: Dict[str, Any] = None,
        activity: str = None
    ) -> None:
        """Update progress for a specific stage."""
        stage_progress = self.stages[stage]

        if progress is not None:
            stage_progress.progress = min(1.0, max(0.0, progress))

        if completed_items is not None:
            stage_progress.completed_items = completed_items

        if total_items is not None:
            stage_progress.total_items = total_items
            # Auto-calculate progress if items are set
            if stage_progress.total_items > 0:
                stage_progress.progress = stage_progress.completed_items / stage_progress.total_items

        if details:
            stage_progress.details.update(details)

        if activity:
            stage_progress.details["current_activity"] = activity

        self.update_display()

    def complete_stage(self, stage: AnalysisStage, success: bool = True) -> None:
        """Mark a stage as completed."""
        stage_progress = self.stages[stage]
        stage_progress.status = "completed" if success else "failed"
        stage_progress.end_time = datetime.now()
        stage_progress.progress = 1.0

        # Auto-advance to next stage
        stage_list = list(AnalysisStage)
        current_index = stage_list.index(stage)
        if current_index + 1 < len(stage_list):
            next_stage = stage_list[current_index + 1]
            self._start_stage(next_stage)

        self.update_display()

    def add_error(self, stage: AnalysisStage, error: str) -> None:
        """Add an error to a stage."""
        self.stages[stage].errors.append(error)
        self.metrics["errors"] += 1
        self.update_display()

    def update_metrics(self, **metrics) -> None:
        """Update live metrics."""
        for key, value in metrics.items():
            if key in self.metrics:
                if key == "sentiment_scores" and isinstance(value, (int, float)):
                    self.metrics[key].append(value)
                else:
                    self.metrics[key] = value
        self.update_display()

    def finish_analysis(self, success: bool = True, summary: Dict[str, Any] = None) -> None:
        """Finish the analysis and show final results."""
        if success:
            self.complete_stage(AnalysisStage.COMPLETE)

        # Show final summary
        if summary:
            self._show_final_summary(summary)

        if self.live_display:
            self.live_display.stop()

    def _show_final_summary(self, summary: Dict[str, Any]) -> None:
        """Show final analysis summary."""
        total_duration = datetime.now() - self.start_time

        summary_text = Text()
        summary_text.append("🎉 Analysis Complete!\n\n", style="bold green")
        summary_text.append(f"⏱️ Total Duration: {str(total_duration).split('.')[0]}\n", style="cyan")
        summary_text.append(f"📊 Articles Processed: {summary.get('total_articles', 0)}\n", style="white")
        summary_text.append(f"🎯 Sentiment Score: {summary.get('avg_sentiment', 0):.2f}\n", style="white")
        summary_text.append(f"🌍 Countries Covered: {summary.get('countries_count', 0)}\n", style="white")
        summary_text.append(f"📁 Output: {summary.get('output_file', 'N/A')}\n", style="dim")

        panel = Panel(
            summary_text,
            title="📋 Analysis Summary",
            border_style="green",
            padding=(1, 2)
        )

        self.console.print("\n")
        self.console.print(panel)

    @contextmanager
    def stage_context(self, stage: AnalysisStage):
        """Context manager for automatic stage management."""
        self._start_stage(stage)
        try:
            yield self
            self.complete_stage(stage, success=True)
        except Exception as e:
            self.add_error(stage, str(e))
            self.complete_stage(stage, success=False)
            raise

    def stop(self):
        """Stop the display."""
        if self.live_display:
            self.live_display.stop()

# Usage example and integration
def create_display_manager() -> RealTimeAnalysisDisplay:
    """Factory function to create display manager."""
    return RealTimeAnalysisDisplay()

# Example usage
if __name__ == "__main__":
    import random

    async def simulate_analysis():
        """Simulate an analysis process for testing."""
        display = RealTimeAnalysisDisplay()

        # Start analysis
        display.start_analysis("test_run_123", {"region": "europe", "topic": "economy"})

        # Simulate initialization
        with display.stage_context(AnalysisStage.INITIALIZATION):
            await asyncio.sleep(1)
            display.update_stage_progress(
                AnalysisStage.INITIALIZATION,
                activity="Loading models and configuration"
            )
            await asyncio.sleep(1)

        # Simulate source selection
        with display.stage_context(AnalysisStage.SOURCE_SELECTION):
            for i in range(1, 26):
                display.update_stage_progress(
                    AnalysisStage.SOURCE_SELECTION,
                    completed_items=i,
                    total_items=25,
                    activity=f"Evaluating source {i}/25"
                )
                await asyncio.sleep(0.1)
            display.update_metrics(sources_selected=25)

        # Simulate article fetching
        with display.stage_context(AnalysisStage.ARTICLE_FETCHING):
            for i in range(1, 101):
                display.update_stage_progress(
                    AnalysisStage.ARTICLE_FETCHING,
                    completed_items=i,
                    total_items=100,
                    activity=f"Fetching article {i}/100"
                )
                display.update_metrics(articles_fetched=i)
                await asyncio.sleep(0.05)

        # Simulate sentiment analysis
        with display.stage_context(AnalysisStage.SENTIMENT_ANALYSIS):
            for i in range(1, 101):
                sentiment_score = random.uniform(-1, 1)
                display.update_stage_progress(
                    AnalysisStage.SENTIMENT_ANALYSIS,
                    completed_items=i,
                    total_items=100,
                    activity=f"Analyzing sentiment {i}/100"
                )
                display.update_metrics(
                    articles_processed=i,
                    sentiment_scores=sentiment_score,
                    processing_rate=i/5.0  # 5 seconds elapsed
                )
                await asyncio.sleep(0.05)

        # Finish
        display.finish_analysis(True, {
            "total_articles": 100,
            "avg_sentiment": 0.15,
            "countries_count": 3,
            "output_file": "output/test_run_123.json"
        })

    if __name__ == "__main__":
        asyncio.run(simulate_analysis())