#!/usr/bin/env python3
"""
AI Agent Runner - Test and run all AI-powered risk intelligence agents
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from sentiment_bot.risk_intelligence.ai_agents import (
    run_ai_agent_job,
    AgentJob,
    AI_AGENT_REGISTRY
)
from sentiment_bot.risk_intelligence.database import get_risk_db


async def demo_ai_query_agent():
    """Demo: Query Agent - Weak Signal Detection"""
    print("\n" + "="*80)
    print("🔍 AI QUERY AGENT - Weak Signal Detection")
    print("="*80)

    job = AgentJob(
        name='detect_ai_risks',
        params={
            'topic': 'artificial intelligence regulation',
            'sources': ['news', 'regulatory', 'tech'],
            'max_leads': 3
        },
        entities=['OpenAI', 'Google', 'EU', 'USA']
    )

    print(f"\n📋 Job: {job.name}")
    print(f"🎯 Topic: {job.params['topic']}")
    print(f"🔎 Sources: {', '.join(job.params['sources'])}")
    print(f"🏢 Entities: {', '.join(job.entities)}")
    print("\n⏳ Running GPT analysis...\n")

    result = await run_ai_agent_job('ai_query', job)

    print(f"✅ Status: {result['status']}")
    print(f"📊 Signals generated: {result['signals_generated']}")
    print(f"💾 Signals emitted: {result['signals_emitted']}")
    print(f"🤖 Model: {result.get('model', 'unknown')}")

    # Show generated signals
    if result['signals_emitted'] > 0:
        db = get_risk_db()
        recent = db.get_latest_signals(limit=3, min_risk_score=0)
        print("\n📰 Generated Signals:")
        for sig in recent[:result['signals_emitted']]:
            if sig['source'] == 'ai_query_agent':
                print(f"\n  🔸 {sig['title']}")
                print(f"     Risk: {sig['risk_score']:.1f} | Confidence: {sig['confidence']:.2f}")
                print(f"     Category: {sig['category']} | Entity: {sig['entity']}")
                print(f"     {sig['summary'][:200]}...")

    return result


async def demo_ai_monitor_agent():
    """Demo: Monitoring Agent - Anomaly Detection"""
    print("\n" + "="*80)
    print("📡 AI MONITORING AGENT - Anomaly Detection")
    print("="*80)

    job = AgentJob(
        name='monitor_crypto_market',
        params={
            'entity': 'cryptocurrency',
            'thresholds': {
                'sentiment_drop': -0.4,
                'volume_spike': 3.0,
                'keyword_frequency': 5
            },
            'time_window_hours': 48
        }
    )

    print(f"\n📋 Job: {job.name}")
    print(f"🎯 Entity: {job.params['entity']}")
    print(f"⏱️  Time window: {job.params['time_window_hours']} hours")
    print(f"🚨 Thresholds: {job.params['thresholds']}")
    print("\n⏳ Running anomaly detection...\n")

    result = await run_ai_agent_job('ai_monitor', job)

    print(f"✅ Status: {result['status']}")
    print(f"📊 Anomalies detected: {result['signals_generated']}")
    print(f"💾 Signals emitted: {result['signals_emitted']}")

    # Show anomalies
    if result['signals_emitted'] > 0:
        db = get_risk_db()
        recent = db.get_latest_signals(limit=5, min_risk_score=0)
        print("\n🚨 Detected Anomalies:")
        for sig in recent[:result['signals_emitted']]:
            if sig['source'] == 'ai_monitor_agent':
                print(f"\n  🔸 {sig['title']}")
                print(f"     Risk: {sig['risk_score']:.1f} | Impact: {sig['impact']}")
                print(f"     {sig['summary'][:200]}...")

    return result


async def demo_ai_forecast_agent():
    """Demo: Forecast Agent - Impact Analysis"""
    print("\n" + "="*80)
    print("📈 AI FORECAST AGENT - Causal Impact Analysis")
    print("="*80)

    job = AgentJob(
        name='forecast_tariff_impact',
        params={
            'event': 'US increases tariffs on Chinese imports by 25%',
            'metric': 'US GDP growth',
            'horizon_weeks': 8
        },
        entities=['USA', 'China', 'global trade']
    )

    print(f"\n📋 Job: {job.name}")
    print(f"⚡ Event: {job.params['event']}")
    print(f"📊 Metric: {job.params['metric']}")
    print(f"⏱️  Horizon: {job.params['horizon_weeks']} weeks")
    print("\n⏳ Running forecast model...\n")

    result = await run_ai_agent_job('ai_forecast', job)

    print(f"✅ Status: {result['status']}")
    print(f"📊 Forecasts generated: {result['signals_generated']}")

    # Show forecast
    if result['signals_emitted'] > 0:
        db = get_risk_db()
        recent = db.get_latest_signals(limit=1, min_risk_score=0)
        for sig in recent:
            if sig['source'] == 'ai_forecast_agent':
                print(f"\n📈 Forecast:")
                print(f"  Title: {sig['title']}")
                print(f"  Risk Score: {sig['risk_score']:.1f}")
                print(f"  Confidence: {sig['confidence']:.2f}")
                print(f"\n  Analysis:\n  {sig['summary']}\n")

                # Show drivers if available
                raw = sig.get('raw', {})
                if isinstance(raw, str):
                    import json
                    try:
                        raw = json.loads(raw)
                    except:
                        pass

                drivers = raw.get('drivers', [])
                if drivers:
                    print("  Causal Drivers:")
                    for i, driver in enumerate(drivers, 1):
                        print(f"    {i}. {driver}")

    return result


async def demo_ai_summarizer_agent():
    """Demo: Summarizer Agent - Executive Brief"""
    print("\n" + "="*80)
    print("📝 AI SUMMARIZER AGENT - Executive Daily Brief")
    print("="*80)

    job = AgentJob(
        name='daily_tech_brief',
        params={
            'entity': 'technology',
            'period_hours': 72,
            'top_n': 20
        }
    )

    print(f"\n📋 Job: {job.name}")
    print(f"🎯 Entity: {job.params['entity']}")
    print(f"⏱️  Period: Last {job.params['period_hours']} hours")
    print("\n⏳ Generating executive brief...\n")

    result = await run_ai_agent_job('ai_summarizer', job)

    print(f"✅ Status: {result['status']}")
    print(f"📊 Briefs generated: {result['signals_generated']}")

    # Show brief
    if result['signals_emitted'] > 0:
        db = get_risk_db()
        recent = db.get_latest_signals(limit=1, min_risk_score=0)
        for sig in recent:
            if sig['source'] == 'ai_summarizer_agent':
                print(f"\n📰 Executive Brief:")
                print(f"\n{sig['summary']}\n")

                # Show structured data
                raw = sig.get('raw', {})
                if isinstance(raw, str):
                    import json
                    try:
                        raw = json.loads(raw)
                    except:
                        pass

                actions = raw.get('recommended_actions', [])
                if actions:
                    print("🎯 Recommended Actions:")
                    for action in actions:
                        print(f"  • {action}")

    return result


async def demo_ai_trend_analyst():
    """Demo: Trend Analyst Agent"""
    print("\n" + "="*80)
    print("📊 AI TREND ANALYST - Emerging Trend Detection")
    print("="*80)

    job = AgentJob(
        name='analyze_market_trends',
        params={
            'category': 'market',
            'time_windows': [24, 72, 168]  # 1d, 3d, 7d
        }
    )

    print(f"\n📋 Job: {job.name}")
    print(f"📈 Category: {job.params['category']}")
    print(f"⏱️  Time windows: {job.params['time_windows']} hours")
    print("\n⏳ Analyzing trends...\n")

    result = await run_ai_agent_job('ai_trend', job)

    print(f"✅ Status: {result['status']}")
    print(f"📊 Trends identified: {result['signals_generated']}")

    # Show trends
    if result['signals_emitted'] > 0:
        db = get_risk_db()
        recent = db.get_latest_signals(limit=5, min_risk_score=0)
        print("\n📈 Identified Trends:")
        for sig in recent[:result['signals_emitted']]:
            if sig['source'] == 'ai_trend_analyst':
                print(f"\n  🔸 {sig['title']}")
                print(f"     Risk: {sig['risk_score']:.1f}")
                print(f"     {sig['summary'][:200]}...")

    return result


async def demo_ai_competitive_intel():
    """Demo: Competitive Intelligence Agent"""
    print("\n" + "="*80)
    print("🎯 AI COMPETITIVE INTELLIGENCE - Strategic Analysis")
    print("="*80)

    job = AgentJob(
        name='analyze_tech_competition',
        params={
            'primary_entity': 'OpenAI',
            'competitors': ['Google', 'Anthropic', 'Microsoft', 'Meta'],
            'time_window_hours': 72
        }
    )

    print(f"\n📋 Job: {job.name}")
    print(f"🎯 Primary: {job.params['primary_entity']}")
    print(f"🏢 Competitors: {', '.join(job.params['competitors'])}")
    print(f"⏱️  Time window: {job.params['time_window_hours']} hours")
    print("\n⏳ Analyzing competitive landscape...\n")

    result = await run_ai_agent_job('ai_competitive', job)

    print(f"✅ Status: {result['status']}")
    print(f"📊 Intelligence findings: {result['signals_generated']}")

    # Show findings
    if result['signals_emitted'] > 0:
        db = get_risk_db()
        recent = db.get_latest_signals(limit=5, min_risk_score=0)
        print("\n🎯 Competitive Intelligence:")
        for sig in recent[:result['signals_emitted']]:
            if sig['source'] == 'ai_competitive_intel':
                print(f"\n  🔸 {sig['title']}")
                print(f"     Risk: {sig['risk_score']:.1f}")
                print(f"     {sig['summary'][:300]}...")

    return result


async def run_all_agents():
    """Run all AI agents in sequence"""
    print("\n" + "🤖"*40)
    print("AI-POWERED RISK INTELLIGENCE AGENTS")
    print("Running 6 AI agents using OpenAI GPT")
    print("🤖"*40)

    results = []

    try:
        # 1. Query Agent
        result = await demo_ai_query_agent()
        results.append(('AI Query Agent', result))
        await asyncio.sleep(2)

        # 2. Monitoring Agent
        result = await demo_ai_monitor_agent()
        results.append(('AI Monitor Agent', result))
        await asyncio.sleep(2)

        # 3. Forecast Agent
        result = await demo_ai_forecast_agent()
        results.append(('AI Forecast Agent', result))
        await asyncio.sleep(2)

        # 4. Summarizer Agent
        result = await demo_ai_summarizer_agent()
        results.append(('AI Summarizer Agent', result))
        await asyncio.sleep(2)

        # 5. Trend Analyst
        result = await demo_ai_trend_analyst()
        results.append(('AI Trend Analyst', result))
        await asyncio.sleep(2)

        # 6. Competitive Intel
        result = await demo_ai_competitive_intel()
        results.append(('AI Competitive Intel', result))

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
        print(f"{status_icon} {agent_name}: {signals} signals emitted")

    print(f"\n📈 Total signals generated across all agents: {total_signals}")

    # Database stats
    db = get_risk_db()
    stats = db.get_signal_stats()
    print(f"\n💾 Database Stats:")
    print(f"   Total signals in DB: {stats['total_signals']}")
    print(f"   High risk (>70): {stats['high_risk_count']}")
    print(f"   Last 24h: {stats['last_24h']}")
    print(f"   Average risk score: {stats['avg_risk_score']:.1f}")

    print("\n✨ All AI agents completed successfully!")
    print("📊 View results in dashboard: python -m sentiment_bot.risk_intelligence.dashboard")
    print("🔗 Or via API: http://localhost:8765/api/latest")


async def interactive_menu():
    """Interactive menu to run individual agents"""
    while True:
        print("\n" + "="*80)
        print("🤖 AI AGENT RUNNER - Select Agent to Run")
        print("="*80)
        print("\n1. 🔍 AI Query Agent - Weak Signal Detection")
        print("2. 📡 AI Monitoring Agent - Anomaly Detection")
        print("3. 📈 AI Forecast Agent - Impact Analysis")
        print("4. 📝 AI Summarizer Agent - Executive Brief")
        print("5. 📊 AI Trend Analyst - Trend Detection")
        print("6. 🎯 AI Competitive Intel - Strategic Analysis")
        print("\n7. 🚀 Run ALL Agents (sequential)")
        print("8. 📊 View Database Stats")
        print("9. 🔄 Clear Recent AI Signals")
        print("0. ❌ Exit")

        choice = input("\nSelect option (0-9): ").strip()

        if choice == '1':
            await demo_ai_query_agent()
        elif choice == '2':
            await demo_ai_monitor_agent()
        elif choice == '3':
            await demo_ai_forecast_agent()
        elif choice == '4':
            await demo_ai_summarizer_agent()
        elif choice == '5':
            await demo_ai_trend_analyst()
        elif choice == '6':
            await demo_ai_competitive_intel()
        elif choice == '7':
            await run_all_agents()
        elif choice == '8':
            db = get_risk_db()
            stats = db.get_signal_stats()
            print("\n📊 Database Statistics:")
            print(f"   Total signals: {stats['total_signals']}")
            print(f"   High risk (>70): {stats['high_risk_count']}")
            print(f"   Last 24h: {stats['last_24h']}")
            print(f"   Avg risk score: {stats['avg_risk_score']:.1f}")
            print(f"\n   By category:")
            for cat, count in stats.get('by_category', {}).items():
                print(f"     • {cat}: {count}")
            print(f"\n   By source:")
            for src, count in stats.get('by_source', {}).items():
                print(f"     • {src}: {count}")
        elif choice == '9':
            db = get_risk_db()
            # Note: This would require adding a delete method to the database class
            print("\n⚠️  Clear function not implemented (prevents accidental data loss)")
            print("   To clear database: rm data/risk_intelligence.db")
        elif choice == '0':
            print("\n👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice. Try again.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Run AI-powered risk intelligence agents')
    parser.add_argument('--all', action='store_true', help='Run all agents sequentially')
    parser.add_argument('--agent', choices=list(AI_AGENT_REGISTRY.keys()),
                       help='Run specific agent')
    parser.add_argument('--interactive', '-i', action='store_true',
                       help='Interactive menu mode')

    args = parser.parse_args()

    # Check for OpenAI key
    if not os.getenv('OPENAI_API_KEY'):
        print("❌ ERROR: OPENAI_API_KEY not set in environment")
        print("Please set your OpenAI API key:")
        print("  export OPENAI_API_KEY='your-key-here'")
        sys.exit(1)

    if args.all:
        asyncio.run(run_all_agents())
    elif args.agent:
        print(f"Running single agent: {args.agent}")
        # Run specific agent with default params
        if args.agent == 'ai_query':
            asyncio.run(demo_ai_query_agent())
        elif args.agent == 'ai_monitor':
            asyncio.run(demo_ai_monitor_agent())
        elif args.agent == 'ai_forecast':
            asyncio.run(demo_ai_forecast_agent())
        elif args.agent == 'ai_summarizer':
            asyncio.run(demo_ai_summarizer_agent())
        elif args.agent == 'ai_trend':
            asyncio.run(demo_ai_trend_analyst())
        elif args.agent == 'ai_competitive':
            asyncio.run(demo_ai_competitive_intel())
    else:
        # Default: interactive menu
        asyncio.run(interactive_menu())
