#!/usr/bin/env python3
"""
Sample 100 articles stratified across topics and source tiers for manual labeling.
Outputs tests/fixtures/gold_v1.jsonl with unlabeled records for human annotation.

Usage:
    python scripts/sample_gold_set.py
    # Then open tests/fixtures/gold_v1.jsonl and fill in the labels.
"""

import json
import os
import random
from collections import defaultdict
from pathlib import Path

random.seed(42)

OUTPUT = Path("tests/fixtures/gold_v1.jsonl")
TARGET = 100

# Stratification buckets
STRATA = {
    "geopolitical": ["Iran", "Sudan", "NATO", "sanctions", "conflict", "diplomacy", "defense"],
    "financial": ["trade policy", "banking", "markets", "economic", "oil", "energy"],
    "tech": ["AI regulation", "technology", "cybersecurity", "crypto"],
    "general": ["general"],
}

STRATA_TARGETS = {"geopolitical": 30, "financial": 30, "tech": 20, "general": 20}


def load_articles():
    articles = []
    output_dir = Path("output")
    for f in sorted(output_dir.glob("articles_*.jsonl")):
        with open(f) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    a = json.loads(line)
                    # Need enough text to label
                    if a.get("text_chars", 0) > 200 and a.get("summary", "").strip():
                        articles.append(a)
                except json.JSONDecodeError:
                    pass
    return articles


def classify_stratum(article):
    topic = (article.get("topic") or "general").lower()
    title = (article.get("title") or "").lower()
    combined = f"{topic} {title}"

    for stratum, keywords in STRATA.items():
        if any(kw.lower() in combined for kw in keywords):
            return stratum
    return "general"


def main():
    articles = load_articles()
    print(f"Loaded {len(articles)} articles with text")

    # Group by stratum
    buckets = defaultdict(list)
    for a in articles:
        s = classify_stratum(a)
        buckets[s].append(a)

    for s, items in buckets.items():
        print(f"  {s}: {len(items)} available")

    # Sample
    sampled = []
    for stratum, target in STRATA_TARGETS.items():
        pool = buckets.get(stratum, [])
        n = min(target, len(pool))
        sampled.extend(random.sample(pool, n))
        if n < target:
            print(f"  WARNING: only {n}/{target} for {stratum}")

    # Fill remainder from general if needed
    if len(sampled) < TARGET:
        remaining = TARGET - len(sampled)
        sampled_ids = {a["id"] for a in sampled}
        extras = [a for a in articles if a["id"] not in sampled_ids]
        sampled.extend(random.sample(extras, min(remaining, len(extras))))

    random.shuffle(sampled)
    print(f"\nSampled {len(sampled)} articles")

    # Write unlabeled gold set
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w") as f:
        for a in sampled:
            record = {
                "article_id": a["id"],
                "title": a["title"],
                "summary": a.get("summary", "")[:500],
                "source": a.get("source", ""),
                "topic": a.get("topic", ""),
                "url": a.get("url", ""),
                # LABEL THESE:
                "sentiment": None,        # -1, 0, or +1
                "entities": [],           # ["United States", "Fed", ...]
                "themes": [],             # ["monetary_policy", "conflict", ...]
                "notes": "",              # optional
            }
            f.write(json.dumps(record) + "\n")

    print(f"Written to {OUTPUT}")
    print(f"\nNext: open {OUTPUT} and label each article:")
    print('  "sentiment": -1 (negative), 0 (neutral), +1 (positive)')
    print('  "entities": list of key actors/countries/orgs mentioned')
    print('  "themes": list from your taxonomy')


if __name__ == "__main__":
    main()
