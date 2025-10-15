#!/usr/bin/env python3
"""
Risk Intelligence REST API
FastAPI endpoints for signal access and agent control
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, timezone
import asyncio
import hmac
import hashlib

from .database import get_risk_db
from .agents import AgentJob, run_agent_job

app = FastAPI(title="BRG Risk Intelligence API", version="3.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request/Response Models
class SignalResponse(BaseModel):
    id: str
    ts: str
    source: str
    category: str
    entity: Optional[str]
    title: str
    summary: str
    risk_score: float
    confidence: float
    impact: str
    tags: List[str]
    link: Optional[str]


class StatsResponse(BaseModel):
    total_signals: int
    by_category: Dict[str, int]
    by_source: Dict[str, int]
    avg_risk_score: float
    high_risk_count: int
    last_24h: int


class AgentJobRequest(BaseModel):
    agent_type: str
    job_name: str
    params: Dict[str, Any]
    entities: List[str] = []


class WebhookSignalRequest(BaseModel):
    title: str
    summary: str
    category: str
    entity: Optional[str] = None
    confidence: float = 0.8
    tags: List[str] = []
    link: Optional[str] = None
    source_signature: Optional[str] = None


# Endpoints
@app.get("/")
async def root():
    """API root"""
    return {
        "service": "BRG Risk Intelligence API",
        "version": "3.0.0",
        "status": "operational"
    }


@app.get("/api/latest", response_model=List[SignalResponse])
async def get_latest_signals(
    limit: int = 50,
    category: Optional[str] = None,
    min_risk_score: float = 0.0
):
    """Get latest signals with optional filters"""
    db = get_risk_db()
    signals = db.get_latest_signals(limit, category, min_risk_score)

    return [
        SignalResponse(
            id=s['id'],
            ts=s['ts'],
            source=s['source'],
            category=s['category'] or 'general',
            entity=s['entity'],
            title=s['title'],
            summary=s['summary'] or '',
            risk_score=s['risk_score'] or 0.0,
            confidence=s['confidence'] or 0.0,
            impact=s['impact'] or 'medium',
            tags=s['tags'],
            link=s['link']
        )
        for s in signals
    ]


@app.get("/api/historical", response_model=List[SignalResponse])
async def get_historical_signals(
    from_ts: Optional[str] = None,
    to_ts: Optional[str] = None,
    category: Optional[str] = None
):
    """Get signals in time range"""
    db = get_risk_db()

    # Default to last 7 days
    if not from_ts:
        from_ts = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    if not to_ts:
        to_ts = datetime.now(timezone.utc).isoformat()

    signals = db.get_signals_time_range(from_ts, to_ts, category)

    return [
        SignalResponse(
            id=s['id'],
            ts=s['ts'],
            source=s['source'],
            category=s['category'] or 'general',
            entity=s['entity'],
            title=s['title'],
            summary=s['summary'] or '',
            risk_score=s['risk_score'] or 0.0,
            confidence=s['confidence'] or 0.0,
            impact=s['impact'] or 'medium',
            tags=s.get('tags', []),
            link=s['link']
        )
        for s in signals
    ]


@app.get("/api/entity/{entity}", response_model=List[SignalResponse])
async def get_entity_signals(entity: str, limit: int = 20):
    """Get signals for specific entity"""
    db = get_risk_db()
    signals = db.get_signals_by_entity(entity, limit)

    return [
        SignalResponse(
            id=s['id'],
            ts=s['ts'],
            source=s['source'],
            category=s['category'] or 'general',
            entity=s['entity'],
            title=s['title'],
            summary=s['summary'] or '',
            risk_score=s['risk_score'] or 0.0,
            confidence=s['confidence'] or 0.0,
            impact=s['impact'] or 'medium',
            tags=s.get('tags', []),
            link=s['link']
        )
        for s in signals
    ]


@app.get("/api/stats", response_model=StatsResponse)
async def get_stats():
    """Get aggregate statistics"""
    db = get_risk_db()
    stats = db.get_signal_stats()

    return StatsResponse(
        total_signals=stats['total_signals'],
        by_category=stats['by_category'],
        by_source=stats['by_source'],
        avg_risk_score=stats['avg_risk_score'],
        high_risk_count=stats['high_risk_count'],
        last_24h=stats['last_24h']
    )


@app.get("/api/analyze")
async def analyze_recent_signals(
    entity: Optional[str] = None,
    period_hours: int = 24,
    category: Optional[str] = None
):
    """Analyze recent signals and return brief"""
    db = get_risk_db()

    start_ts = (datetime.now(timezone.utc) - timedelta(hours=period_hours)).isoformat()
    end_ts = datetime.now(timezone.utc).isoformat()

    signals = db.get_signals_time_range(start_ts, end_ts, category)

    if entity:
        signals = [s for s in signals if s.get('entity') == entity]

    # Sort by risk score
    signals = sorted(signals, key=lambda x: x.get('risk_score', 0), reverse=True)

    # Generate brief
    total = len(signals)
    high_risk = len([s for s in signals if s.get('risk_score', 0) > 70])
    categories = {}
    for s in signals:
        cat = s.get('category', 'general')
        categories[cat] = categories.get(cat, 0) + 1

    top_signals = signals[:5]

    brief = {
        'period_hours': period_hours,
        'entity': entity or 'global',
        'total_signals': total,
        'high_risk_signals': high_risk,
        'categories': categories,
        'top_signals': [
            {
                'title': s['title'],
                'risk_score': s.get('risk_score', 0),
                'category': s.get('category', 'general'),
                'summary': s.get('summary', '')[:200]
            }
            for s in top_signals
        ],
        'recommendation': 'Monitor closely' if high_risk > 0 else 'Normal operations'
    }

    return brief


@app.post("/api/agent/run")
async def run_agent(job_request: AgentJobRequest, background_tasks: BackgroundTasks):
    """Run an agent job"""
    job = AgentJob(
        name=job_request.job_name,
        params=job_request.params,
        entities=job_request.entities
    )

    # Run in background
    result = await run_agent_job(job_request.agent_type, job)

    return result


@app.post("/api/partner/webhook")
async def receive_partner_signal(webhook_data: WebhookSignalRequest):
    """
    Receive external signals from partners
    Requires signature for security in production
    """
    # In production: verify signature
    # if not verify_signature(webhook_data.source_signature, webhook_data.dict()):
    #     raise HTTPException(status_code=401, detail="Invalid signature")

    from .database import Signal
    db = get_risk_db()

    # Create signal
    signal = Signal(
        id=db.generate_signal_id(webhook_data.title, 'partner_webhook', datetime.now(timezone.utc).isoformat()),
        ts=datetime.now(timezone.utc).isoformat(),
        source='partner_webhook',
        category=webhook_data.category,
        entity=webhook_data.entity,
        title=webhook_data.title,
        summary=webhook_data.summary,
        risk_score=webhook_data.confidence * 100,  # Convert to 0-100
        tags=webhook_data.tags,
        link=webhook_data.link,
        raw={'webhook_source': 'partner'},
        confidence=webhook_data.confidence,
        impact='medium'
    )

    success = db.insert_signal(signal)

    if not success:
        raise HTTPException(status_code=409, detail="Duplicate signal")

    return {"status": "accepted", "signal_id": signal.id}


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    db = get_risk_db()
    agent_status = db.get_agent_status()

    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agents": agent_status
    }


def verify_signature(signature: str, data: Dict) -> bool:
    """Verify webhook signature (implement with your secret)"""
    # Example HMAC verification
    secret = "your-webhook-secret"  # Store securely in env
    import json
    payload = json.dumps(data, sort_keys=True)
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


# Run server
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8765)
