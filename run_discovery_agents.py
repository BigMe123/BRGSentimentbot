#!/usr/bin/env python3
"""
Discovery Agent Runner - Find New Sources and Articles
"""

import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from sentiment_bot.risk_intelligence.discovery_agents import (
    run_discovery_agent_job,
    AgentJob,
    DISCOVERY_AGENT_REGISTRY
)
from sentiment_bot.risk_intelligence.database import get_risk_db


async def demo_source_discovery():
    """Demo: Discover new sources (RSS feeds, news sites, blogs)"""
    print("\n" + "="*80)
    print("🔍 SOURCE DISCOVERY AGENT - Finding New Sources")
    print("="*80)

    topic = input("\n📋 Enter topic (or press Enter for 'cryptocurrency'): ").strip()
    if not topic:
        topic = "cryptocurrency"

    job = AgentJob(
        name='discover_crypto_sources',
        params={
            'topic': topic,
            'max_sources': 20,
            'max_depth': 2
        }
    )

    print(f"\n🎯 Topic: {topic}")
    print(f"🔍 Will search for:")
    print(f"   • RSS feeds")
    print(f"   • News sites")
    print(f"   • Blogs")
    print(f"   • Other content sources")
    print("\n" + "="*80)
    print("⏳ Exploring the web...")
    print("="*80 + "\n")

    result = await run_discovery_agent_job('discover_sources', job)

    print("\n" + "="*80)
    print("✅ DISCOVERY COMPLETE")
    print("="*80)
    print(f"Status: {result['status']}")
    print(f"🆕 New sources found: {result['signals_generated']}")
    print(f"💾 Sources saved: {result['signals_emitted']}")

    # Show discovered sources
    if result['signals_emitted'] > 0:
        db = get_risk_db()
        recent = db.get_latest_signals(limit=20, min_risk_score=0)

        print("\n" + "="*80)
        print("🆕 DISCOVERED SOURCES")
        print("="*80)

        for sig in recent[:result['signals_emitted']]:
            if sig['source'] == 'source_discovery_agent':
                print(f"\n🔸 {sig['entity']}")
                print(f"   Credibility: {sig['confidence']:.2f}")
                print(f"   Category: {sig['category']}")

                # Extract source info
                raw = sig.get('raw', {})
                if isinstance(raw, str):
                    import json
                    try:
                        raw = json.loads(raw)
                    except:
                        pass

                source_info = raw.get('source_info', {})
                print(f"   Type: {source_info.get('type', 'unknown')}")
                print(f"   URL: {source_info.get('url', 'N/A')}")
                print(f"   Has RSS: {source_info.get('has_rss', False)}")
                if source_info.get('rss_url'):
                    print(f"   RSS URL: {source_info['rss_url']}")
                print(f"   Discovery: {source_info.get('discovery_method', 'unknown')}")

    return result


async def demo_article_spider():
    """Demo: Spider websites to discover articles"""
    print("\n" + "="*80)
    print("🕷️ ARTICLE SPIDER AGENT - Discovering Articles")
    print("="*80)

    topic = input("\n📋 Enter topic (or press Enter for 'AI regulation'): ").strip()
    if not topic:
        topic = "AI regulation"

    # Get starting URLs
    print("\n🌐 Enter starting URLs (one per line, blank to finish):")
    print("   Examples:")
    print("   • https://www.reuters.com/technology")
    print("   • https://techcrunch.com")
    print()

    start_urls = []
    while True:
        url = input(f"   URL {len(start_urls)+1}: ").strip()
        if not url:
            break
        start_urls.append(url)

    if not start_urls:
        start_urls = [
            'https://www.reuters.com/technology',
            'https://techcrunch.com'
        ]
        print(f"\n   Using default: {start_urls}")

    job = AgentJob(
        name='spider_articles',
        params={
            'topic': topic,
            'start_urls': start_urls,
            'max_articles': 20,
            'max_depth': 3
        }
    )

    print(f"\n🎯 Topic: {topic}")
    print(f"🌐 Starting URLs: {len(start_urls)}")
    print(f"📊 Max articles: 20")
    print(f"🔗 Max depth: 3 links")
    print("\n" + "="*80)
    print("⏳ Spidering websites...")
    print("   This will:")
    print("   1. Visit each starting URL")
    print("   2. Extract articles")
    print("   3. Follow links to find more")
    print("   4. Repeat up to depth=3")
    print("="*80 + "\n")

    result = await run_discovery_agent_job('spider_articles', job)

    print("\n" + "="*80)
    print("✅ SPIDERING COMPLETE")
    print("="*80)
    print(f"Status: {result['status']}")
    print(f"📰 Articles discovered: {result['signals_generated']}")
    print(f"💾 Articles saved: {result['signals_emitted']}")

    # Show discovered articles
    if result['signals_emitted'] > 0:
        db = get_risk_db()
        recent = db.get_latest_signals(limit=20, min_risk_score=0)

        print("\n" + "="*80)
        print("📰 DISCOVERED ARTICLES")
        print("="*80)

        for sig in recent[:result['signals_emitted']]:
            if sig['source'] == 'article_spider_agent':
                # Extract article info
                raw = sig.get('raw', {})
                if isinstance(raw, str):
                    import json
                    try:
                        raw = json.loads(raw)
                    except:
                        pass

                article_info = raw.get('article_info', {})

                print(f"\n📄 {article_info.get('title', 'Untitled')[:80]}")
                print(f"   Domain: {article_info.get('domain', 'unknown')}")
                print(f"   URL: {article_info.get('url', 'N/A')[:80]}")
                print(f"   Published: {article_info.get('published', 'unknown')}")
                print(f"   Words: {article_info.get('word_count', 0)}")
                print(f"   Relevance: {sig['confidence']:.2f}")
                print(f"   Depth: {article_info.get('depth', 0)}")

    return result


async def run_all_discovery():
    """Run all discovery agents"""
    print("\n" + "🔍"*40)
    print("DISCOVERY AGENTS - Finding New Sources & Articles")
    print("🔍"*40)

    results = []

    try:
        # 1. Source Discovery
        result = await demo_source_discovery()
        results.append(('Source Discovery', result))
        await asyncio.sleep(2)

        # 2. Article Spider
        result = await demo_article_spider()
        results.append(('Article Spider', result))

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

    # Summary
    print("\n" + "="*80)
    print("📊 FINAL SUMMARY")
    print("="*80)

    total_discovered = 0
    for agent_name, result in results:
        status_icon = "✅" if result['status'] == 'success' else "❌"
        discovered = result.get('signals_emitted', 0)
        total_discovered += discovered
        print(f"{status_icon} {agent_name}: {discovered} items discovered")

    print(f"\n🆕 Total items discovered: {total_discovered}")

    # Database stats
    db = get_risk_db()
    stats = db.get_signal_stats()
    print(f"\n💾 Database Stats:")
    print(f"   Total signals: {stats['total_signals']}")
    print(f"   Discovery signals: {stats['by_source'].get('source_discovery_agent', 0) + stats['by_source'].get('article_spider_agent', 0)}")

    print("\n✨ Discovery complete!")


async def interactive_menu():
    """Interactive menu"""
    while True:
        print("\n" + "="*80)
        print("🔍 DISCOVERY AGENT RUNNER")
        print("="*80)
        print("\n1. 🔍 Discover New Sources (RSS, news sites, blogs)")
        print("2. 🕷️ Spider Articles (crawl websites)")
        print("3. 🚀 Run Both")
        print("4. 📊 View Discoveries")
        print("0. ❌ Exit")

        choice = input("\nSelect option (0-4): ").strip()

        if choice == '1':
            await demo_source_discovery()
        elif choice == '2':
            await demo_article_spider()
        elif choice == '3':
            await run_all_discovery()
        elif choice == '4':
            db = get_risk_db()

            # Show discovered sources
            print("\n📰 Discovered Sources:")
            sources = [s for s in db.get_latest_signals(limit=50)
                      if s['source'] == 'source_discovery_agent']
            for i, sig in enumerate(sources[:10], 1):
                print(f"  {i}. {sig['entity']} (credibility: {sig['confidence']:.2f})")

            # Show discovered articles
            print("\n📄 Discovered Articles:")
            articles = [s for s in db.get_latest_signals(limit=50)
                       if s['source'] == 'article_spider_agent']
            for i, sig in enumerate(articles[:10], 1):
                print(f"  {i}. {sig['title'][:60]}... (relevance: {sig['confidence']:.2f})")

        elif choice == '0':
            print("\n👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Run discovery agents')
    parser.add_argument('--all', action='store_true', help='Run all discovery agents')
    parser.add_argument('--agent', choices=list(DISCOVERY_AGENT_REGISTRY.keys()),
                       help='Run specific agent')

    args = parser.parse_args()

    if args.all:
        asyncio.run(run_all_discovery())
    elif args.agent:
        if args.agent == 'discover_sources':
            asyncio.run(demo_source_discovery())
        elif args.agent == 'spider_articles':
            asyncio.run(demo_article_spider())
    else:
        # Default: interactive
        asyncio.run(interactive_menu())
