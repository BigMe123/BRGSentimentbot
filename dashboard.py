"""
BRG Intelligence Platform — Streamlit Dashboard
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
    page_title="Boston Risk Group | Intelligence Platform",
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
        "bg":       "#0e1117",
        "bg2":      "#0a1628",
        "panel":    "#141b2d",
        "accent":   "#1a73e8",
        "accent_lt":"#4a9af5",
        "gold":     "#c9a84c",
        "text":     "#e0e0e0",
        "muted":    "#8892a4",
        "border":   "#1e2a3a",
        "sidebar_bg": "linear-gradient(180deg, #0a1628 0%, #0d1320 100%)",
        "input_bg": "#141b2d",
        "hover_bg": "rgba(26,115,232,0.1)",
        "logo":     "assets/brg_logo_white.png",
    },
    "light": {
        "bg":       "#ffffff",
        "bg2":      "#f8f9fb",
        "panel":    "#f0f2f6",
        "accent":   "#0d47a1",
        "accent_lt":"#1565c0",
        "gold":     "#8b6914",
        "text":     "#1a1a2e",
        "muted":    "#5a6170",
        "border":   "#d0d5dd",
        "sidebar_bg": "linear-gradient(180deg, #f0f2f6 0%, #e8eaef 100%)",
        "input_bg": "#ffffff",
        "hover_bg": "rgba(13,71,161,0.06)",
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
        --brg-accent:   {t["accent"]};
        --brg-accent-lt:{t["accent_lt"]};
        --brg-gold:     {t["gold"]};
        --brg-text:     {t["text"]};
        --brg-muted:    {t["muted"]};
        --brg-border:   {t["border"]};
    }}

    /* Hide Streamlit branding */
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    header {{visibility: hidden;}}

    /* Main area */
    .stApp {{
        background: var(--brg-bg);
    }}

    /* Sidebar */
    [data-testid="stSidebar"] {{
        background: {t["sidebar_bg"]};
        border-right: 1px solid var(--brg-border);
    }}
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {{
        color: var(--brg-muted);
        font-size: 0.85rem;
    }}

    /* Metric cards */
    [data-testid="stMetric"] {{
        background: var(--brg-panel);
        border: 1px solid var(--brg-border);
        border-radius: 8px;
        padding: 16px;
    }}
    [data-testid="stMetric"] label {{
        color: var(--brg-muted) !important;
        font-size: 0.75rem !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }}
    [data-testid="stMetric"] [data-testid="stMetricValue"] {{
        color: var(--brg-text) !important;
        font-weight: 600;
    }}

    /* Data tables */
    [data-testid="stDataFrame"] {{
        border: 1px solid var(--brg-border);
        border-radius: 6px;
    }}

    /* Buttons */
    .stButton > button {{
        border: 1px solid var(--brg-border);
        background: var(--brg-panel);
        color: var(--brg-text);
        transition: all 0.2s;
    }}
    .stButton > button:hover {{
        border-color: var(--brg-accent);
        background: {t["hover_bg"]};
    }}
    .stButton > button[kind="primary"] {{
        background: var(--brg-accent);
        border-color: var(--brg-accent);
        color: white;
    }}

    /* Expanders */
    [data-testid="stExpander"] {{
        border: 1px solid var(--brg-border);
        border-radius: 6px;
        background: var(--brg-panel);
    }}

    /* Page dividers */
    hr {{
        border-color: var(--brg-border);
    }}

    /* Selectbox / inputs */
    [data-testid="stSelectbox"] > div > div,
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea {{
        border-color: var(--brg-border);
        background: {t["input_bg"]};
    }}

    /* Custom header bar */
    .brg-header {{
        display: flex;
        align-items: center;
        gap: 16px;
        padding: 12px 0;
        margin-bottom: 8px;
        border-bottom: 2px solid var(--brg-accent);
    }}
    .brg-header h1 {{
        font-size: 1.6rem;
        font-weight: 700;
        color: var(--brg-text);
        margin: 0;
        letter-spacing: 0.02em;
    }}
    .brg-header .brg-sub {{
        font-size: 0.8rem;
        color: var(--brg-muted);
        text-transform: uppercase;
        letter-spacing: 0.1em;
    }}

    /* Classification banner */
    .brg-classification {{
        text-align: center;
        font-size: 0.7rem;
        color: var(--brg-gold);
        letter-spacing: 0.15em;
        text-transform: uppercase;
        padding: 4px 0;
        border-top: 1px solid var(--brg-border);
        margin-top: 24px;
    }}

    /* Section headers */
    .brg-section {{
        font-size: 0.7rem;
        color: var(--brg-accent-lt);
        text-transform: uppercase;
        letter-spacing: 0.12em;
        font-weight: 600;
        margin: 24px 0 8px 0;
    }}

    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 0;
        border-bottom: 1px solid var(--brg-border);
    }}
    .stTabs [data-baseweb="tab"] {{
        color: var(--brg-muted);
        padding: 8px 20px;
    }}
    .stTabs [aria-selected="true"] {{
        color: var(--brg-accent-lt) !important;
        border-bottom: 2px solid var(--brg-accent) !important;
    }}

    /* Theme toggle button */
    .brg-theme-toggle {{
        cursor: pointer;
        text-align: center;
        padding: 4px 12px;
        border-radius: 4px;
        font-size: 0.75rem;
        letter-spacing: 0.05em;
        color: var(--brg-muted);
        border: 1px solid var(--brg-border);
        margin-top: 4px;
    }}
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

def run_label(s):
    ts = s.get("started_at", "")[:16].replace("T", " ")
    topic = s.get("config", {}).get("topic") or "all news"
    n = s.get("collection", {}).get("relevant_count", 0)
    return f"{ts}  |  {topic}  |  {n} articles"

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
    f'<p style="color:{t["gold"]}; font-size:0.7rem; letter-spacing:0.12em; '
    f'text-transform:uppercase; margin-top:-8px;">Intelligence Platform</p>',
    unsafe_allow_html=True,
)
page = st.sidebar.radio("Navigation", [
    "Results", "Events", "AI Analyst", "Compare Scans",
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
    _page_header("Scan Results", "Sentiment Analysis & Risk Assessment")
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
    c1, c2, c3, c4 = st.columns(4)
    stot = analysis.get("sentiment_total", 0)
    mood = "Positive" if stot > 5 else ("Negative" if stot < -5 else "Neutral")
    c1.metric("Articles", f"{n:,}")
    c2.metric("Overall Mood", f"{mood} ({stot:+d})")
    c3.metric("Avg Score", f"{analysis.get('avg_sentiment', 0):.2f}")
    c4.metric("Sources", cur.get("diversity", {}).get("sources", 0))

    # Traceability: explain the overall sentiment score
    with st.expander("How is this calculated?"):
        bd = analysis.get("breakdown", {})
        pos_n = bd.get("positive", bd.get("pos", 0))
        neg_n = bd.get("negative", bd.get("neg", 0))
        neu_n = bd.get("neutral", bd.get("neu", 0))
        st.markdown(f"""
**Overall Mood Score ({stot:+d}):** Calculated as `(positive_count - negative_count) / total_articles * 100`.
- Positive articles (score > +0.05): **{pos_n}**
- Negative articles (score < -0.05): **{neg_n}**
- Neutral articles: **{neu_n}**
- Formula: `({pos_n} - {neg_n}) / {n} * 100 = {stot:+d}`

**Average Score ({analysis.get('avg_sentiment', 0):.2f}):** Mean of all individual VADER sentiment scores.

**Sentiment Scoring Method:** VADER (Valence Aware Dictionary and sEntiment Reasoner).
Each article's text is scored on a -1.0 to +1.0 scale based on keyword intensity, negation,
punctuation, and capitalization. See Methodology page for full details.

**Source count:** {cur.get("diversity", {}).get("sources", 0)} unique news outlets contributed articles.
        """)

    st.divider()
    left, right = st.columns(2)

    with left:
        st.markdown("#### Sentiment Breakdown")
        bd = analysis.get("breakdown", {})
        if bd:
            d = {"Positive": bd.get("positive", bd.get("pos", 0)),
                 "Negative": bd.get("negative", bd.get("neg", 0)),
                 "Neutral": bd.get("neutral", bd.get("neu", 0))}
            st.bar_chart(pd.DataFrame({"Category": d.keys(), "Count": d.values()}).set_index("Category"))

    with right:
        st.markdown("#### Top Sources")
        if articles:
            sc = Counter(a.get("source", "?") for a in articles)
            top = dict(sc.most_common(15))
            st.bar_chart(pd.DataFrame({"Source": top.keys(), "Articles": top.values()}).set_index("Source"))

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
        with st.expander("What are source tiers?"):
            st.markdown("""
**Tier 1 (Major):** Wire services and global prestige outlets — Reuters, AP, BBC, CNN, NYT, Washington Post, Guardian, Al Jazeera, Bloomberg, FT, Wall Street Journal. Highest editorial standards.

**Tier 2 (Regional/Specialized):** Quality regional papers, think tanks, and specialized outlets — CNBC, Foreign Affairs, CSIS, Brookings, Defense News, South China Morning Post, Japan Times, Bellingcat. Strong editorial standards within their domain.

**Tier 3 (Other):** Aggregators, smaller outlets, blogs, and unclassified sources. May have lower editorial standards or unclear provenance. Findings from Tier 3 sources should be corroborated.

Sentiment confidence scores are weighted by tier: Tier 1 = 1.0, Tier 2 = 0.8, Tier 3 = 0.5.
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
                st.markdown("""
**Mentions:** Number of articles where this country appears as a named entity (GPE = Geopolitical Entity).

**Sentiment:** Average VADER sentiment score across all articles mentioning this country.

**Neg%:** Percentage of articles about this country with negative sentiment (score < -0.05).

**Risk Level:** Based on negative percentage:
- **Critical:** >60% negative articles
- **High:** >40% negative articles
- **Elevated:** >25% negative articles
- **Normal:** <=25% negative articles

Click a country below to see the specific articles driving these numbers.
                """)

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
        st.line_chart(pd.DataFrame({"Score": [a.get("sentiment", {}).get("score", 0) for a in articles]}))

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
            tier = a.get("source_tier", 3)
            with st.expander(f"[{sent_label(score)} {score:+.2f}] {article.get('title', '')[:90]}  |  {article.get('source', '')}"):
                col_l, col_r = st.columns([3, 1])
                with col_l:
                    st.write(f"**Source:** {article.get('source', 'Unknown')}  ({TIER_LABELS.get(article.get('source_tier', 3), 'T3')})")
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

**Full Text Retrieval:** Most APIs and RSS feeds only provide headlines and short descriptions (~200 characters). The platform uses newspaper3k to download and extract full article text from each URL. A fallback HTML parser extracts paragraph text when newspaper3k fails. Current success rate: ~84%. Failed extractions fall back to the headline + description for analysis.

---

### 2. Sentiment Analysis

**Method:** VADER (Valence Aware Dictionary and sEntiment Reasoner)

VADER is a rule-based sentiment analysis tool specifically attuned to social media and news text. It uses a human-validated lexicon of ~7,500 sentiment-bearing words and phrases, each rated on a -4 to +4 scale.

**How it works:**
1. Each word in the text is looked up in the VADER lexicon
2. Scores are modified by grammatical rules: negation ("not good" flips polarity), intensifiers ("very good" amplifies), and punctuation
3. The compound score normalizes the sum to a -1.0 to +1.0 range

**Classification thresholds:**
- **Positive:** compound score > +0.05
- **Negative:** compound score < -0.05
- **Neutral:** -0.05 <= compound score <= +0.05

**Confidence weighting:** Sentiment confidence is weighted by source credibility tier:
- Tier 1 sources: confidence = 1.0
- Tier 2 sources: confidence = 0.8
- Tier 3 sources: confidence = 0.5

**Reference:** Hutto, C.J. & Gilbert, E.E. (2014). VADER: A Parsimonious Rule-based Model for Sentiment Analysis of Social Media Text. ICWSM.

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

**Country Risk Level** is computed from the negative sentiment percentage across all articles mentioning a country:
- **Critical:** >60% of articles are negative
- **High:** >40% negative
- **Elevated:** >25% negative
- **Normal:** <=25% negative

**Article Risk Level** is computed from keyword detection in the article text:
- High-risk keywords: crisis, crash, collapse, panic, emergency, critical
- Elevated keywords: concern, worry, risk, threat, warning, caution
- Adjusted by sentiment score (strongly negative articles are bumped up)

**Volatility Index** is the density of volatility keywords (crisis, surge, plunge, etc.) per 100 words, normalized to 0-1 scale.

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
- Click "How is this calculated?" on any metric to see the formula
- Click any country in the Country Risk table to see the specific articles driving the score
- Each article card shows: source, tier, URL, publication date, text length, content hash, confidence score
- All raw data is stored in JSONL format in the `output/` directory for independent verification

**Data retention:** All scan data is stored locally. Nothing is sent to external services except:
- TheNewsAPI (article metadata retrieval)
- GDELT (article metadata retrieval)
- OpenAI (only when AI Analyst or event extraction is explicitly invoked by the user)
    """)
    _page_footer()
