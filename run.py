#!/usr/bin/env python3
"""
BSG Bot Interactive Launcher
The single, simple entry point for all BSG Bot functionality.
Just run: python run.py
"""

import os
import sys
import subprocess
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.text import Text
from rich.layout import Layout
from rich.align import Align

console = Console()


def show_welcome():
    """Display welcome message and system info"""
    welcome_text = Text()
    welcome_text.append("🤖 BSG Bot ", style="bold cyan")
    welcome_text.append("- Sentiment Analysis & Intelligence Platform", style="white")

    panel = Panel(
        Align.center(welcome_text), title="Welcome", border_style="cyan", padding=(1, 2)
    )
    console.print(panel)
    console.print()


def show_main_menu():
    """Show the main interactive menu"""
    table = Table(title="🚀 What would you like to do?", show_header=False)
    table.add_column("Option", style="bold cyan", width=4)
    table.add_column("Action", style="white", width=50)
    table.add_column("Description", style="dim", width=60)

    # Main analysis options
    table.add_row(
        "1",
        "🔍 Run Smart Analysis",
        "Intelligent source selection + sentiment analysis",
    )
    table.add_row(
        "2",
        "🧠 AI Market Intelligence",
        "GPT-4o-mini analysis with trading recommendations",
    )
    table.add_row(
        "3", "📡 Use Modern Connectors", "Reddit, Twitter, YouTube, HackerNews, etc."
    )
    table.add_row(
        "4", "🏥 Check System Health", "View source health metrics and status"
    )

    # Management options
    table.add_row("", "", "")  # Separator
    table.add_row(
        "5", "📊 View Statistics", "SKB catalog stats and source distribution"
    )
    table.add_row("6", "📥 Import SKB Data", "Import sources from YAML files")
    table.add_row("7", "🔧 List Connectors", "Show all available connector types")

    # Quick actions
    table.add_row("", "", "")  # Separator
    table.add_row("8", "⚡ Quick Crypto Analysis", "Fast crypto sentiment analysis")
    table.add_row("9", "🌍 Regional Analysis", "Focus on specific regions")
    table.add_row("10", "🗳️ Election Monitoring", "Political sentiment tracking")

    # System options
    table.add_row("", "", "")  # Separator
    table.add_row("11", "🧪 Run Tests", "Execute test suites")
    table.add_row("12", "📈 Production Dashboard", "Production readiness metrics")
    table.add_row("0", "❌ Exit", "Close BSG Bot")

    console.print(table)
    console.print()


def get_text_input(prompt_text: str, default: str = None) -> str:
    """Get text input with optional default"""
    if default:
        return Prompt.ask(prompt_text, default=default)
    return Prompt.ask(prompt_text)


def run_command(cmd: list, description: str = None):
    """Run a command with nice output"""
    if description:
        console.print(f"\n🔄 {description}...", style="yellow")

    try:
        result = subprocess.run(cmd, cwd=Path.cwd(), capture_output=False, text=True)
        if result.returncode == 0:
            console.print(f"✅ Completed successfully!", style="green")
        else:
            console.print(
                f"⚠️ Command exited with code {result.returncode}", style="yellow"
            )
    except Exception as e:
        console.print(f"❌ Error: {e}", style="red")

    input("\nPress Enter to continue...")


def handle_smart_analysis():
    """Handle smart analysis workflow"""
    console.print("\n🧠 Smart Analysis Configuration", style="bold cyan")

    # Get region
    region = Prompt.ask(
        "Target region",
        choices=["asia", "middle_east", "europe", "americas", "africa", "all"],
        default="all",
    )

    # Get topic
    topic = Prompt.ask(
        "Standard topic",
        choices=[
            "elections",
            "security",
            "economy",
            "politics",
            "energy",
            "climate",
            "tech",
            "all",
        ],
        default="all",
    )

    # Custom topic option
    if topic == "all":
        custom = get_text_input("Or enter custom topic (press Enter to skip)")
        if custom:
            topic = custom

    # Build command
    cmd = ["python", "-m", "sentiment_bot.cli_unified", "run"]

    if region != "all":
        cmd.extend(["--region", region])
    if topic != "all":
        cmd.extend(["--topic", topic])

    # Additional options
    if Confirm.ask("Enable strict matching?", default=False):
        cmd.append("--strict")

    if Confirm.ask("Export to CSV?", default=True):
        cmd.append("--export-csv")

    run_command(cmd, f"Running smart analysis for {topic} in {region}")


def handle_ai_market_intelligence():
    """Handle AI market intelligence workflow with GPT-4o-mini"""
    console.print("\n🧠 AI Market Intelligence Configuration", style="bold cyan")
    console.print(
        "🤖 Using GPT-4o-mini for Wall Street-grade analysis with trading recommendations",
        style="dim",
    )

    # Get region
    region = Prompt.ask(
        "Target region",
        choices=["asia", "middle_east", "europe", "americas", "africa", "all"],
        default="americas",
    )

    # Get market focus
    focus = Prompt.ask(
        "Market focus",
        choices=["economy", "tech", "energy", "healthcare", "finance", "crypto", "all"],
        default="all",
    )

    # Get analysis depth
    budget = Prompt.ask(
        "Analysis depth (seconds)", choices=["15", "30", "60", "120"], default="30"
    )

    # Minimum sources
    min_sources = Prompt.ask(
        "Minimum sources", choices=["2", "5", "10", "20"], default="5"
    )

    # Build command with LLM flag
    cmd = ["python", "-m", "sentiment_bot.cli_unified", "run", "--llm"]

    if region != "all":
        cmd.extend(["--region", region])
    if focus != "all":
        cmd.extend(["--topic", focus])

    cmd.extend(["--budget", budget])
    cmd.extend(["--min-sources", min_sources])

    # Always export for AI analysis
    cmd.append("--export-csv")

    run_command(cmd, f"Running AI market intelligence analysis for {focus} in {region}")


def handle_connectors():
    """Handle connector workflow"""
    console.print("\n📡 Modern Connectors Configuration", style="bold cyan")

    # Get keywords
    keywords = get_text_input("Keywords (comma-separated)", "crypto,bitcoin,blockchain")

    # Get connector type
    connector_type = Prompt.ask(
        "Connector type (or 'all' for all connectors)",
        choices=["all", "reddit", "twitter", "youtube", "hackernews", "google_news"],
        default="all",
    )

    # Get time window
    since = Prompt.ask("Time window", choices=["24h", "7d", "30d"], default="7d")

    # Build command
    cmd = ["python", "-m", "sentiment_bot.cli_unified", "connectors"]
    cmd.extend(["--config", "config/connectors.yaml"])
    cmd.extend(["--keywords", keywords])
    cmd.extend(["--since", since])

    if connector_type != "all":
        cmd.extend(["--type", connector_type])

    if Confirm.ask("Run sentiment analysis?", default=True):
        cmd.append("--analyze")

    limit = int(Prompt.ask("Max items per connector", default="400"))
    cmd.extend(["--limit", str(limit)])

    run_command(cmd, f"Running connectors for '{keywords}'")


def handle_quick_actions():
    """Handle quick action workflows"""
    console.print("\n⚡ Quick Actions", style="bold cyan")

    action = Prompt.ask(
        "Select quick action",
        choices=["crypto", "regional", "elections", "back"],
        default="crypto",
    )

    if action == "back":
        return
    elif action == "crypto":
        cmd = [
            "python",
            "-m",
            "sentiment_bot.cli_unified",
            "connectors",
            "--config",
            "config/connectors.yaml",
            "--keywords",
            "crypto,bitcoin,ethereum,blockchain,defi,web3",
            "--analyze",
            "--since",
            "24h",
            "--limit",
            "200",
        ]
        run_command(cmd, "Running crypto sentiment analysis")
    elif action == "regional":
        region = Prompt.ask(
            "Select region",
            choices=["asia", "middle_east", "europe", "americas", "africa"],
        )
        cmd = [
            "python",
            "-m",
            "sentiment_bot.cli_unified",
            "run",
            "--region",
            region,
            "--export-csv",
        ]
        run_command(cmd, f"Running regional analysis for {region}")
    elif action == "elections":
        cmd = [
            "python",
            "-m",
            "sentiment_bot.cli_unified",
            "run",
            "--topic",
            "elections",
            "--strict",
            "--export-csv",
        ]
        run_command(cmd, "Running election monitoring")


def main():
    """Main interactive loop"""
    try:
        # Check if we're in the right directory
        if not Path("sentiment_bot").exists():
            console.print(
                "❌ Error: Please run this from the BSG Bot directory", style="red"
            )
            sys.exit(1)

        while True:
            console.clear()
            show_welcome()
            show_main_menu()

            choice = Prompt.ask("Select an option", choices=[str(i) for i in range(13)])

            if choice == "0":
                console.print("\n👋 Goodbye! Thanks for using BSG Bot!", style="cyan")
                break
            elif choice == "1":
                handle_smart_analysis()
            elif choice == "2":
                handle_ai_market_intelligence()
            elif choice == "3":
                handle_connectors()
            elif choice == "4":
                run_command(
                    ["python", "-m", "sentiment_bot.cli_unified", "health"],
                    "Checking system health",
                )
            elif choice == "5":
                run_command(
                    ["python", "-m", "sentiment_bot.cli_unified", "stats"],
                    "Loading statistics",
                )
            elif choice == "6":
                yaml_path = get_text_input(
                    "Path to YAML file", "config/skb_sources.yaml"
                )
                run_command(
                    [
                        "python",
                        "-m",
                        "sentiment_bot.cli_unified",
                        "import-skb",
                        yaml_path,
                    ],
                    "Importing SKB data",
                )
            elif choice == "7":
                run_command(
                    ["python", "-m", "sentiment_bot.cli_unified", "list-connectors"],
                    "Loading connector list",
                )
            elif choice in ["8", "9", "10"]:
                handle_quick_actions()
            elif choice == "11":
                test_choice = Prompt.ask(
                    "Which test suite?",
                    choices=["smoke", "complete", "production"],
                    default="smoke",
                )
                if test_choice == "smoke":
                    run_command(["python", "smoke_test.py"], "Running smoke tests")
                elif test_choice == "complete":
                    run_command(
                        ["python", "test_complete_system.py"],
                        "Running complete system tests",
                    )
                elif test_choice == "production":
                    run_command(
                        ["python", "production_readiness_suite.py"],
                        "Running production tests",
                    )
            elif choice == "12":
                run_command(
                    ["python", "production_readiness_demo.py"],
                    "Loading production dashboard",
                )

    except KeyboardInterrupt:
        console.print("\n\n👋 Interrupted by user. Goodbye!", style="yellow")
    except Exception as e:
        console.print(f"\n❌ Unexpected error: {e}", style="red")
        console.print("Please report this issue to the development team.", style="dim")


if __name__ == "__main__":
    main()
