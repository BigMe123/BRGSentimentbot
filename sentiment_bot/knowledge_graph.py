"""Knowledge graph construction and GNN embeddings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Tuple

import networkx as nx
import numpy as np
import torch
from torch_geometric.data import Data
from torch_geometric.nn import GCNConv


@dataclass
class KnowledgeGraph:
    graph: nx.Graph


def ingest_triples(triples: Iterable[Tuple[str, str, str]]) -> KnowledgeGraph:
    g = nx.Graph()
    for head, relation, tail in triples:
        g.add_edge(head, tail, relation=relation)
    return KnowledgeGraph(g)


class GraphEmbedder:
    """Learn node embeddings using a simple GCN."""

    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer

        self.text_model = SentenceTransformer("all-MiniLM-L6-v2")

    def fit(self, kg: KnowledgeGraph) -> None:
        nodes = list(kg.graph.nodes)
        x = torch.tensor(
            self.text_model.encode(nodes, convert_to_numpy=True), dtype=torch.float
        )
        edges = list(kg.graph.edges)
        if not edges:
            edge_index = torch.empty((2, 0), dtype=torch.long)
        else:
            edge_index = torch.tensor(edges, dtype=torch.long).t().contiguous()
        data = Data(x=x, edge_index=edge_index)
        conv1 = GCNConv(x.size(1), 64)
        conv2 = GCNConv(64, 64)
        h = torch.relu(conv1(data.x, data.edge_index))
        h = conv2(h, data.edge_index)
        self.embeddings = {n: h[i].detach().numpy() for i, n in enumerate(nodes)}

    def query_graph(self, question: str, topk: int = 5) -> List[Tuple[str, float]]:
        q = self.text_model.encode(question)
        scores = []
        for node, emb in self.embeddings.items():
            score = float(np.dot(q, emb) / (np.linalg.norm(q) * np.linalg.norm(emb)))
            scores.append((node, score))
        return sorted(scores, key=lambda x: x[1], reverse=True)[:topk]
