"""
Source Selection & Quotas Engine
Selects appropriate sources based on region/topic with diversity quotas.
"""

import yaml
import random
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


@dataclass
class SourceMetadata:
    """Rich metadata for a news source."""
    domain: str
    name: str
    country: str = ""
    region: str = ""
    languages: List[str] = field(default_factory=list)
    topics: List[str] = field(default_factory=list)
    primary_sections: List[str] = field(default_factory=list)
    rss_endpoints: List[str] = field(default_factory=list)
    sitemap_endpoints: List[str] = field(default_factory=list)
    priority: float = 0.5
    policy: str = "allow"  # allow/deny/js_allowed/api_only/respect_robots
    rate_limit_ms: int = 300
    max_docs_per_run: int = 30
    notes: str = ""
    
    # Runtime stats
    historical_yield: float = 0.0  # avg fresh words per run
    freshness_score: float = 0.5  # how recently updated
    
    def matches_criteria(self, region: Optional[str], topic: Optional[str], strict: bool = False) -> float:
        """Calculate match score for region/topic criteria."""
        score = 0.0
        
        # Region matching
        if region:
            if self.region == region:
                score += 1.0
            elif not strict and region in self.notes:
                score += 0.5
            elif strict:
                return 0.0  # Strict mode: no match = exclude
        
        # Topic matching
        if topic:
            if topic in self.topics:
                score += 1.0
            elif not strict and any(t for t in self.topics if topic in t or t in topic):
                score += 0.5
            elif strict and region:  # Both specified in strict mode
                return 0.0
        
        # Boost for priority
        score *= (0.5 + self.priority)
        
        return score


@dataclass
class SelectionPlan:
    """Execution plan for source selection with quotas."""
    sources: List[SourceMetadata]
    quotas: Dict[str, Any]
    budget_allocation: Dict[str, float]  # time allocation per source type
    work_queue: List[Tuple[SourceMetadata, float]]  # (source, allocated_time)
    
    def meets_diversity_requirements(self) -> Tuple[bool, List[str]]:
        """Check if selection meets diversity quotas."""
        issues = []
        
        # Check minimum sources
        if len(self.sources) < self.quotas['min_sources']:
            issues.append(f"Only {len(self.sources)} sources, need {self.quotas['min_sources']}")
        
        # Check editorial families
        families = set()
        for source in self.sources:
            if 'wire' in source.notes.lower() or 'agency' in source.name.lower():
                families.add('wire')
            elif 'think' in source.notes.lower() or 'analysis' in source.notes.lower():
                families.add('think_tank')
            else:
                families.add('publication')
        
        if len(families) < self.quotas.get('min_editorial_families', 3):
            issues.append(f"Only {len(families)} editorial families, need {self.quotas['min_editorial_families']}")
        
        # Check language diversity
        all_languages = set()
        for source in self.sources:
            all_languages.update(source.languages)
        
        if len(all_languages) < self.quotas.get('min_languages', 1):
            issues.append(f"Only {len(all_languages)} languages, need {self.quotas['min_languages']}")
        
        return len(issues) == 0, issues


class SourceSelector:
    """Selects and prioritizes sources based on region/topic criteria."""
    
    def __init__(self, skb_path: Optional[Path] = None):
        """Initialize with Source Knowledge Base."""
        self.skb_path = skb_path or Path("config/sources/skb_v1.yaml")
        self.skb = self._load_skb()
        self.sources_by_region = self._index_by_region()
        self.sources_by_topic = self._index_by_topic()
        self.all_sources = self._flatten_sources()
        
    def _load_skb(self) -> Dict[str, Any]:
        """Load Source Knowledge Base from YAML."""
        if not self.skb_path.exists():
            logger.warning(f"SKB not found at {self.skb_path}, using empty registry")
            return {"regions": {}, "topic_specialists": {}, "default_quotas": {}}
        
        with open(self.skb_path) as f:
            return yaml.safe_load(f)
    
    def _index_by_region(self) -> Dict[str, List[SourceMetadata]]:
        """Index sources by region."""
        index = defaultdict(list)
        
        for region_key, region_data in self.skb.get('regions', {}).items():
            for source_dict in region_data.get('sources', []):
                source = SourceMetadata(**source_dict)
                index[region_key].append(source)
        
        return dict(index)
    
    def _index_by_topic(self) -> Dict[str, List[SourceMetadata]]:
        """Index sources by topic."""
        index = defaultdict(list)
        
        # From regions
        for region_data in self.skb.get('regions', {}).values():
            for source_dict in region_data.get('sources', []):
                source = SourceMetadata(**source_dict)
                for topic in source.topics:
                    index[topic].append(source)
        
        # From topic specialists
        for topic, specialists in self.skb.get('topic_specialists', {}).items():
            for source_dict in specialists:
                source = SourceMetadata(**source_dict)
                source.topics = source_dict.get('topics', [topic])
                index[topic].append(source)
        
        return dict(index)
    
    def _flatten_sources(self) -> List[SourceMetadata]:
        """Get all sources as a flat list."""
        all_sources = []
        seen = set()
        
        for region_sources in self.sources_by_region.values():
            for source in region_sources:
                if source.domain not in seen:
                    all_sources.append(source)
                    seen.add(source.domain)
        
        for topic_sources in self.sources_by_topic.values():
            for source in topic_sources:
                if source.domain not in seen:
                    all_sources.append(source)
                    seen.add(source.domain)
        
        return all_sources
    
    def select_sources(
        self,
        region: Optional[str] = None,
        topic: Optional[str] = None,
        strict: bool = False,
        expand: bool = False,
        min_sources: Optional[int] = None,
        target_words: Optional[int] = None,
        budget_seconds: int = 300
    ) -> SelectionPlan:
        """
        Select sources based on criteria with quota enforcement.
        
        Args:
            region: Target region (e.g., 'asia', 'middle_east')
            topic: Target topic (e.g., 'elections', 'security')
            strict: Only include exact matches
            expand: Include adjacent regions and global specialists
            min_sources: Minimum number of sources required
            target_words: Target word count
            budget_seconds: Time budget in seconds
            
        Returns:
            SelectionPlan with selected sources and quotas
        """
        # Get default quotas
        quotas = self.skb.get('default_quotas', {}).copy()
        if min_sources:
            quotas['min_sources'] = min_sources
        if target_words:
            quotas['target_words'] = target_words
        
        # Start with exact matches
        candidates = []
        
        # Region matches
        if region and region in self.sources_by_region:
            for source in self.sources_by_region[region]:
                score = source.matches_criteria(region, topic, strict)
                if score > 0:
                    candidates.append((source, score))
        
        # Topic matches
        if topic and topic in self.sources_by_topic:
            for source in self.sources_by_topic[topic]:
                # Avoid duplicates
                if not any(c[0].domain == source.domain for c in candidates):
                    score = source.matches_criteria(region, topic, strict)
                    if score > 0:
                        candidates.append((source, score))
        
        # Expand if needed
        if expand and len(candidates) < quotas['min_sources']:
            # Add topic specialists
            if topic and topic in self.skb.get('topic_specialists', {}):
                for source_dict in self.skb['topic_specialists'][topic]:
                    source = SourceMetadata(**source_dict)
                    if not any(c[0].domain == source.domain for c in candidates):
                        candidates.append((source, 0.7))  # Lower score for specialists
            
            # Add high-priority global sources
            for source in self.all_sources:
                if source.priority >= 0.8 and not any(c[0].domain == source.domain for c in candidates):
                    if not region or not strict:  # Only in non-strict mode
                        candidates.append((source, source.priority * 0.5))
        
        # Sort by score and priority
        candidates.sort(key=lambda x: (x[1], x[0].priority), reverse=True)
        
        # Select top sources up to quota
        selected = []
        domains_seen = set()
        
        for source, score in candidates:
            if source.domain not in domains_seen:
                selected.append(source)
                domains_seen.add(source.domain)
                
                if len(selected) >= quotas.get('min_sources', 30) * 2:  # Get extra for filtering
                    break
        
        # Build execution plan
        plan = SelectionPlan(
            sources=selected[:quotas.get('min_sources', 30)],
            quotas=quotas,
            budget_allocation=self._allocate_budget(selected, budget_seconds),
            work_queue=[]
        )
        
        # Build prioritized work queue
        plan.work_queue = self._build_work_queue(plan)
        
        # Log selection
        logger.info(f"Selected {len(plan.sources)} sources for region={region}, topic={topic}")
        meets, issues = plan.meets_diversity_requirements()
        if not meets:
            logger.warning(f"Diversity issues: {issues}")
        
        return plan
    
    def _allocate_budget(self, sources: List[SourceMetadata], budget_seconds: int) -> Dict[str, float]:
        """Allocate time budget across source types."""
        allocation = {
            'fast_feeds': 0.7,  # RSS and simple HTML
            'discovery': 0.1,   # Source discovery
            'long_form': 0.2,   # Think tanks and analysis
        }
        
        # Adjust based on source mix
        think_tank_count = sum(1 for s in sources if 'think' in s.notes.lower())
        wire_count = sum(1 for s in sources if 'wire' in s.notes.lower() or 'agency' in s.name.lower() or s.priority >= 0.85)
        
        if think_tank_count > len(sources) * 0.3:
            # Many think tanks, reduce their allocation
            allocation['long_form'] = 0.15
            allocation['fast_feeds'] = 0.75
        
        if wire_count > len(sources) * 0.5:
            # Many wires, they're fast
            allocation['fast_feeds'] = 0.8
            allocation['discovery'] = 0.05
            allocation['long_form'] = 0.15
        
        return {k: v * budget_seconds for k, v in allocation.items()}
    
    def _build_work_queue(self, plan: SelectionPlan) -> List[Tuple[SourceMetadata, float]]:
        """Build prioritized work queue with time allocations."""
        queue = []
        
        # Categorize sources
        fast_feeds = []
        long_form = []
        
        for source in plan.sources:
            if 'think' in source.notes.lower() or 'analysis' in source.notes.lower():
                long_form.append(source)
            else:
                fast_feeds.append(source)
        
        # Sort by priority and freshness
        fast_feeds.sort(key=lambda s: (s.priority, s.freshness_score), reverse=True)
        long_form.sort(key=lambda s: s.priority, reverse=True)
        
        # Allocate time
        fast_time_per_source = plan.budget_allocation['fast_feeds'] / max(len(fast_feeds), 1)
        long_time_per_source = plan.budget_allocation['long_form'] / max(len(long_form), 1)
        
        # Build queue (fast feeds first for freshness)
        for source in fast_feeds:
            queue.append((source, min(fast_time_per_source, 10)))  # Cap at 10s per source
        
        for source in long_form:
            queue.append((source, min(long_time_per_source, 15)))  # Cap at 15s for long form
        
        return queue
    
    def get_rss_urls_for_selection(self, plan: SelectionPlan) -> List[str]:
        """Extract RSS URLs from selection plan."""
        urls = []
        for source, _ in plan.work_queue:
            urls.extend(source.rss_endpoints)
        return urls
    
    def get_discovery_targets(self, region: str, topic: str) -> List[Dict[str, Any]]:
        """Get targets for active source discovery."""
        targets = []
        
        # Get known good sources in region/topic
        if region in self.sources_by_region:
            for source in self.sources_by_region[region][:5]:  # Top 5
                if source.sitemap_endpoints:
                    targets.append({
                        'domain': source.domain,
                        'type': 'sitemap',
                        'urls': source.sitemap_endpoints
                    })
                elif source.primary_sections:
                    targets.append({
                        'domain': source.domain,
                        'type': 'section',
                        'urls': [f"https://{source.domain}{section}" for section in source.primary_sections]
                    })
        
        return targets