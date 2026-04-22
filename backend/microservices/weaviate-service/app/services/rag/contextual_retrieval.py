"""
Contextual Retrieval Pipeline

Based on Anthropic's Contextual Retrieval pattern, this module generates and prepends
contextual information to document chunks BEFORE indexing. This approach:

- Improves retrieval accuracy by 35-67% (Anthropic research)
- Encodes document-type knowledge IN chunks instead of in prompts
- Reduces token usage at query time (no need for 4000+ token domain prompts)
- Makes chunks self-contained with type and entity context

How it works:
1. Analyze document to identify its type and key entities
2. Generate a contextual prefix for each chunk
3. Prepend context to chunk BEFORE embedding

Example:
    Original chunk:
        "El trabajador tendrá una jornada de 40 horas semanales..."

    Contextualized chunk:
        "[CONTEXTO] Documento tipo `contrato_laboral`. Entidades: fecha:01/01/2025,
        importe:2000€. [CONTENIDO] El trabajador tendrá una jornada de 40 horas semanales..."

Usage:
    from app.services.rag.contextual_retrieval import contextual_retrieval

    # Generate context for a document
    context_result = await contextual_retrieval.analyze_document(
        document_id="doc-123",
        text=document_text,
        metadata={"document_type": "contrato_laboral"},
    )

    # Apply context to chunks
    contextualized_chunks = contextual_retrieval.apply_context_to_chunks(
        chunks=raw_chunks,
        context_result=context_result
    )

References:
    - https://www.anthropic.com/news/contextual-retrieval
    - backend/architecture/SIL-structural-intelligence-layer.md
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ContextGenerationResult:
    """Result of context generation for a document."""
    document_id: str
    document_type: str
    context_prefix: str
    document_summary: str
    key_entities: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextualizedChunk:
    """A chunk with prepended context."""
    original_text: str
    contextualized_text: str
    context_prefix: str
    chunk_index: int
    document_type: str
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Contextual Retrieval Service
# =============================================================================

class ContextualRetrievalService:
    """
    Service for generating and applying contextual information to document chunks.

    This implements Anthropic's Contextual Retrieval pattern:
    1. Identify document type from metadata (provided by upstream classifier)
    2. Extract key entities from text
    3. Generate context prefix for chunks
    4. Prepend context before embedding
    """

    def __init__(self):
        self._llm_client = None
        self._enabled = settings.contextual_retrieval_enabled if hasattr(settings, 'contextual_retrieval_enabled') else True

    async def _get_llm_client(self):
        """Lazy load LLM client (calls SGLang directly via HTTP)."""
        if self._llm_client is None:
            try:
                from app.services.rag.context_enricher import _call_sglang_chat

                # Create a thin wrapper that matches the expected interface
                class _SGLangWrapper:
                    async def chat(self, messages, temperature=0.3, max_tokens=200, **kwargs):
                        class _Response:
                            def __init__(self, text):
                                self.content = text
                        result = await _call_sglang_chat(messages, temperature, max_tokens)
                        return _Response(result)

                self._llm_client = _SGLangWrapper()
            except Exception as e:
                logger.warning(f"Failed to create SGLang client: {e}")
        return self._llm_client

    def generate_context_prefix(self, document_type: str = "", key_entities: Optional[List[str]] = None) -> str:
        """Generate a context prefix string from document_type and key entities.

        The prefix is prepended to each chunk before embedding, improving
        retrieval relevance per Anthropic's Contextual Retrieval pattern.
        """
        parts = ["[CONTEXTO]"]
        if document_type and document_type != "general":
            parts.append(f" Documento tipo `{document_type}`.")
        if key_entities:
            ent_summary = ", ".join(key_entities[:5])
            parts.append(f" Entidades: {ent_summary}.")
        parts.append(" [CONTENIDO]")
        return "".join(parts)

    async def analyze_document(
        self, document_id: str, text: str, metadata: Optional[Dict[str, Any]] = None,
        use_llm: bool = True,
    ) -> ContextGenerationResult:
        """Analyze a document and generate contextual information.

        The context prefix is built from `document_type` (provided by the
        upstream classifier) and key entities extracted from the text. When
        LLM enhancement is enabled, a richer prefix is generated.
        """
        metadata = metadata or {}
        document_type = metadata.get("document_type", "general")
        key_entities = self._extract_key_entities(text)
        doc_summary = self._generate_simple_summary(text)
        context_prefix = self.generate_context_prefix(document_type, key_entities=key_entities)

        if use_llm and self._enabled:
            try:
                llm_client = await self._get_llm_client()
                if llm_client:
                    enhanced_context = await self._enhance_with_llm(
                        text, document_type, key_entities, llm_client
                    )
                    if enhanced_context:
                        context_prefix = enhanced_context
            except Exception as e:
                logger.warning(f"LLM enhancement failed, using rule-based context: {e}")

        return ContextGenerationResult(
            document_id=document_id,
            document_type=document_type,
            context_prefix=context_prefix,
            document_summary=doc_summary,
            key_entities=key_entities,
            metadata={},
        )

    def _extract_key_entities(self, text: str) -> List[str]:
        """Extract common entities (dates, money, NIFs) from document text."""
        entities = []
        date_pattern = r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}'
        dates = re.findall(date_pattern, text)
        entities.extend([f"fecha:{d}" for d in dates[:3]])
        money_pattern = r'(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*(?:€|euros?|EUR)'
        amounts = re.findall(money_pattern, text, re.IGNORECASE)
        entities.extend([f"importe:{a}€" for a in amounts[:3]])
        nif_pattern = r'[A-Z]?\d{7,8}[A-Z]'
        nifs = re.findall(nif_pattern, text)
        entities.extend([f"nif:{n}" for n in nifs[:2]])
        return entities[:10]

    def _generate_simple_summary(self, text: str, max_length: int = 500) -> str:
        """Generate a simple summary from the first part of the document."""
        # Take first portion
        summary = text[:max_length * 2]

        # Truncate at last complete sentence
        last_period = summary.rfind('.')
        if last_period > 100:
            summary = summary[:last_period + 1]
        elif len(summary) > max_length:
            summary = summary[:max_length] + "..."

        return summary.strip()

    async def _enhance_with_llm(
        self, text: str, document_type: str, key_entities: List[str], llm_client
    ) -> Optional[str]:
        """Use LLM to generate enhanced contextual prefix from document_type + entities."""
        if len(text) < 200:
            return None

        entities_text = ", ".join(key_entities[:5]) if key_entities else "(ninguna extraída)"
        prompt = f"""Genera un contexto BREVE (máximo 100 palabras) para este fragmento de documento.

TIPO DE DOCUMENTO: {document_type}
ENTIDADES CLAVE: {entities_text}

DOCUMENTO (primeros 1000 caracteres):
{text[:1000]}

FORMATO REQUERIDO:
[CONTEXTO] [Tipo de documento]. [Descripción breve]. Entidades: [entidades relevantes]. [CONTENIDO]

Responde SOLO con el contexto, sin explicaciones adicionales. /no_think"""

        try:
            response = await llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=200,
            )
            if response and response.content:
                context = re.sub(r"<think>.*?</think>\s*", "", response.content, flags=re.DOTALL).strip()
                if not context.startswith("[CONTEXTO]"):
                    context = f"[CONTEXTO] {context}"
                if not context.endswith("[CONTENIDO]"):
                    context = f"{context} [CONTENIDO]"
                return context
        except Exception as e:
            logger.warning(f"LLM context enhancement failed: {e}")
        return None

    def apply_context_to_chunks(
        self,
        chunks: List[Any],  # DocumentChunk from semantic_chunker
        context_result: ContextGenerationResult,
        include_in_text: bool = True
    ) -> List[ContextualizedChunk]:
        """
        Apply context prefix to a list of chunks.

        Args:
            chunks: List of DocumentChunk objects
            context_result: Result from analyze_document
            include_in_text: Whether to prepend context to chunk text

        Returns:
            List of ContextualizedChunk with context applied
        """
        contextualized = []

        for i, chunk in enumerate(chunks):
            # Get chunk text
            chunk_text = chunk.text if hasattr(chunk, 'text') else str(chunk)

            # Create contextualized text
            if include_in_text:
                contextualized_text = f"{context_result.context_prefix} {chunk_text}"
            else:
                contextualized_text = chunk_text

            # Get chunk metadata
            chunk_metadata = chunk.metadata if hasattr(chunk, 'metadata') else {}

            contextualized.append(ContextualizedChunk(
                original_text=chunk_text,
                contextualized_text=contextualized_text,
                context_prefix=context_result.context_prefix,
                chunk_index=i,
                document_type=context_result.document_type,
                metadata={
                    **chunk_metadata,
                    "context_applied": include_in_text,
                    "context_length": len(context_result.context_prefix),
                }
            ))

        return contextualized

    def enrich_chunk_metadata(
        self,
        chunk_metadata: Dict[str, Any],
        context_result: ContextGenerationResult
    ) -> Dict[str, Any]:
        """
        Enrich chunk metadata with contextual information.

        This adds document type and entity metadata to chunks
        for improved filtering and retrieval.

        Args:
            chunk_metadata: Original chunk metadata
            context_result: Context generation result

        Returns:
            Enriched metadata dictionary
        """
        return {
            **chunk_metadata,
            "document_type": context_result.document_type,
            "key_entities": context_result.key_entities,
            "contextual_retrieval": True,
        }


# =============================================================================
# Global Instance
# =============================================================================

contextual_retrieval = ContextualRetrievalService()


# =============================================================================
# Convenience Functions
# =============================================================================

async def contextualize_document(
    document_id: str,
    text: str,
    chunks: List[Any],
    metadata: Optional[Dict[str, Any]] = None,
    use_llm: bool = False,
) -> Tuple[ContextGenerationResult, List[ContextualizedChunk]]:
    """
    Convenience function to analyze and contextualize a document in one step.

    Args:
        document_id: Document identifier
        text: Full document text
        chunks: Pre-chunked document
        metadata: Document metadata
        use_llm: Whether to use LLM for enhanced analysis

    Returns:
        Tuple of (ContextGenerationResult, List[ContextualizedChunk])
    """
    context_result = await contextual_retrieval.analyze_document(
        document_id=document_id,
        text=text,
        metadata=metadata,
        use_llm=use_llm,
    )

    contextualized_chunks = contextual_retrieval.apply_context_to_chunks(
        chunks=chunks,
        context_result=context_result
    )

    return context_result, contextualized_chunks
