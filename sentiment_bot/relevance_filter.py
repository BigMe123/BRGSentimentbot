"""
Article Relevance Verification
Geo-tagging and topic classification for accurate filtering.
"""

import re
import logging
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from urllib.parse import urlparse
import spacy

logger = logging.getLogger(__name__)

# Try to load spaCy model
try:
    nlp = spacy.load("en_core_web_sm")
except:
    logger.warning("spaCy model not loaded, using fallback NER")
    nlp = None


@dataclass
class RelevanceScore:
    """Relevance scoring for an article."""

    region_score: float = 0.0
    topic_score: float = 0.0
    confidence: float = 0.0
    region_signals: List[str] = None
    topic_signals: List[str] = None
    drop_reason: Optional[str] = None

    def __post_init__(self):
        if self.region_signals is None:
            self.region_signals = []
        if self.topic_signals is None:
            self.topic_signals = []

    @property
    def should_keep(self) -> bool:
        """Decision to keep article."""
        if self.drop_reason:
            return False
        # More lenient: keep if either score is decent, or both are moderate
        return (
            self.region_score >= 0.3
            or self.topic_score >= 0.3
            or (self.region_score >= 0.2 and self.topic_score >= 0.2)
        )

    @property
    def weight(self) -> float:
        """Weight for aggregation (higher relevance = higher weight)."""
        return (self.region_score + self.topic_score) / 2 * self.confidence


class RelevanceFilter:
    """Filter articles by region and topic relevance."""

    def __init__(self):
        """Initialize with region/topic knowledge bases."""
        self.region_patterns = self._build_region_patterns()
        self.topic_lexicons = self._build_topic_lexicons()
        self.dateline_patterns = self._build_dateline_patterns()

    def _build_region_patterns(self) -> Dict[str, Dict[str, Any]]:
        """Build patterns for region detection."""
        return {
            "asia": {
                "countries": [
                    "china",
                    "india",
                    "japan",
                    "korea",
                    "indonesia",
                    "thailand",
                    "vietnam",
                    "philippines",
                    "malaysia",
                    "singapore",
                    "pakistan",
                    "bangladesh",
                    "sri lanka",
                    "nepal",
                    "myanmar",
                    "cambodia",
                    "laos",
                    "taiwan",
                    "hong kong",
                    "mongolia",
                    "kazakhstan",
                    "uzbekistan",
                ],
                "cities": [
                    "beijing",
                    "shanghai",
                    "tokyo",
                    "seoul",
                    "jakarta",
                    "bangkok",
                    "manila",
                    "kuala lumpur",
                    "singapore",
                    "new delhi",
                    "mumbai",
                    "karachi",
                    "dhaka",
                    "colombo",
                    "kathmandu",
                    "yangon",
                    "taipei",
                    "hong kong",
                    "osaka",
                    "kyoto",
                    "busan",
                    "hanoi",
                    "ho chi minh",
                ],
                "regions": [
                    "asia",
                    "asian",
                    "asia-pacific",
                    "apac",
                    "asean",
                    "south asia",
                    "southeast asia",
                    "east asia",
                    "central asia",
                    "indo-pacific",
                ],
                "url_patterns": ["/asia/", "/asian/", "/apac/", "/asean/"],
            },
            "middle_east": {
                "countries": [
                    "israel",
                    "palestine",
                    "jordan",
                    "lebanon",
                    "syria",
                    "iraq",
                    "iran",
                    "saudi arabia",
                    "uae",
                    "kuwait",
                    "qatar",
                    "bahrain",
                    "oman",
                    "yemen",
                    "egypt",
                    "turkey",
                    "libya",
                    "tunisia",
                    "algeria",
                    "morocco",
                ],
                "cities": [
                    "jerusalem",
                    "tel aviv",
                    "gaza",
                    "beirut",
                    "damascus",
                    "baghdad",
                    "tehran",
                    "riyadh",
                    "dubai",
                    "abu dhabi",
                    "kuwait city",
                    "doha",
                    "cairo",
                    "istanbul",
                    "ankara",
                    "tripoli",
                    "tunis",
                    "algiers",
                    "rabat",
                    "amman",
                    "sana'a",
                ],
                "regions": [
                    "middle east",
                    "mideast",
                    "mena",
                    "gulf",
                    "levant",
                    "gcc",
                    "arab",
                    "north africa",
                    "maghreb",
                ],
                "url_patterns": ["/middle-east/", "/mideast/", "/mena/", "/gulf/"],
            },
            "europe": {
                "countries": [
                    "germany",
                    "france",
                    "uk",
                    "united kingdom",
                    "britain",
                    "italy",
                    "spain",
                    "poland",
                    "ukraine",
                    "romania",
                    "netherlands",
                    "belgium",
                    "greece",
                    "portugal",
                    "czech",
                    "hungary",
                    "sweden",
                    "austria",
                    "belarus",
                    "switzerland",
                    "bulgaria",
                    "denmark",
                    "finland",
                    "slovakia",
                    "norway",
                    "ireland",
                    "croatia",
                    "moldova",
                    "bosnia",
                    "albania",
                    "lithuania",
                    "slovenia",
                    "latvia",
                    "estonia",
                ],
                "cities": [
                    "london",
                    "paris",
                    "berlin",
                    "madrid",
                    "rome",
                    "kiev",
                    "kyiv",
                    "bucharest",
                    "warsaw",
                    "budapest",
                    "vienna",
                    "prague",
                    "brussels",
                    "amsterdam",
                    "lisbon",
                    "athens",
                    "stockholm",
                    "copenhagen",
                    "helsinki",
                    "oslo",
                    "dublin",
                    "zurich",
                    "geneva",
                    "milan",
                ],
                "regions": [
                    "europe",
                    "european",
                    "eu",
                    "eurozone",
                    "schengen",
                    "balkans",
                    "scandinavia",
                    "nordic",
                    "eastern europe",
                    "western europe",
                ],
                "url_patterns": ["/europe/", "/eu/", "/uk/", "/germany/", "/france/"],
            },
            "americas": {
                "countries": [
                    "united states",
                    "usa",
                    "us",
                    "america",
                    "canada",
                    "mexico",
                    "brazil",
                    "argentina",
                    "colombia",
                    "peru",
                    "venezuela",
                    "chile",
                    "ecuador",
                    "bolivia",
                    "paraguay",
                    "uruguay",
                    "guyana",
                    "suriname",
                    "guatemala",
                    "cuba",
                    "haiti",
                    "dominican",
                    "honduras",
                    "nicaragua",
                    "el salvador",
                    "costa rica",
                    "panama",
                    "jamaica",
                    "trinidad",
                ],
                "cities": [
                    "washington",
                    "new york",
                    "los angeles",
                    "chicago",
                    "toronto",
                    "mexico city",
                    "sao paulo",
                    "rio",
                    "buenos aires",
                    "lima",
                    "bogota",
                    "caracas",
                    "santiago",
                    "montevideo",
                    "quito",
                    "havana",
                    "panama city",
                    "san jose",
                    "guatemala city",
                ],
                "regions": [
                    "americas",
                    "north america",
                    "south america",
                    "latin america",
                    "central america",
                    "caribbean",
                    "nafta",
                    "mercosur",
                ],
                "url_patterns": ["/americas/", "/us/", "/usa/", "/latin-america/"],
            },
            "africa": {
                "countries": [
                    "south africa",
                    "nigeria",
                    "egypt",
                    "ethiopia",
                    "kenya",
                    "uganda",
                    "algeria",
                    "sudan",
                    "morocco",
                    "angola",
                    "mozambique",
                    "ghana",
                    "madagascar",
                    "cameroon",
                    "ivory coast",
                    "niger",
                    "burkina faso",
                    "mali",
                    "malawi",
                    "zambia",
                    "zimbabwe",
                    "somalia",
                    "senegal",
                    "rwanda",
                    "tunisia",
                    "guinea",
                    "benin",
                    "burundi",
                    "libya",
                ],
                "cities": [
                    "cairo",
                    "lagos",
                    "kinshasa",
                    "johannesburg",
                    "cape town",
                    "nairobi",
                    "addis ababa",
                    "accra",
                    "algiers",
                    "casablanca",
                    "tunis",
                    "kampala",
                    "harare",
                    "lusaka",
                    "dakar",
                    "khartoum",
                ],
                "regions": [
                    "africa",
                    "african",
                    "sub-saharan",
                    "north africa",
                    "west africa",
                    "east africa",
                    "southern africa",
                    "central africa",
                    "sahel",
                    "maghreb",
                    "horn of africa",
                ],
                "url_patterns": ["/africa/", "/african/"],
            },
        }

    def _build_topic_lexicons(self) -> Dict[str, List[str]]:
        """Build keyword lexicons for topic detection."""
        return {
            "elections": [
                "election",
                "vote",
                "voting",
                "ballot",
                "poll",
                "polls",
                "campaign",
                "candidate",
                "electoral",
                "democracy",
                "democratic",
                "referendum",
                "primary",
                "caucus",
                "constituency",
                "voter",
                "turnout",
                "incumbent",
                "opposition",
                "ruling party",
                "parliament",
                "congress",
                "senate",
                "assembly",
                "election commission",
                "electoral college",
                "swing state",
                "exit poll",
                "postal vote",
                "absentee",
                "recount",
                "runoff",
            ],
            "security": [
                "security",
                "military",
                "defense",
                "defence",
                "army",
                "navy",
                "air force",
                "troops",
                "forces",
                "conflict",
                "war",
                "attack",
                "terrorism",
                "terrorist",
                "extremist",
                "militant",
                "insurgent",
                "peacekeeping",
                "nato",
                "alliance",
                "missile",
                "nuclear",
                "weapons",
                "arms",
                "cyber",
                "threat",
                "intelligence",
                "surveillance",
                "border",
                "checkpoint",
            ],
            "economy": [
                "economy",
                "economic",
                "gdp",
                "inflation",
                "unemployment",
                "market",
                "markets",
                "stock",
                "bond",
                "currency",
                "forex",
                "trade",
                "export",
                "import",
                "tariff",
                "deficit",
                "surplus",
                "budget",
                "fiscal",
                "monetary",
                "central bank",
                "interest rate",
                "recession",
                "growth",
                "investment",
                "finance",
                "financial",
                "banking",
                "imf",
                "world bank",
                "debt",
            ],
            "politics": [
                "politics",
                "political",
                "government",
                "president",
                "prime minister",
                "minister",
                "cabinet",
                "parliament",
                "congress",
                "senate",
                "policy",
                "legislation",
                "law",
                "bill",
                "reform",
                "opposition",
                "ruling",
                "coalition",
                "party",
                "diplomatic",
                "embassy",
                "ambassador",
                "summit",
                "bilateral",
                "multilateral",
                "treaty",
                "agreement",
                "sanctions",
            ],
            "energy": [
                "energy",
                "oil",
                "gas",
                "petroleum",
                "opec",
                "crude",
                "barrel",
                "pipeline",
                "refinery",
                "drilling",
                "fracking",
                "renewable",
                "solar",
                "wind",
                "nuclear",
                "electricity",
                "power",
                "grid",
                "blackout",
                "lng",
                "natural gas",
                "coal",
                "mining",
                "uranium",
                "hydroelectric",
                "battery",
                "lithium",
                "hydrogen",
            ],
            "climate": [
                "climate",
                "climate change",
                "global warming",
                "carbon",
                "emissions",
                "greenhouse",
                "paris agreement",
                "cop",
                "ipcc",
                "temperature",
                "drought",
                "flood",
                "hurricane",
                "typhoon",
                "cyclone",
                "wildfire",
                "heatwave",
                "melting",
                "glacier",
                "sea level",
                "renewable",
                "sustainability",
                "environmental",
                "pollution",
                "deforestation",
                "biodiversity",
            ],
            "tech": [
                "technology",
                "tech",
                "digital",
                "ai",
                "artificial intelligence",
                "machine learning",
                "algorithm",
                "data",
                "cyber",
                "internet",
                "online",
                "software",
                "hardware",
                "chip",
                "semiconductor",
                "smartphone",
                "5g",
                "startup",
                "innovation",
                "research",
                "development",
                "silicon valley",
                "tech giant",
                "platform",
                "app",
            ],
        }

    def _build_dateline_patterns(self) -> List[re.Pattern]:
        """Build patterns for dateline extraction."""
        return [
            re.compile(r"^([A-Z][A-Z\s]+)[\s—–-]+", re.MULTILINE),  # "CAIRO — "
            re.compile(
                r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*),?\s+[A-Z][a-z]+\s+\d+", re.MULTILINE
            ),  # "Cairo, August 9"
            re.compile(r"^\(([A-Z][A-Z\s]+)\)", re.MULTILINE),  # "(CAIRO)"
        ]

    def verify_relevance(
        self,
        article: Dict[str, Any],
        target_region: Optional[str] = None,
        target_topics: Optional[List[str]] = None,
        strict: bool = False,
        threshold: float = 0.5,
    ) -> RelevanceScore:
        """
        Verify article relevance for region and topic with enhanced scoring.

        Args:
            article: Article data with 'text', 'title', 'url' fields
            target_region: Target region to match
            target_topics: Target topics to match (can be multiple)
            strict: Strict matching (must match both if specified)
            threshold: Minimum score threshold for keeping article

        Returns:
            RelevanceScore with signals and decision
        """
        score = RelevanceScore()

        # Extract text elements
        text = article.get("text", "")
        title = article.get("title", "")
        url = article.get("url", "")
        combined_text = f"{title} {text[:1000]}".lower()  # Focus on title and lead

        # Handle single topic or list
        if target_topics and isinstance(target_topics, str):
            target_topics = [target_topics]

        # Region verification
        if target_region:
            score.region_score, score.region_signals = self._score_region(
                combined_text, url, target_region
            )

            # Boost if from a region-specific source
            if article.get("_region_boost"):
                score.region_score = min(1.0, score.region_score + 0.3)
                score.region_signals.append("source:regional")

            # Extract dateline for stronger signal
            dateline = self._extract_dateline(text)
            if dateline:
                score.region_signals.append(f"dateline:{dateline}")
                if self._dateline_matches_region(dateline, target_region):
                    score.region_score = min(1.0, score.region_score + 0.3)

        # Topic verification (handle multiple topics)
        if target_topics:
            topic_scores = []
            all_signals = []
            for topic in target_topics:
                t_score, t_signals = self._score_topic(combined_text, url, topic)
                topic_scores.append(t_score)
                all_signals.extend(t_signals)

            # Take best topic score
            score.topic_score = max(topic_scores) if topic_scores else 0.0
            score.topic_signals = list(set(all_signals))  # Deduplicate signals
        else:
            # No specific topics = all topics are relevant
            score.topic_score = 1.0
            score.topic_signals = ["all_topics"]

        # NER enhancement (if available)
        if nlp and (target_region or target_topics):
            entities = self._extract_entities(combined_text[:500])  # Limit for speed

            if target_region:
                region_entities = entities.get("GPE", []) + entities.get("LOC", [])
                for ent in region_entities:
                    if self._entity_matches_region(ent, target_region):
                        score.region_signals.append(f"ner:{ent}")
                        score.region_score = min(1.0, score.region_score + 0.1)

            if target_topics and "elections" in target_topics and "PERSON" in entities:
                # Political figures often mentioned in election coverage
                score.topic_signals.append(f"people:{len(entities['PERSON'])}")
                score.topic_score = min(1.0, score.topic_score + 0.1)

        # Calculate confidence
        total_signals = len(score.region_signals) + len(score.topic_signals)
        score.confidence = min(1.0, 0.3 + (total_signals * 0.1))

        # Strict mode check
        if strict:
            if target_region and score.region_score < 0.5:
                score.drop_reason = "region_mismatch"
            elif target_topics and score.topic_score < 0.5:
                score.drop_reason = "topic_mismatch"
            elif target_region and target_topics:
                if score.region_score < 0.5 or score.topic_score < 0.5:
                    score.drop_reason = "strict_criteria_not_met"
        else:
            # Lenient mode: Allow articles from region-specific sources even with lower scores
            # If we selected a source for this region, trust it more
            if target_region and target_topics:
                # Both specified: need at least one moderate match
                if score.region_score < 0.1 and score.topic_score < 0.1:
                    score.drop_reason = "both_scores_too_low"
            elif target_region and score.region_score < 0.1:
                score.drop_reason = "region_mismatch"
            elif target_topics and score.topic_score < 0.1:
                score.drop_reason = "topic_mismatch"

        return score

    def _score_region(
        self, text: str, url: str, target_region: str
    ) -> Tuple[float, List[str]]:
        """Score region relevance."""
        if target_region not in self.region_patterns:
            return 0.0, []

        patterns = self.region_patterns[target_region]
        score = 0.0
        signals = []

        # Check URL patterns
        for pattern in patterns["url_patterns"]:
            if pattern in url.lower():
                score += 0.3
                signals.append(f"url:{pattern}")

        # Check countries
        for country in patterns["countries"]:
            if country in text:
                score += 0.2
                signals.append(f"country:{country}")
                if len(signals) >= 3:  # Enough signals
                    break

        # Check cities
        for city in patterns["cities"]:
            if city in text:
                score += 0.15
                signals.append(f"city:{city}")
                if len(signals) >= 5:
                    break

        # Check region terms
        for region_term in patterns["regions"]:
            if region_term in text:
                score += 0.1
                signals.append(f"region:{region_term}")

        return min(1.0, score), signals[:10]  # Cap at 10 signals

    def _score_topic(
        self, text: str, url: str, target_topic: str
    ) -> Tuple[float, List[str]]:
        """Score topic relevance."""
        if target_topic not in self.topic_lexicons:
            return 0.0, []

        keywords = self.topic_lexicons[target_topic]
        score = 0.0
        signals = []

        # URL hints
        if target_topic in url.lower() or f"/{target_topic}/" in url:
            score += 0.3
            signals.append(f"url:/{target_topic}/")

        # Keyword matching
        for keyword in keywords:
            if keyword in text:
                score += 0.05
                signals.append(f"kw:{keyword}")
                if len(signals) >= 10:
                    break

        # Specific boosts
        if target_topic == "elections":
            # Check for election-specific patterns
            if re.search(r"\d+\s*%\s*(of\s+)?vote", text):
                score += 0.2
                signals.append("pattern:vote_percentage")
            if re.search(r"(won|lost|leading|trailing)\s+(\w+\s+)?election", text):
                score += 0.2
                signals.append("pattern:election_result")

        return min(1.0, score), signals[:10]

    def _extract_dateline(self, text: str) -> Optional[str]:
        """Extract dateline from article text."""
        for pattern in self.dateline_patterns:
            match = pattern.search(text[:200])  # Check beginning
            if match:
                return match.group(1).strip()
        return None

    def _dateline_matches_region(self, dateline: str, target_region: str) -> bool:
        """Check if dateline matches target region."""
        if target_region not in self.region_patterns:
            return False

        dateline_lower = dateline.lower()
        patterns = self.region_patterns[target_region]

        # Check cities
        for city in patterns["cities"]:
            if city in dateline_lower:
                return True

        # Check countries
        for country in patterns["countries"]:
            if country in dateline_lower:
                return True

        return False

    def _extract_entities(self, text: str) -> Dict[str, List[str]]:
        """Extract named entities using spaCy."""
        if not nlp:
            return {}

        try:
            doc = nlp(text)
            entities = {}
            for ent in doc.ents:
                if ent.label_ not in entities:
                    entities[ent.label_] = []
                entities[ent.label_].append(ent.text)
            return entities
        except:
            return {}

    def _entity_matches_region(self, entity: str, target_region: str) -> bool:
        """Check if entity matches target region."""
        if target_region not in self.region_patterns:
            return False

        entity_lower = entity.lower()
        patterns = self.region_patterns[target_region]

        return (
            entity_lower in patterns["countries"]
            or entity_lower in patterns["cities"]
            or any(region in entity_lower for region in patterns["regions"])
        )
