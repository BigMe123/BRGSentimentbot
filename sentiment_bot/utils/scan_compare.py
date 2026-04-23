"""
Compare two scan runs with bootstrap confidence intervals.

Resamples article-level sentiments 10k times and reports 95% CI on every
country delta. Only flags "Worsening" / "Improving" when the CI excludes zero.
"""

import json
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import defaultdict


def load_scan(jsonl_path: str) -> List[Dict]:
    """Load articles from a JSONL file."""
    articles = []
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    articles.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return articles


def _extract_country_sentiments(articles: List[Dict]) -> Dict[str, List[float]]:
    """Group article sentiments by mentioned countries."""
    country_scores = defaultdict(list)
    for article in articles:
        score = 0.0
        sent = article.get("sentiment", {})
        if isinstance(sent, dict):
            score = sent.get("score", 0.0)
        elif isinstance(sent, (int, float)):
            score = float(sent)

        entities = article.get("entities", [])
        countries = [e["text"] for e in entities if e.get("type") == "GPE"]

        if not countries:
            country_scores["_global"].append(score)
        else:
            for c in countries:
                country_scores[c].append(score)

    return dict(country_scores)


def bootstrap_ci(
    scores_a: List[float],
    scores_b: List[float],
    n_bootstrap: int = 10000,
    ci: float = 0.95,
) -> Tuple[float, float, float]:
    """
    Bootstrap confidence interval on the difference in means (B - A).

    Returns:
        (delta_mean, ci_lower, ci_upper)
    """
    a = np.array(scores_a)
    b = np.array(scores_b)
    observed_delta = np.mean(b) - np.mean(a)

    deltas = np.empty(n_bootstrap)
    rng = np.random.default_rng(42)

    for i in range(n_bootstrap):
        sample_a = rng.choice(a, size=len(a), replace=True)
        sample_b = rng.choice(b, size=len(b), replace=True)
        deltas[i] = np.mean(sample_b) - np.mean(sample_a)

    alpha = (1 - ci) / 2
    ci_lower = float(np.percentile(deltas, alpha * 100))
    ci_upper = float(np.percentile(deltas, (1 - alpha) * 100))

    return float(observed_delta), ci_lower, ci_upper


def compare_scans(
    path_a: str,
    path_b: str,
    min_articles: int = 3,
    n_bootstrap: int = 10000,
) -> Dict[str, Dict]:
    """
    Compare two scan runs with bootstrap CIs.

    Args:
        path_a: Path to older scan JSONL
        path_b: Path to newer scan JSONL
        min_articles: Minimum articles per country to include
        n_bootstrap: Number of bootstrap resamples

    Returns:
        {country: {delta, ci_lower, ci_upper, direction, significant, n_a, n_b}}
    """
    articles_a = load_scan(path_a)
    articles_b = load_scan(path_b)

    countries_a = _extract_country_sentiments(articles_a)
    countries_b = _extract_country_sentiments(articles_b)

    all_countries = set(countries_a.keys()) | set(countries_b.keys())
    results = {}

    for country in sorted(all_countries):
        scores_a = countries_a.get(country, [])
        scores_b = countries_b.get(country, [])

        if len(scores_a) < min_articles or len(scores_b) < min_articles:
            continue

        delta, ci_lower, ci_upper = bootstrap_ci(scores_a, scores_b, n_bootstrap)

        # Direction is significant only if CI excludes zero
        if ci_lower > 0:
            direction = "improving"
            significant = True
        elif ci_upper < 0:
            direction = "worsening"
            significant = True
        else:
            direction = "stable"
            significant = False

        results[country] = {
            "delta": round(delta, 4),
            "ci_lower": round(ci_lower, 4),
            "ci_upper": round(ci_upper, 4),
            "direction": direction,
            "significant": significant,
            "mean_a": round(float(np.mean(scores_a)), 4),
            "mean_b": round(float(np.mean(scores_b)), 4),
            "n_a": len(scores_a),
            "n_b": len(scores_b),
        }

    return results
