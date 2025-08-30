"""
LLM-based sentiment analyzer using OpenAI GPT-4.1-mini for finance-grade analysis.
Returns structured JSON with sentiment, entities, and financial signals.
"""

import json
import os
import asyncio
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

from sentiment_bot.llm_client import LLMClient
from sentiment_bot.llm_cache import get_cache, set_cache

logger = logging.getLogger(__name__)


def coerce_json(response_text: str) -> Dict[str, Any]:
    """
    Extract and validate JSON from LLM response.
    Handles cases where LLM includes extra text around the JSON.
    """
    # Default fallback response
    fallback = {
        "summary": "n/a",
        "sentiment": "neutral",
        "confidence": 0.0,
        "rationale": "parser_fail",
        "entities": [],
        "signals": {
            "earnings_guidance": "n/a",
            "policy_risk": "low",
            "market_impact_hours": "6-24",
        },
        "trading_recommendation": {
            "action": "hold",
            "timeframe": "long-term",
            "risk_level": "low",
            "target_sectors": [],
        },
        "market_implications": {
            "broad_market": "neutral",
            "affected_sectors": [],
            "contrarian_plays": [],
        },
    }

    try:
        # Find JSON boundaries
        start = response_text.find("{")
        end = response_text.rfind("}") + 1

        if start == -1 or end == 0:
            logger.warning("No JSON found in LLM response")
            return fallback

        json_str = response_text[start:end]
        result = json.loads(json_str)

        # Validate required fields and types
        validated = validate_response_schema(result)
        return validated

    except json.JSONDecodeError as e:
        logger.debug(f"JSON parsing failed: {e}")
        # Try extracting key fields if full JSON parsing fails
        try:
            import re
            summary_match = re.search(r'"summary":\s*"([^"]+)"', response_text)
            sentiment_match = re.search(r'"sentiment":\s*"(positive|negative|neutral)"', response_text)
            confidence_match = re.search(r'"confidence":\s*([0-9.]+)', response_text)
            
            if summary_match and sentiment_match:
                partial_result = fallback.copy()
                partial_result.update({
                    "summary": summary_match.group(1)[:200],
                    "sentiment": sentiment_match.group(1),
                    "confidence": float(confidence_match.group(1)) if confidence_match else 0.5,
                    "rationale": "partial_parse"
                })
                return partial_result
        except:
            pass
        return fallback
    except Exception as e:
        logger.warning(f"Response validation failed: {e}")
        return fallback


def validate_response_schema(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and clean LLM response to match expected schema."""

    # Ensure all required fields exist with proper types
    validated = {
        "summary": str(data.get("summary", "n/a"))[:200],  # Truncate if too long
        "sentiment": data.get("sentiment", "neutral"),
        "confidence": float(data.get("confidence", 0.0)),
        "rationale": str(data.get("rationale", "n/a"))[
            :100
        ],  # Increased for more detailed rationale
        "entities": data.get("entities", []),
        "signals": data.get("signals", {}),
        "trading_recommendation": data.get("trading_recommendation", {}),
        "market_implications": data.get("market_implications", {}),
    }

    # Validate sentiment value
    if validated["sentiment"] not in ["positive", "neutral", "negative"]:
        logger.warning(
            f"Invalid sentiment: {validated['sentiment']}, defaulting to neutral"
        )
        validated["sentiment"] = "neutral"

    # Clamp confidence to 0-1 range
    validated["confidence"] = max(0.0, min(1.0, validated["confidence"]))

    # Validate entities structure
    clean_entities = []
    for entity in validated["entities"]:
        if isinstance(entity, dict) and "name" in entity:
            clean_entity = {
                "name": str(entity.get("name", ""))[:50],
                "type": entity.get("type", "ORG"),
                "sentiment": entity.get("sentiment", "neutral"),
            }
            # Validate entity sentiment
            if clean_entity["sentiment"] not in ["positive", "neutral", "negative"]:
                clean_entity["sentiment"] = "neutral"
            clean_entities.append(clean_entity)

    validated["entities"] = clean_entities[:10]  # Limit to 10 entities

    # Validate signals structure
    signals = validated["signals"]
    validated["signals"] = {
        "earnings_guidance": signals.get("earnings_guidance", "n/a"),
        "policy_risk": signals.get("policy_risk", "low"),
        "market_impact_hours": signals.get("market_impact_hours", "6-24"),
    }

    # Validate signal values
    if validated["signals"]["earnings_guidance"] not in ["up", "flat", "down", "n/a"]:
        validated["signals"]["earnings_guidance"] = "n/a"

    if validated["signals"]["policy_risk"] not in ["low", "med", "high"]:
        validated["signals"]["policy_risk"] = "low"

    if validated["signals"]["market_impact_hours"] not in ["0-6", "6-24", "24+"]:
        validated["signals"]["market_impact_hours"] = "6-24"

    # Validate trading recommendation
    trading_rec = validated["trading_recommendation"]
    validated["trading_recommendation"] = {
        "action": trading_rec.get("action", "hold"),
        "timeframe": trading_rec.get("timeframe", "long-term"),
        "risk_level": trading_rec.get("risk_level", "low"),
        "target_sectors": trading_rec.get("target_sectors", []),
    }

    # Validate action
    if validated["trading_recommendation"]["action"] not in [
        "buy",
        "sell",
        "hold",
        "hedge",
    ]:
        validated["trading_recommendation"]["action"] = "hold"

    # Validate timeframe
    if validated["trading_recommendation"]["timeframe"] not in [
        "intraday",
        "1-3days",
        "1-2weeks",
        "long-term",
    ]:
        validated["trading_recommendation"]["timeframe"] = "long-term"

    # Validate risk level
    if validated["trading_recommendation"]["risk_level"] not in [
        "low",
        "medium",
        "high",
    ]:
        validated["trading_recommendation"]["risk_level"] = "low"

    # Ensure target_sectors is a list
    if not isinstance(validated["trading_recommendation"]["target_sectors"], list):
        validated["trading_recommendation"]["target_sectors"] = []

    # Validate market implications
    market_impl = validated["market_implications"]
    validated["market_implications"] = {
        "broad_market": market_impl.get("broad_market", "neutral"),
        "affected_sectors": market_impl.get("affected_sectors", []),
        "contrarian_plays": market_impl.get("contrarian_plays", []),
    }

    # Validate broad_market
    if validated["market_implications"]["broad_market"] not in [
        "bullish",
        "bearish",
        "neutral",
    ]:
        validated["market_implications"]["broad_market"] = "neutral"

    # Ensure affected_sectors and contrarian_plays are lists
    if not isinstance(validated["market_implications"]["affected_sectors"], list):
        validated["market_implications"]["affected_sectors"] = []
    if not isinstance(validated["market_implications"]["contrarian_plays"], list):
        validated["market_implications"]["contrarian_plays"] = []

    return validated


class LLMAnalyzer:
    """LLM-based analyzer for financial sentiment analysis."""

    def __init__(
        self,
        system_prompt: str = None,
        task_prompt_template: str = None,
        model_name: str = None,
    ):
        self.client = LLMClient()
        self.model_name = model_name or self.client.model

        # Load prompts
        if system_prompt:
            self.system_prompt = system_prompt
        else:
            prompt_path = (
                Path(__file__).parent.parent.parent / "prompts" / "system_prompt.txt"
            )
            self.system_prompt = (
                prompt_path.read_text()
                if prompt_path.exists()
                else self._default_system_prompt()
            )

        if task_prompt_template:
            self.task_prompt_template = task_prompt_template
        else:
            prompt_path = (
                Path(__file__).parent.parent.parent / "prompts" / "task_prompt.txt"
            )
            self.task_prompt_template = (
                prompt_path.read_text()
                if prompt_path.exists()
                else self._default_task_prompt()
            )

        # Statistics
        self.processed_count = 0
        self.cache_hits = 0
        self.cache_misses = 0

        logger.info(f"Initialized LLM analyzer with model: {self.model_name}")

    def _default_system_prompt(self) -> str:
        """Fallback system prompt if file not found."""
        return """You are a finance-grade sentiment and risk analyzer. Be concise, factual, and avoid hallucinations.
If information is insufficient, set fields to "n/a". Follow the JSON schema exactly."""

    def _default_task_prompt(self) -> str:
        """Fallback task prompt if file not found."""
        return """Analyze the following document for INVESTOR-RELEVANT sentiment and risk.

Return a SINGLE JSON object with these keys:
summary, sentiment (positive|neutral|negative), confidence (0–1),
rationale (≤30 words), entities (list of {name,type,sentiment}),
signals ({earnings_guidance, policy_risk, market_impact_hours}).

Document:
"{DOC}" """

    async def analyze_batch(self, docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Analyze a batch of documents.

        Args:
            docs: List of {"id": str, "text": str} documents

        Returns:
            List of analysis results with schema validation
        """

        async def _analyze_one(doc: Dict[str, Any]) -> Dict[str, Any]:
            doc_id = doc.get("id", "unknown")
            text = doc.get("text", "")

            # Truncate text to ~2000 tokens (~8000 chars for better rate limiting)
            text = text[:8000]

            # Build prompt
            prompt = self.task_prompt_template.replace("{DOC}", text)

            # Check cache first
            cached_result = get_cache(prompt, self.model_name)
            if cached_result:
                self.cache_hits += 1
                result = cached_result.copy()
                result["id"] = doc_id  # Always update ID
                return result

            # Make API call
            self.cache_misses += 1
            try:
                response_text = await self.client.chat(self.system_prompt, prompt)
                result = coerce_json(response_text)

                # Cache the result (without doc ID)
                cache_result = result.copy()
                cache_result.pop("id", None)  # Don't cache the ID
                set_cache(prompt, self.model_name, cache_result)

            except Exception as e:
                logger.error(f"LLM analysis failed for doc {doc_id}: {e}")
                result = coerce_json("")  # Returns fallback

            result["id"] = doc_id
            return result

        # Process all documents concurrently
        results = await asyncio.gather(*[_analyze_one(doc) for doc in docs])
        self.processed_count += len(results)

        logger.info(
            f"Processed {len(results)} documents. Cache: {self.cache_hits} hits, {self.cache_misses} misses"
        )
        return results

    async def analyze_single(self, text: str, doc_id: str = "single") -> Dict[str, Any]:
        """Analyze a single document."""
        results = await self.analyze_batch([{"id": doc_id, "text": text}])
        return results[0]

    def get_stats(self) -> Dict[str, Any]:
        """Get analyzer statistics."""
        client_stats = self.client.get_stats()
        return {
            **client_stats,
            "processed_documents": self.processed_count,
            "cache_hit_rate": self.cache_hits
            / max(self.cache_hits + self.cache_misses, 1),
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
        }
