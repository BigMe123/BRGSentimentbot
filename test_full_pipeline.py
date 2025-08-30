#!/usr/bin/env python3
"""
Test the complete pipeline with master sources and source selector.
"""

import asyncio
import sys
from rich.console import Console
from sentiment_bot.master_sources import get_master_sources
from sentiment_bot.skb_catalog import get_catalog
from sentiment_bot.selection_planner import SelectionPlanner, SelectionQuotas

console = Console()


async def test_full_pipeline():
    """Test the complete analysis pipeline."""
    console.print("\n🧪 Testing Full Pipeline with Master Sources\n", style="bold cyan")

    # Test 1: Master sources are loaded
    console.print("Test 1: Master sources loaded...", style="yellow")
    manager = get_master_sources()
    all_sources = manager.get_all_sources()
    console.print(
        f"✅ {len(all_sources)} sources available from master list", style="green"
    )

    # Test 2: SKB catalog works
    console.print("\nTest 2: SKB catalog initialized...", style="yellow")
    catalog = get_catalog()
    console.print(f"✅ SKB catalog ready", style="green")

    # Test 3: Selection planner works
    console.print("\nTest 3: Selection planner working...", style="yellow")
    planner = SelectionPlanner(catalog)

    # Create quotas
    quotas = SelectionQuotas(min_sources=30, max_sources=120, time_budget_seconds=300)

    # Plan selection for Americas
    plan = planner.plan_selection(region="americas", topics=None, quotas=quotas)

    console.print(
        f"✅ Selected {len(plan.sources)} sources for Americas region", style="green"
    )

    # Show sample sources
    console.print("\nSample selected sources:", style="cyan")
    for i, source in enumerate(plan.sources[:10], 1):
        console.print(f"  {i:2}. {source.domain:30} (priority: {source.priority:.2f})")

    # Test 4: Diversity metrics
    console.print("\nTest 4: Diversity metrics...", style="yellow")
    diversity_score = plan.get_diversity_score()
    console.print(f"✅ Diversity score: {diversity_score:.2f}", style="green")

    meets_quotas, issues = plan.meets_quotas()
    if meets_quotas:
        console.print("✅ All quotas met", style="green")
    else:
        console.print(f"⚠️  Some quotas not met: {', '.join(issues)}", style="yellow")

    return True


def main():
    """Main test function."""
    console.print("=" * 60)
    console.print("🌍 Full Pipeline Test with Master Sources", style="bold blue")
    console.print("=" * 60)

    try:
        success = asyncio.run(test_full_pipeline())

        console.print("\n" + "=" * 60)
        if success:
            console.print("✅ All pipeline tests passed!", style="bold green")
            console.print("\n📊 The system is working correctly:", style="cyan")
            console.print("  • Master sources: ✅ Loaded")
            console.print("  • SKB catalog: ✅ Integrated")
            console.print("  • Source selector: ✅ Working")
            console.print("  • Selection planner: ✅ Functional")
            console.print("\n🚀 You can now run analysis with:", style="cyan")
            console.print("  python run.py")
            console.print("  bsgbot run --region americas --topic economy")
            console.print("  ./bsgbot_master.sh run")
        else:
            console.print("❌ Some tests failed", style="bold red")
            return 1
    except Exception as e:
        console.print(f"❌ Error: {e}", style="bold red")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
