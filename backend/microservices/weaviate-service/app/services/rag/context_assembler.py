"""
Layer 3: Context Assembly

Builds structured context for the LLM with:
- Token budget management (per model)
- Document headers with metadata
- Section prioritization
- Clear formatting markers
"""

import logging
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from .models import (
    QueryAnalysis,
    RetrievedDocument,
    AssembledContext,
    QueryIntent,
)
from ...core.config import settings

logger = logging.getLogger(__name__)


# Token budgets per model type
TOKEN_BUDGETS = {
    "vllm": 12000,       # vLLM with Qwen2.5-7B (16K context)
    "openai": 8000,      # GPT-4o-mini and above
    "anthropic": 8000,   # Claude models
    "ollama": 4000,      # Legacy/conservative for local models
    "default": 8000,
}


class ContextAssembler:
    """
    Layer 3: Build structured context for LLM

    Assembles retrieved documents into a well-formatted context
    that fits within the token budget and includes clear structure
    for the LLM to understand.
    """

    def __init__(self):
        # Approximate tokens per character (conservative estimate)
        self._chars_per_token = 4

    def assemble_context(
        self,
        query_analysis: QueryAnalysis,
        documents: List[RetrievedDocument],
        max_tokens: Optional[int] = None,
        model_type: str = "vllm",
    ) -> AssembledContext:
        """
        Assemble documents into structured context.

        Args:
            query_analysis: Analyzed query from Layer 1
            documents: Retrieved documents from Layer 2
            max_tokens: Override token budget
            model_type: Type of model (vllm, openai, anthropic)

        Returns:
            AssembledContext with formatted context string
        """
        # Determine token budget
        if max_tokens is None:
            max_tokens = TOKEN_BUDGETS.get(model_type, TOKEN_BUDGETS["default"])

        # Reserve tokens for query and response
        context_budget = int(max_tokens * 0.7)  # 70% for context

        logger.info(f"📝 Assembling context: {len(documents)} docs, {context_budget} token budget")

        # Build context parts
        context_parts = []
        document_headers = []
        included_docs = []
        total_chars = 0
        truncated = False

        # Add query metadata header
        query_header = self._build_query_header(query_analysis)
        context_parts.append(query_header)
        total_chars += len(query_header)

        # Add documents in priority order
        for i, doc in enumerate(documents, 1):
            # Build document section
            doc_section, doc_header = self._build_document_section(
                doc=doc,
                index=i,
                intent=query_analysis.intent,
            )

            # Check if fits in budget
            section_tokens = len(doc_section) // self._chars_per_token
            if total_chars // self._chars_per_token + section_tokens > context_budget:
                # Try truncated version
                truncated_section = self._truncate_section(
                    doc_section,
                    available_chars=(context_budget - total_chars // self._chars_per_token) * self._chars_per_token
                )
                if truncated_section:
                    context_parts.append(truncated_section)
                    total_chars += len(truncated_section)
                    included_docs.append(doc)
                    document_headers.append(doc_header)
                truncated = True
                break

            context_parts.append(doc_section)
            total_chars += len(doc_section)
            included_docs.append(doc)
            document_headers.append(doc_header)

        # Join all parts
        formatted_context = "\n\n".join(context_parts)

        # Estimate final token count
        total_tokens = len(formatted_context) // self._chars_per_token

        return AssembledContext(
            formatted_context=formatted_context,
            documents=included_docs,
            total_tokens=total_tokens,
            max_tokens=max_tokens,
            query_analysis=query_analysis,
            document_headers=document_headers,
            truncated=truncated,
        )

    def _build_query_header(self, query_analysis: QueryAnalysis) -> str:
        """Build the query metadata header section"""
        intent_descriptions = {
            QueryIntent.SEARCH: "Búsqueda de información específica",
            QueryIntent.ANALYZE: "Análisis profundo del contenido",
            QueryIntent.COMPARE: "Comparación entre documentos o conceptos",
            QueryIntent.SUMMARIZE: "Resumen del contenido",
            QueryIntent.EXTRACT: "Extracción de datos específicos",
            QueryIntent.EXPLAIN: "Explicación de un concepto",
            QueryIntent.LIST: "Listado de elementos",
            QueryIntent.UNKNOWN: "Consulta general",
        }

        intent_desc = intent_descriptions.get(query_analysis.intent, "Consulta general")

        header = f"""=== INFORMACIÓN DE LA CONSULTA ===
Consulta Original: {query_analysis.original_query}
Consulta Expandida: {query_analysis.expanded_query}
Tipo de Consulta: {intent_desc}
Términos Clave: {', '.join(query_analysis.key_terms[:5])}
Idioma: {'Español' if query_analysis.language == 'es' else 'Inglés'}"""

        # Add filters if present
        if query_analysis.extracted_filters:
            filter_info = []
            if "document_type_hint" in query_analysis.extracted_filters:
                filter_info.append(f"Tipo de documento: {query_analysis.extracted_filters['document_type_hint']}")
            if "date_hints" in query_analysis.extracted_filters:
                filter_info.append(f"Referencias de fecha: {', '.join(query_analysis.extracted_filters['date_hints'])}")
            if filter_info:
                header += f"\nFiltros Detectados: {'; '.join(filter_info)}"

        return header

    def _build_document_section(
        self,
        doc: RetrievedDocument,
        index: int,
        intent: QueryIntent,
    ) -> tuple[str, str]:
        """
        Build a formatted section for a single document.

        Returns:
            Tuple of (full_section, header_only)
        """
        # Build header
        header_parts = [f"[DOCUMENTO {index}]"]
        header_parts.append(f"Título: {doc.title or 'Sin título'}")

        if doc.document_type:
            header_parts.append(f"Tipo: {doc.document_type}")

        header_parts.append(f"Relevancia: {doc.score:.2f}")

        if doc.total_chunks and doc.total_chunks > 1:
            header_parts.append(f"Fragmento: {doc.chunk_index + 1}/{doc.total_chunks}")

        header = "\n".join(header_parts)

        # Build content section based on intent
        content = doc.content

        # Format content based on intent
        if intent == QueryIntent.SUMMARIZE:
            # For summaries, include full content but mark sections
            content = self._format_for_summary(content)
        elif intent == QueryIntent.EXTRACT:
            # For extraction, highlight potential data points
            content = self._format_for_extraction(content)
        elif intent == QueryIntent.ANALYZE:
            # For analysis, preserve structure
            content = self._format_for_analysis(content)
        else:
            # Default formatting
            content = self._clean_content(content)

        # Combine header and content
        full_section = f"""{header}
---
{content}"""

        return full_section, header

    def _format_for_summary(self, content: str) -> str:
        """Format content for summarization intent"""
        # Clean and preserve paragraph structure
        content = self._clean_content(content)

        # Mark potential section breaks
        content = re.sub(r'\n{3,}', '\n\n[---]\n\n', content)

        return content

    def _format_for_extraction(self, content: str) -> str:
        """Format content for data extraction intent"""
        content = self._clean_content(content)

        # Highlight numbers and dates
        content = re.sub(
            r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
            r'[FECHA: \1]',
            content
        )
        content = re.sub(
            r'(\d+[.,]\d+\s*(?:€|\$|USD|EUR))',
            r'[MONTO: \1]',
            content
        )

        return content

    def _format_for_analysis(self, content: str) -> str:
        """Format content for analysis intent"""
        content = self._clean_content(content)

        # Preserve lists
        content = re.sub(r'^(\s*[-•*]\s)', r'\n\1', content, flags=re.MULTILINE)

        # Preserve numbered items
        content = re.sub(r'^(\s*\d+[.)]\s)', r'\n\1', content, flags=re.MULTILINE)

        return content

    def _clean_content(self, content: str) -> str:
        """Basic content cleaning"""
        # Remove excessive whitespace
        content = re.sub(r'\s+', ' ', content)

        # Restore paragraph breaks
        content = re.sub(r' {2,}', '\n\n', content)

        # Remove leading/trailing whitespace
        content = content.strip()

        return content

    def _truncate_section(self, section: str, available_chars: int) -> Optional[str]:
        """
        Truncate a section to fit available space.

        Returns None if too little space available.
        """
        if available_chars < 200:  # Minimum useful size
            return None

        # Find header end
        header_end = section.find("---")
        if header_end == -1:
            header_end = 0
        else:
            header_end += 4  # Include "---\n"

        header = section[:header_end]
        content = section[header_end:]

        # Calculate available content space
        available_content = available_chars - len(header) - 50  # Margin for truncation notice

        if available_content < 100:
            return None

        # Truncate content
        truncated_content = content[:available_content]

        # Try to end at sentence boundary
        last_period = truncated_content.rfind('.')
        last_newline = truncated_content.rfind('\n')
        cut_point = max(last_period, last_newline)

        if cut_point > available_content // 2:
            truncated_content = truncated_content[:cut_point + 1]

        return f"{header}{truncated_content}\n[... contenido truncado ...]"

    def get_token_count(self, text: str) -> int:
        """Estimate token count for text"""
        return len(text) // self._chars_per_token


# Global instance
context_assembler = ContextAssembler()
