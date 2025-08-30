"""
Selection Planner - Intelligent source selection with quotas and optimization.
Fast selection from massive SKB without materialization.
"""

import time
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import logging
import random

from .skb_catalog import SKBCatalog, SourceRecord, get_catalog

logger = logging.getLogger(__name__)


@dataclass
class SelectionQuotas:
    """Quotas and constraints for source selection."""

    min_sources: int = 30
    max_sources: int = 120
    min_editorial_families: int = 3  # wire, national, local/think-tank
    min_languages: int = 1
    max_per_domain: int = 10  # max docs per domain
    max_domain_word_share: float = 0.15  # max 15% of words from one domain
    max_headless_share: float = 0.10  # max 10% headless sources
    time_budget_seconds: int = 300  # 5 minutes

    # Discovery settings
    discovery_budget_percent: float = 0.10  # 10% of time for discovery
    discovery_max_domains: int = 20
    discovery_max_pages: int = 100


@dataclass
class SelectionPlan:
    """Execution plan with selected sources and allocations."""

    sources: List[SourceRecord]
    quotas: SelectionQuotas
    region: Optional[str]
    topics: List[str]

    # Performance metrics
    selection_time_ms: float = 0

    # Diversity metrics
    editorial_families: Dict[str, int] = field(default_factory=dict)
    language_distribution: Dict[str, int] = field(default_factory=dict)
    region_distribution: Dict[str, int] = field(default_factory=dict)

    # Work allocation
    time_allocations: Dict[str, float] = field(default_factory=dict)

    def get_diversity_score(self) -> float:
        """Calculate diversity score (0-1)."""
        score = 0.0

        # Editorial family diversity
        if len(self.editorial_families) >= self.quotas.min_editorial_families:
            score += 0.33
        else:
            score += 0.33 * (
                len(self.editorial_families) / self.quotas.min_editorial_families
            )

        # Language diversity
        if len(self.language_distribution) >= self.quotas.min_languages:
            score += 0.33

        # Source count
        if len(self.sources) >= self.quotas.min_sources:
            score += 0.34
        else:
            score += 0.34 * (len(self.sources) / self.quotas.min_sources)

        return score

    def meets_quotas(self) -> Tuple[bool, List[str]]:
        """Check if selection meets all quotas."""
        issues = []

        if len(self.sources) < self.quotas.min_sources:
            issues.append(
                f"Only {len(self.sources)} sources, need {self.quotas.min_sources}"
            )

        if len(self.editorial_families) < self.quotas.min_editorial_families:
            issues.append(f"Only {len(self.editorial_families)} editorial families")

        if len(self.language_distribution) < self.quotas.min_languages:
            issues.append(f"Only {len(self.language_distribution)} languages")

        # Check headless share
        headless_count = sum(1 for s in self.sources if s.policy == "headless")
        if headless_count > len(self.sources) * self.quotas.max_headless_share:
            issues.append(f"Too many headless sources: {headless_count}")

        return len(issues) == 0, issues


class SelectionPlanner:
    """Fast source selection with quotas and optimization."""

    def __init__(self, catalog: Optional[SKBCatalog] = None):
        self.catalog = catalog or get_catalog()
        self._priority_cache = {}

    def plan_selection(
        self,
        region: Optional[str] = None,
        topics: Optional[List[str]] = None,
        other_topic: Optional[str] = None,
        strict: bool = False,
        expand: bool = False,
        quotas: Optional[SelectionQuotas] = None,
    ) -> SelectionPlan:
        """
        Plan source selection based on criteria.

        Args:
            region: Target region (asia, middle_east, europe, americas, africa)
            topics: List of standard topics
            other_topic: Free-text topic for fuzzy matching
            strict: Only exact matches
            expand: Include cross-regional specialists
            quotas: Selection quotas (uses defaults if not provided)
        """
        start_time = time.time()
        quotas = quotas or SelectionQuotas()

        # Handle "other topic" mode with fuzzy matching
        if other_topic and not topics:
            topics = self._resolve_other_topic(other_topic)
            if not topics:
                logger.warning(
                    f"No topics matched for '{other_topic}', will trigger discovery"
                )
                topics = []  # Will trigger discovery pass later

        # Build candidate pool using indexes (fast!)
        candidates = self._get_candidates(region, topics, strict, expand)

        # Score and rank candidates
        scored = self._score_sources(candidates, region, topics)

        # Apply quotas and diversity requirements
        selected = self._apply_quotas(scored, quotas)

        # Build execution plan
        plan = SelectionPlan(
            sources=selected,
            quotas=quotas,
            region=region,
            topics=topics or [],
            selection_time_ms=(time.time() - start_time) * 1000,
        )

        # Calculate diversity metrics
        self._calculate_diversity(plan)

        # Allocate time budget
        self._allocate_time_budget(plan)

        # Log selection results
        meets, issues = plan.meets_quotas()
        if not meets:
            logger.warning(f"Selection quotas not fully met: {issues}")

        logger.info(
            f"Selected {len(plan.sources)} sources in {plan.selection_time_ms:.1f}ms, "
            f"diversity score: {plan.get_diversity_score():.2f}"
        )

        return plan

    def _resolve_other_topic(self, query: str) -> List[str]:
        """Resolve free-text topic to standard topics using fuzzy matching."""
        # Normalize query
        query = query.lower().strip()

        # Try fuzzy matching against known topics
        matched_topics = self.catalog.fuzzy_match_topics(query, threshold=0.6)

        if matched_topics:
            logger.info(f"Matched '{query}' to topics: {matched_topics[:3]}")
            return matched_topics[:3]  # Use top 3 matches

        # Try keyword extraction and matching
        keywords = set(query.split())
        stopwords = {"the", "in", "of", "and", "or", "for", "with", "on", "at"}
        keywords -= stopwords

        if keywords:
            # Try each keyword
            all_matches = []
            for keyword in keywords:
                matches = self.catalog.fuzzy_match_topics(keyword, threshold=0.5)
                all_matches.extend(matches)

            if all_matches:
                # Deduplicate and return top matches
                unique = list(dict.fromkeys(all_matches))
                logger.info(f"Keyword matched '{query}' to topics: {unique[:3]}")
                return unique[:3]

        return []

    def _get_candidates(
        self,
        region: Optional[str],
        topics: Optional[List[str]],
        strict: bool,
        expand: bool,
    ) -> List[SourceRecord]:
        """Get candidate sources using precomputed indexes."""
        candidates = []

        if region and topics:
            # Intersection of region and topics
            candidates = self.catalog.get_sources_by_criteria(
                region=region, topics=topics, min_priority=0.3 if not strict else 0.5
            )
        elif region:
            # Region only
            candidates = self.catalog.get_sources_by_region(region)
        elif topics:
            # Topics only - union of all topic sources
            seen = set()
            for topic in topics:
                sources = self.catalog.get_sources_by_topic(topic)
                for source in sources:
                    if source.domain not in seen:
                        candidates.append(source)
                        seen.add(source.domain)
        else:
            # No specific criteria - get high-priority sources
            candidates = self.catalog.get_sources_by_criteria(
                min_priority=0.7, limit=200
            )

        # Expand with global specialists if requested
        if expand and len(candidates) < 50:
            global_sources = self.catalog.get_sources_by_criteria(
                policies=["allow"], min_priority=0.8, limit=50
            )

            # Add sources not already in candidates
            existing_domains = {s.domain for s in candidates}
            for source in global_sources:
                if source.domain not in existing_domains:
                    candidates.append(source)

        logger.info(f"Found {len(candidates)} candidate sources")
        return candidates

    def _score_sources(
        self,
        sources: List[SourceRecord],
        region: Optional[str],
        topics: Optional[List[str]],
    ) -> List[Tuple[SourceRecord, float]]:
        """Score and rank sources."""
        scored = []

        for source in sources:
            score = 0.0

            # Base priority score
            score += source.priority * 2.0

            # Reliability bonus
            score += source.reliability_score * 1.5

            # Freshness bonus
            score += source.freshness_score * 1.0

            # Historical yield bonus
            if source.historical_yield > 0:
                score += min(1.0, source.historical_yield / 1000) * 0.5

            # Region match bonus
            if region and source.region == region:
                score += 1.0

            # Topic match bonus
            if topics:
                matching_topics = set(source.topics) & set(topics)
                score += len(matching_topics) * 0.5

            # Diversity bonus (slight randomization)
            score += random.uniform(0, 0.2)

            # Policy penalty
            if source.policy == "headless":
                score *= 0.7  # Penalize headless sources
            elif source.policy == "api_only":
                score *= 0.9

            scored.append((source, score))

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)

        return scored

    def _apply_quotas(
        self, scored: List[Tuple[SourceRecord, float]], quotas: SelectionQuotas
    ) -> List[SourceRecord]:
        """Apply quotas and diversity requirements."""
        selected = []

        # Track constraints
        domain_counts = defaultdict(int)
        editorial_families = defaultdict(int)
        languages = set()
        headless_count = 0

        for source, score in scored:
            # Check if we've reached max sources
            if len(selected) >= quotas.max_sources:
                break

            # Check per-domain limit
            if domain_counts[source.domain] >= quotas.max_per_domain:
                continue

            # Check headless limit
            if source.policy == "headless":
                if headless_count >= len(selected) * quotas.max_headless_share:
                    continue
                headless_count += 1

            # Add source
            selected.append(source)
            domain_counts[source.domain] += 1

            # Track editorial family
            if "wire" in source.notes.lower() or "agency" in source.name.lower():
                editorial_families["wire"] += 1
            elif "think" in source.notes.lower():
                editorial_families["think_tank"] += 1
            else:
                editorial_families["publication"] += 1

            # Track languages
            languages.update(source.languages)

            # Check if we've met minimum requirements
            if (
                len(selected) >= quotas.min_sources
                and len(editorial_families) >= quotas.min_editorial_families
                and len(languages) >= quotas.min_languages
            ):
                # We've met quotas, but continue to max for better coverage
                pass

        logger.info(
            f"Selected {len(selected)} sources with {len(editorial_families)} "
            f"editorial families and {len(languages)} languages"
        )

        return selected

    def _calculate_diversity(self, plan: SelectionPlan):
        """Calculate diversity metrics for the plan."""
        for source in plan.sources:
            # Editorial family
            if "wire" in source.notes.lower() or "agency" in source.name.lower():
                plan.editorial_families["wire"] = (
                    plan.editorial_families.get("wire", 0) + 1
                )
            elif "think" in source.notes.lower():
                plan.editorial_families["think_tank"] = (
                    plan.editorial_families.get("think_tank", 0) + 1
                )
            else:
                plan.editorial_families["publication"] = (
                    plan.editorial_families.get("publication", 0) + 1
                )

            # Languages
            for lang in source.languages:
                plan.language_distribution[lang] = (
                    plan.language_distribution.get(lang, 0) + 1
                )

            # Regions
            plan.region_distribution[source.region] = (
                plan.region_distribution.get(source.region, 0) + 1
            )

    def _allocate_time_budget(self, plan: SelectionPlan):
        """Allocate time budget across selected sources."""
        total_budget = plan.quotas.time_budget_seconds
        num_sources = len(plan.sources)

        if num_sources == 0:
            return

        # Reserve time for discovery if needed
        discovery_time = 0
        if num_sources < plan.quotas.min_sources:
            discovery_time = total_budget * plan.quotas.discovery_budget_percent
            total_budget -= discovery_time

        # Allocate remaining time based on priority and reliability
        total_score = sum(s.priority * s.reliability_score for s in plan.sources)

        for source in plan.sources:
            source_score = source.priority * source.reliability_score
            allocation = (
                (source_score / total_score) * total_budget if total_score > 0 else 0
            )

            # Apply min/max bounds
            allocation = max(1.0, min(10.0, allocation))  # 1-10 seconds per source

            plan.time_allocations[source.domain] = allocation

        if discovery_time > 0:
            plan.time_allocations["_discovery"] = discovery_time
