"""Core package for the sentiment bot project."""

import importlib
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure config module is available and re-export settings
config = importlib.import_module(".config", __name__)
settings = config.settings

# Initialize master source system
try:
    from .master_sources import get_master_sources, get_source_statistics
    from .unified_source_manager import get_unified_sources, ensure_master_sources

    # Ensure master sources are always used
    ensure_master_sources()

    # Log initialization
    stats = get_source_statistics()
    logger.info(
        f"Master source system initialized with {stats['total_sources']} sources"
    )

except ImportError as e:
    logger.warning(f"Master source system not available: {e}")

__all__ = ["settings", "config", "get_master_sources", "get_unified_sources"]
