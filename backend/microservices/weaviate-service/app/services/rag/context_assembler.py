"""
Layer 3: Context Assembly

Builds structured context for the LLM with:
- Proportional token budget allocation (based on soft weights)
- Smart truncation (sections > paragraphs > sentences)
- Document headers with metadata
- Clear formatting markers
"""

import logging
import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from .models import (
    QueryAnalysis,
    RetrievedDocument,
    AssembledContext,
    QueryIntent,
)
from .soft_selection import allocate_token_budget
from ...core.config import settings

logger = logging.getLogger(__name__)


# Token allocation for structural context (SIL)
STRUCTURAL_CONTEXT_MAX_TOKENS = 500  # Reserve for structural context header


# Token budgets per model type
# Reserve ~4K tokens for system prompt, query, and response generation
TOKEN_BUDGETS = {
    "vllm": 12000,       # vLLM default (adjust based on model's max_model_len)
    "openai": 12000,     # GPT-4o-mini and above (128K context available)
    "anthropic": 12000,  # Claude models (200K context available)
    "ollama": 4000,      # Legacy/conservative for local models
    "default": 8000,
}

# Section markers for smart truncation (in priority order)
SECTION_MARKERS = [
    # Markdown headings
    r'^#{1,6}\s+',
    # Legal document markers
    r'^(?:CAPÍTULO|ARTÍCULO|SECCIÓN|CLÁUSULA|TÍTULO)\s+',
    r'^(?:Art\.|Cap\.|Sec\.)\s*\d+',
    # Numbered sections
    r'^\d+\.\d*\s+[A-ZÁÉÍÓÚ]',
    # Horizontal rules
    r'^[-=_]{3,}$',
    r'^---+$',
]


class ContextAssembler:
    """
    Layer 3: Build structured context for LLM

    Assembles retrieved documents into a well-formatted context
    that fits within the token budget. Supports:
    - Proportional token allocation based on soft weights
    - Smart truncation at semantic boundaries
    - Intent-specific formatting
    """

    def __init__(self):
        # Approximate tokens per character (conservative estimate)
        self._chars_per_token = 4
        # Minimum tokens per document (from config)
        self._min_tokens_per_doc = settings.rag_min_tokens_per_doc
        # Truncation priority from config
        self._truncation_priority = settings.rag_truncation_priority

    def assemble_context(
        self,
        query_analysis: QueryAnalysis,
        documents: List[RetrievedDocument],
        max_tokens: Optional[int] = None,
        model_type: str = "vllm",
        soft_weights: Optional[Dict[str, float]] = None,
        selection_metadata: Optional[Dict[str, Any]] = None,
        structural_context: Optional[str] = None,
    ) -> AssembledContext:
        """
        Assemble documents into structured context with proportional token allocation.

        Args:
            query_analysis: Analyzed query from Layer 1
            documents: Retrieved documents from Layer 2
            max_tokens: Override token budget
            model_type: Type of model (vllm, openai, anthropic)
            soft_weights: Soft selection weights for proportional allocation
            selection_metadata: Metadata from soft selection (diversity, coverage)
            structural_context: Optional pre-computed structural context from SIL

        Returns:
            AssembledContext with formatted context string
        """
        # Determine token budget
        if max_tokens is None:
            max_tokens = TOKEN_BUDGETS.get(model_type, TOKEN_BUDGETS["default"])

        # Reserve tokens for query and response
        context_budget = int(max_tokens * settings.rag_context_budget_fraction)

        # If structural context provided, reserve tokens for it
        structural_tokens_used = 0
        if structural_context:
            structural_tokens_used = min(
                len(structural_context) // self._chars_per_token,
                STRUCTURAL_CONTEXT_MAX_TOKENS
            )
            context_budget -= structural_tokens_used
            logger.info(f"📊 SIL structural context: {structural_tokens_used} tokens reserved")

        # Calculate token allocations
        if soft_weights:
            token_allocations = allocate_token_budget(
                documents=documents,
                soft_weights=soft_weights,
                total_budget=context_budget,
                min_tokens_per_doc=self._min_tokens_per_doc,
            )
            logger.info(
                f"📝 Assembling context: {len(documents)} docs, {context_budget} token budget, "
                f"proportional allocation enabled"
            )
        else:
            # Legacy: equal allocation
            per_doc = context_budget // max(len(documents), 1)
            token_allocations = {doc.id: per_doc for doc in documents}
            logger.info(
                f"📝 Assembling context: {len(documents)} docs, {context_budget} token budget, "
                f"equal allocation ({per_doc} per doc)"
            )

        # Build context parts
        context_parts = []
        document_headers = []
        included_docs = []
        total_chars = 0

        # Add structural context from SIL (if provided) - FIRST for priority
        if structural_context:
            structural_section = self._build_structural_context_section(structural_context)
            context_parts.append(structural_section)
            total_chars += len(structural_section)

        # Add query metadata header
        query_header = self._build_query_header(query_analysis)
        context_parts.append(query_header)
        total_chars += len(query_header)

        # Track documents dropped due to insufficient budget
        dropped_docs = 0

        # Add documents with proportional allocation
        for i, doc in enumerate(documents, 1):
            allocated_tokens = token_allocations.get(doc.id, 0)

            # Skip documents with 0 allocation (dropped by min_weight)
            if allocated_tokens == 0:
                dropped_docs += 1
                logger.debug(f"  Skipping doc {doc.id}: 0 tokens allocated")
                continue

            allocated_chars = allocated_tokens * self._chars_per_token

            # Build document section with allocated budget
            doc_section, doc_header = self._build_document_section_proportional(
                doc=doc,
                index=len(included_docs) + 1,  # Use actual index in output
                intent=query_analysis.intent,
                max_chars=allocated_chars,
            )

            # Update document with allocated tokens
            doc.allocated_tokens = allocated_tokens

            context_parts.append(doc_section)
            total_chars += len(doc_section)
            included_docs.append(doc)
            document_headers.append(doc_header)

        # Join all parts
        formatted_context = "\n\n".join(context_parts)

        # Estimate final token count
        total_tokens = len(formatted_context) // self._chars_per_token

        logger.info(
            f"  Context assembled: {total_tokens} tokens, {len(included_docs)} docs included, "
            f"{dropped_docs} dropped"
        )

        return AssembledContext(
            formatted_context=formatted_context,
            documents=included_docs,
            total_tokens=total_tokens,
            max_tokens=max_tokens,
            query_analysis=query_analysis,
            document_headers=document_headers,
            truncated=any(
                len(doc.content) > (token_allocations.get(doc.id, 0) * self._chars_per_token)
                for doc in included_docs
            ),
            selection_metadata=selection_metadata,
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

    def _build_structural_context_section(self, structural_context: str) -> str:
        """
        Build the structural context section from SIL.

        This section provides pre-computed structural information about
        relevant documents without their full content. It helps the LLM
        understand document relationships, locations, and metadata.
        """
        # Truncate if too long
        max_chars = STRUCTURAL_CONTEXT_MAX_TOKENS * self._chars_per_token
        if len(structural_context) > max_chars:
            structural_context = structural_context[:max_chars] + "\n[... contexto estructural truncado]"

        return f"""=== CONTEXTO ESTRUCTURAL (SIL) ===
{structural_context}
=== FIN CONTEXTO ESTRUCTURAL ==="""

    def _build_document_section_proportional(
        self,
        doc: RetrievedDocument,
        index: int,
        intent: QueryIntent,
        max_chars: int,
    ) -> Tuple[str, str]:
        """
        Build document section with character limit.

        Uses smart truncation: sections > paragraphs > sentences.

        Returns:
            Tuple of (full_section, header_only)
        """
        # Build header
        header_parts = [f"[DOCUMENTO {index}]"]
        header_parts.append(f"Título: {doc.title or 'Sin título'}")

        if doc.document_type:
            header_parts.append(f"Tipo: {doc.document_type}")

        header_parts.append(f"Relevancia: {doc.score:.2f}")

        # Show soft weight if available
        if doc.soft_weight is not None:
            header_parts.append(f"Peso: {doc.soft_weight:.1%}")

        if doc.total_chunks and doc.total_chunks > 1:
            header_parts.append(f"Fragmento: {(doc.chunk_index or 0) + 1}/{doc.total_chunks}")

        header = "\n".join(header_parts)
        header_separator = "\n---\n"

        # Calculate available chars for content
        header_chars = len(header) + len(header_separator) + 50  # Buffer for truncation notice
        available_content_chars = max_chars - header_chars

        if available_content_chars < 100:
            # Not enough space, return minimal
            return f"{header}\n---\n[Contenido omitido por presupuesto de tokens]", header

        # Get and format content
        content = doc.content

        # Format content based on intent
        if intent == QueryIntent.SUMMARIZE:
            content = self._format_for_summary(content)
        elif intent == QueryIntent.EXTRACT:
            content = self._format_for_extraction(content)
        elif intent == QueryIntent.ANALYZE:
            content = self._format_for_analysis(content)
        else:
            content = self._clean_content(content)

        # Truncate if necessary using smart truncation
        if len(content) > available_content_chars:
            content, sections_omitted = self._smart_truncate(
                content,
                available_content_chars,
            )
            truncation_notice = ""
            if sections_omitted > 0:
                truncation_notice = f"\n[... {sections_omitted} secciones adicionales omitidas]"
            content = content + truncation_notice

        # Combine header and content
        full_section = f"{header}{header_separator}{content}"

        return full_section, header

    def _smart_truncate(
        self,
        content: str,
        max_chars: int,
    ) -> Tuple[str, int]:
        """
        Smart truncation with priority: sections > paragraphs > sentences.

        Preserves structural integrity by cutting at semantic boundaries.

        Returns:
            Tuple of (truncated_content, sections_omitted_count)
        """
        if len(content) <= max_chars:
            return content, 0

        # Priority based on config
        priority = self._truncation_priority

        if priority == "sections":
            # Try to cut at section boundaries first
            truncated, omitted = self._truncate_at_sections(content, max_chars)
            if truncated:
                return truncated, omitted

        # Fall through to paragraph truncation
        if priority in ("sections", "paragraphs"):
            truncated = self._truncate_at_paragraphs(content, max_chars)
            if truncated:
                return truncated, 0

        # Fall through to sentence truncation
        truncated = self._truncate_at_sentences(content, max_chars)
        if truncated:
            return truncated, 0

        # Last resort: word boundary
        truncated = self._truncate_at_words(content, max_chars)
        return truncated, 0

    def _truncate_at_sections(
        self,
        content: str,
        max_chars: int,
    ) -> Tuple[Optional[str], int]:
        """
        Truncate at section boundaries (headings, legal markers).

        Returns:
            Tuple of (truncated_content or None, sections_omitted)
        """
        # Find all section boundaries
        section_positions = [0]  # Start of content is always a section

        for pattern in SECTION_MARKERS:
            for match in re.finditer(pattern, content, re.MULTILINE):
                section_positions.append(match.start())

        section_positions = sorted(set(section_positions))

        if len(section_positions) < 2:
            return None, 0  # No sections found, fall through

        # Find the last section that fits
        best_cut = 0
        sections_included = 0

        for i, pos in enumerate(section_positions):
            if pos <= max_chars * 0.95:  # Leave some margin
                best_cut = pos
                sections_included = i + 1
            else:
                break

        if best_cut > max_chars * 0.5:  # At least 50% of content
            # Find actual end of the section (before next section or end)
            next_section_idx = section_positions.index(best_cut) + 1
            if next_section_idx < len(section_positions):
                section_end = section_positions[next_section_idx]
                if section_end <= max_chars:
                    best_cut = section_end

            truncated = content[:best_cut].rstrip()
            sections_omitted = len(section_positions) - sections_included
            return truncated, max(0, sections_omitted)

        return None, 0

    def _truncate_at_paragraphs(self, content: str, max_chars: int) -> Optional[str]:
        """Truncate at paragraph boundaries (\n\n)."""
        paragraphs = content.split('\n\n')

        result = []
        current_length = 0

        for para in paragraphs:
            para_len = len(para) + 2  # +2 for \n\n
            if current_length + para_len <= max_chars:
                result.append(para)
                current_length += para_len
            else:
                break

        if result and current_length > max_chars * 0.5:
            return '\n\n'.join(result)

        return None

    def _truncate_at_sentences(self, content: str, max_chars: int) -> Optional[str]:
        """Truncate at sentence boundaries (. ? !)."""
        # Find sentence endings
        sentence_pattern = r'[.!?][\s\n]+'

        last_good_end = 0
        for match in re.finditer(sentence_pattern, content):
            if match.end() <= max_chars:
                last_good_end = match.end()
            else:
                break

        if last_good_end > max_chars * 0.6:  # At least 60% of target
            return content[:last_good_end].rstrip()

        return None

    def _truncate_at_words(self, content: str, max_chars: int) -> str:
        """Truncate at word boundary (last resort)."""
        truncated = content[:max_chars]
        last_space = truncated.rfind(' ')

        if last_space > max_chars * 0.8:
            return truncated[:last_space].rstrip() + "..."

        return truncated.rstrip() + "..."

    def _format_for_summary(self, content: str) -> str:
        """Format content for summarization intent"""
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
        if not content:
            return ""

        # Normalize newlines first (preserve structure)
        content = content.replace("\r\n", "\n").replace("\r", "\n")

        # Trim trailing whitespace per line (keeps paragraph boundaries)
        content = "\n".join(line.rstrip() for line in content.split("\n"))

        # Collapse excessive blank lines but keep paragraphs
        content = re.sub(r"\n{3,}", "\n\n", content)

        # Collapse repeated spaces/tabs inside lines (without killing newlines)
        content = re.sub(r"[ \t]{2,}", " ", content)

        # Remove leading/trailing whitespace
        return content.strip()

    def _truncate_section(self, section: str, available_chars: int) -> Optional[str]:
        """
        Legacy method for truncating a section to fit available space.

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

        # Use smart truncation
        truncated_content, _ = self._smart_truncate(content, available_content)

        return f"{header}{truncated_content}\n[... contenido truncado ...]"

    def get_token_count(self, text: str) -> int:
        """Estimate token count for text"""
        return len(text) // self._chars_per_token


# Global instance
context_assembler = ContextAssembler()
