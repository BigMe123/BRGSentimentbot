"""
Content filtering: freshness, deduplication, and skew control.
Implements Phase 2 of the performance optimization plan.
"""

import hashlib
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set, Tuple, Any
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from dataclasses import dataclass, field
import logging
from collections import defaultdict, Counter
import mmh3  # MurmurHash3 for fast hashing
from datasketch import MinHash, MinHashLSH  # For near-duplicate detection

logger = logging.getLogger(__name__)


@dataclass
class ArticleMetadata:
    """Enhanced article metadata for filtering."""

    url: str
    canonical_url: str
    domain: str
    title: str
    text: str
    published: Optional[datetime]
    word_count: int
    content_hash: str
    minhash: Optional[MinHash] = None
    fetch_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    analysis_weight: float = 1.0


class ContentFilter:
    """
    Manages content freshness, deduplication, and source skew.

    Features:
    - 24h freshness horizon with configurable boost/decay
    - URL canonicalization and content-hash dedup
    - Near-duplicate detection with MinHash LSH
    - Per-domain caps and word share limits
    """

    def __init__(
        self,
        freshness_hours: int = 24,
        boost_hours: int = 6,
        decay_hours: int = 48,
        max_docs_per_domain: int = 10,
        max_domain_word_share: float = 0.15,
        max_doc_words: int = 5000,
        near_dup_threshold: float = 0.9,
        enable_near_dup: bool = True,
    ):
        self.freshness_hours = freshness_hours
        self.boost_hours = boost_hours
        self.decay_hours = decay_hours
        self.max_docs_per_domain = max_docs_per_domain
        self.max_domain_word_share = max_domain_word_share
        self.max_doc_words = max_doc_words
        self.near_dup_threshold = near_dup_threshold
        self.enable_near_dup = enable_near_dup

        # Deduplication structures
        self.seen_urls: Set[str] = set()
        self.seen_content: Dict[str, str] = {}  # content_hash -> canonical_url
        self.domain_counts: Dict[str, int] = defaultdict(int)
        self.domain_words: Dict[str, int] = defaultdict(int)

        # Near-duplicate detection with LSH
        if enable_near_dup:
            self.lsh = MinHashLSH(threshold=near_dup_threshold, num_perm=128)
            self.minhash_cache: Dict[str, MinHash] = {}

        # Stats
        self.stats = {
            "total_articles": 0,
            "fresh_articles": 0,
            "stale_articles": 0,
            "url_duplicates": 0,
            "content_duplicates": 0,
            "near_duplicates": 0,
            "domain_capped": 0,
            "word_capped": 0,
            "filtered_total": 0,
        }

    def canonicalize_url(self, url: str) -> str:
        """
        Canonicalize URL by removing tracking params and normalizing.
        """
        # Parse URL
        parsed = urlparse(url)

        # Remove common tracking parameters
        tracking_params = {
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "utm_term",
            "utm_content",
            "fbclid",
            "gclid",
            "ref",
            "source",
            "sr_share",
            "sfmc_id",
            "sfmc",
            "_ga",
            "_gid",
            "mc_cid",
            "mc_eid",
            "mkt_tok",
        }

        if parsed.query:
            params = parse_qs(parsed.query, keep_blank_values=True)
            cleaned_params = {
                k: v for k, v in params.items() if k.lower() not in tracking_params
            }
            new_query = urlencode(cleaned_params, doseq=True)
        else:
            new_query = ""

        # Normalize scheme and host
        scheme = "https" if parsed.scheme in ("https", "http") else parsed.scheme
        host = parsed.hostname.lower() if parsed.hostname else ""

        # Remove www. prefix
        if host.startswith("www."):
            host = host[4:]

        # Rebuild URL
        canonical = urlunparse(
            (
                scheme,
                host
                + (
                    f":{parsed.port}"
                    if parsed.port and parsed.port not in (80, 443)
                    else ""
                ),
                parsed.path.rstrip("/") or "/",
                "",
                new_query,
                "",
            )
        )

        return canonical

    def compute_content_hash(self, text: str, length: int = 2000) -> str:
        """
        Compute a stable hash of content for deduplication.
        Uses first N chars after normalization.
        """
        # Normalize text: lowercase, remove extra whitespace
        normalized = re.sub(r"\s+", " ", text.lower().strip())

        # Take stable slice
        slice_text = normalized[:length]

        # Fast hash with MurmurHash3
        hash_value = mmh3.hash128(slice_text)

        return f"{hash_value:032x}"

    def compute_minhash(self, text: str) -> MinHash:
        """
        Compute MinHash signature for near-duplicate detection.
        """
        # Tokenize into shingles (3-grams)
        text_lower = text.lower()
        words = text_lower.split()
        shingles = [" ".join(words[i : i + 3]) for i in range(len(words) - 2)]

        # Create MinHash
        minhash = MinHash(num_perm=128)
        for shingle in shingles:
            minhash.update(shingle.encode("utf-8"))

        return minhash

    def check_freshness(self, published: Optional[datetime]) -> Tuple[bool, float]:
        """
        Check if article is fresh and compute freshness weight.

        Returns:
            Tuple of (is_fresh, weight)
        """
        if published is None:
            # No timestamp - assume current and log
            logger.debug("Article has no timestamp, assuming current")
            return True, 1.0

        now = datetime.now(timezone.utc)

        # Ensure published is timezone-aware
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)

        age_hours = (now - published).total_seconds() / 3600

        # Check freshness horizon
        is_fresh = age_hours <= self.freshness_hours

        # Compute weight with boost/decay
        if age_hours <= self.boost_hours:
            weight = 1.2  # Boost recent articles
        elif age_hours <= self.freshness_hours:
            weight = 1.0  # Normal weight
        elif age_hours <= self.decay_hours:
            # Linear decay from 1.0 to 0.1
            decay_range = self.decay_hours - self.freshness_hours
            decay_progress = (age_hours - self.freshness_hours) / decay_range
            weight = 1.0 - (0.9 * decay_progress)
        else:
            weight = 0.1  # Minimal weight for very old

        return is_fresh, weight

    def check_duplicate(self, article: ArticleMetadata) -> Optional[str]:
        """
        Check for duplicates using multiple strategies.

        Returns:
            Duplicate type if found, None otherwise
        """
        # URL deduplication
        if article.canonical_url in self.seen_urls:
            self.stats["url_duplicates"] += 1
            return "url_duplicate"

        # Content hash deduplication
        if article.content_hash in self.seen_content:
            self.stats["content_duplicates"] += 1
            return "content_duplicate"

        # Near-duplicate detection with MinHash
        if self.enable_near_dup and article.minhash:
            # Query LSH for similar documents
            similar = self.lsh.query(article.minhash)
            if similar:
                self.stats["near_duplicates"] += 1
                return "near_duplicate"

        return None

    def check_domain_caps(self, domain: str, word_count: int) -> Tuple[bool, float]:
        """
        Check domain caps and compute weight.

        Returns:
            Tuple of (is_allowed, weight)
        """
        # Check document count cap
        if self.domain_counts[domain] >= self.max_docs_per_domain:
            self.stats["domain_capped"] += 1
            return False, 0.0

        # Compute word share weight
        total_words = sum(self.domain_words.values())
        if total_words > 0:
            current_share = self.domain_words[domain] / total_words
            target_share = self.max_domain_word_share

            if current_share > target_share:
                # Reduce weight proportionally
                weight = min(1.0, target_share / current_share)
            else:
                weight = 1.0
        else:
            weight = 1.0

        return True, weight

    def filter_and_weight(
        self, articles: List[Dict[str, Any]]
    ) -> List[ArticleMetadata]:
        """
        Filter articles for freshness, duplicates, and skew.
        Returns filtered and weighted articles.
        """
        filtered = []

        for article_data in articles:
            self.stats["total_articles"] += 1

            # Parse article data
            url = article_data.get("url", "")
            title = article_data.get("title", "")
            text = article_data.get("text", "")
            published = article_data.get("published")

            if not url or not text:
                continue

            # Parse published date if string
            if isinstance(published, str):
                try:
                    published = datetime.fromisoformat(published)
                except:
                    published = None

            # Canonicalize URL
            canonical_url = self.canonicalize_url(url)
            domain = urlparse(canonical_url).netloc

            # Cap document words
            if len(text.split()) > self.max_doc_words:
                text = " ".join(text.split()[: self.max_doc_words])
                self.stats["word_capped"] += 1

            word_count = len(text.split())

            # Compute hashes
            content_hash = self.compute_content_hash(text)
            minhash = self.compute_minhash(text) if self.enable_near_dup else None

            # Create metadata
            article = ArticleMetadata(
                url=url,
                canonical_url=canonical_url,
                domain=domain,
                title=title,
                text=text,
                published=published,
                word_count=word_count,
                content_hash=content_hash,
                minhash=minhash,
            )

            # Check freshness
            is_fresh, freshness_weight = self.check_freshness(published)
            if not is_fresh:
                self.stats["stale_articles"] += 1
                self.stats["filtered_total"] += 1
                logger.debug(f"Filtered stale article: {url}")
                continue

            self.stats["fresh_articles"] += 1

            # Check duplicates
            dup_type = self.check_duplicate(article)
            if dup_type:
                self.stats["filtered_total"] += 1
                logger.debug(f"Filtered {dup_type}: {url}")
                continue

            # Check domain caps
            is_allowed, domain_weight = self.check_domain_caps(domain, word_count)
            if not is_allowed:
                self.stats["filtered_total"] += 1
                logger.debug(f"Filtered domain capped: {url}")
                continue

            # Compute final weight
            article.analysis_weight = freshness_weight * domain_weight

            # Update tracking
            self.seen_urls.add(canonical_url)
            self.seen_content[content_hash] = canonical_url
            self.domain_counts[domain] += 1
            self.domain_words[domain] += word_count

            if self.enable_near_dup and minhash:
                self.lsh.insert(canonical_url, minhash)
                self.minhash_cache[canonical_url] = minhash

            filtered.append(article)

        # Log stats
        logger.info(
            f"Content filter: {len(filtered)}/{self.stats['total_articles']} passed "
            f"(fresh={self.stats['fresh_articles']}, "
            f"dup_url={self.stats['url_duplicates']}, "
            f"dup_content={self.stats['content_duplicates']}, "
            f"near_dup={self.stats['near_duplicates']}, "
            f"domain_cap={self.stats['domain_capped']})"
        )

        return filtered

    def get_stats(self) -> Dict[str, Any]:
        """Get filter statistics."""
        stats = self.stats.copy()

        # Add computed metrics
        if stats["total_articles"] > 0:
            stats["fresh_rate"] = stats["fresh_articles"] / stats["total_articles"]
            stats["filter_rate"] = stats["filtered_total"] / stats["total_articles"]

        # Domain distribution
        stats["unique_domains"] = len(self.domain_counts)
        stats["avg_docs_per_domain"] = (
            sum(self.domain_counts.values()) / len(self.domain_counts)
            if self.domain_counts
            else 0
        )

        # Word share distribution
        total_words = sum(self.domain_words.values())
        if total_words > 0:
            word_shares = {
                domain: words / total_words
                for domain, words in self.domain_words.items()
            }
            sorted_shares = sorted(
                word_shares.items(), key=lambda x: x[1], reverse=True
            )

            stats["top1_word_share"] = sorted_shares[0][1] if sorted_shares else 0
            stats["top3_word_share"] = sum(s[1] for s in sorted_shares[:3])
            stats["top1_domain"] = sorted_shares[0][0] if sorted_shares else None

        return stats
