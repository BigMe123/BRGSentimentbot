"""Ensemble sentiment analyzer with confidence scoring and abstention."""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class SentimentResult:
    """Result from ensemble sentiment analysis."""

    score: float  # -1 to +1
    confidence: float  # 0 to 1
    label: str  # positive/negative/neutral/abstain
    components: Dict[str, float]  # individual model scores
    evidence: List[str]  # top evidence sentences
    abstained: bool = False
    abstain_reason: Optional[str] = None


class SentimentEnsemble:
    """Ensemble sentiment with multiple models and confidence gating."""

    def __init__(self, config: Dict = None):
        """Initialize ensemble with config."""
        self.config = config or {}
        self.weights = self.config.get(
            "weights", {"sst2": 0.45, "emotion": 0.25, "nli": 0.30}
        )
        self.abstain_config = self.config.get(
            "abstain", {"max_prob_thresh": 0.65, "disagreement_thresh": 0.35}
        )

        # Lazy load models
        self._sst2_pipeline = None
        self._emotion_pipeline = None
        self._nli_pipeline = None
        self._sarcasm_detector = None

    def _get_sst2_pipeline(self):
        """Lazy load SST-2 sentiment pipeline."""
        if self._sst2_pipeline is None:
            from ..models import get_sentiment_pipeline

            self._sst2_pipeline = get_sentiment_pipeline()
        return self._sst2_pipeline

    def _get_emotion_pipeline(self):
        """Lazy load emotion pipeline."""
        if self._emotion_pipeline is None:
            from ..models import get_emotion_pipeline

            self._emotion_pipeline = get_emotion_pipeline()
        return self._emotion_pipeline

    def _get_nli_pipeline(self):
        """Lazy load NLI pipeline."""
        if self._nli_pipeline is None:
            from ..models import get_nli_pipeline

            self._nli_pipeline = get_nli_pipeline()
        return self._nli_pipeline

    def _get_sarcasm_detector(self):
        """Lazy load sarcasm detector."""
        if self._sarcasm_detector is None:
            from .sarcasm import SarcasmDetector

            self._sarcasm_detector = SarcasmDetector()
        return self._sarcasm_detector

    def score_article(self, text: str, title: Optional[str] = None) -> SentimentResult:
        """Score article with ensemble and confidence."""

        # Use title + first paragraph for efficiency
        analysis_text = f"{title}. {text[:500]}" if title else text[:500]

        components = {}

        # 1. SST-2 sentiment
        try:
            sst2_result = self._get_sst2_pipeline()(analysis_text)[0]
            sst2_score = self._sst2_to_score(sst2_result)
            components["sst2"] = sst2_score
            sst2_confidence = sst2_result["score"]
        except Exception as e:
            logger.warning(f"SST-2 failed: {e}")
            components["sst2"] = 0.0
            sst2_confidence = 0.5

        # 2. Emotion-based sentiment
        try:
            emotion_result = self._get_emotion_pipeline()(analysis_text)[0]
            emotion_score = self._emotion_to_sentiment(emotion_result)
            components["emotion"] = emotion_score
        except Exception as e:
            logger.warning(f"Emotion failed: {e}")
            components["emotion"] = 0.0

        # 3. NLI-based sentiment
        try:
            nli_score = self._nli_sentiment(analysis_text)
            components["nli"] = nli_score
        except Exception as e:
            logger.warning(f"NLI failed: {e}")
            components["nli"] = 0.0

        # 4. Check for sarcasm/irony
        sarcasm_prob = 0.0
        try:
            sarcasm_prob = self._get_sarcasm_detector().detect(analysis_text)
            if sarcasm_prob > 0.6:
                # Dampen extreme scores for sarcastic text
                for key in components:
                    components[key] *= 1 - 0.3 * sarcasm_prob
        except:
            pass  # Sarcasm detection is optional

        # Calculate ensemble score
        ensemble_score = self._weighted_average(components)

        # Calculate confidence and check abstention
        confidence, should_abstain, abstain_reason = self._calculate_confidence(
            components, sst2_confidence
        )

        # Determine label
        if should_abstain:
            label = "abstain"
        elif ensemble_score > 0.1:
            label = "positive"
        elif ensemble_score < -0.1:
            label = "negative"
        else:
            label = "neutral"

        # Extract evidence (simplified for now)
        evidence = self._extract_evidence(text, ensemble_score)

        return SentimentResult(
            score=ensemble_score,
            confidence=confidence,
            label=label,
            components=components,
            evidence=evidence,
            abstained=should_abstain,
            abstain_reason=abstain_reason,
        )

    def _sst2_to_score(self, result: Dict) -> float:
        """Convert SST-2 result to -1 to +1 score."""
        if result["label"].lower() == "positive":
            return result["score"]
        else:
            return -result["score"]

    def _emotion_to_sentiment(self, result: Dict) -> float:
        """Map emotions to sentiment valence."""
        emotion = result["label"].lower()
        score = result["score"]

        # Emotion to valence mapping
        valence_map = {
            "joy": 1.0,
            "love": 0.8,
            "surprise": 0.1,  # Mildly positive
            "fear": -0.6,
            "sadness": -0.8,
            "anger": -0.9,
            "disgust": -0.7,
        }

        base_valence = valence_map.get(emotion, 0.0)
        return base_valence * score

    def _nli_sentiment(self, text: str) -> float:
        """Use NLI for stance-based sentiment."""
        nli = self._get_nli_pipeline()

        # Test hypotheses
        result = nli(
            text,
            candidate_labels=["positive tone", "negative tone", "neutral tone"],
            multi_label=False,
        )

        # Convert to sentiment score
        scores = dict(zip(result["labels"], result["scores"]))
        pos_score = scores.get("positive tone", 0.0)
        neg_score = scores.get("negative tone", 0.0)

        return pos_score - neg_score

    def _weighted_average(self, components: Dict[str, float]) -> float:
        """Calculate weighted average of component scores."""
        total_score = 0.0
        total_weight = 0.0

        for model, score in components.items():
            weight = self.weights.get(model, 0.0)
            total_score += score * weight
            total_weight += weight

        if total_weight > 0:
            return total_score / total_weight
        return 0.0

    def _calculate_confidence(
        self, components: Dict[str, float], max_prob: float
    ) -> Tuple[float, bool, Optional[str]]:
        """Calculate confidence and determine if should abstain."""

        # Check max probability threshold
        if max_prob < self.abstain_config["max_prob_thresh"]:
            return max_prob, True, "low_probability"

        # Check disagreement between models
        scores = list(components.values())
        if len(scores) > 1:
            disagreement = np.std(scores)
            if disagreement > self.abstain_config["disagreement_thresh"]:
                confidence = max(0.1, 1 - disagreement)
                return confidence, True, "high_disagreement"

        # Normal confidence calculation
        confidence = max_prob * (1 - np.std(scores)) if len(scores) > 1 else max_prob

        return confidence, False, None

    def _extract_evidence(self, text: str, score: float) -> List[str]:
        """Extract top evidence sentences (simplified)."""
        # Split into sentences
        sentences = text.split(". ")[:5]  # First 5 sentences

        # For now, return top 2 sentences
        # In production, would use attention weights or SHAP
        return sentences[:2]
