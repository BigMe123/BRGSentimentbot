"""
LLM-as-judge: quality assessment of sentiment analysis.

Samples articles from a scan and asks an LLM to evaluate whether the
assigned sentiment, themes, and entity extractions are correct.
Reports accuracy, common failure modes, and suggestions.
"""

import json
import logging
import random
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

JUDGE_PROMPT = """You are a quality evaluator for a news sentiment analysis system.

For each article below, assess whether the system's analysis is correct.

For each article, output a JSON object with:
- "article_id": the article ID
- "sentiment_correct": true/false — is the sentiment label (pos/neg/neu) and score reasonable?
- "themes_correct": true/false — are the extracted themes relevant?
- "entities_correct": true/false — are the key entities captured?
- "issues": string — describe any problems, or "none"
- "suggested_label": "pos", "neg", or "neu" — what you think the correct label is
- "confidence": 0.0 to 1.0 — your confidence in your assessment

Return a JSON array of these objects. Return ONLY valid JSON, no markdown."""


class LLMJudge:
    """
    Use an LLM to evaluate analysis quality.

    Samples N articles, sends them to the LLM with their analysis results,
    and collects quality assessments.
    """

    def __init__(self, sample_size: int = 20):
        self.sample_size = sample_size
        self._client = None

    def _get_client(self):
        if self._client is None:
            from ..llm_client import LLMClient
            self._client = LLMClient()
        return self._client

    def evaluate(self, article_records, sample_size: int = None) -> Dict:
        """
        Evaluate a set of article records.

        Args:
            article_records: List of ArticleRecord objects
            sample_size: Override default sample size

        Returns:
            {accuracy, sentiment_accuracy, theme_accuracy, entity_accuracy,
             issues, suggestions, sample_size, judgments}
        """
        n = sample_size or self.sample_size
        sample = self._stratified_sample(article_records, n)

        if not sample:
            return {"error": "No articles to evaluate"}

        # Build prompt
        articles_text = self._format_articles(sample)
        prompt = f"{JUDGE_PROMPT}\n\n{articles_text}"

        # Call LLM
        try:
            client = self._get_client()
            import asyncio
            response = asyncio.get_event_loop().run_until_complete(
                client.chat(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                )
            )
        except RuntimeError:
            # No event loop running
            import asyncio
            loop = asyncio.new_event_loop()
            try:
                client = self._get_client()
                response = loop.run_until_complete(
                    client.chat(
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.1,
                    )
                )
            finally:
                loop.close()

        # Parse response
        judgments = self._parse_response(response)
        return self._aggregate(judgments, len(sample))

    def _stratified_sample(self, records, n: int) -> list:
        """Sample N articles, stratified by sentiment label."""
        by_label = {"pos": [], "neg": [], "neu": []}
        for r in records:
            by_label.setdefault(r.sentiment.label, []).append(r)

        per_label = max(1, n // 3)
        sample = []
        for label, recs in by_label.items():
            sample.extend(random.sample(recs, min(per_label, len(recs))))

        # Fill remaining from all records
        remaining = n - len(sample)
        if remaining > 0:
            pool = [r for r in records if r not in sample]
            sample.extend(random.sample(pool, min(remaining, len(pool))))

        return sample[:n]

    def _format_articles(self, records) -> str:
        """Format articles for the judge prompt."""
        parts = []
        for r in records:
            themes = r.signals.themes if r.signals else []
            entities = [e["text"] for e in r.entities[:5]]
            parts.append(
                f"Article ID: {r.id}\n"
                f"Title: {r.title}\n"
                f"Summary: {r.ai_summary or r.summary or '(none)'}\n"
                f"System sentiment: {r.sentiment.label} ({r.sentiment.score:+.3f})\n"
                f"System themes: {', '.join(themes) if themes else '(none)'}\n"
                f"System entities: {', '.join(entities) if entities else '(none)'}\n"
            )
        return "\n---\n".join(parts)

    def _parse_response(self, response: str) -> List[Dict]:
        """Parse LLM judge response."""
        text = response.strip()
        # Find JSON array
        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

        # Try single object
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                obj = json.loads(text[start:end])
                return [obj]
            except json.JSONDecodeError:
                pass

        logger.warning("Could not parse LLM judge response")
        return []

    def _aggregate(self, judgments: List[Dict], sample_size: int) -> Dict:
        """Aggregate judge results into a quality report."""
        if not judgments:
            return {"error": "No judgments parsed", "sample_size": sample_size}

        sent_correct = sum(1 for j in judgments if j.get("sentiment_correct", False))
        theme_correct = sum(1 for j in judgments if j.get("themes_correct", False))
        entity_correct = sum(1 for j in judgments if j.get("entities_correct", False))
        n = len(judgments)

        issues = [j["issues"] for j in judgments if j.get("issues", "none") != "none"]

        return {
            "sample_size": sample_size,
            "judged": n,
            "sentiment_accuracy": round(sent_correct / n, 3) if n else 0,
            "theme_accuracy": round(theme_correct / n, 3) if n else 0,
            "entity_accuracy": round(entity_correct / n, 3) if n else 0,
            "overall_accuracy": round((sent_correct + theme_correct + entity_correct) / (3 * n), 3) if n else 0,
            "issues": issues[:10],
            "judgments": judgments,
        }
