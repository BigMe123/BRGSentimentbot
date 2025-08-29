#!/usr/bin/env python
"""
Initialize SKB SQLite database from existing YAML file.
Run this once to set up the new system.
"""

import logging
from pathlib import Path
from sentiment_bot.skb_catalog import get_catalog

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """Initialize the SKB catalog database."""
    
    # Path to existing SKB YAML
    yaml_path = Path("config/sources/skb_v1.yaml")
    
    if not yaml_path.exists():
        logger.error(f"SKB YAML file not found at {yaml_path}")
        return 1
    
    logger.info("Initializing SKB catalog...")
    
    try:
        # Get catalog instance (creates DB if needed)
        catalog = get_catalog()
        
        # Import from YAML
        logger.info(f"Importing sources from {yaml_path}...")
        catalog.import_from_yaml(str(yaml_path))
        
        # Get stats
        stats = catalog.get_stats()
        
        logger.info("✓ SKB catalog initialized successfully!")
        logger.info(f"  Total sources: {stats['total_sources']}")
        logger.info(f"  Active sources: {stats['active_sources']}")
        logger.info(f"  Regions: {', '.join(stats['regions'].keys())}")
        logger.info(f"  Top topics: {', '.join(list(stats['topics'].keys())[:5])}")
        
        return 0
        
    except Exception as e:
        logger.error(f"Failed to initialize SKB: {e}")
        return 1

if __name__ == "__main__":
    exit(main())