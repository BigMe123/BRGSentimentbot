"""
LLM-based event extractor using GPT-4o-mini.
Decomposes articles into structured actor-action-receiver events.
"""

import json
import asyncio
import logging
from typing import List, Dict, Any, Optional

from sentiment_bot.llm_client import LLMClient
from sentiment_bot.llm_cache import get_cache, set_cache
from sentiment_bot.utils.output_models import (
    ExtractedEvent, EventActor, EventAction, EventLocation,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a geopolitical event extractor. Given a news article, extract structured events.

Each event has:
- actor: {name, type} where type is one of: state, org, person, group, sector, public
- action: {verb, category} where category is one of: cooperate, confront, military, economic, diplomatic, regulatory, communicate
- receiver: {name, type} (optional, same types as actor)
- tone: integer -10 (hostile) to +10 (cooperative)
- domain: one of: military, economic, diplomatic, legal, social, tech
- intensity: integer 1 (routine) to 5 (crisis)
- stance: one of: support, oppose, neutral, threaten, request
- location: {name, coordinates} (optional, where the event happened, NOT where it was reported)
- event_date: ISO date string (when the event happened, NOT the publication date). null if unclear.
- confidence: float 0.0-1.0

Rules:
- Extract 0-5 events per article. Return [] for articles with no clear events.
- event_date is when the event HAPPENED, not when the article was published.
- location is where the event OCCURRED, not where it was reported from.
- Return ONLY a JSON array. No markdown, no explanation."""

TASK_PROMPT = """Extract structured events from this article:

"{DOC}"

Return a JSON array of events. If no clear events, return []."""

# Valid enum values for validation
VALID_ACTOR_TYPES = {"state", "org", "person", "group", "sector", "public"}
VALID_CATEGORIES = {"cooperate", "confront", "military", "economic", "diplomatic", "regulatory", "communicate"}
VALID_DOMAINS = {"military", "economic", "diplomatic", "legal", "social", "tech"}
VALID_STANCES = {"support", "oppose", "neutral", "threaten", "request"}
VALID_SOURCE_TYPES = {"news", "social_media", "official_statement"}

MIN_TEXT_LENGTH = 100
MAX_TEXT_LENGTH = 8000
MAX_EVENTS_PER_ARTICLE = 5


def _coerce_event_json(response_text: str) -> List[Dict[str, Any]]:
    """Extract a JSON array from LLM response text."""
    text = response_text.strip()

    # Try direct parse first
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return [result]
    except json.JSONDecodeError:
        pass

    # Find array boundaries
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    # Find single object
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(text[start:end + 1])
            return [obj]
        except json.JSONDecodeError:
            pass

    logger.warning("Could not parse event JSON from LLM response")
    return []


def _validate_events(raw_events: List[Dict[str, Any]]) -> List[ExtractedEvent]:
    """Validate and clamp raw event dicts into ExtractedEvent models."""
    events = []
    for raw in raw_events[:MAX_EVENTS_PER_ARTICLE]:
        try:
            # Actor (required)
            actor_raw = raw.get("actor", {})
            if not actor_raw or not actor_raw.get("name"):
                continue
            actor_type = actor_raw.get("type", "org")
            if actor_type not in VALID_ACTOR_TYPES:
                actor_type = "org"
            actor = EventActor(name=str(actor_raw["name"])[:100], type=actor_type)

            # Action (required)
            action_raw = raw.get("action", {})
            if not action_raw or not action_raw.get("verb"):
                continue
            category = action_raw.get("category", "communicate")
            if category not in VALID_CATEGORIES:
                category = "communicate"
            action = EventAction(verb=str(action_raw["verb"])[:100], category=category)

            # Receiver (optional)
            receiver = None
            recv_raw = raw.get("receiver")
            if recv_raw and recv_raw.get("name"):
                recv_type = recv_raw.get("type", "org")
                if recv_type not in VALID_ACTOR_TYPES:
                    recv_type = "org"
                receiver = EventActor(name=str(recv_raw["name"])[:100], type=recv_type)

            # Tone: clamp to [-10, 10]
            tone = int(raw.get("tone", 0))
            tone = max(-10, min(10, tone))

            # Domain
            domain = raw.get("domain", "economic")
            if domain not in VALID_DOMAINS:
                domain = "economic"

            # Intensity: clamp to [1, 5]
            intensity = int(raw.get("intensity", 1))
            intensity = max(1, min(5, intensity))

            # Stance
            stance = raw.get("stance", "neutral")
            if stance not in VALID_STANCES:
                stance = "neutral"

            # Location (optional)
            location = None
            loc_raw = raw.get("location")
            if loc_raw and loc_raw.get("name"):
                coords = loc_raw.get("coordinates")
                if coords and isinstance(coords, list) and len(coords) == 2:
                    try:
                        coords = [float(coords[0]), float(coords[1])]
                    except (ValueError, TypeError):
                        coords = None
                else:
                    coords = None
                location = EventLocation(name=str(loc_raw["name"])[:100], coordinates=coords)

            # Event date (optional)
            event_date = raw.get("event_date")
            if event_date and not isinstance(event_date, str):
                event_date = None

            # Source type
            source_type = raw.get("source_type", "news")
            if source_type not in VALID_SOURCE_TYPES:
                source_type = "news"

            # Confidence: clamp to [0, 1]
            confidence = float(raw.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))

            events.append(ExtractedEvent(
                actor=actor,
                action=action,
                receiver=receiver,
                tone=tone,
                domain=domain,
                intensity=intensity,
                stance=stance,
                location=location,
                event_date=event_date,
                source_type=source_type,
                confidence=confidence,
            ))
        except Exception as e:
            logger.debug(f"Skipping malformed event: {e}")
            continue

    return events


class EventExtractor:
    """LLM-based event extractor for geopolitical/economic articles."""

    def __init__(self, model_name: str = None):
        self.client = LLMClient()
        self.model_name = model_name or self.client.model
        self.system_prompt = SYSTEM_PROMPT
        self.task_prompt_template = TASK_PROMPT

        self.processed_count = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.total_events = 0

        logger.info(f"Initialized EventExtractor with model: {self.model_name}")

    async def extract_batch(self, docs: List[Dict[str, Any]]) -> Dict[str, List[ExtractedEvent]]:
        """
        Extract events from a batch of documents.

        Args:
            docs: List of {"id": str, "text": str} documents

        Returns:
            Dict mapping doc ID to list of ExtractedEvent
        """
        async def _extract_one(doc: Dict[str, Any]) -> tuple:
            doc_id = doc.get("id", "unknown")
            text = doc.get("text", "")

            if len(text) < MIN_TEXT_LENGTH:
                return doc_id, []

            text = text[:MAX_TEXT_LENGTH]
            prompt = self.task_prompt_template.replace("{DOC}", text)

            # Check cache
            cache_key = f"events:{prompt}"
            cached = get_cache(cache_key, self.model_name)
            if cached:
                self.cache_hits += 1
                events = [ExtractedEvent(**e) for e in cached]
                return doc_id, events

            # Call LLM
            self.cache_misses += 1
            try:
                response_text = await self.client.chat(self.system_prompt, prompt)
                raw_events = _coerce_event_json(response_text)
                events = _validate_events(raw_events)

                # Cache as dicts
                set_cache(cache_key, self.model_name, [e.model_dump() for e in events])
            except Exception as e:
                logger.error(f"Event extraction failed for {doc_id}: {e}")
                events = []

            return doc_id, events

        results_list = await asyncio.gather(*[_extract_one(doc) for doc in docs])
        results = {}
        for doc_id, events in results_list:
            results[doc_id] = events
            self.total_events += len(events)

        self.processed_count += len(docs)
        logger.info(
            f"Extracted {self.total_events} events from {len(docs)} docs. "
            f"Cache: {self.cache_hits} hits, {self.cache_misses} misses"
        )
        return results

    async def extract_single(self, text: str, doc_id: str = "single") -> List[ExtractedEvent]:
        """Extract events from a single document."""
        results = await self.extract_batch([{"id": doc_id, "text": text}])
        return results.get(doc_id, [])

    def get_stats(self) -> Dict[str, Any]:
        return {
            "processed_documents": self.processed_count,
            "total_events_extracted": self.total_events,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_hit_rate": self.cache_hits / max(self.cache_hits + self.cache_misses, 1),
        }
