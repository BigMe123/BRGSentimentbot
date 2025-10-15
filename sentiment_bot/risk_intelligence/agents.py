#!/usr/bin/env python3
"""
Risk Intelligence Agents
Query, Monitoring, Forecast, and Summarizer agents
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import json

from .database import get_risk_db, Signal
from .enrichment import get_enricher, get_scorer

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


class BaseAgent:
    """Base class for all agents"""

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.db = get_risk_db()
        self.enricher = get_enricher()
        self.scorer = get_scorer()

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
                'agent_params': raw_data
            },
            confidence=confidence,
            impact=impact
        )

        return signal

    def emit_signal(self, signal: Signal) -> bool:
        """Emit signal to database"""
        success = self.db.insert_signal(signal, check_duplicate=True)
        if success:
            logger.info(f"[{self.agent_name}] Emitted signal: {signal.title[:50]}")
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
                'job': job.name
            }

            self.update_heartbeat('healthy')
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


class QueryAgent(BaseAgent):
    """
    Proactively searches heterogeneous sources for weak signals
    Prompt: "Search sources X/Y/Z for early indicators of {topic/entity};
            return 3-5 leads with 1-sentence rationale and confidence 0-1."
    """

    def __init__(self):
        super().__init__("query_agent")

    async def process_job(self, job: AgentJob) -> List[Signal]:
        """Search for weak signals"""
        topic = job.params.get('topic', 'economic indicators')
        sources = job.params.get('sources', ['news', 'social', 'economic'])
        max_leads = job.params.get('max_leads', 5)

        logger.info(f"[QueryAgent] Searching for: {topic}")

        # Simulate weak signal detection
        # In production, this would query actual data sources
        signals = []

        # Example leads (in production, replace with real search)
        mock_leads = [
            {
                'title': f'Unusual trading volume detected in {topic} sector',
                'summary': f'Volume increased by 40% above 30-day average in {topic}-related securities. May indicate insider information or upcoming announcement.',
                'category': 'market',
                'entity': topic,
                'confidence': 0.72,
                'tags': [topic, 'trading', 'volume', 'alert'],
                'link': 'https://example.com/analysis/1'
            },
            {
                'title': f'Social media sentiment shift on {topic}',
                'summary': f'Detected 3x increase in negative sentiment mentions of {topic} on Twitter/Reddit in past 6 hours. Possible emerging issue.',
                'category': 'brand',
                'entity': topic,
                'confidence': 0.65,
                'tags': [topic, 'sentiment', 'social', 'negative'],
                'link': 'https://example.com/social/1'
            },
            {
                'title': f'Regulatory filing mentions {topic} risks',
                'summary': f'New SEC filing from major player includes previously undisclosed {topic} exposure. Potential material risk factor.',
                'category': 'regulatory',
                'entity': topic,
                'confidence': 0.81,
                'tags': [topic, 'regulatory', 'SEC', 'filing'],
                'link': 'https://example.com/filing/1'
            }
        ]

        for lead_data in mock_leads[:max_leads]:
            signal = self.create_signal(
                title=lead_data['title'],
                summary=lead_data['summary'],
                category=lead_data['category'],
                entity=lead_data['entity'],
                confidence=lead_data['confidence'],
                tags=lead_data['tags'],
                raw_data={
                    'link': lead_data['link'],
                    'search_query': topic,
                    'sources_searched': sources,
                    'prompt': f"Search sources {sources} for early indicators of {topic}"
                }
            )
            signals.append(signal)

        return signals


class MonitoringAgent(BaseAgent):
    """
    Watches specific feeds/entities with rules
    Prompt: "Scan today's batch for anomalies in {metric/topic};
            score severity 0-100; short 'so-what'."
    """

    def __init__(self):
        super().__init__("monitor_agent")

    async def process_job(self, job: AgentJob) -> List[Signal]:
        """Monitor feeds for anomalies"""
        entity = job.params.get('entity', 'market')
        thresholds = job.params.get('thresholds', {
            'sentiment_drop': -0.3,
            'volume_spike': 2.0,
            'keyword_frequency': 5
        })

        logger.info(f"[MonitoringAgent] Monitoring: {entity}")

        signals = []

        # Mock anomaly detection (replace with real monitoring)
        anomalies = [
            {
                'title': f'{entity}: Sharp sentiment decline detected',
                'summary': f'Sentiment score dropped from 0.7 to 0.3 in 2 hours. Indicates negative news or event impacting {entity}. Recommend immediate review.',
                'category': 'brand',
                'entity': entity,
                'confidence': 0.88,
                'severity': 75,
                'tags': [entity, 'sentiment', 'decline', 'alert']
            },
            {
                'title': f'{entity}: Unusual keyword frequency spike',
                'summary': f'Keywords "crisis", "concern", "risk" appearing 5x more than baseline in {entity} coverage. Possible emerging issue.',
                'category': 'market',
                'entity': entity,
                'confidence': 0.74,
                'severity': 62,
                'tags': [entity, 'keywords', 'frequency', 'risk']
            }
        ]

        for anomaly in anomalies:
            signal = self.create_signal(
                title=anomaly['title'],
                summary=anomaly['summary'],
                category=anomaly['category'],
                entity=anomaly['entity'],
                confidence=anomaly['confidence'],
                tags=anomaly['tags'],
                raw_data={
                    'anomaly_type': 'threshold_breach',
                    'severity': anomaly['severity'],
                    'thresholds': thresholds,
                    'prompt': f"Scan today's batch for anomalies in {entity}"
                }
            )
            signals.append(signal)

        return signals


class ForecastAgent(BaseAgent):
    """
    Runs causal-impact or short-horizon forecasts after events
    Prompt: "Given event E at T0, estimate 2-6 week directional impact on {metric};
            list top 3 drivers and confidence."
    """

    def __init__(self):
        super().__init__("forecast_agent")

    async def process_job(self, job: AgentJob) -> List[Signal]:
        """Generate causal forecasts"""
        event = job.params.get('event', 'policy announcement')
        metric = job.params.get('metric', 'GDP')
        horizon_weeks = job.params.get('horizon_weeks', 4)

        logger.info(f"[ForecastAgent] Forecasting impact of '{event}' on {metric}")

        signals = []

        # Mock forecast (replace with real models)
        forecast = {
            'title': f'Forecast: {event} impact on {metric}',
            'summary': f'Expected directional impact: -2.5% to -1.2% over {horizon_weeks} weeks. Top drivers: (1) Supply chain disruption (2) Consumer confidence decline (3) Investment pause. Model confidence: 78%.',
            'category': 'macro',
            'entity': metric,
            'confidence': 0.78,
            'tags': [event, metric, 'forecast', 'causal'],
            'drivers': [
                'Supply chain disruption',
                'Consumer confidence decline',
                'Investment pause'
            ],
            'impact_range': [-2.5, -1.2],
            'horizon': horizon_weeks
        }

        signal = self.create_signal(
            title=forecast['title'],
            summary=forecast['summary'],
            category=forecast['category'],
            entity=forecast['entity'],
            confidence=forecast['confidence'],
            tags=forecast['tags'],
            raw_data={
                'event': event,
                'metric': metric,
                'drivers': forecast['drivers'],
                'impact_range': forecast['impact_range'],
                'horizon_weeks': horizon_weeks,
                'model': 'causal_impact_v1',
                'prompt': f"Given event '{event}', estimate {horizon_weeks}-week impact on {metric}"
            }
        )
        signals.append(signal)

        return signals


class SummarizerAgent(BaseAgent):
    """
    Retrieves top N enriched items and produces crisp brief
    Prompt: "Summarize last 24h signals for {entity/region} → 5 bullets (what/so-what/next)."
    """

    def __init__(self):
        super().__init__("summarizer_agent")

    async def process_job(self, job: AgentJob) -> List[Signal]:
        """Summarize recent signals"""
        entity = job.params.get('entity', 'global')
        period_hours = job.params.get('period_hours', 24)
        top_n = job.params.get('top_n', 10)

        logger.info(f"[SummarizerAgent] Summarizing {entity} signals from last {period_hours}h")

        # Get recent signals from DB
        start_ts = (datetime.now(timezone.utc) - timedelta(hours=period_hours)).isoformat()
        end_ts = datetime.now(timezone.utc).isoformat()

        recent_signals = self.db.get_signals_time_range(start_ts, end_ts)

        # Filter by entity if specified
        if entity != 'global':
            recent_signals = [s for s in recent_signals if s.get('entity') == entity]

        # Sort by risk score
        recent_signals = sorted(recent_signals, key=lambda x: x.get('risk_score', 0), reverse=True)
        top_signals = recent_signals[:top_n]

        if not top_signals:
            return []

        # Generate summary
        summary_bullets = []
        categories_seen = set()

        for sig in top_signals[:5]:
            category = sig.get('category', 'general')
            categories_seen.add(category)
            title = sig.get('title', 'Unknown')
            summary_bullets.append(f"• [{category.upper()}] {title}")

        summary_text = "\n".join(summary_bullets)
        analysis = f"""
{len(top_signals)} significant signals detected in last {period_hours}h for {entity}.

Key developments:
{summary_text}

What: Multiple risk indicators across {len(categories_seen)} categories.
So what: Elevated attention required in {', '.join(categories_seen)} domains.
Next: Monitor for escalation; review specific signals for action items.
"""

        signal = self.create_signal(
            title=f'{entity} Risk Summary - Last {period_hours}h',
            summary=analysis.strip(),
            category='summary',
            entity=entity,
            confidence=0.9,
            tags=[entity, 'summary', 'digest'] + list(categories_seen),
            raw_data={
                'period_hours': period_hours,
                'signals_analyzed': len(top_signals),
                'top_signals': [s.get('id') for s in top_signals],
                'prompt': f"Summarize last {period_hours}h signals for {entity}"
            }
        )

        return [signal]


# Agent Registry
AGENT_REGISTRY = {
    'query': QueryAgent,
    'monitor': MonitoringAgent,
    'forecast': ForecastAgent,
    'summarizer': SummarizerAgent
}


def get_agent(agent_type: str) -> BaseAgent:
    """Get agent instance by type"""
    agent_class = AGENT_REGISTRY.get(agent_type)
    if not agent_class:
        raise ValueError(f"Unknown agent type: {agent_type}")
    return agent_class()


async def run_agent_job(agent_type: str, job: AgentJob) -> Dict[str, Any]:
    """Run an agent job"""
    agent = get_agent(agent_type)
    return await agent.run_job(job)
