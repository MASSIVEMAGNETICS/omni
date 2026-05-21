#!/usr/bin/env python3
"""
Shared Memory Graph for Omnirepo

Unified semantic + episodic memory system with REM-style consolidation.

Features:
- Episodic + Semantic nodes
- Embedding-based semantic linking
- REM-style memory consolidation (high-importance memories are strengthened and abstracted)
"""

from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import numpy as np

try:
    from sentence_transformers import SentenceTransformer
    HAS_EMBEDDINGS = True
except ImportError:
    HAS_EMBEDDINGS = False


@dataclass
class MemoryNode:
    id: str
    type: str  # "episode" | "concept" | "semantic"
    content: Dict[str, Any]
    timestamp: str
    importance: float = 0.5
    tags: List[str] = field(default_factory=list)
    embedding: Optional[np.ndarray] = None
    source: str = "unknown"


class SharedMemoryGraph:
    def __init__(self, max_nodes: int = 1000, embedding_model: str = "all-MiniLM-L6-v2"):
        self.nodes: Dict[str, MemoryNode] = {}
        self.edges: List[Dict] = []
        self.max_nodes = max_nodes
        self.embedder = None

        if HAS_EMBEDDINGS:
            try:
                self.embedder = SentenceTransformer(embedding_model)
                print("[SharedMemory] Embedding model loaded")
            except Exception as e:
                print(f"[SharedMemory] Could not load embeddings: {e}")

    def add_event(self, content: Dict[str, Any], source: str = "unknown", importance: float = 0.6) -> str:
        node_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        text = str(content)[:300]
        embedding = None
        if self.embedder:
            embedding = self.embedder.encode(text, normalize_embeddings=True)

        node = MemoryNode(
            id=node_id, type="episode", content=content,
            timestamp=timestamp, importance=importance,
            embedding=embedding, source=source
        )
        self.nodes[node_id] = node

        if embedding is not None:
            self._link_similar(node_id, embedding)

        if len(self.nodes) > self.max_nodes:
            self._prune_oldest()

        return node_id

    def _link_similar(self, new_id: str, new_embedding: np.ndarray, threshold: float = 0.72):
        for node_id, node in self.nodes.items():
            if node_id == new_id or node.embedding is None:
                continue
            similarity = np.dot(new_embedding, node.embedding)
            if similarity >= threshold:
                self.edges.append({
                    "source": new_id, "target": node_id,
                    "relation": "semantic_similarity", "weight": float(similarity)
                })

    def consolidate(self, min_importance: float = 0.7):
        """
        REM-style memory consolidation.

        - High-importance episodic memories are strengthened and abstracted into semantic nodes.
        - Low-importance or redundant memories are pruned or downgraded.
        - Connections between important memories are reinforced.
        """
        print("[SharedMemory] Running REM-style memory consolidation...")

        high_importance = [n for n in self.nodes.values() if n.importance >= min_importance and n.type == "episode"]

        for node in high_importance:
            # Strengthen importance (like memory rehearsal)
            node.importance = min(1.0, node.importance + 0.1)

            # Create or link to semantic concept
            concept_text = str(node.content)[:100]
            concept_id = self._get_or_create_semantic_node(concept_text)

            self.edges.append({
                "source": node.id,
                "target": concept_id,
                "relation": "consolidated_to",
                "weight": 0.9
            })

        # Downgrade or prune low-importance old episodes
        now = datetime.now(timezone.utc)
        for node in list(self.nodes.values()):
            if node.type == "episode" and node.importance < 0.4:
                # Simulate memory decay
                node.importance *= 0.85
                if node.importance < 0.2:
                    self._prune_node(node.id)

        print(f"[SharedMemory] Consolidation complete. Nodes: {len(self.nodes)}, Edges: {len(self.edges)}")

    def _get_or_create_semantic_node(self, text: str) -> str:
        for node in self.nodes.values():
            if node.type == "semantic" and text[:50] in str(node.content):
                return node.id

        node_id = str(uuid.uuid4())
        node = MemoryNode(
            id=node_id,
            type="semantic",
            content={"concept": text},
            timestamp=datetime.now(timezone.utc).isoformat(),
            importance=0.8
        )
        self.nodes[node_id] = node
        return node_id

    def query_context(self, max_nodes: int = 8) -> Dict[str, Any]:
        recent = list(self.nodes.values())[-max_nodes:]
        return {
            "total_nodes": len(self.nodes),
            "recent_events": len(recent),
            "summary": self._generate_summary(recent)
        }

    def _generate_summary(self, nodes: List[MemoryNode]) -> str:
        parts = []
        for n in nodes[-3:]:
            if n.source == "ai_ear":
                parts.append("Heard acoustic event")
            elif n.source == "victor_zero":
                parts.append("Cognitive reflection")
        return " | ".join(parts) if parts else "No recent activity"

    def get_stats(self) -> Dict:
        return {
            "total_nodes": len(self.nodes),
            "edges": len(self.edges),
            "embedding_enabled": self.embedder is not None
        }

    def _prune_oldest(self):
        if not self.nodes:
            return
        oldest = min(self.nodes.keys(), key=lambda k: self.nodes[k].timestamp)
        del self.nodes[oldest]
        self.edges = [e for e in self.edges if e["source"] != oldest and e["target"] != oldest]

    def _prune_node(self, node_id: str):
        if node_id in self.nodes:
            del self.nodes[node_id]
        self.edges = [e for e in self.edges if e["source"] != node_id and e["target"] != node_id]