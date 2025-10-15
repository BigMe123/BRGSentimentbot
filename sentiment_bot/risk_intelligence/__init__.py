#!/usr/bin/env python3
"""
Risk Intelligence Module
Part 3 of BRG Intelligence Platform
"""

from .database import get_risk_db, Signal, RiskDatabase
from .enrichment import get_enricher, get_scorer, TextEnricher, RiskScorer
from .agents import (
    BaseAgent, QueryAgent, MonitoringAgent, ForecastAgent, SummarizerAgent,
    AgentJob, get_agent, run_agent_job, AGENT_REGISTRY
)

__version__ = "3.0.0"

__all__ = [
    'get_risk_db', 'Signal', 'RiskDatabase',
    'get_enricher', 'get_scorer', 'TextEnricher', 'RiskScorer',
    'BaseAgent', 'QueryAgent', 'MonitoringAgent', 'ForecastAgent', 'SummarizerAgent',
    'AgentJob', 'get_agent', 'run_agent_job', 'AGENT_REGISTRY'
]
