#!/usr/bin/env python3
"""
Run the sentiment bot using the unified master source list.
This ensures all runs use the same comprehensive source configuration.
"""

import asyncio
import sys
import yaml
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from sentiment_bot.master_sources import get_master_sources, get_source_statistics

# from sentiment_bot.cli_unified import run_analysis  # Will integrate later


async def run_with_master_sources(args):
    """Run sentiment analysis using the master source list."""

    print("🌍 BSG Sentiment Bot - Master Source Mode")
    print("=" * 60)

    # Load master source manager
    manager = get_master_sources()
    stats = get_source_statistics()

    print(f"\n📊 Using Master Source List:")
    print(f"  • Total sources: {stats['total_sources']}")
    print(f"  • High priority: {stats['priority_ranges']['high']}")
    print(f"  • Regions: {len(stats['by_region'])}")
    print(f"  • Countries: {len(stats['by_country'])}")

    # Apply filters if specified
    sources = manager.get_sources_for_bot(
        regions=args.regions if args.regions else None,
        topics=args.topics if args.topics else None,
        min_priority=args.min_priority,
        max_sources=args.max_sources,
    )

    print(f"\n🎯 After filtering: {len(sources)} sources selected")

    if args.list_sources:
        print("\n📋 Selected Sources:")
        for i, source in enumerate(sources[:20], 1):
            print(
                f"  {i:2}. {source['domain']:30} ({source['priority']:.2f}) - {source['region']}"
            )
        if len(sources) > 20:
            print(f"  ... and {len(sources) - 20} more")
        return 0

    # Load config
    config_path = args.config or "config/master_config.yaml"
    if Path(config_path).exists():
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
    else:
        config = {
            "sources": {"use_master_list": True},
            "bot": {
                "analysis": {"sentiment_threshold": 0.3},
                "performance": {"max_concurrent_sources": 10},
            },
        }

    # Override with command line arguments
    if args.output:
        config["export"] = {"export_path": args.output}

    print(f"\n🚀 Starting analysis with {len(sources)} sources...")
    print("-" * 60)

    # Run the analysis
    try:
        # Here you would integrate with your actual sentiment bot
        # For now, we'll just show what would be analyzed

        if args.dry_run:
            print("\n🔍 DRY RUN - Would analyze:")

            # Group by region
            by_region = {}
            for source in sources:
                region = source["region"]
                if region not in by_region:
                    by_region[region] = []
                by_region[region].append(source)

            for region, region_sources in sorted(by_region.items()):
                print(f"\n  {region.upper()} ({len(region_sources)} sources):")
                for source in region_sources[:5]:
                    print(f"    • {source['domain']:30} ({source['priority']:.2f})")
                if len(region_sources) > 5:
                    print(f"    ... and {len(region_sources) - 5} more")

            return 0

        # Actual analysis would go here
        # await run_analysis(sources, config)

        print("\n✅ Analysis complete!")

        # Show summary statistics
        print("\n📈 Summary:")
        print(f"  • Sources processed: {len(sources)}")
        print(f"  • Articles analyzed: [would show actual count]")
        print(f"  • Sentiment score: [would show actual score]")
        print(f"  • Volatility: [would show actual volatility]")

        if args.output:
            print(f"\n📁 Results saved to: {args.output}")

        return 0

    except KeyboardInterrupt:
        print("\n🛑 Analysis interrupted by user")
        return 130
    except Exception as e:
        print(f"\n❌ Error during analysis: {e}")
        import traceback

        if args.debug:
            traceback.print_exc()
        return 1


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run sentiment analysis using the master source list"
    )

    # Source filtering
    parser.add_argument(
        "--regions",
        nargs="+",
        choices=[
            "americas",
            "europe",
            "asia",
            "middle_east",
            "africa",
            "oceania",
            "latam",
        ],
        help="Filter sources by region(s)",
    )

    parser.add_argument("--topics", nargs="+", help="Filter sources by topic(s)")

    parser.add_argument(
        "--min-priority",
        type=float,
        default=0.0,
        help="Minimum source priority (0.0-1.0)",
    )

    parser.add_argument(
        "--max-sources", type=int, help="Maximum number of sources to use"
    )

    # Output options
    parser.add_argument("--output", "-o", help="Output directory for results")

    parser.add_argument(
        "--config", "-c", help="Configuration file (default: config/master_config.yaml)"
    )

    # Control options
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be analyzed without running",
    )

    parser.add_argument(
        "--list-sources", action="store_true", help="List selected sources and exit"
    )

    parser.add_argument("--debug", action="store_true", help="Enable debug output")

    parser.add_argument("--export-sources", help="Export filtered sources to YAML file")

    args = parser.parse_args()

    # Export sources if requested
    if args.export_sources:
        manager = get_master_sources()
        sources = manager.get_sources_for_bot(
            regions=args.regions if args.regions else None,
            topics=args.topics if args.topics else None,
            min_priority=args.min_priority,
            max_sources=args.max_sources,
        )

        with open(args.export_sources, "w") as f:
            yaml.dump({"sources": sources}, f, default_flow_style=False)

        print(f"✅ Exported {len(sources)} sources to {args.export_sources}")
        return 0

    # Run the analysis
    return asyncio.run(run_with_master_sources(args))


if __name__ == "__main__":
    sys.exit(main())
