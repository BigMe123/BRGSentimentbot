#!/usr/bin/env python3
"""
BRG Intelligence Platform - Main Launcher
Launches the unified dashboard with real-time operations

This launcher starts the visually stunning BRG-branded dashboard
that runs REAL bot operations (not simulations).

Features:
- BRG dark theme (#0d1117 background)
- Live bot activity feed
- Real data from all 3 systems
- Interactive controls
- Professional OpenAI-style design
"""

import sys
import os
from pathlib import Path

def main():
    """Launch the BRG Unified Dashboard"""

    print("=" * 60)
    print("BRG UNIFIED INTELLIGENCE PLATFORM")
    print("=" * 60)
    print("Launching with REAL bot operations...")
    print("   [OK] Risk Intelligence Agents")
    print("   [OK] Sentiment Analysis Connectors")
    print("   [OK] Economic Forecasting Models")
    print("=" * 60)

    # Verify we're in the right directory
    base_dir = Path(__file__).parent
    os.chdir(base_dir)

    # Check if PyQt6 is available
    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError:
        print("\n[ERROR] ERROR: PyQt6 is required for the dashboard")
        print("[INSTALL] Install with: pip install PyQt6 matplotlib")
        print("\nAlternatively, use the control center:")
        print("   python gui_launcher.py")
        return 1

    # Import and launch the unified dashboard
    try:
        from unified_dashboard import UnifiedDashboard

        app = QApplication(sys.argv)
        app.setApplicationName("BRG Intelligence Platform")

        # Create and show dashboard
        dashboard = UnifiedDashboard()
        dashboard.show()

        print("[SUCCESS] Dashboard launched! Watch the Live Bot Activity tab for real operations.")
        print("=" * 60)

        return app.exec()

    except Exception as e:
        print(f"\n[ERROR] ERROR launching dashboard: {e}")
        print("\n[HELP] Troubleshooting:")
        print("   1. Ensure all dependencies are installed:")
        print("      pip install PyQt6 matplotlib")
        print("   2. Check that unified_dashboard.py exists")
        print("   3. Try the alternative control center:")
        print("      python gui_launcher.py")
        return 1

if __name__ == "__main__":
    sys.exit(main())
