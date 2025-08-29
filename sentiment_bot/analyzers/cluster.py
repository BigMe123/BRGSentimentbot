"""Document clustering for deduplication and summarization."""

import numpy as np
from typing import List, Dict, Optional, Tuple
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics.pairwise import cosine_similarity
import logging

logger = logging.getLogger(__name__)

class DocumentClusterer:
    """Cluster similar documents to reduce redundancy."""
    
    def __init__(self, config: Dict = None):
        """Initialize clusterer."""
        self.config = config or {}
        self.cosine_threshold = self.config.get('cosine_threshold', 0.78)
        self.min_cluster_size = self.config.get('min_cluster_size', 2)
        self.model_name = self.config.get('model', 'sentence-transformers/all-MiniLM-L6-v2')
        
        self._embedder = None
    
    def _get_embedder(self):
        """Lazy load sentence transformer."""
        if self._embedder is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._embedder = SentenceTransformer(self.model_name)
            except ImportError:
                logger.error("sentence-transformers not installed. Installing...")
                import subprocess
                subprocess.run(["pip", "install", "sentence-transformers"])
                from sentence_transformers import SentenceTransformer
                self._embedder = SentenceTransformer(self.model_name)
        return self._embedder
    
    def cluster_articles(self, articles: List[Dict]) -> List[Dict]:
        """Cluster articles and add cluster IDs.
        
        Args:
            articles: List of article dicts with 'title' and 'description'
            
        Returns:
            Articles with 'cluster_id' added
        """
        if len(articles) < 2:
            # No clustering needed
            for i, article in enumerate(articles):
                article['cluster_id'] = i
            return articles
        
        # Create text representations
        texts = []
        for article in articles:
            # Combine title and description for embedding
            title = article.get('title', '')
            desc = article.get('description', '')[:200]  # First 200 chars
            text = f"{title}. {desc}"
            texts.append(text)
        
        # Get embeddings
        embeddings = self._get_embeddings(texts)
        
        # Cluster
        cluster_ids = self._cluster_embeddings(embeddings)
        
        # Add cluster IDs to articles
        for article, cluster_id in zip(articles, cluster_ids):
            article['cluster_id'] = int(cluster_id)
        
        return articles
    
    def _get_embeddings(self, texts: List[str]) -> np.ndarray:
        """Get embeddings for texts."""
        embedder = self._get_embedder()
        
        # Batch encode
        embeddings = embedder.encode(
            texts,
            batch_size=32,
            show_progress_bar=False,
            convert_to_numpy=True
        )
        
        return embeddings
    
    def _cluster_embeddings(self, embeddings: np.ndarray) -> np.ndarray:
        """Cluster embeddings using agglomerative clustering."""
        
        # Calculate similarity matrix
        similarities = cosine_similarity(embeddings)
        
        # Convert to distance matrix
        distances = 1 - similarities
        
        # Perform clustering
        clustering = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=1 - self.cosine_threshold,
            metric='precomputed',
            linkage='average'
        )
        
        cluster_ids = clustering.fit_predict(distances)
        
        return cluster_ids
    
    def get_cluster_representatives(self, articles: List[Dict]) -> Dict[int, Dict]:
        """Get representative article for each cluster.
        
        Returns:
            Dict mapping cluster_id to representative article
        """
        clusters = {}
        
        for article in articles:
            cluster_id = article.get('cluster_id', -1)
            
            if cluster_id not in clusters:
                clusters[cluster_id] = []
            clusters[cluster_id].append(article)
        
        representatives = {}
        for cluster_id, cluster_articles in clusters.items():
            # Choose article with longest content as representative
            # Could also use centroid in embedding space
            representative = max(
                cluster_articles,
                key=lambda a: len(a.get('description', '') + a.get('content', ''))
            )
            representatives[cluster_id] = representative
        
        return representatives
    
    def summarize_cluster(self, articles: List[Dict]) -> Dict:
        """Create summary for a cluster of articles.
        
        Returns:
            Cluster summary with citations
        """
        if not articles:
            return {}
        
        # Sort by content length (prefer longer articles)
        articles.sort(key=lambda a: len(a.get('content', a.get('description', ''))), reverse=True)
        
        # Take top 3 for citations
        top_articles = articles[:3]
        
        # Extract key points from each article
        key_points = []
        for article in top_articles:
            title = article.get('title', '')
            if title:
                key_points.append(title)
        
        # Create cluster summary
        summary = {
            'size': len(articles),
            'key_points': key_points[:3],
            'sources': [
                {
                    'title': a.get('title', 'Untitled'),
                    'domain': a.get('domain', 'Unknown'),
                    'link': a.get('link', '')
                }
                for a in top_articles
            ],
            'cluster_sentiment': self._aggregate_cluster_sentiment(articles),
            'earliest_date': min(
                (a.get('published_date') for a in articles if a.get('published_date')),
                default=None
            )
        }
        
        return summary
    
    def _aggregate_cluster_sentiment(self, articles: List[Dict]) -> Dict:
        """Aggregate sentiment across cluster."""
        
        sentiments = []
        for article in articles:
            if 'sentiment_score' in article:
                sentiments.append(article['sentiment_score'])
        
        if not sentiments:
            return {'score': 0.0, 'label': 'neutral'}
        
        avg_sentiment = np.mean(sentiments)
        
        if avg_sentiment > 0.1:
            label = 'positive'
        elif avg_sentiment < -0.1:
            label = 'negative'
        else:
            label = 'neutral'
        
        return {
            'score': float(avg_sentiment),
            'label': label,
            'std_dev': float(np.std(sentiments))
        }
    
    def deduplicate_by_clusters(self, articles: List[Dict]) -> Tuple[List[Dict], int]:
        """Remove duplicates keeping one per cluster.
        
        Returns:
            (deduplicated articles, number removed)
        """
        # First cluster
        articles = self.cluster_articles(articles)
        
        # Get representatives
        representatives = self.get_cluster_representatives(articles)
        
        # Keep only representatives
        deduped = list(representatives.values())
        removed = len(articles) - len(deduped)
        
        return deduped, removed