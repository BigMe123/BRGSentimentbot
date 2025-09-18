#!/usr/bin/env python3
"""
Comprehensive Liechtenstein Report Generator
===========================================
Economic, Jobs, Commodities, FX, and GPI analysis using hybrid news system.
Fully integrated with TheNewsAPI.com for comprehensive coverage.
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Any
from dataclasses import dataclass
import json
from collections import defaultdict, Counter
import numpy as np

from sentiment_bot.hybrid_source_registry import HybridSourceRegistry, UnifiedEvent
from sentiment_bot.api_source_registry import APISourceRegistry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class EconomicSignal:
    """Economic sentiment signal from news."""
    category: str  # 'economy', 'jobs', 'commodities', 'fx'
    sentiment: float  # -100 to +100
    confidence: float  # 0 to 1
    source: str
    title: str
    published_at: datetime
    relevance_score: float


@dataclass
class GPISignal:
    """Global Perception Index signal."""
    observer_country: str
    target_country: str
    sentiment: float
    confidence: float
    source: str
    title: str
    published_at: datetime


class EconomicAnalyzer:
    """Analyzes economic sentiment from news articles."""

    def __init__(self):
        self.economic_keywords = {
            'economy': {
                'positive': ['growth', 'expansion', 'recovery', 'boom', 'strong economy', 'prosperity', 'thriving', 'robust'],
                'negative': ['recession', 'decline', 'crisis', 'contraction', 'downturn', 'collapse', 'struggling', 'weak economy']
            },
            'jobs': {
                'positive': ['job creation', 'employment growth', 'hiring', 'low unemployment', 'job opportunities', 'workforce expansion'],
                'negative': ['job losses', 'layoffs', 'unemployment', 'job cuts', 'redundancies', 'workforce reduction']
            },
            'commodities': {
                'positive': ['commodity prices rising', 'resource boom', 'mining growth', 'export increase', 'trade surplus'],
                'negative': ['commodity crash', 'resource decline', 'mining downturn', 'export drop', 'trade deficit']
            },
            'fx': {
                'positive': ['currency strengthening', 'strong franc', 'exchange rate gains', 'monetary stability'],
                'negative': ['currency weakening', 'franc decline', 'exchange rate losses', 'monetary instability', 'devaluation']
            }
        }

    def analyze_economic_sentiment(self, event: UnifiedEvent) -> List[EconomicSignal]:
        """Extract economic signals from news event."""
        signals = []
        text = f"{event.title} {event.full_text}".lower()

        for category, keywords in self.economic_keywords.items():
            relevance = self._calculate_relevance(text, category)

            if relevance > 0.1:  # Only process if relevant
                sentiment = self._calculate_sentiment(text, keywords)
                confidence = min(relevance * 2, 1.0)  # Higher relevance = higher confidence

                signal = EconomicSignal(
                    category=category,
                    sentiment=sentiment,
                    confidence=confidence,
                    source=event.domain,
                    title=event.title,
                    published_at=event.published_at,
                    relevance_score=relevance
                )
                signals.append(signal)

        return signals

    def _calculate_relevance(self, text: str, category: str) -> float:
        """Calculate how relevant text is to economic category."""
        all_keywords = self.economic_keywords[category]['positive'] + self.economic_keywords[category]['negative']
        matches = sum(1 for keyword in all_keywords if keyword in text)
        return min(matches / 3.0, 1.0)  # Normalize to 0-1

    def _calculate_sentiment(self, text: str, keywords: Dict[str, List[str]]) -> float:
        """Calculate sentiment score for economic category."""
        positive_matches = sum(1 for keyword in keywords['positive'] if keyword in text)
        negative_matches = sum(1 for keyword in keywords['negative'] if keyword in text)

        total_matches = positive_matches + negative_matches
        if total_matches == 0:
            return 0.0

        # Score from -100 to +100
        score = ((positive_matches - negative_matches) / total_matches) * 100
        return score


class GPIAnalyzer:
    """Analyzes global perception from news articles."""

    def __init__(self):
        self.sentiment_keywords = {
            'positive': ['cooperation', 'partnership', 'agreement', 'alliance', 'success', 'achievement', 'progress', 'stability'],
            'negative': ['conflict', 'dispute', 'tension', 'disagreement', 'crisis', 'problem', 'concern', 'instability']
        }

        self.country_domains = {
            'dw.com': 'Germany',
            'spiegel.de': 'Germany',
            'bbc.com': 'United Kingdom',
            'cnn.com': 'United States',
            'lemonde.fr': 'France',
            'swissinfo.ch': 'Switzerland',
            'orf.at': 'Austria',
            'repubblica.it': 'Italy'
        }

    def analyze_gpi_sentiment(self, event: UnifiedEvent, target_country: str) -> GPISignal:
        """Extract GPI signal from news event."""
        observer_country = self.country_domains.get(event.domain, 'Unknown')

        if observer_country == 'Unknown':
            # Try to infer from TLD
            if '.de' in event.domain:
                observer_country = 'Germany'
            elif '.uk' in event.domain:
                observer_country = 'United Kingdom'
            elif '.fr' in event.domain:
                observer_country = 'France'
            else:
                observer_country = 'International'

        text = f"{event.title} {event.full_text}".lower()
        sentiment = self._calculate_gpi_sentiment(text, target_country.lower())
        confidence = self._calculate_confidence(text, target_country)

        return GPISignal(
            observer_country=observer_country,
            target_country=target_country,
            sentiment=sentiment,
            confidence=confidence,
            source=event.domain,
            title=event.title,
            published_at=event.published_at
        )

    def _calculate_gpi_sentiment(self, text: str, target_country: str) -> float:
        """Calculate sentiment towards target country."""
        if target_country not in text:
            return 0.0

        positive_matches = sum(1 for keyword in self.sentiment_keywords['positive'] if keyword in text)
        negative_matches = sum(1 for keyword in self.sentiment_keywords['negative'] if keyword in text)

        total_matches = positive_matches + negative_matches
        if total_matches == 0:
            return 0.0

        score = ((positive_matches - negative_matches) / total_matches) * 100
        return score

    def _calculate_confidence(self, text: str, target_country: str) -> float:
        """Calculate confidence in sentiment assessment."""
        mentions = text.count(target_country.lower())
        return min(mentions * 0.3, 1.0)


class LiechtensteinReportGenerator:
    """Generates comprehensive Liechtenstein analysis report."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.hybrid_registry = HybridSourceRegistry(api_key)
        self.api_registry = APISourceRegistry(api_key)
        self.economic_analyzer = EconomicAnalyzer()
        self.gpi_analyzer = GPIAnalyzer()

    def generate_comprehensive_report(self, days_back: int = 30) -> Dict[str, Any]:
        """Generate comprehensive Liechtenstein report."""
        print("🇱🇮 GENERATING COMPREHENSIVE LIECHTENSTEIN REPORT")
        print("=" * 70)
        print(f"Analysis Period: {days_back} days")
        print(f"News Sources: RSS + TheNewsAPI.com (hybrid)")
        print()

        report = {
            'country': 'Liechtenstein',
            'analysis_date': datetime.now().isoformat(),
            'period_days': days_back,
            'data_sources': 'RSS + TheNewsAPI.com',
            'sections': {}
        }

        # 1. Fetch comprehensive news coverage
        print("📰 STEP 1: Fetching News Coverage")
        print("-" * 40)

        all_events = self._fetch_liechtenstein_news(days_back)
        report['total_articles_analyzed'] = len(all_events)

        print(f"Total articles collected: {len(all_events)}")

        # Count by source type
        rss_count = len([e for e in all_events if e.fetch_channel.value == 'rss'])
        api_count = len([e for e in all_events if e.fetch_channel.value == 'api'])
        print(f"  📡 RSS sources: {rss_count} articles")
        print(f"  🌐 API fallback: {api_count} articles")

        if not all_events:
            print("⚠️ No articles found for analysis")
            return report

        # 2. Economic Analysis
        print(f"\n💰 STEP 2: Economic Analysis")
        print("-" * 40)
        economic_report = self._analyze_economic_indicators(all_events)
        report['sections']['economic'] = economic_report

        # 3. Jobs Analysis
        print(f"\n👥 STEP 3: Employment Analysis")
        print("-" * 40)
        jobs_report = self._analyze_employment(all_events)
        report['sections']['jobs'] = jobs_report

        # 4. Commodities Analysis
        print(f"\n📦 STEP 4: Commodities Analysis")
        print("-" * 40)
        commodities_report = self._analyze_commodities(all_events)
        report['sections']['commodities'] = commodities_report

        # 5. FX Analysis
        print(f"\n💱 STEP 5: Currency/FX Analysis")
        print("-" * 40)
        fx_report = self._analyze_fx(all_events)
        report['sections']['fx'] = fx_report

        # 6. GPI Analysis
        print(f"\n🌍 STEP 6: Global Perception Index")
        print("-" * 40)
        gpi_report = self._analyze_global_perception(all_events)
        report['sections']['gpi'] = gpi_report

        # 7. Generate Summary
        print(f"\n📋 STEP 7: Executive Summary")
        print("-" * 40)
        summary = self._generate_executive_summary(report)
        report['executive_summary'] = summary

        return report

    def _fetch_liechtenstein_news(self, days_back: int) -> List[UnifiedEvent]:
        """Fetch comprehensive Liechtenstein news using hybrid system."""
        all_events = []

        # Multiple search terms for comprehensive coverage
        search_terms = [
            "Liechtenstein",
            "Liechtenstein economy",
            "Liechtenstein finance",
            "Liechtenstein banking",
            "Liechtenstein trade"
        ]

        for term in search_terms:
            events = self.hybrid_registry.fetch_articles(
                query=term,
                max_articles=20
            )
            all_events.extend(events)

        # Deduplicate
        seen_urls = set()
        unique_events = []
        for event in all_events:
            if event.url not in seen_urls:
                unique_events.append(event)
                seen_urls.add(event.url)

        # Filter by date
        cutoff_date = datetime.now() - timedelta(days=days_back)
        recent_events = [e for e in unique_events if e.published_at >= cutoff_date]

        return recent_events

    def _analyze_economic_indicators(self, events: List[UnifiedEvent]) -> Dict[str, Any]:
        """Analyze economic indicators from news."""
        economic_signals = []

        for event in events:
            signals = self.economic_analyzer.analyze_economic_sentiment(event)
            economic_signals.extend(signals)

        # Filter for economy-specific signals
        economy_signals = [s for s in economic_signals if s.category == 'economy']

        if not economy_signals:
            return {
                'sentiment_score': 0,
                'confidence': 0,
                'signal_count': 0,
                'assessment': 'Insufficient data for economic analysis'
            }

        # Calculate weighted average
        total_weight = sum(s.confidence for s in economy_signals)
        if total_weight > 0:
            weighted_sentiment = sum(s.sentiment * s.confidence for s in economy_signals) / total_weight
        else:
            weighted_sentiment = 0

        confidence = min(len(economy_signals) / 10.0, 1.0)

        # Generate assessment
        if weighted_sentiment > 20:
            assessment = "Positive economic sentiment"
        elif weighted_sentiment < -20:
            assessment = "Negative economic sentiment"
        else:
            assessment = "Neutral economic sentiment"

        print(f"Economic sentiment: {weighted_sentiment:.1f}/100")
        print(f"Confidence: {confidence:.2f}")
        print(f"Signals analyzed: {len(economy_signals)}")

        return {
            'sentiment_score': round(weighted_sentiment, 1),
            'confidence': round(confidence, 2),
            'signal_count': len(economy_signals),
            'assessment': assessment,
            'key_articles': [{'title': s.title, 'source': s.source, 'sentiment': s.sentiment}
                           for s in economy_signals[:3]]
        }

    def _analyze_employment(self, events: List[UnifiedEvent]) -> Dict[str, Any]:
        """Analyze employment/jobs indicators."""
        job_signals = []

        for event in events:
            signals = self.economic_analyzer.analyze_economic_sentiment(event)
            job_signals.extend([s for s in signals if s.category == 'jobs'])

        if not job_signals:
            return {
                'sentiment_score': 0,
                'confidence': 0,
                'signal_count': 0,
                'assessment': 'Limited employment data available'
            }

        # Calculate metrics
        total_weight = sum(s.confidence for s in job_signals)
        weighted_sentiment = sum(s.sentiment * s.confidence for s in job_signals) / total_weight if total_weight > 0 else 0
        confidence = min(len(job_signals) / 5.0, 1.0)

        if weighted_sentiment > 15:
            assessment = "Positive employment outlook"
        elif weighted_sentiment < -15:
            assessment = "Employment concerns present"
        else:
            assessment = "Stable employment situation"

        print(f"Employment sentiment: {weighted_sentiment:.1f}/100")
        print(f"Job-related signals: {len(job_signals)}")

        return {
            'sentiment_score': round(weighted_sentiment, 1),
            'confidence': round(confidence, 2),
            'signal_count': len(job_signals),
            'assessment': assessment
        }

    def _analyze_commodities(self, events: List[UnifiedEvent]) -> Dict[str, Any]:
        """Analyze commodities/trade indicators."""
        commodity_signals = []

        for event in events:
            signals = self.economic_analyzer.analyze_economic_sentiment(event)
            commodity_signals.extend([s for s in signals if s.category == 'commodities'])

        if not commodity_signals:
            return {
                'sentiment_score': 0,
                'confidence': 0,
                'signal_count': 0,
                'assessment': 'Limited commodities data - Liechtenstein is service-oriented economy'
            }

        total_weight = sum(s.confidence for s in commodity_signals)
        weighted_sentiment = sum(s.sentiment * s.confidence for s in commodity_signals) / total_weight if total_weight > 0 else 0
        confidence = min(len(commodity_signals) / 3.0, 1.0)

        assessment = "Limited commodities exposure - primarily financial services economy"

        print(f"Commodities sentiment: {weighted_sentiment:.1f}/100")
        print(f"Commodities signals: {len(commodity_signals)}")

        return {
            'sentiment_score': round(weighted_sentiment, 1),
            'confidence': round(confidence, 2),
            'signal_count': len(commodity_signals),
            'assessment': assessment
        }

    def _analyze_fx(self, events: List[UnifiedEvent]) -> Dict[str, Any]:
        """Analyze currency/FX indicators."""
        fx_signals = []

        for event in events:
            signals = self.economic_analyzer.analyze_economic_sentiment(event)
            fx_signals.extend([s for s in signals if s.category == 'fx'])

        # Also look for Swiss Franc mentions (Liechtenstein uses CHF)
        chf_mentions = 0
        for event in events:
            text = f"{event.title} {event.full_text}".lower()
            if any(term in text for term in ['swiss franc', 'chf', 'franc', 'currency']):
                chf_mentions += 1

        if not fx_signals and chf_mentions == 0:
            return {
                'sentiment_score': 0,
                'confidence': 0,
                'signal_count': 0,
                'currency': 'Swiss Franc (CHF)',
                'assessment': 'Limited FX data - uses Swiss Franc currency'
            }

        total_weight = sum(s.confidence for s in fx_signals) if fx_signals else 1
        weighted_sentiment = sum(s.sentiment * s.confidence for s in fx_signals) / total_weight if fx_signals else 0
        confidence = min((len(fx_signals) + chf_mentions) / 5.0, 1.0)

        assessment = f"Uses Swiss Franc (CHF) - {chf_mentions} currency-related mentions found"

        print(f"FX sentiment: {weighted_sentiment:.1f}/100")
        print(f"Currency mentions: {chf_mentions}")
        print(f"FX signals: {len(fx_signals)}")

        return {
            'sentiment_score': round(weighted_sentiment, 1),
            'confidence': round(confidence, 2),
            'signal_count': len(fx_signals),
            'currency': 'Swiss Franc (CHF)',
            'currency_mentions': chf_mentions,
            'assessment': assessment
        }

    def _analyze_global_perception(self, events: List[UnifiedEvent]) -> Dict[str, Any]:
        """Analyze global perception of Liechtenstein."""
        gpi_signals = []

        for event in events:
            if 'liechtenstein' in event.title.lower() or 'liechtenstein' in event.full_text.lower():
                signal = self.gpi_analyzer.analyze_gpi_sentiment(event, 'Liechtenstein')
                if signal.confidence > 0.1:  # Filter low-confidence signals
                    gpi_signals.append(signal)

        if not gpi_signals:
            return {
                'overall_score': 0,
                'confidence': 0,
                'observer_count': 0,
                'assessment': 'Limited global perception data available'
            }

        # Aggregate by observer country
        observer_sentiments = defaultdict(list)
        for signal in gpi_signals:
            observer_sentiments[signal.observer_country].append(signal)

        # Calculate overall GPI
        total_weight = sum(s.confidence for s in gpi_signals)
        overall_gpi = sum(s.sentiment * s.confidence for s in gpi_signals) / total_weight if total_weight > 0 else 0
        confidence = min(len(gpi_signals) / 15.0, 1.0)

        # Top observers
        top_observers = []
        for country, signals in observer_sentiments.items():
            if len(signals) >= 1:
                avg_sentiment = sum(s.sentiment for s in signals) / len(signals)
                top_observers.append((country, avg_sentiment, len(signals)))

        top_observers.sort(key=lambda x: x[1], reverse=True)

        if overall_gpi > 25:
            assessment = "Generally positive global perception"
        elif overall_gpi < -25:
            assessment = "Some negative global perception"
        else:
            assessment = "Neutral global perception"

        print(f"Global Perception Index: {overall_gpi:.1f}/100")
        print(f"Observer countries: {len(observer_sentiments)}")
        print(f"Total GPI signals: {len(gpi_signals)}")

        return {
            'overall_score': round(overall_gpi, 1),
            'confidence': round(confidence, 2),
            'observer_count': len(observer_sentiments),
            'signal_count': len(gpi_signals),
            'assessment': assessment,
            'top_observers': [{'country': country, 'sentiment': round(sentiment, 1), 'articles': count}
                            for country, sentiment, count in top_observers[:5]]
        }

    def _generate_executive_summary(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """Generate executive summary of all analyses."""
        sections = report['sections']

        # Calculate overall economic health score
        economic_scores = []
        if sections.get('economic', {}).get('confidence', 0) > 0.3:
            economic_scores.append(sections['economic']['sentiment_score'])
        if sections.get('jobs', {}).get('confidence', 0) > 0.3:
            economic_scores.append(sections['jobs']['sentiment_score'])

        overall_economic = sum(economic_scores) / len(economic_scores) if economic_scores else 0

        # Key findings
        key_findings = []

        # Economic
        econ_score = sections.get('economic', {}).get('sentiment_score', 0)
        if econ_score > 15:
            key_findings.append("✅ Positive economic sentiment detected")
        elif econ_score < -15:
            key_findings.append("⚠️ Economic concerns present in news coverage")
        else:
            key_findings.append("📊 Neutral economic sentiment")

        # GPI
        gpi_score = sections.get('gpi', {}).get('overall_score', 0)
        if gpi_score > 20:
            key_findings.append("🌍 Strong positive global perception")
        elif gpi_score < -20:
            key_findings.append("🌍 Some negative global perception")
        else:
            key_findings.append("🌍 Neutral global perception")

        # Data quality
        total_articles = report.get('total_articles_analyzed', 0)
        if total_articles > 20:
            key_findings.append(f"📈 Strong data coverage ({total_articles} articles analyzed)")
        elif total_articles > 10:
            key_findings.append(f"📊 Moderate data coverage ({total_articles} articles analyzed)")
        else:
            key_findings.append(f"📉 Limited data coverage ({total_articles} articles analyzed)")

        # Risk assessment
        risks = []
        if sections.get('economic', {}).get('sentiment_score', 0) < -20:
            risks.append("Economic sentiment concerns")
        if sections.get('gpi', {}).get('overall_score', 0) < -20:
            risks.append("Negative global perception trends")
        if total_articles < 10:
            risks.append("Limited data availability for analysis")

        if not risks:
            risks.append("No significant risks identified")

        summary = {
            'overall_economic_sentiment': round(overall_economic, 1),
            'gpi_score': sections.get('gpi', {}).get('overall_score', 0),
            'data_quality': 'Strong' if total_articles > 20 else 'Moderate' if total_articles > 10 else 'Limited',
            'key_findings': key_findings,
            'risk_factors': risks,
            'recommendation': self._generate_recommendation(overall_economic, gpi_score, total_articles)
        }

        print("Executive Summary Generated")
        print(f"Overall Economic Sentiment: {summary['overall_economic_sentiment']}/100")
        print(f"GPI Score: {summary['gpi_score']}/100")
        print(f"Data Quality: {summary['data_quality']}")

        return summary

    def _generate_recommendation(self, economic_score: float, gpi_score: float, article_count: int) -> str:
        """Generate strategic recommendation."""
        if article_count < 5:
            return "Insufficient data for reliable assessment. Recommend expanding news monitoring coverage."

        if economic_score > 15 and gpi_score > 15:
            return "Positive outlook across economic and perception metrics. Continue monitoring for trend confirmation."
        elif economic_score < -15 or gpi_score < -15:
            return "Some negative indicators present. Recommend closer monitoring and stakeholder engagement."
        else:
            return "Stable neutral indicators. Continue regular monitoring for emerging trends."

    def print_detailed_report(self, report: Dict[str, Any]):
        """Print formatted detailed report."""
        print("\n" + "=" * 80)
        print("🇱🇮 COMPREHENSIVE LIECHTENSTEIN ANALYSIS REPORT")
        print("=" * 80)
        print(f"Generated: {report['analysis_date'][:19]}")
        print(f"Period: {report['period_days']} days")
        print(f"Articles Analyzed: {report['total_articles_analyzed']}")
        print(f"Data Sources: {report['data_sources']}")

        # Executive Summary
        summary = report['executive_summary']
        print(f"\n📋 EXECUTIVE SUMMARY")
        print("-" * 40)
        print(f"Overall Economic Sentiment: {summary['overall_economic_sentiment']}/100")
        print(f"Global Perception Index: {summary['gpi_score']}/100")
        print(f"Data Quality: {summary['data_quality']}")
        print(f"\nKey Findings:")
        for finding in summary['key_findings']:
            print(f"  {finding}")
        print(f"\nRisk Factors:")
        for risk in summary['risk_factors']:
            print(f"  • {risk}")
        print(f"\nRecommendation: {summary['recommendation']}")

        # Detailed Sections
        sections = report['sections']

        print(f"\n💰 ECONOMIC ANALYSIS")
        print("-" * 40)
        econ = sections.get('economic', {})
        print(f"Sentiment Score: {econ.get('sentiment_score', 0)}/100")
        print(f"Confidence: {econ.get('confidence', 0):.2f}")
        print(f"Assessment: {econ.get('assessment', 'No data')}")

        print(f"\n👥 EMPLOYMENT ANALYSIS")
        print("-" * 40)
        jobs = sections.get('jobs', {})
        print(f"Sentiment Score: {jobs.get('sentiment_score', 0)}/100")
        print(f"Assessment: {jobs.get('assessment', 'No data')}")

        print(f"\n📦 COMMODITIES ANALYSIS")
        print("-" * 40)
        commodities = sections.get('commodities', {})
        print(f"Assessment: {commodities.get('assessment', 'No data')}")

        print(f"\n💱 CURRENCY/FX ANALYSIS")
        print("-" * 40)
        fx = sections.get('fx', {})
        print(f"Currency: {fx.get('currency', 'N/A')}")
        print(f"Assessment: {fx.get('assessment', 'No data')}")

        print(f"\n🌍 GLOBAL PERCEPTION INDEX")
        print("-" * 40)
        gpi = sections.get('gpi', {})
        print(f"Overall Score: {gpi.get('overall_score', 0)}/100")
        print(f"Observer Countries: {gpi.get('observer_count', 0)}")
        print(f"Assessment: {gpi.get('assessment', 'No data')}")

        if gpi.get('top_observers'):
            print("Top Observer Countries:")
            for obs in gpi['top_observers']:
                print(f"  {obs['country']}: {obs['sentiment']}/100 ({obs['articles']} articles)")

        print("\n" + "=" * 80)


def main():
    """Generate comprehensive Liechtenstein report."""
    api_key = "BAV2J2VwecIEtxHVm1zOMGERfU52TA88zmW43Fbw"

    generator = LiechtensteinReportGenerator(api_key)
    report = generator.generate_comprehensive_report(days_back=30)

    generator.print_detailed_report(report)

    # Save report to file
    output_file = f"liechtenstein_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2, default=str)

    print(f"\n💾 Report saved to: {output_file}")


if __name__ == "__main__":
    main()