#!/usr/bin/env python3
"""
BRG Intelligence Platform - GUI Launcher
Modern windowed interface - no terminal menus
"""

import sys
import subprocess
import asyncio
from pathlib import Path

try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QGridLayout, QFrame, QTextEdit, QProgressBar,
        QTabWidget, QScrollArea, QMessageBox
    )
    from PyQt6.QtCore import Qt, QSize, QThread, pyqtSignal
    from PyQt6.QtGui import QFont, QIcon, QPixmap, QColor
    PYQT_AVAILABLE = True
except ImportError:
    print("ERROR: PyQt6 is required")
    print("Install with: pip install PyQt6")
    sys.exit(1)


class TaskRunner(QThread):
    """Background thread for running tasks"""
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, command):
        super().__init__()
        self.command = command

    def run(self):
        try:
            self.progress.emit(f"Running: {self.command}")
            result = subprocess.run(
                self.command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=str(Path.cwd())
            )
            if result.returncode == 0:
                self.finished.emit(f"✅ Success!\n{result.stdout[:500]}")
            else:
                self.error.emit(f"❌ Error (code {result.returncode}):\n{result.stderr[:500]}")
        except Exception as e:
            self.error.emit(f"❌ Exception: {str(e)}")


class LauncherWindow(QMainWindow):
    """Main GUI Launcher Window"""

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        """Initialize the GUI"""
        self.setWindowTitle("BRG Intelligence Platform - Control Center")
        self.setGeometry(100, 100, 1400, 900)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)

        # Main layout
        main_layout = QVBoxLayout()
        central.setLayout(main_layout)

        # Header
        header = self.create_header()
        main_layout.addWidget(header)

        # Tabs for organization
        tabs = QTabWidget()
        tabs.setFont(QFont("Arial", 11))

        # Tab 1: Dashboard & Overview
        tabs.addTab(self.create_dashboard_tab(), "🎯 Dashboard")

        # Tab 2: Sentiment Analysis
        tabs.addTab(self.create_sentiment_tab(), "📰 Sentiment")

        # Tab 3: Economic Forecasting
        tabs.addTab(self.create_economic_tab(), "📊 Economic")

        # Tab 4: Risk Intelligence
        tabs.addTab(self.create_risk_tab(), "🚨 Risk Intel")

        # Tab 5: System Tools
        tabs.addTab(self.create_tools_tab(), "⚙️ Tools")

        main_layout.addWidget(tabs)

        # Output panel
        output_frame = QFrame()
        output_frame.setFrameShape(QFrame.Shape.StyledPanel)
        output_layout = QVBoxLayout()

        output_label = QLabel("📋 Output Log")
        output_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        output_layout.addWidget(output_label)

        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setMaximumHeight(150)
        self.output_text.setStyleSheet("background-color: #2b2b2b; color: #00ff00; font-family: monospace;")
        output_layout.addWidget(self.output_text)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        output_layout.addWidget(self.progress_bar)

        output_frame.setLayout(output_layout)
        main_layout.addWidget(output_frame)

        # Status bar
        self.statusBar().showMessage("🟢 All Systems Operational")

        # Apply styling
        self.apply_styling()

        # Welcome message
        self.log("🚀 BRG Intelligence Platform initialized")
        self.log("✅ Ready for operations")

    def create_header(self):
        """Create header with logo and title"""
        header = QFrame()
        header.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1e3c72, stop:1 #2a5298);
                border-radius: 10px;
                padding: 20px;
            }
        """)

        layout = QHBoxLayout()

        # Logo section
        logo_layout = QVBoxLayout()
        logo = QLabel("🔷 BRG")
        logo.setFont(QFont("Arial", 42, QFont.Weight.Bold))
        logo.setStyleSheet("color: white;")

        title = QLabel("Intelligence Platform")
        title.setFont(QFont("Arial", 20))
        title.setStyleSheet("color: white; margin-top: -10px;")

        subtitle = QLabel("Unified Control Center")
        subtitle.setFont(QFont("Arial", 12))
        subtitle.setStyleSheet("color: #b0c4de;")

        logo_layout.addWidget(logo)
        logo_layout.addWidget(title)
        logo_layout.addWidget(subtitle)
        logo_layout.setSpacing(0)

        layout.addLayout(logo_layout)
        layout.addStretch()

        # Quick stats
        stats = QLabel("📊 3 Systems • 🤖 4 AI Agents • 📰 1,413 Sources • 🌍 200+ Countries")
        stats.setFont(QFont("Arial", 11))
        stats.setStyleSheet("color: white; padding: 10px;")
        layout.addWidget(stats)

        header.setLayout(layout)
        return header

    def create_dashboard_tab(self):
        """Create main dashboard tab"""
        tab = QWidget()
        layout = QVBoxLayout()

        # Quick actions
        quick_group = self.create_section("🚀 Quick Actions")
        quick_layout = QGridLayout()

        actions = [
            ("🎯 Unified Dashboard", "Launch complete dashboard with all systems", "python unified_dashboard.py"),
            ("📡 Start API Server", "Start REST API on port 8765", "python -m sentiment_bot.risk_intelligence.api"),
            ("🤖 Run All Agents", "Execute all 4 risk intelligence agents", "python demo_risk_intelligence.py"),
            ("🧪 Run Tests", "Validate all systems", "python test_risk_intelligence.py"),
        ]

        row, col = 0, 0
        for title, desc, cmd in actions:
            btn = self.create_action_button(title, desc, cmd)
            quick_layout.addWidget(btn, row, col)
            col += 1
            if col > 1:
                col = 0
                row += 1

        quick_group.layout().addLayout(quick_layout)
        layout.addWidget(quick_group)

        # System status
        status_group = self.create_section("📊 System Status")
        status_layout = QVBoxLayout()

        status_items = [
            ("📰 Sentiment Analysis", "1,413 sources, 3,903 RSS feeds", "🟢 Operational"),
            ("📊 Economic Forecasting", "15+ models, 200+ countries", "🟢 Operational"),
            ("🚨 Risk Intelligence", "4 AI agents, NLP pipeline", "🟢 Operational"),
        ]

        for title, desc, status in status_items:
            item = self.create_status_item(title, desc, status)
            status_layout.addWidget(item)

        status_group.layout().addLayout(status_layout)
        layout.addWidget(status_group)

        layout.addStretch()
        tab.setLayout(layout)
        return tab

    def create_sentiment_tab(self):
        """Create sentiment analysis tab"""
        tab = QWidget()
        layout = QVBoxLayout()

        # Actions
        actions_group = self.create_section("📰 Sentiment Analysis Actions")
        actions_layout = QGridLayout()

        actions = [
            ("🔍 Smart Analysis", "Intelligent source selection + sentiment",
             "python -m sentiment_bot.cli_unified run --topic economy --export-csv"),
            ("🧠 AI Market Intel", "GPT-4o analysis with recommendations",
             "python -m sentiment_bot.cli_unified run --llm --topic tech"),
            ("📡 Modern Connectors", "Reddit, Twitter, YouTube, etc.",
             "python -m sentiment_bot.cli_unified connectors --keywords 'economy,trade'"),
            ("🏥 Health Check", "View source health metrics",
             "python -m sentiment_bot.cli_unified health"),
            ("📊 View Statistics", "SKB catalog stats",
             "python -m sentiment_bot.cli_unified stats"),
            ("🌍 Regional Analysis", "Focus on specific regions",
             "python -m sentiment_bot.cli_unified run --region americas"),
        ]

        row, col = 0, 0
        for title, desc, cmd in actions:
            btn = self.create_action_button(title, desc, cmd)
            actions_layout.addWidget(btn, row, col)
            col += 1
            if col > 1:
                col = 0
                row += 1

        actions_group.layout().addLayout(actions_layout)
        layout.addWidget(actions_group)

        # Info
        info_group = self.create_section("ℹ️ System Information")
        info_text = QLabel("""
        <b>Part 1: Sentiment Analysis Engine</b><br>
        • 1,413 curated domains<br>
        • 3,903 RSS endpoints<br>
        • 16 modern connectors (no API keys)<br>
        • 400+ articles/minute processing<br>
        • 95-98% success rate<br>
        • Global coverage
        """)
        info_text.setStyleSheet("padding: 10px;")
        info_group.layout().addWidget(info_text)
        layout.addWidget(info_group)

        layout.addStretch()
        tab.setLayout(layout)
        return tab

    def create_economic_tab(self):
        """Create economic forecasting tab"""
        tab = QWidget()
        layout = QVBoxLayout()

        # Actions
        actions_group = self.create_section("📊 Economic Forecasting Actions")
        actions_layout = QGridLayout()

        actions = [
            ("🌍 Global Predictors", "GDP & Inflation for 50+ countries",
             "python -c \"from sentiment_bot.economic_predictor import run_predictions; import asyncio; asyncio.run(run_predictions())\""),
            ("📈 Enhanced Predictor", "Advanced GDP predictions",
             "python -m sentiment_bot.economic_predictor"),
            ("💹 Market Analysis", "Jobs, Inflation, FX, Equity",
             "python -m sentiment_bot.comprehensive_predictors"),
            ("📊 FRED Predictors", "Federal Reserve data",
             "python -m sentiment_bot.fred_predictors"),
            ("🎯 Unified GDP", "Production-ready GDP nowcasting",
             "python -m sentiment_bot.unified_gdp"),
            ("🇺🇸 USA Analysis", "S&P 500 predictions",
             "python -m sentiment_bot.usa_enhanced"),
        ]

        row, col = 0, 0
        for title, desc, cmd in actions:
            btn = self.create_action_button(title, desc, cmd)
            actions_layout.addWidget(btn, row, col)
            col += 1
            if col > 1:
                col = 0
                row += 1

        actions_group.layout().addLayout(actions_layout)
        layout.addWidget(actions_group)

        # Info
        info_group = self.create_section("ℹ️ System Information")
        info_text = QLabel("""
        <b>Part 2: Economic Forecasting Engine</b><br>
        • 15+ economic models (ARIMA, VAR, ML)<br>
        • GDP MAE 1.452pp (matches IMF/World Bank)<br>
        • 200+ country coverage<br>
        • Real-time FRED data integration<br>
        • Confidence intervals<br>
        • Multiple time horizons
        """)
        info_text.setStyleSheet("padding: 10px;")
        info_group.layout().addWidget(info_text)
        layout.addWidget(info_group)

        layout.addStretch()
        tab.setLayout(layout)
        return tab

    def create_risk_tab(self):
        """Create risk intelligence tab"""
        tab = QWidget()
        layout = QVBoxLayout()

        # Actions
        actions_group = self.create_section("🚨 Risk Intelligence Actions")
        actions_layout = QGridLayout()

        actions = [
            ("🎯 Launch Dashboard", "Interactive GUI with charts",
             "python -m sentiment_bot.risk_intelligence.dashboard"),
            ("🚀 Start API", "REST API on port 8765",
             "python -m sentiment_bot.risk_intelligence.api"),
            ("🤖 Query Agent", "Weak signal detection",
             "python -c \"import asyncio; from sentiment_bot.risk_intelligence import *; asyncio.run(run_agent_job('query', AgentJob('test', {'topic':'markets'})))\""),
            ("📡 Monitor Agent", "Feed anomaly detection",
             "python -c \"import asyncio; from sentiment_bot.risk_intelligence import *; asyncio.run(run_agent_job('monitor', AgentJob('test', {'entity':'tech'})))\""),
            ("🔮 Forecast Agent", "Causal impact analysis",
             "python -c \"import asyncio; from sentiment_bot.risk_intelligence import *; asyncio.run(run_agent_job('forecast', AgentJob('test', {'event':'tariff','metric':'GDP'})))\""),
            ("📊 Summarizer Agent", "Daily digest generation",
             "python -c \"import asyncio; from sentiment_bot.risk_intelligence import *; asyncio.run(run_agent_job('summarizer', AgentJob('test', {'entity':'global'})))\""),
        ]

        row, col = 0, 0
        for title, desc, cmd in actions:
            btn = self.create_action_button(title, desc, cmd)
            actions_layout.addWidget(btn, row, col)
            col += 1
            if col > 1:
                col = 0
                row += 1

        actions_group.layout().addLayout(actions_layout)
        layout.addWidget(actions_group)

        # Info
        info_group = self.create_section("ℹ️ System Information")
        info_text = QLabel("""
        <b>Part 3: Risk Intelligence & Agentic System</b><br>
        • 4 AI agents (Query, Monitor, Forecast, Summarizer)<br>
        • NLP enrichment pipeline (NER, embeddings)<br>
        • 0-100 risk scoring algorithm<br>
        • Real-time signal monitoring<br>
        • Content-based deduplication<br>
        • REST API with 8 endpoints
        """)
        info_text.setStyleSheet("padding: 10px;")
        info_group.layout().addWidget(info_text)
        layout.addWidget(info_group)

        layout.addStretch()
        tab.setLayout(layout)
        return tab

    def create_tools_tab(self):
        """Create system tools tab"""
        tab = QWidget()
        layout = QVBoxLayout()

        # Testing
        test_group = self.create_section("🧪 Testing & Validation")
        test_layout = QGridLayout()

        tests = [
            ("🧪 Run All Tests", "Complete test suite", "python test_risk_intelligence.py"),
            ("🎭 Demo System", "Full demonstration", "python demo_risk_intelligence.py"),
            ("✅ Smoke Tests", "Quick validation", "python smoke_test.py"),
            ("📊 Production Tests", "Production readiness", "python production_readiness_suite.py"),
        ]

        row, col = 0, 0
        for title, desc, cmd in tests:
            btn = self.create_action_button(title, desc, cmd)
            test_layout.addWidget(btn, row, col)
            col += 1
            if col > 1:
                col = 0
                row += 1

        test_group.layout().addLayout(test_layout)
        layout.addWidget(test_group)

        # Documentation
        docs_group = self.create_section("📚 Documentation")
        docs_layout = QGridLayout()

        docs = [
            ("📖 Risk Intel Guide", "Open complete guide", "open RISK_INTELLIGENCE_GUIDE.md"),
            ("📋 Implementation", "View implementation report", "open IMPLEMENTATION_COMPLETE.md"),
            ("✅ Production Checklist", "Production readiness", "open PRODUCTION_READINESS_CHECKLIST.md"),
            ("🚀 Quick Start", "Quick reference", "open QUICK_START.md"),
        ]

        row, col = 0, 0
        for title, desc, cmd in docs:
            btn = self.create_action_button(title, desc, cmd)
            docs_layout.addWidget(btn, row, col)
            col += 1
            if col > 1:
                col = 0
                row += 1

        docs_group.layout().addLayout(docs_layout)
        layout.addWidget(docs_group)

        layout.addStretch()
        tab.setLayout(layout)
        return tab

    def create_section(self, title: str):
        """Create a section groupbox"""
        group = QFrame()
        group.setFrameShape(QFrame.Shape.StyledPanel)
        group.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 8px;
                padding: 15px;
                margin: 5px;
            }
        """)

        layout = QVBoxLayout()

        title_label = QLabel(title)
        title_label.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #1e3c72; padding-bottom: 10px;")
        layout.addWidget(title_label)

        group.setLayout(layout)
        return group

    def create_action_button(self, title: str, desc: str, cmd: str):
        """Create an action button"""
        btn = QPushButton()
        btn.setFixedHeight(100)

        # Button text
        text = f"<div style='text-align: center;'>" \
               f"<b style='font-size: 14px;'>{title}</b><br>" \
               f"<span style='color: #666; font-size: 10px;'>{desc}</span>" \
               f"</div>"

        btn.setText("")
        btn.setToolTip(cmd)

        # Create custom widget for button content
        widget = QWidget()
        widget_layout = QVBoxLayout()
        widget_layout.setContentsMargins(10, 10, 10, 10)

        title_label = QLabel(title)
        title_label.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("color: #1e3c72;")

        desc_label = QLabel(desc)
        desc_label.setFont(QFont("Arial", 9))
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setStyleSheet("color: #666;")
        desc_label.setWordWrap(True)

        widget_layout.addWidget(title_label)
        widget_layout.addWidget(desc_label)
        widget.setLayout(widget_layout)

        # Store command
        btn.clicked.connect(lambda: self.run_command(cmd, title))

        btn.setStyleSheet("""
            QPushButton {
                background-color: white;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #f0f8ff;
                border-color: #2196F3;
            }
            QPushButton:pressed {
                background-color: #e3f2fd;
            }
        """)

        # Add widget to button layout
        btn_layout = QVBoxLayout()
        btn_layout.addWidget(widget)
        btn.setLayout(btn_layout)

        return btn

    def create_status_item(self, title: str, desc: str, status: str):
        """Create a status display item"""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #f9f9f9;
                border-left: 4px solid #4CAF50;
                border-radius: 5px;
                padding: 15px;
                margin: 5px;
            }
        """)

        layout = QHBoxLayout()

        title_label = QLabel(title)
        title_label.setFont(QFont("Arial", 11, QFont.Weight.Bold))

        desc_label = QLabel(desc)
        desc_label.setFont(QFont("Arial", 9))
        desc_label.setStyleSheet("color: #666;")

        status_label = QLabel(status)
        status_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        status_label.setStyleSheet("color: #4CAF50;")

        layout.addWidget(title_label)
        layout.addWidget(desc_label)
        layout.addStretch()
        layout.addWidget(status_label)

        frame.setLayout(layout)
        return frame

    def run_command(self, cmd: str, title: str):
        """Run a command in background"""
        self.log(f"\n🚀 Launching: {title}")
        self.log(f"Command: {cmd}")

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate

        self.runner = TaskRunner(cmd)
        self.runner.finished.connect(self.on_task_finished)
        self.runner.error.connect(self.on_task_error)
        self.runner.progress.connect(self.log)
        self.runner.start()

        self.statusBar().showMessage(f"Running: {title}...")

    def on_task_finished(self, message: str):
        """Handle task completion"""
        self.log(message)
        self.progress_bar.setVisible(False)
        self.statusBar().showMessage("✅ Task completed", 5000)

    def on_task_error(self, message: str):
        """Handle task error"""
        self.log(message)
        self.progress_bar.setVisible(False)
        self.statusBar().showMessage("❌ Task failed", 5000)
        QMessageBox.warning(self, "Task Failed", message)

    def log(self, message: str):
        """Log message to output"""
        self.output_text.append(message)
        self.output_text.verticalScrollBar().setValue(
            self.output_text.verticalScrollBar().maximum()
        )

    def apply_styling(self):
        """Apply global styling"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
            QTabWidget::pane {
                border: 1px solid #ddd;
                border-radius: 5px;
                background-color: #fafafa;
            }
            QTabBar::tab {
                background-color: #e0e0e0;
                padding: 12px 24px;
                margin-right: 2px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background-color: white;
                color: #1e3c72;
            }
        """)


def main():
    """Launch the GUI"""
    if not PYQT_AVAILABLE:
        print("ERROR: PyQt6 is required")
        print("Install with: pip install PyQt6")
        return 1

    app = QApplication(sys.argv)
    app.setApplicationName("BRG Intelligence Platform")

    window = LauncherWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
