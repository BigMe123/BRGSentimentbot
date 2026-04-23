"""
Source credibility tiers for news outlets.

Tier 1: Major wire services and global prestige outlets (Reuters, AP, BBC, NYT, etc.)
Tier 2: Regional quality papers, think tanks, specialized outlets
Tier 3: Aggregators, tabloids, blogs, unknown sources

Each tier has a weight used to adjust sentiment confidence.
"""

import re

# Tier 1: Wire services, global prestige (weight 1.0)
TIER_1 = {
    "Reuters", "Associated Press", "AP", "AFP",
    "BBC News", "CNN", "New York Times", "Washington Post",
    "The Guardian", "Al Jazeera", "Financial Times",
    "Wall Street Journal", "Bloomberg", "The Economist",
    "NPR", "PBS", "ABC News", "NBC News", "CBS News",
    "France 24", "Deutsche Welle", "NHK",
}

# Tier 2: Regional quality, think tanks, specialized (weight 0.8)
TIER_2 = {
    "CNBC", "Forbes", "Axios", "Politico", "The Hill",
    "Foreign Affairs", "Foreign Policy", "CFR", "CSIS",
    "Brookings", "RAND", "Atlantic Council", "Carnegie",
    "Defense News", "Defense One", "Janes", "Breaking Defense",
    "War on the Rocks", "Lawfare", "The Diplomat",
    "South China Morning Post", "Japan Times", "Nikkei Asia",
    "Straits Times", "Bangkok Post", "Le Monde",
    "Der Spiegel", "Euronews", "ABC Australia",
    "Daily Maverick", "India Today", "Economic Times",
    "Middle East Institute", "BESA Center",
    "Nature", "Science Daily", "STAT", "New Scientist",
    "Ars Technica", "TechCrunch", "Wired", "The Verge",
    "SpaceNews", "NASA", "Bellingcat", "The Intercept",
    "RealClearDefense", "NATO", "NZ Herald",
    "Buenos Aires Times", "Mint",
}

# Everything else is Tier 3 (weight 0.5)

TIER_WEIGHTS = {1: 1.0, 2: 0.8, 3: 0.5}


def get_tier(source_name: str) -> int:
    """Return credibility tier (1, 2, or 3) for a source name."""
    if source_name in TIER_1:
        return 1
    if source_name in TIER_2:
        return 2
    # Word-boundary partial match for long names (e.g. "BBC News World" matches "BBC News")
    name_lower = source_name.lower()
    for t1 in TIER_1:
        if re.search(r'\b' + re.escape(t1.lower()) + r'\b', name_lower):
            return 1
    for t2 in TIER_2:
        if re.search(r'\b' + re.escape(t2.lower()) + r'\b', name_lower):
            return 2
    return 3


def get_weight(source_name: str) -> float:
    """Return credibility weight (1.0, 0.8, or 0.5) for a source."""
    return TIER_WEIGHTS[get_tier(source_name)]


def tier_label(tier: int) -> str:
    """Human-readable tier label."""
    return {1: "Tier 1 (Major)", 2: "Tier 2 (Regional/Specialized)", 3: "Tier 3 (Other)"}[tier]
