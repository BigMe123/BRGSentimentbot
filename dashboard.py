"""
BRG Sentiment Bot — Streamlit Dashboard
Run: streamlit run dashboard.py
"""

import streamlit as st
import json
import subprocess
import sys
import os
import re
import pandas as pd
from pathlib import Path
from datetime import datetime
from collections import Counter

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from ai_analyst import PRESETS as AI_PRESETS, build_data_snapshot, call_openai

st.set_page_config(
    page_title="Boston Risk Group",
    page_icon="assets/brg_logo.png",
    layout="wide",
    initial_sidebar_state="expanded",
)

OUTPUT_DIR = Path("./output")
OUTPUT_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# BRG Theme — Dark / Light toggle
# ---------------------------------------------------------------------------

if "brg_theme" not in st.session_state:
    st.session_state.brg_theme = "dark"

_THEMES = {
    "dark": {
        "bg":       "#0b1018",
        "bg2":      "#0f1520",
        "panel":    "#111827",
        "panel_lt": "#151d2b",
        "accent":   "#4f8cff",
        "accent_lt":"#8ab4ff",
        "gold":     "#c7a75a",
        "pos":      "#28a46f",
        "neg":      "#d64a4a",
        "neu":      "#8993a4",
        "warn":     "#d9902f",
        "text":     "#eef2f7",
        "muted":    "#9aa4b2",
        "border":   "#263244",
        "sidebar_bg": "#0b1018",
        "input_bg": "#111827",
        "hover_bg": "rgba(79,140,255,0.08)",
        "shadow":   "0 1px 2px rgba(0,0,0,0.24)",
        "logo":     "assets/brg_logo_white.png",
    },
    "light": {
        "bg":       "#f7f8fb",
        "bg2":      "#eef1f6",
        "panel":    "#ffffff",
        "panel_lt": "#f8fafc",
        "accent":   "#255fb8",
        "accent_lt":"#477ed6",
        "gold":     "#8b6914",
        "pos":      "#177a52",
        "neg":      "#b83434",
        "neu":      "#667085",
        "warn":     "#a25f16",
        "text":     "#101428",
        "muted":    "#5a6170",
        "border":   "#d7dde8",
        "sidebar_bg": "#ffffff",
        "input_bg": "#ffffff",
        "hover_bg": "rgba(37,95,184,0.06)",
        "shadow":   "0 1px 2px rgba(16,24,40,0.08)",
        "logo":     "assets/brg_logo.png",
    },
}

t = _THEMES[st.session_state.brg_theme]

st.markdown(f"""
<style>
    /* --- BRG palette ({"dark" if st.session_state.brg_theme == "dark" else "light"}) --- */
    :root {{
        --brg-bg:       {t["bg"]};
        --brg-bg2:      {t["bg2"]};
        --brg-panel:    {t["panel"]};
        --brg-panel-lt: {t["panel_lt"]};
        --brg-accent:   {t["accent"]};
        --brg-accent-lt:{t["accent_lt"]};
        --brg-gold:     {t["gold"]};
        --brg-pos:      {t["pos"]};
        --brg-neg:      {t["neg"]};
        --brg-neu:      {t["neu"]};
        --brg-warn:     {t["warn"]};
        --brg-text:     {t["text"]};
        --brg-muted:    {t["muted"]};
        --brg-border:   {t["border"]};
        --brg-shadow:   {t["shadow"]};
    }}

    /* Hide Streamlit branding */
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    header {{visibility: hidden;}}

    html, body, [class*="css"] {{
        font-feature-settings: 'cv11', 'ss01', 'ss03';
        -webkit-font-smoothing: antialiased;
    }}

    /* Main area */
    .stApp {{
        background: var(--brg-bg);
    }}

    .block-container {{ padding-top: 1.1rem; padding-bottom: 4rem; max-width: 1440px; }}

    /* Sidebar — locked open, cannot be collapsed/hidden/slid */
    [data-testid="stSidebar"] {{
        background: {t["sidebar_bg"]};
        border-right: 1px solid var(--brg-border);
        min-width: 280px !important;
        max-width: 280px !important;
        width: 280px !important;
        transform: none !important;
        visibility: visible !important;
        display: block !important;
        position: relative !important;
    }}
    /* Hide the chevron / collapse button so the user cannot toggle the sidebar */
    [data-testid="stSidebarCollapseButton"],
    [data-testid="collapsedControl"],
    [data-testid="stSidebarCollapsedControl"],
    button[kind="header"][data-testid="baseButton-header"] {{
        display: none !important;
        visibility: hidden !important;
        pointer-events: none !important;
    }}
    /* Ensure the main content always shifts to the right of the (always-visible) sidebar */
    section[data-testid="stSidebar"] + section,
    [data-testid="stSidebarUserContent"] {{
        display: block !important;
    }}
    /* Prevent the slim "edge resizer" handle from appearing */
    [data-testid="stSidebar"] > div:first-child > div:first-child {{
        pointer-events: auto;
    }}
    [data-testid="stSidebar"] [data-testid="stSidebarNav"] {{
        display: block !important;
    }}
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {{
        color: var(--brg-muted);
        font-size: 0.85rem;
    }}
    /* Sidebar nav radio rows look like nav items */
    [data-testid="stSidebar"] [role="radiogroup"] > label {{
        border: 1px solid transparent;
        border-radius: 5px;
        padding: 6px 10px;
        margin: 1px 0;
        transition: all 0.15s ease;
    }}
    [data-testid="stSidebar"] [role="radiogroup"] > label:hover {{
        background: {t["hover_bg"]};
        border-color: var(--brg-border);
    }}

    /* Metric cards */
    [data-testid="stMetric"] {{
        background: var(--brg-panel);
        border: 1px solid var(--brg-border);
        border-radius: 6px;
        padding: 12px 14px;
        box-shadow: var(--brg-shadow);
    }}
    [data-testid="stMetric"]:hover {{
        border-color: var(--brg-accent);
    }}
    [data-testid="stMetric"] label {{
        color: var(--brg-muted) !important;
        font-size: 0.7rem !important;
        text-transform: uppercase;
        letter-spacing: 0;
        font-weight: 600 !important;
    }}
    [data-testid="stMetric"] [data-testid="stMetricValue"] {{
        color: var(--brg-text) !important;
        font-weight: 600;
        font-size: 1.55rem;
    }}

    /* Data tables */
    [data-testid="stDataFrame"] {{
        border: 1px solid var(--brg-border);
        border-radius: 6px;
        box-shadow: var(--brg-shadow);
    }}

    /* Buttons */
    .stButton > button {{
        border: 1px solid var(--brg-border);
        background: var(--brg-panel);
        color: var(--brg-text);
        border-radius: 5px;
        font-weight: 500;
        transition: all 0.15s ease;
    }}
    .stButton > button:hover {{
        border-color: var(--brg-accent);
        background: {t["hover_bg"]};
    }}
    .stButton > button[kind="primary"] {{
        background: var(--brg-accent);
        border-color: var(--brg-accent);
        color: white;
        box-shadow: none;
    }}

    /* Expanders */
    [data-testid="stExpander"] {{
        border: 1px solid var(--brg-border);
        border-radius: 6px;
        background: var(--brg-panel);
    }}

    /* Page dividers */
    hr {{ border-color: var(--brg-border); }}

    /* Selectbox / inputs */
    [data-testid="stSelectbox"] > div > div,
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea {{
        border-color: var(--brg-border);
        background: {t["input_bg"]};
        border-radius: 5px;
    }}

    /* Custom header bar */
    .brg-header {{
        display: flex;
        align-items: center;
        gap: 14px;
        padding: 10px 0 12px;
        margin-bottom: 12px;
        border-bottom: 1px solid var(--brg-border);
        position: relative;
    }}
    .brg-header::after {{
        content: '';
        position: absolute;
        left: 0; bottom: -1px;
        width: 72px; height: 2px;
        background: var(--brg-accent);
    }}
    .brg-header h1 {{
        font-size: 1.55rem;
        font-weight: 700;
        color: var(--brg-text);
        margin: 0;
        letter-spacing: 0;
    }}
    .brg-header .brg-sub {{
        font-size: 0.72rem;
        color: var(--brg-muted);
        text-transform: uppercase;
        letter-spacing: 0;
    }}

    /* Classification banner */
    .brg-classification {{
        text-align: center;
        font-size: 0.68rem;
        color: var(--brg-gold);
        letter-spacing: 0;
        text-transform: uppercase;
        padding: 6px 0;
        border-top: 1px solid var(--brg-border);
        margin-top: 32px;
    }}

    /* Section headers */
    .brg-section {{
        font-size: 0.68rem;
        color: var(--brg-accent-lt);
        text-transform: uppercase;
        letter-spacing: 0;
        font-weight: 700;
        margin: 24px 0 8px 0;
        display: flex;
        align-items: center;
        gap: 10px;
    }}
    .brg-section::before {{
        content: '';
        width: 4px; height: 14px;
        background: var(--brg-accent);
        border-radius: 2px;
    }}

    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 0;
        border-bottom: 1px solid var(--brg-border);
    }}
    .stTabs [data-baseweb="tab"] {{
        color: var(--brg-muted);
        padding: 9px 18px;
        font-weight: 500;
    }}
    .stTabs [aria-selected="true"] {{
        color: var(--brg-accent-lt) !important;
        border-bottom: 2px solid var(--brg-accent) !important;
    }}

    /* BRG cards (custom HTML) */
    .brg-card {{
        background: var(--brg-panel);
        border: 1px solid var(--brg-border);
        border-radius: 6px;
        padding: 14px 16px;
        box-shadow: var(--brg-shadow);
    }}
    .brg-card-row {{
        display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 14px;
    }}
    .brg-kpi {{
        flex: 1 1 180px;
        background: var(--brg-panel);
        border: 1px solid var(--brg-border);
        border-radius: 6px;
        padding: 12px 14px;
        box-shadow: var(--brg-shadow);
        position: relative;
        overflow: hidden;
    }}
    .brg-kpi-label {{
        font-size: 0.66rem; color: var(--brg-muted);
        text-transform: uppercase; letter-spacing: 0; font-weight: 600;
    }}
    .brg-kpi-value {{
        font-size: 1.45rem; font-weight: 700; color: var(--brg-text);
        margin-top: 2px;
    }}
    .brg-kpi-delta {{ font-size: 0.78rem; margin-top: 2px; }}
    .brg-kpi.pos .brg-kpi-delta {{ color: var(--brg-pos); }}
    .brg-kpi.neg .brg-kpi-delta {{ color: var(--brg-neg); }}
    .brg-kpi-bar {{
        position: absolute; left: 0; bottom: 0; height: 3px;
        background: var(--brg-accent);
    }}

    /* Sentiment pills */
    .brg-pill {{
        display: inline-flex; align-items: center; gap: 6px;
        padding: 2px 8px; border-radius: 4px;
        font-size: 0.72rem; font-weight: 600; letter-spacing: 0;
        border: 1px solid var(--brg-border);
    }}
    .brg-pill.pos {{ color: var(--brg-pos); border-color: rgba(22,199,132,0.35); background: rgba(22,199,132,0.08); }}
    .brg-pill.neg {{ color: var(--brg-neg); border-color: rgba(234,57,67,0.35); background: rgba(234,57,67,0.08); }}
    .brg-pill.neu {{ color: var(--brg-muted); }}
    .brg-pill.warn {{ color: var(--brg-warn); border-color: rgba(247,147,26,0.35); background: rgba(247,147,26,0.08); }}

    /* Risk-level badge */
    .brg-risk {{
        display: inline-block; padding: 1px 7px; border-radius: 4px;
        font-size: 0.7rem; font-weight: 600; letter-spacing: 0;
    }}
    .brg-risk.critical {{ background: rgba(234,57,67,0.18); color: var(--brg-neg); }}
    .brg-risk.high     {{ background: rgba(247,147,26,0.18); color: var(--brg-warn); }}
    .brg-risk.elevated {{ background: rgba(212,177,94,0.18); color: var(--brg-gold); }}
    .brg-risk.normal   {{ background: rgba(126,138,160,0.14); color: var(--brg-muted); }}

    /* Theme toggle button */
    .brg-theme-toggle {{
        cursor: pointer;
        text-align: center;
        padding: 4px 12px;
        border-radius: 6px;
        font-size: 0.75rem;
        letter-spacing: 0;
        color: var(--brg-muted);
        border: 1px solid var(--brg-border);
        margin-top: 4px;
    }}

    .brg-formula {{
        background: var(--brg-panel-lt);
        border: 1px solid var(--brg-border);
        border-left: 3px solid var(--brg-accent);
        border-radius: 6px;
        padding: 10px 12px;
        margin: 8px 0 12px;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        font-size: 0.82rem;
        color: var(--brg-text);
    }}
    .brg-note {{
        color: var(--brg-muted);
        font-size: 0.86rem;
        line-height: 1.45;
    }}
    .brg-check {{
        display: flex;
        align-items: flex-start;
        gap: 10px;
        padding: 9px 0;
        border-bottom: 1px solid var(--brg-border);
    }}
    .brg-check:last-child {{ border-bottom: 0; }}
    .brg-check .status {{
        min-width: 74px;
        font-size: 0.7rem;
        text-transform: uppercase;
        font-weight: 700;
        color: var(--brg-muted);
    }}
    .brg-check.ok .status {{ color: var(--brg-pos); }}
    .brg-check.warn .status {{ color: var(--brg-warn); }}
    .brg-check.fail .status {{ color: var(--brg-neg); }}
    .muted {{ color: var(--brg-muted); }}

    /* Subtle scrollbar */
    ::-webkit-scrollbar {{ width: 10px; height: 10px; }}
    ::-webkit-scrollbar-thumb {{ background: var(--brg-border); border-radius: 6px; }}
    ::-webkit-scrollbar-thumb:hover {{ background: var(--brg-accent); }}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_summaries():
    out = []
    for f in OUTPUT_DIR.glob("run_summary_*.json"):
        try: d = json.loads(f.read_text()); d["_file"] = f.name; out.append(d)
        except Exception: pass
    out.sort(key=lambda s: s.get("started_at", ""), reverse=True)
    return out

def load_articles(run_id):
    p = OUTPUT_DIR / f"articles_{run_id}.jsonl"
    if not p.exists(): return []
    arts = []
    for ln in p.read_text().splitlines():
        if ln.strip():
            try: arts.append(json.loads(ln))
            except Exception: pass
    return arts

def load_events(run_id):
    p = OUTPUT_DIR / f"events_{run_id}.jsonl"
    if not p.exists(): return []
    evts = []
    for ln in p.read_text().splitlines():
        if ln.strip():
            try: evts.append(json.loads(ln))
            except Exception: pass
    return evts

def sent_label(score):
    if score > 0.05: return "POS"
    if score < -0.05: return "NEG"
    return "NEU"


# ---------------------------------------------------------------------------
# Modern visual helpers (used by Results + Risk Intelligence)
# ---------------------------------------------------------------------------

def kpi_ribbon(items):
    """items: list of dicts {label, value, delta?, tone? ('pos'|'neg'|'')}"""
    cards = []
    for it in items:
        tone = it.get("tone", "")
        delta = it.get("delta", "")
        cls = f"brg-kpi {tone}".strip()
        delta_html = f'<div class="brg-kpi-delta">{delta}</div>' if delta else ''
        cards.append(
            f'<div class="{cls}">'
            f'<div class="brg-kpi-label">{it["label"]}</div>'
            f'<div class="brg-kpi-value">{it["value"]}</div>'
            f'{delta_html}'
            f'<div class="brg-kpi-bar" style="width:{it.get("bar", 35)}%"></div>'
            f'</div>'
        )
    st.markdown(f'<div class="brg-card-row">{"".join(cards)}</div>',
                unsafe_allow_html=True)


def risk_pill(label, kind="neu"):
    return f'<span class="brg-pill {kind}">{label}</span>'


def risk_gauge(score, label="Sentiment", height=190):
    """Semicircular gauge for a -1..1 score."""
    try:
        import plotly.graph_objects as go
    except ImportError:
        st.metric(label, f"{score:+.2f}")
        return
    s = max(-1.0, min(1.0, float(score)))
    color = (
        _THEMES[st.session_state.brg_theme]["pos"] if s > 0.05
        else _THEMES[st.session_state.brg_theme]["neg"] if s < -0.05
        else _THEMES[st.session_state.brg_theme]["neu"]
    )
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=round(s, 2),
        number={"valueformat": ".2f", "font": {"size": 28}},
        gauge={
            "axis": {"range": [-1, 1], "tickwidth": 0,
                     "tickvals": [-1, -0.5, 0, 0.5, 1],
                     "ticktext": ["-1.0", "-0.5", "0", "+0.5", "+1.0"]},
            "bar": {"color": color, "thickness": 0.30},
            "bgcolor": "rgba(0,0,0,0)",
            "borderwidth": 0,
            "steps": [
                {"range": [-1.0, -0.2], "color": "rgba(234,57,67,0.18)"},
                {"range": [-0.2, 0.2],  "color": "rgba(126,138,160,0.10)"},
                {"range": [0.2, 1.0],   "color": "rgba(22,199,132,0.18)"},
            ],
        },
        title={"text": label, "font": {"size": 12, "color": _THEMES[st.session_state.brg_theme]["muted"]}},
    ))
    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=30, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font={"color": _THEMES[st.session_state.brg_theme]["text"]},
    )
    st.plotly_chart(fig, use_container_width=True)


def sentiment_distribution_chart(scores):
    """Histogram of article sentiment scores using Plotly with theme colors."""
    try:
        import plotly.graph_objects as go
        import numpy as np
    except ImportError:
        return None
    if not scores:
        return None
    th = _THEMES[st.session_state.brg_theme]
    bins = np.linspace(-1.0, 1.0, 21)
    counts, edges = np.histogram(scores, bins=bins)
    centers = (edges[:-1] + edges[1:]) / 2
    colors = [
        th["neg"] if c < -0.05 else (th["pos"] if c > 0.05 else th["neu"])
        for c in centers
    ]
    fig = go.Figure(go.Bar(x=centers, y=counts, marker_color=colors,
                           marker_line_width=0, hovertemplate="%{y} articles<extra></extra>"))
    fig.update_layout(
        height=240, margin=dict(l=10, r=10, t=10, b=30),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font={"color": th["text"]},
        xaxis=dict(title="Sentiment score", gridcolor=th["border"], zerolinecolor=th["border"]),
        yaxis=dict(title="Articles", gridcolor=th["border"]),
    )
    return fig


def source_x_sentiment_heatmap(articles, top_n=15):
    """Source x sentiment-bucket heatmap."""
    try:
        import plotly.graph_objects as go
    except ImportError:
        return None
    if not articles:
        return None
    th = _THEMES[st.session_state.brg_theme]
    src_counts = Counter(a.get("source", "?") for a in articles)
    top_sources = [s for s, _ in src_counts.most_common(top_n)]
    buckets = ["Strong-", "Mod-", "Mild-", "Neutral", "Mild+", "Mod+", "Strong+"]
    edges = [-1.001, -0.50, -0.20, -0.05, 0.05, 0.20, 0.50, 1.001]

    grid = [[0] * len(buckets) for _ in top_sources]
    src_idx = {s: i for i, s in enumerate(top_sources)}
    for a in articles:
        s = a.get("source", "?")
        if s not in src_idx:
            continue
        score = a.get("sentiment", {}).get("score", 0) or 0
        for j in range(len(buckets)):
            if edges[j] < score <= edges[j + 1]:
                grid[src_idx[s]][j] += 1
                break
    fig = go.Figure(go.Heatmap(
        z=grid,
        x=buckets,
        y=top_sources,
        colorscale=[
            [0.0, "rgba(126,138,160,0.06)"],
            [0.5, th["accent"]],
            [1.0, th["accent_lt"]],
        ],
        hovertemplate="%{y} — %{x}: %{z}<extra></extra>",
        showscale=False,
    ))
    fig.update_layout(
        height=max(220, 26 * len(top_sources) + 60),
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font={"color": th["text"], "size": 11},
        xaxis=dict(side="top"),
        yaxis=dict(autorange="reversed"),
    )
    return fig


def simple_bar_chart(labels, values, *, title="", horizontal=False, colors=None, height=260):
    try:
        import plotly.graph_objects as go
    except ImportError:
        return None
    th = _THEMES[st.session_state.brg_theme]
    if colors is None:
        colors = [th["accent"]] * len(labels)
    if horizontal:
        fig = go.Figure(go.Bar(
            x=values,
            y=labels,
            orientation="h",
            marker_color=colors,
            marker_line_width=0,
            hovertemplate="%{y}: %{x}<extra></extra>",
        ))
        fig.update_yaxes(autorange="reversed")
    else:
        fig = go.Figure(go.Bar(
            x=labels,
            y=values,
            marker_color=colors,
            marker_line_width=0,
            hovertemplate="%{x}: %{y}<extra></extra>",
        ))
    layout_kwargs = {}
    if title:
        layout_kwargs["title"] = {"text": title, "font": {"size": 13}}
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=28 if title else 10, b=30),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": th["text"], "size": 11},
        xaxis=dict(gridcolor=th["border"], zerolinecolor=th["border"]),
        yaxis=dict(gridcolor=th["border"], zerolinecolor=th["border"]),
        showlegend=False,
        **layout_kwargs,
    )
    return fig


def sentiment_trend_chart(scores):
    try:
        import plotly.graph_objects as go
    except ImportError:
        return None
    if not scores:
        return None
    th = _THEMES[st.session_state.brg_theme]
    fig = go.Figure(go.Scatter(
        y=scores,
        mode="lines",
        line={"color": th["accent"], "width": 1.8},
        hovertemplate="Article %{x}<br>Score %{y:+.2f}<extra></extra>",
    ))
    fig.add_hline(y=0, line_color=th["border"], line_width=1)
    fig.update_layout(
        height=240,
        margin=dict(l=10, r=10, t=10, b=30),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": th["text"], "size": 11},
        xaxis=dict(title="Article order", gridcolor=th["border"]),
        yaxis=dict(title="Score", range=[-1, 1], gridcolor=th["border"]),
    )
    return fig


def _ramme_of(a):
    """Return the rich RAMME dict on an article, regardless of field name."""
    return a.get("ramme") or a.get("_ramme") or {}


def model_agreement_panel(articles):
    """Aggregate per-model components from articles and render a panel."""
    # Articles store the legacy single-score view; the RAMME components are
    # available in article['ramme'] when produced by the new pipeline.
    components = []
    for a in articles:
        comps = _ramme_of(a).get("components") or []
        comps_tuple = [
            (c.get("name", "?"), float(c.get("score", 0)), c.get("label", "neutral"))
            for c in comps
        ]
        if comps_tuple:
            components.append(comps_tuple)
    if not components:
        return None
    try:
        from sentiment_bot.analyzers.model_agreement import compute_agreement
    except Exception:
        return None
    return compute_agreement(components)


def drift_panel(current_scores, summaries, current_run_id):
    """Compute PSI vs. last N runs as rolling baseline."""
    try:
        from sentiment_bot.analyzers.drift_detector import DriftDetector
    except Exception:
        return None
    baseline = []
    seen = 0
    for s in summaries:
        if s.get("run_id") == current_run_id:
            continue
        arts = load_articles(s["run_id"])
        baseline.extend(a.get("sentiment", {}).get("score", 0) or 0 for a in arts)
        seen += 1
        if seen >= 10:
            break
    if not baseline or not current_scores:
        return None
    return DriftDetector().psi(current_scores, baseline)


def run_label(s):
    ts = s.get("started_at", "")[:16].replace("T", " ")
    topic = s.get("config", {}).get("topic") or "all news"
    n = s.get("collection", {}).get("relevant_count", 0)
    return f"{ts}  |  {topic}  |  {n} articles"


def _article_score(a):
    return float((a.get("sentiment") or {}).get("score", 0) or 0)


def _sentiment_counts(articles):
    counts = Counter()
    for a in articles:
        label = (a.get("sentiment") or {}).get("label")
        score = _article_score(a)
        if label in ("pos", "positive"):
            counts["positive"] += 1
        elif label in ("neg", "negative"):
            counts["negative"] += 1
        elif label in ("neu", "neutral"):
            counts["neutral"] += 1
        elif score > 0.05:
            counts["positive"] += 1
        elif score < -0.05:
            counts["negative"] += 1
        else:
            counts["neutral"] += 1
    return counts


def _risk_weighted_score(scores):
    if not scores:
        return 0.0
    weighted = [(s * 1.18) if s < 0 else (s * 0.95) for s in scores]
    return sum(weighted) / len(weighted)


def _pct(n, d):
    return f"{(n / d * 100):.0f}%" if d else "0%"


def _score_engine_label(articles):
    for a in articles:
        ramme = _ramme_of(a)
        if ramme:
            if any((ramme.get("components") or [])):
                return "RAMME ensemble"
            return "RAMME fallback"
    return "VADER / legacy"


def _run_quality_checks(articles):
    if not articles:
        return [{"state": "fail", "check": "Article data", "detail": "No article records are available for this scan."}]

    n = len(articles)
    scores = [_article_score(a) for a in articles]
    counts = _sentiment_counts(articles)
    ramme_present = sum(1 for a in articles if _ramme_of(a))
    ramme_components = sum(1 for a in articles if (_ramme_of(a).get("components") or []))
    zero_scores = sum(1 for s in scores if abs(s) < 1e-9)
    short_text = sum(1 for a in articles if int(a.get("text_chars", 0) or 0) < 160)
    max_label_share = max(counts.values()) / n if counts else 0
    confs = [
        float((a.get("sentiment") or {}).get("confidence", 0) or 0)
        for a in articles
    ]
    low_conf = sum(1 for c in confs if c < 0.40)

    checks = []
    if ramme_present and ramme_components == 0:
        checks.append({
            "state": "fail",
            "check": "Model components",
            "detail": "RAMME payload exists but no component scores were stored. This usually means model inference failed.",
        })
    elif ramme_present:
        checks.append({
            "state": "ok",
            "check": "Model components",
            "detail": f"{ramme_components}/{n} articles include per-model component scores.",
        })
    else:
        checks.append({
            "state": "warn",
            "check": "Model components",
            "detail": "No RAMME payload found. This scan was likely created before the RAMME output schema.",
        })

    checks.append({
        "state": "fail" if zero_scores == n else ("warn" if zero_scores / n > 0.35 else "ok"),
        "check": "Score variation",
        "detail": f"{zero_scores}/{n} articles have exactly zero sentiment. High zero counts can indicate fallback or extraction issues.",
    })
    checks.append({
        "state": "warn" if max_label_share > 0.85 else "ok",
        "check": "Label concentration",
        "detail": f"Largest label bucket is {_pct(max(counts.values()), n)} of articles ({dict(counts)}).",
    })
    checks.append({
        "state": "warn" if short_text / n > 0.30 else "ok",
        "check": "Text extraction",
        "detail": f"{short_text}/{n} articles have under 160 extracted characters and rely mostly on headline/description.",
    })
    checks.append({
        "state": "warn" if low_conf / n > 0.40 else "ok",
        "check": "Confidence",
        "detail": f"{low_conf}/{n} articles have classifier confidence below 40%.",
    })
    return checks


def _render_quality_checks(articles):
    for item in _run_quality_checks(articles):
        st.markdown(
            f'<div class="brg-check {item["state"]}">'
            f'<div class="status">{item["state"]}</div>'
            f'<div><strong>{item["check"]}</strong><br>'
            f'<span class="brg-note">{item["detail"]}</span></div></div>',
            unsafe_allow_html=True,
        )


def _component_rows(article):
    rows = []
    for comp in (_ramme_of(article).get("components") or []):
        rows.append({
            "Model": comp.get("name", "?"),
            "Score": round(float(comp.get("score", 0) or 0), 3),
            "Label": comp.get("label", "neutral"),
            "Confidence": f"{float(comp.get('confidence', 0) or 0):.0%}",
        })
    return rows


def run_bot(args, placeholder=None):
    cmd = [sys.executable, "-m", "sentiment_bot.cli_unified"] + args
    env = os.environ.copy(); env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env=env)
    lines = []
    try:
        for line in proc.stdout:
            lines.append(line)
            if placeholder:
                clean = [re.sub(r'\x1b\[[0-9;]*m', '', l).rstrip() for l in lines[-20:]]
                placeholder.code("\n".join(clean), language=None)
        proc.wait(timeout=3600)
    except subprocess.TimeoutExpired:
        proc.kill(); lines.append("\n[TIMEOUT]")
    return "".join(lines), proc.returncode or 0

TIER_LABELS = {1: "Tier 1 (Major)", 2: "Tier 2 (Regional)", 3: "Tier 3 (Other)"}

# ---------------------------------------------------------------------------
# Rate limiting — prevent a single session from burning all API credits
# ---------------------------------------------------------------------------

RATE_LIMIT_FILE = OUTPUT_DIR / ".rate_limits.json"
DAILY_CREDIT_CAP = 2000        # max credits across ALL users per day
SESSION_SCAN_CAP = 3           # max scans per session
SESSION_CREDIT_CAP = 600       # max credits per session
COOLDOWN_MINUTES = 5           # minutes between scans per session

def _load_rate_data():
    if RATE_LIMIT_FILE.exists():
        try:
            return json.loads(RATE_LIMIT_FILE.read_text())
        except Exception:
            pass
    return {"date": "", "credits_used": 0, "scans": 0}

def _save_rate_data(data):
    RATE_LIMIT_FILE.write_text(json.dumps(data))

def _check_rate_limit(credits_requested: int) -> tuple:
    """Returns (allowed: bool, reason: str)."""
    today = datetime.now().strftime("%Y-%m-%d")

    # Global daily cap
    data = _load_rate_data()
    if data.get("date") != today:
        data = {"date": today, "credits_used": 0, "scans": 0}
    if data["credits_used"] + credits_requested > DAILY_CREDIT_CAP:
        remaining = DAILY_CREDIT_CAP - data["credits_used"]
        return False, f"Daily credit limit reached ({data['credits_used']}/{DAILY_CREDIT_CAP} used). {remaining} remaining. Resets at midnight."

    # Per-session caps
    sess_scans = st.session_state.get("_rate_scans", 0)
    sess_credits = st.session_state.get("_rate_credits", 0)
    last_scan = st.session_state.get("_rate_last_scan")

    if sess_scans >= SESSION_SCAN_CAP:
        return False, f"Session limit: {SESSION_SCAN_CAP} scans max per session. Refresh the page to start a new session."

    if sess_credits + credits_requested > SESSION_CREDIT_CAP:
        return False, f"Session credit limit: {sess_credits}/{SESSION_CREDIT_CAP} credits used. Try a smaller scan or refresh."

    if last_scan:
        elapsed = (datetime.now() - datetime.fromisoformat(last_scan)).total_seconds() / 60
        if elapsed < COOLDOWN_MINUTES:
            wait = COOLDOWN_MINUTES - elapsed
            return False, f"Cooldown: wait {wait:.0f} more minutes between scans."

    return True, ""

def _record_scan(credits_used: int):
    """Record a completed scan for rate limiting."""
    today = datetime.now().strftime("%Y-%m-%d")
    data = _load_rate_data()
    if data.get("date") != today:
        data = {"date": today, "credits_used": 0, "scans": 0}
    data["credits_used"] += credits_used
    data["scans"] += 1
    _save_rate_data(data)

    st.session_state["_rate_scans"] = st.session_state.get("_rate_scans", 0) + 1
    st.session_state["_rate_credits"] = st.session_state.get("_rate_credits", 0) + credits_used
    st.session_state["_rate_last_scan"] = datetime.now().isoformat()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

LOGO_PATH = Path(t["logo"])
if LOGO_PATH.exists():
    st.sidebar.image(str(LOGO_PATH), width=180)
st.sidebar.markdown(
    f'<p style="color:{t["gold"]}; font-size:0.7rem; letter-spacing:0; '
    f'text-transform:uppercase; margin-top:-8px;">Risk Monitor</p>',
    unsafe_allow_html=True,
)
page = st.sidebar.radio("Navigation", [
    "Results", "Risk Intelligence", "Events", "AI Analyst", "Compare Scans",
    "New Scan", "Past Scans", "Methodology",
], label_visibility="collapsed")
st.sidebar.divider()

# Theme toggle
_other = "light" if st.session_state.brg_theme == "dark" else "dark"
_icon = "Switch to Light" if st.session_state.brg_theme == "dark" else "Switch to Dark"
if st.sidebar.button(_icon, use_container_width=True, key="theme_toggle"):
    st.session_state.brg_theme = _other
    st.rerun()

st.sidebar.caption("Boston Risk Group")

# ---------------------------------------------------------------------------
# Tutorial walkthrough
# ---------------------------------------------------------------------------

TUTORIAL_STEPS = [
    {
        "title": "Welcome to BRG Sentiment Bot",
        "body": (
            "This tool scans hundreds of news sources, analyzes sentiment, "
            "extracts geopolitical events, and generates intelligence reports.\n\n"
            "This quick walkthrough will show you how to run a scan and read the results. "
            "You can skip at any time."
        ),
        "page": None,
    },
    {
        "title": "Step 1: Run a Scan",
        "body": (
            "Go to **New Scan** in the sidebar.\n\n"
            "- Enter a topic (e.g. *Ukraine*, *AI regulation*, *oil prices*)\n"
            "- Choose how far back to search (7d is a good default)\n"
            "- Pick how many articles (300 is standard)\n"
            "- Under Advanced, check **Extract events** for actor-action-receiver analysis\n"
            "- Hit **Start Scan** and wait ~2-10 minutes\n\n"
            "The bot will fetch articles from 100+ sources, scrape full text, "
            "and run sentiment analysis on each one."
        ),
        "page": "New Scan",
    },
    {
        "title": "Step 2: View Results",
        "body": (
            "After a scan completes, go to **Results**.\n\n"
            "You'll see:\n"
            "- **Overview metrics** — article count, overall mood, avg score, source count\n"
            "- **Sentiment breakdown** — positive/negative/neutral distribution\n"
            "- **Country risk table** — which countries are mentioned and their risk levels\n"
            "- **Source credibility** — articles broken down by Tier 1/2/3 outlets\n"
            "- **All articles** — filterable table with every article, score, and source\n\n"
            "Click any article to see its full details, entities, themes, and events."
        ),
        "page": "Results",
    },
    {
        "title": "Step 3: Explore Events",
        "body": (
            "If you enabled **Extract events**, go to the **Events** page.\n\n"
            "Events break down *who did what to whom*:\n"
            "- **Relationships** — actor-receiver pairs with tone scores\n"
            "- **Network graph** — visual map of how actors interact\n"
            "- **Top Actors** — ranked by activity, with drill-down\n"
            "- **Action Breakdown** — economic, military, diplomatic, etc.\n"
            "- **Timeline** — events plotted by date with tone trends\n\n"
            "Use the filters in the **All Events** tab to search by domain, action, or tone range."
        ),
        "page": "Events",
    },
    {
        "title": "Step 4: AI Analyst",
        "body": (
            "The **AI Analyst** sends your scan data to GPT-4o for analysis.\n\n"
            "Quick reports:\n"
            "- **Intelligence Brief** — executive summary with risk assessment\n"
            "- **Country Risk Profile** — deep dive on a region\n"
            "- **Market Impact** — financial implications\n"
            "- **Threat Assessment** — security-focused analysis\n\n"
            "You can also ask **custom questions** about the data.\n\n"
            "That's it! You're ready to go."
        ),
        "page": "AI Analyst",
    },
]

if "tutorial_active" not in st.session_state:
    st.session_state.tutorial_active = False
    st.session_state.tutorial_step = 0
    st.session_state.tutorial_dismissed = True

# Show tutorial offer on first visit
if st.session_state.tutorial_active and not st.session_state.tutorial_dismissed:
    step = st.session_state.tutorial_step

    if step < len(TUTORIAL_STEPS):
        ts = TUTORIAL_STEPS[step]

        with st.sidebar.container():
            st.sidebar.markdown("---")
            st.sidebar.markdown(f"**{ts['title']}**")
            st.sidebar.markdown(ts["body"])

            cols = st.sidebar.columns(3 if step > 0 else 2)
            col_idx = 0

            if step > 0:
                if cols[col_idx].button("Back", key=f"tut_back_{step}", use_container_width=True):
                    st.session_state.tutorial_step -= 1
                    st.rerun()
                col_idx += 1

            if step < len(TUTORIAL_STEPS) - 1:
                if cols[col_idx].button("Next", key=f"tut_next_{step}", type="primary", use_container_width=True):
                    st.session_state.tutorial_step += 1
                    st.rerun()
            else:
                if cols[col_idx].button("Done", key=f"tut_done_{step}", type="primary", use_container_width=True):
                    st.session_state.tutorial_dismissed = True
                    st.session_state.tutorial_active = False
                    st.rerun()
            col_idx += 1

            if cols[col_idx].button("Skip", key=f"tut_skip_{step}", use_container_width=True):
                st.session_state.tutorial_dismissed = True
                st.session_state.tutorial_active = False
                st.rerun()

            st.sidebar.caption(f"Step {step + 1} of {len(TUTORIAL_STEPS)}")
            st.sidebar.markdown("---")
else:
    # Show restart button
    if st.sidebar.button("Tutorial", use_container_width=True, key="restart_tutorial"):
        st.session_state.tutorial_active = True
        st.session_state.tutorial_step = 0
        st.session_state.tutorial_dismissed = False
        st.rerun()


# =====================================================================
# RESULTS
# =====================================================================

def _page_header(title, subtitle=""):
    """Render a branded BRG page header."""
    sub_html = f'<div class="brg-sub">{subtitle}</div>' if subtitle else ''
    st.markdown(
        f'<div class="brg-header">'
        f'<h1>{title}</h1>{sub_html}'
        f'</div>',
        unsafe_allow_html=True,
    )

def _page_footer():
    """Render bottom classification banner."""
    st.markdown(
        '<div class="brg-classification">Boston Risk Group | Proprietary & Confidential</div>',
        unsafe_allow_html=True,
    )


if page == "Results":
    _page_header("Scan Results", "Summary · Sources · Article Trace")
    summaries = load_summaries()
    if not summaries:
        st.info("No scans yet. Run a New Scan to get started."); st.stop()

    run_opts = {run_label(s): s["run_id"] for s in summaries}
    sel = st.selectbox("Select scan", list(run_opts.keys()), index=0)
    run_id = run_opts[sel]
    cur = next(s for s in summaries if s["run_id"] == run_id)
    analysis = cur.get("analysis", {})
    articles = load_articles(run_id)
    n = len(articles) or cur.get("collection", {}).get("relevant_count", 0)

    # --- Overview metrics (each expandable for traceability) ---
    st.markdown('<div class="brg-section">Overview</div>', unsafe_allow_html=True)
    stot = analysis.get("sentiment_total", 0)
    mood = "Positive" if stot > 5 else ("Negative" if stot < -5 else "Neutral")
    avg_display = analysis.get("avg_sentiment", 0)
    kpi_ribbon([
        {"label": "Articles", "value": f"{n:,}", "bar": min(100, n / 5)},
        {"label": "Overall mood", "value": f"{mood} ({stot:+d})",
         "tone": "pos" if stot > 5 else ("neg" if stot < -5 else ""),
         "bar": max(0, min(100, stot + 50))},
        {"label": "Avg score", "value": f"{avg_display:+.2f}",
         "tone": "pos" if avg_display > 0.05 else ("neg" if avg_display < -0.05 else ""),
         "bar": int((avg_display + 1) * 50)},
        {"label": "Sources", "value": f"{cur.get('diversity', {}).get('sources', 0):,}",
         "bar": min(100, cur.get("diversity", {}).get("sources", 0) * 3)},
    ])

    # Traceability: explain the displayed metrics with live scan values.
    with st.expander("How is this calculated?"):
        bd = analysis.get("breakdown", {})
        live_counts = _sentiment_counts(articles) if articles else Counter()
        pos_n = bd.get("positive", bd.get("pos", live_counts.get("positive", 0)))
        neg_n = bd.get("negative", bd.get("neg", live_counts.get("negative", 0)))
        neu_n = bd.get("neutral", bd.get("neu", live_counts.get("neutral", 0)))
        avg = analysis.get("avg_sentiment", 0)
        source_n = cur.get("diversity", {}).get("sources", 0)
        engine = _score_engine_label(articles)
        metric = st.radio(
            "Inspect metric",
            ["Overall mood", "Average score", "Article score", "Source count", "Data quality"],
            horizontal=True,
            key=f"calc_metric_{run_id}",
        )
        if metric == "Overall mood":
            st.markdown(
                f'<div class="brg-formula">({pos_n} positive - {neg_n} negative) / {max(n, 1)} articles * 100 = {stot:+d}</div>',
                unsafe_allow_html=True,
            )
            st.write(
                "The dashboard classifies article-level scores above `+0.05` as positive, "
                "below `-0.05` as negative, and everything in between as neutral. "
                "The overall mood score is a breadth measure, not an average magnitude measure."
            )
        elif metric == "Average score":
            st.markdown(
                f'<div class="brg-formula">mean(article sentiment scores) = {avg:+.3f}</div>',
                unsafe_allow_html=True,
            )
            st.write(
                f"Current scoring engine: **{engine}**. RAMME scores blend specialist model outputs, "
                "headline/body weighting, temperature-scaled probabilities, and a lightweight fallback "
                "only when model inference is unavailable. Fast-mode scans use VADER."
            )
        elif metric == "Article score":
            sample_articles = [a for a in articles if _component_rows(a)]
            if sample_articles:
                labels = [
                    f"{idx + 1}. {_article_score(a):+.2f} | {a.get('source', '?')} | {a.get('title', '')[:80]}"
                    for idx, a in enumerate(sample_articles[:150])
                ]
                pick = st.selectbox("Inspect one article", labels, key=f"calc_article_{run_id}")
                chosen = sample_articles[labels.index(pick)]
                st.markdown(
                    '<div class="brg-formula">headline/body blend -> component weighted mean -> confidence calibration</div>',
                    unsafe_allow_html=True,
                )
                ramme = _ramme_of(chosen)
                st.write(
                    f"Final score `{_article_score(chosen):+.3f}`; RAMME label `{ramme.get('label', 'n/a')}`; "
                    f"title score `{ramme.get('title_score', 0):+.3f}`; body score `{ramme.get('body_score', 0):+.3f}`."
                )
                st.dataframe(pd.DataFrame(_component_rows(chosen)), use_container_width=True, hide_index=True)
            else:
                st.write("This scan does not contain RAMME component rows. Re-run the scan to populate article-level model traces.")
        elif metric == "Source count":
            st.markdown(
                f'<div class="brg-formula">count(distinct article.source) = {source_n}</div>',
                unsafe_allow_html=True,
            )
            st.write(
                "Source tiers are shown for analyst context and corroboration. They are no longer used as the article sentiment confidence score; "
                "confidence now comes from the classifier output saved on each article."
            )
        else:
            _render_quality_checks(articles)

    st.divider()
    left, right = st.columns(2)

    with left:
        st.markdown("#### Sentiment Breakdown")
        bd = analysis.get("breakdown", {})
        if bd:
            d = {"Positive": bd.get("positive", bd.get("pos", 0)),
                 "Negative": bd.get("negative", bd.get("neg", 0)),
                 "Neutral": bd.get("neutral", bd.get("neu", 0))}
            th = _THEMES[st.session_state.brg_theme]
            fig = simple_bar_chart(
                list(d.keys()),
                list(d.values()),
                colors=[th["pos"], th["neg"], th["neu"]],
                height=260,
            )
            if fig is not None:
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.dataframe(pd.DataFrame({"Category": d.keys(), "Count": d.values()}), use_container_width=True, hide_index=True)

    with right:
        st.markdown("#### Top Sources")
        if articles:
            sc = Counter(a.get("source", "?") for a in articles)
            top = dict(sc.most_common(15))
            fig = simple_bar_chart(list(top.keys()), list(top.values()), horizontal=True, height=360)
            if fig is not None:
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.dataframe(pd.DataFrame({"Source": top.keys(), "Articles": top.values()}), use_container_width=True, hide_index=True)

    # --- Source credibility breakdown ---
    if articles:
        st.markdown("#### Source Credibility")
        tier_counts = Counter(a.get("source_tier", 3) for a in articles)
        tier_rows = []
        for t in [1, 2, 3]:
            cnt = tier_counts.get(t, 0)
            pct = cnt / len(articles) * 100 if articles else 0
            tier_rows.append({"Tier": TIER_LABELS.get(t, "?"), "Articles": cnt, "Percentage": f"{pct:.0f}%"})
        st.dataframe(pd.DataFrame(tier_rows), use_container_width=True, hide_index=True)
        with st.expander("How are source tiers used?"):
            st.markdown("""
**Tier 1 (Major):** Wire services and global prestige outlets — Reuters, AP, BBC, CNN, NYT, Washington Post, Guardian, Al Jazeera, Bloomberg, FT, Wall Street Journal. Highest editorial standards.

**Tier 2 (Regional/Specialized):** Quality regional papers, think tanks, and specialized outlets — CNBC, Foreign Affairs, CSIS, Brookings, Defense News, South China Morning Post, Japan Times, Bellingcat. Strong editorial standards within their domain.

**Tier 3 (Other):** Aggregators, smaller outlets, blogs, and unclassified sources. May have lower editorial standards or unclear provenance. Findings from Tier 3 sources should be corroborated.

Source tiers are not part of the sentiment formula. They are displayed as provenance and corroboration context. Classifier confidence is saved from the model or fallback scorer on each article.
            """)

    # --- Country risk table ---
    if articles:
        cc = Counter(); cs = {}
        for a in articles:
            score = a.get("sentiment", {}).get("score", 0)
            for e in a.get("entities", []):
                if e.get("type") == "GPE":
                    cc[e["text"]] += 1; cs.setdefault(e["text"], []).append(score)
        if cc:
            st.markdown("#### Country Risk Overview")
            rows = []
            for name, cnt in cc.most_common(20):
                avg = sum(cs[name]) / len(cs[name])
                neg = sum(1 for s in cs[name] if s < -0.05) / len(cs[name])
                risk = "Critical" if neg > .6 else ("High" if neg > .4 else ("Elevated" if neg > .25 else "Normal"))
                rows.append({"Country": name, "Mentions": cnt, "Sentiment": round(avg, 2), "Neg%": f"{neg:.0%}", "Risk": risk})
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            with st.expander("How is country risk calculated?"):
                country_view = st.radio(
                    "Inspect",
                    ["Formula", "Thresholds", "Example"],
                    horizontal=True,
                    key=f"country_calc_{run_id}",
                )
                if country_view == "Formula":
                    st.markdown(
                        '<div class="brg-formula">country sentiment = mean(scores for articles mentioning country as GPE)</div>'
                        '<div class="brg-formula">negative share = negative article mentions / total country mentions</div>',
                        unsafe_allow_html=True,
                    )
                    st.write(
                        "The score source is the same article-level sentiment shown elsewhere in the scan: RAMME by default, VADER only for fast-mode scans. "
                        "A country mention is counted when the entity extractor tags it as `GPE`."
                    )
                elif country_view == "Thresholds":
                    st.dataframe(pd.DataFrame([
                        {"Risk": "Critical", "Rule": "Negative share > 60%"},
                        {"Risk": "High", "Rule": "Negative share > 40%"},
                        {"Risk": "Elevated", "Rule": "Negative share > 25%"},
                        {"Risk": "Normal", "Rule": "Negative share <= 25%"},
                    ]), use_container_width=True, hide_index=True)
                    st.write("These thresholds are intentionally simple and auditable. Low-mention countries should be reviewed by opening the drill-down below.")
                else:
                    example = rows[0]
                    st.markdown(
                        f'<div class="brg-formula">{example["Country"]}: {example["Mentions"]} mentions, '
                        f'{example["Neg%"]} negative -> {example["Risk"]}</div>',
                        unsafe_allow_html=True,
                    )
                    st.write("Use the country selector below to inspect the specific article titles, scores, sources, and tiers driving any row.")

            # Country drill-down
            pick = st.selectbox("Drill into country", ["(select)"] + [r["Country"] for r in rows])
            if pick != "(select)":
                ca = [a for a in articles if any(e.get("text") == pick and e.get("type") == "GPE" for e in a.get("entities", []))]
                if ca:
                    sc2 = [a.get("sentiment", {}).get("score", 0) for a in ca]
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Articles", len(ca))
                    m2.metric("Avg Sentiment", f"{sum(sc2)/len(sc2):+.2f}")
                    m3.metric("Sources", len(set(a.get("source", "") for a in ca)))
                    st.markdown(f"**Articles mentioning {pick}:**")
                    for a in sorted(ca, key=lambda x: abs(x.get("sentiment", {}).get("score", 0)), reverse=True)[:15]:
                        s = a.get("sentiment", {}).get("score", 0)
                        tier = TIER_LABELS.get(a.get("source_tier", 3), "T3")
                        url = a.get("url", "")
                        title = a.get("title", "Untitled")
                        src = a.get("source", "?")
                        link_md = f"[{title}]({url})" if url else title
                        st.write(f"- [{sent_label(s)} {s:+.2f}] **{src}** ({tier}) — {link_md}")

    # Themes
    triggers = analysis.get("top_triggers", [])
    if triggers:
        st.markdown("#### Key Themes")
        st.write("  ".join(f"`{t.replace('_', ' ').title()}`" for t in triggers))

    # Sentiment trend
    if articles:
        st.divider()
        st.markdown("#### Sentiment Trend (article order)")
        fig = sentiment_trend_chart([a.get("sentiment", {}).get("score", 0) for a in articles])
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.dataframe(pd.DataFrame({"Score": [a.get("sentiment", {}).get("score", 0) for a in articles]}), use_container_width=True)

    # --- Full article table ---
    if articles:
        st.divider()
        st.markdown(f"### All Articles ({len(articles):,})")
        f1, f2, f3 = st.columns(3)
        with f1: src_pick = st.multiselect("Source", sorted(set(a.get("source", "") for a in articles)))
        with f2: mood_pick = st.multiselect("Mood", ["Positive", "Negative", "Neutral"])
        with f3: sort_pick = st.selectbox("Sort", ["Strongest first", "Most positive", "Most negative", "Newest"])

        filt = articles
        if src_pick: filt = [a for a in filt if a.get("source") in src_pick]
        if mood_pick:
            mm = {"Positive": "pos", "Negative": "neg", "Neutral": "neu"}
            lb = {mm[m] for m in mood_pick}
            filt = [a for a in filt if a.get("sentiment", {}).get("label") in lb]
        if sort_pick == "Strongest first": filt.sort(key=lambda a: abs(a.get("sentiment", {}).get("score", 0)), reverse=True)
        elif sort_pick == "Most positive": filt.sort(key=lambda a: a.get("sentiment", {}).get("score", 0), reverse=True)
        elif sort_pick == "Most negative": filt.sort(key=lambda a: a.get("sentiment", {}).get("score", 0))
        else: filt.sort(key=lambda a: a.get("published_at", ""), reverse=True)

        st.caption(f"{len(filt)} of {len(articles)}")
        tbl = [{"Score": round(a.get("sentiment", {}).get("score", 0), 2),
                "Title": a.get("title", "")[:100], "Source": a.get("source", ""),
                "Tier": TIER_LABELS.get(a.get("source_tier", 3), "T3")[:6],
                "Published": a.get("published_at", "")[:16],
                "Risk": (a.get("signals") or {}).get("risk_level", ""),
                "Chars": a.get("text_chars", 0)} for a in filt]
        if tbl:
            st.dataframe(pd.DataFrame(tbl), use_container_width=True, hide_index=True, height=min(len(tbl)*35+40, 800))

        # Expandable article details with full traceability
        st.markdown("#### Article Details")
        PER_PAGE = 50
        tp = max(1, (len(filt) + PER_PAGE - 1) // PER_PAGE)
        pg = st.number_input("Page", 1, tp, 1) if tp > 1 else 1
        for article in filt[(pg-1)*PER_PAGE:pg*PER_PAGE]:
            score = article.get("sentiment", {}).get("score", 0)
            tier = article.get("source_tier", 3)
            with st.expander(f"[{sent_label(score)} {score:+.2f}] {article.get('title', '')[:90]}  |  {article.get('source', '')}"):
                col_l, col_r = st.columns([3, 1])
                with col_l:
                    st.write(f"**Source:** {article.get('source', 'Unknown')}  ({TIER_LABELS.get(tier, 'T3')})")
                    st.write(f"**Published:** {article.get('published_at', '')[:19]}")
                    if article.get("url"):
                        st.markdown(f"**URL:** [{article['url'][:80]}...]({article['url']})" if len(article.get('url', '')) > 80 else f"**URL:** [{article['url']}]({article['url']})")
                    st.write(f"**Text length:** {article.get('text_chars', 0):,} characters analyzed")
                    st.write(f"**Content hash:** `{article.get('hash', 'n/a')[:16]}...`")
                with col_r:
                    st.metric("Sentiment", f"{score:+.2f}")
                    conf = article.get("sentiment", {}).get("confidence", 0)
                    st.write(f"**Confidence:** {conf:.0%}")
                    sig = article.get("signals") or {}
                    st.write(f"**Risk:** {sig.get('risk_level', 'normal')}")
                    st.write(f"**Volatility:** {sig.get('volatility', 0):.2f}")

                if article.get("ai_summary"):
                    st.info(f"**AI Summary:** {article['ai_summary']}")
                elif article.get("summary"):
                    st.write(f"**Description:** {article['summary'][:300]}")

                themes = (article.get("signals") or {}).get("themes", [])
                if themes:
                    st.write("**Themes:** " + ", ".join(t.replace("_", " ").title() for t in themes))
                ents = article.get("entities", [])
                if ents:
                    st.write("**Entities:** " + ", ".join(f"`{e['text']}` ({e['type']})" for e in ents[:10]))
                for ev in article.get("events", []):
                    a_name = ev.get("actor", {}).get("name", "?")
                    verb = ev.get("action", {}).get("verb", "?")
                    recv = (ev.get("receiver") or {}).get("name", "")
                    st.write(f"- {a_name} *{verb}*{f' -> {recv}' if recv else ''} (tone: {ev.get('tone', 0):+d})")

                comp_rows = _component_rows(article)
                if comp_rows:
                    st.markdown("**Article score trace**")
                    ramme = _ramme_of(article)
                    st.markdown(
                        f'<div class="brg-formula">final={score:+.3f}; '
                        f'title={float(ramme.get("title_score", 0) or 0):+.3f}; '
                        f'body={float(ramme.get("body_score", 0) or 0):+.3f}; '
                        f'agreement={float(ramme.get("agreement", 0) or 0):.2f}</div>',
                        unsafe_allow_html=True,
                    )
                    st.dataframe(pd.DataFrame(comp_rows), use_container_width=True, hide_index=True)


# =====================================================================
# RISK INTELLIGENCE
# =====================================================================

elif page == "Risk Intelligence":
    _page_header("Risk Intelligence", "Model Trace · Drift · Agreement")

    summaries = load_summaries()
    if not summaries:
        st.info("No scans yet. Run a New Scan to populate the intelligence panel.")
        st.stop()

    run_opts = {run_label(s): s["run_id"] for s in summaries}
    sel = st.selectbox("Select scan", list(run_opts.keys()), index=0,
                       key="risk_intel_scan")
    run_id = run_opts[sel]
    summary = next((s for s in summaries if s["run_id"] == run_id), {})
    articles = load_articles(run_id)

    if not articles:
        st.warning("No articles available for this scan.")
        st.stop()

    scores = [a.get("sentiment", {}).get("score", 0) or 0 for a in articles]
    avg_score = sum(scores) / max(len(scores), 1)
    risk_articles = [s for s in scores if s < -0.20]
    risk_share = len(risk_articles) / max(len(scores), 1)
    # Asymmetric risk-weighted aggregate (downside-amplified)
    rw = [(s * 1.18) if s < 0 else (s * 0.95) for s in scores]
    rw_score = sum(rw) / max(len(rw), 1)

    agreement = model_agreement_panel(articles)

    def _avg_kappa(stats):
        if stats is None or not stats.pairwise_agreement:
            return None
        vals = list(stats.pairwise_agreement.values())
        return sum(vals) / len(vals)

    avg_kappa = _avg_kappa(agreement)
    agreement_value = f"{avg_kappa:+.2f}" if avg_kappa is not None else "n/a"

    kpi_ribbon([
        {"label": "Articles", "value": f"{len(articles):,}",
         "tone": "", "bar": min(100, len(articles) / 5)},
        {"label": "Avg sentiment", "value": f"{avg_score:+.2f}",
         "tone": "pos" if avg_score > 0.05 else ("neg" if avg_score < -0.05 else ""),
         "bar": int((avg_score + 1) * 50)},
        {"label": "Risk-weighted", "value": f"{rw_score:+.2f}",
         "tone": "neg" if rw_score < -0.05 else ("pos" if rw_score > 0.05 else ""),
         "bar": int((rw_score + 1) * 50)},
        {"label": "Negative share", "value": f"{risk_share * 100:.0f}%",
         "tone": "neg" if risk_share > 0.30 else "",
         "bar": int(risk_share * 100)},
        {"label": "Mean kappa", "value": agreement_value,
         "tone": "warn" if avg_kappa is not None and avg_kappa < 0.20 else "",
         "bar": int((avg_kappa + 1) * 50) if avg_kappa is not None else 0},
    ])

    with st.expander("How is Risk Intelligence calculated?"):
        calc = st.radio(
            "Inspect metric",
            ["Risk-weighted score", "Negative share", "Model agreement", "Drift PSI", "FLS / ESG", "Data quality"],
            horizontal=True,
            key=f"risk_calc_{run_id}",
        )
        if calc == "Risk-weighted score":
            st.markdown(
                f'<div class="brg-formula">mean(score * 1.18 if negative else score * 0.95) = {rw_score:+.3f}</div>',
                unsafe_allow_html=True,
            )
            st.write(
                "This keeps the original article score direction but amplifies downside by 18% and dampens upside by 5%. "
                "It is a risk lens, not a replacement for average sentiment."
            )
        elif calc == "Negative share":
            st.markdown(
                f'<div class="brg-formula">{len(risk_articles)} articles with score < -0.20 / {len(articles)} total = {risk_share:.1%}</div>',
                unsafe_allow_html=True,
            )
            st.write("The threshold is stricter than the basic negative label threshold (`-0.05`) so this panel focuses on material downside signals.")
        elif calc == "Model agreement":
            if agreement is None:
                st.write("Agreement requires RAMME component rows on each article. Re-run older scans to populate this field.")
            else:
                st.markdown(
                    f'<div class="brg-formula">mean pairwise Cohen kappa = {avg_kappa if avg_kappa is not None else 0:+.3f}</div>',
                    unsafe_allow_html=True,
                )
                st.write(
                    "Each specialist model casts a positive/negative/neutral label. Pairwise kappa estimates whether models agree beyond chance. "
                    "Low kappa means the headline/body/model mix should be reviewed before drawing a strong conclusion."
                )
        elif calc == "Drift PSI":
            st.markdown(
                '<div class="brg-formula">PSI = sum((current_bucket - baseline_bucket) * ln(current_bucket / baseline_bucket))</div>',
                unsafe_allow_html=True,
            )
            st.write(
                "Current scores are bucketed from strong negative to strong positive and compared with the prior 10 scans. "
                "Moderate/significant PSI means today’s sentiment distribution moved materially versus recent baseline."
            )
        elif calc == "FLS / ESG":
            st.write(
                "Forward-looking statements and ESG tags come from RAMME auxiliary classifiers when available. "
                "If model inference is unavailable, conservative keyword fallbacks fill FLS/ESG probabilities so the panel does not silently go blank."
            )
        else:
            _render_quality_checks(articles)

    st.divider()

    g1, g2 = st.columns([1, 2])
    with g1:
        risk_gauge(rw_score, label="Risk-weighted score")
    with g2:
        st.markdown("##### Sentiment distribution")
        fig = sentiment_distribution_chart(scores)
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption("Distribution unavailable.")

    st.divider()

    h1, h2 = st.columns([3, 2])
    with h1:
        st.markdown("##### Source × sentiment heatmap")
        hm = source_x_sentiment_heatmap(articles, top_n=15)
        if hm is not None:
            st.plotly_chart(hm, use_container_width=True)
        else:
            st.caption("Not enough source diversity to render a heatmap.")
    with h2:
        st.markdown("##### Drift (PSI vs. last 10 scans)")
        report = drift_panel(scores, summaries, run_id)
        if report is None:
            st.caption("Need at least one prior scan to compute drift.")
        else:
            sev = report.severity
            kind = "neg" if sev == "significant" else ("warn" if sev == "moderate" else "pos")
            st.markdown(
                f'<div class="brg-card"><div class="brg-kpi-label">PSI</div>'
                f'<div class="brg-kpi-value">{report.psi:.3f}</div>'
                f'{risk_pill(sev.upper(), kind)}</div>',
                unsafe_allow_html=True,
            )
            try:
                import pandas as pd
                df = pd.DataFrame({
                    "Bucket": report.bin_labels,
                    "Current": [f"{x * 100:.1f}%" for x in report.current_dist],
                    "Baseline": [f"{x * 100:.1f}%" for x in report.baseline_dist],
                    "Δ": [f"{(c - b) * 100:+.1f}%"
                          for c, b in zip(report.current_dist, report.baseline_dist)],
                })
                st.dataframe(df, use_container_width=True, hide_index=True)
            except Exception:
                pass

    st.divider()

    st.markdown("##### Model agreement (Cohen's κ across specialists)")
    if agreement is None:
        st.info(
            "Per-model component scores are not yet stored on these articles. "
            "Re-run a scan with the RAMME pipeline enabled (the default in this build) "
            "to populate per-specialist agreement metrics."
        )
    else:
        try:
            import pandas as pd
            bias_df = pd.DataFrame({
                "Model": list(agreement.per_model_mean.keys()),
                "Mean score": [f"{v:+.2f}" for v in agreement.per_model_mean.values()],
                "Bias": [f"{agreement.per_model_bias.get(k, 0):+.2f}"
                         for k in agreement.per_model_mean.keys()],
            })
            st.dataframe(bias_df, use_container_width=True, hide_index=True)
            if agreement.pairwise_agreement:
                pairs_df = pd.DataFrame([
                    {"Pair": k.replace("|", " ↔ "), "Cohen's κ": f"{v:+.2f}"}
                    for k, v in agreement.pairwise_agreement.items()
                ])
                st.dataframe(pairs_df, use_container_width=True, hide_index=True)
            mean_kappa = avg_kappa if avg_kappa is not None else 0.0
            st.caption(
                f"Mean pairwise κ: {mean_kappa:+.2f}  •  "
                f"Avg σ across models: {agreement.avg_score_std:.2f}  •  "
                f"Label disagreement: {agreement.avg_label_disagreement:.0%}  •  "
                f"n = {agreement.n_articles}"
            )
        except Exception:
            st.caption("Could not render agreement table.")

    st.divider()

    fls_articles = [a for a in articles if _ramme_of(a).get("fls_flag")]
    esg_articles = [a for a in articles if _ramme_of(a).get("esg_flag")]

    f1, f2 = st.columns(2)
    with f1:
        st.markdown("##### Forward-looking statements")
        if not fls_articles:
            st.caption("No forward-looking statements detected (or RAMME data not available).")
        else:
            for a in fls_articles[:8]:
                fls = _ramme_of(a).get("fls", {}) or {}
                conf = max(fls.values()) if fls else 0
                st.markdown(
                    f"- **{a.get('title', '')[:120]}**  "
                    f"<span class='brg-pill warn'>FLS {conf:.0%}</span>  "
                    f"<span class='muted'>{a.get('source', '?')}</span>",
                    unsafe_allow_html=True,
                )
    with f2:
        st.markdown("##### ESG signals")
        if not esg_articles:
            st.caption("No ESG signals tagged (or RAMME data not available).")
        else:
            buckets = Counter(_ramme_of(a).get("esg_flag", "none") for a in esg_articles)
            for bucket, n in buckets.most_common():
                st.markdown(
                    f"- {risk_pill(bucket.title(), 'warn')} &nbsp; {n} articles",
                    unsafe_allow_html=True,
                )

    st.divider()

    st.markdown("##### Aspect-based sentiment (per entity)")
    aspect_rows = []
    for a in articles:
        for asp in (_ramme_of(a).get("aspects") or []):
            aspect_rows.append({
                "Entity": asp.get("entity", "?"),
                "Score": asp.get("score", 0),
                "Label": asp.get("label", "neutral"),
                "Source": a.get("source", "?"),
                "Title": (a.get("title") or "")[:90],
            })
    if not aspect_rows:
        st.caption("Aspect-level sentiment becomes available once entities are extracted by the RAMME pipeline.")
    else:
        try:
            import pandas as pd
            df = pd.DataFrame(aspect_rows)
            agg = df.groupby("Entity")["Score"].agg(["mean", "count"]).reset_index()
            agg = agg.sort_values("count", ascending=False).head(20)
            agg.columns = ["Entity", "Avg score", "Mentions"]
            agg["Avg score"] = agg["Avg score"].map(lambda v: f"{v:+.2f}")
            st.dataframe(agg, use_container_width=True, hide_index=True)
        except Exception:
            st.caption("Could not render aspect table.")


# =====================================================================
# EVENTS
# =====================================================================

elif page == "Events":
    _page_header("Event Intelligence", "Structured Actor-Action-Receiver Analysis")

    summaries = load_summaries()
    if not summaries:
        st.info("No scans yet. Run a New Scan with --extract-events to get started."); st.stop()

    run_opts = {run_label(s): s["run_id"] for s in summaries}
    sel = st.selectbox("Select scan", list(run_opts.keys()), index=0)
    run_id = run_opts[sel]
    events = load_events(run_id)

    if not events:
        st.warning("No events found for this scan. Re-run with **Extract Events** enabled in New Scan."); st.stop()

    st.success(f"{len(events)} events extracted from {len(set(e.get('article_id','') for e in events))} articles")

    # --- Overview metrics ---
    st.markdown('<div class="brg-section">Overview</div>', unsafe_allow_html=True)
    tones = [e.get("tone", 0) for e in events]
    avg_tone = sum(tones) / len(tones) if tones else 0
    hostile_n = sum(1 for t in tones if t < -3)
    coop_n = sum(1 for t in tones if t > 3)
    actors_unique = len(set(e.get("actor", {}).get("name", "") for e in events))

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Events", f"{len(events):,}")
    c2.metric("Unique Actors", f"{actors_unique:,}")
    c3.metric("Avg Tone", f"{avg_tone:+.1f}")
    c4.metric("Hostile", f"{hostile_n}", help="Events with tone < -3")
    c5.metric("Cooperative", f"{coop_n}", help="Events with tone > +3")

    tab_rel, tab_actors, tab_actions, tab_timeline, tab_table = st.tabs([
        "Relationships", "Top Actors", "Action Breakdown", "Timeline", "All Events"
    ])

    # --- Relationships tab ---
    with tab_rel:
        st.markdown("#### Key Actor-Receiver Relationships")
        rels = {}
        for e in events:
            recv = (e.get("receiver") or {}).get("name")
            if not recv: continue
            actor = e.get("actor", {}).get("name", "?")
            key = (actor, recv)
            if key not in rels:
                rels[key] = {"tones": [], "actions": [], "domains": []}
            rels[key]["tones"].append(e.get("tone", 0))
            rels[key]["actions"].append(e.get("action", {}).get("category", "?"))
            rels[key]["domains"].append(e.get("domain", "?"))

        if rels:
            rel_rows = []
            for (actor, recv), data in sorted(rels.items(), key=lambda x: len(x[1]["tones"]), reverse=True):
                avg_t = sum(data["tones"]) / len(data["tones"])
                top_action = Counter(data["actions"]).most_common(1)[0][0]
                top_domain = Counter(data["domains"]).most_common(1)[0][0]
                rel_rows.append({
                    "Actor": actor, "Receiver": recv,
                    "Events": len(data["tones"]),
                    "Avg Tone": round(avg_t, 1),
                    "Primary Action": top_action,
                    "Domain": top_domain,
                })

            # Tone filter
            tone_filter = st.select_slider(
                "Filter by tone",
                options=["All", "Hostile only (<-3)", "Cooperative only (>3)"],
                value="All",
            )
            if tone_filter == "Hostile only (<-3)":
                rel_rows = [r for r in rel_rows if r["Avg Tone"] < -3]
            elif tone_filter == "Cooperative only (>3)":
                rel_rows = [r for r in rel_rows if r["Avg Tone"] > 3]

            st.dataframe(
                pd.DataFrame(rel_rows[:50]),
                use_container_width=True, hide_index=True,
                column_config={
                    "Avg Tone": st.column_config.NumberColumn(format="%+.1f"),
                },
            )

            # Network visualization
            st.markdown("#### Relationship Network")
            try:
                import plotly.graph_objects as go
                import math

                top_rels = sorted(rels.items(), key=lambda x: len(x[1]["tones"]), reverse=True)[:30]
                nodes_set = set()
                for (a, r), _ in top_rels:
                    nodes_set.add(a); nodes_set.add(r)
                nodes = list(nodes_set)
                node_idx = {n: i for i, n in enumerate(nodes)}

                # Layout: circular
                n_nodes = len(nodes)
                node_x = [math.cos(2 * math.pi * i / n_nodes) for i in range(n_nodes)]
                node_y = [math.sin(2 * math.pi * i / n_nodes) for i in range(n_nodes)]

                # Edges
                edge_x, edge_y, edge_colors = [], [], []
                annotations = []
                for (a, r), data in top_rels:
                    ai, ri = node_idx[a], node_idx[r]
                    edge_x += [node_x[ai], node_x[ri], None]
                    edge_y += [node_y[ai], node_y[ri], None]
                    avg_t = sum(data["tones"]) / len(data["tones"])

                edge_trace = go.Scatter(
                    x=edge_x, y=edge_y, mode="lines",
                    line=dict(width=0.8, color="rgba(150,150,150,0.4)"),
                    hoverinfo="none",
                )

                # Node colors by net tone received
                tone_received = {}
                for (a, r), data in top_rels:
                    avg_t = sum(data["tones"]) / len(data["tones"])
                    tone_received.setdefault(r, []).append(avg_t)
                    tone_received.setdefault(a, [])

                node_colors = []
                for n in nodes:
                    t_list = tone_received.get(n, [])
                    if t_list:
                        avg = sum(t_list) / len(t_list)
                        node_colors.append(avg)
                    else:
                        node_colors.append(0)

                # Node sizes by event count
                actor_counts = Counter(e.get("actor", {}).get("name", "") for e in events)
                node_sizes = [max(10, min(40, actor_counts.get(n, 1) * 2)) for n in nodes]

                node_trace = go.Scatter(
                    x=node_x, y=node_y, mode="markers+text",
                    text=nodes, textposition="top center",
                    textfont=dict(size=9),
                    marker=dict(
                        size=node_sizes,
                        color=node_colors,
                        colorscale=[[0, "#e74c3c"], [0.5, "#95a5a6"], [1, "#27ae60"]],
                        cmin=-8, cmax=8,
                        colorbar=dict(title="Tone", thickness=15, len=0.5),
                        line=dict(width=1, color="#333"),
                    ),
                    hovertext=[f"{n}: {actor_counts.get(n,0)} events" for n in nodes],
                    hoverinfo="text",
                )

                fig = go.Figure(data=[edge_trace, node_trace])
                fig.update_layout(
                    showlegend=False,
                    xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                    yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                    margin=dict(l=20, r=20, t=20, b=20),
                    height=500,
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(fig, use_container_width=True)
            except ImportError:
                st.caption("Install plotly for network visualization: pip install plotly")

    # --- Top Actors tab ---
    with tab_actors:
        st.markdown("#### Most Active Actors")
        actor_data = {}
        for e in events:
            name = e.get("actor", {}).get("name", "?")
            atype = e.get("actor", {}).get("type", "?")
            if name not in actor_data:
                actor_data[name] = {"type": atype, "tones": [], "domains": [], "stances": []}
            actor_data[name]["tones"].append(e.get("tone", 0))
            actor_data[name]["domains"].append(e.get("domain", "?"))
            actor_data[name]["stances"].append(e.get("stance", "?"))

        actor_rows = []
        for name, data in sorted(actor_data.items(), key=lambda x: len(x[1]["tones"]), reverse=True)[:30]:
            avg_t = sum(data["tones"]) / len(data["tones"])
            top_domain = Counter(data["domains"]).most_common(1)[0][0]
            top_stance = Counter(data["stances"]).most_common(1)[0][0]
            actor_rows.append({
                "Actor": name, "Type": data["type"],
                "Events": len(data["tones"]),
                "Avg Tone": round(avg_t, 1),
                "Top Domain": top_domain,
                "Top Stance": top_stance,
            })

        st.dataframe(
            pd.DataFrame(actor_rows),
            use_container_width=True, hide_index=True,
            column_config={"Avg Tone": st.column_config.NumberColumn(format="%+.1f")},
        )

        # Actor type breakdown
        st.markdown("#### Actor Types")
        type_counts = Counter(e.get("actor", {}).get("type", "?") for e in events)
        st.bar_chart(pd.DataFrame({"Type": type_counts.keys(), "Count": type_counts.values()}).set_index("Type"))

        # Drill-down
        actor_pick = st.selectbox("Drill into actor", ["(select)"] + [r["Actor"] for r in actor_rows])
        if actor_pick != "(select)":
            actor_events = [e for e in events if e.get("actor", {}).get("name") == actor_pick]
            st.markdown(f"**{actor_pick}** - {len(actor_events)} events")
            ae_tones = [e.get("tone", 0) for e in actor_events]
            m1, m2, m3 = st.columns(3)
            m1.metric("Events", len(actor_events))
            m2.metric("Avg Tone", f"{sum(ae_tones)/len(ae_tones):+.1f}")
            m3.metric("Receivers", len(set((e.get("receiver") or {}).get("name", "") for e in actor_events if e.get("receiver"))))
            for e in actor_events[:20]:
                recv = (e.get("receiver") or {}).get("name", "")
                verb = e.get("action", {}).get("verb", "?")
                tone = e.get("tone", 0)
                domain = e.get("domain", "?")
                loc = (e.get("location") or {}).get("name", "")
                date = e.get("event_date", "")
                tone_color = "red" if tone < -3 else ("green" if tone > 3 else "gray")
                recv_str = f" -> **{recv}**" if recv else ""
                loc_str = f" [{loc}]" if loc else ""
                date_str = f" ({date})" if date else ""
                st.write(f"- :{tone_color}_circle: `{tone:+d}` {actor_pick} *{verb}*{recv_str} ({domain}){loc_str}{date_str}")

    # --- Action Breakdown tab ---
    with tab_actions:
        st.markdown("#### Action Categories")
        cat_counts = Counter(e.get("action", {}).get("category", "?") for e in events)
        st.bar_chart(pd.DataFrame({"Category": cat_counts.keys(), "Count": cat_counts.values()}).set_index("Category"))

        st.markdown("#### Domain Distribution")
        dom_counts = Counter(e.get("domain", "?") for e in events)
        st.bar_chart(pd.DataFrame({"Domain": dom_counts.keys(), "Count": dom_counts.values()}).set_index("Domain"))

        st.markdown("#### Stance Distribution")
        stance_counts = Counter(e.get("stance", "?") for e in events)
        st.bar_chart(pd.DataFrame({"Stance": stance_counts.keys(), "Count": stance_counts.values()}).set_index("Stance"))

        st.markdown("#### Intensity Distribution")
        intensity_counts = Counter(e.get("intensity", 1) for e in events)
        st.bar_chart(pd.DataFrame({
            "Intensity": [str(k) for k in sorted(intensity_counts.keys())],
            "Count": [intensity_counts[k] for k in sorted(intensity_counts.keys())]
        }).set_index("Intensity"))

    # --- Timeline tab ---
    with tab_timeline:
        st.markdown("#### Events by Date")
        dated = [e for e in events if e.get("event_date")]
        if dated:
            date_counts = Counter(e["event_date"][:10] for e in dated)
            date_df = pd.DataFrame(sorted(date_counts.items()), columns=["Date", "Events"])
            st.bar_chart(date_df.set_index("Date"))

            st.markdown("#### Tone Over Time")
            date_tones = {}
            for e in dated:
                d = e["event_date"][:10]
                date_tones.setdefault(d, []).append(e.get("tone", 0))
            tone_df = pd.DataFrame([
                {"Date": d, "Avg Tone": sum(t)/len(t)}
                for d, t in sorted(date_tones.items())
            ])
            st.line_chart(tone_df.set_index("Date"))

            st.markdown("#### Locations")
            located = [e for e in events if e.get("location")]
            if located:
                loc_counts = Counter(e["location"].get("name", "?") for e in located)
                loc_rows = [{"Location": name, "Events": cnt} for name, cnt in loc_counts.most_common(20)]
                st.dataframe(pd.DataFrame(loc_rows), use_container_width=True, hide_index=True)
        else:
            st.info("No events have date information.")

    # --- All Events table ---
    with tab_table:
        st.markdown(f"#### All Events ({len(events):,})")

        # Filters
        f1, f2, f3 = st.columns(3)
        with f1:
            domain_filter = st.multiselect("Domain", sorted(set(e.get("domain", "") for e in events)))
        with f2:
            category_filter = st.multiselect("Action", sorted(set(e.get("action", {}).get("category", "") for e in events)))
        with f3:
            tone_range = st.slider("Tone range", -10, 10, (-10, 10))

        filt = events
        if domain_filter:
            filt = [e for e in filt if e.get("domain") in domain_filter]
        if category_filter:
            filt = [e for e in filt if e.get("action", {}).get("category") in category_filter]
        filt = [e for e in filt if tone_range[0] <= e.get("tone", 0) <= tone_range[1]]

        st.caption(f"Showing {len(filt)} of {len(events)} events")

        tbl = []
        for e in filt:
            recv = (e.get("receiver") or {}).get("name", "")
            tbl.append({
                "Actor": e.get("actor", {}).get("name", "?"),
                "Action": e.get("action", {}).get("verb", "?"),
                "Category": e.get("action", {}).get("category", "?"),
                "Receiver": recv,
                "Tone": e.get("tone", 0),
                "Domain": e.get("domain", "?"),
                "Intensity": e.get("intensity", 1),
                "Stance": e.get("stance", "?"),
                "Location": (e.get("location") or {}).get("name", ""),
                "Date": e.get("event_date", ""),
                "Confidence": e.get("confidence", 0),
                "Article": e.get("article_title", "")[:60],
            })

        if tbl:
            st.dataframe(
                pd.DataFrame(tbl),
                use_container_width=True, hide_index=True,
                height=min(len(tbl) * 35 + 40, 800),
                column_config={
                    "Tone": st.column_config.NumberColumn(format="%+d"),
                    "Confidence": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.0%%"),
                },
            )

    _page_footer()


# =====================================================================
# AI ANALYST
# =====================================================================

elif page == "AI Analyst":
    _page_header("AI Analyst", "GPT-4o Intelligence Briefings")

    summaries = load_summaries()
    if not summaries:
        st.info("Run a New Scan first."); st.stop()

    run_opts = {run_label(s): s["run_id"] for s in summaries}
    sel = st.selectbox("Select scan", list(run_opts.keys()), index=0)
    run_id = run_opts[sel]
    cur = next(s for s in summaries if s["run_id"] == run_id)
    articles = load_articles(run_id)
    if not articles:
        st.warning("No articles for this scan."); st.stop()

    st.success(f"{len(articles)} articles from {len(set(a.get('source','') for a in articles))} sources loaded.")
    snapshot = build_data_snapshot(articles, cur.get("analysis", {}))

    st.markdown("### Quick Reports")
    cols = st.columns(4)
    chosen = None
    for i, name in enumerate(AI_PRESETS):
        if cols[i % 4].button(name, use_container_width=True, key=f"p_{i}"):
            chosen = name

    AI_QUERY_CAP = 10  # max AI queries per session
    ai_used = st.session_state.get("_rate_ai_queries", 0)
    st.caption(f"AI queries this session: {ai_used}/{AI_QUERY_CAP}")

    if chosen:
        if ai_used >= AI_QUERY_CAP:
            st.error(f"AI query limit reached ({AI_QUERY_CAP}/session). Refresh to start a new session.")
        else:
            with st.spinner(f"Generating {chosen}..."):
                result = call_openai(AI_PRESETS[chosen], snapshot)
            st.session_state["_rate_ai_queries"] = ai_used + 1
            st.markdown(f"### {chosen}")
            st.markdown(result)
            st.download_button("Download as text", data=f"# {chosen}\nGenerated: {datetime.now():%Y-%m-%d %H:%M}\nScan: {run_id} | {len(articles)} articles\n\n{result}",
                               file_name=f"BRG_{chosen.replace(' ','_')}_{run_id}.txt", mime="text/plain")

    st.divider()
    st.markdown("### Custom Question")
    q = st.text_area("Your question", placeholder="e.g. What are the biggest risks for Southeast Asia based on this data?", height=80)
    if st.button("Analyze", type="primary"):
        if ai_used >= AI_QUERY_CAP:
            st.error(f"AI query limit reached ({AI_QUERY_CAP}/session). Refresh to start a new session.")
        elif q.strip():
            with st.spinner("Analyzing..."):
                result = call_openai(q, snapshot)
            st.session_state["_rate_ai_queries"] = st.session_state.get("_rate_ai_queries", 0) + 1
            st.markdown(result)
        else:
            st.warning("Enter a question.")


# =====================================================================
# COMPARE SCANS
# =====================================================================

elif page == "Compare Scans":
    _page_header("Compare Scans", "Temporal Risk Analysis")

    summaries = load_summaries()
    if len(summaries) < 2:
        st.info("Need at least 2 scans to compare. Run more scans first.")
        st.stop()

    c1, c2 = st.columns(2)
    labels = {run_label(s): s["run_id"] for s in summaries}
    label_list = list(labels.keys())
    with c1:
        sel_a = st.selectbox("Scan A (older)", label_list, index=min(1, len(label_list)-1))
    with c2:
        sel_b = st.selectbox("Scan B (newer)", label_list, index=0)

    id_a, id_b = labels[sel_a], labels[sel_b]
    cur_a = next(s for s in summaries if s["run_id"] == id_a)
    cur_b = next(s for s in summaries if s["run_id"] == id_b)
    arts_a = load_articles(id_a)
    arts_b = load_articles(id_b)

    if not arts_a or not arts_b:
        st.warning("One or both scans have no article data."); st.stop()

    # Overall comparison
    st.markdown("### Overall Comparison")
    an_a, an_b = cur_a.get("analysis", {}), cur_b.get("analysis", {})
    cmp_rows = []
    for label, key in [("Sentiment Score", "sentiment_total"), ("Avg Sentiment", "avg_sentiment"),
                        ("Volatility", "volatility_index")]:
        va, vb = an_a.get(key, 0), an_b.get(key, 0)
        delta = vb - va
        cmp_rows.append({"Metric": label, "Scan A": round(va, 2), "Scan B": round(vb, 2), "Change": round(delta, 2)})
    cmp_rows.append({"Metric": "Articles", "Scan A": len(arts_a), "Scan B": len(arts_b), "Change": len(arts_b) - len(arts_a)})
    st.dataframe(pd.DataFrame(cmp_rows), use_container_width=True, hide_index=True)

    # Country comparison
    st.markdown("### Country Sentiment Shifts")

    def _country_scores(articles):
        cc = {}
        for a in articles:
            score = a.get("sentiment", {}).get("score", 0)
            for e in a.get("entities", []):
                if e.get("type") == "GPE":
                    cc.setdefault(e["text"], []).append(score)
        return {k: sum(v)/len(v) for k, v in cc.items() if len(v) >= 3}

    scores_a = _country_scores(arts_a)
    scores_b = _country_scores(arts_b)
    all_countries = set(scores_a) | set(scores_b)

    shifts = []
    for country in all_countries:
        sa = scores_a.get(country)
        sb = scores_b.get(country)
        if sa is not None and sb is not None:
            delta = sb - sa
            direction = "Improving" if delta > 0.05 else ("Worsening" if delta < -0.05 else "Stable")
            shifts.append({"Country": country, "Scan A": round(sa, 2), "Scan B": round(sb, 2),
                          "Change": round(delta, 2), "Direction": direction})

    if shifts:
        shifts.sort(key=lambda x: x["Change"])
        st.dataframe(pd.DataFrame(shifts), use_container_width=True, hide_index=True)

        worsening = [s for s in shifts if s["Direction"] == "Worsening"]
        improving = [s for s in shifts if s["Direction"] == "Improving"]
        if worsening:
            st.markdown("**Worsening:** " + ", ".join(f"**{s['Country']}** ({s['Change']:+.2f})" for s in worsening[:10]))
        if improving:
            st.markdown("**Improving:** " + ", ".join(f"**{s['Country']}** ({s['Change']:+.2f})" for s in improving[:10]))
    else:
        st.info("Not enough overlapping countries to compare (need 3+ mentions each).")

    # Theme comparison
    st.markdown("### Theme Shifts")
    themes_a = Counter(); themes_b = Counter()
    for a in arts_a:
        for t in (a.get("signals") or {}).get("themes", []): themes_a[t] += 1
    for a in arts_b:
        for t in (a.get("signals") or {}).get("themes", []): themes_b[t] += 1
    all_themes = set(themes_a) | set(themes_b)
    theme_rows = []
    for t in all_themes:
        ca, cb = themes_a.get(t, 0), themes_b.get(t, 0)
        theme_rows.append({"Theme": t.replace("_", " ").title(), "Scan A": ca, "Scan B": cb, "Change": cb - ca})
    if theme_rows:
        theme_rows.sort(key=lambda x: x["Change"], reverse=True)
        st.dataframe(pd.DataFrame(theme_rows), use_container_width=True, hide_index=True)


# =====================================================================
# NEW SCAN
# =====================================================================

elif page == "New Scan":
    _page_header("New Scan", "Data Collection & Analysis")
    st.markdown('<div class="brg-section">Configure Scan Parameters</div>', unsafe_allow_html=True)

    with st.form("scan"):
        query = st.text_input("Topic (leave empty for all news)", placeholder="e.g. Ukraine, AI, oil prices")
        c1, c2 = st.columns(2)
        with c1:
            freshness = st.select_slider("How far back?", ["1h", "6h", "24h", "7d", "30d"], value="7d")
        with c2:
            target = st.select_slider("How many articles?", [50, 100, 200, 300, 500, 1000, 2000, 3000], value=300)

        with st.expander("Advanced options"):
            a1, a2 = st.columns(2)
            with a1:
                category = st.selectbox("Category", [None, "business", "technology", "science", "health", "sports", "entertainment", "general"],
                                        format_func=lambda x: x.title() if x else "All")
                extract_events = st.checkbox("Extract events (who did what to whom)", help="Requires OpenAI key")
            with a2:
                summarize = st.checkbox("AI summaries (adds ~1s per article)")
                export_csv = st.checkbox("Export CSV")
                region_filter = st.text_input("Region filter", placeholder="europe, asia, middle_east")
                topic_filter = st.text_input("Topic filter", placeholder="energy, elections, trade")

        st.caption(f"Estimated: ~{max(2 + (target//60 if summarize else 0), 1)} min  |  ~{target} API credits")
        go = st.form_submit_button("Start Scan", type="primary", use_container_width=True)

    # Show current usage
    sess_scans = st.session_state.get("_rate_scans", 0)
    sess_credits = st.session_state.get("_rate_credits", 0)
    daily_data = _load_rate_data()
    today = datetime.now().strftime("%Y-%m-%d")
    daily_used = daily_data["credits_used"] if daily_data.get("date") == today else 0
    st.caption(
        f"Session: {sess_scans}/{SESSION_SCAN_CAP} scans, {sess_credits}/{SESSION_CREDIT_CAP} credits  |  "
        f"Daily: {daily_used}/{DAILY_CREDIT_CAP} credits"
    )

    if go:
        # Rate limit check
        allowed, reason = _check_rate_limit(target)
        if not allowed:
            st.error(f"Rate limited: {reason}")
        else:
            args = ["run"]
            if query: args.append(query)
            if category: args.extend(["--category", category])
            args.extend(["--freshness", freshness, "--target", str(target)])
            if extract_events: args.append("--extract-events")
            if summarize: args.append("--summarize")
            if export_csv: args.append("--export-csv")
            if region_filter: args.extend(["--region", region_filter])
            if topic_filter: args.extend(["--topic", topic_filter])

            st.info(f"Scanning {target} articles from 100+ sources...")
            box = st.empty(); box.code("Starting...", language=None)
            stdout, code = run_bot(args, placeholder=box)
            if code == 0:
                _record_scan(target)
                box.empty()
                st.success("Scan complete. Go to Results or AI Analyst to explore.")
                with st.expander("Technical log", expanded=False): st.text(re.sub(r'\x1b\[[0-9;]*m', '', stdout))
            else:
                box.empty(); st.error("Scan failed.")
                with st.expander("Error log"): st.text(stdout)


# =====================================================================
# PAST SCANS
# =====================================================================

elif page == "Past Scans":
    _page_header("Past Scans", "Scan History & Management")
    summaries = load_summaries()
    if not summaries:
        st.info("No scans yet."); st.stop()

    rows = []
    for s in summaries:
        a = s.get("analysis", {}); c = s.get("collection", {}); cfg = s.get("config", {})
        stot = a.get("sentiment_total", 0)
        mood = "Positive" if stot > 5 else ("Negative" if stot < -5 else "Neutral")
        rows.append({"Date": s.get("started_at", "")[:16].replace("T", " "), "Topic": cfg.get("topic", "all news"),
                      "Articles": c.get("relevant_count", 0), "Mood": f"{mood} ({stot:+d})",
                      "Sources": s.get("diversity", {}).get("sources", 0), "ID": s.get("run_id", "")})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.divider()
    ids = [s["run_id"] for s in summaries]
    pick = st.selectbox("Delete a scan", ["(none)"] + ids)
    if pick != "(none)" and st.button(f"Delete {pick}", type="secondary"):
        for pat in [f"articles_{pick}.*", f"run_summary_{pick}.*", f"events_{pick}.*", f"dashboard_run_summary_{pick}.*"]:
            for f in OUTPUT_DIR.glob(pat): f.unlink()
        st.success(f"Deleted {pick}"); st.rerun()


# =====================================================================
# METHODOLOGY
# =====================================================================

elif page == "Methodology":
    _page_header("Methodology", "Analytical Framework & Data Provenance")

    st.markdown("""
---

### 1. Data Collection

**Sources:** Articles are collected from three independent pipelines running in parallel:

| Pipeline | Source | Cost | Coverage | Articles/Scan |
|----------|--------|------|----------|---------------|
| TheNewsAPI | Commercial news API (thenewsapi.com) | ~1 credit/article | Global English-language news | User-defined target |
| RSS Feeds | 117 direct RSS feeds from major outlets | Free | BBC, CNN, NYT, Al Jazeera, Guardian, Reuters, CNBC, WSJ, 100+ more | ~1,500 per scan |
| GDELT | GDELT Project DOC 2.0 API | Free | Global multilingual event data | Up to 250 per scan |

**Deduplication:** Articles are deduplicated by URL hash (MD5). If two sources carry the same article URL, only one copy is retained.

**Freshness Filter:** Articles are filtered by publication date against the user-specified time window (e.g., "7d" = last 7 days). Articles without parseable dates from RSS feeds are retained.

**Full Text Retrieval:** Most APIs and RSS feeds only provide headlines and short descriptions. The platform attempts full-text extraction in this order: trafilatura, newspaper3k, then a raw paragraph scrape. Failed extractions fall back to the headline + description for analysis and are visible through each article's text length.

---

### 2. Sentiment Analysis

**Default method:** RAMME — a risk-aware, confidence-weighted ensemble.

RAMME routes each article through domain-specific sentiment components where available:

| Component | Use |
|-----------|-----|
| FinBERT-Tone | Financial and market tone |
| Financial-news RoBERTa | Cross-check for finance/news sentiment |
| CardiffNLP news/Twitter RoBERTa | General news tone |
| FLS classifier | Forward-looking statement probability |
| ESG classifier | Environmental, social, governance tagging |
| Lightweight fallback | VADER + BRG risk lexicon when model inference is unavailable |

**Article score:** Component probabilities are normalized to `positive`, `negative`, and `neutral`. A component score is `positive_probability - negative_probability`. Component scores are confidence-weighted, headline/body blended, and stored on each article as RAMME trace data.

**Classification thresholds:**
- **Positive:** final article score > +0.05
- **Negative:** final article score < -0.05
- **Neutral:** -0.05 <= final article score <= +0.05

**Risk-weighted score:** Risk Intelligence applies an asymmetric lens: negative scores are multiplied by `1.18`; positive scores by `0.95`. This is used for downside monitoring, not for changing the original article score.

**Confidence:** The dashboard now shows classifier confidence from the article sentiment result. Source tiers are displayed separately for provenance and corroboration; they are not used as sentiment confidence.

**Fast mode:** If the user explicitly enables fast mode, sentiment uses VADER only.

---

### 3. Source Credibility Tiers

Sources are classified into three tiers based on editorial standards, fact-checking practices, and institutional reputation:

**Tier 1 — Major Wire Services & Prestige Outlets**
Reuters, Associated Press, AFP, BBC News, CNN, New York Times, Washington Post, The Guardian, Al Jazeera, Financial Times, Wall Street Journal, Bloomberg, The Economist, NPR, France 24, Deutsche Welle.

**Tier 2 — Regional Quality & Specialized**
CNBC, Forbes, Politico, Foreign Affairs, Foreign Policy, CFR, CSIS, Brookings, RAND, Defense News, South China Morning Post, Japan Times, Bellingcat, Nature, Ars Technica, TechCrunch, and others.

**Tier 3 — Other**
All remaining sources including aggregators, smaller outlets, and unclassified sources. Tier 3 findings should be corroborated with Tier 1/2 sources before being included in client deliverables.

---

### 4. Entity Extraction

**Method:** Pattern-matching against curated dictionaries.

- **Countries (GPE):** Matched against a comprehensive list of 200+ countries, territories, and common aliases. Aliases are deduplicated to canonical names (e.g., "US", "USA", "America" all map to "United States").
- **Organizations (ORG):** Matched against a curated list of major international organizations, central banks, and corporations.
- **Tickers:** Regex pattern matching for stock ticker symbols (2-5 uppercase letters) and major indices.

**Limitations:** This is dictionary-based, not NLP-based. It will miss entities not in the dictionary and may occasionally match false positives (e.g., "US" in "focus").

---

### 5. Risk Assessment

**Country Risk Level** is computed from the negative article share across all articles mentioning a country as a GPE entity:
- **Critical:** >60% of articles are negative
- **High:** >40% negative
- **Elevated:** >25% negative
- **Normal:** <=25% negative

**Article Risk Level** is computed from keyword detection in the article text and adjusted upward when article sentiment is materially negative:
- High-risk keywords: crisis, crash, collapse, panic, emergency, critical
- Elevated keywords: concern, worry, risk, threat, warning, caution
- Adjusted by sentiment score (strongly negative articles are bumped up)

**Volatility Index** is the density of volatility keywords (crisis, surge, plunge, disruption, etc.) per 100 words, normalized to 0-1 scale.

---

### 6. Theme Detection

Themes are assigned by keyword matching in article text:

| Theme | Keywords |
|-------|----------|
| Inflation | inflation, CPI, prices, cost |
| Monetary Policy | rate, interest, hike, cut, fed, ECB |
| Economic Growth | recession, growth, GDP, economy |
| Geopolitical Risk | war, conflict, military, sanctions |
| Political Risk | election, vote, poll, candidate |
| Energy | oil, gas, energy, OPEC, crude |
| AI/Tech | AI, artificial intelligence, ML, GPT |
| Crypto | crypto, bitcoin, blockchain |

An article can have multiple themes. Top 5 are retained per article.

---

### 7. Event Extraction (Optional)

When enabled, GPT-4o-mini decomposes each article into structured events:
- **Actor:** Who initiated the action (state, org, person, group)
- **Action:** What they did (verb + category: cooperate/confront/military/economic/diplomatic)
- **Receiver:** Who was affected
- **Tone:** -10 (hostile) to +10 (cooperative)
- **Domain:** military, economic, diplomatic, legal, social, tech

Events are cached to avoid redundant API calls.

---

### 8. AI Analyst

The AI Analyst page sends a structured data snapshot to GPT-4o-mini containing:
- Overall scan statistics
- Country mention counts and average sentiments
- Source diversity breakdown
- Top 80 articles by sentiment strength (title, source, score, themes, entities)
- Extracted events (if available)

The model is prompted as a BRG intelligence analyst and instructed to cite specific data points, note uncertainties, and use hedging language for uncertain assessments.

---

### 9. Scan Comparison

Compares two scans by computing deltas in:
- Overall sentiment score
- Per-country average sentiment (countries with 3+ mentions in both scans)
- Theme frequency counts

Direction labels: Improving (delta > +0.05), Worsening (delta < -0.05), Stable (within +/-0.05).

---

### 10. Traceability

Every statistic in this platform is traceable to its source articles:
- Open the calculation drawers on Results and Risk Intelligence to see formulas, live inputs, and QA checks
- Click any country in the Country Risk table to see the specific articles driving the score
- Each article card shows: source, tier, URL, publication date, text length, content hash, confidence score, and RAMME component trace when available
- All raw data is stored in JSONL format in the `output/` directory for independent verification

**Data retention:** All scan data is stored locally. Nothing is sent to external services except:
- TheNewsAPI (article metadata retrieval)
- GDELT (article metadata retrieval)
- OpenAI (only when AI Analyst or event extraction is explicitly invoked by the user)
    """)
    _page_footer()
