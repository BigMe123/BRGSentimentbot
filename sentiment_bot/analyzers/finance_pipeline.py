"""
BRG Risk-Aware Multi-Model Ensemble (RAMME).

A stacked specialist sentiment pipeline tuned for the kind of finance + geopolitical
news BRG analyses. Replaces the older DistilBERT-SST2 + plain RoBERTa setup with
domain-specialist transformers, asymmetric risk weighting, forward-looking signal
detection, ESG flagging, and calibrated confidence.

Design goals:
- Specialist over general: FinBERT-Tone (yiyanghkust) for finance tone,
  FinBERT-FLS for forward-looking statements, FinBERT-ESG for ESG buckets,
  RoBERTa-financial-news as a cross-check, Twitter-RoBERTa for non-finance news,
  optional DeBERTa-v3 NLI for stance hypothesis testing.
- Title bias: news headlines carry the dominant sentiment signal — score the
  title separately and weight it.
- Sentence-level entity ABSA: when an entity list is provided, score sentiment
  in sentences mentioning each entity instead of doc-level only.
- Risk-aware aggregation: BRG's clients care more about downside surprises, so
  the ensemble applies asymmetric weighting that boosts negative consensus.
- Calibrated probabilities: combine temperature scaling with the existing
  ConfidenceCalibrator (isotonic) to map model confidence to reliable
  probabilities.
- Remote-first: prefer the HF Inference API (free GPU) and only fall back to
  local transformers when remote is unavailable. VADER is the last resort.

Public API:
    from sentiment_bot.analyzers.finance_pipeline import RiskAwareEnsemble, RAMMEResult

    pipe = RiskAwareEnsemble()
    result = pipe.score_text(text, title="Headline", entities=["Apple", "Fed"])
    results = pipe.score_batch(texts, titles=titles, themes_per_text=themes)
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Model registry — explicit IDs so behaviour is reproducible
# ---------------------------------------------------------------------------

MODELS: Dict[str, Dict[str, str]] = {
    "fin_tone":    {"id": "yiyanghkust/finbert-tone",                 "kind": "sentiment"},
    "fin_fls":     {"id": "yiyanghkust/finbert-fls",                  "kind": "fls"},
    "fin_esg":     {"id": "yiyanghkust/finbert-esg",                  "kind": "esg"},
    "fin_news":    {"id": "mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis",
                    "kind": "sentiment"},
    "news_roberta":{"id": "cardiffnlp/twitter-roberta-base-sentiment-latest", "kind": "sentiment"},
    "stance_nli":  {"id": "MoritzLaurer/deberta-v3-base-zeroshot-v2.0",       "kind": "nli"},
}

FINANCE_THEMES = {
    "inflation", "monetary_policy", "economic_growth", "markets",
    "banking", "earnings", "commodities", "crypto", "ai_disruption",
}

# Trigger ESG outside finance when these terms appear (corporate / policy news)
ESG_KEYWORDS = (
    "emissions", "climate", "carbon", "regulation", "compliance",
    "labor", "human rights", "governance", "board", "lawsuit",
    "fraud", "boycott", "diversity", "supply chain", "renewable",
    "fossil fuel", "esg",
)
# NLI stance hypotheses — used when enable_stance=True
STANCE_HYPOTHESES = [
    ("bullish", "This article expresses an optimistic or positive outlook."),
    ("bearish", "This article expresses a pessimistic or negative outlook."),
    ("risk",    "This article describes a material risk, threat, or downside."),
]

# Asymmetric risk weights — BRG cares more about negative tail
NEG_RISK_BOOST = 1.18
POS_BIAS_DAMP  = 0.95
TITLE_WEIGHT   = 0.65   # share of doc score that title contributes
DEFAULT_TEMPERATURE = 1.30  # > 1 softens overconfident logits

# FLS labels exposed by FinBERT-FLS:
#   "Specific FLS", "Non-specific FLS", "Not FLS"
# ESG labels exposed by FinBERT-ESG:
#   "Environmental", "Social", "Governance", "None"


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ComponentScore:
    """Score from one specialist model."""
    name: str
    score: float           # [-1, 1]
    confidence: float      # [0, 1]
    label: str             # positive | negative | neutral | n/a
    probs: Dict[str, float] = field(default_factory=dict)


@dataclass
class AspectSentiment:
    """Sentiment for one entity / aspect."""
    entity: str
    score: float
    mentions: int
    sentences: List[str] = field(default_factory=list)


@dataclass
class RAMMEResult:
    """Full output of the risk-aware ensemble."""
    score: float                                # final aggregated sentiment, [-1, 1]
    label: str                                  # positive | negative | neutral | abstain
    confidence: float                           # calibrated, [0, 1]
    raw_confidence: float                       # pre-calibration model confidence
    risk_score: float                           # asymmetric, downside-amplified [-1, 1]
    domain: str                                 # finance | geopolitics | general
    title_score: float = 0.0
    body_score: float = 0.0
    fls: Dict[str, float] = field(default_factory=dict)        # forward-looking statement probs
    fls_flag: bool = False                                    # any FLS detected
    esg: Dict[str, float] = field(default_factory=dict)        # ESG bucket probs
    esg_flag: Optional[str] = None                            # primary ESG bucket if any
    stance: Dict[str, float] = field(default_factory=dict)    # NLI stance probs (bullish/bearish/risk)
    components: List[ComponentScore] = field(default_factory=list)
    agreement: float = 0.0                                    # 1 - std(component scores)
    aspects: List[AspectSentiment] = field(default_factory=list)
    abstain: bool = False
    abstain_reason: Optional[str] = None
    primary_model: str = ""

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["components"] = [asdict(c) for c in self.components]
        d["aspects"] = [asdict(a) for a in self.aspects]
        return d


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")


def _split_sentences(text: str) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []
    sents = _SENT_SPLIT.split(text)
    return [s.strip() for s in sents if s and len(s.strip()) > 4]


def _is_finance(themes: Optional[Sequence[str]]) -> bool:
    if not themes:
        return False
    return any(t in FINANCE_THEMES for t in themes)


def _classify_domain(text: str, themes: Optional[Sequence[str]]) -> str:
    """Lightweight keyword-based domain classifier (no model load)."""
    if _is_finance(themes):
        return "finance"
    txt = (text or "")[:1000].lower()
    geo_kws = ("sanction", "treaty", "diplomat", "military", "border",
               "geopolitic", "minister", "embassy", "regime", "iran",
               "strait of hormuz", "hormuz", "missile", "conflict",
               "ceasefire", "blockade", "naval")
    fin_kws = ("earnings", "guidance", "revenue", "dividend", "inflation",
               "fed ", "central bank", "interest rate", "ecb", "yield",
               "oil", "crude", "brent", "wti", "opec", "stocks", "shares",
               "market", "markets", "commodity", "commodities", "tanker",
               "shipping", "supply", "prices", "futures")
    geo = sum(1 for k in geo_kws if k in txt)
    fin = sum(1 for k in fin_kws if k in txt)
    if fin >= 2 and fin >= geo:
        return "finance"
    if geo >= 2:
        return "geopolitics"
    return "general"


def _temperature(probs: Dict[str, float], T: float = DEFAULT_TEMPERATURE) -> Dict[str, float]:
    """Apply temperature scaling to probability dict (softer when T>1)."""
    if not probs or T == 1.0:
        return probs
    import math
    eps = 1e-9
    logits = {k: math.log(max(v, eps)) for k, v in probs.items()}
    scaled = {k: v / T for k, v in logits.items()}
    m = max(scaled.values())
    exp = {k: math.exp(v - m) for k, v in scaled.items()}
    s = sum(exp.values()) or 1.0
    return {k: v / s for k, v in exp.items()}


def _label_from_score(score: float) -> str:
    if score > 0.10:
        return "positive"
    if score < -0.10:
        return "negative"
    return "neutral"


def _asymmetric_risk(score: float) -> float:
    """Apply BRG's downside-amplification."""
    if score < 0:
        return max(-1.0, score * NEG_RISK_BOOST)
    return score * POS_BIAS_DAMP


def _normalize_probs(items, model_name: str = "") -> Dict[str, float]:
    """HF pipeline output -> {positive, negative, neutral} dict.

    Handles a variety of label conventions used by the specialist models:
      - LABEL_0/1/2 (Twitter-RoBERTa: neg/neu/pos)
      - "Positive"/"Negative"/"Neutral" (FinBERT-Tone)
      - "positive"/"negative" (RoBERTa-financial-news, no neutral)
    """
    out: Dict[str, float] = {}
    if not items:
        return out
    if isinstance(items, list) and items and isinstance(items[0], list):
        items = items[0]
    if not isinstance(items, list):
        return out
    for item in items:
        lbl = str(item.get("label", "")).strip().lower()
        if lbl.startswith("label_"):
            try:
                idx = int(lbl.split("_", 1)[1])
                lbl = ["negative", "neutral", "positive"][idx]
            except Exception:
                continue
        # FinBERT-Tone uses Positive/Negative/Neutral
        if lbl in ("positive", "pos"):
            out["positive"] = float(item.get("score", 0))
        elif lbl in ("negative", "neg"):
            out["negative"] = float(item.get("score", 0))
        elif lbl in ("neutral", "neu"):
            out["neutral"] = float(item.get("score", 0))
        # FinBERT-FLS labels
        elif "fls" in lbl or "specific" in lbl:
            out[lbl] = float(item.get("score", 0))
        # FinBERT-ESG labels
        elif lbl in ("environmental", "social", "governance", "none"):
            out[lbl] = float(item.get("score", 0))
    # If only positive/negative present, infer neutral residual
    if "neutral" not in out and ("positive" in out or "negative" in out):
        out["neutral"] = max(0.0, 1.0 - out.get("positive", 0) - out.get("negative", 0))
    return out


_NEGATIVE_RISK_TERMS: Dict[str, float] = {
    "threat": 0.28, "threaten": 0.28, "risk": 0.22, "fear": 0.20,
    "warning": 0.18, "warn": 0.18, "disrupt": 0.26, "disruption": 0.26,
    "disruptions": 0.26, "disrupted": 0.24,
    "standoff": 0.22, "tension": 0.20, "tensions": 0.20,
    "stalled": 0.22, "no progress": 0.20, "limbo": 0.16,
    "conflict": 0.25, "war": 0.30, "attack": 0.30, "strike": 0.24,
    "menace": 0.26, "menaces": 0.26,
    "sanction": 0.22, "sanctions": 0.22, "blockade": 0.30,
    "restrict": 0.20, "restricts": 0.20, "restriction": 0.20,
    "closure": 0.28, "closed": 0.20,
    "crisis": 0.30, "plunge": 0.26, "slump": 0.22, "fall": 0.14,
    "lower": 0.12, "loss": 0.20, "losses": 0.20, "default": 0.32,
    "inflation": 0.18, "shortage": 0.24, "shortages": 0.24,
    "lawsuit": 0.24, "probe": 0.20, "fraud": 0.34,
}

_POSITIVE_TERMS: Dict[str, float] = {
    "gain": 0.18, "gains": 0.18, "climb": 0.16, "rally": 0.22,
    "rise": 0.14, "rises": 0.14, "surge": 0.10, "surges": 0.10,
    "advance": 0.16, "advanced": 0.16, "recover": 0.20,
    "deal": 0.24, "agreement": 0.24, "ceasefire": 0.24,
    "progress": 0.18, "ease": 0.22, "eases": 0.22,
    "growth": 0.18, "profit": 0.20, "beat": 0.18,
}

_FLS_TERMS = (
    "will", "would", "could", "may", "might", "expects", "expected",
    "forecast", "forecasted", "projected", "projection", "outlook",
    "guidance", "plans to", "aims to", "likely to", "set to",
)

_ESG_BUCKET_TERMS: Dict[str, Tuple[str, ...]] = {
    "environmental": (
        "climate", "emissions", "carbon", "pollution", "renewable",
        "fossil fuel", "oil spill", "environmental",
    ),
    "social": (
        "labor", "workers", "human rights", "diversity", "boycott",
        "safety", "community", "supply chain",
    ),
    "governance": (
        "governance", "board", "fraud", "lawsuit", "probe",
        "investigation", "compliance", "regulation", "regulatory",
    ),
}


def _contains_term(text: str, term: str) -> bool:
    if " " in term:
        return term in text
    return re.search(rf"\b{re.escape(term)}\b", text) is not None


def _probs_from_score(score: float) -> Dict[str, float]:
    score = max(-1.0, min(1.0, score))
    return {
        "positive": max(0.0, score),
        "negative": max(0.0, -score),
        "neutral": max(0.0, 1.0 - abs(score)),
    }


# ---------------------------------------------------------------------------
# Risk-aware ensemble
# ---------------------------------------------------------------------------


class RiskAwareEnsemble:
    """The BRG RAMME pipeline.

    Lazily routes inference to the HF Inference API (preferred) or local
    transformers (fallback). Components are selected based on the document's
    domain so non-finance news doesn't pay for FinBERT inference.
    """

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        title_weight: float = TITLE_WEIGHT,
        max_aspect_entities: int = 5,
        enable_fls: bool = True,
        enable_esg: bool = True,
        enable_stance: bool = False,  # NLI is heavy; off by default
    ):
        self.weights = weights or {
            "fin_tone":     0.40,
            "fin_news":     0.25,
            "news_roberta": 0.35,
        }
        self.temperature = temperature
        self.title_weight = title_weight
        self.max_aspect_entities = max_aspect_entities
        self.enable_fls = enable_fls
        self.enable_esg = enable_esg
        self.enable_stance = enable_stance
        self._calibrator = None
        self._calibrator_checked = False
        # Cache loaded local transformers pipelines so we don't re-load
        # one per call (the dominant latency cost in fallback mode).
        self._local_pipes: Dict[str, object] = {}

    # ---- Public API -----------------------------------------------------

    def score_text(
        self,
        text: str,
        title: Optional[str] = None,
        themes: Optional[Sequence[str]] = None,
        entities: Optional[Sequence[str]] = None,
    ) -> RAMMEResult:
        return self.score_batch(
            [text],
            titles=[title] if title is not None else None,
            themes_per_text=[list(themes) if themes else None],
            entities_per_text=[list(entities) if entities else None],
        )[0]

    def score_batch(
        self,
        texts: Sequence[str],
        titles: Optional[Sequence[Optional[str]]] = None,
        themes_per_text: Optional[Sequence[Optional[Sequence[str]]]] = None,
        entities_per_text: Optional[Sequence[Optional[Sequence[str]]]] = None,
    ) -> List[RAMMEResult]:
        n = len(texts)
        titles = list(titles) if titles else [None] * n
        themes_per_text = list(themes_per_text) if themes_per_text else [None] * n
        entities_per_text = list(entities_per_text) if entities_per_text else [None] * n

        domains = [
            _classify_domain(f"{titles[i] or ''} {texts[i] or ''}", themes_per_text[i])
            for i in range(n)
        ]
        results: List[RAMMEResult] = [
            RAMMEResult(score=0.0, label="neutral", confidence=0.0,
                        raw_confidence=0.0, risk_score=0.0, domain=d)
            for d in domains
        ]

        # ---- Stage 1: doc-level component scoring ----------------------
        body_inputs = [(i, (texts[i] or "")[:1800]) for i in range(n) if texts[i]]
        title_inputs = [(i, (titles[i] or "")[:512]) for i in range(n) if titles[i]]

        # Pick which models to call per index, based on domain
        models_for_idx: Dict[int, List[str]] = {}
        for i, dom in enumerate(domains):
            if dom == "finance":
                models_for_idx[i] = ["fin_tone", "fin_news", "news_roberta"]
            elif dom == "geopolitics":
                models_for_idx[i] = ["news_roberta", "fin_tone"]
            else:
                models_for_idx[i] = ["news_roberta"]

        # Doc-level
        body_results: Dict[Tuple[int, str], Dict[str, float]] = {}
        for model_key in MODELS:
            if MODELS[model_key]["kind"] != "sentiment":
                continue
            indices = [i for i in range(n) if model_key in models_for_idx.get(i, [])]
            if not indices:
                continue
            inputs = [texts[i] or "" for i in indices]
            preds = self._run_sentiment(MODELS[model_key]["id"], inputs)
            for i, p in zip(indices, preds):
                body_results[(i, model_key)] = p

        # Title-level (only finance/geo where titles matter)
        title_results: Dict[Tuple[int, str], Dict[str, float]] = {}
        for model_key in ("fin_tone", "news_roberta"):
            indices = [i for i in range(n) if titles[i] and model_key in models_for_idx.get(i, [])]
            if not indices:
                continue
            inputs = [titles[i] or "" for i in indices]
            preds = self._run_sentiment(MODELS[model_key]["id"], inputs)
            for i, p in zip(indices, preds):
                title_results[(i, model_key)] = p

        # FLS detection — only on finance docs
        fls_results: Dict[int, Dict[str, float]] = {}
        if self.enable_fls:
            fls_idx = [i for i in range(n) if domains[i] == "finance" and texts[i]]
            if fls_idx:
                preds = self._run_sentiment(MODELS["fin_fls"]["id"],
                                            [texts[i][:1500] for i in fls_idx])
                for i, p in zip(fls_idx, preds):
                    fls_results[i] = p

        # ESG detection — fire on finance docs *and* on any doc whose body
        # contains corporate/policy keywords (e.g. labor disputes, climate
        # regulation, governance scandals are not always tagged "finance").
        esg_results: Dict[int, Dict[str, float]] = {}
        if self.enable_esg:
            esg_idx = []
            for i in range(n):
                if not texts[i]:
                    continue
                if domains[i] == "finance":
                    esg_idx.append(i); continue
                lower = texts[i][:2000].lower()
                if any(kw in lower for kw in ESG_KEYWORDS):
                    esg_idx.append(i)
            if esg_idx:
                preds = self._run_sentiment(MODELS["fin_esg"]["id"],
                                            [texts[i][:1500] for i in esg_idx])
                for i, p in zip(esg_idx, preds):
                    esg_results[i] = p

        # Stance hypothesis testing via NLI (heavy — off by default)
        stance_results: Dict[int, Dict[str, float]] = {}
        if self.enable_stance:
            stance_idx = [i for i in range(n) if texts[i]]
            if stance_idx:
                stance_results = self._run_stance(
                    [(texts[i][:1500]) for i in stance_idx],
                    indices=stance_idx,
                )

        # ---- Stage 2: aggregate per document ---------------------------
        for i in range(n):
            r = results[i]
            r.fls = _temperature(fls_results.get(i, {}), self.temperature)
            r.fls_flag = bool(r.fls and (
                r.fls.get("specific fls", 0) + r.fls.get("non-specific fls", 0) > 0.5
            ))
            r.esg = _temperature(esg_results.get(i, {}), self.temperature)
            if r.esg:
                primary = max(r.esg.items(), key=lambda kv: kv[1])
                if primary[1] > 0.4 and primary[0] != "none":
                    r.esg_flag = primary[0]

            comps: List[ComponentScore] = []
            for model_key in models_for_idx.get(i, []):
                probs = body_results.get((i, model_key), {})
                if not probs:
                    continue
                probs = _temperature(probs, self.temperature)
                pos = probs.get("positive", 0.0)
                neg = probs.get("negative", 0.0)
                score = pos - neg
                conf = max(probs.values()) if probs else 0.0
                comps.append(ComponentScore(
                    name=model_key, score=score, confidence=conf,
                    label=_label_from_score(score), probs=probs,
                ))
            r.components = comps

            body_score = self._weighted_score(comps)
            r.body_score = body_score

            # Title score: small ensemble (fin_tone + news_roberta when present)
            tcomps: List[ComponentScore] = []
            for model_key in ("fin_tone", "news_roberta"):
                tprobs = title_results.get((i, model_key), {})
                if not tprobs:
                    continue
                tprobs = _temperature(tprobs, self.temperature)
                tpos = tprobs.get("positive", 0.0)
                tneg = tprobs.get("negative", 0.0)
                tscore = tpos - tneg
                tcomps.append(ComponentScore(
                    name=f"{model_key}_title", score=tscore,
                    confidence=max(tprobs.values()) if tprobs else 0.0,
                    label=_label_from_score(tscore), probs=tprobs,
                ))
            title_score = self._weighted_score(tcomps) if tcomps else 0.0
            r.title_score = title_score

            # Combined score: title-weighted blend
            if tcomps:
                combined = self.title_weight * title_score + (1.0 - self.title_weight) * body_score
            else:
                combined = body_score

            # Risk-aware asymmetric weighting
            r.score = combined
            r.risk_score = _asymmetric_risk(combined)
            r.label = _label_from_score(combined)
            # Primary model = highest weight × confidence contributor (not first)
            if comps:
                def _contrib(c: ComponentScore) -> float:
                    base = c.name.replace("_title", "")
                    return self.weights.get(base, 0.20) * (0.5 + 0.5 * c.confidence)
                r.primary_model = max(comps, key=_contrib).name
            else:
                r.primary_model = "n/a"

            # Attach NLI stance hypothesis scores (when enable_stance=True)
            if stance_results.get(i):
                r.stance = stance_results[i]
                # If risk hypothesis dominates, nudge label/risk_score down
                risk_p = r.stance.get("risk", 0.0)
                if risk_p > 0.65 and r.score > -0.30:
                    r.risk_score = _asymmetric_risk(min(r.score, -0.20))

            # Confidence: average of component confidences scaled by agreement
            scores = [c.score for c in comps] or [0.0]
            agreement = 1.0 - (max(scores) - min(scores)) / 2.0  # 0 (max disagreement) → 1
            r.agreement = max(0.0, min(1.0, agreement))
            mean_conf = sum(c.confidence for c in comps) / max(len(comps), 1)
            r.raw_confidence = mean_conf * (0.5 + 0.5 * r.agreement)
            r.confidence = self._calibrate(r.raw_confidence)

            # Abstain when disagreement is high and confidence weak
            if r.raw_confidence < 0.40 and r.agreement < 0.55:
                r.abstain = True
                r.abstain_reason = "low_confidence_high_disagreement"
                r.label = "abstain"

            # Stage 3: per-entity ABSA (sentence-level)
            ents = list(entities_per_text[i] or [])[: self.max_aspect_entities]
            if ents and texts[i]:
                r.aspects = self._aspect_sentiment(texts[i], ents)

        return results

    # ---- Internal: model dispatch --------------------------------------

    def _run_sentiment(self, model_id: str, texts: Sequence[str]) -> List[Dict[str, float]]:
        """Run a sentiment-style classifier on a batch. Returns list of prob dicts."""
        # Try remote first
        try:
            from . import hf_inference as hf
            if hf.is_available():
                raw = hf.sentiment_batch(list(texts), model=model_id, max_workers=8)
                # raw items are {label, score, confidence, probs}
                probs = []
                for r in raw:
                    r = r or {}
                    probs.append(
                        r.get("probs") or _normalize_probs([{
                            "label": r.get("label", "neutral"),
                            "score": r.get("confidence", 0),
                        }])
                    )
                return self._fill_empty_probs(model_id, texts, probs)
        except Exception as e:
            logger.debug(f"Remote sentiment failed for {model_id}: {e}")

        # Local fallback
        try:
            return self._run_sentiment_local(model_id, texts)
        except Exception as e:
            logger.debug(f"Local sentiment failed for {model_id}: {e}")
            return self._run_lightweight_fallback(model_id, texts)

    def _run_sentiment_local(self, model_id: str, texts: Sequence[str]) -> List[Dict[str, float]]:
        pipe = self._get_local_pipe(model_id, task="text-classification")
        outs = pipe([t[:1800] for t in texts], batch_size=8)
        return self._fill_empty_probs(
            model_id,
            texts,
            [_normalize_probs(o, model_id) for o in outs],
        )

    def _fill_empty_probs(
        self,
        model_id: str,
        texts: Sequence[str],
        probs: Sequence[Dict[str, float]],
    ) -> List[Dict[str, float]]:
        fallback = None
        out: List[Dict[str, float]] = []
        for text, p in zip(texts, probs):
            if p:
                out.append(dict(p))
                continue
            if fallback is None:
                fallback = self._run_lightweight_fallback(model_id, texts)
            out.append(fallback[len(out)])
        return out

    def _get_local_pipe(self, model_id: str, task: str = "text-classification"):
        """Return a cached local transformers pipeline. Loads once per model.

        This is the single biggest cost-saver in fallback mode — without
        the cache, every batch call would re-load the model from disk."""
        key = f"{task}::{model_id}"
        cached = self._local_pipes.get(key)
        if cached is not None:
            return cached
        from transformers import pipeline as hf_pipeline
        try:
            from transformers.utils import logging as hf_logging
            hf_logging.set_verbosity_error()
        except Exception:
            pass
        try:
            import torch
            device = ("mps" if torch.backends.mps.is_available()
                     else ("cuda:0" if torch.cuda.is_available() else "cpu"))
        except Exception:
            device = "cpu"
        pipe = hf_pipeline(
            task,
            model=model_id,
            device=device if device != "cpu" else -1,
            token=False,
            top_k=None if task == "text-classification" else 1,
            truncation=True,
            max_length=512,
        )
        self._local_pipes[key] = pipe
        return pipe

    # ---- Lightweight fallback -----------------------------------------

    def _run_lightweight_fallback(self, model_id: str, texts: Sequence[str]) -> List[Dict[str, float]]:
        """Dependency-free fallback used when HF and local transformers fail.

        This keeps the classifier useful in the default lightweight install.
        It is intentionally conservative, but it must not return empty
        component lists because empty components collapse the run to all
        neutral.
        """
        if model_id == MODELS["fin_fls"]["id"]:
            return [self._fls_fallback(t) for t in texts]
        if model_id == MODELS["fin_esg"]["id"]:
            return [self._esg_fallback(t) for t in texts]
        return [self._sentiment_fallback(t) for t in texts]

    def _sentiment_fallback(self, text: str) -> Dict[str, float]:
        txt = (text or "")[:2500].lower()
        if not txt.strip():
            return {"positive": 0.0, "negative": 0.0, "neutral": 1.0}

        vader_score = 0.0
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            analyzer = getattr(self, "_vader", None)
            if analyzer is None:
                analyzer = SentimentIntensityAnalyzer()
                self._vader = analyzer
            vader_score = float(analyzer.polarity_scores(txt)["compound"])
        except Exception:
            vader_score = 0.0

        neg = sum(w for term, w in _NEGATIVE_RISK_TERMS.items() if _contains_term(txt, term))
        pos = sum(w for term, w in _POSITIVE_TERMS.items() if _contains_term(txt, term))

        # In commodity/geopolitical news, rising prices caused by supply shocks
        # are a risk signal even when words like "climb" look positive.
        oil_context = any(k in txt for k in ("oil", "crude", "brent", "wti", "hormuz", "tanker"))
        shock_context = any(k in txt for k in ("threat", "standoff", "disrupt", "sanction", "war", "conflict", "restrict"))
        if oil_context and shock_context and any(k in txt for k in ("rise", "rises", "surge", "surges", "climb", "climbs")):
            neg += 0.22
            pos *= 0.65

        lex_score = 0.0
        if pos or neg:
            lex_score = max(-0.85, min(0.85, (pos - neg) / max(pos + neg, 0.8)))

        score = (0.45 * vader_score) + (0.55 * lex_score)
        if abs(score) < 0.04 and (pos or neg):
            score = 0.12 if pos > neg else -0.12
        return _probs_from_score(score)

    def _fls_fallback(self, text: str) -> Dict[str, float]:
        txt = (text or "").lower()
        hits = sum(1 for term in _FLS_TERMS if term in txt)
        if hits <= 0:
            return {"specific fls": 0.05, "non-specific fls": 0.10, "not fls": 0.85}
        specific = min(0.70, 0.18 + 0.12 * hits)
        nonspecific = min(0.45, 0.12 + 0.06 * hits)
        not_fls = max(0.05, 1.0 - specific - nonspecific)
        return {"specific fls": specific, "non-specific fls": nonspecific, "not fls": not_fls}

    def _esg_fallback(self, text: str) -> Dict[str, float]:
        txt = (text or "").lower()
        scores = {
            bucket: sum(1 for term in terms if term in txt)
            for bucket, terms in _ESG_BUCKET_TERMS.items()
        }
        bucket, hits = max(scores.items(), key=lambda kv: kv[1])
        if hits <= 0:
            return {"environmental": 0.05, "social": 0.05, "governance": 0.05, "none": 0.85}
        strength = min(0.75, 0.35 + 0.12 * hits)
        rest = (1.0 - strength) / 3.0
        out = {"environmental": rest, "social": rest, "governance": rest, "none": rest}
        out[bucket] = strength
        return out

    # ---- Stance via NLI (zero-shot hypothesis testing) ------------------

    def _run_stance(self, texts: Sequence[str],
                    indices: Sequence[int]) -> Dict[int, Dict[str, float]]:
        """Run zero-shot NLI against BRG stance hypotheses (bullish/bearish/risk).

        Uses the HF Inference API zero-shot endpoint when available, else a
        local zero-shot pipeline. Returns {idx: {hypothesis_label: score}}."""
        labels = [h[0] for h in STANCE_HYPOTHESES]
        # Try remote zero-shot first
        try:
            from . import hf_inference as hf
            if hasattr(hf, "zero_shot_batch") and hf.is_available():
                raw = hf.zero_shot_batch(list(texts),
                                          candidate_labels=labels,
                                          model=MODELS["stance_nli"]["id"])
                return {idx: {lbl: float(score)
                              for lbl, score in zip(r.get("labels", []), r.get("scores", []))}
                        for idx, r in zip(indices, raw)}
        except Exception as e:
            logger.debug(f"Remote stance NLI failed: {e}")

        # Local fallback — heavy
        try:
            from transformers import pipeline as hf_pipeline
            try:
                import torch
                device = ("mps" if torch.backends.mps.is_available()
                         else ("cuda:0" if torch.cuda.is_available() else "cpu"))
            except Exception:
                device = "cpu"
            key = f"zero-shot::{MODELS['stance_nli']['id']}"
            pipe = self._local_pipes.get(key)
            if pipe is None:
                pipe = hf_pipeline(
                    "zero-shot-classification",
                    model=MODELS["stance_nli"]["id"],
                    device=device if device != "cpu" else -1,
                )
                self._local_pipes[key] = pipe
            outs = pipe(list(texts), candidate_labels=labels, multi_label=True)
            if isinstance(outs, dict):
                outs = [outs]
            return {idx: {lbl: float(score)
                          for lbl, score in zip(o["labels"], o["scores"])}
                    for idx, o in zip(indices, outs)}
        except Exception as e:
            logger.debug(f"Local stance NLI failed: {e}")
            return {}

    # ---- Aggregation & calibration -------------------------------------

    def _weighted_score(self, comps: List[ComponentScore]) -> float:
        if not comps:
            return 0.0
        total = 0.0
        wsum = 0.0
        for c in comps:
            base = c.name.replace("_title", "")
            w = self.weights.get(base, 0.20)
            # Confidence-weighted: confident components count more
            w *= 0.5 + 0.5 * c.confidence
            total += c.score * w
            wsum += w
        return total / wsum if wsum > 0 else 0.0

    def _calibrate(self, raw: float) -> float:
        """Run raw confidence through ConfidenceCalibrator (isotonic if fitted)."""
        if not self._calibrator_checked:
            try:
                from .confidence_calibrator import ConfidenceCalibrator
                self._calibrator = ConfidenceCalibrator()
            except Exception:
                self._calibrator = None
            self._calibrator_checked = True
        if self._calibrator is not None:
            try:
                return float(self._calibrator.calibrate(raw))
            except Exception:
                pass
        # Heuristic fallback: shrink toward 0.5
        return 0.5 + (raw - 0.5) * 0.7

    # ---- Entity-aware ABSA ---------------------------------------------

    def _aspect_sentiment(self, text: str, entities: Sequence[str]) -> List[AspectSentiment]:
        """Score sentiment in sentences mentioning each entity."""
        sents = _split_sentences(text)
        if not sents:
            return []

        ent_to_sents: Dict[str, List[str]] = {}
        for ent in entities:
            ent_l = ent.lower()
            hits = [s for s in sents if ent_l in s.lower()][:5]
            if hits:
                ent_to_sents[ent] = hits

        if not ent_to_sents:
            return []

        # Flatten and run a single batched sentiment call
        flat_sents: List[str] = []
        flat_owner: List[str] = []
        for ent, sl in ent_to_sents.items():
            for s in sl:
                flat_sents.append(s)
                flat_owner.append(ent)

        # Use FinBERT-Tone for finance-y entity ABSA — it works well
        # on individual sentences and gives clean 3-class output.
        probs_list = self._run_sentiment(MODELS["fin_tone"]["id"], flat_sents)

        agg: Dict[str, List[float]] = {ent: [] for ent in ent_to_sents}
        for ent, probs in zip(flat_owner, probs_list):
            if not probs:
                continue
            score = probs.get("positive", 0) - probs.get("negative", 0)
            agg[ent].append(score)

        out: List[AspectSentiment] = []
        for ent, sl in ent_to_sents.items():
            scores = agg.get(ent, [])
            if not scores:
                continue
            avg = sum(scores) / len(scores)
            out.append(AspectSentiment(
                entity=ent,
                score=avg,
                mentions=len(sl),
                sentences=sl[:3],
            ))
        out.sort(key=lambda a: abs(a.score), reverse=True)
        return out


# ---------------------------------------------------------------------------
# Convenience module-level helpers
# ---------------------------------------------------------------------------


_singleton: Optional[RiskAwareEnsemble] = None


def get_pipeline() -> RiskAwareEnsemble:
    global _singleton
    if _singleton is None:
        _singleton = RiskAwareEnsemble()
    return _singleton


def score_text(text: str, **kwargs) -> RAMMEResult:
    return get_pipeline().score_text(text, **kwargs)


def score_batch(texts: Sequence[str], **kwargs) -> List[RAMMEResult]:
    return get_pipeline().score_batch(texts, **kwargs)
