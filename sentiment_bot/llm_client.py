"""
LLM Client adapter supporting OpenAI, Anthropic, and OpenAI-compatible endpoints.
Handles async requests, retries, rate limiting, and different API formats.
"""

import os
import asyncio
import json
import time
import hashlib
import logging
from typing import Dict, Any, List, Optional
import aiohttp
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class LLMClient:
    """Async LLM client with retry logic and rate limiting."""

    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "openai")
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.temp = float(os.getenv("LLM_TEMPERATURE", "0"))
        self.max_tokens = int(os.getenv("LLM_MAX_TOKENS", "600"))
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
        self.sem = asyncio.Semaphore(int(os.getenv("LLM_CONCURRENCY", "4")))
        self.rate_delay = int(os.getenv("LLM_RATE_DELAY", "20"))
        self.headers = self._headers()

        # Request tracking for debugging
        self.total_requests = 0
        self.failed_requests = 0

        logger.info(f"Initialized LLM client: {self.provider}/{self.model}")

    def _headers(self) -> Dict[str, str]:
        """Build headers based on provider."""
        if self.provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY not set in environment")
            return {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

        if self.provider == "anthropic":
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY not set in environment")
            return {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }

        # http: OpenAI-compatible (vLLM, etc.)
        return {"Content-Type": "application/json"}

    def _sleep_hint_from_headers(self, headers) -> float:
        """Extract sleep time from Retry-After header or use default."""
        retry_after = headers.get("retry-after")
        if retry_after:
            try:
                return float(retry_after)
            except (ValueError, TypeError):
                pass
        return 2.0  # Default backoff

    async def _post(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Make HTTP POST request with improved rate limiting and retry logic."""
        async with self.sem:
            self.total_requests += 1
            backoff = 1.0

            for attempt in range(6):  # Increased max attempts
                try:
                    timeout = aiohttp.ClientTimeout(total=120)
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        async with session.post(
                            url, headers=self.headers, json=payload
                        ) as response:

                            # Handle rate limits and server errors
                            if response.status in (429, 500, 502, 503, 504):
                                body = await response.text()

                                # Check for quota issues
                                if (
                                    "insufficient_quota" in body
                                    or "exceeded your current quota" in body
                                ):
                                    self.failed_requests += 1
                                    raise RuntimeError(
                                        "OpenAI: insufficient_quota (budget cap hit)"
                                    )

                                # Use Retry-After header if available, otherwise exponential backoff
                                if response.status == 429:
                                    sleep_time = self._sleep_hint_from_headers(
                                        response.headers
                                    )
                                else:
                                    sleep_time = backoff

                                logger.warning(
                                    f"HTTP {response.status}, retrying in {sleep_time}s (attempt {attempt+1}/6)"
                                )
                                await asyncio.sleep(sleep_time)
                                backoff = min(backoff * 2, 20)  # Cap at 20 seconds
                                continue

                            response.raise_for_status()
                            return await response.json()

                except asyncio.TimeoutError:
                    wait_time = min(2**attempt, 30)
                    logger.warning(
                        f"Request timeout, retrying in {wait_time}s (attempt {attempt+1}/6)"
                    )
                    await asyncio.sleep(wait_time)
                except aiohttp.ClientError as e:
                    wait_time = min(2**attempt, 30)
                    logger.warning(
                        f"Client error: {e}, retrying in {wait_time}s (attempt {attempt+1}/6)"
                    )
                    await asyncio.sleep(wait_time)
                except Exception as e:
                    wait_time = min(2**attempt, 30)
                    logger.warning(
                        f"Request failed: {e}, retrying in {wait_time}s (attempt {attempt+1}/6)"
                    )
                    await asyncio.sleep(wait_time)

            self.failed_requests += 1
            raise RuntimeError(f"LLM request failed after 6 retries to {url}")

    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        """Send chat completion request and return response text."""
        if self.provider == "openai" or self.provider == "http":
            url = f"{self.base_url}/chat/completions"
            payload = {
                "model": self.model,
                "temperature": self.temp,
                "max_tokens": self.max_tokens,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }

            try:
                data = await self._post(url, payload)
                return data["choices"][0]["message"]["content"].strip()
            except KeyError as e:
                logger.error(f"Unexpected OpenAI response format: {data}")
                raise RuntimeError(f"Invalid API response: missing {e}")

        if self.provider == "anthropic":
            url = "https://api.anthropic.com/v1/messages"
            payload = {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "temperature": self.temp,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            }

            try:
                data = await self._post(url, payload)
                # Anthropic returns list of content blocks
                return "".join(
                    block.get("text", "") for block in data["content"]
                ).strip()
            except KeyError as e:
                logger.error(f"Unexpected Anthropic response format: {data}")
                raise RuntimeError(f"Invalid API response: missing {e}")

        raise ValueError(f"Unknown LLM_PROVIDER={self.provider}")

    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics."""
        return {
            "provider": self.provider,
            "model": self.model,
            "total_requests": self.total_requests,
            "failed_requests": self.failed_requests,
            "success_rate": (self.total_requests - self.failed_requests)
            / max(self.total_requests, 1),
            "concurrency_limit": self.sem._value,
        }
