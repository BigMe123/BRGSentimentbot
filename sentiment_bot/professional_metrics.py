"""Professional metrics and reporting for sentiment analysis."""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import numpy as np
import logging

logger = logging.getLogger(__name__)

class ProfessionalMetrics:
    """Collect and report professional metrics."""
    
    def __init__(self, output_dir: str = "output"):
        """Initialize metrics collector."""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        self.run_metrics = {}
        self.article_metrics = []
    
    def emit_run_summary(
        self,
        run_id: str,
        config: Dict,
        results: Dict,
        articles: List[Dict],
        performance: Dict
    ) -> str:
        """Emit comprehensive run summary.
        
        Returns:
            Path to summary file
        """
        
        # Calculate metrics
        metrics = self._calculate_metrics(results, articles, performance)
        
        # Create summary
        summary = {
            'run_id': run_id,
            'timestamp': datetime.now().isoformat(),
            'configuration': config,
            'metrics': metrics,
            'results': results,
            'performance': performance
        }
        
        # Write summary JSON
        summary_path = self.output_dir / f"run_summary_{run_id}.json"
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        # Write articles JSONL
        articles_path = self.output_dir / f"articles_{run_id}.jsonl"
        with open(articles_path, 'w') as f:
            for article in articles:
                f.write(json.dumps(article, default=str) + '\n')
        
        # Generate dashboard
        self._generate_dashboard(metrics, summary_path)
        
        logger.info(f"Metrics written to {summary_path}")
        return str(summary_path)
    
    def _calculate_metrics(
        self,
        results: Dict,
        articles: List[Dict],
        performance: Dict
    ) -> Dict:
        """Calculate comprehensive metrics."""
        
        # Quality metrics
        sentiments = [a.get('sentiment_score', 0) for a in articles if 'sentiment_score' in a]
        confidences = [a.get('confidence', 0) for a in articles if 'confidence' in a]
        abstained = [a for a in articles if a.get('abstained', False)]
        
        # Coverage metrics
        domains = set(a.get('domain') for a in articles if a.get('domain'))
        languages = set(a.get('language', 'en') for a in articles)
        countries = set(a.get('country') for a in articles if a.get('country'))
        
        # Clustering metrics
        cluster_ids = [a.get('cluster_id') for a in articles if 'cluster_id' in a]
        unique_clusters = len(set(cluster_ids)) if cluster_ids else 0
        
        # Aspect metrics
        all_aspects = []
        for article in articles:
            if 'aspects' in article:
                all_aspects.extend(article['aspects'])
        
        positive_aspects = [a for a in all_aspects if a.get('sentiment_label') == 'positive']
        negative_aspects = [a for a in all_aspects if a.get('sentiment_label') == 'negative']
        
        metrics = {
            # Quality
            'total_articles': len(articles),
            'analyzed_articles': len(sentiments),
            'abstain_rate': len(abstained) / len(articles) if articles else 0,
            'confidence_avg': np.mean(confidences) if confidences else 0,
            'confidence_std': np.std(confidences) if confidences else 0,
            'confidence_histogram': self._histogram(confidences, bins=5),
            
            # Sentiment
            'sentiment_avg': np.mean(sentiments) if sentiments else 0,
            'sentiment_std': np.std(sentiments) if sentiments else 0,
            'sentiment_positive': sum(1 for s in sentiments if s > 0.1),
            'sentiment_negative': sum(1 for s in sentiments if s < -0.1),
            'sentiment_neutral': sum(1 for s in sentiments if -0.1 <= s <= 0.1),
            
            # Coverage
            'unique_domains': len(domains),
            'unique_languages': len(languages),
            'unique_countries': len(countries),
            'diversity_score': self._calculate_diversity(domains, languages, countries),
            
            # Clustering
            'clusters_found': unique_clusters,
            'deduplication_rate': 1 - (unique_clusters / len(articles)) if articles else 0,
            
            # Aspects
            'total_aspects': len(all_aspects),
            'unique_aspects': len(set(a.get('text') for a in all_aspects)),
            'positive_aspects_count': len(positive_aspects),
            'negative_aspects_count': len(negative_aspects),
            'top_positive_aspects': self._top_aspects(positive_aspects, 5),
            'top_negative_aspects': self._top_aspects(negative_aspects, 5),
            
            # Performance
            'fetch_success_rate': performance.get('fetch_success_rate', 0),
            'freshness_rate': performance.get('freshness_rate', 0),
            'fresh_words': performance.get('fresh_words', 0),
            'processing_time': performance.get('processing_time', 0),
            'articles_per_second': len(articles) / performance.get('processing_time', 1)
        }
        
        return metrics
    
    def _histogram(self, values: List[float], bins: int = 5) -> Dict:
        """Create histogram data."""
        if not values:
            return {}
        
        hist, edges = np.histogram(values, bins=bins)
        
        return {
            f"{edges[i]:.2f}-{edges[i+1]:.2f}": int(hist[i])
            for i in range(len(hist))
        }
    
    def _calculate_diversity(
        self,
        domains: set,
        languages: set,
        countries: set
    ) -> float:
        """Calculate diversity score (0-1)."""
        
        # Simple diversity calculation
        domain_score = min(len(domains) / 10, 1.0)  # Cap at 10
        language_score = min(len(languages) / 5, 1.0)  # Cap at 5
        country_score = min(len(countries) / 10, 1.0)  # Cap at 10
        
        return (domain_score + language_score + country_score) / 3
    
    def _top_aspects(self, aspects: List[Dict], limit: int = 5) -> List[Dict]:
        """Get top aspects by importance."""
        
        if not aspects:
            return []
        
        # Sort by importance
        sorted_aspects = sorted(
            aspects,
            key=lambda a: a.get('importance', 0),
            reverse=True
        )
        
        # Deduplicate and return top
        seen = set()
        top = []
        for aspect in sorted_aspects:
            text = aspect.get('text', '')
            if text not in seen:
                seen.add(text)
                top.append({
                    'text': text,
                    'sentiment': aspect.get('sentiment_score', 0),
                    'importance': aspect.get('importance', 0)
                })
                if len(top) >= limit:
                    break
        
        return top
    
    def _generate_dashboard(self, metrics: Dict, summary_path: Path):
        """Generate dashboard output."""
        
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        from rich.layout import Layout
        from rich import box
        
        # Create dashboard file
        dashboard_path = summary_path.parent / f"dashboard_{summary_path.stem}.txt"
        
        console = Console(record=True)
        
        # Title
        console.print(Panel.fit(
            "[bold cyan]BSG Bot Professional Analytics Dashboard[/bold cyan]",
            box=box.DOUBLE
        ))
        
        # Quality Metrics
        quality_table = Table(title="Quality Metrics", box=box.ROUNDED)
        quality_table.add_column("Metric", style="cyan")
        quality_table.add_column("Value", style="yellow")
        
        quality_table.add_row("Total Articles", str(metrics['total_articles']))
        quality_table.add_row("Analyzed", str(metrics['analyzed_articles']))
        quality_table.add_row("Abstain Rate", f"{metrics['abstain_rate']:.1%}")
        quality_table.add_row("Avg Confidence", f"{metrics['confidence_avg']:.2f}")
        quality_table.add_row("Clusters Found", str(metrics['clusters_found']))
        quality_table.add_row("Dedup Rate", f"{metrics['deduplication_rate']:.1%}")
        
        console.print(quality_table)
        
        # Sentiment Distribution
        sent_table = Table(title="Sentiment Analysis", box=box.ROUNDED)
        sent_table.add_column("Category", style="cyan")
        sent_table.add_column("Count", style="yellow")
        sent_table.add_column("Percentage", style="green")
        
        total = metrics['sentiment_positive'] + metrics['sentiment_negative'] + metrics['sentiment_neutral']
        if total > 0:
            sent_table.add_row(
                "Positive",
                str(metrics['sentiment_positive']),
                f"{metrics['sentiment_positive']/total:.1%}"
            )
            sent_table.add_row(
                "Negative",
                str(metrics['sentiment_negative']),
                f"{metrics['sentiment_negative']/total:.1%}"
            )
            sent_table.add_row(
                "Neutral",
                str(metrics['sentiment_neutral']),
                f"{metrics['sentiment_neutral']/total:.1%}"
            )
        
        console.print(sent_table)
        
        # Confidence Histogram
        if metrics.get('confidence_histogram'):
            conf_table = Table(title="Confidence Distribution", box=box.SIMPLE)
            conf_table.add_column("Range", style="cyan")
            conf_table.add_column("Count", style="yellow")
            conf_table.add_column("Bar", style="green")
            
            max_count = max(metrics['confidence_histogram'].values(), default=1)
            for range_str, count in metrics['confidence_histogram'].items():
                bar_length = int(20 * count / max_count)
                bar = "█" * bar_length
                conf_table.add_row(range_str, str(count), bar)
            
            console.print(conf_table)
        
        # Coverage Metrics
        coverage_table = Table(title="Coverage & Diversity", box=box.ROUNDED)
        coverage_table.add_column("Metric", style="cyan")
        coverage_table.add_column("Value", style="yellow")
        
        coverage_table.add_row("Unique Domains", str(metrics['unique_domains']))
        coverage_table.add_row("Languages", str(metrics['unique_languages']))
        coverage_table.add_row("Countries", str(metrics['unique_countries']))
        coverage_table.add_row("Diversity Score", f"{metrics['diversity_score']:.2f}")
        coverage_table.add_row("Freshness Rate", f"{metrics['freshness_rate']:.1%}")
        coverage_table.add_row("Fresh Words", f"{metrics['fresh_words']:,}")
        
        console.print(coverage_table)
        
        # Top Aspects
        if metrics.get('top_positive_aspects'):
            pos_table = Table(title="Top Positive Aspects", box=box.SIMPLE)
            pos_table.add_column("Aspect", style="green")
            pos_table.add_column("Score", style="yellow")
            
            for aspect in metrics['top_positive_aspects']:
                pos_table.add_row(aspect['text'], f"{aspect['sentiment']:.2f}")
            
            console.print(pos_table)
        
        if metrics.get('top_negative_aspects'):
            neg_table = Table(title="Top Negative Aspects", box=box.SIMPLE)
            neg_table.add_column("Aspect", style="red")
            neg_table.add_column("Score", style="yellow")
            
            for aspect in metrics['top_negative_aspects']:
                neg_table.add_row(aspect['text'], f"{aspect['sentiment']:.2f}")
            
            console.print(neg_table)
        
        # Save dashboard
        with open(dashboard_path, 'w') as f:
            f.write(console.export_text())
        
        logger.info(f"Dashboard saved to {dashboard_path}")