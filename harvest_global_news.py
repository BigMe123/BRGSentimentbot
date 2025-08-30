#!/usr/bin/env python3
"""
Batch harvester for global news sources
Processes 660+ news sources efficiently using the enhanced stealth harvester
"""

import asyncio
import sys
import os
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sentiment_bot.stealth_harvester_enhanced import EnhancedStealthHarvester


async def harvest_global_news():
    """Harvest all global news sources with progress tracking."""

    print("🌍 Global News Harvester")
    print("=" * 70)

    # Load seeds
    seeds_file = "config/global_news_seeds.txt"
    if not os.path.exists(seeds_file):
        print(f"❌ Seeds file not found: {seeds_file}")
        return 1

    # Read domains
    domains = []
    with open(seeds_file, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                domains.append(line)

    print(f"📊 Loaded {len(domains)} news sources")
    print(f"🔧 Configuration: config/stealth_harvester_config.yaml")

    # Initialize harvester
    harvester = EnhancedStealthHarvester(
        config_path="config/stealth_harvester_config.yaml"
    )

    # Adjust for batch processing
    harvester.max_workers = 10  # Increase workers for faster processing

    print(f"⚡ Using {harvester.max_workers} concurrent workers")
    print(f"💾 Database: {harvester.db.db_path}")
    print("-" * 70)

    # Start time
    start_time = datetime.now()

    # Process in batches to show progress
    batch_size = 50
    total_batches = (len(domains) + batch_size - 1) // batch_size

    discovered = 0
    failed = 0

    for batch_num in range(total_batches):
        batch_start = batch_num * batch_size
        batch_end = min(batch_start + batch_size, len(domains))
        batch = domains[batch_start:batch_end]

        print(
            f"\n📦 Processing batch {batch_num + 1}/{total_batches} ({len(batch)} sources)"
        )
        print(f"   Sources {batch_start + 1}-{batch_end} of {len(domains)}")

        # Process batch concurrently
        await harvester.run_concurrent_harvest(batch)

        # Update statistics
        batch_discovered = 0
        batch_failed = 0
        for domain in batch:
            if harvester.db.get_source(domain):
                batch_discovered += 1
            else:
                batch_failed += 1

        discovered += batch_discovered
        failed += batch_failed

        # Show batch results
        print(f"   ✅ Discovered: {batch_discovered}/{len(batch)}")
        if batch_failed > 0:
            print(f"   ❌ Failed: {batch_failed}/{len(batch)}")

        # Show cumulative progress
        progress = (batch_end / len(domains)) * 100
        elapsed = (datetime.now() - start_time).total_seconds()
        rate = discovered / elapsed if elapsed > 0 else 0
        eta = (len(domains) - batch_end) / rate if rate > 0 else 0

        print(
            f"   📈 Overall Progress: {progress:.1f}% ({discovered}/{len(domains)} discovered)"
        )
        print(f"   ⏱️  Rate: {rate:.1f} sources/second")
        if eta > 0:
            print(f"   ⏳ ETA: {int(eta // 60)}m {int(eta % 60)}s")

    # Final statistics
    elapsed_total = (datetime.now() - start_time).total_seconds()
    print("\n" + "=" * 70)
    print("✅ Harvest Complete!")
    print("-" * 70)
    print(f"📊 Final Statistics:")
    print(f"   • Total sources: {len(domains)}")
    print(f"   • Successfully discovered: {discovered}")
    print(f"   • Failed: {failed}")
    print(f"   • Success rate: {(discovered/len(domains)*100):.1f}%")
    print(f"   • Total time: {int(elapsed_total // 60)}m {int(elapsed_total % 60)}s")
    print(f"   • Average rate: {discovered/elapsed_total:.2f} sources/second")

    # Database statistics
    all_sources = harvester.db.get_all_sources()
    sources_with_rss = [s for s in all_sources if s.rss_feeds]

    print(f"\n💾 Database Statistics:")
    print(f"   • Total sources in DB: {len(all_sources)}")
    print(f"   • Sources with RSS feeds: {len(sources_with_rss)}")

    # Protection level breakdown
    protection_levels = {}
    for source in all_sources:
        level = source.protection_level
        protection_levels[level] = protection_levels.get(level, 0) + 1

    print(f"\n🛡️  Protection Levels:")
    for level, count in sorted(
        protection_levels.items(), key=lambda x: x[1], reverse=True
    ):
        percentage = (count / len(all_sources)) * 100
        print(f"   • {level}: {count} ({percentage:.1f}%)")

    # Region breakdown
    regions = {}
    for source in all_sources:
        region = source.region
        regions[region] = regions.get(region, 0) + 1

    print(f"\n🌍 Geographic Distribution:")
    for region, count in sorted(regions.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / len(all_sources)) * 100
        print(f"   • {region}: {count} ({percentage:.1f}%)")

    # Topic analysis
    all_topics = {}
    for source in all_sources:
        for topic in source.topics:
            all_topics[topic] = all_topics.get(topic, 0) + 1

    print(f"\n📰 Topic Coverage:")
    for topic, count in sorted(all_topics.items(), key=lambda x: x[1], reverse=True)[
        :10
    ]:
        percentage = (count / len(all_sources)) * 100
        print(f"   • {topic}: {count} sources ({percentage:.1f}%)")

    # Export results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"output/global_news_sources_{timestamp}.yaml"

    print(f"\n📝 Exporting to YAML...")
    yaml_content = harvester.export_to_yaml()

    os.makedirs("output", exist_ok=True)
    with open(output_file, "w") as f:
        f.write(yaml_content)

    print(f"   ✅ Exported to: {output_file}")

    # Also create a simplified SKB format
    skb_file = f"config/skb_sources_global_{timestamp}.yaml"
    print(f"\n📋 Creating SKB-compatible source list...")

    skb_lines = [
        "# Global News Sources for SKB\n",
        "# Auto-generated from harvest\n\n",
        "sources:\n",
    ]

    # Sort by priority for SKB
    sorted_sources = sorted(all_sources, key=lambda x: x.priority, reverse=True)

    for source in sorted_sources:
        skb_lines.append(f'  - domain: "{source.domain}"\n')
        skb_lines.append(f'    name: "{source.name}"\n')
        skb_lines.append(f"    topics: {source.topics}\n")
        skb_lines.append(f"    priority: {source.priority:.2f}\n")
        skb_lines.append(f'    region: "{source.region}"\n')
        if source.rss_feeds:
            skb_lines.append(f"    rss_endpoints: {source.rss_feeds}\n")
        skb_lines.append("\n")

    with open(skb_file, "w") as f:
        f.writelines(skb_lines)

    print(f"   ✅ SKB sources saved to: {skb_file}")

    # Top recommendations
    print(f"\n⭐ Top 20 High-Priority Sources (by score):")
    for i, source in enumerate(sorted_sources[:20], 1):
        rss_indicator = "📡" if source.rss_feeds else "❌"
        print(
            f"   {i:2}. {source.domain:30} (Priority: {source.priority:.2f}) {rss_indicator}"
        )

    # Cleanup
    await harvester.close()

    print("\n" + "=" * 70)
    print("🎉 Global news harvest completed successfully!")
    print(f"📚 Added {discovered} news sources to the SKB catalog")

    return 0


async def main():
    """Main entry point."""
    try:
        return await harvest_global_news()
    except KeyboardInterrupt:
        print("\n🛑 Harvest interrupted by user")
        return 130
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
