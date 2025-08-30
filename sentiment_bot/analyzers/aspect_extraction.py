"""Extract aspects (entities, topics) from text for targeted sentiment."""

import spacy
from typing import List, Dict, Set
from collections import Counter
import logging

logger = logging.getLogger(__name__)


class AspectExtractor:
    """Extract entities and noun phrases as aspects for sentiment analysis."""

    def __init__(self, model: str = "en_core_web_sm", max_aspects: int = 8):
        """Initialize with spaCy model."""
        self.max_aspects = max_aspects
        self._nlp = None
        self.model_name = model

        # Common stopwords to filter
        self.aspect_stopwords = {
            "article",
            "report",
            "news",
            "story",
            "coverage",
            "statement",
            "announcement",
            "update",
            "development",
        }

    def _get_nlp(self):
        """Lazy load spaCy model."""
        if self._nlp is None:
            try:
                self._nlp = spacy.load(self.model_name)
            except:
                # Try to download if not present
                import subprocess

                subprocess.run(["python", "-m", "spacy", "download", self.model_name])
                self._nlp = spacy.load(self.model_name)
        return self._nlp

    def extract_aspects(self, text: str, context: Dict = None) -> List[Dict]:
        """Extract aspects from text.

        Args:
            text: Input text
            context: Optional context with region/topic hints

        Returns:
            List of aspects with metadata
        """
        nlp = self._get_nlp()
        doc = nlp(text[:5000])  # Limit text length for performance

        aspects = []
        seen = set()

        # 1. Extract named entities
        entity_counts = Counter()
        for ent in doc.ents:
            if ent.label_ in ["PERSON", "ORG", "GPE", "LOC", "NORP"]:
                # GPE = countries/cities, NORP = nationalities/groups
                normalized = ent.text.lower().strip()
                if normalized not in self.aspect_stopwords and len(normalized) > 2:
                    entity_counts[ent.text] += 1

                    if ent.text not in seen:
                        aspects.append(
                            {
                                "text": ent.text,
                                "type": "entity",
                                "label": ent.label_,
                                "count": 1,
                                "importance": 0.0,  # Will calculate later
                            }
                        )
                        seen.add(ent.text)

        # 2. Extract important noun chunks
        chunk_counts = Counter()
        for chunk in doc.noun_chunks:
            # Filter out generic chunks
            if len(chunk.text.split()) <= 3:  # Max 3 words
                normalized = chunk.text.lower().strip()
                if (
                    normalized not in self.aspect_stopwords
                    and normalized not in seen
                    and len(normalized) > 3
                ):

                    # Check if it's meaningful (has proper noun or is frequent)
                    has_proper = any(token.pos_ == "PROPN" for token in chunk)
                    if has_proper or chunk_counts[chunk.text] > 1:
                        chunk_counts[chunk.text] += 1

                        if chunk.text not in seen:
                            aspects.append(
                                {
                                    "text": chunk.text,
                                    "type": "noun_phrase",
                                    "label": "NP",
                                    "count": 1,
                                    "importance": 0.0,
                                }
                            )
                            seen.add(chunk.text)

        # 3. Update counts
        for aspect in aspects:
            if aspect["type"] == "entity":
                aspect["count"] = entity_counts.get(aspect["text"], 1)
            elif aspect["type"] == "noun_phrase":
                aspect["count"] = chunk_counts.get(aspect["text"], 1)

        # 4. Calculate importance scores
        aspects = self._calculate_importance(aspects, context)

        # 5. Sort by importance and limit
        aspects.sort(key=lambda x: x["importance"], reverse=True)

        return aspects[: self.max_aspects]

    def _calculate_importance(
        self, aspects: List[Dict], context: Dict = None
    ) -> List[Dict]:
        """Calculate importance score for each aspect."""

        # Get max count for normalization
        max_count = max([a["count"] for a in aspects], default=1)

        for aspect in aspects:
            # Base importance on frequency
            freq_score = aspect["count"] / max_count

            # Boost entities over noun phrases
            type_boost = 1.2 if aspect["type"] == "entity" else 1.0

            # Boost based on entity type
            label_boost = 1.0
            if aspect["label"] == "PERSON":
                label_boost = 1.3
            elif aspect["label"] == "ORG":
                label_boost = 1.2
            elif aspect["label"] == "GPE":
                label_boost = 1.1

            # Context boost (if aspect matches region/topic keywords)
            context_boost = 1.0
            if context:
                aspect_lower = aspect["text"].lower()
                if context.get("region") and context["region"].lower() in aspect_lower:
                    context_boost = 1.5
                if context.get("topic") and context["topic"].lower() in aspect_lower:
                    context_boost = 1.4

            # Calculate final importance
            aspect["importance"] = freq_score * type_boost * label_boost * context_boost

        return aspects

    def merge_similar_aspects(self, aspects: List[Dict]) -> List[Dict]:
        """Merge similar aspects (e.g., 'Biden' and 'President Biden')."""
        merged = []
        seen_texts = set()

        for aspect in aspects:
            # Check if this aspect is substring of existing
            merged_with_existing = False
            aspect_lower = aspect["text"].lower()

            for existing in merged:
                existing_lower = existing["text"].lower()

                # Check substring relationship
                if aspect_lower in existing_lower or existing_lower in aspect_lower:
                    # Merge into the longer one
                    if len(aspect["text"]) > len(existing["text"]):
                        existing["text"] = aspect["text"]
                    existing["count"] += aspect["count"]
                    existing["importance"] = max(
                        existing["importance"], aspect["importance"]
                    )
                    merged_with_existing = True
                    break

            if not merged_with_existing:
                merged.append(aspect.copy())

        return merged
