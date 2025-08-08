"""Core package for the sentiment bot project."""

import importlib

# Ensure config module is available and re-export settings
config = importlib.import_module(".config", __name__)
settings = config.settings

__all__ = ["settings", "config"]
