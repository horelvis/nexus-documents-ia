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

Implementation:
Uses local sentence-transformers model (same as RAG pipeline) when
EMBEDDING_PROVIDER=sentence-transformers, or falls back to HTTP embedding
service if configured.
"""

import asyncio
import logging
from typing import List, Optional
import httpx

from .schemas import StructuralMetadata
from ...core.config import settings

logger = logging.getLogger(__name__)

# Global model cache (shared with weaviate_service)
_embedding_model = None
_embedding_model_lock = asyncio.Lock()


async def _get_local_embedding_model():
    """Get or load the local sentence-transformers model."""
    global _embedding_model

    if _embedding_model is not None:
        return _embedding_model

    async with _embedding_model_lock:
        # Double-check after acquiring lock
        if _embedding_model is not None:
            return _embedding_model

        try:
            from sentence_transformers import SentenceTransformer
            import torch

            # Determine device
            device = settings.embedding_device
            if device == "auto":
                device = "cuda" if torch.cuda.is_available() else "cpu"
            elif device == "cuda" and not torch.cuda.is_available():
                logger.warning("⚠️ CUDA requested but not available, falling back to CPU")
                device = "cpu"

            # Load model
            model_name = settings.embedding_model
            logger.info(f"🔄 Loading embedding model for SIL: {model_name} on {device}")

            _embedding_model = SentenceTransformer(model_name, device=device)

            logger.info(f"✅ Loaded embedding model for SIL: {model_name} on {device}")
            return _embedding_model

        except Exception as e:
            logger.error(f"❌ Failed to load embedding model: {e}")
            return None


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
        self._embedding_model_name = settings.embedding_model
        self._embedding_provider = settings.embedding_provider

    async def initialize(self) -> None:
        """Initialize the embedder."""
        if self._initialized:
            return

        # Pre-load model if using local sentence-transformers
        if self._embedding_provider == "sentence-transformers":
            model = await _get_local_embedding_model()
            if model:
                logger.info("✅ StructuralEmbedder initialized with local sentence-transformers")
            else:
                logger.warning("⚠️ StructuralEmbedder: local model failed, will use fallback")
        else:
            logger.info(f"✅ StructuralEmbedder initialized with {self._embedding_provider}")

        self._initialized = True

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
        """Generate embedding for a single text using configured provider."""
        # Try local sentence-transformers first
        if self._embedding_provider == "sentence-transformers":
            return await self._generate_embedding_local(text)

        # Fall back to HTTP service
        return await self._generate_embedding_http(text)

    async def _generate_embedding_local(self, text: str) -> Optional[List[float]]:
        """Generate embedding using local sentence-transformers model."""
        try:
            model = await _get_local_embedding_model()
            if model is None:
                logger.warning("Local embedding model not available")
                return None

            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            embedding = await loop.run_in_executor(
                None,
                lambda: model.encode(text, convert_to_numpy=True).tolist()
            )
            return embedding

        except Exception as e:
            logger.error(f"Failed to generate local embedding: {e}")
            return None

    async def _generate_embedding_http(self, text: str) -> Optional[List[float]]:
        """Generate embedding using HTTP embedding service (fallback)."""
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
            logger.error(f"Failed to generate HTTP embedding: {e}")
            return None

    async def _generate_embeddings_batch(
        self,
        texts: List[str],
    ) -> List[Optional[List[float]]]:
        """Generate embeddings for multiple texts in batch using configured provider."""
        # Try local sentence-transformers first
        if self._embedding_provider == "sentence-transformers":
            return await self._generate_embeddings_batch_local(texts)

        # Fall back to HTTP service
        return await self._generate_embeddings_batch_http(texts)

    async def _generate_embeddings_batch_local(
        self,
        texts: List[str],
    ) -> List[Optional[List[float]]]:
        """Generate embeddings in batch using local sentence-transformers model."""
        try:
            model = await _get_local_embedding_model()
            if model is None:
                logger.warning("Local embedding model not available")
                return [None] * len(texts)

            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            embeddings = await loop.run_in_executor(
                None,
                lambda: [emb.tolist() for emb in model.encode(texts, convert_to_numpy=True)]
            )
            return embeddings

        except Exception as e:
            logger.error(f"Failed to generate local batch embeddings: {e}")
            return [None] * len(texts)

    async def _generate_embeddings_batch_http(
        self,
        texts: List[str],
    ) -> List[Optional[List[float]]]:
        """Generate embeddings in batch using HTTP embedding service (fallback)."""
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
            logger.error(f"Failed to generate HTTP batch embeddings: {e}")
            return [None] * len(texts)


# Global singleton instance
structural_embedder = StructuralEmbedder()
