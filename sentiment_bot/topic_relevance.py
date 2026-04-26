"""Topic relevance screening for noisy news scans.

The fetchers intentionally cast a wide net. This module applies a second,
auditable relevance gate so vague topics like "microchips" or "wokeness" do
not keep articles where a word appears once in an unrelated body paragraph.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


@dataclass
class TopicTaxonomy:
    name: str
    aliases: List[str] = field(default_factory=list)
    core_title: List[str] = field(default_factory=list)
    context_body: List[str] = field(default_factory=list)
    international_context: List[str] = field(default_factory=list)
    exclude_title: List[str] = field(default_factory=list)
    require_international: bool = False
    min_score: float = 0.55
    strict_min_score: float = 0.62
    min_context_matches: int = 1
    min_international_matches: int = 1


@dataclass
class RelevanceDecision:
    keep: bool
    score: float
    reason: str
    topic: Optional[str] = None
    stage: str = "prefetch"
    signals: List[str] = field(default_factory=list)


def split_topic_query(topic: Optional[str]) -> List[str]:
    """Split user topic text into auditable topic clauses."""
    if not topic:
        return []
    parts = [p.strip() for p in re.split(r"[,;/|]+", topic) if p.strip()]
    return parts or [topic.strip()]


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _word_re(term: str) -> re.Pattern:
    tokens = _norm(term).split()
    if not tokens:
        return re.compile(r"a^")
    pat = r"\b" + r"[^a-z0-9]+".join(re.escape(w) for w in tokens) + r"\b"
    return re.compile(pat, re.IGNORECASE)


def _hits(text: str, terms: Sequence[str]) -> List[str]:
    if not text or not terms:
        return []
    normalized = _norm(text)
    out = []
    for term in terms:
        if _word_re(term).search(normalized):
            out.append(term)
    return out


def _article_fields(article: Dict[str, Any]) -> Tuple[str, str, str]:
    title = article.get("title") or ""
    body = " ".join(
        str(article.get(k) or "")
        for k in ("description", "summary", "content")
    )
    full = f"{title} {body}"
    return title, body, full


def _default_taxonomy_path() -> Path:
    return Path(__file__).resolve().parent.parent / "config" / "topic_taxonomies.yaml"


@lru_cache(maxsize=2)
def load_taxonomies(path: Optional[str] = None) -> Dict[str, TopicTaxonomy]:
    cfg_path = Path(path) if path else _default_taxonomy_path()
    if not cfg_path.exists():
        return {}

    try:
        import yaml
        data = yaml.safe_load(cfg_path.read_text()) or {}
    except Exception as exc:
        logger.warning("Could not load topic taxonomy %s: %s", cfg_path, exc)
        return {}

    defaults = data.get("defaults") or {}
    topics = {}
    for name, raw in (data.get("topics") or {}).items():
        item = dict(defaults)
        item.update(raw or {})
        topics[name] = TopicTaxonomy(
            name=name,
            aliases=list(item.get("aliases") or []),
            core_title=list(item.get("core_title") or []),
            context_body=list(item.get("context_body") or []),
            international_context=list(item.get("international_context") or []),
            exclude_title=list(item.get("exclude_title") or []),
            require_international=bool(item.get("require_international", False)),
            min_score=float(item.get("min_score", 0.55)),
            strict_min_score=float(item.get("strict_min_score", 0.62)),
            min_context_matches=int(item.get("min_context_matches", 1)),
            min_international_matches=int(item.get("min_international_matches", 1)),
        )
    return topics


def resolve_taxonomy(topic: str) -> Optional[TopicTaxonomy]:
    topic_n = _norm(topic)
    for tax in load_taxonomies().values():
        names = [tax.name, *tax.aliases]
        if topic_n in {_norm(n) for n in names}:
            return tax
    return None


def _score_taxonomy(
    article: Dict[str, Any],
    tax: TopicTaxonomy,
    *,
    strict: bool = False,
) -> RelevanceDecision:
    title, body, full = _article_fields(article)
    title_l = title.lower()
    full_l = full.lower()

    excluded = _hits(title_l, tax.exclude_title)
    if excluded:
        return RelevanceDecision(
            keep=False,
            score=0.0,
            topic=tax.name,
            reason=f"excluded title phrase: {', '.join(excluded[:3])}",
            signals=excluded,
        )

    title_core = _hits(title_l, tax.core_title)
    full_core = _hits(full_l, tax.core_title)
    context = _hits(full_l, tax.context_body)
    intl = _hits(full_l, tax.international_context)

    title_ok = bool(title_core)
    context_ok = len(context) >= tax.min_context_matches
    intl_ok = (not tax.require_international) or len(intl) >= tax.min_international_matches

    score = 0.0
    if title_ok:
        score += 0.42
    elif full_core and not strict:
        score += 0.18
    score += min(0.28, 0.10 * len(context))
    score += min(0.22, 0.08 * len(intl))
    if _hits(full_l, tax.aliases):
        score += 0.08
    score = min(1.0, score)

    missing = []
    if not title_ok:
        missing.append("topic term in title")
    if not context_ok:
        missing.append("domain context")
    if not intl_ok:
        missing.append("international context")

    threshold = tax.strict_min_score if strict else tax.min_score
    if missing or score < threshold:
        return RelevanceDecision(
            keep=False,
            score=round(score, 3),
            topic=tax.name,
            reason=f"missing {', '.join(missing) if missing else 'score threshold'}",
            signals=[*title_core[:4], *context[:4], *intl[:4]],
        )

    return RelevanceDecision(
        keep=True,
        score=round(score, 3),
        topic=tax.name,
        reason="taxonomy match",
        signals=[*title_core[:4], *context[:4], *intl[:4]],
    )


def _fallback_keywords(topic: str) -> List[str]:
    try:
        from .config import TOPIC_MAP
        if topic in TOPIC_MAP:
            return list(TOPIC_MAP[topic])
        topic_key = topic.lower().replace(" ", "_")
        if topic_key in TOPIC_MAP:
            return list(TOPIC_MAP[topic_key])
    except Exception:
        pass
    return [topic.replace("_", " ")]


def _score_keyword_topic(article: Dict[str, Any], topic: str, *, strict: bool = False) -> RelevanceDecision:
    title, _body, full = _article_fields(article)
    terms = [t for t in _fallback_keywords(topic) if t]
    title_hits = _hits(title.lower(), terms)
    full_hits = _hits(full.lower(), terms)
    if title_hits:
        return RelevanceDecision(True, 0.62, "keyword match in title", topic=topic, signals=title_hits[:4])
    if full_hits and not strict:
        return RelevanceDecision(True, 0.40, "keyword match outside title", topic=topic, signals=full_hits[:4])
    return RelevanceDecision(False, 0.0, "no topic keyword match", topic=topic)


def score_article_relevance(
    article: Dict[str, Any],
    *,
    topic: Optional[str] = None,
    region: Optional[str] = None,
    strict: bool = False,
) -> RelevanceDecision:
    """Score one article against a user topic and optional region.

    Multiple comma-separated topics use OR semantics: any one topic match can
    keep the article. Region is an additional soft signal here; source fetchers
    already use region/topic terms upstream.
    """
    topics = split_topic_query(topic)
    decisions: List[RelevanceDecision] = []

    for t in topics:
        tax = resolve_taxonomy(t)
        if tax:
            decisions.append(_score_taxonomy(article, tax, strict=strict))
        else:
            decisions.append(_score_keyword_topic(article, t, strict=strict))

    if not decisions:
        decision = RelevanceDecision(True, 0.5, "no topic filter", topic=None)
    else:
        decision = max(decisions, key=lambda d: d.score)

    if region:
        region_terms = [region.replace("_", " ")]
        try:
            from .config import REGION_MAP
            region_terms = REGION_MAP.get(region, region_terms)
        except Exception:
            pass
        _title, _body, full = _article_fields(article)
        region_hits = _hits(full.lower(), region_terms)
        if not region_hits and strict:
            return RelevanceDecision(
                False,
                min(decision.score, 0.35),
                "missing region context",
                topic=decision.topic,
                stage="strict",
                signals=decision.signals,
            )
        if region_hits:
            decision.score = min(1.0, decision.score + 0.08)
            decision.signals = [*decision.signals, *region_hits[:3]]

    decision.stage = "strict" if strict else "prefetch"
    decision.keep = decision.keep and decision.score >= (0.50 if strict else 0.35)
    return decision


def filter_articles_by_relevance(
    articles: Sequence[Dict[str, Any]],
    *,
    topic: Optional[str] = None,
    region: Optional[str] = None,
    strict: bool = False,
) -> List[Dict[str, Any]]:
    if not topic and not region:
        return list(articles)

    kept: List[Dict[str, Any]] = []
    for article in articles:
        decision = score_article_relevance(article, topic=topic, region=region, strict=strict)
        article["_relevance_score"] = decision.score
        article["_relevance_reason"] = decision.reason
        article["_relevance_topic"] = decision.topic
        article["_relevance_signals"] = decision.signals
        if decision.keep:
            kept.append(article)
    return kept


def apply_embedding_gate(
    articles: Sequence[Dict[str, Any]],
    *,
    topic: Optional[str],
    threshold: float = 0.35,
) -> List[Dict[str, Any]]:
    """Optional semantic relevance gate using sentence-transformers.

    This is deliberately opt-in because the model adds memory pressure.
    If sentence-transformers is not installed, the input is returned unchanged.
    """
    if not topic or not articles:
        return list(articles)
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np
    except Exception:
        logger.warning("Semantic relevance requested but sentence-transformers is not installed")
        return list(articles)

    model_name = os.getenv("BRG_RELEVANCE_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    model = SentenceTransformer(model_name)
    query_vec = model.encode([f"International news about {topic}"], normalize_embeddings=True)[0]
    texts = [
        f"{a.get('title', '')}. {a.get('description', '') or a.get('summary', '')} {str(a.get('content', ''))[:800]}"
        for a in articles
    ]
    vecs = model.encode(texts, normalize_embeddings=True)
    sims = np.dot(vecs, query_vec)

    kept = []
    for article, sim in zip(articles, sims):
        article["_embedding_relevance"] = float(sim)
        if sim >= threshold:
            kept.append(article)
    return kept


def ai_relevance_judge(article: Dict[str, Any], *, topic: str, region: Optional[str] = None) -> RelevanceDecision:
    """Optional OpenAI relevance judge for borderline cases.

    Sends only article metadata/snippets. This should be called only when the
    user explicitly enables AI relevance screening.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return RelevanceDecision(True, article.get("_relevance_score", 0.5), "AI judge skipped: OPENAI_API_KEY missing")

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        snippet = {
            "title": article.get("title", ""),
            "source": article.get("domain") or article.get("source", ""),
            "description": article.get("description") or article.get("summary", ""),
            "content_excerpt": str(article.get("content", ""))[:1200],
            "topic": topic,
            "region": region,
        }
        prompt = (
            "Decide whether this article is substantively relevant to the requested news topic. "
            "Require the article's main subject to match the topic; incidental one-word mentions are not enough. "
            "For microchips/semiconductors, prefer international trade, sanctions, supply chain, Taiwan/China/US, "
            "or strategic industry coverage. Return compact JSON: "
            '{"keep": true|false, "score": 0..1, "reason": "short"}\n\n'
            f"{json.dumps(snippet, ensure_ascii=False)}"
        )
        resp = client.chat.completions.create(
            model=os.getenv("BRG_RELEVANCE_OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        text = resp.choices[0].message.content or "{}"
        match = re.search(r"\{.*\}", text, re.S)
        data = json.loads(match.group(0) if match else text)
        return RelevanceDecision(
            keep=bool(data.get("keep")),
            score=float(data.get("score", 0.0)),
            reason=f"AI judge: {data.get('reason', '')}".strip(),
            topic=topic,
        )
    except Exception as exc:
        logger.warning("AI relevance judge failed: %s", exc)
        return RelevanceDecision(True, article.get("_relevance_score", 0.5), "AI judge failed open")


def apply_ai_relevance_gate(
    articles: Sequence[Dict[str, Any]],
    *,
    topic: Optional[str],
    region: Optional[str] = None,
    max_articles: int = 250,
) -> List[Dict[str, Any]]:
    if not topic or not articles:
        return list(articles)
    kept = []
    for idx, article in enumerate(articles):
        if idx >= max_articles:
            kept.append(article)
            continue
        decision = ai_relevance_judge(article, topic=topic, region=region)
        article["_ai_relevance_score"] = decision.score
        article["_ai_relevance_reason"] = decision.reason
        if decision.keep:
            kept.append(article)
    return kept
