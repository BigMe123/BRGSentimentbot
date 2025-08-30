#!/usr/bin/env python3
"""
Fix source metadata to include editorial families and RSS feeds.
"""

import sqlite3
import json
import time
from typing import Dict, List


def classify_editorial_family(domain: str, name: str) -> str:
    """Classify source into editorial family."""
    domain_lower = domain.lower()
    name_lower = name.lower() if name else ""

    # Wire services / News agencies
    wire_indicators = [
        "reuters",
        "apnews",
        "ap.org",
        "afp",
        "tass",
        "xinhua",
        "bloomberg",
        "upi",
        "ansa",
        "efe",
        "dpa",
        "kyodo",
        "associated press",
        "agence france",
        "news agency",
    ]

    # Think tanks / Research
    think_tank_indicators = [
        "brookings",
        "heritage",
        "cato",
        "rand",
        "csis",
        "cfr",
        "carnegie",
        "hoover",
        "urban",
        "aei",
        "chatham",
        "iiss",
        "wilsoncenter",
        "institute",
        "foundation",
        "research",
        "center for",
        "council on",
    ]

    # Government / Official
    government_indicators = [
        ".gov",
        "un.org",
        "who.int",
        "nato.int",
        "europa.eu",
        "worldbank",
        "imf.org",
        "wto.org",
        "unesco",
        "unicef",
    ]

    # Check for wire services
    for indicator in wire_indicators:
        if indicator in domain_lower or indicator in name_lower:
            return "wire"

    # Check for think tanks
    for indicator in think_tank_indicators:
        if indicator in domain_lower or indicator in name_lower:
            return "think_tank"

    # Check for government
    for indicator in government_indicators:
        if indicator in domain_lower:
            return "government"

    # Default to publication
    return "publication"


def get_common_rss_feeds(domain: str) -> List[str]:
    """Get common RSS feed URLs for a domain."""
    # Common RSS feed patterns
    base = f"https://{domain}"
    common_feeds = []

    # Special cases for known sources
    rss_mappings = {
        "nytimes.com": ["https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml"],
        "washingtonpost.com": ["https://feeds.washingtonpost.com/rss/world"],
        "reuters.com": ["https://www.reuters.com/rssFeed/worldNews"],
        "bbc.com": ["http://feeds.bbci.co.uk/news/rss.xml"],
        "cnn.com": ["http://rss.cnn.com/rss/cnn_topstories.rss"],
        "theguardian.com": ["https://www.theguardian.com/world/rss"],
        "wsj.com": ["https://feeds.a.dj.com/rss/RSSWorldNews.xml"],
        "bloomberg.com": ["https://feeds.bloomberg.com/politics/news.rss"],
        "ft.com": ["https://www.ft.com/?format=rss"],
        "economist.com": ["https://www.economist.com/sections/economics/rss.xml"],
        "npr.org": ["https://feeds.npr.org/1001/rss.xml"],
        "apnews.com": ["https://feeds.apnews.com/rss/apf-topnews"],
        "foxnews.com": ["http://feeds.foxnews.com/foxnews/latest"],
        "nbcnews.com": ["https://feeds.nbcnews.com/nbcnews/public/news"],
        "abcnews.go.com": ["https://abcnews.go.com/abcnews/topstories"],
        "cbsnews.com": ["https://www.cbsnews.com/latest/rss/main"],
        "aljazeera.com": ["https://www.aljazeera.com/xml/rss/all.xml"],
        "techcrunch.com": ["https://techcrunch.com/feed/"],
        "wired.com": ["https://www.wired.com/feed/rss"],
        "arstechnica.com": ["https://feeds.arstechnica.com/arstechnica/index"],
        "reddit.com": ["https://www.reddit.com/r/worldnews/.rss"],
    }

    # Check if we have specific feeds for this domain
    for key, feeds in rss_mappings.items():
        if key in domain:
            return feeds

    # Otherwise, try common patterns
    common_patterns = [
        f"{base}/rss",
        f"{base}/feed",
        f"{base}/rss.xml",
        f"{base}/feed.xml",
        f"{base}/feeds",
        f"{base}/atom.xml",
        f"{base}/index.rss",
        f"{base}/news/rss",
        f"{base}/latest/rss",
    ]

    # Return the most likely candidates
    return common_patterns[:3]


def fix_source_metadata():
    """Fix source metadata in the database."""
    print("🔧 Fixing Source Metadata")
    print("=" * 60)

    # Connect to database
    conn = sqlite3.connect("skb_catalog.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get all sources
    cursor.execute("SELECT * FROM sources")
    sources = cursor.fetchall()

    print(f"📊 Processing {len(sources)} sources...")

    updated = 0
    for source in sources:
        domain = source["domain"]
        name = source["name"]
        data = json.loads(source["data"]) if source["data"] else {}

        # Classify editorial family
        editorial_family = classify_editorial_family(domain, name)

        # Add to notes field for the selection planner
        notes = data.get("notes", "")
        if editorial_family == "wire":
            if "wire" not in notes.lower() and "agency" not in notes.lower():
                notes = f"Wire service/News agency. {notes}".strip()
        elif editorial_family == "think_tank":
            if "think" not in notes.lower():
                notes = f"Think tank/Research organization. {notes}".strip()
        elif editorial_family == "government":
            if "government" not in notes.lower() and "official" not in notes.lower():
                notes = f"Government/Official source. {notes}".strip()

        data["notes"] = notes
        data["editorial_family"] = editorial_family

        # Add RSS feeds if missing
        if not data.get("rss_endpoints") or len(data.get("rss_endpoints", [])) == 0:
            data["rss_endpoints"] = get_common_rss_feeds(domain)

        # Ensure required fields exist
        if "primary_sections" not in data:
            data["primary_sections"] = []
        if "languages" not in data:
            data["languages"] = ["en"]  # Default to English
        if "sitemap_endpoints" not in data:
            data["sitemap_endpoints"] = []

        # Update the source
        cursor.execute(
            """
            UPDATE sources 
            SET data = ?, last_updated = ?
            WHERE domain = ?
        """,
            (json.dumps(data), time.time(), domain),
        )

        updated += 1
        if updated % 50 == 0:
            print(f"  ✓ Updated {updated} sources...")
            conn.commit()

    # Final commit
    conn.commit()

    print(f"\n✅ Updated {updated} sources with metadata")

    # Show statistics
    print("\n📊 Editorial Family Distribution:")
    cursor.execute(
        """
        SELECT 
            json_extract(data, '$.editorial_family') as family,
            COUNT(*) as count
        FROM sources
        GROUP BY family
        ORDER BY count DESC
    """
    )

    for row in cursor.fetchall():
        family = row["family"] or "unclassified"
        count = row["count"]
        print(f"  • {family:15} {count:4} sources")

    # Check RSS feeds
    cursor.execute(
        """
        SELECT COUNT(*) as total,
               SUM(CASE WHEN json_array_length(json_extract(data, '$.rss_endpoints')) > 0 THEN 1 ELSE 0 END) as with_rss
        FROM sources
    """
    )

    row = cursor.fetchone()
    total = row["total"]
    with_rss = row["with_rss"] or 0

    print(f"\n📡 RSS Feed Coverage:")
    print(f"  • Total sources: {total}")
    print(f"  • With RSS feeds: {with_rss} ({100*with_rss/total:.1f}%)")

    # Show sample sources with RSS
    print("\n🔍 Sample sources with RSS feeds:")
    cursor.execute(
        """
        SELECT domain, 
               json_extract(data, '$.editorial_family') as family,
               json_extract(data, '$.rss_endpoints') as feeds
        FROM sources
        WHERE json_array_length(json_extract(data, '$.rss_endpoints')) > 0
        LIMIT 10
    """
    )

    for i, row in enumerate(cursor.fetchall(), 1):
        feeds = json.loads(row["feeds"]) if row["feeds"] else []
        print(f"  {i:2}. {row['domain']:30} ({row['family']}) - {len(feeds)} feeds")

    conn.close()

    print("\n✅ Metadata fix complete!")
    print("\n💡 Now run analysis to use the updated metadata:")
    print("  bsgbot run --region americas")
    print("  python run.py")


if __name__ == "__main__":
    fix_source_metadata()
