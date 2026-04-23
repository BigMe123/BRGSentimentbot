"""
Event graph construction from extracted events.

Builds a directed graph of actor relationships from ExtractedEvent objects.
Nodes are actors, edges are actions with tone/intensity metadata.
Supports querying for actor centrality, hostile/cooperative clusters,
and relationship summaries.
"""

import logging
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)

try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False


class EventGraph:
    """
    Directed multigraph of actor-action-receiver relationships.

    Each edge carries: action category, tone, intensity, domain, count.
    """

    def __init__(self):
        if not HAS_NETWORKX:
            raise ImportError("networkx required: pip install networkx")
        self.graph = nx.DiGraph()
        self._edge_details = defaultdict(list)  # (actor, receiver) -> [event dicts]

    def add_events(self, events) -> int:
        """
        Add ExtractedEvent objects to the graph.

        Args:
            events: List of ExtractedEvent (Pydantic models)

        Returns:
            Number of edges added.
        """
        added = 0
        for event in events:
            actor = event.actor.name
            self.graph.add_node(actor, type=event.actor.type)

            if event.receiver:
                receiver = event.receiver.name
                self.graph.add_node(receiver, type=event.receiver.type)

                key = (actor, receiver)
                self._edge_details[key].append({
                    "category": event.action.category,
                    "verb": event.action.verb,
                    "tone": event.tone,
                    "intensity": event.intensity,
                    "domain": event.domain,
                    "stance": event.stance,
                })

                # Aggregate edge attributes
                details = self._edge_details[key]
                avg_tone = sum(d["tone"] for d in details) / len(details)
                self.graph.add_edge(
                    actor, receiver,
                    weight=len(details),
                    avg_tone=round(avg_tone, 2),
                    categories=[d["category"] for d in details],
                )
                added += 1

        return added

    def add_from_records(self, article_records) -> int:
        """Add events from ArticleRecord objects."""
        all_events = []
        for record in article_records:
            all_events.extend(record.events)
        return self.add_events(all_events)

    def top_actors(self, n: int = 10) -> List[Dict]:
        """
        Top actors by degree centrality.

        Returns:
            List of {actor, type, degree, in_degree, out_degree, avg_tone_received}
        """
        if not self.graph.nodes:
            return []

        centrality = nx.degree_centrality(self.graph)
        actors = []
        for node, cent in sorted(centrality.items(), key=lambda x: -x[1])[:n]:
            in_edges = self.graph.in_edges(node, data=True)
            tones = [d.get("avg_tone", 0) for _, _, d in in_edges]
            actors.append({
                "actor": node,
                "type": self.graph.nodes[node].get("type", "unknown"),
                "centrality": round(cent, 3),
                "in_degree": self.graph.in_degree(node),
                "out_degree": self.graph.out_degree(node),
                "avg_tone_received": round(sum(tones) / len(tones), 2) if tones else 0.0,
            })
        return actors

    def key_relationships(self, n: int = 10) -> List[Dict]:
        """
        Top relationships by interaction count.

        Returns:
            List of {actor, receiver, count, avg_tone, categories}
        """
        edges = []
        for (actor, receiver), details in self._edge_details.items():
            avg_tone = sum(d["tone"] for d in details) / len(details)
            cats = list(set(d["category"] for d in details))
            edges.append({
                "actor": actor,
                "receiver": receiver,
                "count": len(details),
                "avg_tone": round(avg_tone, 2),
                "categories": cats,
            })

        edges.sort(key=lambda x: x["count"], reverse=True)
        return edges[:n]

    def hostile_pairs(self, tone_threshold: float = -3.0) -> List[Dict]:
        """Find actor pairs with hostile relationships (avg tone below threshold)."""
        pairs = []
        for (actor, receiver), details in self._edge_details.items():
            avg_tone = sum(d["tone"] for d in details) / len(details)
            if avg_tone <= tone_threshold:
                pairs.append({
                    "actor": actor,
                    "receiver": receiver,
                    "avg_tone": round(avg_tone, 2),
                    "count": len(details),
                    "actions": [d["verb"] for d in details],
                })
        pairs.sort(key=lambda x: x["avg_tone"])
        return pairs

    def cooperative_pairs(self, tone_threshold: float = 3.0) -> List[Dict]:
        """Find actor pairs with cooperative relationships."""
        pairs = []
        for (actor, receiver), details in self._edge_details.items():
            avg_tone = sum(d["tone"] for d in details) / len(details)
            if avg_tone >= tone_threshold:
                pairs.append({
                    "actor": actor,
                    "receiver": receiver,
                    "avg_tone": round(avg_tone, 2),
                    "count": len(details),
                    "actions": [d["verb"] for d in details],
                })
        pairs.sort(key=lambda x: -x["avg_tone"])
        return pairs

    def domain_breakdown(self) -> Dict[str, int]:
        """Count events by domain (military, economic, diplomatic, etc.)."""
        counts = defaultdict(int)
        for details in self._edge_details.values():
            for d in details:
                counts[d["domain"]] += 1
        return dict(sorted(counts.items(), key=lambda x: -x[1]))

    def to_dict(self) -> Dict:
        """Serialize graph to dict for JSON output."""
        return {
            "nodes": len(self.graph.nodes),
            "edges": len(self.graph.edges),
            "top_actors": self.top_actors(10),
            "key_relationships": self.key_relationships(10),
            "hostile_pairs": self.hostile_pairs(),
            "cooperative_pairs": self.cooperative_pairs(),
            "domain_breakdown": self.domain_breakdown(),
        }
