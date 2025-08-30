#!/usr/bin/env python3
"""
Add news sources to existing SKB catalog with proper schema
Compatible with the current SKB catalog database structure
"""

import sqlite3
import json
import time
from datetime import datetime


def add_sources_to_skb():
    """Add news sources to SKB catalog with proper schema."""

    print("🌍 Adding Global News Sources to SKB Catalog")
    print("=" * 60)

    # Connect to existing SKB catalog
    db_path = "skb_catalog.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Read global news seeds
    seeds_file = "config/global_news_seeds.txt"
    sources = []

    with open(seeds_file, "r") as f:
        current_category = "general"
        current_region = "americas"

        for line in f:
            line = line.strip()

            # Track category and region from comments
            if line.startswith("#"):
                if "US NEWS" in line:
                    current_category = "news"
                    current_region = "americas"
                elif "EUROPEAN" in line:
                    current_category = "news"
                    current_region = "europe"
                elif "ASIAN" in line:
                    current_category = "news"
                    current_region = "asia"
                elif "MIDDLE EAST" in line:
                    current_category = "news"
                    current_region = "middle_east"
                elif "AFRICA" in line:
                    current_category = "news"
                    current_region = "africa"
                elif "OCEANIA" in line:
                    current_category = "news"
                    current_region = "oceania"
                elif "LATIN AMERICA" in line:
                    current_category = "news"
                    current_region = "latam"
                elif "CANADA" in line:
                    current_category = "news"
                    current_region = "americas"
                elif "Tech" in line or "Technology" in line:
                    current_category = "tech"
                elif "Financial" in line or "Business" in line:
                    current_category = "business"
                elif "Science" in line:
                    current_category = "science"
                elif "Defense" in line or "Security" in line:
                    current_category = "security"
                elif "Alternative" in line:
                    current_category = "alternative"
                elif "Crypto" in line:
                    current_category = "crypto"
                continue

            if not line:
                continue

            # Determine country from domain
            country = "US"  # Default
            domain_lower = line.lower()

            if domain_lower.endswith(".uk"):
                country = "UK"
            elif domain_lower.endswith(".ca"):
                country = "Canada"
            elif domain_lower.endswith(".au"):
                country = "Australia"
            elif domain_lower.endswith(".nz"):
                country = "New Zealand"
            elif domain_lower.endswith(".de"):
                country = "Germany"
            elif domain_lower.endswith(".fr"):
                country = "France"
            elif domain_lower.endswith(".it"):
                country = "Italy"
            elif domain_lower.endswith(".es"):
                country = "Spain"
            elif domain_lower.endswith(".nl"):
                country = "Netherlands"
            elif domain_lower.endswith(".be"):
                country = "Belgium"
            elif domain_lower.endswith(".ch"):
                country = "Switzerland"
            elif domain_lower.endswith(".at"):
                country = "Austria"
            elif domain_lower.endswith(".se"):
                country = "Sweden"
            elif domain_lower.endswith(".no"):
                country = "Norway"
            elif domain_lower.endswith(".dk"):
                country = "Denmark"
            elif domain_lower.endswith(".fi"):
                country = "Finland"
            elif domain_lower.endswith(".pl"):
                country = "Poland"
            elif domain_lower.endswith(".cz"):
                country = "Czech Republic"
            elif domain_lower.endswith(".hu"):
                country = "Hungary"
            elif domain_lower.endswith(".ru"):
                country = "Russia"
            elif domain_lower.endswith(".cn"):
                country = "China"
            elif domain_lower.endswith(".jp"):
                country = "Japan"
            elif domain_lower.endswith(".kr"):
                country = "South Korea"
            elif domain_lower.endswith(".in"):
                country = "India"
            elif domain_lower.endswith(".sg"):
                country = "Singapore"
            elif domain_lower.endswith(".my"):
                country = "Malaysia"
            elif domain_lower.endswith(".th"):
                country = "Thailand"
            elif domain_lower.endswith(".id"):
                country = "Indonesia"
            elif domain_lower.endswith(".ph"):
                country = "Philippines"
            elif domain_lower.endswith(".vn"):
                country = "Vietnam"
            elif domain_lower.endswith(".tw"):
                country = "Taiwan"
            elif domain_lower.endswith(".hk"):
                country = "Hong Kong"
            elif domain_lower.endswith(".il"):
                country = "Israel"
            elif domain_lower.endswith(".ae"):
                country = "UAE"
            elif domain_lower.endswith(".sa"):
                country = "Saudi Arabia"
            elif domain_lower.endswith(".eg"):
                country = "Egypt"
            elif domain_lower.endswith(".za"):
                country = "South Africa"
            elif domain_lower.endswith(".ng"):
                country = "Nigeria"
            elif domain_lower.endswith(".ke"):
                country = "Kenya"
            elif domain_lower.endswith(".br"):
                country = "Brazil"
            elif domain_lower.endswith(".mx"):
                country = "Mexico"
            elif domain_lower.endswith(".ar"):
                country = "Argentina"
            elif domain_lower.endswith(".cl"):
                country = "Chile"
            elif domain_lower.endswith(".co"):
                country = "Colombia"
            elif domain_lower.endswith(".pe"):
                country = "Peru"
            elif domain_lower.endswith(".ve"):
                country = "Venezuela"
            elif domain_lower.endswith(".uy"):
                country = "Uruguay"
            elif domain_lower.endswith(".py"):
                country = "Paraguay"
            elif domain_lower.endswith(".ec"):
                country = "Ecuador"
            else:
                # Try to infer from known domains
                if "bbc" in domain_lower:
                    country = "UK"
                elif any(
                    x in domain_lower
                    for x in ["cnn", "fox", "nbc", "abc", "cbs", "npr", "pbs"]
                ):
                    country = "US"
                elif "cbc" in domain_lower:
                    country = "Canada"
                elif "abc.net.au" in domain_lower:
                    country = "Australia"
                elif "aljazeera" in domain_lower:
                    country = "Qatar"
                elif "rt.com" in domain_lower or "tass" in domain_lower:
                    country = "Russia"
                elif "xinhua" in domain_lower or "cgtn" in domain_lower:
                    country = "China"
                elif "nhk" in domain_lower:
                    country = "Japan"
                elif "france24" in domain_lower:
                    country = "France"
                elif "dw.com" in domain_lower:
                    country = "Germany"

            sources.append(
                {
                    "domain": line,
                    "category": current_category,
                    "region": current_region,
                    "country": country,
                }
            )

    print(f"📊 Found {len(sources)} news sources to add")

    # Process sources
    added = 0
    updated = 0
    skipped = 0

    for source in sources:
        domain = source["domain"]
        domain_lower = domain.lower()

        # Create name from domain
        name = domain.replace(".com", "").replace(".org", "").replace(".net", "")
        name = name.replace(".co.uk", "").replace(".co.", "").replace(".", " ").strip()
        name = name.title()

        # Determine topics
        topics = []
        if source["category"] == "tech" or any(
            x in domain_lower for x in ["tech", "wired", "verge"]
        ):
            topics.append("technology")
        if source["category"] == "business" or any(
            x in domain_lower for x in ["business", "finance", "forbes", "bloomberg"]
        ):
            topics.append("economy")
        if any(x in domain_lower for x in ["politic", "thehill"]):
            topics.append("politics")
        if source["category"] == "security" or any(
            x in domain_lower for x in ["defense", "military"]
        ):
            topics.append("security")
        if source["category"] == "science" or any(
            x in domain_lower for x in ["science", "nature"]
        ):
            topics.append("science")
        if source["category"] == "crypto" or any(
            x in domain_lower for x in ["crypto", "bitcoin"]
        ):
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
            "nature.com",
            "sciencemag.org",
            "un.org",
            "who.int",
        ]
        if any(t in domain_lower for t in trusted):
            priority += 0.3

        # Boost major networks
        if any(x in domain_lower for x in ["cnn", "fox", "nbc", "abc", "cbs"]):
            priority += 0.2

        # Boost by category
        if source["category"] in ["business", "tech", "science"]:
            priority += 0.1

        priority = min(0.95, priority)

        # Create data JSON
        data = {
            "topics": topics,
            "category": source["category"],
            "language": "en",  # Default to English
            "type": "news",
            "subtype": source["category"],
            "rss_feeds": [],  # Will be populated by harvester
            "last_crawled": None,
            "crawl_frequency": "daily",
        }

        # Adjust language for non-English sources
        if source["country"] in ["France", "Belgium", "Switzerland"] and any(
            x in domain for x in [".fr", "france"]
        ):
            data["language"] = "fr"
        elif source["country"] in ["Germany", "Austria", "Switzerland"] and any(
            x in domain for x in [".de", "german"]
        ):
            data["language"] = "de"
        elif source["country"] in ["Spain", "Mexico", "Argentina", "Colombia"] and any(
            x in domain for x in [".es", ".mx", ".ar"]
        ):
            data["language"] = "es"
        elif source["country"] in ["Italy"] and ".it" in domain:
            data["language"] = "it"
        elif source["country"] in ["Netherlands"] and ".nl" in domain:
            data["language"] = "nl"
        elif source["country"] in ["Portugal", "Brazil"] and any(
            x in domain for x in [".pt", ".br"]
        ):
            data["language"] = "pt"
        elif source["country"] in ["Russia"] and ".ru" in domain:
            data["language"] = "ru"
        elif source["country"] in ["China"] and ".cn" in domain:
            data["language"] = "zh"
        elif source["country"] in ["Japan"] and ".jp" in domain:
            data["language"] = "ja"
        elif source["country"] in ["South Korea"] and ".kr" in domain:
            data["language"] = "ko"
        elif source["country"] in ["India"] and ".in" in domain:
            data["language"] = "hi"  # Could also be 'en'

        # Calculate scores
        reliability_score = 0.5
        if any(t in domain_lower for t in trusted):
            reliability_score = 0.9
        elif any(x in domain_lower for x in ["cnn", "fox", "nbc", "abc", "cbs"]):
            reliability_score = 0.8
        elif source["category"] in ["alternative"]:
            reliability_score = 0.4

        freshness_score = 0.7  # Most news sites update frequently
        if source["category"] in ["tech", "crypto"]:
            freshness_score = 0.9  # Tech news changes rapidly

        # Insert or update
        try:
            cursor.execute(
                """
                INSERT INTO sources (
                    domain, name, region, country, data, priority,
                    policy, historical_yield, freshness_score,
                    reliability_score, validation_status, last_updated
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    domain,
                    name,
                    source["region"],
                    source["country"],
                    json.dumps(data),
                    priority,
                    "allow",
                    0.0,  # historical_yield
                    freshness_score,
                    reliability_score,
                    "active",
                    datetime.now().isoformat(),
                ),
            )
            added += 1

            if added % 50 == 0:
                print(f"  ✓ Added {added} sources...")
                conn.commit()

        except sqlite3.IntegrityError:
            # Already exists, update it
            try:
                cursor.execute(
                    """
                    UPDATE sources 
                    SET name = ?, region = ?, country = ?, data = ?,
                        priority = ?, freshness_score = ?, reliability_score = ?,
                        last_updated = ?
                    WHERE domain = ?
                """,
                    (
                        name,
                        source["region"],
                        source["country"],
                        json.dumps(data),
                        priority,
                        freshness_score,
                        reliability_score,
                        datetime.now().isoformat(),
                        domain,
                    ),
                )
                updated += 1
            except Exception as e:
                print(f"  ⚠️  Failed to update {domain}: {e}")
                skipped += 1
        except Exception as e:
            print(f"  ⚠️  Failed to add {domain}: {e}")
            skipped += 1

    # Final commit
    conn.commit()

    print("\n" + "=" * 60)
    print("✅ SKB Catalog Update Complete!")
    print(f"  • Added: {added} new sources")
    print(f"  • Updated: {updated} existing sources")
    print(f"  • Skipped: {skipped} sources")

    # Query statistics
    cursor.execute("SELECT COUNT(*) FROM sources")
    total = cursor.fetchone()[0]
    print(f"  • Total sources in catalog: {total}")

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

    # Country breakdown (top 20)
    print("\n🏳️ Top 20 Countries by Source Count:")
    cursor.execute(
        """
        SELECT country, COUNT(*) as count
        FROM sources
        GROUP BY country
        ORDER BY count DESC
        LIMIT 20
    """
    )
    for i, (country, count) in enumerate(cursor.fetchall(), 1):
        print(f"  {i:2}. {country:20} {count:3} sources")

    # Top priority sources
    print("\n⭐ Top 20 High-Priority Sources:")
    cursor.execute(
        """
        SELECT domain, name, priority, region, country
        FROM sources
        ORDER BY priority DESC
        LIMIT 20
    """
    )
    for i, (domain, name, priority, region, country) in enumerate(cursor.fetchall(), 1):
        print(f"  {i:2}. {domain:30} ({priority:.2f}) - {country}")

    # Validation status
    print("\n📊 Validation Status:")
    cursor.execute(
        """
        SELECT validation_status, COUNT(*) as count
        FROM sources
        GROUP BY validation_status
    """
    )
    for status, count in cursor.fetchall():
        print(f"  • {status:10} {count:4} sources")

    conn.close()

    print("\n✅ Successfully added global news sources to SKB catalog!")
    print(f"📊 Database: {db_path}")
    print("\n💡 Next steps:")
    print("1. Run the stealth harvester to discover RSS feeds:")
    print("   python harvest_global_news.py")
    print("2. Or use the enhanced harvester for specific sources:")
    print(
        "   python -m sentiment_bot.stealth_harvester_enhanced --seeds config/global_news_seeds.txt"
    )


if __name__ == "__main__":
    add_sources_to_skb()
