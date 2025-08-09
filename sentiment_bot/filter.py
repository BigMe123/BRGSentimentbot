"""
Article relevance filtering module.
Ensures articles match specified region and topic criteria.
"""
from typing import Optional, Dict, List, Tuple
import re
from langdetect import detect, LangDetectException
import logging

logger = logging.getLogger(__name__)

# Region-specific keywords and entities
REGION_KEYWORDS: Dict[str, List[str]] = {
    "asia": [
        "china", "india", "japan", "south korea", "north korea", "indonesia", 
        "asia", "asian", "beijing", "tokyo", "delhi", "seoul", "jakarta",
        "thailand", "vietnam", "philippines", "singapore", "malaysia",
        "pakistan", "bangladesh", "myanmar", "cambodia", "laos",
        "taiwan", "hong kong", "shanghai", "mumbai", "bangkok"
    ],
    "europe": [
        "germany", "france", "uk", "united kingdom", "britain", "europe", "eu",
        "european union", "italy", "spain", "poland", "netherlands", "belgium",
        "sweden", "norway", "denmark", "finland", "austria", "switzerland",
        "portugal", "greece", "czech", "hungary", "romania", "bulgaria",
        "london", "paris", "berlin", "rome", "madrid", "warsaw", "brussels"
    ],
    "middle_east": [
        "israel", "palestine", "iran", "iraq", "syria", "lebanon", "jordan",
        "saudi arabia", "uae", "emirates", "dubai", "qatar", "kuwait",
        "yemen", "oman", "bahrain", "middle east", "arab", "persian gulf",
        "jerusalem", "tehran", "baghdad", "damascus", "riyadh", "doha"
    ],
    "africa": [
        "africa", "african", "nigeria", "egypt", "south africa", "kenya",
        "ethiopia", "ghana", "morocco", "algeria", "tunisia", "libya",
        "zimbabwe", "uganda", "sudan", "congo", "tanzania", "mozambique",
        "cairo", "lagos", "johannesburg", "nairobi", "addis ababa", "accra"
    ],
    "americas": [
        "usa", "united states", "america", "american", "canada", "mexico", "brazil",
        "argentina", "chile", "colombia", "peru", "venezuela", "ecuador",
        "bolivia", "paraguay", "uruguay", "washington", "new york", "ottawa",
        "mexico city", "brasilia", "buenos aires", "santiago", "bogota",
        "silicon valley", "san francisco", "los angeles", "chicago", "boston",
        "seattle", "microsoft", "google", "openai", "tech stocks", "wall street"
    ],
    "oceania": [
        "australia", "new zealand", "papua new guinea", "fiji", "samoa",
        "tonga", "vanuatu", "solomon islands", "sydney", "melbourne",
        "auckland", "wellington", "canberra", "brisbane", "perth"
    ]
}

# Topic-specific keywords
TOPIC_KEYWORDS: Dict[str, List[str]] = {
    "elections": [
        "vote", "voting", "election", "electoral", "poll", "polling", "ballot",
        "campaign", "candidate", "parliament", "congress", "senate", "president",
        "prime minister", "democracy", "referendum", "constituency", "party",
        "opposition", "incumbent", "coalition", "debate", "primary", "caucus"
    ],
    "defense": [
        "military", "army", "navy", "air force", "marine", "missile", "defense",
        "defence", "weapon", "warfare", "soldier", "troops", "battalion", "war",
        "conflict", "security", "strategic", "tactical", "combat", "armed forces",
        "pentagon", "nato", "alliance", "submarine", "fighter jet", "drone"
    ],
    "economy": [
        "economy", "economic", "gdp", "inflation", "recession", "growth",
        "market", "stock", "bond", "currency", "dollar", "euro", "yen",
        "trade", "export", "import", "tariff", "investment", "finance",
        "bank", "central bank", "federal reserve", "interest rate", "unemployment"
    ],
    "technology": [
        "technology", "tech", "ai", "artificial intelligence", "machine learning",
        "software", "hardware", "internet", "cyber", "digital", "data",
        "algorithm", "blockchain", "cryptocurrency", "quantum", "5g", "6g",
        "silicon valley", "startup", "innovation", "research", "development"
    ],
    "climate": [
        "climate", "climate change", "global warming", "carbon", "emission",
        "renewable", "solar", "wind", "energy", "fossil fuel", "environment",
        "pollution", "greenhouse", "paris agreement", "cop", "sustainability",
        "electric vehicle", "ev", "green", "conservation", "biodiversity"
    ],
    "health": [
        "health", "healthcare", "medical", "medicine", "hospital", "doctor",
        "vaccine", "vaccination", "pandemic", "epidemic", "virus", "disease",
        "treatment", "therapy", "pharmaceutical", "drug", "fda", "who",
        "clinical trial", "diagnosis", "patient", "public health", "mental health"
    ]
}

def check_language(text: str) -> bool:
    """Check if text is in English."""
    try:
        lang = detect(text[:1000])  # Check first 1000 chars for speed
        return lang == 'en'
    except LangDetectException:
        # If detection fails, assume English and continue
        return True
    except Exception as e:
        logger.debug(f"Language detection error: {e}")
        return True

def count_keyword_matches(text: str, keywords: List[str]) -> int:
    """Count keyword matches in text (case-insensitive)."""
    text_lower = text.lower()
    count = 0
    for keyword in keywords:
        # Use word boundaries for more accurate matching
        pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
        count += len(re.findall(pattern, text_lower))
    return count

def calculate_relevance_score(
    text: str, 
    title: str, 
    region_keywords: List[str], 
    topic_keywords: List[str]
) -> Tuple[float, float, float]:
    """
    Calculate relevance scores for region and topic.
    Returns (combined_score, region_score, topic_score)
    """
    # Combine title and text, but weight title more heavily
    full_text = f"{title} {title} {title} {text}"  # Title appears 3x for weight
    
    # Count matches
    region_matches = count_keyword_matches(full_text, region_keywords)
    topic_matches = count_keyword_matches(full_text, topic_keywords)
    
    # Normalize by text length (per 1000 chars)
    text_length = max(len(full_text), 1)
    region_score = (region_matches * 1000) / text_length
    topic_score = (topic_matches * 1000) / text_length
    
    # Combined score (multiplicative to require both)
    combined_score = region_score * topic_score
    
    return combined_score, region_score, topic_score

def is_relevant(
    article_text: str, 
    article_title: str, 
    region: str, 
    topic: str,
    min_region_score: float = 0.5,
    min_topic_score: float = 0.5,
    min_combined_score: float = 0.25
) -> Tuple[bool, Optional[str], Dict[str, float]]:
    """
    Check if article is relevant to specified region and topic.
    
    Returns:
        (is_relevant, rejection_reason, scores_dict)
    """
    scores = {"region": 0.0, "topic": 0.0, "combined": 0.0}
    
    # 1. Language check
    if not check_language(article_text):
        return False, "Not English", scores
    
    # 2. Get keywords for region and topic
    region_lower = region.lower()
    topic_lower = topic.lower()
    
    region_kw = REGION_KEYWORDS.get(region_lower, [region_lower])
    topic_kw = TOPIC_KEYWORDS.get(topic_lower, [topic_lower])
    
    # 3. Calculate relevance scores
    combined_score, region_score, topic_score = calculate_relevance_score(
        article_text, article_title, region_kw, topic_kw
    )
    
    scores = {
        "region": region_score,
        "topic": topic_score,
        "combined": combined_score
    }
    
    # 4. Check thresholds
    if region_score < min_region_score:
        return False, f"Low region relevance ({region_score:.2f} < {min_region_score})", scores
    
    if topic_score < min_topic_score:
        return False, f"Low topic relevance ({topic_score:.2f} < {min_topic_score})", scores
    
    if combined_score < min_combined_score:
        return False, f"Low combined relevance ({combined_score:.2f} < {min_combined_score})", scores
    
    # 5. Additional validation for false positives
    # Check for sports false positives (e.g., "Asia Cup" in cricket)
    sports_keywords = ["cup", "championship", "tournament", "league", "match", "game", "sport"]
    if any(sport in article_title.lower() for sport in sports_keywords):
        # Require higher relevance scores for sports articles
        if region_score < min_region_score * 2 or topic_score < min_topic_score * 2:
            return False, "Sports article with weak region/topic relevance", scores
    
    return True, None, scores

def get_supported_regions() -> List[str]:
    """Get list of supported regions."""
    return list(REGION_KEYWORDS.keys())

def get_supported_topics() -> List[str]:
    """Get list of supported topics."""
    return list(TOPIC_KEYWORDS.keys())

def add_custom_keywords(region: str, keywords: List[str]) -> None:
    """Add custom keywords for a region."""
    region_lower = region.lower()
    if region_lower not in REGION_KEYWORDS:
        REGION_KEYWORDS[region_lower] = []
    REGION_KEYWORDS[region_lower].extend(keywords)

def add_custom_topic_keywords(topic: str, keywords: List[str]) -> None:
    """Add custom keywords for a topic."""
    topic_lower = topic.lower()
    if topic_lower not in TOPIC_KEYWORDS:
        TOPIC_KEYWORDS[topic_lower] = []
    TOPIC_KEYWORDS[topic_lower].extend(keywords)