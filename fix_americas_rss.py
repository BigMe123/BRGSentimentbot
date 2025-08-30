#!/usr/bin/env python3
"""Fix and add RSS feeds for Americas sources."""

import sqlite3
import json

# Working RSS feeds for Americas sources
AMERICAS_RSS_UPDATES = {
    # US Sources
    "apnews.com": [],  # AP News RSS is broken, removing for now
    "cnn.com": ["http://rss.cnn.com/rss/cnn_topstories.rss"],
    "foxnews.com": ["https://moxie.foxnews.com/google-publisher/latest.xml"],
    "nytimes.com": ["https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml"],
    "washingtonpost.com": ["https://feeds.washingtonpost.com/rss/politics"],
    "wsj.com": ["https://feeds.a.dj.com/rss/RSSWorldNews.xml"],
    "usatoday.com": ["http://rssfeeds.usatoday.com/usatoday-NewsTopStories"],
    "politico.com": ["https://www.politico.com/rss/politicopicks.xml"],
    "npr.org": ["https://feeds.npr.org/1001/rss.xml"],
    "cbsnews.com": ["https://www.cbsnews.com/latest/rss/main"],
    "nbcnews.com": ["https://feeds.nbcnews.com/nbcnews/public/news"],
    "abcnews.go.com": ["https://feeds.abcnews.com/abcnews/topstories"],
    # Canada
    "cbc.ca": ["https://www.cbc.ca/cmlink/rss-topstories"],
    "globeandmail.com": [
        "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/canada/"
    ],
    # Mexico
    "eluniversal.com.mx": ["https://www.eluniversal.com.mx/rss.xml"],
    # Brazil
    "folha.uol.com.br": ["https://feeds.folha.uol.com.br/poder/rss091.xml"],
    "oglobo.globo.com": ["https://oglobo.globo.com/rss/politica/"],
}


def add_americas_sources():
    """Add new Americas sources to the database."""
    conn = sqlite3.connect("skb_catalog.db")
    cursor = conn.cursor()

    # Add new sources that don't exist
    new_sources = {
        "cnn.com": {
            "name": "CNN",
            "country": "US",
            "region": "americas",
            "languages": ["en"],
            "topics": ["politics", "general", "elections"],
            "priority": 0.85,
            "policy": "allow",
        },
        "foxnews.com": {
            "name": "Fox News",
            "country": "US",
            "region": "americas",
            "languages": ["en"],
            "topics": ["politics", "general", "elections"],
            "priority": 0.80,
            "policy": "allow",
        },
        "nytimes.com": {
            "name": "New York Times",
            "country": "US",
            "region": "americas",
            "languages": ["en"],
            "topics": ["politics", "economy", "general"],
            "priority": 0.90,
            "policy": "allow",
        },
        "washingtonpost.com": {
            "name": "Washington Post",
            "country": "US",
            "region": "americas",
            "languages": ["en"],
            "topics": ["politics", "elections", "general"],
            "priority": 0.85,
            "policy": "allow",
        },
        "politico.com": {
            "name": "Politico",
            "country": "US",
            "region": "americas",
            "languages": ["en"],
            "topics": ["politics", "elections"],
            "priority": 0.85,
            "policy": "allow",
        },
        "npr.org": {
            "name": "NPR",
            "country": "US",
            "region": "americas",
            "languages": ["en"],
            "topics": ["politics", "general", "society"],
            "priority": 0.80,
            "policy": "allow",
        },
        "cbc.ca": {
            "name": "CBC",
            "country": "CA",
            "region": "americas",
            "languages": ["en"],
            "topics": ["politics", "general", "society"],
            "priority": 0.75,
            "policy": "allow",
        },
    }

    for domain, source_data in new_sources.items():
        # Check if source exists
        cursor.execute("SELECT domain FROM sources WHERE domain = ?", (domain,))
        if not cursor.fetchone():
            # Add new source
            data = source_data.copy()
            data["domain"] = domain
            data["rss_endpoints"] = AMERICAS_RSS_UPDATES.get(domain, [])
            data["historical_yield"] = 0.0
            data["freshness_score"] = 0.5
            data["reliability_score"] = 0.5
            data["validation_status"] = "active"

            cursor.execute(
                """
                INSERT INTO sources (
                    domain, name, region, country, data, priority, 
                    policy, validation_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    domain,
                    data["name"],
                    data["region"],
                    data["country"],
                    json.dumps(data),
                    data["priority"],
                    data["policy"],
                    "active",
                ),
            )

            # Update topic index
            for topic in data["topics"]:
                cursor.execute(
                    "INSERT OR IGNORE INTO topic_index (topic, domain) VALUES (?, ?)",
                    (topic.lower(), domain),
                )

            # Update language index
            for language in data["languages"]:
                cursor.execute(
                    "INSERT OR IGNORE INTO language_index (language, domain) VALUES (?, ?)",
                    (language.lower(), domain),
                )

            print(f"Added new source: {domain}")

    conn.commit()
    conn.close()


def update_rss_feeds():
    """Update RSS feeds in the database."""
    conn = sqlite3.connect("skb_catalog.db")
    cursor = conn.cursor()

    for domain, rss_endpoints in AMERICAS_RSS_UPDATES.items():
        # Get current data
        cursor.execute("SELECT data FROM sources WHERE domain = ?", (domain,))
        row = cursor.fetchone()

        if row:
            data = json.loads(row[0])
            data["rss_endpoints"] = rss_endpoints

            # Update the record
            cursor.execute(
                "UPDATE sources SET data = ? WHERE domain = ?",
                (json.dumps(data), domain),
            )
            print(f"Updated {domain} with RSS: {rss_endpoints}")

    conn.commit()
    conn.close()
    print("RSS feeds updated successfully")


if __name__ == "__main__":
    print("Adding Americas sources...")
    add_americas_sources()
    print("\nUpdating RSS feeds...")
    update_rss_feeds()
