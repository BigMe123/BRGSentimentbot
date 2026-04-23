"""Core package for the sentiment bot project."""

import importlib
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

config = importlib.import_module(".config", __name__)
settings = config.settings

__all__ = ["settings", "config"]
