#!/usr/bin/env python3
"""
Risk Intelligence Interactive Dashboard
PyQt6-based GUI with real-time charts and interactive controls
"""

import sys
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict
import json

try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QComboBox, QTableWidget, QTableWidgetItem,
        QTabWidget, QTextEdit, QGroupBox, QGridLayout, QSplitter,
        QProgressBar, QCheckBox, QSpinBox
    )
    from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread
    from PyQt6.QtGui import QPixmap, QFont, QColor
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False
    print("PyQt6 not available. Install with: pip install PyQt6")

try:
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("Matplotlib not available. Install with: pip install matplotlib")

from .database import get_risk_db
from .agents import run_agent_job, AgentJob


class SignalWorker(QThread):
    """Background worker for fetching signals"""
    signals_updated = pyqtSignal(list)

    def __init__(self, db):
        super().__init__()
        self.db = db
        self.running = True

    def run(self):
        """Fetch signals periodically"""
        while self.running:
            signals = self.db.get_latest_signals(limit=100)
            self.signals_updated.emit(signals)
            self.msleep(5000)  # Update every 5 seconds

    def stop(self):
        self.running = False


class ChartWidget(FigureCanvasQTAgg):
    """Matplotlib chart widget"""

    def __init__(self, parent=None, width=5, height=4, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = self.fig.add_subplot(111)
        super().__init__(self.fig)


class RiskDashboard(QMainWindow):
    """Main Risk Intelligence Dashboard"""

    def __init__(self):
        super().__init__()
        self.db = get_risk_db()
        self.signals = []
        self.initUI()
        self.start_workers()

    def initUI(self):
        """Initialize UI components"""
        self.setWindowTitle("BRG Risk Intelligence Dashboard")
        self.setGeometry(100, 100, 1600, 1000)

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        # Header with logo placeholder
        header = self.create_header()
        main_layout.addWidget(header)

        # Tab widget for different views
        tabs = QTabWidget()
        tabs.addTab(self.create_overview_tab(), "Overview")
        tabs.addTab(self.create_signals_tab(), "Live Signals")
        tabs.addTab(self.create_agents_tab(), "Agent Control")
        tabs.addTab(self.create_analytics_tab(), "Analytics")
        main_layout.addWidget(tabs)

        # Status bar
        self.statusBar().showMessage("Connected to Risk Intelligence System")

    def create_header(self):
        """Create header with logo and stats"""
        header = QGroupBox()
        layout = QHBoxLayout()

        # Logo placeholder
        logo_label = QLabel("🔷 BRG")
        logo_label.setFont(QFont("Arial", 24, QFont.Weight.Bold))
        logo_label.setStyleSheet("color: #0066cc;")
        layout.addWidget(logo_label)

        # Title
        title_label = QLabel("Risk Intelligence & Agentic System")
        title_label.setFont(QFont("Arial", 18))
        layout.addWidget(title_label)

        layout.addStretch()

        # Live stats
        self.stats_label = QLabel("Loading...")
        self.stats_label.setFont(QFont("Arial", 10))
        layout.addWidget(self.stats_label)

        # Refresh button
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(self.refresh_all)
        layout.addWidget(refresh_btn)

        header.setLayout(layout)
        return header

    def create_overview_tab(self):
        """Create overview tab with charts"""
        tab = QWidget()
        layout = QVBoxLayout()

        # Metrics row
        metrics_layout = QHBoxLayout()

        self.total_signals_label = QLabel("Total Signals: 0")
        self.total_signals_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        metrics_layout.addWidget(self.total_signals_label)

        self.high_risk_label = QLabel("High Risk: 0")
        self.high_risk_label.setStyleSheet("font-size: 16px; font-weight: bold; color: red;")
        metrics_layout.addWidget(self.high_risk_label)

        self.avg_score_label = QLabel("Avg Score: 0.0")
        self.avg_score_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        metrics_layout.addWidget(self.avg_score_label)

        self.last_24h_label = QLabel("Last 24h: 0")
        self.last_24h_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        metrics_layout.addWidget(self.last_24h_label)

        layout.addLayout(metrics_layout)

        # Charts
        if MATPLOTLIB_AVAILABLE:
            charts_splitter = QSplitter(Qt.Orientation.Horizontal)

            # Risk score distribution chart
            self.risk_chart = ChartWidget(self, width=5, height=4, dpi=100)
            charts_splitter.addWidget(self.risk_chart)

            # Category breakdown chart
            self.category_chart = ChartWidget(self, width=5, height=4, dpi=100)
            charts_splitter.addWidget(self.category_chart)

            layout.addWidget(charts_splitter)
        else:
            layout.addWidget(QLabel("Charts unavailable (install matplotlib)"))

        # Recent high-risk signals
        recent_group = QGroupBox("Recent High-Risk Signals")
        recent_layout = QVBoxLayout()
        self.recent_signals_text = QTextEdit()
        self.recent_signals_text.setReadOnly(True)
        recent_layout.addWidget(self.recent_signals_text)
        recent_group.setLayout(recent_layout)
        layout.addWidget(recent_group)

        tab.setLayout(layout)
        return tab

    def create_signals_tab(self):
        """Create live signals feed tab"""
        tab = QWidget()
        layout = QVBoxLayout()

        # Filters
        filters_layout = QHBoxLayout()

        filters_layout.addWidget(QLabel("Category:"))
        self.category_filter = QComboBox()
        self.category_filter.addItems([
            "all", "macro", "regulatory", "supply_chain",
            "brand", "market", "geopolitical", "energy", "tech"
        ])
        self.category_filter.currentTextChanged.connect(self.filter_signals)
        filters_layout.addWidget(self.category_filter)

        filters_layout.addWidget(QLabel("Min Risk Score:"))
        self.risk_filter = QSpinBox()
        self.risk_filter.setRange(0, 100)
        self.risk_filter.setValue(0)
        self.risk_filter.setSingleStep(10)
        self.risk_filter.valueChanged.connect(self.filter_signals)
        filters_layout.addWidget(self.risk_filter)

        filters_layout.addStretch()
        layout.addLayout(filters_layout)

        # Signals table
        self.signals_table = QTableWidget()
        self.signals_table.setColumnCount(7)
        self.signals_table.setHorizontalHeaderLabels([
            "Time", "Category", "Entity", "Title", "Risk Score", "Impact", "Source"
        ])
        self.signals_table.setColumnWidth(3, 400)
        layout.addWidget(self.signals_table)

        # Signal detail
        detail_group = QGroupBox("Signal Detail")
        detail_layout = QVBoxLayout()
        self.signal_detail_text = QTextEdit()
        self.signal_detail_text.setReadOnly(True)
        detail_layout.addWidget(self.signal_detail_text)
        detail_group.setLayout(detail_layout)
        layout.addWidget(detail_group)

        # Connect table selection
        self.signals_table.itemSelectionChanged.connect(self.show_signal_detail)

        tab.setLayout(layout)
        return tab

    def create_agents_tab(self):
        """Create agent control tab"""
        tab = QWidget()
        layout = QVBoxLayout()

        # Agent status
        status_group = QGroupBox("Agent Status")
        status_layout = QVBoxLayout()
        self.agent_status_table = QTableWidget()
        self.agent_status_table.setColumnCount(5)
        self.agent_status_table.setHorizontalHeaderLabels([
            "Agent", "Status", "Last Heartbeat", "Signals Produced", "Avg Confidence"
        ])
        status_layout.addWidget(self.agent_status_table)
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        # Agent controls
        control_group = QGroupBox("Run Agent Job")
        control_layout = QGridLayout()

        control_layout.addWidget(QLabel("Agent Type:"), 0, 0)
        self.agent_type_combo = QComboBox()
        self.agent_type_combo.addItems(["query", "monitor", "forecast", "summarizer"])
        control_layout.addWidget(self.agent_type_combo, 0, 1)

        control_layout.addWidget(QLabel("Topic/Entity:"), 1, 0)
        self.agent_topic_combo = QComboBox()
        self.agent_topic_combo.setEditable(True)
        self.agent_topic_combo.addItems([
            "economy", "market", "energy", "tech", "geopolitical",
            "USA", "China", "Europe", "global"
        ])
        control_layout.addWidget(self.agent_topic_combo, 1, 1)

        self.run_agent_btn = QPushButton("▶️ Run Agent Job")
        self.run_agent_btn.clicked.connect(self.run_agent_job)
        control_layout.addWidget(self.run_agent_btn, 2, 0, 1, 2)

        self.agent_progress = QProgressBar()
        control_layout.addWidget(self.agent_progress, 3, 0, 1, 2)

        control_group.setLayout(control_layout)
        layout.addWidget(control_group)

        # Job results
        results_group = QGroupBox("Job Results")
        results_layout = QVBoxLayout()
        self.job_results_text = QTextEdit()
        self.job_results_text.setReadOnly(True)
        results_layout.addWidget(self.job_results_text)
        results_group.setLayout(results_layout)
        layout.addWidget(results_group)

        tab.setLayout(layout)
        return tab

    def create_analytics_tab(self):
        """Create analytics tab"""
        tab = QWidget()
        layout = QVBoxLayout()

        # Time series chart
        if MATPLOTLIB_AVAILABLE:
            self.timeseries_chart = ChartWidget(self, width=10, height=6, dpi=100)
            layout.addWidget(self.timeseries_chart)
        else:
            layout.addWidget(QLabel("Charts unavailable (install matplotlib)"))

        # Analytics summary
        summary_group = QGroupBox("Analytics Summary")
        summary_layout = QVBoxLayout()
        self.analytics_text = QTextEdit()
        self.analytics_text.setReadOnly(True)
        summary_layout.addWidget(self.analytics_text)
        summary_group.setLayout(summary_layout)
        layout.addWidget(summary_group)

        tab.setLayout(layout)
        return tab

    def start_workers(self):
        """Start background workers"""
        # Signal fetcher
        self.signal_worker = SignalWorker(self.db)
        self.signal_worker.signals_updated.connect(self.update_signals)
        self.signal_worker.start()

        # Stats updater timer
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self.update_stats)
        self.stats_timer.start(5000)  # Every 5 seconds

        # Initial load
        self.refresh_all()

    def update_signals(self, signals: List[Dict]):
        """Update signals display"""
        self.signals = signals
        self.filter_signals()

    def filter_signals(self):
        """Filter and display signals"""
        category = self.category_filter.currentText()
        min_risk = self.risk_filter.value()

        filtered = self.signals
        if category != "all":
            filtered = [s for s in filtered if s.get('category') == category]
        if min_risk > 0:
            filtered = [s for s in filtered if s.get('risk_score', 0) >= min_risk]

        # Update table
        self.signals_table.setRowCount(len(filtered))
        for i, signal in enumerate(filtered):
            self.signals_table.setItem(i, 0, QTableWidgetItem(signal.get('ts', '')[:19]))
            self.signals_table.setItem(i, 1, QTableWidgetItem(signal.get('category', '')))
            self.signals_table.setItem(i, 2, QTableWidgetItem(signal.get('entity', '')))
            self.signals_table.setItem(i, 3, QTableWidgetItem(signal.get('title', '')))

            risk_score_item = QTableWidgetItem(f"{signal.get('risk_score', 0):.1f}")
            risk_score = signal.get('risk_score', 0)
            if risk_score >= 70:
                risk_score_item.setBackground(QColor(255, 200, 200))
            self.signals_table.setItem(i, 4, risk_score_item)

            self.signals_table.setItem(i, 5, QTableWidgetItem(signal.get('impact', '')))
            self.signals_table.setItem(i, 6, QTableWidgetItem(signal.get('source', '')))

    def show_signal_detail(self):
        """Show selected signal detail"""
        selected = self.signals_table.selectedItems()
        if not selected:
            return

        row = selected[0].row()
        if row >= len(self.signals):
            return

        signal = self.signals[row]

        detail = f"""
<h3>{signal.get('title', 'N/A')}</h3>
<p><b>Risk Score:</b> {signal.get('risk_score', 0):.1f} | <b>Impact:</b> {signal.get('impact', 'N/A')}</p>
<p><b>Category:</b> {signal.get('category', 'N/A')} | <b>Entity:</b> {signal.get('entity', 'N/A')}</p>
<p><b>Source:</b> {signal.get('source', 'N/A')} | <b>Confidence:</b> {signal.get('confidence', 0):.2f}</p>
<p><b>Time:</b> {signal.get('ts', 'N/A')}</p>
<hr>
<p><b>Summary:</b></p>
<p>{signal.get('summary', 'No summary available')}</p>
<p><b>Tags:</b> {', '.join(signal.get('tags', []))}</p>
"""
        if signal.get('link'):
            detail += f"<p><b>Link:</b> <a href='{signal['link']}'>{signal['link']}</a></p>"

        self.signal_detail_text.setHtml(detail)

    def update_stats(self):
        """Update statistics"""
        stats = self.db.get_signal_stats()

        self.total_signals_label.setText(f"Total Signals: {stats['total_signals']}")
        self.high_risk_label.setText(f"High Risk: {stats['high_risk_count']}")
        self.avg_score_label.setText(f"Avg Score: {stats['avg_risk_score']:.1f}")
        self.last_24h_label.setText(f"Last 24h: {stats['last_24h']}")

        # Update header stats
        self.stats_label.setText(
            f"Signals: {stats['total_signals']} | High Risk: {stats['high_risk_count']} | "
            f"24h: {stats['last_24h']}"
        )

        # Update recent high-risk signals
        high_risk_signals = [s for s in self.signals if s.get('risk_score', 0) > 70][:5]
        recent_text = "\n\n".join([
            f"[{s.get('category', 'N/A').upper()}] {s.get('title', 'N/A')} (Score: {s.get('risk_score', 0):.1f})"
            for s in high_risk_signals
        ])
        self.recent_signals_text.setText(recent_text or "No high-risk signals")

        # Update charts
        if MATPLOTLIB_AVAILABLE:
            self.update_charts(stats)

        # Update agent status
        self.update_agent_status()

    def update_charts(self, stats: Dict):
        """Update matplotlib charts"""
        # Risk score distribution
        self.risk_chart.axes.clear()
        risk_ranges = ['0-25', '26-50', '51-75', '76-100']
        risk_counts = [0, 0, 0, 0]
        for s in self.signals:
            score = s.get('risk_score', 0)
            if score <= 25:
                risk_counts[0] += 1
            elif score <= 50:
                risk_counts[1] += 1
            elif score <= 75:
                risk_counts[2] += 1
            else:
                risk_counts[3] += 1

        self.risk_chart.axes.bar(risk_ranges, risk_counts, color=['green', 'yellow', 'orange', 'red'])
        self.risk_chart.axes.set_title('Risk Score Distribution')
        self.risk_chart.axes.set_ylabel('Count')
        self.risk_chart.draw()

        # Category breakdown
        self.category_chart.axes.clear()
        categories = list(stats['by_category'].keys())[:8]
        counts = [stats['by_category'][c] for c in categories]
        self.category_chart.axes.pie(counts, labels=categories, autopct='%1.1f%%')
        self.category_chart.axes.set_title('Signals by Category')
        self.category_chart.draw()

    def update_agent_status(self):
        """Update agent status table"""
        agent_status = self.db.get_agent_status()
        self.agent_status_table.setRowCount(len(agent_status))

        for i, agent in enumerate(agent_status):
            self.agent_status_table.setItem(i, 0, QTableWidgetItem(agent.get('agent_name', '')))
            self.agent_status_table.setItem(i, 1, QTableWidgetItem(agent.get('status', '')))
            self.agent_status_table.setItem(i, 2, QTableWidgetItem(agent.get('last_heartbeat', '')[:19]))
            self.agent_status_table.setItem(i, 3, QTableWidgetItem(str(agent.get('signals_produced', 0))))
            self.agent_status_table.setItem(i, 4, QTableWidgetItem(f"{agent.get('avg_confidence', 0):.2f}"))

    def run_agent_job(self):
        """Run selected agent job"""
        agent_type = self.agent_type_combo.currentText()
        topic = self.agent_topic_combo.currentText()

        self.run_agent_btn.setEnabled(False)
        self.agent_progress.setValue(0)
        self.job_results_text.append(f"\n[{datetime.now():%H:%M:%S}] Running {agent_type} agent for {topic}...")

        # Create job
        job = AgentJob(
            name=f"{agent_type}_job",
            params={'topic': topic, 'entity': topic},
            entities=[topic]
        )

        # Run async
        async def run():
            result = await run_agent_job(agent_type, job)
            return result

        # Run in event loop (simplified - in production use proper async integration)
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        result = loop.run_until_complete(run())

        self.agent_progress.setValue(100)
        self.job_results_text.append(json.dumps(result, indent=2))
        self.run_agent_btn.setEnabled(True)
        self.refresh_all()

    def refresh_all(self):
        """Refresh all data"""
        self.signals = self.db.get_latest_signals(limit=100)
        self.update_signals(self.signals)
        self.update_stats()

    def closeEvent(self, event):
        """Clean shutdown"""
        if hasattr(self, 'signal_worker'):
            self.signal_worker.stop()
            self.signal_worker.wait()
        event.accept()


def launch_dashboard():
    """Launch the dashboard"""
    if not PYQT_AVAILABLE:
        print("ERROR: PyQt6 is required for the dashboard")
        print("Install with: pip install PyQt6")
        return

    app = QApplication(sys.argv)
    dashboard = RiskDashboard()
    dashboard.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    launch_dashboard()
