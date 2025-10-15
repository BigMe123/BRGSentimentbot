#!/usr/bin/env python3
"""
Live AI Agent Runner - Agents that actively scrape the internet
"""

import asyncio
import sys
import os
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sentiment_bot.risk_intelligence.live_agents import (
    run_live_agent_job,
    AgentJob,
    LIVE_AGENT_REGISTRY
)
from sentiment_bot.risk_intelligence.database import get_risk_db


async def demo_live_query_agent():
    """Demo: Live Query Agent - Scrapes Internet for Signals"""
    print("\n" + "="*80)
    print("🌐 LIVE QUERY AGENT - Actively Scouring the Internet")
    print("="*80)

    # Choose your topic!
    topic = input("\n🔍 Enter topic to search (or press Enter for 'cryptocurrency regulation'): ").strip()
    if not topic:
        topic = "cryptocurrency regulation Bitcoin"

    job = AgentJob(
        name='live_internet_scan',
        params={
            'topic': topic,
            'sources': ['news', 'web'],  # Scrape news + web search
            'max_leads': 5,              # Generate 5 signals
            'max_articles': 50,          # Fetch 50 articles from internet
            'signal_type': 'all'         # Both weak and strong
        },
        entities=['Bitcoin', 'Ethereum', 'SEC', 'USA', 'EU']
    )

    print(f"\n📋 Job: {job.name}")
    print(f"🎯 Topic: {topic}")
    print(f"🌐 Sources: News aggregator + Web search")
    print(f"📊 Will fetch: 50 articles from internet")
    print(f"🤖 GPT will analyze and generate: 5 risk signals")
    print("\n" + "="*80)
    print("⏳ STEP 1: Fetching fresh data from internet...")
    print("   📰 Scraping Google News, GDELT, Reuters, BBC, etc.")
    print("   🔍 Running web searches...")
    print("="*80)

    result = await run_live_agent_job('live_query', job)

    print("\n" + "="*80)
    print("✅ INTERNET SCRAPING COMPLETE")
    print("="*80)
    print(f"Status: {result['status']}")
    print(f"📊 Signals generated: {result['signals_generated']}")
    print(f"💾 Signals emitted: {result['signals_emitted']}")
    print(f"🤖 Model: {result.get('model', 'unknown')}")

    # Show generated signals
    if result['signals_emitted'] > 0:
        db = get_risk_db()
        recent = db.get_latest_signals(limit=10, min_risk_score=0)

        print("\n" + "="*80)
        print("📰 SIGNALS GENERATED FROM INTERNET DATA")
        print("="*80)

        for sig in recent[:result['signals_emitted']]:
            if sig['source'] == 'live_query_agent':
                print(f"\n🔸 {sig['title']}")
                print(f"   Risk: {sig['risk_score']:.1f}/100 | Confidence: {sig['confidence']:.2f}")
                print(f"   Category: {sig['category']} | Entity: {sig.get('entity', 'N/A')}")

                # Show evidence
                raw = sig.get('raw', {})
                if isinstance(raw, str):
                    import json
                    try:
                        raw = json.loads(raw)
                    except:
                        pass

                articles_count = raw.get('articles_analyzed', 0)
                evidence = raw.get('evidence', [])
                source_urls = raw.get('source_urls', [])

                print(f"   📊 Based on {articles_count} internet articles")
                if evidence:
                    print(f"   📚 Evidence: {', '.join(evidence[:2])}")
                if source_urls:
                    print(f"   🔗 Sources:")
                    for url in source_urls[:2]:
                        print(f"      • {url}")

                print(f"\n   Analysis:")
                print(f"   {sig['summary'][:300]}...")
                print()

    return result


async def demo_live_monitor_agent():
    """Demo: Live Monitoring Agent - Real-time Entity Monitoring"""
    print("\n" + "="*80)
    print("📡 LIVE MONITORING AGENT - Real-Time Anomaly Detection")
    print("="*80)

    # Choose entity to monitor
    entity = input("\n🎯 Enter entity to monitor (or press Enter for 'Bitcoin'): ").strip()
    if not entity:
        entity = "Bitcoin"

    job = AgentJob(
        name='live_monitoring',
        params={
            'entity': entity,
            'thresholds': {
                'sentiment_drop': -0.5,
                'volume_spike': 4.0
            },
            'time_window_hours': 48,
            'max_articles': 30
        }
    )

    print(f"\n📋 Job: {job.name}")
    print(f"🎯 Entity: {entity}")
    print(f"⏱️  Time window: Last 48 hours")
    print(f"📊 Will fetch: 30 fresh articles from internet")
    print("\n" + "="*80)
    print("⏳ Fetching fresh data from internet...")
    print("="*80)

    result = await run_live_agent_job('live_monitor', job)

    print("\n" + "="*80)
    print("✅ MONITORING COMPLETE")
    print("="*80)
    print(f"Status: {result['status']}")
    print(f"🚨 Anomalies detected: {result['signals_generated']}")
    print(f"💾 Signals emitted: {result['signals_emitted']}")

    # Show anomalies
    if result['signals_emitted'] > 0:
        db = get_risk_db()
        recent = db.get_latest_signals(limit=10, min_risk_score=0)

        print("\n" + "="*80)
        print("🚨 ANOMALIES DETECTED FROM LIVE DATA")
        print("="*80)

        for sig in recent[:result['signals_emitted']]:
            if sig['source'] == 'live_monitor_agent':
                print(f"\n🔸 {sig['title']}")
                print(f"   Risk: {sig['risk_score']:.1f}/100 | Impact: {sig['impact']}")

                raw = sig.get('raw', {})
                if isinstance(raw, str):
                    import json
                    try:
                        raw = json.loads(raw)
                    except:
                        pass

                severity = raw.get('severity', 0)
                articles = raw.get('articles_analyzed', 0)

                print(f"   Severity: {severity}/100 | Based on {articles} articles")
                print(f"\n   Analysis:")
                print(f"   {sig['summary'][:300]}...")

    return result


async def run_all_live_agents():
    """Run all live agents sequentially"""
    print("\n" + "🌐"*40)
    print("LIVE AI AGENTS - ACTIVELY SCOURING THE INTERNET")
    print("These agents fetch fresh data in real-time!")
    print("🌐"*40)

    results = []

    try:
        # 1. Live Query Agent
        result = await demo_live_query_agent()
        results.append(('Live Query Agent', result))
        await asyncio.sleep(2)

        # 2. Live Monitoring Agent
        result = await demo_live_monitor_agent()
        results.append(('Live Monitor Agent', result))

    except Exception as e:
        print(f"\n❌ Error running agents: {e}")
        import traceback
        traceback.print_exc()

    # Summary
    print("\n" + "="*80)
    print("📊 FINAL SUMMARY")
    print("="*80)

    total_signals = 0
    for agent_name, result in results:
        status_icon = "✅" if result['status'] == 'success' else "❌"
        signals = result.get('signals_emitted', 0)
        total_signals += signals
        print(f"{status_icon} {agent_name}: {signals} signals from internet data")

    print(f"\n📈 Total signals generated: {total_signals}")

    # Database stats
    db = get_risk_db()
    stats = db.get_signal_stats()
    print(f"\n💾 Database Stats:")
    print(f"   Total signals: {stats['total_signals']}")
    print(f"   High risk (>70): {stats['high_risk_count']}")
    print(f"   Average risk: {stats['avg_risk_score']:.1f}")

    print("\n✨ All live agents completed successfully!")
    print("📊 View results in dashboard: python -m sentiment_bot.risk_intelligence.dashboard")


async def interactive_menu():
    """Interactive menu for live agents"""
    while True:
        print("\n" + "="*80)
        print("🌐 LIVE AI AGENT RUNNER - Agents that Scrape the Internet")
        print("="*80)
        print("\n1. 🔍 Live Query Agent - Scrape internet for risk signals")
        print("2. 📡 Live Monitoring Agent - Monitor entity with fresh data")
        print("3. 🚀 Run Both Agents")
        print("4. 📊 View Database Stats")
        print("0. ❌ Exit")

        choice = input("\nSelect option (0-4): ").strip()

        if choice == '1':
            await demo_live_query_agent()
        elif choice == '2':
            await demo_live_monitor_agent()
        elif choice == '3':
            await run_all_live_agents()
        elif choice == '4':
            db = get_risk_db()
            stats = db.get_signal_stats()
            print("\n📊 Database Statistics:")
            print(f"   Total signals: {stats['total_signals']}")
            print(f"   High risk (>70): {stats['high_risk_count']}")
            print(f"   Avg risk: {stats['avg_risk_score']:.1f}")

            # Show live vs non-live
            live_signals = [s for s in db.get_latest_signals(limit=100)
                          if s['source'].startswith('live_')]
            print(f"   Internet-sourced signals: {len(live_signals)}")

        elif choice == '0':
            print("\n👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice. Try again.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Run live AI agents that scrape the internet')
    parser.add_argument('--all', action='store_true', help='Run all agents')
    parser.add_argument('--agent', choices=list(LIVE_AGENT_REGISTRY.keys()),
                       help='Run specific live agent')
    parser.add_argument('--topic', type=str, help='Topic to search for')

    args = parser.parse_args()

    # Check for OpenAI key
    if not os.getenv('OPENAI_API_KEY'):
        print("❌ ERROR: OPENAI_API_KEY not set in environment")
        print("Please set your OpenAI API key:")
        print("  export OPENAI_API_KEY='your-key-here'")
        sys.exit(1)

    if args.all:
        asyncio.run(run_all_live_agents())
    elif args.agent:
        if args.agent == 'live_query':
            asyncio.run(demo_live_query_agent())
        elif args.agent == 'live_monitor':
            asyncio.run(demo_live_monitor_agent())
    else:
        # Default: interactive menu
        asyncio.run(interactive_menu())
