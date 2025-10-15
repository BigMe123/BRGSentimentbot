#!/usr/bin/env python3
"""
Boston Risk Group - Sentiment Analysis & Threat Detection CLI
A comprehensive tool for analyzing political volatility and risk through sentiment analysis.
"""

import json
import csv
import re
import argparse
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
import requests
import time
from collections import Counter

# Third-party imports (install with: pip install textblob vaderSentiment newspaper3k)
try:
    from textblob import TextBlob
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    from newspaper import Article
except ImportError as e:
    print(f"Missing required packages. Install with: pip install textblob vaderSentiment newspaper3k")
    exit(1)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class ContentItem:
    """Represents a piece of content for analysis"""
    text: str
    source: str
    url: Optional[str] = None
    timestamp: Optional[str] = None
    metadata: Optional[Dict] = None

@dataclass
class AnalysisResult:
    """Results of sentiment and threat analysis"""
    volatility_score: float
    confidence: float
    sentiment_polarity: float
    threat_indicators: List[str]
    intensity_score: float
    source_credibility: float
    top_triggers: List[str]
    processed_count: int
    timestamp: str

class SentimentAnalyzer:
    """Core sentiment analysis and threat detection engine"""
    
    def __init__(self):
        self.vader = SentimentIntensityAnalyzer()
        
        # Threat indicator keywords (expandable)
        self.threat_keywords = {
            'political_instability': [
                'resign', 'coup', 'protest', 'riot', 'uprising', 'revolution',
                'government fall', 'political crisis', 'instability', 'unrest',
                'demonstration', 'martial law', 'emergency', 'opposition'
            ],
            'military_conflict': [
                'war', 'conflict', 'invasion', 'attack', 'bombing', 'missile',
                'military', 'combat', 'battle', 'offensive', 'strike', 'assault',
                'troops', 'casualties', 'ceasefire', 'escalation'
            ],
            'economic_shock': [
                'crash', 'collapse', 'recession', 'inflation', 'currency',
                'market fall', 'economic crisis', 'bankruptcy', 'debt crisis',
                'financial instability', 'devaluation', 'sanctions'
            ]
        }
        
        # Source credibility weights
        self.source_weights = {
            'reuters': 0.95,
            'bbc': 0.90,
            'ap': 0.92,
            'cnn': 0.75,
            'fox': 0.70,
            'reddit': 0.40,
            'twitter': 0.35,
            'facebook': 0.30,
            'blog': 0.45,
            'unknown': 0.50
        }

    def preprocess_text(self, text: str) -> str:
        """Clean and preprocess text for analysis"""
        # Remove URLs
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        
        # Remove hashtags, mentions, emojis (basic)
        text = re.sub(r'#\w+', '', text)
        text = re.sub(r'@\w+', '', text)
        text = re.sub(r'[^\w\s.,!?;:]', '', text)
        
        # Remove extra whitespace
        text = ' '.join(text.split())
        
        return text.strip()

    def is_relevant_content(self, text: str) -> bool:
        """Classify if content is relevant for risk analysis"""
        text_lower = text.lower()
        
        # Check for any threat keywords
        for category, keywords in self.threat_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return True
        
        # Additional relevance indicators
        relevance_indicators = [
            'government', 'policy', 'election', 'trade', 'economy',
            'international', 'diplomatic', 'security', 'defense'
        ]
        
        return any(indicator in text_lower for indicator in relevance_indicators)

    def analyze_sentiment(self, text: str) -> Dict[str, float]:
        """Perform sentiment analysis using multiple methods"""
        # VADER sentiment
        vader_scores = self.vader.polarity_scores(text)
        
        # TextBlob sentiment
        blob = TextBlob(text)
        textblob_polarity = blob.sentiment.polarity
        textblob_subjectivity = blob.sentiment.subjectivity
        
        return {
            'vader_compound': vader_scores['compound'],
            'vader_positive': vader_scores['pos'],
            'vader_negative': vader_scores['neg'],
            'vader_neutral': vader_scores['neu'],
            'textblob_polarity': textblob_polarity,
            'textblob_subjectivity': textblob_subjectivity
        }

    def detect_threats(self, text: str) -> Tuple[List[str], float]:
        """Detect threat indicators and calculate intensity"""
        text_lower = text.lower()
        detected_threats = []
        intensity_score = 0.0
        
        for category, keywords in self.threat_keywords.items():
            category_threats = []
            for keyword in keywords:
                if keyword in text_lower:
                    category_threats.append(keyword)
                    # Weight by keyword severity (simple approach)
                    if keyword in ['war', 'coup', 'crash', 'collapse']:
                        intensity_score += 2.0
                    elif keyword in ['protest', 'inflation', 'conflict']:
                        intensity_score += 1.5
                    else:
                        intensity_score += 1.0
            
            if category_threats:
                detected_threats.extend(category_threats)
        
        return detected_threats, min(intensity_score, 10.0)

    def get_source_credibility(self, source: str) -> float:
        """Determine source credibility weight"""
        source_lower = source.lower()
        
        for source_type, weight in self.source_weights.items():
            if source_type in source_lower:
                return weight
        
        return self.source_weights['unknown']

    def calculate_volatility_score(self, sentiment: Dict[str, float], 
                                 threats: List[str], intensity: float, 
                                 credibility: float) -> Tuple[float, float]:
        """Calculate overall volatility score and confidence"""
        
        # Sentiment component (negative sentiment increases volatility)
        sentiment_component = abs(sentiment['vader_compound']) * 2.0
        if sentiment['vader_compound'] < -0.1:  # Negative sentiment
            sentiment_component *= 1.5
        
        # Threat component
        threat_component = len(threats) * 0.5 + intensity * 0.3
        
        # Combine components with weights
        raw_score = (
            sentiment_component * 0.3 +
            threat_component * 0.5 +
            sentiment['textblob_subjectivity'] * 0.2
        ) * credibility
        
        # Normalize to 0-10 scale
        volatility_score = min(raw_score, 10.0)
        
        # Calculate confidence based on multiple factors
        confidence = min(
            (credibility * 0.4 + 
             min(len(threats) / 5.0, 1.0) * 0.3 + 
             sentiment['textblob_subjectivity'] * 0.3), 
            1.0
        )
        
        return volatility_score, confidence

class DataIngestion:
    """Handle various data input sources"""
    
    @staticmethod
    def load_from_file(filepath: str) -> List[ContentItem]:
        """Load content from file (txt, csv, json)"""
        path = Path(filepath)
        content_items = []
        
        try:
            if path.suffix.lower() == '.txt':
                with open(path, 'r', encoding='utf-8') as f:
                    text = f.read()
                    # Split by paragraphs or lines
                    chunks = [chunk.strip() for chunk in text.split('\n\n') if chunk.strip()]
                    content_items = [ContentItem(text=chunk, source='file') for chunk in chunks]
            
            elif path.suffix.lower() == '.csv':
                with open(path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        # Assume columns: text, source, url (optional)
                        content_items.append(ContentItem(
                            text=row.get('text', ''),
                            source=row.get('source', 'unknown'),
                            url=row.get('url'),
                            metadata=row
                        ))
            
            elif path.suffix.lower() == '.json':
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for item in data:
                            content_items.append(ContentItem(
                                text=item.get('text', ''),
                                source=item.get('source', 'unknown'),
                                url=item.get('url'),
                                metadata=item
                            ))
            
        except Exception as e:
            logger.error(f"Error loading file {filepath}: {e}")
        
        return content_items

    @staticmethod
    def scrape_news_sample() -> List[ContentItem]:
        """Scrape sample news headlines (demo implementation)"""
        # This is a simplified demo - in production, you'd use news APIs
        sample_headlines = [
            "Government announces new economic measures amid inflation concerns",
            "Protests continue in capital over controversial policy changes",
            "Military exercises begin near disputed border region",
            "Central bank raises interest rates to combat rising prices",
            "Opposition leader calls for early elections",
            "Trade negotiations reach critical phase",
            "Currency hits new low against major trading partners",
            "Security forces deployed to maintain order in affected areas"
        ]
        
        return [ContentItem(text=headline, source='news_api') for headline in sample_headlines]

def main():
    """Main CLI interface"""
    parser = argparse.ArgumentParser(description='Boston Risk Group Sentiment Analysis CLI')
    parser.add_argument('--input', '-i', type=str, help='Input file path (txt, csv, json)')
    parser.add_argument('--output', '-o', type=str, help='Output file path (json)')
    parser.add_argument('--sample', action='store_true', help='Use sample news data')
    parser.add_argument('--threshold', '-t', type=float, default=5.0, help='Volatility threshold for alerts')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Initialize analyzer
    analyzer = SentimentAnalyzer()
    
    # Load data
    content_items = []
    if args.input:
        content_items = DataIngestion.load_from_file(args.input)
        logger.info(f"Loaded {len(content_items)} items from {args.input}")
    elif args.sample:
        content_items = DataIngestion.scrape_news_sample()
        logger.info(f"Using {len(content_items)} sample news items")
    else:
        logger.error("Please specify --input file or --sample flag")
        return
    
    if not content_items:
        logger.error("No content to analyze")
        return
    
    # Process content
    logger.info("Starting analysis...")
    
    processed_results = []
    relevant_count = 0
    total_volatility = 0.0
    total_confidence = 0.0
    all_threats = []
    all_triggers = []
    
    for item in content_items:
        # Preprocess
        clean_text = analyzer.preprocess_text(item.text)
        
        if not clean_text or len(clean_text) < 10:
            continue
        
        # Check relevance
        if not analyzer.is_relevant_content(clean_text):
            continue
        
        relevant_count += 1
        
        # Analyze sentiment
        sentiment_scores = analyzer.analyze_sentiment(clean_text)
        
        # Detect threats
        threats, intensity = analyzer.detect_threats(clean_text)
        
        # Get source credibility
        credibility = analyzer.get_source_credibility(item.source)
        
        # Calculate volatility score
        volatility, confidence = analyzer.calculate_volatility_score(
            sentiment_scores, threats, intensity, credibility
        )
        
        total_volatility += volatility
        total_confidence += confidence
        all_threats.extend(threats)
        
        if volatility > args.threshold:
            all_triggers.append(clean_text[:100] + "...")
        
        processed_results.append({
            'text': clean_text[:200] + "..." if len(clean_text) > 200 else clean_text,
            'volatility_score': round(volatility, 2),
            'confidence': round(confidence, 2),
            'sentiment': sentiment_scores,
            'threats': threats,
            'intensity': round(intensity, 2),
            'credibility': round(credibility, 2),
            'source': item.source
        })
        
        if args.verbose:
            logger.debug(f"Processed: {clean_text[:50]}... -> Score: {volatility:.2f}")
    
    # Calculate overall results
    if relevant_count > 0:
        avg_volatility = total_volatility / relevant_count
        avg_confidence = total_confidence / relevant_count
        
        # Get top threat indicators
        threat_counter = Counter(all_threats)
        top_threats = [threat for threat, count in threat_counter.most_common(5)]
        
        # Create final result
        result = AnalysisResult(
            volatility_score=round(avg_volatility, 2),
            confidence=round(avg_confidence, 2),
            sentiment_polarity=round(sum(r['sentiment']['vader_compound'] for r in processed_results) / len(processed_results), 2),
            threat_indicators=top_threats,
            intensity_score=round(sum(r['intensity'] for r in processed_results) / len(processed_results), 2),
            source_credibility=round(sum(r['credibility'] for r in processed_results) / len(processed_results), 2),
            top_triggers=all_triggers[:3],
            processed_count=relevant_count,
            timestamp=datetime.now().isoformat()
        )
        
        # Output results
        print("\n" + "="*60)
        print("BOSTON RISK GROUP - VOLATILITY ANALYSIS REPORT")
        print("="*60)
        print(f"Overall Volatility Score: {result.volatility_score}/10")
        print(f"Confidence Level: {result.confidence:.1%}")
        print(f"Processed Items: {result.processed_count}")
        print(f"Analysis Timestamp: {result.timestamp}")
        
        if result.volatility_score >= args.threshold:
            print(f"\n⚠️  HIGH VOLATILITY ALERT (>{args.threshold})")
        
        print(f"\nTop Threat Indicators:")
        for threat in result.threat_indicators:
            print(f"  • {threat}")
        
        if result.top_triggers:
            print(f"\nHigh-Risk Content Samples:")
            for trigger in result.top_triggers:
                print(f"  • {trigger}")
        
        print(f"\nTechnical Details:")
        print(f"  Sentiment Polarity: {result.sentiment_polarity}")
        print(f"  Average Intensity: {result.intensity_score}")
        print(f"  Source Credibility: {result.source_credibility}")
        
        # Save to file if requested
        if args.output:
            output_data = {
                'summary': asdict(result),
                'detailed_results': processed_results
            }
            
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Results saved to {args.output}")
        
    else:
        print("No relevant content found for analysis.")

if __name__ == '__main__':
    main()