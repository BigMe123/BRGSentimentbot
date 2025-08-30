"""Model management with explicit IDs and device selection."""

import torch
import yaml
from pathlib import Path
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)

# Load config
config_path = Path(__file__).parent.parent / "config" / "defaults.yaml"
if config_path.exists():
    with open(config_path) as f:
        CONFIG = yaml.safe_load(f)
else:
    CONFIG = {"models": {}, "runtime": {"device_preference": ["cpu"]}}


def _pick_device(preferences: List[str]) -> Any:
    """Select best available device from preferences."""
    for device in preferences:
        if device.startswith("cuda") and torch.cuda.is_available():
            return 0  # CUDA device 0
        if device.startswith("mps") and torch.backends.mps.is_available():
            return "mps"
    return -1  # CPU


def build_pipeline(task: str, model_key: str = None, **kwargs):
    """Build a pipeline with explicit model and device configuration."""
    from transformers import pipeline

    # Get device preference
    device_pref = CONFIG.get("runtime", {}).get("device_preference", ["cpu"])
    device = _pick_device(device_pref)

    # Get model config
    if model_key and model_key in CONFIG.get("models", {}):
        model_config = CONFIG["models"][model_key]
        kwargs["model"] = model_config["id"]
        kwargs["revision"] = model_config.get("revision", "main")

    # Set device
    if device == "mps":
        kwargs["device"] = "mps:0"
    elif device == 0:
        kwargs["device"] = 0
    # For CPU, omit device parameter

    logger.info(
        f"Building {task} pipeline with model {kwargs.get('model', 'default')} on device {device}"
    )

    return pipeline(task, **kwargs)


def get_sentiment_pipeline():
    """Get sentiment analysis pipeline with configured model."""
    return build_pipeline("sentiment-analysis", "sentiment")


def get_nli_pipeline():
    """Get zero-shot classification pipeline with configured model."""
    return build_pipeline("zero-shot-classification", "nli")


def get_summarizer_pipeline():
    """Get summarization pipeline with configured model."""
    return build_pipeline("summarization", "summarizer")


def get_emotion_pipeline():
    """Get emotion detection pipeline with configured model."""
    from transformers import pipeline

    device_pref = CONFIG.get("runtime", {}).get("device_preference", ["cpu"])
    device = _pick_device(device_pref)

    model_config = CONFIG.get("models", {}).get("emotion", {})
    model_id = model_config.get("id", "j-hartmann/emotion-english-distilroberta-base")
    revision = model_config.get("revision", "main")

    kwargs = {"model": model_id, "revision": revision}

    if device == "mps":
        kwargs["device"] = "mps:0"
    elif device == 0:
        kwargs["device"] = 0

    return pipeline("text-classification", **kwargs)


def batched_predict(pipeline_func, texts: List[str], batch_size: int = None):
    """Batch inference for better performance."""
    if batch_size is None:
        batch_size = CONFIG.get("runtime", {}).get("batch_size", 16)

    results = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        batch_results = pipeline_func(batch)
        results.extend(batch_results)

    return results
