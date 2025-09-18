"""
Real-time performance monitoring dashboard using Rich for terminal UI.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.text import Text
from rich.align import Align
import time

from .performance_monitor import PerformanceMonitor
from .rss_monitor import RSSMonitor


class PerformanceDashboard:
    """
    Real-time terminal dashboard for monitoring system performance.

    Features:
    - Live updating metrics
    - RSS feed health status
    - Model performance tracking
    - Alert notifications
    - Resource utilization
    """

    def __init__(self, performance_monitor: PerformanceMonitor,
                 rss_monitor: RSSMonitor,
                 refresh_interval: int = 5):
        self.performance_monitor = performance_monitor
        self.rss_monitor = rss_monitor
        self.refresh_interval = refresh_interval
        self.console = Console()
        self.start_time = datetime.now()

    def create_header(self) -> Panel:
        """Create dashboard header with title and uptime."""
        uptime = datetime.now() - self.start_time
        hours = int(uptime.total_seconds() // 3600)
        minutes = int((uptime.total_seconds() % 3600) // 60)
        seconds = int(uptime.total_seconds() % 60)

        header_text = Text()
        header_text.append("BSG Bot Performance Dashboard\n", style="bold cyan")
        header_text.append(f"Uptime: {hours:02d}:{minutes:02d}:{seconds:02d}", style="green")
        header_text.append(f" | Last Update: {datetime.now().strftime('%H:%M:%S')}", style="yellow")

        return Panel(Align.center(header_text), box_double=True)

    def create_model_metrics_table(self) -> Table:
        """Create table showing model performance metrics."""
        metrics = self.performance_monitor.get_current_metrics()

        table = Table(title="📊 Model Performance", show_header=True, header_style="bold magenta")
        table.add_column("Model", style="cyan", width=12)
        table.add_column("Country", style="green", width=15)
        table.add_column("MAPE", justify="right", style="yellow")
        table.add_column("RMSE", justify="right", style="yellow")
        table.add_column("Dir. Acc", justify="right", style="magenta")
        table.add_column("Coverage", justify="right", style="blue")
        table.add_column("Samples", justify="right", style="white")

        for model_type, countries in metrics.items():
            for country, perf in countries.items():
                # Color code MAPE based on threshold
                mape_style = "green" if perf.mape < 5 else "yellow" if perf.mape < 10 else "red"

                table.add_row(
                    model_type.upper(),
                    country.replace("_", " ").title(),
                    Text(f"{perf.mape:.2f}%", style=mape_style),
                    f"{perf.rmse:.3f}",
                    f"{perf.directional_accuracy:.1%}",
                    f"{perf.confidence_coverage:.1%}",
                    str(perf.sample_size)
                )

        return table

    async def create_feed_health_panel(self) -> Panel:
        """Create panel showing RSS feed health status."""
        # Get feed health from monitor
        feed_status = await self.rss_monitor.get_all_feed_status()

        # Count by status
        healthy = sum(1 for s in feed_status.values() if s.status == "healthy")
        degraded = sum(1 for s in feed_status.values() if s.status == "degraded")
        error = sum(1 for s in feed_status.values() if s.status == "error")
        quarantined = sum(1 for s in feed_status.values() if s.status == "quarantined")

        # Create status text
        status_text = Text()
        status_text.append(f"✅ Healthy: {healthy}\n", style="green")
        status_text.append(f"⚠️  Degraded: {degraded}\n", style="yellow")
        status_text.append(f"❌ Error: {error}\n", style="red")
        status_text.append(f"🔒 Quarantined: {quarantined}", style="dim red")

        # Add feed details
        if degraded > 0 or error > 0:
            status_text.append("\n\n", style="")
            status_text.append("Problem Feeds:\n", style="bold")

            problem_feeds = [(url, s) for url, s in feed_status.items()
                           if s.status in ["degraded", "error"]][:5]

            for url, status in problem_feeds:
                domain = url.split('/')[2] if '/' in url else url
                symbol = "⚠️" if status.status == "degraded" else "❌"
                status_text.append(f"{symbol} {domain[:30]}...\n", style="dim")

        return Panel(status_text, title="📡 RSS Feed Health", border_style="blue")

    def create_alerts_panel(self) -> Panel:
        """Create panel showing recent alerts."""
        alerts = self.performance_monitor.check_alerts(hours_back=1)

        if not alerts:
            content = Text("✅ No active alerts", style="green")
        else:
            content = Text()
            for alert in alerts[:5]:  # Show latest 5 alerts
                # Choose icon based on severity
                icon = "🔴" if alert["severity"] == "critical" else "🟡" if alert["severity"] == "warning" else "🔵"

                # Format time
                alert_time = datetime.fromisoformat(alert["timestamp"])
                time_ago = datetime.now() - alert_time
                if time_ago.total_seconds() < 60:
                    time_str = f"{int(time_ago.total_seconds())}s ago"
                elif time_ago.total_seconds() < 3600:
                    time_str = f"{int(time_ago.total_seconds() / 60)}m ago"
                else:
                    time_str = f"{int(time_ago.total_seconds() / 3600)}h ago"

                content.append(f"{icon} [{time_str}] ", style="dim")
                content.append(f"{alert['message']}\n", style="white")

        return Panel(content, title="⚠️ Alerts", border_style="red")

    def create_predictions_chart(self) -> Panel:
        """Create a simple ASCII chart of recent predictions."""
        # Get recent predictions from database
        import sqlite3
        conn = sqlite3.connect(self.performance_monitor.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT model_type, prediction, actual, timestamp
            FROM predictions
            WHERE actual IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT 20
        """)

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return Panel("No recent predictions with actuals", title="📈 Recent Predictions")

        # Create simple ASCII chart
        chart_text = Text()

        for row in rows:
            model, pred, actual, ts = row
            timestamp = datetime.fromisoformat(ts)

            # Create bar visualization
            pred_bar_len = min(int(abs(pred) * 10), 30)
            actual_bar_len = min(int(abs(actual) * 10), 30)

            chart_text.append(f"{timestamp.strftime('%H:%M')} ", style="dim")
            chart_text.append(f"{model[:3]} ", style="cyan")

            # Prediction bar
            chart_text.append("P:", style="yellow")
            chart_text.append("█" * pred_bar_len, style="yellow")
            chart_text.append(f" {pred:.2f}\n", style="yellow")

            # Actual bar
            chart_text.append("       A:", style="green")
            chart_text.append("█" * actual_bar_len, style="green")
            chart_text.append(f" {actual:.2f}\n", style="green")

        return Panel(chart_text, title="📈 Recent Predictions vs Actuals")

    def create_system_stats(self) -> Panel:
        """Create panel showing system statistics."""
        import psutil

        # Get system stats
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        stats_text = Text()
        stats_text.append("System Resources\n", style="bold")
        stats_text.append("-" * 20 + "\n", style="dim")

        # CPU with color coding
        cpu_style = "green" if cpu_percent < 50 else "yellow" if cpu_percent < 80 else "red"
        stats_text.append(f"CPU:    {cpu_percent:5.1f}% ", style=cpu_style)
        stats_text.append("█" * int(cpu_percent / 5), style=cpu_style)
        stats_text.append("\n")

        # Memory
        mem_style = "green" if memory.percent < 50 else "yellow" if memory.percent < 80 else "red"
        stats_text.append(f"Memory: {memory.percent:5.1f}% ", style=mem_style)
        stats_text.append("█" * int(memory.percent / 5), style=mem_style)
        stats_text.append(f"\n        {memory.used / 1024**3:.1f}GB / {memory.total / 1024**3:.1f}GB\n", style="dim")

        # Disk
        disk_style = "green" if disk.percent < 50 else "yellow" if disk.percent < 80 else "red"
        stats_text.append(f"Disk:   {disk.percent:5.1f}% ", style=disk_style)
        stats_text.append("█" * int(disk.percent / 5), style=disk_style)

        return Panel(stats_text, title="💻 System Stats", border_style="cyan")

    async def create_layout(self) -> Layout:
        """Create the complete dashboard layout."""
        layout = Layout()

        # Create main sections
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3)
        )

        # Split body into left and right
        layout["body"].split_row(
            Layout(name="left", ratio=2),
            Layout(name="right", ratio=1)
        )

        # Split left into upper and lower
        layout["left"].split_column(
            Layout(name="metrics", ratio=1),
            Layout(name="predictions", ratio=1)
        )

        # Split right into sections
        layout["right"].split_column(
            Layout(name="feeds", ratio=1),
            Layout(name="alerts", ratio=1),
            Layout(name="system", ratio=1)
        )

        # Populate sections
        layout["header"].update(self.create_header())
        layout["metrics"].update(self.create_model_metrics_table())
        layout["predictions"].update(self.create_predictions_chart())
        layout["feeds"].update(await self.create_feed_health_panel())
        layout["alerts"].update(self.create_alerts_panel())
        layout["system"].update(self.create_system_stats())

        # Footer with commands
        footer_text = Text()
        footer_text.append("Commands: ", style="bold")
        footer_text.append("[Q] Quit | [R] Refresh | [C] Clear Alerts | [E] Export Report", style="cyan")
        layout["footer"].update(Panel(Align.center(footer_text), style="dim"))

        return layout

    async def run(self):
        """Run the dashboard with live updates."""
        with Live(await self.create_layout(), refresh_per_second=1, console=self.console) as live:
            try:
                while True:
                    await asyncio.sleep(self.refresh_interval)
                    live.update(await self.create_layout())
            except KeyboardInterrupt:
                pass

    def export_report(self, output_path: str):
        """Export current dashboard state to a report file."""
        report = self.performance_monitor.generate_performance_report(output_path)
        self.console.print(f"[green]Report exported to: {output_path}[/green]")
        return report


async def run_dashboard(performance_monitor: Optional[PerformanceMonitor] = None,
                       rss_monitor: Optional[RSSMonitor] = None):
    """Convenience function to run the dashboard."""
    if not performance_monitor:
        performance_monitor = PerformanceMonitor()
    if not rss_monitor:
        rss_monitor = RSSMonitor()

    dashboard = PerformanceDashboard(performance_monitor, rss_monitor)
    await dashboard.run()


if __name__ == "__main__":
    # Run standalone dashboard
    asyncio.run(run_dashboard())