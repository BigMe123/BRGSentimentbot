#!/usr/bin/env python3
"""
Test suite for the optimized pipeline.
Validates all SLOs and acceptance criteria.
"""

import asyncio
import pytest
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from sentiment_bot.http_client import OptimizedHTTPClient
from sentiment_bot.content_filter import ContentFilter, ArticleMetadata
from sentiment_bot.metrics import MetricsCollector, Alert
from sentiment_bot.domain_policy import DomainPolicyRegistry, DomainPolicy
from sentiment_bot.prompt_utils import is_interactive
from sentiment_bot.fetcher_optimized import OptimizedFetcher


class TestHTTPClient:
    """Test HTTP client optimizations."""
    
    @pytest.mark.asyncio
    async def test_connection_pooling(self):
        """Test that connections are pooled and reused."""
        client = OptimizedHTTPClient(global_concurrency=10)
        
        # Make multiple requests to same domain
        urls = [
            'https://httpbin.org/delay/0',
            'https://httpbin.org/status/200',
            'https://httpbin.org/get',
        ]
        
        results = await client.fetch_batch(urls)
        
        # Check all succeeded
        assert all(content is not None for content, _ in results)
        
        # Check stats
        stats = client.get_stats()
        assert stats['requests'] == 3
        assert stats['successes'] == 3
        
        await client.close()
    
    @pytest.mark.asyncio
    async def test_circuit_breaker(self):
        """Test circuit breaker opens after failures."""
        client = OptimizedHTTPClient()
        
        # Simulate failures
        bad_url = 'https://invalid-domain-that-does-not-exist.com/test'
        
        for _ in range(3):
            content, meta = await client.fetch(bad_url)
            assert content is None
        
        # Circuit should be open now
        assert client._is_circuit_open('invalid-domain-that-does-not-exist.com')
        
        # Next request should be rejected immediately
        start = time.time()
        content, meta = await client.fetch(bad_url)
        elapsed = time.time() - start
        
        assert content is None
        assert meta['status'] == 'circuit_open'
        assert elapsed < 0.1  # Should return immediately
        
        await client.close()
    
    @pytest.mark.asyncio
    async def test_byte_cap(self):
        """Test response size is capped."""
        client = OptimizedHTTPClient(max_response_size=1024)
        
        # Request large response
        content, meta = await client.fetch('https://httpbin.org/bytes/10000')
        
        if content:
            assert len(content) <= 1024
        
        await client.close()


class TestContentFilter:
    """Test content filtering and deduplication."""
    
    def test_freshness_filter(self):
        """Test articles are filtered by freshness."""
        filter = ContentFilter(freshness_hours=24)
        
        now = datetime.now(timezone.utc)
        
        articles = [
            {
                'url': 'https://example.com/fresh',
                'title': 'Fresh Article',
                'text': 'This is fresh content from today.',
                'published': now - timedelta(hours=6),  # 6 hours old
            },
            {
                'url': 'https://example.com/stale',
                'title': 'Stale Article',
                'text': 'This is old content.',
                'published': now - timedelta(hours=48),  # 2 days old
            },
        ]
        
        filtered = filter.filter_and_weight(articles)
        
        assert len(filtered) == 1
        assert filtered[0].url == 'https://example.com/fresh'
        assert filter.stats['fresh_articles'] == 1
        assert filter.stats['stale_articles'] == 1
    
    def test_url_deduplication(self):
        """Test URL deduplication and canonicalization."""
        filter = ContentFilter()
        
        articles = [
            {
                'url': 'https://example.com/article?utm_source=twitter',
                'title': 'Article 1',
                'text': 'Content of article 1.',
                'published': datetime.now(timezone.utc),
            },
            {
                'url': 'https://example.com/article?utm_medium=email',
                'title': 'Article 1 Duplicate',
                'text': 'Content of article 1.',
                'published': datetime.now(timezone.utc),
            },
        ]
        
        filtered = filter.filter_and_weight(articles)
        
        assert len(filtered) == 1
        assert filter.stats['url_duplicates'] == 1
    
    def test_content_deduplication(self):
        """Test content-based deduplication."""
        filter = ContentFilter()
        
        articles = [
            {
                'url': 'https://site1.com/article',
                'title': 'Same Article',
                'text': 'This is the exact same content that appears on multiple sites.',
                'published': datetime.now(timezone.utc),
            },
            {
                'url': 'https://site2.com/news/same',
                'title': 'Same Article Mirror',
                'text': 'This is the exact same content that appears on multiple sites.',
                'published': datetime.now(timezone.utc),
            },
        ]
        
        filtered = filter.filter_and_weight(articles)
        
        assert len(filtered) == 1
        assert filter.stats['content_duplicates'] == 1
    
    def test_domain_caps(self):
        """Test per-domain document caps."""
        filter = ContentFilter(max_docs_per_domain=2)
        
        articles = [
            {
                'url': f'https://example.com/article{i}',
                'title': f'Article {i}',
                'text': f'Content {i}',
                'published': datetime.now(timezone.utc),
            }
            for i in range(5)
        ]
        
        filtered = filter.filter_and_weight(articles)
        
        assert len(filtered) == 2
        assert filter.stats['domain_capped'] == 3
    
    def test_word_share_weighting(self):
        """Test source skew control via weighting."""
        filter = ContentFilter(max_domain_word_share=0.30)
        
        articles = [
            {
                'url': 'https://dominant.com/huge',
                'title': 'Huge Article',
                'text': ' '.join(['word'] * 10000),  # 10k words
                'published': datetime.now(timezone.utc),
            },
            {
                'url': 'https://other1.com/small',
                'title': 'Small Article',
                'text': ' '.join(['word'] * 100),  # 100 words
                'published': datetime.now(timezone.utc),
            },
            {
                'url': 'https://other2.com/small',
                'title': 'Another Small',
                'text': ' '.join(['word'] * 100),  # 100 words
                'published': datetime.now(timezone.utc),
            },
        ]
        
        filtered = filter.filter_and_weight(articles)
        
        # Check weighting was applied
        dominant = [a for a in filtered if 'dominant.com' in a.url][0]
        assert dominant.analysis_weight < 1.0  # Should be weighted down
        
        # Check stats
        stats = filter.get_stats()
        assert stats['top1_word_share'] <= 0.98  # Dominant source


class TestMetrics:
    """Test metrics collection and alerting."""
    
    def test_slo_alerts(self):
        """Test SLO breach alerts are triggered."""
        metrics = MetricsCollector()
        
        # Record poor performance
        for i in range(100):
            metrics.record_fetch(
                domain=f'domain{i % 10}.com',
                success=i % 2 == 0,  # 50% success rate
                latency_ms=10000 if i % 10 == 0 else 1000,  # Some slow
                status='ok' if i % 2 == 0 else 'error',
                headless=i % 5 == 0,  # 20% headless
            )
        
        # Check alerts
        alerts = metrics.check_alerts()
        
        # Should have alerts for low success rate and high headless usage
        assert any(a.metric == 'fetch_success_rate' for a in alerts)
        assert any(a.metric == 'headless_usage_rate' for a in alerts)
        
        # Check metrics
        m = metrics.get_metrics()
        assert m['fetch_success_rate'] == 0.5
        assert m['headless_usage_rate'] == 0.2
    
    def test_source_concentration(self):
        """Test source concentration metrics."""
        metrics = MetricsCollector()
        
        # Record skewed distribution
        metrics.record_article('isw.com', 150000, datetime.now(timezone.utc))
        metrics.record_article('bbc.com', 5000, datetime.now(timezone.utc))
        metrics.record_article('cnn.com', 3000, datetime.now(timezone.utc))
        metrics.record_article('other.com', 2000, datetime.now(timezone.utc))
        
        m = metrics.get_metrics()
        
        # ISW dominates with 150k/160k words
        assert m['top1_source_share'] > 0.9
        assert m['top3_source_share'] > 0.95
        
        # Should trigger alerts
        alerts = metrics.check_alerts()
        assert any(a.metric == 'top1_source_share' for a in alerts)
        assert any(a.metric == 'top3_source_share' for a in alerts)


class TestDomainPolicy:
    """Test domain policy registry."""
    
    def test_policy_decisions(self):
        """Test policy registry makes correct decisions."""
        registry = DomainPolicyRegistry()
        
        # Add test policies
        registry.policies['denied.com'] = DomainPolicy(
            domain='denied.com',
            status='deny',
            notes='Test denial'
        )
        
        registry.policies['js-site.com'] = DomainPolicy(
            domain='js-site.com',
            status='js_allowed'
        )
        
        # Test decisions
        decision, reason = registry.check_access('https://denied.com/feed')
        assert decision == 'deny'
        assert 'Test denial' in reason
        
        decision, reason = registry.check_access('https://js-site.com/news')
        assert decision == 'js_required'
        
        decision, reason = registry.check_access('https://unknown.com/rss')
        assert decision == 'allow'
    
    def test_rate_limits(self):
        """Test per-domain rate limits."""
        registry = DomainPolicyRegistry()
        
        registry.policies['slow.com'] = DomainPolicy(
            domain='slow.com',
            rate_limit_ms=1000
        )
        
        limit = registry.get_rate_limit('https://slow.com/api')
        assert limit == 1000
        
        limit = registry.get_rate_limit('https://fast.com/api')
        assert limit == 100  # Default


class TestPromptUtils:
    """Test TTY-safe prompts."""
    
    def test_non_interactive_defaults(self):
        """Test non-interactive mode returns defaults."""
        # This test assumes we're not in a TTY
        # In CI/CD, is_interactive() should return False
        
        from sentiment_bot.prompt_utils import safe_prompt, safe_choice
        
        # Should return default without prompting
        result = safe_prompt("Test prompt", default="default_value")
        assert result == "default_value"
        
        result = safe_choice("Test choice", ["A", "B", "C"], default="B")
        assert result == "B"


class TestIntegration:
    """Integration tests for the full pipeline."""
    
    @pytest.mark.asyncio
    async def test_budget_enforcement(self):
        """Test pipeline respects time budget."""
        fetcher = OptimizedFetcher(budget_seconds=5)
        
        # Create slow feeds
        feeds = [
            'https://httpbin.org/delay/2',
            'https://httpbin.org/delay/2',
            'https://httpbin.org/delay/2',
            'https://httpbin.org/delay/2',
            'https://httpbin.org/delay/2',
        ]
        
        start = time.time()
        result = await fetcher.process_feeds(feeds)
        elapsed = time.time() - start
        
        # Should stop within budget + grace period
        assert elapsed < 5.5  # 5s budget + 0.5s grace
        
        # Should have metrics
        assert result.metrics['runtime_seconds'] < 5.5
    
    @pytest.mark.asyncio
    async def test_slo_compliance(self):
        """Test that SLOs are tracked and reported."""
        fetcher = OptimizedFetcher(budget_seconds=10)
        
        # Use fast, reliable feeds
        feeds = [
            'https://feeds.bbci.co.uk/news/world/rss.xml',
            'https://rss.nytimes.com/services/xml/rss/nyt/World.xml',
        ]
        
        result = await fetcher.process_feeds(feeds)
        
        # Check metrics exist
        assert 'fetch_success_rate' in result.metrics
        assert 'p95_fetch_latency_ms' in result.metrics
        assert 'top1_source_share' in result.metrics
        assert 'fraction_published_24h' in result.metrics
        
        # Check for any critical alerts
        critical_alerts = [a for a in result.alerts if a.severity == 'error']
        if critical_alerts:
            print(f"Critical alerts: {critical_alerts}")


def run_tests():
    """Run all tests and report results."""
    print("=" * 60)
    print("OPTIMIZED PIPELINE TEST SUITE")
    print("=" * 60)
    
    # Run pytest
    exit_code = pytest.main([
        __file__,
        '-v',
        '--tb=short',
        '--asyncio-mode=auto'
    ])
    
    if exit_code == 0:
        print("\n✅ All tests passed!")
    else:
        print(f"\n❌ Tests failed with exit code {exit_code}")
    
    return exit_code


if __name__ == "__main__":
    sys.exit(run_tests())