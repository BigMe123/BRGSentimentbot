from __future__ import annotations

from typing import List, Tuple

# Ordered choices for regions and topics used in the interactive CLI
REGION_ORDER = [
    "africa",
    "asia",
    "europe",
    "latin_america",
    "middle_east",
    "north_america",
    "oceania",
]

TOPIC_ORDER = [
    "energy",
    "elections",
    "sanctions",
    "cybersecurity",
    "protests",
    "trade",
    "banking",
    "sovereign_risk",
    "supply_chain",
    "climate",
    "migration",
    "health",
    "conflict",
    "technology",
    "defense",
    "natural_disasters",
    "terrorism",
    "infrastructure",
    "diplomacy",
]

REGION_CHOICES: List[Tuple[str, str]] = [
    ("All Regions", "all"),
    *[(name.replace("_", " ").title(), name) for name in REGION_ORDER],
]

TOPIC_CHOICES: List[Tuple[str, str]] = [
    ("All Topics", "all"),
    *[(name.replace("_", " ").title(), name) for name in TOPIC_ORDER],
]

WINDOW_CHOICES: List[Tuple[str, str]] = [
    ("Minute", "minute"),
    ("Half Hour", "half_hour"),
    ("Hour", "hour"),
    ("Day", "day"),
    ("Week", "week"),
    ("Month", "month"),
    ("Year", "year"),
]

REGION_KEYS = [c[1] for c in REGION_CHOICES]
TOPIC_KEYS = [c[1] for c in TOPIC_CHOICES]
WINDOW_KEYS = [c[1] for c in WINDOW_CHOICES]


def parse_multi_selection(selection: str, options: List[str]) -> List[str]:
    """Parse a comma separated selection of numbers into option keys.

    Returns an empty list when ``all`` is chosen.
    Raises ``ValueError`` on invalid input.
    """

    if selection.strip().lower() in {"all", ""}:
        return []
    parts = [p.strip() for p in selection.split(",") if p.strip()]
    result = []
    for part in parts:
        if not part.isdigit():
            raise ValueError("invalid selection")
        idx = int(part) - 1
        if idx < 0 or idx >= len(options):
            raise ValueError("invalid selection")
        if idx == 0:
            return []
        result.append(options[idx])
    return result


def parse_single_selection(selection: str, options: List[str]) -> str:
    """Parse a single numeric selection into an option key."""

    if not selection.strip().isdigit():
        raise ValueError("invalid selection")
    idx = int(selection) - 1
    if idx < 0 or idx >= len(options):
        raise ValueError("invalid selection")
    return options[idx]
