#!/usr/bin/env python3
"""
Script to integrate RSS registry into the SKB catalog.
This adds all the curated RSS feeds to your existing catalog.
"""

import yaml
import sqlite3
from pathlib import Path

# Load RSS registry
registry_path = Path("config/rss_registry.yaml")
with open(registry_path) as f:
    RSS_REGISTRY = yaml.safe_load(f)

# Connect to SKB catalog
db_path = Path("skb_catalog.db")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Add sources from registry
added = 0
updated = 0

for region, sources in RSS_REGISTRY.items():
    if region == "global":
        continue  # Handle global sources separately

    for domain, info in sources.items():
        # Check if source exists
        cursor.execute("SELECT domain, data FROM sources WHERE domain = ?", (domain,))
        existing = cursor.fetchone()

        if existing:
            # Update the JSON data with RSS endpoints
            import json

            data = json.loads(existing[1]) if existing[1] else {}

            # Update RSS endpoints in data
            data["rss_endpoints"] = info.get("rss_endpoints", [])
            data["editorial_family"] = info.get("editorial_family", "broadsheet")
            data["languages"] = info.get("languages", ["en"])

            # Update topics
            existing_topics = data.get("topics", [])
            new_topics = info.get("topics", [])

            # Add elections for political sources
            if any(t in ["politics", "general"] for t in new_topics):
                new_topics.append("elections")

            # Merge topics
            all_topics = list(set(existing_topics + new_topics))
            data["topics"] = all_topics

            # Update the source
            cursor.execute(
                "UPDATE sources SET data = ?, last_updated = CURRENT_TIMESTAMP WHERE domain = ?",
                (json.dumps(data), domain),
            )

            updated += 1
        else:
            # Insert new source
            import json

            editorial_family = info.get("editorial_family", "broadsheet")
            languages = info.get("languages", ["en"])
            topics = info.get("topics", ["general"])

            # Add elections for political sources
            if any(t in ["politics", "general"] for t in topics):
                topics.append("elections")

            # Create data JSON
            data = {
                "rss_endpoints": info.get("rss_endpoints", []),
                "topics": list(set(topics)),
                "editorial_family": editorial_family,
                "languages": languages,
                "metadata": {"from_registry": True},
            }

            name = (
                domain.replace("www.", "")
                .replace(".com", "")
                .replace(".co.uk", "")
                .replace(".org", "")
                .title()
            )

            cursor.execute(
                """
                INSERT INTO sources (
                    domain, name, region, policy, priority, data, validation_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    domain,
                    name,
                    region,
                    "allow",
                    0.7,  # Default priority
                    json.dumps(data),
                    "active",
                ),
            )

            added += 1

# Add global sources for backfill
import json

for domain, info in RSS_REGISTRY.get("global", {}).items():
    cursor.execute("SELECT domain FROM sources WHERE domain = ?", (domain,))
    if not cursor.fetchone():
        # Create data JSON for global source
        data = {
            "rss_endpoints": info.get("rss_endpoints", []),
            "topics": [
                "general",
                "politics",
                "economy",
                "elections",
                "security",
                "climate",
                "tech",
            ],
            "editorial_family": info.get("editorial_family", "wire"),
            "languages": info.get("languages", ["en"]),
            "metadata": {"from_registry": True, "is_global": True},
        }

        name = (
            domain.replace("www.", "").replace(".com", "").replace(".org", "").title()
        )

        cursor.execute(
            """
            INSERT INTO sources (
                domain, name, region, policy, priority, data, validation_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                domain,
                name,
                "global",
                "allow",
                0.8,  # Higher priority for global sources
                json.dumps(data),
                "active",
            ),
        )

        added += 1

# Commit changes
conn.commit()

print(f"✅ RSS Registry Integration Complete")
print(f"   Added: {added} new sources")
print(f"   Updated: {updated} existing sources")

# Show stats
cursor.execute("SELECT COUNT(*) FROM sources WHERE validation_status = 'active'")
total = cursor.fetchone()[0]

# Count sources with elections topic in their JSON data
cursor.execute(
    """
    SELECT COUNT(*) 
    FROM sources 
    WHERE validation_status = 'active' 
    AND json_extract(data, '$.topics') LIKE '%elections%'
"""
)
elections = cursor.fetchone()[0]

# Count sources with RSS endpoints
cursor.execute(
    """
    SELECT COUNT(*)
    FROM sources
    WHERE validation_status = 'active'
    AND json_array_length(json_extract(data, '$.rss_endpoints')) > 0
"""
)
with_rss = cursor.fetchone()[0]

print(f"\n📊 Catalog Stats:")
print(f"   Total active sources: {total}")
print(f"   Sources for elections: {elections}")
print(f"   Sources with RSS feeds: {with_rss}")

conn.close()
