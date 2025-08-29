"""
Smart Source Selection - Intelligent ranking and selection based on topic/region relevance.
"""

import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class SourceScore:
    """Scoring components for a source."""
    domain: str
    base_priority: float
    topic_relevance: float
    regional_relevance: float
    freshness_history: float
    editorial_diversity: float
    total_score: float
    explanation: str


class SmartSelector:
    """Intelligently scores and selects sources based on context."""
    
    # Topic keyword mappings for relevance scoring
    TOPIC_KEYWORDS = {
        'elections': {
            'primary': ['election', 'vote', 'voting', 'poll', 'candidate', 'campaign', 
                       'ballot', 'electoral', 'democracy', 'referendum'],
            'secondary': ['politics', 'party', 'minister', 'president', 'parliament',
                         'congress', 'senate', 'governor', 'mayor'],
            'boost_domains': ['elections', 'politics', 'politi']
        },
        'economy': {
            'primary': ['economy', 'economic', 'gdp', 'inflation', 'recession', 'growth',
                       'market', 'stock', 'trade', 'finance', 'fiscal', 'monetary'],
            'secondary': ['business', 'company', 'industry', 'bank', 'investment',
                         'currency', 'dollar', 'euro', 'yen'],
            'boost_domains': ['business', 'finance', 'economic', 'markets', 'bloomberg']
        },
        'security': {
            'primary': ['security', 'military', 'defense', 'army', 'navy', 'force',
                       'terror', 'threat', 'conflict', 'war', 'peace'],
            'secondary': ['police', 'crime', 'border', 'intelligence', 'cyber',
                         'missile', 'nuclear', 'weapon'],
            'boost_domains': ['defense', 'military', 'security', 'strategic']
        },
        'climate': {
            'primary': ['climate', 'warming', 'carbon', 'emission', 'renewable',
                       'solar', 'wind', 'energy', 'fossil', 'greenhouse'],
            'secondary': ['environment', 'pollution', 'sustainable', 'green',
                         'conservation', 'biodiversity', 'weather'],
            'boost_domains': ['climate', 'environment', 'green', 'sustainable', 'energy']
        },
        'tech': {
            'primary': ['technology', 'tech', 'ai', 'artificial', 'digital', 'cyber',
                       'software', 'hardware', 'internet', 'data', 'algorithm'],
            'secondary': ['startup', 'innovation', 'platform', 'app', 'cloud',
                         'blockchain', 'crypto', 'quantum', 'robot'],
            'boost_domains': ['tech', 'wired', 'verge', 'ars', 'zdnet', 'cnet']
        },
        'politics': {
            'primary': ['politics', 'political', 'government', 'policy', 'legislation',
                       'parliament', 'congress', 'minister', 'president'],
            'secondary': ['party', 'opposition', 'coalition', 'cabinet', 'diplomatic',
                         'foreign', 'domestic', 'reform'],
            'boost_domains': ['politics', 'politi', 'gov', 'parliament']
        }
    }
    
    # Regional characteristics for scoring
    REGIONAL_TRAITS = {
        'asia': {
            'languages': ['en', 'zh', 'ja', 'ko', 'hi', 'ur', 'bn', 'id', 'th', 'vi'],
            'key_countries': ['IN', 'CN', 'JP', 'KR', 'PK', 'BD', 'ID', 'TH', 'MY', 'SG', 'PH', 'VN'],
            'regional_keywords': ['asia', 'asian', 'asean', 'apac', 'indo-pacific'],
            'boost_domains': ['asia', 'asean', 'hindu', 'dawn', 'scmp', 'nikkei', 'korea', 'jakarta']
        },
        'europe': {
            'languages': ['en', 'fr', 'de', 'es', 'it', 'nl', 'pt', 'pl', 'ru'],
            'key_countries': ['GB', 'FR', 'DE', 'ES', 'IT', 'NL', 'BE', 'CH', 'AT', 'PL'],
            'regional_keywords': ['europe', 'european', 'eu', 'brexit', 'eurozone'],
            'boost_domains': ['europe', 'eu', 'bbc', 'guardian', 'lemonde', 'spiegel', 'elpais']
        },
        'middle_east': {
            'languages': ['ar', 'en', 'he', 'fa', 'tr'],
            'key_countries': ['SA', 'AE', 'IL', 'IR', 'IQ', 'SY', 'JO', 'LB', 'EG', 'TR'],
            'regional_keywords': ['middle east', 'arab', 'gulf', 'levant', 'maghreb'],
            'boost_domains': ['aljazeera', 'arabiya', 'haaretz', 'dailystar', 'jordan', 'gulf']
        },
        'americas': {
            'languages': ['en', 'es', 'pt', 'fr'],
            'key_countries': ['US', 'CA', 'MX', 'BR', 'AR', 'CO', 'CL', 'PE', 'VE'],
            'regional_keywords': ['america', 'americas', 'latino', 'caribbean', 'nafta'],
            'boost_domains': ['cnn', 'nytimes', 'washingtonpost', 'wsj', 'globo', 'clarin', 'reforma']
        },
        'africa': {
            'languages': ['en', 'fr', 'ar', 'sw', 'pt'],
            'key_countries': ['NG', 'ZA', 'EG', 'ET', 'KE', 'GH', 'TZ', 'DZ', 'MA'],
            'regional_keywords': ['africa', 'african', 'sahara', 'sahel', 'sub-saharan'],
            'boost_domains': ['africa', 'allafrica', 'dailymaverick', 'nation', 'guardian.ng']
        }
    }
    
    def __init__(self):
        self.cache = {}
    
    def score_source(self, 
                     source: Dict,
                     topic: Optional[str] = None,
                     region: Optional[str] = None,
                     context: Optional[Dict] = None) -> SourceScore:
        """
        Score a source based on relevance to topic and region.
        
        Args:
            source: Source dictionary with domain, topics, region, etc.
            topic: Target topic
            region: Target region
            context: Additional context (e.g., current events, trending topics)
        
        Returns:
            SourceScore with detailed scoring breakdown
        """
        
        domain = source.get('domain', '')
        source_topics = source.get('topics', [])
        source_region = source.get('region', '')
        source_priority = source.get('priority', 0.5)
        
        # Base priority from catalog
        base_score = source_priority
        
        # Topic relevance scoring
        topic_score = self._score_topic_relevance(
            domain, source_topics, topic
        ) if topic else 0.5
        
        # Regional relevance scoring
        regional_score = self._score_regional_relevance(
            domain, source_region, region
        ) if region else 0.5
        
        # Historical freshness (from past performance)
        freshness_score = source.get('freshness_score', 0.5)
        
        # Editorial diversity bonus
        editorial_family = source.get('editorial_family', 'unknown')
        diversity_score = self._score_editorial_diversity(editorial_family)
        
        # Calculate weighted total
        weights = {
            'base': 0.2,
            'topic': 0.35,
            'regional': 0.25,
            'freshness': 0.1,
            'diversity': 0.1
        }
        
        total = (
            base_score * weights['base'] +
            topic_score * weights['topic'] +
            regional_score * weights['regional'] +
            freshness_score * weights['freshness'] +
            diversity_score * weights['diversity']
        )
        
        # Generate explanation
        explanation = self._generate_explanation(
            domain, topic_score, regional_score, editorial_family
        )
        
        return SourceScore(
            domain=domain,
            base_priority=base_score,
            topic_relevance=topic_score,
            regional_relevance=regional_score,
            freshness_history=freshness_score,
            editorial_diversity=diversity_score,
            total_score=total,
            explanation=explanation
        )
    
    def _score_topic_relevance(self, domain: str, source_topics: List[str], target_topic: str) -> float:
        """Score how relevant a source is to the target topic."""
        
        if not target_topic:
            return 0.5
        
        score = 0.0
        topic_config = self.TOPIC_KEYWORDS.get(target_topic, {})
        
        # Check if topic is explicitly listed
        if target_topic in source_topics:
            score += 0.5
        
        # Check for related topics
        primary_keywords = topic_config.get('primary', [])
        for topic in source_topics:
            if any(keyword in topic.lower() for keyword in primary_keywords):
                score += 0.3
                break
        
        # Domain name bonus
        boost_domains = topic_config.get('boost_domains', [])
        domain_lower = domain.lower()
        if any(boost in domain_lower for boost in boost_domains):
            score += 0.2
        
        return min(1.0, score)
    
    def _score_regional_relevance(self, domain: str, source_region: str, target_region: str) -> float:
        """Score how relevant a source is to the target region."""
        
        if not target_region:
            return 0.5
        
        score = 0.0
        region_config = self.REGIONAL_TRAITS.get(target_region, {})
        
        # Direct region match
        if source_region == target_region:
            score += 0.5
        elif source_region == 'global':
            score += 0.3  # Global sources are somewhat relevant
        
        # Domain name bonus
        boost_domains = region_config.get('boost_domains', [])
        domain_lower = domain.lower()
        if any(boost in domain_lower for boost in boost_domains):
            score += 0.3
        
        # Regional keywords in domain
        regional_keywords = region_config.get('regional_keywords', [])
        if any(keyword in domain_lower for keyword in regional_keywords):
            score += 0.2
        
        return min(1.0, score)
    
    def _score_editorial_diversity(self, editorial_family: str) -> float:
        """Score based on editorial family for diversity."""
        
        # Prefer certain editorial families for quality
        quality_scores = {
            'wire': 0.9,           # Wire services are high quality
            'public_broadcaster': 0.85,  # Public broadcasters are reliable
            'broadsheet': 0.8,     # Quality newspapers
            'broadcaster': 0.7,    # TV/Radio news
            'state_media': 0.5,    # State media can be biased
            'tabloid': 0.4,        # Tabloids are less reliable
            'unknown': 0.5
        }
        
        return quality_scores.get(editorial_family, 0.5)
    
    def _generate_explanation(self, domain: str, topic_score: float, 
                             regional_score: float, editorial_family: str) -> str:
        """Generate human-readable explanation of scoring."""
        
        parts = []
        
        if topic_score > 0.7:
            parts.append("highly relevant to topic")
        elif topic_score > 0.4:
            parts.append("moderately relevant to topic")
        
        if regional_score > 0.7:
            parts.append("strong regional focus")
        elif regional_score > 0.4:
            parts.append("regional coverage")
        
        if editorial_family in ['wire', 'public_broadcaster']:
            parts.append(f"trusted {editorial_family.replace('_', ' ')}")
        
        return f"{domain}: {', '.join(parts) if parts else 'general source'}"
    
    def rank_sources(self, 
                     sources: List[Dict],
                     topic: Optional[str] = None,
                     region: Optional[str] = None,
                     max_sources: int = 50) -> List[Tuple[Dict, SourceScore]]:
        """
        Rank sources by relevance and return top selections.
        
        Returns:
            List of (source, score) tuples, sorted by score
        """
        
        scored_sources = []
        
        for source in sources:
            score = self.score_source(source, topic, region)
            scored_sources.append((source, score))
        
        # Sort by total score descending
        scored_sources.sort(key=lambda x: x[1].total_score, reverse=True)
        
        # Log top selections
        logger.info(f"Top 5 sources for {topic}/{region}:")
        for source, score in scored_sources[:5]:
            logger.info(f"  {score.explanation} (score: {score.total_score:.2f})")
        
        return scored_sources[:max_sources]
    
    def get_fetch_limit(self, source_score: float, base_limit: int = 25) -> int:
        """
        Determine how many articles to fetch from a source based on its score.
        Higher scoring sources get more articles.
        """
        
        if source_score > 0.8:
            return int(base_limit * 1.5)  # 150% for excellent sources
        elif source_score > 0.6:
            return base_limit  # 100% for good sources
        elif source_score > 0.4:
            return int(base_limit * 0.7)  # 70% for average sources
        else:
            return int(base_limit * 0.5)  # 50% for poor sources