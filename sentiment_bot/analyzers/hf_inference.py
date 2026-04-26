"""
Remote inference via Hugging Face Inference API.

Replaces slow local MPS inference with free remote GPU compute.
Uses raw HTTP calls for reliability (the huggingface_hub client
has parsing bugs with zero-shot responses).

Set HF_TOKEN in .env (free at huggingface.co/settings/tokens).
"""

import os
import logging
import requests

# Ensure .env is loaded
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

API_BASE = "https://router.huggingface.co/hf-inference/models"


def _headers() -> Dict[str, str]:
    token = os.environ.get("HF_TOKEN", "")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def _post(model: str, payload: dict, timeout: int = 30) -> list | dict | None:
    """POST to HF Inference API, return parsed JSON."""
    url = f"{API_BASE}/{model}"
    try:
        headers = _headers()
        r = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if r.status_code in (401, 403) and headers:
            # A stale/invalid HF_TOKEN should not poison public-model calls.
            r = requests.post(url, headers={}, json=payload, timeout=timeout)
        if r.status_code == 503:
            # Model loading, retry once after wait
            import time
            wait = min(r.json().get("estimated_time", 20), 30)
            logger.info(f"Model {model} loading, waiting {wait}s...")
            time.sleep(wait)
            r = requests.post(url, headers=headers, json=payload, timeout=60)
            if r.status_code in (401, 403) and headers:
                r = requests.post(url, headers={}, json=payload, timeout=60)
        if r.status_code != 200:
            logger.debug(f"HF API {r.status_code}: {r.text[:200]}")
            return None
        return r.json()
    except Exception as e:
        logger.debug(f"HF API error: {e}")
        return None


def classify_zero_shot(
    text: str,
    labels: List[str],
    multi_label: bool = True,
    model: str = "facebook/bart-large-mnli",
) -> Dict[str, float]:
    """Zero-shot classification. Returns {label: score}."""
    result = _post(model, {
        "inputs": text[:2000],
        "parameters": {"candidate_labels": labels, "multi_label": multi_label},
    })
    if not result:
        return {}
    # Response is [{label, score}, ...]
    if isinstance(result, list):
        return {item["label"]: item["score"] for item in result}
    # Or {labels: [...], scores: [...]}
    if isinstance(result, dict) and "labels" in result:
        return dict(zip(result["labels"], result["scores"]))
    return {}


def sentiment_analysis(
    text: str,
    model: str = "cardiffnlp/twitter-roberta-base-sentiment-latest",
) -> Dict:
    """Sentiment analysis. Returns {label, score, confidence, probs}."""
    result = _post(model, {"inputs": text[:1500]})
    if not result:
        return {"label": "neutral", "score": 0.0, "confidence": 0.0, "probs": {}}

    # Response is [[{label, score}, ...]]
    items = result[0] if isinstance(result, list) and result and isinstance(result[0], list) else result
    if isinstance(items, list):
        probs = {}
        for item in items:
            lbl = item.get("label", "").lower()
            if lbl.startswith("label_"):
                idx = int(lbl.split("_")[1])
                lbl = ["negative", "neutral", "positive"][idx]
            probs[lbl] = item.get("score", 0)
    else:
        return {"label": "neutral", "score": 0.0, "confidence": 0.0, "probs": {}}

    pos = probs.get("positive", 0)
    neg = probs.get("negative", 0)
    score = pos - neg
    label = "positive" if score > 0.05 else ("negative" if score < -0.05 else "neutral")
    return {"label": label, "score": score, "confidence": max(probs.values()), "probs": probs}


def sentiment_batch(
    texts: List[str],
    model: str = "cardiffnlp/twitter-roberta-base-sentiment-latest",
    max_workers: int = 10,
) -> List[Dict]:
    """Batch sentiment with concurrent API calls."""
    results = [None] * len(texts)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(sentiment_analysis, text, model): i
            for i, text in enumerate(texts)
        }
        for future in as_completed(futures):
            idx = futures[future]
            try:
                results[idx] = future.result()
            except Exception:
                results[idx] = {"label": "neutral", "score": 0.0, "confidence": 0.0, "probs": {}}
    return results


def classify_batch(
    texts: List[str],
    labels: List[str],
    multi_label: bool = True,
    model: str = "facebook/bart-large-mnli",
    max_workers: int = 10,
) -> List[Dict[str, float]]:
    """Batch zero-shot classification with concurrent API calls."""
    results = [None] * len(texts)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(classify_zero_shot, text, labels, multi_label, model): i
            for i, text in enumerate(texts)
        }
        for future in as_completed(futures):
            idx = futures[future]
            try:
                results[idx] = future.result()
            except Exception:
                results[idx] = {}
    return results


def is_available() -> bool:
    """Check if HF Inference API is reachable."""
    try:
        headers = _headers()
        r = requests.post(
            f"{API_BASE}/cardiffnlp/twitter-roberta-base-sentiment-latest",
            headers=headers,
            json={"inputs": "test"},
            timeout=10,
        )
        if r.status_code in (401, 403) and headers:
            r = requests.post(
                f"{API_BASE}/cardiffnlp/twitter-roberta-base-sentiment-latest",
                headers={},
                json={"inputs": "test"},
                timeout=10,
            )
        return r.status_code == 200
    except Exception:
        return False
