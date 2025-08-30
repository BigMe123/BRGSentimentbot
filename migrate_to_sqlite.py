#!/usr/bin/env python3
"""
Migration script to convert JSON database to SQLite
Preserves all discovered sources from the original harvester.
"""

import json
import sqlite3
import os
import sys
from pathlib import Path


def migrate_json_to_sqlite(
    json_path: str = ".stealth_harvest_db.json",
    sqlite_path: str = ".stealth_harvest.db",
):
    """Migrate from JSON database to SQLite."""

    print("🔄 Database Migration Tool")
    print("=" * 60)

    # Check if JSON file exists
    if not os.path.exists(json_path):
        print(f"❌ JSON database not found: {json_path}")
        print("Nothing to migrate.")
        return False

    # Load JSON data
    print(f"📖 Reading JSON database: {json_path}")
    try:
        with open(json_path, "r") as f:
            json_data = json.load(f)
        print(f"  ✓ Found {len(json_data)} sources")
    except Exception as e:
        print(f"❌ Failed to read JSON: {e}")
        return False

    # Check if SQLite already exists
    if os.path.exists(sqlite_path):
        response = input(
            f"\n⚠️  SQLite database already exists: {sqlite_path}\n"
            "Do you want to merge data? (y/n): "
        )
        if response.lower() != "y":
            print("Migration cancelled.")
            return False

    # Create SQLite connection
    print(f"\n💾 Creating/Opening SQLite database: {sqlite_path}")
    conn = sqlite3.connect(sqlite_path)
    cursor = conn.cursor()

    # Create tables
    print("📊 Setting up database schema...")
    cursor.executescript(
        """
        CREATE TABLE IF NOT EXISTS sources (
            domain TEXT PRIMARY KEY,
            name TEXT,
            topics TEXT,
            priority REAL,
            policy TEXT,
            region TEXT,
            rss_feeds TEXT,
            language TEXT,
            discovered_at REAL,
            protection_level TEXT,
            bypass_method TEXT,
            success_rate REAL,
            last_accessed REAL,
            fetch_strategy TEXT
        );
        
        CREATE TABLE IF NOT EXISTS request_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT,
            timestamp REAL,
            status_code INTEGER,
            success BOOLEAN,
            protection_detected TEXT,
            bypass_used TEXT
        );
        
        CREATE TABLE IF NOT EXISTS cookies (
            domain TEXT PRIMARY KEY,
            cookies TEXT,
            updated_at REAL
        );
        
        CREATE INDEX IF NOT EXISTS idx_sources_protection ON sources(protection_level);
        CREATE INDEX IF NOT EXISTS idx_sources_priority ON sources(priority);
        CREATE INDEX IF NOT EXISTS idx_history_timestamp ON request_history(timestamp);
    """
    )

    # Migrate sources
    print("\n🚀 Migrating sources...")
    migrated = 0
    skipped = 0

    for domain, record in json_data.items():
        try:
            # Determine fetch strategy based on protection level
            protection = record.get("protection_level", "none")
            fetch_strategy = (
                "browser" if protection in ["advanced", "fortress"] else "requests"
            )

            cursor.execute(
                """
                INSERT OR REPLACE INTO sources VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    record.get("domain", domain),
                    record.get("name", ""),
                    json.dumps(record.get("topics", [])),
                    record.get("priority", 0.5),
                    record.get("policy", "allow"),
                    record.get("region", "unknown"),
                    json.dumps(record.get("rss_feeds", [])),
                    record.get("language", "en"),
                    record.get("discovered_at"),
                    record.get("protection_level", "none"),
                    record.get("bypass_method", ""),
                    record.get("success_rate", 0.0),
                    record.get("discovered_at"),  # Use discovered_at as last_accessed
                    fetch_strategy,
                ),
            )
            migrated += 1

            # Show progress
            if migrated % 10 == 0:
                print(f"  ✓ Migrated {migrated} sources...")

        except Exception as e:
            print(f"  ⚠️  Failed to migrate {domain}: {e}")
            skipped += 1

    # Commit changes
    conn.commit()
    conn.close()

    print("\n" + "=" * 60)
    print("✅ Migration Complete!")
    print(f"  • Migrated: {migrated} sources")
    if skipped > 0:
        print(f"  • Skipped: {skipped} sources (errors)")
    print(f"  • SQLite database: {sqlite_path}")

    # Backup JSON file
    backup_path = json_path + ".backup"
    print(f"\n📦 Creating backup: {backup_path}")
    os.rename(json_path, backup_path)
    print("  ✓ Original JSON backed up")

    print("\n💡 Next Steps:")
    print("1. Use the enhanced harvester with SQLite:")
    print(
        "   python -m sentiment_bot.stealth_harvester_enhanced --seeds your_seeds.txt"
    )
    print("\n2. Query the database directly:")
    print(f"   sqlite3 {sqlite_path}")
    print("   > SELECT domain, protection_level FROM sources WHERE priority > 0.7;")
    print("\n3. Restore from backup if needed:")
    print(f"   mv {backup_path} {json_path}")

    return True


def show_statistics(sqlite_path: str = ".stealth_harvest.db"):
    """Show statistics from the SQLite database."""

    if not os.path.exists(sqlite_path):
        print(f"❌ Database not found: {sqlite_path}")
        return

    conn = sqlite3.connect(sqlite_path)
    cursor = conn.cursor()

    print("\n📊 Database Statistics")
    print("=" * 60)

    # Total sources
    cursor.execute("SELECT COUNT(*) FROM sources")
    total = cursor.fetchone()[0]
    print(f"Total sources: {total}")

    # By protection level
    print("\nBy Protection Level:")
    cursor.execute(
        """
        SELECT protection_level, COUNT(*) 
        FROM sources 
        GROUP BY protection_level 
        ORDER BY COUNT(*) DESC
    """
    )
    for level, count in cursor.fetchall():
        print(f"  • {level or 'none'}: {count}")

    # By region
    print("\nBy Region:")
    cursor.execute(
        """
        SELECT region, COUNT(*) 
        FROM sources 
        GROUP BY region 
        ORDER BY COUNT(*) DESC
    """
    )
    for region, count in cursor.fetchall():
        print(f"  • {region}: {count}")

    # Top priority sources
    print("\nTop 5 Priority Sources:")
    cursor.execute(
        """
        SELECT domain, name, priority, protection_level 
        FROM sources 
        ORDER BY priority DESC 
        LIMIT 5
    """
    )
    for i, (domain, name, priority, protection) in enumerate(cursor.fetchall(), 1):
        print(f"  {i}. {domain} ({priority:.2f}) - {protection}")

    # Sources with RSS feeds
    cursor.execute(
        """
        SELECT COUNT(*) 
        FROM sources 
        WHERE rss_feeds != '[]'
    """
    )
    rss_count = cursor.fetchone()[0]
    print(f"\nSources with RSS feeds: {rss_count}/{total} ({100*rss_count/total:.1f}%)")

    conn.close()


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Migrate JSON database to SQLite")
    parser.add_argument(
        "--json", default=".stealth_harvest_db.json", help="Path to JSON database"
    )
    parser.add_argument(
        "--sqlite", default=".stealth_harvest.db", help="Path to SQLite database"
    )
    parser.add_argument(
        "--stats", action="store_true", help="Show statistics after migration"
    )

    args = parser.parse_args()

    success = migrate_json_to_sqlite(args.json, args.sqlite)

    if success and args.stats:
        show_statistics(args.sqlite)


if __name__ == "__main__":
    main()
