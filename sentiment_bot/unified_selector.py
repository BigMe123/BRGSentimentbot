"""
Unified Source Selection System
Standardizes selection across all modes with country, region, topic, and keyword support
"""

from typing import List, Dict, Set, Optional, Any
from dataclasses import dataclass
from .region_country_mapper import get_region_mapper
from .master_sources import get_master_sources
import re


@dataclass
class SelectionCriteria:
    """Unified selection criteria for all modes"""
    regions: Optional[List[str]] = None
    countries: Optional[List[str]] = None
    topics: Optional[List[str]] = None
    keywords: Optional[List[str]] = None
    custom_question: Optional[str] = None
    min_sources: int = 10
    max_sources: int = 100
    priority_threshold: float = 0.5
    language: Optional[str] = "en"


class UnifiedSourceSelector:
    """Unified source selection that works consistently across all modes"""

    def __init__(self):
        self.region_mapper = get_region_mapper()
        self.master_sources = get_master_sources()

    def select_sources(self, criteria: SelectionCriteria) -> List[Dict]:
        """
        Select sources based on unified criteria
        Works the same way across all modes (CLI, API, interactive)
        """
        selected = []

        # Step 1: Expand regions to countries
        target_countries = self._expand_countries(criteria)

        # Step 2: Get all sources from master list
        all_sources = self.master_sources.get_all_sources()

        # Step 3: Filter by country
        if target_countries:
            filtered_sources = self._filter_by_countries(all_sources, target_countries)
        else:
            filtered_sources = all_sources

        # Step 4: Filter by topics
        if criteria.topics:
            filtered_sources = self._filter_by_topics(filtered_sources, criteria.topics)

        # Step 5: Filter by keywords (if custom question)
        if criteria.custom_question or criteria.keywords:
            filtered_sources = self._filter_by_relevance(
                filtered_sources,
                criteria.custom_question,
                criteria.keywords
            )

        # Step 6: Filter by priority
        filtered_sources = [
            s for s in filtered_sources
            if s.get('priority', 0) >= criteria.priority_threshold
        ]

        # Step 7: Filter by language
        if criteria.language:
            filtered_sources = [
                s for s in filtered_sources
                if s.get('language', 'en') == criteria.language
            ]

        # Step 8: Sort by priority and relevance
        filtered_sources = self._rank_sources(filtered_sources, criteria)

        # Step 9: Apply limits
        if len(filtered_sources) > criteria.max_sources:
            selected = filtered_sources[:criteria.max_sources]
        else:
            selected = filtered_sources

        # Step 10: Ensure minimum sources
        if len(selected) < criteria.min_sources:
            # Add more general sources
            additional = self._add_fallback_sources(
                all_sources,
                selected,
                criteria.min_sources - len(selected)
            )
            selected.extend(additional)

        return selected

    def _expand_countries(self, criteria: SelectionCriteria) -> Set[str]:
        """Expand regions to countries"""
        countries = set()

        # Add explicitly selected countries
        if criteria.countries:
            countries.update(criteria.countries)

        # Expand regions to countries
        if criteria.regions:
            for region in criteria.regions:
                region_countries = self.region_mapper.get_countries_by_region(region)
                countries.update(region_countries)

        return countries

    def _filter_by_countries(self, sources: List[Any], countries: Set[str]) -> List[Any]:
        """Filter sources by country"""
        filtered = []

        for source in sources:
            # Handle both dict and object types
            if hasattr(source, 'country'):
                source_country = source.country
            elif isinstance(source, dict):
                source_country = source.get('country', 'Global')
            else:
                source_country = 'Global'

            # Include if country matches or source is global
            if source_country in countries or source_country == 'Global':
                filtered.append(source)

        return filtered

    def _filter_by_topics(self, sources: List[Any], topics: List[str]) -> List[Any]:
        """Filter sources by topics"""
        filtered = []

        for source in sources:
            # Handle both dict and object types
            if hasattr(source, 'topics'):
                source_topics = source.topics or []
            elif isinstance(source, dict):
                source_topics = source.get('topics', [])
            else:
                source_topics = []

            # Check if any topic matches
            for topic in topics:
                topic_lower = topic.lower()
                for source_topic in source_topics:
                    if topic_lower in source_topic.lower() or source_topic.lower() in topic_lower:
                        filtered.append(source)
                        break

        return filtered

    def _filter_by_relevance(self, sources: List[Any],
                            question: Optional[str],
                            keywords: Optional[List[str]]) -> List[Any]:
        """Filter sources by relevance to question/keywords"""
        filtered = []

        # Extract keywords from question if provided
        if question:
            question_keywords = self._extract_keywords(question)
            if keywords:
                keywords = list(set(keywords + question_keywords))
            else:
                keywords = question_keywords

        if not keywords:
            return sources

        for source in sources:
            # Check domain, name, and topics for keyword matches
            if hasattr(source, 'domain'):
                domain = source.domain or ''
                name = source.name or ''
                topics = source.topics or []
            elif isinstance(source, dict):
                domain = source.get('domain', '')
                name = source.get('name', '')
                topics = source.get('topics', [])
            else:
                domain = ''
                name = ''
                topics = []

            source_text = ' '.join([domain, name, ' '.join(topics)]).lower()

            for keyword in keywords:
                if keyword.lower() in source_text:
                    filtered.append(source)
                    break

        # If too few matches, return all sources
        if len(filtered) < 5:
            return sources

        return filtered

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text"""
        # Remove common words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at',
                     'to', 'for', 'of', 'with', 'by', 'from', 'as', 'is',
                     'was', 'are', 'were', 'been', 'be', 'will', 'would',
                     'could', 'should', 'may', 'might', 'what', 'how', 'why',
                     'when', 'where', 'who', 'which'}

        # Extract words
        words = re.findall(r'\b[a-z]+\b', text.lower())

        # Filter stop words and short words
        keywords = [w for w in words if w not in stop_words and len(w) > 3]

        # Get unique keywords
        return list(set(keywords))

    def _rank_sources(self, sources: List[Any], criteria: SelectionCriteria) -> List[Any]:
        """Rank sources by relevance and priority"""

        def score_source(source):
            score = 0.0

            # Handle both dict and object types
            if hasattr(source, 'priority'):
                priority = source.priority or 0.5
                country = source.country
                topics = source.topics or []
                rss_endpoints = getattr(source, 'rss_endpoints', None)
            elif isinstance(source, dict):
                priority = source.get('priority', 0.5)
                country = source.get('country', 'Global')
                topics = source.get('topics', [])
                rss_endpoints = source.get('rss_endpoints')
            else:
                priority = 0.5
                country = 'Global'
                topics = []
                rss_endpoints = None

            # Priority score
            score += priority * 2

            # Country match score
            if criteria.countries:
                if country in criteria.countries:
                    score += 1.0

            # Topic match score
            if criteria.topics:
                for topic in criteria.topics:
                    if any(topic.lower() in st.lower() for st in topics):
                        score += 0.5

            # Has RSS endpoints
            if rss_endpoints:
                score += 0.3

            return score

        # Sort by score
        sources_with_scores = [(s, score_source(s)) for s in sources]
        sources_with_scores.sort(key=lambda x: x[1], reverse=True)

        return [s for s, _ in sources_with_scores]

    def _add_fallback_sources(self, all_sources: List[Any],
                             selected: List[Any],
                             needed: int) -> List[Any]:
        """Add fallback sources to meet minimum requirement"""
        # Get selected domains
        selected_domains = set()
        for s in selected:
            if hasattr(s, 'domain'):
                selected_domains.add(s.domain)
            elif isinstance(s, dict):
                selected_domains.add(s.get('domain'))

        # Get high-priority global sources
        fallback = []
        for source in all_sources:
            # Get domain
            if hasattr(source, 'domain'):
                domain = source.domain
                country = source.country
                priority = source.priority or 0
            elif isinstance(source, dict):
                domain = source.get('domain')
                country = source.get('country', 'Global')
                priority = source.get('priority', 0)
            else:
                continue

            if domain not in selected_domains:
                if country == 'Global' and priority > 0.8:
                    fallback.append(source)
                    if len(fallback) >= needed:
                        break

        return fallback

    def analyze_custom_question(self, question: str) -> Dict[str, Any]:
        """
        Analyze a custom question and return structured analysis
        """
        # Extract entities and topics from question
        keywords = self._extract_keywords(question)

        # Detect regions/countries mentioned
        mentioned_countries = []
        mentioned_regions = []

        for region in ['asia', 'europe', 'africa', 'americas', 'middle_east']:
            if region.replace('_', ' ') in question.lower():
                mentioned_regions.append(region)

        # Detect topics
        detected_topics = []
        topic_keywords = {
            'economy': ['gdp', 'growth', 'recession', 'economy', 'economic'],
            'trade': ['trade', 'import', 'export', 'tariff', 'customs'],
            'inflation': ['inflation', 'prices', 'cpi', 'cost'],
            'employment': ['jobs', 'employment', 'unemployment', 'labor'],
            'markets': ['stock', 'market', 'equity', 'bonds', 'trading'],
            'currency': ['dollar', 'euro', 'yen', 'currency', 'forex', 'fx'],
            'commodities': ['oil', 'gold', 'copper', 'wheat', 'commodity'],
            'technology': ['tech', 'ai', 'software', 'digital', 'cyber'],
            'energy': ['energy', 'oil', 'gas', 'renewable', 'solar', 'wind'],
            'climate': ['climate', 'carbon', 'emissions', 'warming', 'environmental'],
        }

        for topic, topic_words in topic_keywords.items():
            if any(word in question.lower() for word in topic_words):
                detected_topics.append(topic)

        return {
            'question': question,
            'keywords': keywords,
            'detected_topics': detected_topics,
            'detected_regions': mentioned_regions,
            'detected_countries': mentioned_countries,
            'suggested_criteria': SelectionCriteria(
                regions=mentioned_regions if mentioned_regions else None,
                countries=mentioned_countries if mentioned_countries else None,
                topics=detected_topics if detected_topics else None,
                keywords=keywords[:10],  # Top 10 keywords
                custom_question=question
            )
        }

    def generate_report(self, question: str, articles: List[Dict],
                       analysis_results: Dict) -> Dict[str, Any]:
        """
        Generate structured report for custom question analysis
        """
        report = {
            'question': question,
            'timestamp': self._get_timestamp(),
            'summary': {
                'total_articles': len(articles),
                'sentiment_score': analysis_results.get('sentiment_score', 0),
                'confidence': analysis_results.get('confidence', 0),
            },
            'key_findings': [],
            'sentiment_breakdown': analysis_results.get('sentiment', {}),
            'top_themes': [],
            'geographic_distribution': {},
            'recommendations': [],
            'data_sources': []
        }

        # Extract key findings
        if 'key_insights' in analysis_results:
            for insight in analysis_results['key_insights'][:5]:
                report['key_findings'].append({
                    'finding': insight.get('title', ''),
                    'sentiment': insight.get('sentiment', ''),
                    'confidence': insight.get('score', 0)
                })

        # Extract themes
        if 'top_topics' in analysis_results:
            report['top_themes'] = analysis_results['top_topics'][:10]

        # Geographic distribution
        country_counts = {}
        for article in articles:
            country = article.get('country', 'Unknown')
            country_counts[country] = country_counts.get(country, 0) + 1
        report['geographic_distribution'] = country_counts

        # Generate recommendations based on sentiment
        sentiment_score = analysis_results.get('sentiment_score', 0)
        if sentiment_score > 20:
            report['recommendations'].append("Positive sentiment detected - consider bullish positioning")
        elif sentiment_score < -20:
            report['recommendations'].append("Negative sentiment detected - consider defensive positioning")
        else:
            report['recommendations'].append("Neutral sentiment - maintain balanced approach")

        # Add economic predictions if available
        if 'economic_predictions' in analysis_results:
            report['economic_outlook'] = analysis_results['economic_predictions']

        # Add market analysis if available
        if 'market_analysis' in analysis_results:
            report['market_signals'] = analysis_results['market_analysis']

        # List data sources used
        source_set = set()
        for article in articles[:50]:  # Sample
            source = article.get('domain', article.get('source', 'Unknown'))
            source_set.add(source)
        report['data_sources'] = list(source_set)[:20]

        return report

    def _get_timestamp(self) -> str:
        """Get current timestamp"""
        from datetime import datetime
        return datetime.now().isoformat()


# Singleton instance
_selector_instance = None


def get_unified_selector() -> UnifiedSourceSelector:
    """Get singleton instance of unified selector"""
    global _selector_instance
    if _selector_instance is None:
        _selector_instance = UnifiedSourceSelector()
    return _selector_instance


# Export
__all__ = ['UnifiedSourceSelector', 'SelectionCriteria', 'get_unified_selector']