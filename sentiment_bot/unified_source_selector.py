#!/usr/bin/env python3
"""
Unified Source Selector
======================

Standardizes source selection across all analysis modes.
Ensures consistent, production-ready source filtering regardless of analysis type.
"""

import yaml
from typing import Dict, List, Optional, Set
from pathlib import Path
from dataclasses import dataclass
from enum import Enum
from .region_country_mapper import get_region_mapper

class AnalysisMode(Enum):
    """Different analysis modes available."""
    SMART = "smart"
    ECONOMIC = "economic"
    MARKET = "market"
    AI_QUESTION = "ai_question"
    COMPREHENSIVE = "comprehensive"

class RegionFilter(Enum):
    """Region filtering options."""
    ALL = "all"
    ASIA = "asia"
    EUROPE = "europe"
    AMERICAS = "americas"
    MIDDLE_EAST = "middle_east"
    AFRICA = "africa"

@dataclass
class SourceSelection:
    """Represents a standardized source selection."""
    sources: List[Dict]
    total_count: int
    countries_covered: Set[str]
    regions_covered: Set[str]
    languages: Set[str]
    selection_criteria: Dict
    quality_score: float

class UnifiedSourceSelector:
    """
    Unified source selector for all analysis modes.
    Provides consistent, production-ready source selection.
    """

    def __init__(self, config_path: str = "config/master_sources_production.yaml"):
        """Initialize with production sources."""
        self.config_path = config_path
        self.sources = self._load_sources()
        self.region_mapper = get_region_mapper()

    def _load_sources(self) -> List[Dict]:
        """Load production-validated sources."""
        try:
            with open(self.config_path, "r") as f:
                config = yaml.safe_load(f)
            sources = config.get("sources", [])
            print(f"📋 Loaded {len(sources)} production sources")
            return sources
        except FileNotFoundError:
            print(f"⚠️  Production sources not found at {self.config_path}")
            print("   Falling back to validated sources...")
            try:
                with open("config/master_sources_validated.yaml", "r") as f:
                    config = yaml.safe_load(f)
                return config.get("sources", [])
            except FileNotFoundError:
                print("❌ No validated sources found!")
                return []

    def select_for_mode(
        self,
        mode: AnalysisMode,
        region: Optional[str] = None,
        countries: Optional[List[str]] = None,
        topics: Optional[List[str]] = None,
        min_sources: int = 20,
        max_sources: int = 100,
        quality_threshold: float = 0.8,
        country_filter_mode: str = "include"  # "include", "exclude", "prefer"
    ) -> SourceSelection:
        """
        Select sources for a specific analysis mode.

        Args:
            mode: Analysis mode (smart, economic, market, etc.)
            region: Target region filter
            countries: Specific countries to filter by
            topics: Topic filters
            min_sources: Minimum number of sources
            max_sources: Maximum number of sources
            quality_threshold: Quality threshold (0.0-1.0)
            country_filter_mode: How to apply country filter:
                - "include": Only include sources from specified countries
                - "exclude": Exclude sources from specified countries
                - "prefer": Prefer sources from specified countries but include others if needed

        Returns:
            SourceSelection object with selected sources
        """
        print(f"🎯 Selecting sources for {mode.value} analysis...")

        # Apply mode-specific defaults
        if mode == AnalysisMode.ECONOMIC:
            # Economic analysis needs financial sources
            preferred_topics = topics or ["economy", "business", "markets"]
            min_sources = max(min_sources, 15)
        elif mode == AnalysisMode.MARKET:
            # Market analysis needs high-frequency sources
            preferred_topics = topics or ["economy", "business", "markets", "technology"]
            min_sources = max(min_sources, 25)
        elif mode == AnalysisMode.AI_QUESTION:
            # AI question answering needs diverse sources
            preferred_topics = topics or ["economy", "business", "technology", "politics"]
            min_sources = max(min_sources, 30)
        else:
            # Smart and comprehensive modes
            preferred_topics = topics or ["economy", "business"]

        # Start with all sources
        candidates = self.sources.copy()

        # Apply region filter
        if region and region != "all":
            candidates = self._filter_by_region(candidates, region)
            print(f"📍 Region filter ({region}): {len(candidates)} sources")

        # Apply country filter with different modes
        if countries:
            candidates = self._filter_by_countries(candidates, countries, country_filter_mode)
            print(f"🌍 Country filter ({country_filter_mode}): {len(candidates)} sources")

        # Apply topic filter
        if preferred_topics:
            candidates = self._filter_by_topics(candidates, preferred_topics)
            print(f"📂 Topic filter: {len(candidates)} sources")

        # Apply quality scoring
        scored_sources = self._score_sources(candidates, mode, preferred_topics)

        # Select top sources
        selected = self._select_top_sources(
            scored_sources, min_sources, max_sources, quality_threshold
        )

        # Build selection object
        selection = self._build_selection(selected, mode, {
            "region": region,
            "countries": countries,
            "topics": preferred_topics,
            "min_sources": min_sources,
            "max_sources": max_sources,
            "quality_threshold": quality_threshold
        })

        self._log_selection_summary(selection)
        return selection

    def _filter_by_region(self, sources: List[Dict], region: str) -> List[Dict]:
        """Filter sources by region using comprehensive mapping."""
        # Use the comprehensive region mapper for accurate country lists
        target_countries = self.region_mapper.get_countries_by_region(region)

        if not target_countries:
            print(f"⚠️  Unknown region: {region}")
            return sources

        # Convert to lowercase for matching
        target_countries_lower = [country.lower().replace(' ', '_') for country in target_countries]

        filtered = []
        for source in sources:
            source_countries = source.get("countries", [])
            if any(country.lower() in target_countries_lower for country in source_countries):
                filtered.append(source)

        print(f"📍 Region '{region}' includes {len(target_countries)} countries, found {len(filtered)} sources")
        return filtered

    def _filter_by_countries(self, sources: List[Dict], countries: List[str], mode: str = "include") -> List[Dict]:
        """
        Filter sources by specific countries with different modes.

        Args:
            sources: List of source dictionaries
            countries: List of country names to filter by
            mode: Filter mode - "include", "exclude", or "prefer"
        """
        # Normalize country names for matching
        target_countries = [country.lower().replace(' ', '_') for country in countries]

        if mode == "include":
            # Only include sources from specified countries
            filtered = []
            for source in sources:
                source_countries = [c.lower() for c in source.get("countries", [])]
                if any(country in target_countries for country in source_countries):
                    filtered.append(source)
            return filtered

        elif mode == "exclude":
            # Exclude sources from specified countries
            filtered = []
            for source in sources:
                source_countries = [c.lower() for c in source.get("countries", [])]
                if not any(country in target_countries for country in source_countries):
                    filtered.append(source)
            return filtered

        elif mode == "prefer":
            # Prefer sources from specified countries but include others
            preferred = []
            others = []

            for source in sources:
                source_countries = [c.lower() for c in source.get("countries", [])]
                if any(country in target_countries for country in source_countries):
                    preferred.append(source)
                else:
                    others.append(source)

            # Return preferred first, then others
            print(f"   🎯 Found {len(preferred)} preferred sources, {len(others)} others")
            return preferred + others

        else:
            print(f"⚠️  Unknown country filter mode: {mode}, defaulting to 'include'")
            return self._filter_by_countries(sources, countries, "include")

    def _filter_by_topics(self, sources: List[Dict], topics: List[str]) -> List[Dict]:
        """Filter sources by topics."""
        return [
            source for source in sources
            if any(topic in source.get("topics", []) for topic in topics)
        ]

    def _score_sources(self, sources: List[Dict], mode: AnalysisMode, topics: List[str]) -> List[tuple]:
        """Score sources based on mode and topic relevance."""
        scored = []

        for source in sources:
            score = 0.0

            # Base quality score
            entry_count = source.get("entry_count", 0)
            if entry_count > 100:
                score += 0.4
            elif entry_count > 50:
                score += 0.3
            elif entry_count > 20:
                score += 0.2
            else:
                score += 0.1

            # Topic relevance
            source_topics = source.get("topics", [])
            topic_match = len(set(topics) & set(source_topics)) / len(topics) if topics else 0.5
            score += topic_match * 0.3

            # Domain quality (known high-quality sources)
            domain = source.get("domain", "")
            premium_domains = {
                "economist.com": 0.3,
                "ft.com": 0.3,
                "wsj.com": 0.3,
                "bloomberg.com": 0.3,
                "reuters.com": 0.25,
                "bbc.com": 0.25,
                "cnn.com": 0.2,
                "nytimes.com": 0.2
            }
            score += premium_domains.get(domain, 0.0)

            # Mode-specific bonuses
            if mode == AnalysisMode.ECONOMIC:
                if "economy" in source_topics or "business" in source_topics:
                    score += 0.1
            elif mode == AnalysisMode.MARKET:
                if entry_count > 50:  # High-frequency sources preferred
                    score += 0.1

            scored.append((source, min(score, 1.0)))

        return sorted(scored, key=lambda x: x[1], reverse=True)

    def _select_top_sources(
        self, scored_sources: List[tuple], min_sources: int, max_sources: int, quality_threshold: float
    ) -> List[Dict]:
        """Select top sources based on scores and constraints."""
        # First, get all sources above quality threshold
        quality_sources = [source for source, score in scored_sources if score >= quality_threshold]

        # If we don't have enough quality sources, lower the threshold gradually
        if len(quality_sources) < min_sources:
            for threshold in [0.7, 0.6, 0.5, 0.4, 0.3]:
                quality_sources = [source for source, score in scored_sources if score >= threshold]
                if len(quality_sources) >= min_sources:
                    break

        # Ensure we have at least min_sources
        if len(quality_sources) < min_sources:
            quality_sources = [source for source, score in scored_sources[:min_sources]]

        # Cap at max_sources
        return quality_sources[:max_sources]

    def _build_selection(self, sources: List[Dict], mode: AnalysisMode, criteria: Dict) -> SourceSelection:
        """Build a SourceSelection object."""
        countries = set()
        regions = set()
        languages = set()

        for source in sources:
            countries.update(source.get("countries", []))
            languages.add(source.get("language", "unknown"))

        # Map countries to regions
        country_region_map = {
            "china": "asia", "japan": "asia", "india": "asia",
            "germany": "europe", "united_kingdom": "europe", "france": "europe",
            "united_states": "americas", "canada": "americas"
        }

        for country in countries:
            if country in country_region_map:
                regions.add(country_region_map[country])

        # Calculate quality score
        avg_entries = sum(source.get("entry_count", 0) for source in sources) / len(sources) if sources else 0
        quality_score = min(1.0, avg_entries / 100.0)

        return SourceSelection(
            sources=sources,
            total_count=len(sources),
            countries_covered=countries,
            regions_covered=regions,
            languages=languages,
            selection_criteria=criteria,
            quality_score=quality_score
        )

    def _log_selection_summary(self, selection: SourceSelection):
        """Log selection summary."""
        print(f"\n📊 Source Selection Summary:")
        print(f"   ✅ Selected: {selection.total_count} sources")
        print(f"   🌍 Countries: {len(selection.countries_covered)}")
        print(f"   🗺️  Regions: {len(selection.regions_covered)}")
        print(f"   🔤 Languages: {len(selection.languages)}")
        print(f"   ⭐ Quality Score: {selection.quality_score:.2f}")

        # Show top countries
        country_counts = {}
        for source in selection.sources:
            for country in source.get("countries", []):
                country_counts[country] = country_counts.get(country, 0) + 1

        if country_counts:
            print(f"   📍 Top Countries:")
            for country, count in sorted(country_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
                print(f"     • {country}: {count} sources")

    def get_standard_config_for_mode(self, mode: AnalysisMode) -> Dict:
        """Get standard configuration for a specific mode."""
        configs = {
            AnalysisMode.SMART: {
                "min_sources": 20,
                "max_sources": 50,
                "quality_threshold": 0.6,
                "topics": ["economy", "business"]
            },
            AnalysisMode.ECONOMIC: {
                "min_sources": 15,
                "max_sources": 40,
                "quality_threshold": 0.7,
                "topics": ["economy", "business", "markets"]
            },
            AnalysisMode.MARKET: {
                "min_sources": 25,
                "max_sources": 60,
                "quality_threshold": 0.6,
                "topics": ["economy", "business", "markets", "technology"]
            },
            AnalysisMode.AI_QUESTION: {
                "min_sources": 30,
                "max_sources": 80,
                "quality_threshold": 0.5,
                "topics": ["economy", "business", "technology", "politics"]
            },
            AnalysisMode.COMPREHENSIVE: {
                "min_sources": 40,
                "max_sources": 100,
                "quality_threshold": 0.5,
                "topics": ["economy", "business", "technology", "politics", "energy"]
            }
        }
        return configs.get(mode, configs[AnalysisMode.SMART])

# Example usage and testing
if __name__ == "__main__":
    selector = UnifiedSourceSelector()

    # Test different modes
    for mode in AnalysisMode:
        print(f"\n{'='*60}")
        print(f"Testing {mode.value.upper()} mode")
        print(f"{'='*60}")

        config = selector.get_standard_config_for_mode(mode)
        selection = selector.select_for_mode(mode, **config)

        print(f"Selected {selection.total_count} sources with quality {selection.quality_score:.2f}")