#!/usr/bin/env python3
"""Update RSS feeds for major news sources."""

import sqlite3
import json

# Working RSS feeds for major sources
RSS_UPDATES = {
    "bbc.com": ["https://feeds.bbci.co.uk/news/rss.xml"],
    "theguardian.com": ["https://www.theguardian.com/world/rss"],
    "www.dw.com": ["https://rss.dw.com/rdf/rss-en-all"],
    "reuters.com": ["https://feeds.reuters.com/reuters/topNews"],
    "independent.co.uk": ["https://www.independent.co.uk/rss"],
    "telegraph.co.uk": ["https://www.telegraph.co.uk/rss.xml"],
    "news.sky.com": ["https://feeds.skynews.com/feeds/rss/home.xml"],
    "ft.com": ["https://www.ft.com/?format=rss"],
    "economist.com": ["https://www.economist.com/feeds/print-sections/77/business.xml"],
}

def update_rss_feeds():
    """Update RSS feeds in the database."""
    conn = sqlite3.connect('skb_catalog.db')
    cursor = conn.cursor()
    
    for domain, rss_endpoints in RSS_UPDATES.items():
        # Get current data
        cursor.execute("SELECT data FROM sources WHERE domain = ?", (domain,))
        row = cursor.fetchone()
        
        if row:
            data = json.loads(row[0])
            data['rss_endpoints'] = rss_endpoints
            
            # Update the record
            cursor.execute(
                "UPDATE sources SET data = ? WHERE domain = ?",
                (json.dumps(data), domain)
            )
            print(f"Updated {domain} with RSS: {rss_endpoints}")
    
    conn.commit()
    conn.close()
    print("RSS feeds updated successfully")

if __name__ == "__main__":
    update_rss_feeds()