"""Topic-aware relevance and stance detection using NLI."""

from typing import List, Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class TopicAnalyzer:
    """Analyze topic relevance and stance using NLI."""

    def __init__(self, config: Dict = None):
        """Initialize with config."""
        self.config = config or {}
        self._nli_pipeline = None

        # Default thresholds
        self.relevance_threshold = self.config.get("relevance_threshold", 0.7)
        self.stance_threshold = self.config.get("stance_threshold", 0.6)

        # Topic templates
        self.topic_templates = {
            "elections": [
                "This article is about elections",
                "This discusses voting or electoral processes",
                "This covers political campaigns",
            ],
            "economy": [
                "This article is about economic matters",
                "This discusses financial or business topics",
                "This covers market or trade issues",
            ],
            "security": [
                "This article is about security or defense",
                "This discusses military or conflict issues",
                "This covers safety or threat topics",
            ],
            "climate": [
                "This article is about climate or environment",
                "This discusses weather or environmental changes",
                "This covers sustainability or green topics",
            ],
            "politics": [
                "This article is about politics or government",
                "This discusses policy or governance",
                "This covers political parties or leaders",
            ],
            "tech": [
                "This article is about technology",
                "This discusses digital or innovation topics",
                "This covers AI, software, or hardware",
            ],
            "energy": [
                "This article is about energy",
                "This discusses oil, gas, or renewables",
                "This covers power generation or consumption",
            ],
        }

        # Stance templates by topic
        self.stance_templates = {
            "elections": {
                "fraud_claims": "The article alleges election fraud",
                "democracy_support": "The article supports democratic processes",
                "reform_advocacy": "The article advocates for electoral reform",
            },
            "economy": {
                "growth_optimism": "The article is optimistic about economic growth",
                "recession_concern": "The article expresses concern about recession",
                "policy_criticism": "The article criticizes economic policies",
            },
            "climate": {
                "action_urgency": "The article emphasizes urgent climate action",
                "skepticism": "The article expresses climate skepticism",
                "innovation_focus": "The article focuses on climate solutions",
            },
        }

    def _get_nli_pipeline(self):
        """Lazy load NLI pipeline."""
        if self._nli_pipeline is None:
            from ..models import get_nli_pipeline

            self._nli_pipeline = get_nli_pipeline()
        return self._nli_pipeline

    def is_about(self, text: str, topic: str) -> Tuple[bool, float]:
        """Check if text is about a specific topic.

        Returns:
            (is_relevant, confidence_score)
        """
        nli = self._get_nli_pipeline()

        # Get templates for this topic
        templates = self.topic_templates.get(
            topic.lower(), [f"This article is about {topic}"]
        )

        # Test each template
        max_score = 0.0
        for template in templates:
            try:
                result = nli(
                    text[:1500],  # Use first part of text
                    candidate_labels=[template],
                    multi_label=False,
                )
                score = result["scores"][0]
                max_score = max(max_score, score)
            except Exception as e:
                logger.warning(f"NLI failed for template '{template}': {e}")

        is_relevant = max_score >= self.relevance_threshold
        return is_relevant, max_score

    def detect_stances(self, text: str, topic: str) -> Dict[str, float]:
        """Detect stances toward key themes in the topic.

        Returns:
            Dict mapping stance_name to probability
        """
        nli = self._get_nli_pipeline()

        # Get stance templates for this topic
        stances = self.stance_templates.get(topic.lower(), {})

        if not stances:
            return {}

        stance_scores = {}

        for stance_name, hypothesis in stances.items():
            try:
                result = nli(
                    text[:1500], candidate_labels=[hypothesis], multi_label=False
                )
                score = result["scores"][0]

                # Only include if above threshold
                if score >= self.stance_threshold:
                    stance_scores[stance_name] = score

            except Exception as e:
                logger.warning(f"Stance detection failed for '{stance_name}': {e}")

        return stance_scores

    def extract_topic_tags(
        self, text: str, topic: str, region: Optional[str] = None
    ) -> List[str]:
        """Extract relevant topic tags using zero-shot classification.

        Returns:
            List of relevant tags
        """
        nli = self._get_nli_pipeline()

        # Define tag candidates based on topic
        tag_candidates = self._get_tag_candidates(topic, region)

        if not tag_candidates:
            return []

        try:
            # Multi-label classification for tags
            result = nli(text[:1500], candidate_labels=tag_candidates, multi_label=True)

            # Filter by threshold
            tags = []
            for label, score in zip(result["labels"], result["scores"]):
                if score >= 0.5:  # Tag threshold
                    tags.append(label)

            return tags[:5]  # Max 5 tags

        except Exception as e:
            logger.warning(f"Tag extraction failed: {e}")
            return []

    def _get_tag_candidates(
        self, topic: str, region: Optional[str] = None
    ) -> List[str]:
        """Get candidate tags for a topic/region combination."""

        # Base tags by topic
        topic_tags = {
            "elections": [
                "vote-buying",
                "campaign-finance",
                "voter-turnout",
                "election-fraud",
                "poll-monitoring",
                "coalition-building",
                "electoral-reform",
                "voting-rights",
                "exit-polls",
            ],
            "economy": [
                "inflation",
                "unemployment",
                "gdp-growth",
                "trade-deficit",
                "monetary-policy",
                "fiscal-stimulus",
                "market-crash",
                "currency-crisis",
                "investment",
                "sanctions",
            ],
            "security": [
                "terrorism",
                "military-action",
                "border-conflict",
                "cybersecurity",
                "defense-spending",
                "peacekeeping",
                "arms-trade",
                "insurgency",
                "maritime-security",
            ],
            "climate": [
                "carbon-emissions",
                "renewable-energy",
                "deforestation",
                "extreme-weather",
                "paris-agreement",
                "green-tech",
                "fossil-fuels",
                "sustainability",
                "climate-adaptation",
            ],
        }

        # Get base tags
        tags = topic_tags.get(topic.lower(), [])

        # Add region-specific tags if applicable
        if region:
            region_specific = {
                "asia": ["asean", "belt-and-road", "indo-pacific"],
                "middle_east": ["oil-politics", "sectarian-conflict", "refugee-crisis"],
                "europe": ["eu-policy", "brexit", "nato"],
                "africa": ["au-summit", "resource-extraction", "aid-dependency"],
                "americas": ["trade-agreement", "immigration", "drug-policy"],
            }

            if region.lower() in region_specific:
                tags.extend(region_specific[region.lower()])

        return tags

    def analyze_full(self, text: str, topic: str, region: Optional[str] = None) -> Dict:
        """Full topic analysis including relevance, stances, and tags.

        Returns:
            Complete topic analysis results
        """

        # Check relevance
        is_relevant, relevance_score = self.is_about(text, topic)

        # Get stances
        stances = self.detect_stances(text, topic) if is_relevant else {}

        # Extract tags
        tags = self.extract_topic_tags(text, topic, region) if is_relevant else []

        return {
            "topic": topic,
            "is_relevant": is_relevant,
            "relevance_score": relevance_score,
            "stances": stances,
            "tags": tags,
            "region": region,
        }
