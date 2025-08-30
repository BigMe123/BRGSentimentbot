#!/usr/bin/env python3
"""
Batch harvest sources with progress tracking
"""

import asyncio
import sys
import time
from sentiment_bot.stealth_harvester import StealthHarvester


async def batch_harvest(seeds_file: str, output_file: str, batch_size: int = 5):
    """Harvest sources in batches with progress tracking"""

    # Load domains
    domains = []
    with open(seeds_file, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                if line.startswith("- "):
                    line = line[2:].strip()
                domains.append(line)

    print(f"📊 BATCH HARVESTING {len(domains)} DOMAINS")
    print("=" * 50)

    harvester = StealthHarvester(db_path=f"{output_file}.db.json")

    # Reduce delays for batch processing
    harvester._original_smart_delay = harvester._smart_delay

    async def faster_delay(base_delay: float = 1.0, jitter: float = 0.5):
        """Faster delays for batch processing"""
        await asyncio.sleep(base_delay + random.uniform(-jitter, jitter))

    import random

    harvester._smart_delay = faster_delay

    successful = 0
    failed = 0
    start_time = time.time()

    for i, domain in enumerate(domains, 1):
        print(f"\n[{i}/{len(domains)}] Processing {domain}...")

        try:
            record = await harvester.discover_from_domain(domain)
            if record:
                successful += 1
                status = f"✅ {record.protection_level} protection"
                if record.rss_feeds:
                    status += f", {len(record.rss_feeds)} feeds"
            else:
                failed += 1
                status = "❌ Failed"
        except Exception as e:
            failed += 1
            status = f"⚠️ Error: {str(e)[:30]}"

        print(f"  {status}")

        # Progress update every batch_size domains
        if i % batch_size == 0:
            elapsed = time.time() - start_time
            rate = i / elapsed
            remaining = (len(domains) - i) / rate
            print(f"\n📈 Progress: {i}/{len(domains)} ({i*100//len(domains)}%)")
            print(f"   Success rate: {successful}/{i} ({successful*100//i}%)")
            print(f"   Time elapsed: {elapsed:.0f}s")
            print(f"   Est. remaining: {remaining:.0f}s")

    # Save results
    harvester.save_db()

    # Export to YAML
    yaml_content = harvester.to_yaml()
    with open(output_file, "w") as f:
        f.write(yaml_content)

    # Final summary
    elapsed = time.time() - start_time
    print("\n" + "=" * 50)
    print("✅ HARVEST COMPLETE")
    print(f"  Total: {len(domains)} domains")
    print(f"  Successful: {successful} ({successful*100//len(domains)}%)")
    print(f"  Failed: {failed}")
    print(f"  Time: {elapsed:.0f}s ({elapsed/len(domains):.1f}s per domain)")
    print(f"  Output: {output_file}")

    await harvester.close()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python batch_harvest.py <seeds_file> <output_file>")
        sys.exit(1)

    asyncio.run(batch_harvest(sys.argv[1], sys.argv[2]))
