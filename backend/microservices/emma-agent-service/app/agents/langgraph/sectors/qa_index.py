"""
Sector QA Embedding Index — Trainable

Loads a fine-tuned model if available, otherwise falls back to base model.
Pre-embeds domain QA pairs at startup for fast semantic concept matching.

Model loading priority:
  1. Fine-tuned: models/{sector}/ (if exists)
  2. Base: sentence-transformers/all-MiniLM-L6-v2

Usage:
    index = get_sector_qa_index("legal")
    matches = index.search("despido disciplinario", top_k=3)
"""

import logging
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import yaml

logger = logging.getLogger(__name__)

BASE_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def _find_project_root() -> str:
    """Find project root (directory containing both 'app/' and 'config/')."""
    current = os.path.dirname(os.path.abspath(__file__))
    for _ in range(10):
        if os.path.isdir(os.path.join(current, "app")) and os.path.isdir(os.path.join(current, "config")):
            return current
        current = os.path.dirname(current)
    # Fallback: relative from __file__
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


_PROJECT_ROOT = _find_project_root()
MODELS_DIR = os.path.join(_PROJECT_ROOT, "models")
CONFIG_DIR = os.path.join(_PROJECT_ROOT, "config", "sector_qa")


@dataclass
class ConceptMatch:
    """A matched QA concept with metadata for graph expansion and retrieval."""
    id: str
    score: float
    related_laws: List[str]
    domain: str
    graph_keywords: List[str]
    description: str


class SectorQAIndex:
    """
    Embedding-based QA index for a sector.

    Pre-embeds all questions from the sector's QA YAML at initialization,
    then uses cosine similarity for fast concept matching at query time.
    """

    def __init__(self, sector: str):
        self.sector = sector
        self._embeddings: Optional[np.ndarray] = None
        self._concept_indices: List[int] = []
        self._concepts: List[dict] = []
        self._encode = None
        self._initialized = False
        self._model_name = ""

    def initialize(self):
        """Load model and pre-embed QA pairs."""
        if self._initialized:
            return

        # 1. Choose model: fine-tuned (if exists) or base
        trained_path = os.path.join(MODELS_DIR, self.sector)
        if os.path.isdir(trained_path):
            self._model_name = trained_path
            logger.info(f"Loading fine-tuned model for sector '{self.sector}' from {trained_path}")
        else:
            self._model_name = BASE_MODEL
            logger.info(f"No trained model for '{self.sector}', using base: {BASE_MODEL}")

        # 2. Load encoder
        if self._model_name == BASE_MODEL:
            from fastembed import TextEmbedding
            encoder = TextEmbedding(BASE_MODEL)
            self._encode = lambda texts: list(encoder.embed(texts))
        else:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(self._model_name)
            self._encode = lambda texts: model.encode(texts, show_progress_bar=False).tolist()

        # 3. Load QA YAML
        yaml_path = os.path.join(CONFIG_DIR, f"{self.sector}_qa.yaml")
        if not os.path.exists(yaml_path):
            logger.warning(f"No QA config for sector '{self.sector}': {yaml_path}")
            self._initialized = True
            return

        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        # 4. Embed all questions
        texts = []
        concept_indices = []
        for i, concept in enumerate(data.get("concepts", [])):
            for q in concept.get("questions", []):
                texts.append(q)
                concept_indices.append(i)

        if not texts:
            self._initialized = True
            return

        embeddings = self._encode(texts)
        self._embeddings = np.array(embeddings, dtype=np.float32)
        # Normalize for fast cosine similarity via dot product
        norms = np.linalg.norm(self._embeddings, axis=1, keepdims=True)
        self._embeddings = self._embeddings / np.where(norms > 0, norms, 1)

        self._concept_indices = concept_indices
        self._concepts = data["concepts"]
        self._initialized = True

        logger.info(
            f"✅ SectorQAIndex[{self.sector}]: {len(self._concepts)} concepts, "
            f"{len(texts)} questions, model={self._model_name}"
        )

    def search(self, query: str, top_k: int = 3, threshold: float = 0.65) -> List[ConceptMatch]:
        """
        Find concepts matching the query by cosine similarity.

        Args:
            query: User query text
            top_k: Maximum concepts to return
            threshold: Minimum similarity score

        Returns:
            List of ConceptMatch sorted by score descending
        """
        if not self._initialized:
            self.initialize()
        if self._embeddings is None or len(self._embeddings) == 0:
            return []

        # Encode and normalize query
        query_emb = np.array(self._encode([query])[0], dtype=np.float32)
        norm = np.linalg.norm(query_emb)
        if norm > 0:
            query_emb = query_emb / norm

        # Cosine similarity (embeddings already normalized)
        scores = self._embeddings @ query_emb

        # Dedupe: max score per concept
        concept_scores: Dict[int, float] = {}
        for idx, score in enumerate(scores):
            c_idx = self._concept_indices[idx]
            if c_idx not in concept_scores or score > concept_scores[c_idx]:
                concept_scores[c_idx] = float(score)

        # Sort, filter, return
        sorted_concepts = sorted(concept_scores.items(), key=lambda x: x[1], reverse=True)
        results = []
        for c_idx, score in sorted_concepts[:top_k]:
            if score < threshold:
                break
            c = self._concepts[c_idx]
            results.append(ConceptMatch(
                id=c["id"],
                score=score,
                related_laws=c.get("related_laws", []),
                domain=c.get("domain", ""),
                graph_keywords=c.get("graph_keywords", []),
                description=c.get("description", ""),
            ))
        return results


# Singletons per sector
_indices: Dict[str, SectorQAIndex] = {}


def get_sector_qa_index(sector: str) -> Optional[SectorQAIndex]:
    """Get or create QA index for sector. Returns None if initialization fails."""
    if sector not in _indices:
        idx = SectorQAIndex(sector)
        try:
            idx.initialize()
            _indices[sector] = idx
        except Exception as e:
            logger.error(f"Failed to init QA index for {sector}: {e}")
            return None
    return _indices[sector]
