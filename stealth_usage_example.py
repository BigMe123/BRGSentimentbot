#!/usr/bin/env python3
"""
Example usage of the stealth harvester for your sentiment bot
"""

import asyncio
import json
from sentiment_bot.stealth_harvester import StealthHarvester


async def harvest_challenging_sources():
    """Harvest sources that typically block bots"""

    # Sources known to have anti-bot protection
    challenging_sources = [
        # News sites with protection
        "bloomberg.com",
        "wsj.com",
        "ft.com",
        "economist.com",
        # European sources
        "lemonde.fr",
        "spiegel.de",
        "elpais.com",
        # Tech news
        "techcrunch.com",
        "theverge.com",
        "arstechnica.com",
    ]

    print("🛡️ STEALTH HARVESTING CHALLENGING SOURCES")
    print("=" * 50)

    harvester = StealthHarvester(db_path="stealth_sources.json")

    # Optional: Configure proxies for IP rotation
    # with open("proxies.txt", "r") as f:
    #     harvester.proxy_config.proxies = [line.strip() for line in f]

    results = {"successful": [], "failed": [], "protected": []}

    for domain in challenging_sources:
        print(f"\n🎯 Attempting {domain}...")

        try:
            record = await harvester.discover_from_domain(domain)

            if record:
                info = {
                    "domain": domain,
                    "name": record.name,
                    "protection": record.protection_level,
                    "bypass": record.bypass_method,
                    "feeds": record.rss_feeds,
                    "success_rate": record.success_rate,
                }

                if record.protection_level in ["advanced", "fortress"]:
                    results["protected"].append(info)
                    print(f"  🛡️ Protected site accessed! ({record.protection_level})")
                else:
                    results["successful"].append(info)
                    print(f"  ✅ Successfully harvested")

                if record.rss_feeds:
                    print(f"  📡 Found {len(record.rss_feeds)} RSS feeds")

            else:
                results["failed"].append(domain)
                print(f"  ❌ Failed to access")

        except Exception as e:
            results["failed"].append(domain)
            print(f"  ⚠️ Error: {str(e)[:50]}...")

    # Save results
    harvester.save_db()

    # Export to YAML for sentiment bot
    yaml_content = harvester.to_yaml()
    with open("config/stealth_sources.yaml", "w") as f:
        f.write(yaml_content)

    # Print summary
    print("\n" + "=" * 50)
    print("📊 HARVEST SUMMARY")
    print("=" * 50)
    print(f"✅ Successful: {len(results['successful'])} sites")
    print(f"🛡️ Protected but accessed: {len(results['protected'])} sites")
    print(f"❌ Failed: {len(results['failed'])} sites")

    if results["protected"]:
        print("\n🏆 DEFEATED PROTECTIONS:")
        for site in results["protected"]:
            print(f"  - {site['domain']}: {site['protection']} ({site['bypass']})")

    # Save detailed results
    with open("harvest_results.json", "w") as f:
        json.dump(results, f, indent=2)

    await harvester.close()

    return results


async def integrate_with_sentiment_bot():
    """Example of integrating stealth sources with sentiment bot"""

    print("\n🤖 INTEGRATING WITH SENTIMENT BOT")
    print("=" * 50)

    # First harvest with stealth
    harvester = StealthHarvester(db_path="integrated_sources.json")

    # Discover a protected source
    domain = "bloomberg.com"
    record = await harvester.discover_from_domain(domain)

    if record and record.rss_feeds:
        print(f"✅ Found {len(record.rss_feeds)} feeds from {domain}")

        # Create source config for sentiment bot
        source_config = {
            "domain": record.domain,
            "name": record.name,
            "topics": record.topics,
            "priority": record.priority,
            "rss_endpoints": record.rss_feeds,
            "stealth_required": record.protection_level != "none",
            "bypass_method": record.bypass_method,
        }

        print("\n📝 Source configuration for sentiment bot:")
        print(json.dumps(source_config, indent=2))

        # Now you can use this with sentiment bot
        print("\n🚀 To use with sentiment bot:")
        print(
            "python -m sentiment_bot.cli_unified run --sources integrated_sources.json"
        )

    await harvester.close()


async def test_specific_site(domain: str):
    """Test a specific site with detailed output"""

    print(f"\n🔬 DETAILED TEST: {domain}")
    print("=" * 50)

    harvester = StealthHarvester(db_path=f".test_{domain.replace('.', '_')}.json")

    # Enable verbose output
    record = await harvester.discover_from_domain(domain)

    if record:
        print(f"\n✅ SUCCESSFULLY ACCESSED {domain}")
        print(f"  Name: {record.name}")
        print(f"  Protection: {record.protection_level}")
        print(f"  Bypass: {record.bypass_method or 'none'}")
        print(f"  Success Rate: {record.success_rate:.0%}")
        print(f"  Topics: {', '.join(record.topics)}")
        print(f"  Region: {record.region}")

        if record.rss_feeds:
            print(f"\n📡 RSS FEEDS FOUND:")
            for feed in record.rss_feeds:
                print(f"  - {feed}")
        else:
            print("\n⚠️ No RSS feeds found")

    else:
        print(f"\n❌ FAILED TO ACCESS {domain}")
        print("  Try using browser mode or adding proxies")

    await harvester.close()


def main():
    """Main entry point"""
    import sys

    if len(sys.argv) > 1:
        # Test specific site
        domain = sys.argv[1]
        asyncio.run(test_specific_site(domain))
    else:
        # Run full harvest
        asyncio.run(harvest_challenging_sources())
        # asyncio.run(integrate_with_sentiment_bot())


if __name__ == "__main__":
    main()
