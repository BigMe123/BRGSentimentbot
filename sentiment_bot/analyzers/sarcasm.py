"""Sarcasm and irony detection for sentiment adjustment."""

import re
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class SarcasmDetector:
    """Detect sarcasm and irony in text."""

    def __init__(self):
        """Initialize detector."""
        self._model = None
        self._tokenizer = None

        # Heuristic patterns for sarcasm
        self.sarcasm_patterns = [
            r"\b(yeah right|sure thing|oh great|wonderful|fantastic|brilliant)\b",
            r"\b(obviously|clearly|definitely) not\b",
            r"\.{3,}",  # Multiple dots often indicate sarcasm
            r"[!?]{2,}",  # Multiple exclamation/question marks
            r"\b(wow|oh wow|amazing)\b.*\b(not|terrible|awful)\b",
        ]

        # Negation patterns
        self.negation_patterns = [
            r"\b(not|never|no|neither|nor|nobody|nothing|nowhere)\b",
            r"\b(hardly|scarcely|barely|seldom|rarely)\b",
            r"n't\b",  # Contractions
            r"\b(without|lack|absent|missing)\b",
        ]

        # Intensifier patterns
        self.intensifier_patterns = [
            r"\b(very|extremely|absolutely|completely|totally|utterly)\b",
            r"\b(really|quite|pretty|fairly|rather|somewhat)\b",
            r"\b(incredibly|remarkably|exceptionally|extraordinarily)\b",
        ]

    def detect(self, text: str) -> float:
        """Detect sarcasm probability in text.

        Returns:
            Probability of sarcasm (0-1)
        """
        # Try model-based detection first
        model_prob = self._detect_with_model(text)

        # Heuristic detection
        heuristic_prob = self._detect_with_heuristics(text)

        # Combine probabilities
        if model_prob is not None:
            # Weight model more heavily
            combined = 0.7 * model_prob + 0.3 * heuristic_prob
        else:
            combined = heuristic_prob

        return min(1.0, combined)

    def _detect_with_model(self, text: str) -> Optional[float]:
        """Use transformer model for sarcasm detection."""
        try:
            if self._model is None:
                from transformers import pipeline

                # Use a small irony detection model
                self._model = pipeline(
                    "text-classification",
                    model="cardiffnlp/twitter-roberta-base-irony",
                    device=-1,  # CPU
                )

            result = self._model(text[:512])  # Limit text length

            # Extract irony probability
            for item in result:
                if item["label"].lower() in ["irony", "sarcasm", "label_1"]:
                    return item["score"]

            return 0.0

        except Exception as e:
            logger.debug(f"Model-based sarcasm detection failed: {e}")
            return None

    def _detect_with_heuristics(self, text: str) -> float:
        """Use heuristic patterns for sarcasm detection."""

        text_lower = text.lower()
        score = 0.0

        # Check sarcasm patterns
        for pattern in self.sarcasm_patterns:
            if re.search(pattern, text_lower):
                score += 0.2

        # Check for quotation marks around positive words (often sarcastic)
        if re.search(
            r'["\'].*\b(great|wonderful|amazing|excellent|perfect)\b.*["\']', text_lower
        ):
            score += 0.3

        # Check for contradiction patterns
        if re.search(r"\b(but|however|although|though)\b.*\b(not|never)\b", text_lower):
            score += 0.15

        # Check for excessive punctuation
        if len(re.findall(r"[!?]", text)) > 3:
            score += 0.1

        # Cap at 1.0
        return min(1.0, score)

    def adjust_sentiment_for_sarcasm(
        self, sentiment_score: float, sarcasm_prob: float
    ) -> float:
        """Adjust sentiment score based on sarcasm probability.

        Args:
            sentiment_score: Original sentiment (-1 to 1)
            sarcasm_prob: Sarcasm probability (0 to 1)

        Returns:
            Adjusted sentiment score
        """
        if sarcasm_prob < 0.3:
            # Low sarcasm, no adjustment
            return sentiment_score

        if sarcasm_prob > 0.7:
            # High sarcasm, flip or neutralize
            if abs(sentiment_score) > 0.5:
                # Strong sentiment, likely flip
                return -sentiment_score * 0.7
            else:
                # Weak sentiment, neutralize
                return sentiment_score * 0.3

        # Medium sarcasm, dampen
        dampening = 1 - (sarcasm_prob * 0.5)
        return sentiment_score * dampening

    def detect_negation_context(self, text: str, target_phrase: str) -> bool:
        """Check if target phrase appears in negation context.

        Args:
            text: Full text
            target_phrase: Phrase to check for negation

        Returns:
            True if negated
        """
        # Find position of target phrase
        target_pos = text.lower().find(target_phrase.lower())
        if target_pos == -1:
            return False

        # Check preceding context (up to 50 chars)
        start = max(0, target_pos - 50)
        preceding = text[start:target_pos].lower()

        # Check for negation
        for pattern in self.negation_patterns:
            if re.search(pattern, preceding):
                return True

        return False

    def detect_intensifiers(self, text: str) -> float:
        """Detect intensifier strength in text.

        Returns:
            Intensification factor (1.0 = normal, >1 = intensified)
        """
        text_lower = text.lower()

        intensifier_count = 0
        for pattern in self.intensifier_patterns:
            intensifier_count += len(re.findall(pattern, text_lower))

        # Calculate intensification factor
        if intensifier_count == 0:
            return 1.0
        elif intensifier_count == 1:
            return 1.2
        elif intensifier_count == 2:
            return 1.4
        else:
            return 1.5  # Cap at 1.5x
