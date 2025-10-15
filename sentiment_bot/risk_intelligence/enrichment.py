#!/usr/bin/env python3
"""
Enrichment Layer for Risk Intelligence
Text processing: NER, embeddings, taxonomy, language detection
"""

import re
from typing import Dict, List, Optional, Tuple, Set
from datetime import datetime, timezone
import logging

# Try to import NLP libraries (graceful fallback)
try:
    import spacy
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False

logger = logging.getLogger(__name__)


class TextEnricher:
    """Text enrichment and entity extraction"""

    def __init__(self):
        self.nlp = None
        self.embedder = None

        # Load spaCy model if available
        if SPACY_AVAILABLE:
            try:
                self.nlp = spacy.load("en_core_web_sm")
                logger.info("Loaded spaCy model for NER")
            except Exception as e:
                logger.warning(f"Could not load spaCy model: {e}")

        # Load embedding model if available
        if EMBEDDINGS_AVAILABLE:
            try:
                self.embedder = SentenceTransformer('all-MiniLM-L6-v2')
                logger.info("Loaded sentence transformer for embeddings")
            except Exception as e:
                logger.warning(f"Could not load embedding model: {e}")

        # Taxonomy categories
        self.taxonomy = {
            'macro': ['gdp', 'inflation', 'interest rate', 'unemployment', 'recession', 'growth', 'monetary policy'],
            'regulatory': ['regulation', 'compliance', 'sanction', 'policy', 'law', 'ban', 'restriction'],
            'supply_chain': ['supply chain', 'logistics', 'shortage', 'disruption', 'inventory', 'shipping'],
            'brand': ['reputation', 'scandal', 'boycott', 'controversy', 'backlash', 'crisis'],
            'market': ['stock', 'equity', 'commodity', 'forex', 'volatility', 'crash', 'rally'],
            'geopolitical': ['war', 'conflict', 'tension', 'sanction', 'embargo', 'dispute', 'election'],
            'energy': ['oil', 'gas', 'energy', 'opec', 'renewable', 'crude', 'pipeline'],
            'tech': ['technology', 'ai', 'cyber', 'data breach', 'software', 'hardware', 'semiconductor'],
            'climate': ['climate', 'weather', 'disaster', 'flood', 'drought', 'hurricane', 'emission'],
            'finance': ['banking', 'credit', 'debt', 'default', 'liquidity', 'capital', 'investment']
        }

    def extract_entities(self, text: str) -> Dict[str, List[str]]:
        """Extract named entities from text"""
        entities = {
            'orgs': [],
            'places': [],
            'persons': [],
            'money': [],
            'dates': []
        }

        if not self.nlp:
            # Fallback: simple pattern matching
            entities['orgs'] = self._extract_orgs_simple(text)
            entities['places'] = self._extract_places_simple(text)
            return entities

        # Use spaCy NER
        doc = self.nlp(text[:10000])  # Limit length
        for ent in doc.ents:
            if ent.label_ == 'ORG':
                entities['orgs'].append(ent.text)
            elif ent.label_ in ['GPE', 'LOC']:
                entities['places'].append(ent.text)
            elif ent.label_ == 'PERSON':
                entities['persons'].append(ent.text)
            elif ent.label_ == 'MONEY':
                entities['money'].append(ent.text)
            elif ent.label_ == 'DATE':
                entities['dates'].append(ent.text)

        # Deduplicate
        for key in entities:
            entities[key] = list(set(entities[key]))[:10]  # Top 10

        return entities

    def _extract_orgs_simple(self, text: str) -> List[str]:
        """Simple org extraction without spaCy"""
        # Common org suffixes
        patterns = [
            r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:Inc|Corp|Ltd|LLC|AG|SA|GmbH)',
            r'\b([A-Z]{2,})\b'  # Acronyms
        ]
        orgs = []
        for pattern in patterns:
            matches = re.findall(pattern, text)
            orgs.extend(matches)
        return list(set(orgs))[:10]

    def _extract_places_simple(self, text: str) -> List[str]:
        """Simple place extraction"""
        # Common countries/cities
        places = ['United States', 'China', 'India', 'UK', 'Germany', 'France', 'Japan',
                 'Russia', 'Brazil', 'Canada', 'Mexico', 'Australia', 'South Korea',
                 'New York', 'London', 'Beijing', 'Tokyo', 'Paris', 'Berlin', 'Moscow']

        found = []
        text_lower = text.lower()
        for place in places:
            if place.lower() in text_lower:
                found.append(place)

        return found

    def categorize_text(self, text: str, title: str = "") -> List[str]:
        """Categorize text into taxonomy categories"""
        combined = f"{title} {text}".lower()
        categories = []

        for category, keywords in self.taxonomy.items():
            for keyword in keywords:
                if keyword in combined:
                    categories.append(category)
                    break

        # Default category if none found
        if not categories:
            categories = ['general']

        return list(set(categories))

    def generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate text embedding for similarity search"""
        if not self.embedder:
            return None

        try:
            # Truncate to 512 tokens
            text_truncated = text[:2000]
            embedding = self.embedder.encode(text_truncated)
            return embedding.tolist()
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            return None

    def detect_language(self, text: str) -> str:
        """Detect text language (simple heuristic)"""
        # Simple: check for common English words
        english_words = ['the', 'is', 'at', 'which', 'on', 'and', 'a', 'an', 'as', 'are']
        sample = text.lower()[:500]
        english_count = sum(1 for word in english_words if f' {word} ' in sample)

        if english_count >= 3:
            return 'en'
        return 'unknown'

    def extract_tags(self, text: str, title: str = "", max_tags: int = 10) -> List[str]:
        """Extract relevant tags from text"""
        tags = set()

        # Extract from title
        title_words = re.findall(r'\b[A-Z][a-z]+\b', title)
        tags.update(title_words)

        # Extract entities
        entities = self.extract_entities(text)
        for entity_list in entities.values():
            tags.update(entity_list[:3])

        # Extract key terms
        key_terms = self._extract_key_terms(text)
        tags.update(key_terms)

        # Clean and limit
        tags = [tag for tag in tags if len(tag) > 2 and len(tag) < 30]
        return list(tags)[:max_tags]

    def _extract_key_terms(self, text: str) -> Set[str]:
        """Extract key terms from text"""
        # Simple frequency-based extraction
        words = re.findall(r'\b[A-Z][a-z]{2,}\b', text)
        # Count occurrences
        from collections import Counter
        word_counts = Counter(words)
        # Top 5 most common
        return set([word for word, count in word_counts.most_common(5) if count > 1])

    def compute_risk_indicators(self, text: str) -> Dict[str, float]:
        """Compute risk indicators from text"""
        text_lower = text.lower()

        # Risk keyword categories
        risk_keywords = {
            'crisis': ['crisis', 'crash', 'collapse', 'failure', 'disaster'],
            'negative': ['decline', 'fall', 'drop', 'decrease', 'loss', 'negative'],
            'uncertainty': ['uncertain', 'volatile', 'unpredictable', 'risk', 'concern'],
            'conflict': ['war', 'conflict', 'tension', 'dispute', 'clash'],
            'urgency': ['urgent', 'immediate', 'critical', 'emergency', 'alert']
        }

        indicators = {}
        for category, keywords in risk_keywords.items():
            count = sum(1 for keyword in keywords if keyword in text_lower)
            # Normalize to 0-1
            indicators[category] = min(count / 3.0, 1.0)

        return indicators

    def enrich_document(self, title: str, text: str, source: str = "") -> Dict:
        """Full enrichment pipeline"""
        enriched = {
            'title': title,
            'text': text[:5000],  # Truncate
            'source': source,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'language': self.detect_language(text),
            'entities': self.extract_entities(text),
            'categories': self.categorize_text(text, title),
            'tags': self.extract_tags(text, title),
            'risk_indicators': self.compute_risk_indicators(text),
            'char_count': len(text),
            'word_count': len(text.split())
        }

        # Optional embedding
        embedding = self.generate_embedding(f"{title}. {text[:500]}")
        if embedding:
            enriched['embedding'] = embedding

        return enriched


class RiskScorer:
    """Compute risk scores for signals"""

    def __init__(self):
        self.source_trust_scores = {
            'query_agent': 0.7,
            'monitor_agent': 0.8,
            'forecast_agent': 0.85,
            'summarizer_agent': 0.75,
            'partner_webhook': 0.9,
            'manual': 1.0
        }

    def compute_risk_score(self, enriched: Dict, confidence: float,
                          source: str) -> float:
        """
        Compute 0-100 risk score
        Factors: risk indicators, source trust, confidence, category
        """
        # Base score from risk indicators
        indicators = enriched.get('risk_indicators', {})
        indicator_score = sum(indicators.values()) / max(len(indicators), 1)

        # Source trust
        source_trust = self.source_trust_scores.get(source, 0.5)

        # Category severity weights
        category_weights = {
            'geopolitical': 0.9,
            'market': 0.85,
            'regulatory': 0.8,
            'macro': 0.75,
            'supply_chain': 0.7,
            'brand': 0.6,
            'general': 0.5
        }

        categories = enriched.get('categories', ['general'])
        category_score = max([category_weights.get(cat, 0.5) for cat in categories])

        # Weighted combination
        risk_score = (
            indicator_score * 40 +  # 40% from text indicators
            confidence * 30 +        # 30% from model confidence
            source_trust * 20 +      # 20% from source trust
            category_score * 10      # 10% from category
        )

        return min(risk_score, 100.0)

    def compute_impact(self, risk_score: float) -> str:
        """Compute impact level from risk score"""
        if risk_score >= 80:
            return 'critical'
        elif risk_score >= 60:
            return 'high'
        elif risk_score >= 40:
            return 'medium'
        else:
            return 'low'


# Singleton instances
_enricher_instance: Optional[TextEnricher] = None
_scorer_instance: Optional[RiskScorer] = None

def get_enricher() -> TextEnricher:
    """Get singleton enricher"""
    global _enricher_instance
    if _enricher_instance is None:
        _enricher_instance = TextEnricher()
    return _enricher_instance

def get_scorer() -> RiskScorer:
    """Get singleton scorer"""
    global _scorer_instance
    if _scorer_instance is None:
        _scorer_instance = RiskScorer()
    return _scorer_instance
