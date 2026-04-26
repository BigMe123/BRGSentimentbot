"""
Inter-model agreement / disagreement metrics.

When the specialist models in the RAMME ensemble disagree, the resulting
sentiment score is uncertain regardless of how confident any individual model
is. This module quantifies that uncertainty and exposes it for the dashboard.

Metrics:
- Pairwise label agreement (Cohen's-kappa-like)
- Score variance across models (std)
- Per-model bias (mean score offset vs ensemble)
- Confusion matrix between two models
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Dict, List, Sequence, Tuple

logger = logging.getLogger(__name__)


@dataclass
class AgreementStats:
    n_articles: int
    pairwise_agreement: Dict[str, float]   # "modelA|modelB" -> Cohen's kappa
    per_model_mean: Dict[str, float]
    per_model_bias: Dict[str, float]       # offset vs ensemble mean
    avg_score_std: float                   # average std of per-article scores
    avg_label_disagreement: float          # 0 (perfect agree) -> 1 (max disagree)


def _cohens_kappa(a: Sequence[str], b: Sequence[str]) -> float:
    """Symmetric agreement, corrected for chance. -1..1."""
    if len(a) != len(b) or not a:
        return 0.0
    labels = sorted(set(list(a) + list(b)))
    n = len(a)
    # Observed agreement
    obs = sum(1 for x, y in zip(a, b) if x == y) / n
    # Expected by chance
    pa = {l: a.count(l) / n for l in labels}
    pb = {l: b.count(l) / n for l in labels}
    exp = sum(pa[l] * pb[l] for l in labels)
    if exp >= 1.0:
        return 1.0
    return (obs - exp) / (1.0 - exp)


def compute_agreement(
    components_per_article: Sequence[Sequence[Tuple[str, float, str]]],
) -> AgreementStats:
    """
    components_per_article: each element is a list of (model_name, score, label)
    tuples for one article.
    """
    if not components_per_article:
        return AgreementStats(0, {}, {}, {}, 0.0, 0.0)

    # Bucket by model
    by_model_score: Dict[str, List[float]] = defaultdict(list)
    by_model_label: Dict[str, List[str]] = defaultdict(list)
    article_stds: List[float] = []
    label_disagreements: List[float] = []

    for comps in components_per_article:
        scores = [c[1] for c in comps]
        labels = [c[2] for c in comps]
        if scores:
            article_stds.append(pstdev(scores) if len(scores) > 1 else 0.0)
        if labels:
            distinct = len(set(labels))
            # 1 distinct label -> 0 disagreement; len(labels) distinct -> 1
            label_disagreements.append(
                (distinct - 1) / max(len(labels) - 1, 1)
            )
        for name, score, label in comps:
            by_model_score[name].append(score)
            by_model_label[name].append(label)

    per_model_mean = {m: mean(s) for m, s in by_model_score.items() if s}
    overall_mean = mean(per_model_mean.values()) if per_model_mean else 0.0
    per_model_bias = {m: v - overall_mean for m, v in per_model_mean.items()}

    # Pairwise kappa on labels
    models = sorted(by_model_label)
    pairwise: Dict[str, float] = {}
    for i, m1 in enumerate(models):
        for m2 in models[i + 1:]:
            # align: only use articles where both models scored
            a, b = by_model_label[m1], by_model_label[m2]
            min_n = min(len(a), len(b))
            if min_n < 5:
                continue
            pairwise[f"{m1}|{m2}"] = round(_cohens_kappa(a[:min_n], b[:min_n]), 3)

    return AgreementStats(
        n_articles=len(components_per_article),
        pairwise_agreement=pairwise,
        per_model_mean={k: round(v, 3) for k, v in per_model_mean.items()},
        per_model_bias={k: round(v, 3) for k, v in per_model_bias.items()},
        avg_score_std=round(mean(article_stds), 3) if article_stds else 0.0,
        avg_label_disagreement=round(mean(label_disagreements), 3) if label_disagreements else 0.0,
    )
