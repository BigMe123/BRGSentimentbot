"""Analyze sentiment toward specific aspects using NLI."""

from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class AspectSentimentAnalyzer:
    """Analyze sentiment toward specific aspects in text."""

    def __init__(self):
        """Initialize analyzer."""
        self._nli_pipeline = None

    def _get_nli_pipeline(self):
        """Lazy load NLI pipeline."""
        if self._nli_pipeline is None:
            from ..models import get_nli_pipeline

            self._nli_pipeline = get_nli_pipeline()
        return self._nli_pipeline

    def score_aspects(self, text: str, aspects: List[Dict]) -> List[Dict]:
        """Score sentiment toward each aspect.

        Args:
            text: Full article text
            aspects: List of aspects from AspectExtractor

        Returns:
            Aspects with sentiment scores added
        """
        nli = self._get_nli_pipeline()

        # Limit text for performance
        context_text = text[:2000]

        scored_aspects = []

        for aspect in aspects:
            aspect_text = aspect["text"]

            # Create hypothesis templates
            hypotheses = [
                f"The tone toward {aspect_text} is positive",
                f"The tone toward {aspect_text} is negative",
                f"The tone toward {aspect_text} is neutral",
            ]

            try:
                # Run NLI
                result = nli(
                    context_text, candidate_labels=hypotheses, multi_label=False
                )

                # Parse results
                scores = {}
                for label, score in zip(result["labels"], result["scores"]):
                    if "positive" in label:
                        scores["positive"] = score
                    elif "negative" in label:
                        scores["negative"] = score
                    elif "neutral" in label:
                        scores["neutral"] = score

                # Calculate sentiment score
                sentiment_score = scores.get("positive", 0) - scores.get("negative", 0)

                # Determine label
                if sentiment_score > 0.2:
                    sentiment_label = "positive"
                elif sentiment_score < -0.2:
                    sentiment_label = "negative"
                else:
                    sentiment_label = "neutral"

                # Add sentiment to aspect
                aspect_with_sentiment = aspect.copy()
                aspect_with_sentiment.update(
                    {
                        "sentiment_score": sentiment_score,
                        "sentiment_label": sentiment_label,
                        "sentiment_confidence": max(result["scores"]),
                    }
                )

                scored_aspects.append(aspect_with_sentiment)

            except Exception as e:
                logger.warning(f"Failed to score aspect '{aspect_text}': {e}")
                # Add neutral sentiment as fallback
                aspect_with_sentiment = aspect.copy()
                aspect_with_sentiment.update(
                    {
                        "sentiment_score": 0.0,
                        "sentiment_label": "neutral",
                        "sentiment_confidence": 0.0,
                    }
                )
                scored_aspects.append(aspect_with_sentiment)

        return scored_aspects

    def aggregate_aspect_sentiments(self, scored_aspects: List[Dict]) -> Dict:
        """Aggregate aspect sentiments into summary."""

        if not scored_aspects:
            return {
                "overall_score": 0.0,
                "dominant_sentiment": "neutral",
                "aspect_summary": {},
            }

        # Calculate weighted average (by importance)
        total_weighted_score = 0.0
        total_weight = 0.0

        # Group by sentiment
        sentiment_groups = {"positive": [], "negative": [], "neutral": []}

        for aspect in scored_aspects:
            weight = aspect.get("importance", 1.0)
            total_weighted_score += aspect["sentiment_score"] * weight
            total_weight += weight

            sentiment_groups[aspect["sentiment_label"]].append(aspect["text"])

        overall_score = total_weighted_score / total_weight if total_weight > 0 else 0.0

        # Determine dominant sentiment
        if overall_score > 0.1:
            dominant = "positive"
        elif overall_score < -0.1:
            dominant = "negative"
        else:
            dominant = "neutral"

        return {
            "overall_score": overall_score,
            "dominant_sentiment": dominant,
            "aspect_summary": {
                "positive_aspects": sentiment_groups["positive"],
                "negative_aspects": sentiment_groups["negative"],
                "neutral_aspects": sentiment_groups["neutral"],
            },
            "detailed_aspects": scored_aspects,
        }
