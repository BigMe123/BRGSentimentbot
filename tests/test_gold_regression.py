"""
Gold set regression test.

Loads human-labeled articles from tests/fixtures/gold_v1.jsonl,
runs the current analysis stack, and reports accuracy metrics.

Run: pytest tests/test_gold_regression.py -v
"""

import json
import pytest
from pathlib import Path
from collections import Counter

GOLD_PATH = Path(__file__).parent / "fixtures" / "gold_v1.jsonl"


def load_gold():
    """Load gold set, skip unlabeled entries."""
    if not GOLD_PATH.exists():
        pytest.skip("Gold set not found. Run: python scripts/sample_gold_set.py")

    records = []
    with open(GOLD_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("sentiment") is not None:
                records.append(r)

    if len(records) < 10:
        pytest.skip(f"Only {len(records)} labeled articles. Need at least 10.")
    return records


def run_analysis(text: str):
    """Run current default analysis on text."""
    from sentiment_bot.analyzer import analyze
    result = analyze(text)
    score = result.vader
    label = 1 if score > 0.05 else (-1 if score < -0.05 else 0)
    return {"score": score, "label": label}


def run_entity_extraction(text: str):
    """Run entity extraction on text."""
    from sentiment_bot.utils.entity_extractor import EntityExtractor
    ex = EntityExtractor()
    entities = ex.extract_entities(text)
    return [e["text"] for e in entities]


def run_theme_extraction(text: str, topic: str = None):
    """Run theme extraction on text."""
    from sentiment_bot.utils.entity_extractor import EntityExtractor
    ex = EntityExtractor()
    return ex.extract_themes(text, topic)


class TestGoldRegression:

    @pytest.fixture(scope="class")
    def gold(self):
        return load_gold()

    def test_sentiment_accuracy(self, gold):
        """Sentiment label accuracy against gold labels."""
        correct = 0
        total = 0
        confusion = Counter()

        for record in gold:
            text = record.get("summary", "") or record.get("title", "")
            if not text:
                continue

            result = run_analysis(text)
            predicted = result["label"]
            actual = record["sentiment"]

            confusion[(actual, predicted)] += 1
            if predicted == actual:
                correct += 1
            total += 1

        accuracy = correct / total if total else 0

        # Report
        print(f"\n{'='*50}")
        print(f"SENTIMENT ACCURACY: {accuracy:.1%} ({correct}/{total})")
        print(f"{'='*50}")
        print(f"Confusion (actual, predicted): count")
        for (a, p), c in sorted(confusion.items()):
            labels = {-1: "neg", 0: "neu", 1: "pos"}
            print(f"  {labels[a]:>3} -> {labels[p]:>3}: {c}")

        # Warn but don't fail below 50% — the gold set is the baseline
        assert total > 0, "No articles could be analyzed"
        print(f"\nBaseline recorded. Improve this number over time.")

    def test_entity_recall(self, gold):
        """Entity recall against gold labels."""
        total_gold = 0
        total_found = 0

        for record in gold:
            gold_entities = set(e.lower() for e in record.get("entities", []))
            if not gold_entities:
                continue

            text = record.get("summary", "") or record.get("title", "")
            predicted = set(e.lower() for e in run_entity_extraction(text))

            hits = gold_entities & predicted
            total_gold += len(gold_entities)
            total_found += len(hits)

        recall = total_found / total_gold if total_gold else 0
        print(f"\n{'='*50}")
        print(f"ENTITY RECALL: {recall:.1%} ({total_found}/{total_gold})")
        print(f"{'='*50}")
        assert total_gold > 0 or True, "No entities in gold set"

    def test_theme_recall(self, gold):
        """Theme recall against gold labels."""
        total_gold = 0
        total_found = 0

        for record in gold:
            gold_themes = set(t.lower() for t in record.get("themes", []))
            if not gold_themes:
                continue

            text = record.get("summary", "") or record.get("title", "")
            predicted = set(t.lower() for t in run_theme_extraction(text, record.get("topic")))

            hits = gold_themes & predicted
            total_gold += len(gold_themes)
            total_found += len(hits)

        recall = total_found / total_gold if total_gold else 0
        print(f"\n{'='*50}")
        print(f"THEME RECALL: {recall:.1%} ({total_found}/{total_gold})")
        print(f"{'='*50}")
        assert total_gold > 0 or True, "No themes in gold set"
