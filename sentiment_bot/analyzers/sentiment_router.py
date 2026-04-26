"""
Domain-routed sentiment. Replaces VADER as the default hot path.

Financial articles -> FinBERT
Everything else -> news-RoBERTa (CardiffNLP)

Uses HF Inference API (free remote GPU) by default.
Falls back to local inference if HF_TOKEN not set or API down.
Falls back to VADER only with --fast flag.
"""

from __future__ import annotations
import logging
import os
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

FINANCIAL_THEMES = {
    "inflation", "monetary_policy", "economic_growth",
    "markets", "banking", "earnings", "commodities",
}

FINBERT_MODEL = "yiyanghkust/finbert-tone"
NEWS_MODEL = "cardiffnlp/twitter-roberta-base-sentiment-latest"


@dataclass
class SentimentResult:
    score: float          # continuous, [-1, 1]
    label: str            # "positive" | "negative" | "neutral"
    confidence: float     # [0, 1]
    model: str            # which model produced this
    raw_probs: dict       # {"positive": 0.7, "negative": 0.1, "neutral": 0.2}
    # Optional rich RAMME payload (fls, esg, components, aspects, agreement,
    # abstain reason, stance, etc.). Populated when the RAMME pipeline ran.
    # Stored as a plain dict so existing pydantic serializers keep working.
    ramme: Optional[dict] = None


def _is_financial(themes: list[str] | None) -> bool:
    if not themes:
        return False
    return any(t in FINANCIAL_THEMES for t in themes)


def _chunk_text(text: str, max_chars: int = 1800) -> list[str]:
    """Split long text into model-safe chunks."""
    if len(text) <= max_chars:
        return [text]
    chunks = []
    for para in text.split("\n\n"):
        if len(para) <= max_chars:
            chunks.append(para)
        else:
            sents = para.replace("? ", "?|").replace("! ", "!|").replace(". ", ".|").split("|")
            buf = ""
            for s in sents:
                if len(buf) + len(s) > max_chars:
                    if buf:
                        chunks.append(buf)
                    buf = s
                else:
                    buf += s
            if buf:
                chunks.append(buf)
    return chunks or [text[:max_chars]]


def _normalize_probs(raw: list[dict]) -> dict:
    """HF pipeline output -> {positive, negative, neutral} dict."""
    out = {}
    for item in raw:
        lbl = item["label"].lower()
        if lbl.startswith("label_"):
            idx = int(lbl.split("_")[1])
            lbl = ["negative", "neutral", "positive"][idx]
        out[lbl] = item["score"]
    return out


def _probs_to_result(probs: dict, model_name: str) -> SentimentResult:
    pos = probs.get("positive", 0.0)
    neg = probs.get("negative", 0.0)
    score = pos - neg
    if score > 0.05:
        label = "positive"
    elif score < -0.05:
        label = "negative"
    else:
        label = "neutral"
    confidence = max(probs.values()) if probs else 0.0
    return SentimentResult(score, label, confidence, model_name, probs)


def analyze_batch_remote(
    texts: list[str],
    themes_per_text: list[list[str] | None] | None = None,
) -> list[SentimentResult]:
    """
    Batch sentiment via HF Inference API (free remote GPU).
    Routes financial texts to FinBERT, everything else to news-RoBERTa.
    """
    from . import hf_inference as hf

    if themes_per_text is None:
        themes_per_text = [None] * len(texts)

    results: list[SentimentResult | None] = [None] * len(texts)

    # Separate financial vs general
    fin_indices = [i for i, th in enumerate(themes_per_text) if _is_financial(th)]
    gen_indices = [i for i in range(len(texts)) if i not in set(fin_indices)]

    for indices, model, model_name in [
        (fin_indices, FINBERT_MODEL, "finbert-tone"),
        (gen_indices, NEWS_MODEL, "news-roberta"),
    ]:
        if not indices:
            continue

        batch_texts = []
        for i in indices:
            text = texts[i]
            if not text or not text.strip():
                results[i] = SentimentResult(0.0, "neutral", 0.0, model_name, {})
                continue
            # For chunked texts, take first chunk (API doesn't batch well with chunks)
            chunks = _chunk_text(text)
            batch_texts.append((i, chunks[0]))

        if not batch_texts:
            continue

        # Concurrent API calls
        api_results = hf.sentiment_batch(
            [t for _, t in batch_texts],
            model=model,
            max_workers=10,
        )

        for (orig_idx, _), api_result in zip(batch_texts, api_results):
            results[orig_idx] = SentimentResult(
                score=api_result.get("score", 0.0),
                label=api_result.get("label", "neutral"),
                confidence=api_result.get("confidence", 0.0),
                model=model_name,
                raw_probs=api_result.get("probs", {}),
            )

    # Fill any gaps
    for i in range(len(results)):
        if results[i] is None:
            results[i] = SentimentResult(0.0, "neutral", 0.0, "unknown", {})

    return results


def analyze_batch_local(
    texts: list[str],
    themes_per_text: list[list[str] | None] | None = None,
    batch_size: int = 8,
) -> list[SentimentResult]:
    """
    Batch sentiment via local transformers (MPS/CUDA/CPU).
    Only used as fallback when remote API is unavailable.
    """
    try:
        from transformers import pipeline as hf_pipeline
        import torch
    except ImportError:
        logger.warning("transformers not installed, falling back to VADER")
        return analyze_batch_vader(texts)

    device = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")

    if themes_per_text is None:
        themes_per_text = [None] * len(texts)

    results: list[SentimentResult | None] = [None] * len(texts)

    fin_indices = [i for i, th in enumerate(themes_per_text) if _is_financial(th)]
    gen_indices = [i for i in range(len(texts)) if i not in set(fin_indices)]

    for indices, model_id, model_name in [
        (fin_indices, FINBERT_MODEL, "finbert-tone"),
        (gen_indices, NEWS_MODEL, "news-roberta"),
    ]:
        if not indices:
            continue

        try:
            pipe = hf_pipeline(
                "sentiment-analysis",
                model=model_id,
                device=device,
                top_k=None,
                truncation=True,
                max_length=512,
            )
        except Exception as e:
            logger.warning(f"Failed to load {model_id}: {e}")
            for i in indices:
                results[i] = SentimentResult(0.0, "neutral", 0.0, "error", {})
            continue

        batch = [(i, texts[i][:1800]) for i in indices if texts[i] and texts[i].strip()]
        for i in indices:
            if not texts[i] or not texts[i].strip():
                results[i] = SentimentResult(0.0, "neutral", 0.0, model_name, {})

        if batch:
            raw_outputs = pipe([t for _, t in batch], batch_size=batch_size)
            for (orig_idx, _), raw in zip(batch, raw_outputs):
                probs = _normalize_probs(raw)
                results[orig_idx] = _probs_to_result(probs, model_name)

    for i in range(len(results)):
        if results[i] is None:
            results[i] = SentimentResult(0.0, "neutral", 0.0, "unknown", {})

    return results


def analyze_batch_vader(texts: list[str]) -> list[SentimentResult]:
    """VADER fallback. Only used with --fast flag."""
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    vader = SentimentIntensityAnalyzer()
    results = []
    for text in texts:
        if not text:
            results.append(SentimentResult(0.0, "neutral", 0.0, "vader", {}))
            continue
        s = vader.polarity_scores(text[:2000])
        score = s["compound"]
        label = "positive" if score > 0.05 else ("negative" if score < -0.05 else "neutral")
        results.append(SentimentResult(
            score=score,
            label=label,
            confidence=abs(score),
            model="vader",
            raw_probs={"positive": s["pos"], "negative": s["neg"], "neutral": s["neu"]},
        ))
    return results


def _ramme_to_legacy(r) -> SentimentResult:
    """Adapt a RAMMEResult into the legacy SentimentResult shape so existing
    callers (cli_unified, dashboard) keep working unchanged.

    The full rich payload (fls, esg, components, aspects, agreement,
    stance, abstain reason) is preserved on the `.ramme` attribute so
    downstream code can opt into the upgraded fields without a separate
    pipeline call."""
    primary = r.primary_model or "ramme"
    rich = r.to_dict() if hasattr(r, "to_dict") else None
    if getattr(r, "abstain", False) or r.label == "abstain":
        label = "neutral"
    else:
        label = "positive" if r.score > 0.05 else ("negative" if r.score < -0.05 else "neutral")
    return SentimentResult(
        score=r.score,
        label=label,
        confidence=r.confidence,
        model=f"ramme/{primary}",
        raw_probs={"positive": max(0.0,  r.score),
                   "negative": max(0.0, -r.score),
                   "neutral":  max(0.0, 1.0 - abs(r.score))},
        ramme=rich,
    )


def analyze_batch(
    texts: list[str],
    themes_per_text: list[list[str] | None] | None = None,
    titles: list[str | None] | None = None,
    entities_per_text: list[list[str] | None] | None = None,
    fast: bool = False,
    ramme: bool = True,
) -> list[SentimentResult]:
    """
    Main entry point. Risk-aware multi-model ensemble (RAMME) by default.

    Args:
        texts: article texts
        themes_per_text: themes per article for domain routing
        titles: optional headlines (used for title-weighted scoring)
        entities_per_text: optional entity lists for ABSA
        fast: if True, skip ML and use VADER
        ramme: if True (default), use the new BRG risk-aware ensemble.
               Set False to use the legacy FinBERT/RoBERTa router.
    """
    if fast:
        logger.info("--fast mode: using VADER")
        return analyze_batch_vader(texts)

    if ramme:
        try:
            from .finance_pipeline import RiskAwareEnsemble
            pipe = RiskAwareEnsemble()
            logger.info(f"Running RAMME on {len(texts)} articles")
            results = pipe.score_batch(
                texts,
                titles=titles,
                themes_per_text=themes_per_text,
                entities_per_text=entities_per_text,
            )
            return [_ramme_to_legacy(r) for r in results]
        except Exception as e:
            logger.warning(f"RAMME failed, falling back to legacy router: {e}")

    # Legacy path: try remote, then local
    try:
        from . import hf_inference as hf
        if hf.is_available():
            logger.info(f"Running sentiment on {len(texts)} articles via HF Inference API")
            return analyze_batch_remote(texts, themes_per_text)
    except Exception as e:
        logger.debug(f"Remote inference unavailable: {e}")

    logger.info(f"Running sentiment on {len(texts)} articles locally")
    return analyze_batch_local(texts, themes_per_text)


def analyze_batch_ramme(
    texts: list[str],
    titles: list[str | None] | None = None,
    themes_per_text: list[list[str] | None] | None = None,
    entities_per_text: list[list[str] | None] | None = None,
):
    """Return the rich RAMMEResult objects (not the legacy adapter).

    Use this when you need fls/esg/aspects/agreement — e.g. the dashboard's
    Risk Intelligence page.
    """
    from .finance_pipeline import RiskAwareEnsemble
    pipe = RiskAwareEnsemble()
    return pipe.score_batch(
        texts,
        titles=titles,
        themes_per_text=themes_per_text,
        entities_per_text=entities_per_text,
    )


def analyze_one(text: str, themes: list[str] | None = None) -> SentimentResult:
    return analyze_batch([text], [themes])[0]
