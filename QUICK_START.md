# 🚀 Risk Intelligence System - Quick Start

## One-Minute Setup

```bash
# 1. Install (30 seconds)
pip install fastapi uvicorn pydantic spacy sentence-transformers
python -m spacy download en_core_web_sm

# Optional GUI
pip install PyQt6 matplotlib

# 2. Launch (10 seconds)
python run.py
# → Select Option 23
# → Choose: dashboard / api_server / run_agents

# 3. Verify (20 seconds)
python test_risk_intelligence.py
```

## 🎯 Quick Reference

### Launch Commands
- `python run.py` → Interactive menu (Option 23)
- `python -m sentiment_bot.risk_intelligence.api` → API server
- `python -m sentiment_bot.risk_intelligence.dashboard` → GUI
- `python test_risk_intelligence.py` → Run tests
- `python demo_risk_intelligence.py` → Full demo

### API Endpoints (port 8765)
- `GET /api/latest` → Latest signals
- `GET /api/stats` → Statistics
- `GET /api/entity/{entity}` → Entity signals
- `POST /api/agent/run` → Run agent job
- `GET /docs` → Swagger UI

### Python API
```python
from sentiment_bot.risk_intelligence import get_risk_db, run_agent_job, AgentJob
db = get_risk_db()
signals = db.get_latest_signals(limit=50)
```

### 4 Agents
- **query**: Weak signal detection
- **monitor**: Anomaly surveillance  
- **forecast**: Causal impact analysis
- **summarizer**: Daily digest generation

**Status**: ✅ Production Ready | **Version**: 3.0.0
