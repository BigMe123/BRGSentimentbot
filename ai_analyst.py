"""
BRG AI Analyst — standalone module for GPT-powered analysis of scan results.
Used by dashboard.py but fully independent from the sentiment bot pipeline.
"""

import os
import json
from pathlib import Path
from collections import Counter
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


BRG_SYSTEM_PROMPT = (
    "You are an intelligence analyst at Boston Risk Group (BRG), a strategic intelligence and "
    "geopolitical risk analysis organization serving embassies, NGOs, and non-profits.\n\n"
    "Your analysis should be: evidence-based (cite specific data), balanced, actionable, "
    "professional, and structured with clear headings. Note data limitations. "
    "Use hedging for uncertain assessments (e.g., 'likely', 'suggests')."
)

PRESETS = {
    "Intelligence Brief": (
        "Generate a professional intelligence brief. Include: Executive Summary, "
        "Key Findings (bullets), Risk Assessment by region, Emerging Threats, "
        "Opportunities, and Recommended Actions. Cite specific articles."
    ),
    "Country Risk Profile": (
        "For each country mentioned 5+ times, generate: sentiment trend, key drivers, "
        "risk level (low/medium/high/critical), and 1-2 sentence outlook."
    ),
    "Threat Assessment": (
        "Identify top 5-10 threats. For each: description, severity (1-5), "
        "likelihood (1-5), affected regions, monitoring indicators."
    ),
    "Executive Summary": (
        "Concise executive summary (250-400 words) of the global news landscape. "
        "Key developments, sentiment shifts, actors, and policy implications."
    ),
    "Trend Analysis": (
        "Analyze patterns: recurring themes, sentiment clusters, geographic hotspots, "
        "cross-cutting issues, escalation/de-escalation signals."
    ),
    "Stakeholder Map": (
        "Map key actors: role in events, relationships, sentiment direction, influence. "
        "Identify alliances and tensions."
    ),
    "OSINT Assessment": (
        "Evaluate from OSINT perspective: source reliability, information gaps, "
        "biases, verification needs, collection recommendations."
    ),
}


def build_data_snapshot(articles, analysis, max_articles=80):
    """Build a concise text snapshot of scan data for GPT context."""
    lines = []

    sentiment_total = analysis.get("sentiment_total", 0)
    breakdown = analysis.get("breakdown", {})
    lines.append(f"SCAN: {len(articles)} articles. Sentiment: {sentiment_total:+d}.")
    lines.append(f"Pos: {breakdown.get('positive', breakdown.get('pos', 0))}, "
                 f"Neg: {breakdown.get('negative', breakdown.get('neg', 0))}, "
                 f"Neu: {breakdown.get('neutral', breakdown.get('neu', 0))}")
    lines.append(f"Themes: {', '.join(analysis.get('top_triggers', []))}")
    lines.append("")

    # Countries
    country_counts = Counter()
    country_sentiments = {}
    for a in articles:
        score = a.get("sentiment", {}).get("score", 0)
        for e in a.get("entities", []):
            if e.get("type") == "GPE":
                name = e["text"]
                country_counts[name] += 1
                country_sentiments.setdefault(name, []).append(score)

    if country_counts:
        lines.append("COUNTRIES (top 20):")
        for name, count in country_counts.most_common(20):
            avg = sum(country_sentiments[name]) / len(country_sentiments[name])
            lines.append(f"  {name}: {count} mentions, sentiment {avg:+.2f}")
        lines.append("")

    # Sources
    src_counts = Counter(a.get("source", "?") for a in articles)
    lines.append(f"SOURCES ({len(src_counts)}): " +
                 ", ".join(f"{s} ({c})" for s, c in src_counts.most_common(10)))
    lines.append("")

    # Articles
    sorted_arts = sorted(articles, key=lambda a: abs(a.get("sentiment", {}).get("score", 0)), reverse=True)
    lines.append(f"ARTICLES (top {min(max_articles, len(sorted_arts))} by sentiment):")
    for a in sorted_arts[:max_articles]:
        score = a.get("sentiment", {}).get("score", 0)
        risk = (a.get("signals") or {}).get("risk_level", "normal")
        themes = (a.get("signals") or {}).get("themes", [])
        entities_str = ", ".join(e.get("text", "") for e in a.get("entities", [])[:5])
        lines.append(f"  [{score:+.2f}] [{risk}] {a.get('source', '?')}: {a.get('title', '?')}")
        if themes or entities_str:
            lines.append(f"    Themes: {', '.join(themes) or '-'} | Entities: {entities_str or '-'}")
        if a.get("ai_summary"):
            lines.append(f"    Summary: {a['ai_summary']}")

    # Events
    all_events = []
    for a in articles:
        for ev in a.get("events", []):
            all_events.append(ev)
    if all_events:
        lines.append(f"\nEVENTS ({len(all_events)}):")
        for ev in all_events[:30]:
            actor = ev.get("actor", {}).get("name", "?")
            verb = ev.get("action", {}).get("verb", "?")
            receiver = (ev.get("receiver") or {}).get("name", "")
            tone = ev.get("tone", 0)
            recv = f" -> {receiver}" if receiver else ""
            lines.append(f"  {actor} {verb}{recv} (tone: {tone:+d})")

    return "\n".join(lines)


def call_openai(user_prompt: str, data_snapshot: str):
    """Call OpenAI and return response text."""
    try:
        from openai import OpenAI
    except ImportError:
        return "Error: `pip install openai` first."

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return "Error: OPENAI_API_KEY not set in .env"

    try:
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": BRG_SYSTEM_PROMPT},
                {"role": "user", "content": f"DATA:\n{data_snapshot}\n\nREQUEST:\n{user_prompt}"},
            ],
            temperature=0.3,
            max_tokens=4000,
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"Error: {e}"
