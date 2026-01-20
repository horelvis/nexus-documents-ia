"""
Structural Embedder

Generates embeddings for structural descriptions (NOT document content).

These embeddings enable semantic search over document STRUCTURE:
- "Find contracts in the ACME folder" → semantic match on structural description
- "Documents related to HR from 2024" → semantic match on domain + year

Key Principle:
We embed the STRUCTURAL DESCRIPTION, not the document content.
This allows semantic search to find structurally similar documents
without having to embed and search through all the content.
"""

import logging
from typing import List, Optional
import httpx

from .schemas import StructuralMetadata
from ...core.config import settings

logger = logging.getLogger(__name__)


class StructuralEmbedder:
    """
    Generates embeddings for structural descriptions.

    Uses the same embedding model as the rest of the RAG system
    but applies it to structural descriptions rather than document content.

    This enables:
    - Semantic search over document structure
    - Finding structurally similar documents
    - Clustering documents by structural similarity
    """

    def __init__(self):
        self._initialized = False
        self._embedding_url = settings.embedding_url
        self._embedding_model = settings.embedding_model

    async def initialize(self) -> None:
        """Initialize the embedder."""
        if self._initialized:
            return
        self._initialized = True
        logger.info("✅ StructuralEmbedder initialized")

    async def embed_structural_description(
        self,
        structural_metadata: StructuralMetadata,
    ) -> Optional[List[float]]:
        """
        Generate embedding for a document's structural description.

        Args:
            structural_metadata: The structural metadata containing the description

        Returns:
            Embedding vector or None if generation fails

        Example description that gets embedded:
        "Contrato de servicios profesionales con cliente ACME ubicado en
         /Clientes/ACME/2024/Contratos. Dominio: legal. Departamento: Ventas."
        """
        description = structural_metadata.structural_description

        if not description:
            logger.warning(
                f"No structural description for document {structural_metadata.document_id}"
            )
            return None

        return await self._generate_embedding(description)

    async def embed_structural_descriptions_batch(
        self,
        metadata_list: List[StructuralMetadata],
    ) -> List[Optional[List[float]]]:
        """
        Generate embeddings for multiple structural descriptions.

        Args:
            metadata_list: List of structural metadata objects

        Returns:
            List of embedding vectors (None for failed embeddings)
        """
        descriptions = [m.structural_description for m in metadata_list]

        # Filter out empty descriptions
        valid_indices = [i for i, d in enumerate(descriptions) if d]
        valid_descriptions = [descriptions[i] for i in valid_indices]

        if not valid_descriptions:
            return [None] * len(metadata_list)

        # Generate embeddings in batch
        embeddings = await self._generate_embeddings_batch(valid_descriptions)

        # Map back to original positions
        result = [None] * len(metadata_list)
        for i, idx in enumerate(valid_indices):
            if i < len(embeddings):
                result[idx] = embeddings[i]

        return result

    async def embed_query_for_structural_search(
        self,
        query: str,
    ) -> Optional[List[float]]:
        """
        Generate embedding for a query to search structural descriptions.

        The query should describe structural aspects to search for:
        - "contratos de ACME del 2024"
        - "documentos de RRHH"
        - "facturas del departamento de ventas"

        NOT content queries like:
        - "cláusulas de penalización" (this needs content search)

        Args:
            query: Structural query text

        Returns:
            Query embedding vector
        """
        if not query:
            return None

        # Optionally enhance query for structural matching
        enhanced_query = self._enhance_structural_query(query)

        return await self._generate_embedding(enhanced_query)

    def _enhance_structural_query(self, query: str) -> str:
        """
        Optionally enhance query for better structural matching.

        This can add context that helps match structural descriptions.
        """
        # For now, return as-is. Could add prefixes like:
        # "Documento: " + query
        # Or expand abbreviations
        return query

    async def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for a single text."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self._embedding_url}/embed",
                    json={
                        "inputs": text,
                        "truncate": True,
                    },
                )

                if response.status_code == 200:
                    embeddings = response.json()
                    if embeddings and len(embeddings) > 0:
                        return embeddings[0]

                logger.warning(
                    f"Embedding request failed with status {response.status_code}"
                )
                return None

        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            return None

    async def _generate_embeddings_batch(
        self,
        texts: List[str],
    ) -> List[Optional[List[float]]]:
        """Generate embeddings for multiple texts in batch."""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self._embedding_url}/embed",
                    json={
                        "inputs": texts,
                        "truncate": True,
                    },
                )

                if response.status_code == 200:
                    embeddings = response.json()
                    return embeddings if embeddings else [None] * len(texts)

                logger.warning(
                    f"Batch embedding request failed with status {response.status_code}"
                )
                return [None] * len(texts)

        except Exception as e:
            logger.error(f"Failed to generate batch embeddings: {e}")
            return [None] * len(texts)


# Global singleton instance
structural_embedder = StructuralEmbedder()
