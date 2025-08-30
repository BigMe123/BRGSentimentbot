"""
SKB YAML Loader for dynamic source integration.
"""

import os
import json
import re
from typing import List, Dict, Any
from .skb_catalog import SourceRecord


def load_harvested_yaml(path: str) -> List[SourceRecord]:
    """Load harvested sources from YAML format."""
    if not os.path.exists(path):
        return []

    sources = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        # Parse simple YAML format used by harvester
        items = _parse_simple_yaml(content)

        for item in items:
            if "domain" not in item:
                continue

            # Create SourceRecord with defaults
            source = SourceRecord(
                domain=item["domain"],
                name=item.get("name", item["domain"]),
                region=item.get("region", "europe"),  # Default to europe for harvested
                country=_infer_country(item["domain"]),
                languages=item.get("languages", ["en"]),
                topics=item.get("topics", ["general"]),
                rss_endpoints=item.get("rss_endpoints", []),
                priority=item.get("priority", 0.5),
                policy=item.get("policy", "allow"),
                validation_status="active",
            )
            sources.append(source)

    except Exception as e:
        print(f"Warning: Could not load harvested sources from {path}: {e}")

    return sources


def _parse_simple_yaml(content: str) -> List[Dict[str, Any]]:
    """Parse the simple YAML format produced by the harvester."""
    items = []
    current_item = {}

    for line in content.split("\n"):
        line = line.strip()

        if not line or line.startswith("#"):
            continue

        if line.startswith("- "):
            # New item starting
            if current_item:
                items.append(current_item)
            current_item = {}
            line = line[2:].strip()

        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()

            # Handle different value types
            if value.startswith('"') and value.endswith('"'):
                # String value
                value = value[1:-1]
            elif value.startswith("[") and value.endswith("]"):
                # List value - parse JSON
                try:
                    value = json.loads(value)
                except:
                    value = []
            elif value.replace(".", "").isdigit():
                # Numeric value
                try:
                    value = float(value)
                except:
                    pass

            current_item[key] = value

    # Add final item
    if current_item:
        items.append(current_item)

    return items


def _infer_country(domain: str) -> str:
    """Infer country from domain."""
    tld_map = {
        ".uk": "GB",
        ".fr": "FR",
        ".de": "DE",
        ".it": "IT",
        ".es": "ES",
        ".nl": "NL",
        ".se": "SE",
        ".no": "NO",
        ".fi": "FI",
        ".dk": "DK",
        ".pl": "PL",
        ".cz": "CZ",
        ".hu": "HU",
        ".ru": "RU",
    }

    for tld, country in tld_map.items():
        if domain.endswith(tld):
            return country

    # Check for known domains
    if "bbc" in domain:
        return "GB"
    elif "france24" in domain:
        return "FR"
    elif "dw" in domain:
        return "DE"
    elif "euronews" in domain:
        return "FR"  # Based in Lyon
    elif "politico.eu" in domain:
        return "BE"  # Brussels

    return "EU"  # Generic EU
