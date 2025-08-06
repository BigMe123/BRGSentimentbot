"""Sentiment and volatility analysis tools.

This module prefers the :mod:`vaderSentiment` package for lexicon based
sentiment analysis.  When the dependency is missing a very small lexicon
analyzer is used as a fallback.  The fallback is intentionally simple and
is **not** a drop in replacement for VADER.  Results produced by the
fallback are flagged as ``low_quality`` so that downstream modules can
detect the degraded state and react accordingly (e.g. by skipping
automated trading decisions or prompting the user to install
``vaderSentiment``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from statistics import fmean, stdev
from typing import Iterable, List, Dict
from collections import Counter

try:  # pragma: no cover - optional dependency
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

    _vader = SentimentIntensityAnalyzer()
    VADER_AVAILABLE = True
except Exception:  # pragma: no cover - fallback

    class SentimentIntensityAnalyzer:  # type: ignore
        """Enhanced lexicon based sentiment analyzer.

        This is a simplified analyzer used only when the real
        :mod:`vaderSentiment` package is unavailable.  It tokenises input
        using a basic regular expression and scores text by counting
        positive and negative words from small lexicons derived from the
        VADER paper.
        """

        # Expanded lexicons with intensity weights
        POS = {
            # Strong positive (weight: 3)
            "excellent": 3, "amazing": 3, "wonderful": 3, "fantastic": 3, 
            "outstanding": 3, "perfect": 3, "brilliant": 3, "superb": 3,
            "exceptional": 3, "magnificent": 3, "spectacular": 3, "incredible": 3,
            # Moderate positive (weight: 2)
            "great": 2, "good": 2, "positive": 2, "fortunate": 2, "correct": 2,
            "superior": 2, "better": 2, "improved": 2, "effective": 2, "successful": 2,
            "profitable": 2, "beneficial": 2, "favorable": 2, "promising": 2,
            # Mild positive (weight: 1)
            "nice": 1, "okay": 1, "fine": 1, "decent": 1, "adequate": 1,
            "satisfactory": 1, "acceptable": 1, "reasonable": 1, "fair": 1,
        }
        
        NEG = {
            # Strong negative (weight: -3)
            "terrible": -3, "awful": -3, "horrible": -3, "disastrous": -3,
            "catastrophic": -3, "devastating": -3, "atrocious": -3, "dreadful": -3,
            "appalling": -3, "abysmal": -3, "pathetic": -3, "miserable": -3,
            # Moderate negative (weight: -2)
            "bad": -2, "poor": -2, "negative": -2, "unfortunate": -2, "wrong": -2,
            "inferior": -2, "worse": -2, "ineffective": -2, "unsuccessful": -2,
            "unprofitable": -2, "harmful": -2, "unfavorable": -2, "problematic": -2,
            # Mild negative (weight: -1)
            "disappointing": -1, "mediocre": -1, "subpar": -1, "lacking": -1,
            "inadequate": -1, "unsatisfactory": -1, "unacceptable": -1, "weak": -1,
        }
        
        # Intensifiers and diminishers
        INTENSIFIERS = {
            "very": 1.5, "extremely": 2.0, "absolutely": 2.0, "totally": 1.8,
            "really": 1.5, "quite": 1.3, "particularly": 1.5, "especially": 1.5,
            "remarkably": 1.7, "incredibly": 2.0, "extraordinarily": 2.0,
        }
        
        DIMINISHERS = {
            "somewhat": 0.5, "slightly": 0.5, "barely": 0.3, "hardly": 0.3,
            "marginally": 0.4, "mildly": 0.5, "moderately": 0.7, "fairly": 0.8,
        }
        
        # Negation words
        NEGATIONS = {
            "not", "no", "never", "neither", "nowhere", "nothing", "none",
            "nobody", "nowhere", "cannot", "can't", "won't", "wouldn't",
            "shouldn't", "couldn't", "doesn't", "didn't", "isn't", "wasn't",
        }

        word_re = re.compile(r"\b\w+\b")
        emoji_re = re.compile(r"[:;=][-)DPO\[\]{}|\\]|[-)DPO\[\]{}|\\][:;=]")

        def polarity_scores(self, text: str) -> dict[str, float]:
            words = self.word_re.findall(text.lower())
            
            score = 0.0
            pos_count = 0
            neg_count = 0
            neu_count = 0
            
            # Check for emojis
            positive_emojis = len(re.findall(r"[:\);\)=\)]|\(:|\):|\(:", text))
            negative_emojis = len(re.findall(r"[:\(;\(=\(]|\):|:\(", text))
            score += (positive_emojis - negative_emojis) * 0.5
            
            # Process words with context
            for i, word in enumerate(words):
                word_score = 0
                
                # Check sentiment lexicons
                if word in self.POS:
                    word_score = self.POS[word]
                    pos_count += 1
                elif word in self.NEG:
                    word_score = self.NEG[word]
                    neg_count += 1
                else:
                    neu_count += 1
                    continue
                
                # Check for negation in previous 3 words
                negated = False
                for j in range(max(0, i-3), i):
                    if words[j] in self.NEGATIONS:
                        negated = True
                        break
                
                if negated:
                    word_score *= -0.5  # Reduce but don't fully reverse
                
                # Check for intensifiers/diminishers in previous word
                if i > 0:
                    prev_word = words[i-1]
                    if prev_word in self.INTENSIFIERS:
                        word_score *= self.INTENSIFIERS[prev_word]
                    elif prev_word in self.DIMINISHERS:
                        word_score *= self.DIMINISHERS[prev_word]
                
                score += word_score
            
            # Normalize score to [-1, 1] range
            total_words = len(words) if words else 1
            compound = max(-1, min(1, score / (total_words ** 0.5)))
            
            # Calculate component scores
            total_sentiment_words = pos_count + neg_count + neu_count
            if total_sentiment_words > 0:
                pos = pos_count / total_sentiment_words
                neg = neg_count / total_sentiment_words
                neu = neu_count / total_sentiment_words
            else:
                pos = neg = 0.0
                neu = 1.0
            
            return {
                "compound": compound,
                "pos": pos,
                "neg": neg,
                "neu": neu
            }

    _vader = SentimentIntensityAnalyzer()
    VADER_AVAILABLE = False

try:  # pragma: no cover - optional heavy deps
    from transformers import pipeline

    try:
        _bert = pipeline("sentiment-analysis")
    except Exception:
        _bert = None
    try:
        _nli = pipeline("zero-shot-classification")
    except Exception:
        _nli = None
    try:
        _summarizer = pipeline("summarization")
    except Exception:
        _summarizer = None
    try:
        _emotion = pipeline("text-classification", model="j-hartmann/emotion-english-distilroberta-base")
    except Exception:
        _emotion = None
except Exception:  # pragma: no cover - optional dependency
    pipeline = None  # type: ignore
    _bert = _nli = _summarizer = _emotion = None


@dataclass
class Analysis:
    vader: float
    bert: float
    labels: List[str]
    summary: str
    low_quality: bool = False
    # New fields for enhanced analysis
    emotion_scores: Dict[str, float] = field(default_factory=dict)
    subjectivity: float = 0.0
    readability: float = 0.0
    word_count: int = 0
    sentence_count: int = 0
    avg_word_length: float = 0.0
    complexity_score: float = 0.0
    pos_neg_ratio: float = 0.0
    confidence_level: float = 0.0
    key_phrases: List[str] = field(default_factory=list)
    sentiment_breakdown: Dict[str, float] = field(default_factory=dict)


@dataclass
class Snapshot:
    ts: str | None = None
    volatility: float = 0.0
    confidence: float = 0.0
    triggers: List[str] | None = None
    # New fields for enhanced snapshot
    trend: str = "neutral"  # "bullish", "bearish", "neutral"
    momentum: float = 0.0
    dispersion: float = 0.0
    sentiment_stability: float = 0.0
    risk_score: float = 0.0
    dominant_emotion: str = "neutral"
    alert_level: str = "normal"  # "normal", "caution", "warning", "critical"


class TextMetrics:
    """Helper class for calculating text complexity and readability metrics."""
    
    @staticmethod
    def flesch_reading_ease(text: str) -> float:
        """Calculate Flesch Reading Ease score (simplified)."""
        sentences = re.split(r'[.!?]+', text)
        words = re.findall(r'\b\w+\b', text)
        if not sentences or not words:
            return 0.0
        
        syllables = sum(TextMetrics._count_syllables(word) for word in words)
        if len(sentences) == 0 or len(words) == 0:
            return 0.0
            
        score = 206.835 - 1.015 * (len(words) / len(sentences)) - 84.6 * (syllables / len(words))
        return max(0, min(100, score))
    
    @staticmethod
    def _count_syllables(word: str) -> int:
        """Estimate syllable count in a word."""
        word = word.lower()
        vowels = "aeiou"
        syllable_count = 0
        previous_was_vowel = False
        
        for char in word:
            is_vowel = char in vowels
            if is_vowel and not previous_was_vowel:
                syllable_count += 1
            previous_was_vowel = is_vowel
        
        if word.endswith("e"):
            syllable_count -= 1
        if syllable_count == 0:
            syllable_count = 1
            
        return syllable_count
    
    @staticmethod
    def calculate_subjectivity(text: str) -> float:
        """Estimate text subjectivity based on opinion indicators."""
        subjective_indicators = [
            "think", "believe", "feel", "opinion", "seems", "appears",
            "probably", "maybe", "perhaps", "might", "could", "would",
            "should", "ought", "guess", "suppose", "assume", "imagine"
        ]
        
        words = re.findall(r'\b\w+\b', text.lower())
        if not words:
            return 0.0
            
        subjective_count = sum(1 for word in words if word in subjective_indicators)
        return min(1.0, subjective_count / len(words) * 10)


def extract_key_phrases(text: str, max_phrases: int = 5) -> List[str]:
    """Extract key phrases using simple n-gram analysis."""
    # Simple bigram and trigram extraction
    words = re.findall(r'\b\w+\b', text.lower())
    if len(words) < 2:
        return words[:max_phrases]
    
    # Generate bigrams and trigrams
    bigrams = [f"{words[i]} {words[i+1]}" for i in range(len(words)-1)]
    trigrams = [f"{words[i]} {words[i+1]} {words[i+2]}" for i in range(len(words)-2)]
    
    # Count frequency
    phrase_freq = Counter(bigrams + trigrams)
    
    # Filter out common phrases
    common_phrases = {"of the", "in the", "to the", "and the", "on the", "at the", "by the"}
    phrase_freq = {k: v for k, v in phrase_freq.items() if k not in common_phrases and v > 1}
    
    # Return top phrases
    top_phrases = sorted(phrase_freq.items(), key=lambda x: x[1], reverse=True)
    return [phrase for phrase, _ in top_phrases[:max_phrases]]


def analyze(text: str) -> Analysis:
    """Analyse *text* and return enhanced sentiment metrics.

    The returned :class:`Analysis` object includes a ``low_quality`` flag
    which is ``True`` when the result was produced by the lightweight
    fallback analyzer rather than the full VADER implementation.
    """
    
    # Basic VADER analysis
    vader_scores = _vader.polarity_scores(text)
    vader_score = vader_scores.get("compound", 0.0)
    
    # Sentiment breakdown
    sentiment_breakdown = {
        "positive": vader_scores.get("pos", 0.0),
        "negative": vader_scores.get("neg", 0.0),
        "neutral": vader_scores.get("neu", 0.0)
    }
    
    # BERT sentiment
    bert_score = 0.0
    if _bert:
        try:
            res = _bert(text[:512])[0]  # BERT has token limit
            bert_score = res.get("score", 0.0) * (
                1 if res.get("label") == "POSITIVE" else -1
            )
        except Exception:
            pass
    
    # Zero-shot classification
    labels: List[str] = []
    if _nli:
        try:
            candidate_labels = ["threat", "opportunity", "risk", "safe", "urgent", "stable"]
            nli_res = _nli(text[:512], candidate_labels=candidate_labels)
            cand = nli_res.get("labels", [])
            scores = nli_res.get("scores", [])
            # Get top 2 labels with scores > 0.3
            labels = [cand[i] for i, score in enumerate(scores[:2]) if score > 0.3]
        except Exception:
            pass
    
    # Emotion detection
    emotion_scores: Dict[str, float] = {}
    if _emotion:
        try:
            emotions = _emotion(text[:512])
            for emotion in emotions:
                emotion_scores[emotion["label"]] = emotion["score"]
        except Exception:
            pass
    
    # Text summarization
    summary = text[:200]
    if _summarizer and len(text) > 300:
        try:
            summary = _summarizer(text[:1000], max_length=150, min_length=50)[0]["summary_text"]
        except Exception:
            pass
    
    # Calculate text metrics
    metrics = TextMetrics()
    readability = metrics.flesch_reading_ease(text)
    subjectivity = metrics.calculate_subjectivity(text)
    
    # Basic text statistics
    words = re.findall(r'\b\w+\b', text)
    sentences = re.split(r'[.!?]+', text)
    word_count = len(words)
    sentence_count = len([s for s in sentences if s.strip()])
    avg_word_length = sum(len(w) for w in words) / len(words) if words else 0
    
    # Complexity score (combination of readability and sentence length)
    complexity_score = 0.0
    if sentence_count > 0:
        avg_sentence_length = word_count / sentence_count
        complexity_score = (100 - readability) / 100 * 0.5 + min(1.0, avg_sentence_length / 30) * 0.5
    
    # Positive/negative ratio
    pos_neg_ratio = 0.0
    if sentiment_breakdown["negative"] > 0:
        pos_neg_ratio = sentiment_breakdown["positive"] / sentiment_breakdown["negative"]
    elif sentiment_breakdown["positive"] > 0:
        pos_neg_ratio = 10.0  # High positive ratio when no negative
    
    # Confidence level (based on agreement between VADER and BERT)
    confidence_level = 1.0 - abs(vader_score - bert_score) / 2 if bert_score != 0 else 0.5
    
    # Extract key phrases
    key_phrases = extract_key_phrases(text)
    
    return Analysis(
        vader=vader_score,
        bert=bert_score,
        labels=labels,
        summary=summary,
        low_quality=not VADER_AVAILABLE,
        emotion_scores=emotion_scores,
        subjectivity=subjectivity,
        readability=readability,
        word_count=word_count,
        sentence_count=sentence_count,
        avg_word_length=avg_word_length,
        complexity_score=complexity_score,
        pos_neg_ratio=pos_neg_ratio,
        confidence_level=confidence_level,
        key_phrases=key_phrases,
        sentiment_breakdown=sentiment_breakdown
    )


def aggregate(results: Iterable[Analysis]) -> Snapshot:
    """Aggregate many :class:`Analysis` objects with enhanced metrics."""
    
    results = list(results)
    if not results:
        return Snapshot()
    
    # Calculate volatility as average absolute sentiment across analyzers
    sentiment_values = [
        (abs(r.vader) + abs(r.bert)) / 2 for r in results
    ]
    vol = fmean(sentiment_values)
    
    # Calculate dispersion (standard deviation)
    dispersion = stdev(sentiment_values) if len(sentiment_values) > 1 else 0.0
    
    # Calculate confidence (weighted by individual confidence levels)
    individual_confidences = [r.confidence_level for r in results]
    base_confidence = len(results) / (len(results) + 10)
    weighted_confidence = fmean(individual_confidences) if individual_confidences else 0.5
    confidence = (base_confidence + weighted_confidence) / 2
    
    # Determine trend
    recent_sentiments = sentiment_values[-5:] if len(sentiment_values) > 5 else sentiment_values
    older_sentiments = sentiment_values[:-5] if len(sentiment_values) > 5 else []
    
    trend = "neutral"
    momentum = 0.0
    if older_sentiments:
        recent_avg = fmean(recent_sentiments)
        older_avg = fmean(older_sentiments)
        momentum = recent_avg - older_avg
        
        if momentum > 0.1:
            trend = "bullish"
        elif momentum < -0.1:
            trend = "bearish"
    
    # Calculate sentiment stability (inverse of volatility in recent results)
    recent_results = results[-10:] if len(results) > 10 else results
    recent_sentiments = [r.vader for r in recent_results]
    sentiment_stability = 1.0 - (stdev(recent_sentiments) if len(recent_sentiments) > 1 else 0.0)
    
    # Risk score (combination of volatility, dispersion, and negative sentiment)
    avg_sentiment = fmean(sentiment_values)
    negative_weight = max(0, -avg_sentiment)
    risk_score = (vol * 0.3 + dispersion * 0.3 + negative_weight * 0.4)
    
    # Determine dominant emotion
    all_emotions: Counter = Counter()
    for r in results:
        if r.emotion_scores:
            for emotion, score in r.emotion_scores.items():
                all_emotions[emotion] += score
    
    dominant_emotion = "neutral"
    if all_emotions:
        dominant_emotion = all_emotions.most_common(1)[0][0]
    
    # Determine alert level based on risk and sentiment
    alert_level = "normal"
    if risk_score > 0.7 or avg_sentiment < -0.5:
        alert_level = "critical"
    elif risk_score > 0.5 or avg_sentiment < -0.3:
        alert_level = "warning"
    elif risk_score > 0.3 or vol > 0.5:
        alert_level = "caution"
    
    # Collect trigger words from labels
    all_labels = []
    for r in results:
        all_labels.extend(r.labels)
    
    trigger_counter = Counter(all_labels)
    triggers = [label for label, _ in trigger_counter.most_common(5)]
    
    return Snapshot(
        volatility=vol,
        confidence=confidence,
        triggers=triggers,
        trend=trend,
        momentum=momentum,
        dispersion=dispersion,
        sentiment_stability=sentiment_stability,
        risk_score=risk_score,
        dominant_emotion=dominant_emotion,
        alert_level=alert_level
    )
