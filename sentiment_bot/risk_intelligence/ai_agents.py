#!/usr/bin/env python3
"""
AI-Powered Risk Intelligence Agents
Uses OpenAI GPT to analyze real data and generate insights
"""

import asyncio
import logging
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from .database import get_risk_db, Signal
from .enrichment import get_enricher, get_scorer
from ..llm_client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class AgentJob:
    """Input contract for agent jobs"""
    name: str
    params: Dict[str, Any]
    since: Optional[str] = None
    entities: List[str] = None

    def __post_init__(self):
        if self.entities is None:
            self.entities = []


class AIBaseAgent:
    """Base class for AI-powered agents using GPT"""

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.db = get_risk_db()
        self.enricher = get_enricher()
        self.scorer = get_scorer()
        self.llm = LLMClient()

        logger.info(f"[{agent_name}] Initialized with GPT model: {self.llm.model}")

    def create_signal(self, title: str, summary: str, category: str,
                     entity: Optional[str], confidence: float,
                     tags: List[str], raw_data: Dict) -> Signal:
        """Create a signal from agent output"""
        # Enrich the text
        enriched = self.enricher.enrich_document(title, summary, self.agent_name)

        # Compute risk score
        risk_score = self.scorer.compute_risk_score(enriched, confidence, self.agent_name)
        impact = self.scorer.compute_impact(risk_score)

        # Merge tags
        all_tags = list(set(tags + enriched['tags']))

        # Generate ID
        ts = datetime.now(timezone.utc).isoformat()
        signal_id = self.db.generate_signal_id(title, self.agent_name, ts)

        # Create signal
        signal = Signal(
            id=signal_id,
            ts=ts,
            source=self.agent_name,
            category=category,
            entity=entity,
            title=title,
            summary=summary,
            risk_score=risk_score,
            tags=all_tags[:15],
            link=raw_data.get('link'),
            raw={
                'enriched': enriched,
                'confidence': confidence,
                'agent_params': raw_data,
                'gpt_model': self.llm.model
            },
            confidence=confidence,
            impact=impact
        )

        return signal

    def emit_signal(self, signal: Signal) -> bool:
        """Emit signal to database"""
        success = self.db.insert_signal(signal, check_duplicate=True)
        if success:
            logger.info(f"[{self.agent_name}] Emitted signal: {signal.title[:50]} (risk={signal.risk_score:.1f})")
        else:
            logger.debug(f"[{self.agent_name}] Duplicate signal skipped: {signal.title[:50]}")
        return success

    def update_heartbeat(self, status: str = 'healthy', error: Optional[str] = None):
        """Update agent health status"""
        self.db.update_agent_heartbeat(self.agent_name, status, error)

    async def process_job(self, job: AgentJob) -> List[Signal]:
        """Process a job - to be implemented by subclasses"""
        raise NotImplementedError

    async def run_job(self, job: AgentJob) -> Dict[str, Any]:
        """Run a job and return results"""
        try:
            self.update_heartbeat('healthy')
            logger.info(f"[{self.agent_name}] Starting job: {job.name}")

            signals = await self.process_job(job)

            # Emit signals
            emitted_count = 0
            for signal in signals:
                if self.emit_signal(signal):
                    emitted_count += 1

            result = {
                'agent': self.agent_name,
                'status': 'success',
                'signals_generated': len(signals),
                'signals_emitted': emitted_count,
                'job': job.name,
                'model': self.llm.model
            }

            self.update_heartbeat('healthy')
            logger.info(f"[{self.agent_name}] Job complete: {emitted_count}/{len(signals)} signals emitted")
            return result

        except Exception as e:
            logger.error(f"[{self.agent_name}] Job failed: {e}", exc_info=True)
            self.update_heartbeat('degraded', str(e))
            return {
                'agent': self.agent_name,
                'status': 'error',
                'error': str(e),
                'job': job.name
            }


class AIQueryAgent(AIBaseAgent):
    """
    AI-powered signal detection (both weak and strong)
    Uses GPT to analyze news, social media, and economic data for risk indicators
    """

    def __init__(self):
        super().__init__("ai_query_agent")

    async def process_job(self, job: AgentJob) -> List[Signal]:
        """Search for risk signals using GPT analysis"""
        topic = job.params.get('topic', 'economic indicators')
        sources = job.params.get('sources', ['news', 'social', 'economic'])
        max_leads = job.params.get('max_leads', 5)
        signal_type = job.params.get('signal_type', 'all')  # weak, strong, or all
        entities = job.entities or []

        logger.info(f"[AIQueryAgent] Analyzing: {topic} (type: {signal_type}, entities: {entities})")

        # Get recent data from database to analyze
        recent_signals = self.db.get_latest_signals(limit=100, min_risk_score=0)

        # Build context for GPT
        context_data = []
        for sig in recent_signals[:20]:
            context_data.append({
                'title': sig.get('title', ''),
                'category': sig.get('category', ''),
                'entity': sig.get('entity', ''),
                'risk_score': sig.get('risk_score', 0)
            })

        signal_desc = {
            'weak': 'early indicators and emerging risks that may escalate',
            'strong': 'confirmed major risks with clear evidence and immediate impact',
            'all': 'both weak (emerging) and strong (confirmed) risk signals'
        }

        system_prompt = f"""You are a risk intelligence analyst specializing in detecting risk signals.
Your job is to identify {signal_desc.get(signal_type, 'risk signals')} related to: {topic}

Signal Types to Detect:
- WEAK SIGNALS: Early indicators, unusual patterns, emerging trends (may or may not materialize)
- STRONG SIGNALS: Confirmed events, major announcements, clear risks with evidence

Analyze available data sources and identify {max_leads} risk signals (prioritize by importance/severity).

For each signal, provide:
1. A clear, specific title
2. A detailed analysis (2-3 sentences) explaining the signal and its potential impact
3. Signal strength: "weak" or "strong" based on evidence quality
4. Confidence score (0.0-1.0) based on data quality and signal strength
5. Category: macro, regulatory, supply_chain, brand, market, geopolitical, energy, tech, climate, or finance
6. Main entity affected (company, country, or sector)
7. 3-5 relevant tags

Focus on: {', '.join(sources)}
Entities of interest: {', '.join(entities) if entities else 'any'}

Return ONLY valid JSON array with this exact structure:
[
  {{
    "title": "specific descriptive title",
    "analysis": "detailed explanation of the signal and its impact/implications",
    "signal_strength": "weak|strong",
    "confidence": 0.75,
    "category": "market",
    "entity": "tech sector",
    "tags": ["tag1", "tag2", "tag3"]
  }}
]"""

        user_prompt = f"""Analyze current landscape for topic: {topic}

Recent context from existing signals:
{json.dumps(context_data[:10], indent=2)}

Identify {max_leads} NEW risk signals (not duplicates) including:
- Weak signals: Early indicators, unusual patterns, emerging trends
- Strong signals: Confirmed events, major developments, clear risks

Focus on actionable intelligence with high relevance to the topic.
Return JSON array only."""

        try:
            response = await self.llm.chat(system_prompt, user_prompt)

            # Parse GPT response
            # Try to extract JSON if wrapped in markdown
            response_clean = response.strip()
            if response_clean.startswith('```'):
                # Remove markdown code blocks
                lines = response_clean.split('\n')
                response_clean = '\n'.join(lines[1:-1]) if len(lines) > 2 else response_clean
                response_clean = response_clean.replace('```json', '').replace('```', '').strip()

            leads = json.loads(response_clean)

            if not isinstance(leads, list):
                logger.error(f"GPT returned non-list: {response[:200]}")
                return []

            # Convert GPT analysis to signals
            signals = []
            for lead in leads[:max_leads]:
                try:
                    signal_strength = lead.get('signal_strength', 'weak')
                    tags = lead.get('tags', [])
                    tags.append(signal_strength)  # Add strength as tag

                    signal = self.create_signal(
                        title=lead.get('title', 'Untitled Signal'),
                        summary=lead.get('analysis', 'No analysis provided'),
                        category=lead.get('category', 'general'),
                        entity=lead.get('entity'),
                        confidence=float(lead.get('confidence', 0.5)),
                        tags=tags,
                        raw_data={
                            'search_query': topic,
                            'sources_searched': sources,
                            'signal_strength': signal_strength,
                            'gpt_response': lead,
                            'prompt': user_prompt[:500]
                        }
                    )
                    signals.append(signal)
                except Exception as e:
                    logger.error(f"Failed to create signal from lead: {e}")
                    continue

            return signals

        except json.JSONDecodeError as e:
            logger.error(f"GPT returned invalid JSON: {response[:500]}")
            return []
        except Exception as e:
            logger.error(f"GPT analysis failed: {e}")
            return []


class AIMonitoringAgent(AIBaseAgent):
    """
    AI-powered anomaly detection
    Uses GPT to identify unusual patterns and threshold breaches
    """

    def __init__(self):
        super().__init__("ai_monitor_agent")

    async def process_job(self, job: AgentJob) -> List[Signal]:
        """Monitor feeds for anomalies using GPT"""
        entity = job.params.get('entity', 'market')
        thresholds = job.params.get('thresholds', {})
        time_window = job.params.get('time_window_hours', 24)

        logger.info(f"[AIMonitoringAgent] Monitoring: {entity} (last {time_window}h)")

        # Get recent signals for this entity
        start_ts = (datetime.now(timezone.utc) - timedelta(hours=time_window)).isoformat()
        end_ts = datetime.now(timezone.utc).isoformat()

        recent_signals = self.db.get_signals_time_range(start_ts, end_ts)

        # Filter by entity if specified
        if entity != 'global':
            recent_signals = [s for s in recent_signals
                            if s.get('entity', '').lower() == entity.lower()
                            or entity.lower() in s.get('title', '').lower()]

        if not recent_signals:
            logger.info(f"No recent signals found for {entity}")
            return []

        # Prepare data for GPT analysis
        signal_data = []
        for sig in recent_signals[:30]:
            signal_data.append({
                'timestamp': sig.get('ts', ''),
                'title': sig.get('title', ''),
                'category': sig.get('category', ''),
                'risk_score': sig.get('risk_score', 0),
                'confidence': sig.get('confidence', 0)
            })

        system_prompt = f"""You are an anomaly detection system for risk intelligence.
Analyze time-series data to identify unusual patterns, threshold breaches, or emerging trends.

Focus on detecting:
- Sudden sentiment shifts
- Unusual activity spikes
- Risk score escalations
- Pattern breaks from baseline
- Clustering of related incidents

Entity: {entity}
Time window: Last {time_window} hours
Thresholds: {json.dumps(thresholds)}

Return ONLY valid JSON array with detected anomalies:
[
  {{
    "title": "specific anomaly title",
    "analysis": "detailed explanation of what changed and why it matters",
    "severity": 75,
    "confidence": 0.85,
    "category": "market",
    "tags": ["tag1", "tag2"]
  }}
]

If no significant anomalies detected, return empty array []."""

        user_prompt = f"""Analyze these {len(signal_data)} recent signals for {entity}:

{json.dumps(signal_data, indent=2)}

Identify any anomalies, patterns, or threshold breaches. Focus on actionable insights.
Return JSON array of anomalies (or empty array if none detected)."""

        try:
            response = await self.llm.chat(system_prompt, user_prompt)

            # Clean and parse
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
                    signal = self.create_signal(
                        title=anomaly.get('title', 'Anomaly Detected'),
                        summary=anomaly.get('analysis', 'No analysis'),
                        category=anomaly.get('category', 'general'),
                        entity=entity,
                        confidence=float(anomaly.get('confidence', 0.7)),
                        tags=anomaly.get('tags', [entity, 'anomaly']),
                        raw_data={
                            'anomaly_type': 'ai_detected',
                            'severity': anomaly.get('severity', 50),
                            'thresholds': thresholds,
                            'signals_analyzed': len(signal_data)
                        }
                    )
                    signals.append(signal)
                except Exception as e:
                    logger.error(f"Failed to create anomaly signal: {e}")
                    continue

            return signals

        except json.JSONDecodeError as e:
            logger.error(f"GPT returned invalid JSON: {response[:500]}")
            return []
        except Exception as e:
            logger.error(f"Anomaly detection failed: {e}")
            return []


class AIForecastAgent(AIBaseAgent):
    """
    AI-powered causal impact forecasting
    Uses GPT to analyze events and predict impacts
    """

    def __init__(self):
        super().__init__("ai_forecast_agent")

    async def process_job(self, job: AgentJob) -> List[Signal]:
        """Generate causal forecasts using GPT"""
        event = job.params.get('event', 'policy announcement')
        metric = job.params.get('metric', 'GDP')
        horizon_weeks = job.params.get('horizon_weeks', 4)
        entities = job.entities or []

        logger.info(f"[AIForecastAgent] Forecasting: {event} → {metric} ({horizon_weeks}w)")

        # Get recent related signals for context
        recent_signals = self.db.get_latest_signals(limit=50, min_risk_score=50)

        context_data = []
        for sig in recent_signals[:15]:
            context_data.append({
                'title': sig.get('title', ''),
                'summary': sig.get('summary', '')[:200],
                'category': sig.get('category', '')
            })

        system_prompt = f"""You are an economic and geopolitical forecasting expert.
Analyze events and predict their causal impact on specific metrics.

Event: {event}
Metric: {metric}
Time horizon: {horizon_weeks} weeks
Affected entities: {', '.join(entities) if entities else 'multiple'}

Provide a detailed forecast including:
1. Directional impact (positive/negative/mixed)
2. Magnitude estimate (quantitative range if possible)
3. Top 3-5 causal drivers
4. Confidence level (0.0-1.0)
5. Key uncertainties

Return ONLY valid JSON:
{{
  "title": "Forecast: {event} impact on {metric}",
  "impact_direction": "negative",
  "impact_magnitude": "-1.5% to -0.8%",
  "drivers": ["driver 1", "driver 2", "driver 3"],
  "analysis": "detailed explanation of forecast logic and assumptions",
  "confidence": 0.78,
  "uncertainties": ["uncertainty 1", "uncertainty 2"],
  "category": "macro",
  "tags": ["forecast", "causal"]
}}"""

        user_prompt = f"""Recent context signals:
{json.dumps(context_data, indent=2)}

Forecast the {horizon_weeks}-week impact of "{event}" on {metric}.
Provide quantitative estimates where possible.
Return JSON only."""

        try:
            response = await self.llm.chat(system_prompt, user_prompt)

            # Clean and parse
            response_clean = response.strip()
            if response_clean.startswith('```'):
                lines = response_clean.split('\n')
                response_clean = '\n'.join(lines[1:-1]) if len(lines) > 2 else response_clean
                response_clean = response_clean.replace('```json', '').replace('```', '').strip()

            forecast = json.loads(response_clean)

            signal = self.create_signal(
                title=forecast.get('title', f'Forecast: {event} → {metric}'),
                summary=forecast.get('analysis', 'No analysis provided'),
                category=forecast.get('category', 'macro'),
                entity=metric,
                confidence=float(forecast.get('confidence', 0.7)),
                tags=forecast.get('tags', ['forecast', event, metric]),
                raw_data={
                    'event': event,
                    'metric': metric,
                    'impact_direction': forecast.get('impact_direction'),
                    'impact_magnitude': forecast.get('impact_magnitude'),
                    'drivers': forecast.get('drivers', []),
                    'uncertainties': forecast.get('uncertainties', []),
                    'horizon_weeks': horizon_weeks
                }
            )

            return [signal]

        except json.JSONDecodeError as e:
            logger.error(f"GPT returned invalid JSON: {response[:500]}")
            return []
        except Exception as e:
            logger.error(f"Forecast generation failed: {e}")
            return []


class AISummarizerAgent(AIBaseAgent):
    """
    AI-powered daily digest generation
    Uses GPT to create executive summaries
    """

    def __init__(self):
        super().__init__("ai_summarizer_agent")

    async def process_job(self, job: AgentJob) -> List[Signal]:
        """Generate executive summary using GPT"""
        entity = job.params.get('entity', 'global')
        period_hours = job.params.get('period_hours', 24)
        top_n = job.params.get('top_n', 15)

        logger.info(f"[AISummarizerAgent] Summarizing {entity} (last {period_hours}h)")

        # Get recent signals
        start_ts = (datetime.now(timezone.utc) - timedelta(hours=period_hours)).isoformat()
        end_ts = datetime.now(timezone.utc).isoformat()

        recent_signals = self.db.get_signals_time_range(start_ts, end_ts)

        # Filter by entity
        if entity != 'global':
            recent_signals = [s for s in recent_signals
                            if s.get('entity', '').lower() == entity.lower()
                            or entity.lower() in s.get('title', '').lower()]

        if not recent_signals:
            return []

        # Sort by risk score
        recent_signals = sorted(recent_signals, key=lambda x: x.get('risk_score', 0), reverse=True)
        top_signals = recent_signals[:top_n]

        # Prepare for GPT
        signal_summaries = []
        for sig in top_signals:
            signal_summaries.append({
                'time': sig.get('ts', '')[-8:-3],  # HH:MM
                'title': sig.get('title', ''),
                'category': sig.get('category', ''),
                'risk_score': sig.get('risk_score', 0),
                'summary': sig.get('summary', '')[:300]
            })

        system_prompt = f"""You are an executive briefing analyst.
Create a concise, actionable daily intelligence brief.

Entity: {entity}
Period: Last {period_hours} hours
Signals analyzed: {len(top_signals)}

Structure your brief:
1. **Executive Summary** (2-3 sentences)
2. **Top Risks** (3-5 bullet points with category labels)
3. **Key Themes** (identify patterns across signals)
4. **Recommended Actions** (2-3 specific next steps)

Return ONLY valid JSON:
{{
  "title": "{entity} Risk Brief - Last {period_hours}h",
  "executive_summary": "2-3 sentence overview",
  "top_risks": ["risk 1", "risk 2", "risk 3"],
  "key_themes": ["theme 1", "theme 2"],
  "recommended_actions": ["action 1", "action 2"],
  "analysis": "full brief text in markdown format",
  "confidence": 0.9,
  "tags": ["summary", "digest"]
}}"""

        user_prompt = f"""Signals to summarize:
{json.dumps(signal_summaries, indent=2)}

Create executive brief focusing on actionable insights.
Return JSON only."""

        try:
            response = await self.llm.chat(system_prompt, user_prompt)

            # Clean and parse
            response_clean = response.strip()
            if response_clean.startswith('```'):
                lines = response_clean.split('\n')
                response_clean = '\n'.join(lines[1:-1]) if len(lines) > 2 else response_clean
                response_clean = response_clean.replace('```json', '').replace('```', '').strip()

            brief = json.loads(response_clean)

            signal = self.create_signal(
                title=brief.get('title', f'{entity} Risk Summary'),
                summary=brief.get('analysis', brief.get('executive_summary', '')),
                category='summary',
                entity=entity,
                confidence=float(brief.get('confidence', 0.9)),
                tags=brief.get('tags', ['summary', entity]),
                raw_data={
                    'period_hours': period_hours,
                    'signals_analyzed': len(top_signals),
                    'top_risks': brief.get('top_risks', []),
                    'key_themes': brief.get('key_themes', []),
                    'recommended_actions': brief.get('recommended_actions', [])
                }
            )

            return [signal]

        except json.JSONDecodeError as e:
            logger.error(f"GPT returned invalid JSON: {response[:500]}")
            return []
        except Exception as e:
            logger.error(f"Summary generation failed: {e}")
            return []


class AITrendAnalystAgent(AIBaseAgent):
    """
    NEW: AI-powered trend analysis agent
    Identifies emerging trends across multiple time windows
    """

    def __init__(self):
        super().__init__("ai_trend_analyst")

    async def process_job(self, job: AgentJob) -> List[Signal]:
        """Analyze trends using GPT"""
        category = job.params.get('category', 'all')
        time_windows = job.params.get('time_windows', [24, 72, 168])  # 1d, 3d, 7d

        logger.info(f"[AITrendAnalyst] Analyzing trends: {category}")

        # Get signals across different time windows
        all_signals = []
        for hours in time_windows:
            start_ts = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
            signals = self.db.get_signals_time_range(start_ts, datetime.now(timezone.utc).isoformat())
            all_signals.extend(signals)

        if not all_signals:
            return []

        # Group by time windows
        trend_data = {}
        for window_hours in time_windows:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
            window_signals = []
            for s in all_signals:
                try:
                    ts_str = s.get('ts', '')
                    if ts_str:
                        ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                        if not ts.tzinfo:
                            ts = ts.replace(tzinfo=timezone.utc)
                        if ts >= cutoff:
                            window_signals.append(s)
                except Exception:
                    continue

            # Aggregate stats
            categories = {}
            for s in window_signals:
                cat = s.get('category', 'unknown')
                categories[cat] = categories.get(cat, 0) + 1

            trend_data[f'{window_hours}h'] = {
                'count': len(window_signals),
                'avg_risk': sum(s.get('risk_score', 0) for s in window_signals) / max(len(window_signals), 1),
                'categories': categories
            }

        system_prompt = f"""You are a trend analysis expert.
Identify emerging trends, accelerating risks, and pattern shifts.

Analyze signal data across multiple time windows to detect:
- Trending topics (increasing frequency)
- Risk escalations (increasing severity)
- Category shifts (changing risk distribution)
- Velocity changes (acceleration/deceleration)

Return ONLY valid JSON array:
[
  {{
    "title": "trend title",
    "analysis": "detailed trend analysis with evidence",
    "trend_direction": "accelerating|stable|decelerating",
    "confidence": 0.85,
    "category": "market",
    "tags": ["trend", "emerging"]
  }}
]"""

        user_prompt = f"""Trend data across time windows:
{json.dumps(trend_data, indent=2)}

Recent signal titles:
{json.dumps([s.get('title', '') for s in all_signals[:30]], indent=2)}

Identify 2-4 significant trends. Return JSON array."""

        try:
            response = await self.llm.chat(system_prompt, user_prompt)

            response_clean = response.strip()
            if response_clean.startswith('```'):
                lines = response_clean.split('\n')
                response_clean = '\n'.join(lines[1:-1]) if len(lines) > 2 else response_clean
                response_clean = response_clean.replace('```json', '').replace('```', '').strip()

            trends = json.loads(response_clean)

            signals = []
            for trend in trends:
                signal = self.create_signal(
                    title=trend.get('title', 'Trend Detected'),
                    summary=trend.get('analysis', ''),
                    category=trend.get('category', 'general'),
                    entity=category,
                    confidence=float(trend.get('confidence', 0.7)),
                    tags=trend.get('tags', ['trend']),
                    raw_data={
                        'trend_direction': trend.get('trend_direction'),
                        'time_windows_analyzed': time_windows,
                        'signals_analyzed': len(all_signals)
                    }
                )
                signals.append(signal)

            return signals

        except Exception as e:
            logger.error(f"Trend analysis failed: {e}")
            return []


class AICompetitiveIntelAgent(AIBaseAgent):
    """
    NEW: AI-powered competitive intelligence agent
    Monitors competitors and identifies strategic moves
    """

    def __init__(self):
        super().__init__("ai_competitive_intel")

    async def process_job(self, job: AgentJob) -> List[Signal]:
        """Analyze competitive landscape using GPT"""
        primary_entity = job.params.get('primary_entity', 'company')
        competitors = job.params.get('competitors', [])
        time_window = job.params.get('time_window_hours', 72)

        logger.info(f"[AICompetitiveIntel] Analyzing: {primary_entity} vs {competitors}")

        # Get signals mentioning any entity
        start_ts = (datetime.now(timezone.utc) - timedelta(hours=time_window)).isoformat()
        all_signals = self.db.get_signals_time_range(start_ts, datetime.now(timezone.utc).isoformat())

        # Filter for relevant entities
        entities_to_track = [primary_entity] + competitors
        relevant_signals = []
        for sig in all_signals:
            title_lower = sig.get('title', '').lower()
            entity_lower = sig.get('entity', '').lower()
            if any(ent.lower() in title_lower or ent.lower() in entity_lower
                   for ent in entities_to_track):
                relevant_signals.append(sig)

        if not relevant_signals:
            return []

        # Prepare competitive data
        intel_data = {}
        for entity in entities_to_track:
            entity_signals = [s for s in relevant_signals
                            if entity.lower() in s.get('title', '').lower()
                            or entity.lower() in s.get('entity', '').lower()]

            intel_data[entity] = {
                'signal_count': len(entity_signals),
                'avg_risk': sum(s.get('risk_score', 0) for s in entity_signals) / max(len(entity_signals), 1),
                'recent_titles': [s.get('title', '') for s in entity_signals[:5]]
            }

        system_prompt = f"""You are a competitive intelligence analyst.
Analyze competitive landscape and identify strategic moves, market positioning, and risks.

Primary entity: {primary_entity}
Competitors: {', '.join(competitors)}

Identify:
- Strategic moves (product launches, acquisitions, partnerships)
- Competitive advantages/disadvantages
- Market positioning changes
- Emerging threats or opportunities

Return ONLY valid JSON array:
[
  {{
    "title": "intelligence finding",
    "analysis": "detailed competitive analysis",
    "implication": "what this means for {primary_entity}",
    "confidence": 0.80,
    "category": "market",
    "tags": ["competitive", "strategic"]
  }}
]"""

        user_prompt = f"""Competitive intelligence data:
{json.dumps(intel_data, indent=2)}

Analyze competitive landscape. Focus on actionable insights for {primary_entity}.
Return JSON array (2-3 findings)."""

        try:
            response = await self.llm.chat(system_prompt, user_prompt)

            response_clean = response.strip()
            if response_clean.startswith('```'):
                lines = response_clean.split('\n')
                response_clean = '\n'.join(lines[1:-1]) if len(lines) > 2 else response_clean
                response_clean = response_clean.replace('```json', '').replace('```', '').strip()

            findings = json.loads(response_clean)

            signals = []
            for finding in findings:
                signal = self.create_signal(
                    title=finding.get('title', 'Competitive Intel'),
                    summary=f"{finding.get('analysis', '')}\n\nImplication: {finding.get('implication', '')}",
                    category=finding.get('category', 'market'),
                    entity=primary_entity,
                    confidence=float(finding.get('confidence', 0.75)),
                    tags=finding.get('tags', ['competitive', 'strategic']),
                    raw_data={
                        'primary_entity': primary_entity,
                        'competitors_tracked': competitors,
                        'signals_analyzed': len(relevant_signals)
                    }
                )
                signals.append(signal)

            return signals

        except Exception as e:
            logger.error(f"Competitive intel failed: {e}")
            return []


# AI Agent Registry
AI_AGENT_REGISTRY = {
    'ai_query': AIQueryAgent,
    'ai_monitor': AIMonitoringAgent,
    'ai_forecast': AIForecastAgent,
    'ai_summarizer': AISummarizerAgent,
    'ai_trend': AITrendAnalystAgent,
    'ai_competitive': AICompetitiveIntelAgent
}


def get_ai_agent(agent_type: str) -> AIBaseAgent:
    """Get AI agent instance by type"""
    agent_class = AI_AGENT_REGISTRY.get(agent_type)
    if not agent_class:
        raise ValueError(f"Unknown AI agent type: {agent_type}. Available: {list(AI_AGENT_REGISTRY.keys())}")
    return agent_class()


async def run_ai_agent_job(agent_type: str, job: AgentJob) -> Dict[str, Any]:
    """Run an AI agent job"""
    agent = get_ai_agent(agent_type)
    return await agent.run_job(job)
