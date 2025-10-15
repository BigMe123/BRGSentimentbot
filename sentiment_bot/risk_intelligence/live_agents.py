#!/usr/bin/env python3
"""
Live AI Agents - Internet-Connected Version
Agents that actively scrape the web for real-time risk signals
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
import json

from .ai_agents import AIBaseAgent, AgentJob, Signal
from ..connectors.news_aggregator import NewsAggregatorConnector
from ..connectors.web_search import WebSearchConnector

logger = logging.getLogger(__name__)


class LiveQueryAgent(AIBaseAgent):
    """
    AI Query Agent with LIVE INTERNET ACCESS
    Scrapes news, social media, and web search results in real-time
    """

    def __init__(self):
        super().__init__("live_query_agent")

    async def process_job(self, job: AgentJob) -> List[Signal]:
        """Search internet for risk signals using real data"""
        topic = job.params.get('topic', 'economic indicators')
        sources = job.params.get('sources', ['news', 'web'])
        max_leads = job.params.get('max_leads', 5)
        max_articles = job.params.get('max_articles', 50)
        signal_type = job.params.get('signal_type', 'all')
        entities = job.entities or []

        logger.info(f"[LiveQueryAgent] 🌐 SCOURING INTERNET for: {topic}")
        logger.info(f"[LiveQueryAgent] Sources: {sources} | Max articles: {max_articles}")

        # ========================================
        # STEP 1: FETCH LIVE DATA FROM INTERNET
        # ========================================

        all_articles = []

        # Fetch from news sources
        if 'news' in sources:
            logger.info(f"[LiveQueryAgent] 📰 Fetching live news...")
            news_connector = NewsAggregatorConnector(
                topic=topic,
                max_results=max_articles,
                days_back=7
            )

            article_count = 0
            async for article in news_connector.fetch():
                all_articles.append(article)
                article_count += 1
                if article_count >= max_articles:
                    break

            logger.info(f"[LiveQueryAgent] ✅ Fetched {len(all_articles)} news articles")

        # Fetch from web search
        if 'web' in sources:
            logger.info(f"[LiveQueryAgent] 🔍 Fetching web search results...")
            try:
                web_connector = WebSearchConnector(
                    queries=[topic] + entities[:3],
                    max_results=20
                )

                web_count = 0
                async for result in web_connector.fetch():
                    all_articles.append(result)
                    web_count += 1

                logger.info(f"[LiveQueryAgent] ✅ Fetched {web_count} web results")
            except Exception as e:
                logger.warning(f"[LiveQueryAgent] Web search failed: {e}")

        if not all_articles:
            logger.warning(f"[LiveQueryAgent] ⚠️  No articles found for '{topic}'")
            return []

        # ========================================
        # STEP 2: PREPARE DATA FOR GPT ANALYSIS
        # ========================================

        # Extract key information from articles
        article_summaries = []
        for article in all_articles[:30]:  # Send top 30 to GPT
            # Convert datetime to string if needed
            published_at = article.get('published_at', '')
            if hasattr(published_at, 'isoformat'):
                published_at = published_at.isoformat()
            elif not isinstance(published_at, str):
                published_at = str(published_at)

            article_summaries.append({
                'title': article.get('title', '')[:200],
                'text': article.get('text', '')[:500],
                'source': article.get('source', ''),
                'url': article.get('url', '')[:100],
                'published_at': published_at
            })

        # ========================================
        # STEP 3: GPT ANALYZES REAL INTERNET DATA
        # ========================================

        signal_desc = {
            'weak': 'early indicators and emerging risks',
            'strong': 'confirmed major risks with clear evidence',
            'all': 'both weak (emerging) and strong (confirmed) risk signals'
        }

        system_prompt = f"""You are a risk intelligence analyst analyzing REAL-TIME internet data.

You have access to {len(all_articles)} recent articles from the internet about: {topic}

Your job: Identify {signal_desc.get(signal_type, 'risk signals')} from this REAL data.

Signal Types:
- WEAK SIGNALS: Early indicators, unusual patterns, emerging trends (low evidence)
- STRONG SIGNALS: Confirmed events, major announcements, clear risks (high evidence)

Analyze the articles and identify {max_leads} most important risk signals.

For each signal:
1. Title - Clear, specific headline
2. Analysis - 3-4 sentences explaining the signal and its implications
3. Evidence - Which article(s) support this signal
4. Signal strength - "weak" or "strong" based on evidence quality
5. Confidence - 0.0-1.0 based on data quality
6. Category - macro, regulatory, supply_chain, brand, market, geopolitical, energy, tech, climate, finance
7. Entity - Main affected entity (company, country, sector)
8. Tags - 3-5 relevant keywords

Focus on: {', '.join(sources)}
Entities: {', '.join(entities) if entities else 'any'}

Return ONLY valid JSON array:
[
  {{
    "title": "specific headline",
    "analysis": "detailed explanation with evidence",
    "evidence": ["article title 1", "article title 2"],
    "signal_strength": "weak|strong",
    "confidence": 0.75,
    "category": "market",
    "entity": "tech sector",
    "tags": ["tag1", "tag2", "tag3"]
  }}
]"""

        user_prompt = f"""REAL-TIME INTERNET DATA for: {topic}

Total articles analyzed: {len(all_articles)}
Date range: Last 7 days

Sample articles:
{json.dumps(article_summaries[:15], indent=2)}

Identify {max_leads} risk signals from this REAL data.
Prioritize signals with strong evidence from multiple sources.
Return JSON array only."""

        # ========================================
        # STEP 4: GET GPT ANALYSIS
        # ========================================

        try:
            logger.info(f"[LiveQueryAgent] 🤖 Analyzing with GPT...")
            response = await self.llm.chat(system_prompt, user_prompt)

            # Parse GPT response
            response_clean = response.strip()
            if response_clean.startswith('```'):
                lines = response_clean.split('\n')
                response_clean = '\n'.join(lines[1:-1]) if len(lines) > 2 else response_clean
                response_clean = response_clean.replace('```json', '').replace('```', '').strip()

            leads = json.loads(response_clean)

            if not isinstance(leads, list):
                logger.error(f"GPT returned non-list: {response[:200]}")
                return []

            # ========================================
            # STEP 5: CREATE SIGNALS FROM GPT ANALYSIS
            # ========================================

            signals = []
            for lead in leads[:max_leads]:
                try:
                    signal_strength = lead.get('signal_strength', 'weak')
                    tags = lead.get('tags', [])
                    tags.extend(['internet_sourced', signal_strength, 'live_data'])

                    # Find supporting articles
                    evidence = lead.get('evidence', [])
                    source_urls = []
                    for article in all_articles[:20]:
                        for ev_title in evidence:
                            if ev_title.lower() in article.get('title', '').lower():
                                source_urls.append(article.get('url', ''))
                                break

                    signal = self.create_signal(
                        title=lead.get('title', 'Untitled Signal'),
                        summary=lead.get('analysis', 'No analysis provided'),
                        category=lead.get('category', 'general'),
                        entity=lead.get('entity'),
                        confidence=float(lead.get('confidence', 0.5)),
                        tags=tags[:15],
                        raw_data={
                            'search_query': topic,
                            'sources_searched': sources,
                            'signal_strength': signal_strength,
                            'articles_analyzed': len(all_articles),
                            'evidence': evidence,
                            'source_urls': source_urls[:5],
                            'internet_fetch': True,
                            'live_data': True,
                            'gpt_response': lead
                        }
                    )
                    signals.append(signal)
                    logger.info(f"[LiveQueryAgent] ✅ Created signal: {lead.get('title', '')[:50]}")

                except Exception as e:
                    logger.error(f"Failed to create signal: {e}")
                    continue

            logger.info(f"[LiveQueryAgent] 🎉 Generated {len(signals)} signals from internet data")
            return signals

        except json.JSONDecodeError as e:
            logger.error(f"GPT returned invalid JSON: {response[:500]}")
            return []
        except Exception as e:
            logger.error(f"GPT analysis failed: {e}")
            return []


class LiveMonitoringAgent(AIBaseAgent):
    """
    AI Monitoring Agent with LIVE INTERNET ACCESS
    Continuously monitors specific entities by scraping fresh data
    """

    def __init__(self):
        super().__init__("live_monitor_agent")

    async def process_job(self, job: AgentJob) -> List[Signal]:
        """Monitor entity using live internet data"""
        entity = job.params.get('entity', 'market')
        thresholds = job.params.get('thresholds', {})
        time_window = job.params.get('time_window_hours', 24)
        max_articles = job.params.get('max_articles', 30)

        logger.info(f"[LiveMonitorAgent] 🌐 MONITORING {entity} with live data")

        # ========================================
        # STEP 1: FETCH FRESH DATA FROM INTERNET
        # ========================================

        logger.info(f"[LiveMonitorAgent] 📰 Fetching fresh news about {entity}...")

        news_connector = NewsAggregatorConnector(
            topic=entity,
            max_results=max_articles,
            days_back=2  # Recent news only
        )

        articles = []
        async for article in news_connector.fetch():
            articles.append(article)

        if not articles:
            logger.warning(f"[LiveMonitorAgent] ⚠️  No recent articles for {entity}")
            return []

        logger.info(f"[LiveMonitorAgent] ✅ Fetched {len(articles)} fresh articles")

        # Also get historical signals for comparison
        start_ts = (datetime.now(timezone.utc) - timedelta(hours=time_window*2)).isoformat()
        recent_signals = self.db.get_signals_time_range(start_ts, datetime.now(timezone.utc).isoformat())

        # Filter by entity
        entity_signals = [s for s in recent_signals
                         if entity.lower() in s.get('title', '').lower()
                         or entity.lower() == s.get('entity', '').lower()]

        # ========================================
        # STEP 2: PREPARE DATA FOR GPT
        # ========================================

        article_data = []
        for article in articles[:20]:
            article_data.append({
                'time': article.get('published_at', '')[-8:],
                'title': article.get('title', '')[:200],
                'source': article.get('source', ''),
                'text_preview': article.get('text', '')[:300]
            })

        historical_data = []
        for sig in entity_signals[-10:]:
            historical_data.append({
                'time': sig.get('ts', '')[-8:],
                'title': sig.get('title', ''),
                'risk_score': sig.get('risk_score', 0)
            })

        # ========================================
        # STEP 3: GPT ANALYZES FOR ANOMALIES
        # ========================================

        system_prompt = f"""You are an anomaly detection system analyzing REAL-TIME internet data.

Entity: {entity}
Fresh articles: {len(articles)} from last 48 hours
Historical signals: {len(entity_signals)} from last {time_window*2} hours
Thresholds: {json.dumps(thresholds)}

Detect anomalies by comparing fresh internet data to historical patterns:
- Sudden sentiment shifts (negative news surge)
- Unusual activity spikes (coverage increase)
- Risk escalations (crisis keywords)
- Pattern breaks (deviation from baseline)

Return ONLY valid JSON array:
[
  {{
    "title": "anomaly title",
    "analysis": "what changed and why it matters (3-4 sentences)",
    "severity": 75,
    "confidence": 0.85,
    "category": "market",
    "tags": ["anomaly", "tag2"],
    "evidence": ["article title 1"]
  }}
]

If no significant anomalies, return empty array []."""

        user_prompt = f"""FRESH INTERNET DATA for {entity}:

Recent articles ({len(articles)} total):
{json.dumps(article_data, indent=2)}

Historical signals for comparison:
{json.dumps(historical_data, indent=2)}

Identify anomalies by comparing fresh data to historical patterns.
Return JSON array (or [] if no anomalies)."""

        try:
            logger.info(f"[LiveMonitorAgent] 🤖 Analyzing with GPT...")
            response = await self.llm.chat(system_prompt, user_prompt)

            response_clean = response.strip()
            if response_clean.startswith('```'):
                lines = response_clean.split('\n')
                response_clean = '\n'.join(lines[1:-1]) if len(lines) > 2 else response_clean
                response_clean = response_clean.replace('```json', '').replace('```', '').strip()

            anomalies = json.loads(response_clean)

            if not isinstance(anomalies, list):
                return []

            signals = []
            for anomaly in anomalies:
                try:
                    tags = anomaly.get('tags', [entity, 'anomaly'])
                    tags.extend(['internet_sourced', 'live_monitoring'])

                    signal = self.create_signal(
                        title=anomaly.get('title', 'Anomaly Detected'),
                        summary=anomaly.get('analysis', 'No analysis'),
                        category=anomaly.get('category', 'general'),
                        entity=entity,
                        confidence=float(anomaly.get('confidence', 0.7)),
                        tags=tags[:15],
                        raw_data={
                            'anomaly_type': 'live_detection',
                            'severity': anomaly.get('severity', 50),
                            'articles_analyzed': len(articles),
                            'historical_signals': len(entity_signals),
                            'thresholds': thresholds,
                            'evidence': anomaly.get('evidence', []),
                            'internet_fetch': True,
                            'live_data': True
                        }
                    )
                    signals.append(signal)
                    logger.info(f"[LiveMonitorAgent] 🚨 Detected anomaly: {anomaly.get('title', '')[:50]}")

                except Exception as e:
                    logger.error(f"Failed to create anomaly signal: {e}")
                    continue

            logger.info(f"[LiveMonitorAgent] 🎉 Detected {len(signals)} anomalies from live data")
            return signals

        except json.JSONDecodeError as e:
            logger.error(f"GPT returned invalid JSON: {response[:500]}")
            return []
        except Exception as e:
            logger.error(f"Anomaly detection failed: {e}")
            return []


# Live Agent Registry
LIVE_AGENT_REGISTRY = {
    'live_query': LiveQueryAgent,
    'live_monitor': LiveMonitoringAgent
}


def get_live_agent(agent_type: str) -> AIBaseAgent:
    """Get live agent instance by type"""
    agent_class = LIVE_AGENT_REGISTRY.get(agent_type)
    if not agent_class:
        raise ValueError(f"Unknown live agent type: {agent_type}. Available: {list(LIVE_AGENT_REGISTRY.keys())}")
    return agent_class()


async def run_live_agent_job(agent_type: str, job: AgentJob) -> Dict[str, Any]:
    """Run a live agent job"""
    agent = get_live_agent(agent_type)
    return await agent.run_job(job)
