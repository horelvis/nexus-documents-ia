"""
Per-Chunk Context Enricher (Anthropic Contextual Retrieval Enhancement)

When CONTEXTUAL_RETRIEVAL_USE_LLM=true, this module generates per-chunk context
using the LLM. Instead of the same domain-level prefix for all chunks, each chunk
gets a unique 1-2 sentence context that situates it within the document.

This is the "full" Anthropic Contextual Retrieval pattern:
1. Send full document as system context (vLLM prefix caching)
2. For each chunk, ask the LLM: "Sitúa este fragmento en 1-2 frases"
3. Prepend the per-chunk context before embedding

Cost: ~50ms/chunk with local vLLM (Qwen3-14B). A 50-chunk document = ~2.5s extra.
Acceptable for offline indexing.

The per-chunk context is stored in the `chunk_context` Weaviate property for
debug/display purposes.

Usage:
    from app.services.rag.context_enricher import context_enricher

    enriched = await context_enricher.enrich_chunks(
        full_text=document_text,
        chunks=chunks,
        doc_metadata={"title": "Contrato de trabajo", "domain": "labor"},
    )
    # Each chunk now has context prepended to content
    # and chunk_context in metadata
"""

import logging
import re
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Regex to strip <think>...</think> tags from Qwen3 output
_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)

# Reusable async HTTP client for vLLM calls
_http_client: Optional[httpx.AsyncClient] = None


async def _get_http_client() -> httpx.AsyncClient:
    """Get or create a reusable async HTTP client."""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=30.0)
    return _http_client


async def _call_vllm_chat(
    messages: List[Dict[str, str]],
    temperature: float = 0.3,
    max_tokens: int = 150,
) -> Optional[str]:
    """Call vLLM's OpenAI-compatible chat/completions endpoint.

    Returns the assistant message content, or None on failure.
    """
    base_url = settings.vllm_base_url.rstrip("/")
    model = settings.vllm_model
    url = f"{base_url}/chat/completions"

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    try:
        client = await _get_http_client()
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        if content:
            # Strip <think>...</think> tags from Qwen3 thinking mode output
            content = _THINK_RE.sub("", content).strip()
        return content if content else None
    except Exception as e:
        logger.debug(f"vLLM chat call failed: {e}")
        return None

# System prompt for per-chunk context generation
_SYSTEM_PROMPT = """\
Eres un asistente de indexación documental. Tu tarea es generar un contexto breve \
(1-2 frases, máximo 100 palabras) que sitúe un fragmento dentro de su documento.

El contexto debe:
1. Indicar de qué tipo de documento proviene el fragmento
2. Mencionar la sección o tema al que pertenece
3. Incluir legislación aplicable si es relevante

IMPORTANTE: Responde SOLO con el contexto, sin explicaciones ni etiquetas."""

# User prompt template (includes /no_think to suppress Qwen3 thinking mode)
_USER_PROMPT = """\
DOCUMENTO: {title}
FRAGMENTO #{chunk_index} de {total_chunks}:
---
{chunk_content}
---
Genera el contexto breve para este fragmento. /no_think"""


class ContextEnricher:
    """Generate per-chunk contextual preambles via LLM."""

    async def enrich_chunks(
        self,
        full_text: str,
        chunks: list,
        doc_metadata: Optional[Dict[str, Any]] = None,
    ) -> list:
        """Enrich each chunk with a per-chunk LLM-generated context.

        Modifies chunks in-place: prepends context to content and stores
        the context in metadata["chunk_context"].

        Args:
            full_text: The complete document text (sent once as system context).
            chunks: List of DocumentChunk objects with .content and .metadata.
            doc_metadata: Document metadata (title, domain, etc.).

        Returns:
            The same chunks list, modified in-place.
        """
        doc_metadata = doc_metadata or {}
        title = doc_metadata.get("title", "Documento")

        if not chunks:
            return chunks

        # Build system prompt with document excerpt (first 3000 chars for prefix caching)
        doc_excerpt = full_text[:3000]
        system_msg = f"{_SYSTEM_PROMPT}\n\nDOCUMENTO COMPLETO (extracto):\n{doc_excerpt}"

        if not settings.vllm_enabled:
            logger.info("vLLM disabled — skipping per-chunk enrichment")
            return chunks

        enriched_count = 0
        total = len(chunks)

        for chunk in chunks:
            content = chunk.content if hasattr(chunk, 'content') else str(chunk)
            chunk_index = chunk.chunk_index if hasattr(chunk, 'chunk_index') else 0

            user_msg = _USER_PROMPT.format(
                title=title,
                chunk_index=chunk_index + 1,
                total_chunks=total,
                chunk_content=content[:500],  # Limit chunk content in prompt
            )

            try:
                context_text = await _call_vllm_chat(
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": user_msg},
                    ],
                    temperature=0.3,
                    max_tokens=150,
                )

                if context_text:
                    # Prepend to chunk content
                    original = chunk.content
                    chunk.content = f"[CONTEXTO] {context_text} [CONTENIDO] {original}"

                    # Store in metadata for debug/display
                    if hasattr(chunk, 'metadata'):
                        chunk.metadata["chunk_context"] = context_text
                        chunk.metadata["chunk_context_applied"] = True

                    enriched_count += 1

            except Exception as e:
                logger.debug(f"Per-chunk context failed for chunk {chunk_index}: {e}")
                # Non-fatal: chunk keeps its original content

        logger.info(
            f"ContextEnricher: enriched {enriched_count}/{total} chunks with per-chunk context"
        )

        return chunks


# Global instance
context_enricher = ContextEnricher()
