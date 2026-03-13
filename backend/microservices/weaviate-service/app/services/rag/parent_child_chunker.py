"""
Parent-Child Chunk Retrieval

Implements the "search small, retrieve large" pattern:
- Parents (~1500 tokens): Large semantic chunks for rich LLM context
- Children (~300 tokens): Small sub-chunks for precise vector matching

Architecture:
    Document → SemanticChunker (section-aware) → Parents (~1500 tokens)
              → RecursiveCharacterTextSplitter → Children (~300 tokens, overlap 50)
              → Weaviate: children with vector + parent_content as TEXT property (not vectorized)
              → Search: match children → return parent_content to LLM

The children carry their parent's content as a non-vectorized Weaviate property.
SmartSearch transparently swaps `content` for `parent_content` when available,
giving the LLM richer context while maintaining precise vector matching.

Usage:
    from app.services.rag.parent_child_chunker import parent_child_chunker

    children = parent_child_chunker.chunk_with_parents(text, metadata, doc_type)
    # Each child has: content, parent_content, parent_chunk_id, child_index
"""

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ChildChunk:
    """A child chunk with reference to its parent."""
    content: str
    parent_content: str
    parent_chunk_id: str
    child_index: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    section_title: Optional[str] = None
    chunk_index: int = 0  # Global index across all children
    total_chunks: int = 1
    token_count: int = 0


class ParentChildChunker:
    """Creates parent-child chunk hierarchies for the "search small, retrieve large" pattern.

    Parents are produced by SemanticChunker (structure-aware, ~1500 tokens).
    Children are created by splitting each parent into smaller overlapping chunks.
    """

    def __init__(
        self,
        parent_chunk_size: int = 0,
        child_chunk_size: int = 0,
        child_overlap: int = 0,
    ):
        self._parent_size = parent_chunk_size or settings.parent_chunk_size
        self._child_size = child_chunk_size or settings.child_chunk_size
        self._child_overlap = child_overlap or settings.child_chunk_overlap

    def chunk_with_parents(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        doc_type: str = "general",
    ) -> List[ChildChunk]:
        """Split document into parent-child chunk hierarchy.

        Args:
            text: Full document text.
            metadata: Document metadata to propagate to children.
            doc_type: Document type hint for SemanticChunker.

        Returns:
            List of ChildChunk objects, each containing its parent's content.
        """
        metadata = metadata or {}

        # Step 1: Create parents using SemanticChunker (reuse existing logic)
        parents = self._create_parents(text, metadata, doc_type)

        if not parents:
            logger.warning("ParentChildChunker: SemanticChunker returned 0 parents")
            return []

        # Step 2: Split each parent into children
        children: List[ChildChunk] = []
        global_index = 0

        for parent in parents:
            parent_id = self._generate_parent_id(parent.content)
            child_texts = self._split_into_children(parent.content)

            for child_idx, child_text in enumerate(child_texts):
                children.append(ChildChunk(
                    content=child_text,
                    parent_content=parent.content,
                    parent_chunk_id=parent_id,
                    child_index=child_idx,
                    metadata={
                        **metadata,
                        **(parent.metadata if hasattr(parent, 'metadata') else {}),
                        "parent_chunk_id": parent_id,
                        "child_index": child_idx,
                        "children_count": len(child_texts),
                    },
                    section_title=parent.section_title if hasattr(parent, 'section_title') else None,
                    chunk_index=global_index,
                    token_count=len(child_text) // 4,  # Rough estimate
                ))
                global_index += 1

        # Cap total children per document (prevent storage explosion)
        MAX_CHILDREN = 500
        if len(children) > MAX_CHILDREN:
            logger.warning(
                f"ParentChildChunker: capping {len(children)} children → {MAX_CHILDREN} "
                f"(document too large for fine-grained chunking)"
            )
            children = children[:MAX_CHILDREN]

        # Set total_chunks on all children
        total = len(children)
        for child in children:
            child.total_chunks = total

        logger.info(
            f"ParentChildChunker: {len(parents)} parents → {len(children)} children "
            f"(parent ~{self._parent_size} tokens, child ~{self._child_size} tokens)"
        )

        return children

    def _create_parents(self, text: str, metadata: Dict[str, Any], doc_type: str):
        """Create parent chunks using SemanticChunker with larger target size.

        After SemanticChunker, any oversized parents (> 3x target) are force-split
        to prevent child explosion (e.g., 16K children from one massive parent).
        """
        try:
            from .semantic_chunker import SemanticChunker, DocumentType

            # Map doc_type string to enum
            try:
                dt = DocumentType(doc_type) if doc_type else DocumentType.GENERAL
            except (ValueError, KeyError):
                dt = DocumentType.GENERAL

            chunker = SemanticChunker(
                chunk_size=self._parent_size,
                max_chunk_size=self._parent_size * 2,
            )

            raw_parents = chunker.chunk_document(text, metadata=metadata, document_type=dt)

            # Guard: force-split any parent exceeding 3x target size
            return self._cap_parent_sizes(raw_parents, metadata)

        except Exception as e:
            logger.error(f"SemanticChunker failed for parents: {e}")
            # Fallback: simple text splitting
            return self._fallback_split(text, self._parent_size, metadata)

    def _cap_parent_sizes(self, parents, metadata: Dict[str, Any]):
        """Split oversized parents to prevent child explosion.

        If a parent exceeds 3x target size (in chars), force-split it into
        ~parent_size chunks using sentence-aware splitting.
        """
        from .semantic_chunker import DocumentChunk

        max_parent_chars = self._parent_size * 4 * 3  # 3x target, in chars (~18K chars for 1500 tok target)
        result = []

        for parent in parents:
            if len(parent.content) <= max_parent_chars:
                result.append(parent)
            else:
                # Force-split oversized parent
                oversized_chars = len(parent.content)
                target_chars = self._parent_size * 4  # ~6000 chars for 1500 tokens
                sub_texts = self._force_split_text(parent.content, target_chars)
                for i, sub_text in enumerate(sub_texts):
                    result.append(DocumentChunk(
                        content=sub_text,
                        metadata={**parent.metadata, "force_split_index": i},
                        section_title=parent.section_title,
                        chunk_index=0,
                    ))
                logger.info(
                    f"ParentChildChunker: force-split oversized parent "
                    f"({oversized_chars} chars → {len(sub_texts)} sub-parents)"
                )

        return result

    @staticmethod
    def _force_split_text(text: str, target_chars: int) -> List[str]:
        """Split text into chunks of ~target_chars, breaking at sentence boundaries."""
        chunks = []
        start = 0
        text_len = len(text)

        while start < text_len:
            end = min(start + target_chars, text_len)

            # Try to break at sentence boundary within last 20%
            if end < text_len:
                search_start = max(start, end - target_chars // 5)
                for sep in ['. ', '.\n', '\n\n', '; ', '\n']:
                    last_sep = text.rfind(sep, search_start, end)
                    if last_sep > start:
                        end = last_sep + len(sep)
                        break

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            start = end

        return chunks if chunks else [text]

    def _split_into_children(self, parent_text: str) -> List[str]:
        """Split a parent chunk into overlapping children."""
        if len(parent_text) <= self._child_size * 4:  # ~chars, not tokens
            return [parent_text]

        # Character-level splitting (approximate tokens as chars/4)
        char_size = self._child_size * 4
        char_overlap = self._child_overlap * 4

        children = []
        start = 0
        text_len = len(parent_text)

        while start < text_len:
            end = min(start + char_size, text_len)

            # Try to break at sentence boundary
            if end < text_len:
                # Look for sentence end within last 20% of chunk
                search_start = max(start, end - char_size // 5)
                for sep in ['. ', '.\n', '\n\n', '; ', '\n']:
                    last_sep = parent_text.rfind(sep, search_start, end)
                    if last_sep > start:
                        end = last_sep + len(sep)
                        break

            chunk_text = parent_text[start:end].strip()
            if chunk_text:
                children.append(chunk_text)

            # Advance with overlap
            start = end - char_overlap if end < text_len else text_len

        return children if children else [parent_text]

    @staticmethod
    def _generate_parent_id(content: str) -> str:
        """Generate a stable ID for a parent chunk based on its content."""
        return hashlib.sha256(content[:500].encode()).hexdigest()[:16]

    @staticmethod
    def _fallback_split(text: str, chunk_size: int, metadata: Dict[str, Any]):
        """Simple fallback splitting when SemanticChunker fails."""
        from .semantic_chunker import DocumentChunk

        char_size = chunk_size * 4
        chunks = []
        for i in range(0, len(text), char_size):
            chunk_text = text[i:i + char_size].strip()
            if chunk_text:
                chunks.append(DocumentChunk(
                    content=chunk_text,
                    metadata=metadata,
                    chunk_index=len(chunks),
                ))
        return chunks


# Global instance
parent_child_chunker = ParentChildChunker()
