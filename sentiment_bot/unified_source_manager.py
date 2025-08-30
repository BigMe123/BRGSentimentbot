#!/usr/bin/env python3
"""
Unified Source Manager - Ensures ALL components use the master source list.
This module intercepts and redirects all source requests to the master source system.
"""

import logging
from typing import List, Dict, Optional, Any
from .master_sources import get_master_sources, MasterSourceManager

logger = logging.getLogger(__name__)


class UnifiedSourceManager:
    """
    Single point of access for ALL source operations.
    This class ensures that no matter how sources are requested,
    they always come from the master source list.
    """

    def __init__(self):
        """Initialize with master source manager."""
        self.master = get_master_sources()
        logger.info(
            f"Unified Source Manager initialized with {len(self.master.sources)} sources"
        )

    def get_sources(self, **kwargs) -> List[Dict]:
        """
        Get sources - ALWAYS from master list.
        This method intercepts all source requests.
        """
        # Log the request to ensure we're catching everything
        logger.debug(f"Source request intercepted with params: {kwargs}")

        # Extract any filtering parameters
        regions = kwargs.get("regions", kwargs.get("region", None))
        if regions and not isinstance(regions, list):
            regions = [regions]

        topics = kwargs.get("topics", kwargs.get("topic", None))
        if topics and not isinstance(topics, list):
            topics = [topics]

        min_priority = kwargs.get("min_priority", kwargs.get("priority", 0.0))
        max_sources = kwargs.get("max_sources", kwargs.get("limit", None))

        # Always use master sources
        sources = self.master.get_sources_for_bot(
            regions=regions,
            topics=topics,
            min_priority=min_priority,
            max_sources=max_sources,
        )

        logger.info(f"Returning {len(sources)} sources from master list")
        return sources

    def get_source(self, domain: str) -> Optional[Dict]:
        """Get a specific source by domain."""
        source = self.master.get_source(domain)
        if source:
            return source.to_dict()
        return None

    def get_all_sources(self) -> List[Dict]:
        """Get all sources without filtering."""
        return self.get_sources()

    def get_high_priority_sources(self, threshold: float = 0.7) -> List[Dict]:
        """Get high priority sources."""
        return self.get_sources(min_priority=threshold)

    def get_sources_by_region(self, region: str) -> List[Dict]:
        """Get sources for a specific region."""
        return self.get_sources(region=region)

    def get_sources_by_topic(self, topic: str) -> List[Dict]:
        """Get sources for a specific topic."""
        return self.get_sources(topic=topic)

    def reload(self):
        """Reload sources from database."""
        self.master.reload()
        logger.info(f"Sources reloaded: {len(self.master.sources)} sources available")

    def get_statistics(self) -> Dict:
        """Get source statistics."""
        return self.master.get_statistics()


# Global singleton instance
_unified_manager: Optional[UnifiedSourceManager] = None


def get_unified_sources() -> UnifiedSourceManager:
    """Get the singleton unified source manager."""
    global _unified_manager
    if _unified_manager is None:
        _unified_manager = UnifiedSourceManager()
    return _unified_manager


# Override functions that might be used elsewhere
def load_sources_from_yaml(path: str) -> List[Dict]:
    """
    Legacy function - now redirects to master sources.
    Ignores the path and always returns master sources.
    """
    logger.warning(f"Legacy load_sources_from_yaml called with path: {path}")
    logger.info("Redirecting to master source list")
    return get_unified_sources().get_all_sources()


def load_sources_from_config(config: Dict) -> List[Dict]:
    """
    Legacy function - now redirects to master sources.
    Applies any filters from config but uses master list.
    """
    logger.warning("Legacy load_sources_from_config called")
    logger.info("Redirecting to master source list")

    # Extract any filtering from config
    filters = config.get("filters", {})
    return get_unified_sources().get_sources(**filters)


def get_sources_from_file(filename: str) -> List[Dict]:
    """
    Legacy function - now redirects to master sources.
    Ignores filename and returns master sources.
    """
    logger.warning(f"Legacy get_sources_from_file called with: {filename}")
    logger.info("Redirecting to master source list")
    return get_unified_sources().get_all_sources()


# Patch any direct file reading attempts
def ensure_master_sources():
    """
    Call this at startup to ensure all source access goes through master list.
    """
    import warnings

    # Set up warning for any attempts to read old source files
    def warn_on_legacy_access(filename):
        if any(
            x in str(filename) for x in ["sources.yaml", "seeds.txt", "skb_sources"]
        ):
            warnings.warn(
                f"Attempted to access legacy source file: {filename}\n"
                "All source access should go through master_sources module",
                DeprecationWarning,
                stacklevel=2,
            )

    # Monkey-patch file operations if needed
    import builtins

    _original_open = builtins.open

    def patched_open(file, *args, **kwargs):
        warn_on_legacy_access(file)
        return _original_open(file, *args, **kwargs)

    # Only patch in development/debug mode
    import os

    if os.environ.get("ENFORCE_MASTER_SOURCES", "").lower() == "true":
        builtins.open = patched_open

    logger.info("Master source enforcement initialized")


# Auto-initialize on import
ensure_master_sources()
