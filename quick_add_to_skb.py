#!/usr/bin/env python3
"""
Quick script to add news sources directly to SKB catalog
This adds sources immediately without harvesting RSS feeds
"""

import sqlite3
import time
from pathlib import Path


def quick_add_to_skb():
    """Add news sources directly to SKB catalog database."""

    print("🚀 Quick SKB Catalog Updater")
    print("=" * 60)

    # Connect to SKB catalog database
    db_path = "skb_catalog.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Ensure table exists
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS sources (
            domain TEXT PRIMARY KEY,
            name TEXT,
            topics TEXT,
            priority REAL,
            policy TEXT DEFAULT 'allow',
            region TEXT,
            rss_endpoints TEXT,
            language TEXT DEFAULT 'en',
            last_updated REAL
        )
    """
    )

    # Read global news seeds
    seeds_file = "config/global_news_seeds.txt"
    domains = []

    with open(seeds_file, "r") as f:
        current_category = "general"
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                # Track category from comments
                if line.startswith("# ===") and "US NEWS" in line:
                    current_category = "us"
                elif line.startswith("# ===") and "EUROPEAN" in line:
                    current_category = "europe"
                elif line.startswith("# ===") and "ASIAN" in line:
                    current_category = "asia"
                elif line.startswith("# ===") and "MIDDLE EAST" in line:
                    current_category = "middle_east"
                elif line.startswith("# ===") and "AFRICA" in line:
                    current_category = "africa"
                elif line.startswith("# ===") and "OCEANIA" in line:
                    current_category = "oceania"
                elif line.startswith("# ===") and "LATIN" in line:
                    current_category = "latam"
                elif line.startswith("# ===") and "CANADA" in line:
                    current_category = "canada"
                elif "Tech" in line or "Technology" in line:
                    current_category = "tech"
                elif "Financial" in line or "Business" in line:
                    current_category = "business"
                elif "Alternative" in line:
                    current_category = "alternative"
                continue

            domains.append((line, current_category))

    print(f"📊 Found {len(domains)} news sources to add")

    # Categorize and prioritize
    added = 0
    updated = 0
    skipped = 0

    for domain, category in domains:
        # Determine region based on domain and category
        region = "unknown"
        if category == "us":
            region = "americas"
        elif category == "europe":
            region = "europe"
        elif category == "asia":
            region = "asia"
        elif category == "middle_east":
            region = "middle_east"
        elif category == "africa":
            region = "africa"
        elif category == "oceania":
            region = "oceania"
        elif category == "latam":
            region = "latam"
        elif category == "canada":
            region = "americas"
        else:
            # Infer from domain
            if (
                domain.endswith(".uk")
                or domain.endswith(".fr")
                or domain.endswith(".de")
            ):
                region = "europe"
            elif domain.endswith(".au") or domain.endswith(".nz"):
                region = "oceania"
            elif domain.endswith(".ca"):
                region = "americas"
            elif (
                domain.endswith(".in")
                or domain.endswith(".jp")
                or domain.endswith(".cn")
            ):
                region = "asia"
            elif domain.endswith(".za"):
                region = "africa"
            elif (
                domain.endswith(".br")
                or domain.endswith(".mx")
                or domain.endswith(".ar")
            ):
                region = "latam"

        # Determine topics based on domain and category
        topics = []
        domain_lower = domain.lower()

        if category == "tech" or any(
            x in domain_lower for x in ["tech", "wired", "verge", "ars"]
        ):
            topics.append("tech")
        if category == "business" or any(
            x in domain_lower
            for x in [
                "business",
                "finance",
                "market",
                "economic",
                "forbes",
                "bloomberg",
                "wsj",
            ]
        ):
            topics.append("economy")
        if any(x in domain_lower for x in ["politic", "thehill", "politico"]):
            topics.append("politics")
        if any(x in domain_lower for x in ["defense", "military", "security"]):
            topics.append("security")
        if any(x in domain_lower for x in ["foreign", "diplomat", "international"]):
            topics.append("diplomacy")
        if any(x in domain_lower for x in ["science", "nature", "research"]):
            topics.append("science")
        if any(x in domain_lower for x in ["health", "medical", "medicine"]):
            topics.append("health")
        if any(x in domain_lower for x in ["climate", "environment", "green"]):
            topics.append("environment")
        if any(x in domain_lower for x in ["crypto", "bitcoin", "blockchain"]):
            topics.append("crypto")

        if not topics:
            topics.append("general")

        # Calculate priority
        priority = 0.5  # Base priority

        # Boost trusted sources
        trusted = [
            "reuters",
            "apnews",
            "bbc",
            "npr",
            "pbs",
            "economist",
            "ft.com",
            "wsj",
            "nytimes",
            "washingtonpost",
            "guardian",
            "bloomberg",
        ]
        if any(t in domain_lower for t in trusted):
            priority += 0.3

        # Boost by category
        if category in ["us", "europe", "business", "tech"]:
            priority += 0.1

        # Boost major outlets
        if any(x in domain_lower for x in ["cnn", "fox", "nbc", "abc", "cbs"]):
            priority += 0.15

        priority = min(0.95, priority)  # Cap at 0.95

        # Prepare name (clean domain name)
        name = domain.replace(".com", "").replace(".org", "").replace(".net", "")
        name = name.replace(".co.uk", "").replace(".", " ").title()

        # Insert or update
        try:
            cursor.execute(
                """
                INSERT INTO sources (domain, name, topics, priority, region, last_updated)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (domain, name, ",".join(topics), priority, region, time.time()),
            )
            added += 1

            if added % 50 == 0:
                print(f"  ✓ Added {added} sources...")
                conn.commit()  # Commit periodically

        except sqlite3.IntegrityError:
            # Already exists, update it
            cursor.execute(
                """
                UPDATE sources 
                SET name = ?, topics = ?, priority = ?, region = ?, last_updated = ?
                WHERE domain = ?
            """,
                (name, ",".join(topics), priority, region, time.time(), domain),
            )
            updated += 1
        except Exception as e:
            print(f"  ⚠️  Failed to add {domain}: {e}")
            skipped += 1

    # Final commit
    conn.commit()

    # Show statistics
    print("\n" + "=" * 60)
    print("✅ SKB Catalog Update Complete!")
    print(f"  • Added: {added} new sources")
    print(f"  • Updated: {updated} existing sources")
    print(f"  • Skipped: {skipped} sources")

    # Query total count
    cursor.execute("SELECT COUNT(*) FROM sources")
    total = cursor.fetchone()[0]
    print(f"  • Total sources in catalog: {total}")

    # Show top sources by priority
    print("\n⭐ Top 20 Sources by Priority:")
    cursor.execute(
        """
        SELECT domain, name, priority, topics, region
        FROM sources
        ORDER BY priority DESC
        LIMIT 20
    """
    )

    for i, (domain, name, priority, topics, region) in enumerate(cursor.fetchall(), 1):
        print(f"  {i:2}. {domain:30} ({priority:.2f}) - {region:10} [{topics}]")

    # Regional breakdown
    print("\n🌍 Sources by Region:")
    cursor.execute(
        """
        SELECT region, COUNT(*) as count
        FROM sources
        GROUP BY region
        ORDER BY count DESC
    """
    )

    for region, count in cursor.fetchall():
        print(f"  • {region:15} {count:4} sources")

    # Close database
    conn.close()

    print("\n✅ All sources added to SKB catalog successfully!")
    print(f"📊 Database: {db_path}")

    # Create a YAML export for review
    print("\n📝 Exporting to YAML for review...")

    # Reconnect for export
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT domain, name, topics, priority, region
        FROM sources
        ORDER BY priority DESC
    """
    )

    yaml_lines = [
        "# SKB Global News Sources\n",
        "# Auto-generated catalog\n\n",
        "sources:\n",
    ]

    for domain, name, topics, priority, region in cursor.fetchall():
        topic_list = topics.split(",") if topics else ["general"]
        yaml_lines.append(f'  - domain: "{domain}"\n')
        yaml_lines.append(f'    name: "{name}"\n')
        yaml_lines.append(f"    topics: {topic_list}\n")
        yaml_lines.append(f"    priority: {priority:.2f}\n")
        yaml_lines.append(f'    region: "{region}"\n')
        yaml_lines.append("\n")

    output_file = "config/skb_sources_quick.yaml"
    with open(output_file, "w") as f:
        f.writelines(yaml_lines)

    print(f"  ✅ Exported to: {output_file}")

    conn.close()
    print("\n🎉 Quick SKB update completed!")


if __name__ == "__main__":
    quick_add_to_skb()
