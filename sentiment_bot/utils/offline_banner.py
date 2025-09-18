"""
Offline Mode Banner Utilities
Displays cache status and offline mode indicators
"""

from typing import Dict, List, Optional
from datetime import datetime


def format_cache_status(cache_info: Dict) -> str:
    """
    Format cache information into a readable status string

    Args:
        cache_info: Dictionary with cache metadata

    Returns:
        Formatted cache status string
    """
    if not cache_info:
        return "🌐 LIVE"

    source = cache_info.get('source', 'unknown')
    provider = cache_info.get('provider', 'unknown')
    age_hours = cache_info.get('age_hours', 0)
    offline_mode = cache_info.get('offline_mode', False)

    if offline_mode:
        if age_hours < 1:
            age_str = f"{int(age_hours * 60)}m"
        elif age_hours < 24:
            age_str = f"{age_hours:.1f}h"
        else:
            age_str = f"{age_hours/24:.1f}d"

        return f"📦 CACHED ({age_str} old) - {provider.upper()}"
    else:
        return f"🌐 LIVE - {provider.upper()}"


def generate_offline_banner(data_sources: List[Dict], show_details: bool = True) -> str:
    """
    Generate offline mode banner for multiple data sources

    Args:
        data_sources: List of data sources with cache info
        show_details: Whether to show detailed cache information

    Returns:
        Formatted offline mode banner
    """
    if not data_sources:
        return ""

    # Check if any sources are cached
    cached_sources = [src for src in data_sources if src.get('_cache_info', {}).get('offline_mode', False)]
    live_sources = [src for src in data_sources if not src.get('_cache_info', {}).get('offline_mode', True)]

    if not cached_sources:
        return "🌐 All data sources are LIVE"

    banner_lines = []

    if len(cached_sources) == len(data_sources):
        # All sources cached
        banner_lines.append("📦 OFFLINE MODE - All data served from cache")
    else:
        # Mixed mode
        banner_lines.append(f"⚠️ MIXED MODE - {len(cached_sources)}/{len(data_sources)} sources cached")

    if show_details:
        banner_lines.append("Data sources:")

        for src in data_sources:
            cache_info = src.get('_cache_info', {})
            provider_name = cache_info.get('provider', 'unknown')
            country = src.get('country', 'unknown')

            status_str = format_cache_status(cache_info)
            banner_lines.append(f"  • {country} ({provider_name}): {status_str}")

    return "\n".join(banner_lines)


def get_cache_summary(data_sources: List[Dict]) -> Dict:
    """
    Get summary statistics about cache usage

    Args:
        data_sources: List of data sources with cache info

    Returns:
        Dictionary with cache usage statistics
    """
    if not data_sources:
        return {
            'total_sources': 0,
            'cached_sources': 0,
            'live_sources': 0,
            'cache_percentage': 0,
            'offline_mode': False,
            'mixed_mode': False
        }

    cached_count = sum(1 for src in data_sources if src.get('_cache_info', {}).get('offline_mode', False))
    live_count = len(data_sources) - cached_count

    return {
        'total_sources': len(data_sources),
        'cached_sources': cached_count,
        'live_sources': live_count,
        'cache_percentage': round(cached_count / len(data_sources) * 100, 1),
        'offline_mode': cached_count == len(data_sources),
        'mixed_mode': 0 < cached_count < len(data_sources)
    }


def format_api_cache_status(data_sources: List[Dict]) -> Dict:
    """
    Format cache status for API responses

    Args:
        data_sources: List of data sources with cache info

    Returns:
        Dictionary with cache status for API
    """
    summary = get_cache_summary(data_sources)

    # Extract detailed source information
    source_details = []
    for src in data_sources:
        cache_info = src.get('_cache_info', {})
        source_details.append({
            'provider': cache_info.get('provider', 'unknown'),
            'country': src.get('country', 'unknown'),
            'source_type': cache_info.get('source', 'unknown'),
            'age_hours': cache_info.get('age_hours', 0),
            'cached_at': cache_info.get('cached_at', cache_info.get('fetched_at')),
            'offline_mode': cache_info.get('offline_mode', False)
        })

    return {
        'cache_summary': summary,
        'source_details': source_details,
        'banner_text': generate_offline_banner(data_sources, show_details=False)
    }