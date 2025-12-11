"""
PDF to Markdown Conversion Service

Uses PyMuPDF4LLM to convert PDFs to LLM-optimized Markdown format.
This provides a cleaner text representation than raw PDF viewing,
with preserved structure (headings, tables, lists).
"""

import logging
import io
import re
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

import fitz  # PyMuPDF
import pymupdf4llm

logger = logging.getLogger(__name__)


@dataclass
class MarkdownPage:
    """Represents a single page of Markdown content."""
    page_number: int
    content: str
    char_count: int


@dataclass
class MarkdownDocument:
    """Complete document converted to Markdown."""
    full_markdown: str
    pages: List[MarkdownPage]
    total_pages: int
    total_chars: int
    metadata: Dict[str, Any]


class PDFMarkdownService:
    """
    Service for converting PDFs to Markdown format using PyMuPDF4LLM.

    Features:
    - Preserves document structure (headings, paragraphs, lists)
    - Extracts tables in Markdown format
    - Handles multi-column layouts
    - Provides page-by-page access for large documents
    """

    def __init__(self):
        self._cache: Dict[str, MarkdownDocument] = {}

    def convert_pdf_bytes(
        self,
        pdf_bytes: bytes,
        cache_key: Optional[str] = None,
        page_chunks: bool = True,
        write_images: bool = False,
        show_progress: bool = False
    ) -> MarkdownDocument:
        """
        Convert PDF bytes to Markdown.

        Args:
            pdf_bytes: Raw PDF content
            cache_key: Optional key for caching results
            page_chunks: If True, splits result by pages
            write_images: If True, includes base64 images in output
            show_progress: If True, logs progress for large documents

        Returns:
            MarkdownDocument with full content and per-page breakdown
        """
        # Check cache first
        if cache_key and cache_key in self._cache:
            logger.debug(f"Returning cached Markdown for {cache_key}")
            return self._cache[cache_key]

        try:
            # Open PDF from bytes
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            total_pages = len(doc)

            if show_progress:
                logger.info(f"Converting {total_pages} page PDF to Markdown")

            # Extract metadata
            metadata = {
                "title": doc.metadata.get("title", ""),
                "author": doc.metadata.get("author", ""),
                "subject": doc.metadata.get("subject", ""),
                "creator": doc.metadata.get("creator", ""),
                "pages": total_pages
            }

            # Convert to Markdown using pymupdf4llm
            # page_chunks=True returns list of dicts with 'text' key per page
            md_output = pymupdf4llm.to_markdown(
                doc,
                page_chunks=page_chunks,
                write_images=write_images,
                show_progress=show_progress
            )

            # Process output
            pages: List[MarkdownPage] = []
            full_content_parts: List[str] = []

            if page_chunks and isinstance(md_output, list):
                # Output is list of dicts with 'text' per page
                for idx, page_data in enumerate(md_output):
                    page_text = page_data.get("text", "") if isinstance(page_data, dict) else str(page_data)

                    # Clean up the markdown
                    page_text = self._clean_markdown(page_text)

                    pages.append(MarkdownPage(
                        page_number=idx + 1,
                        content=page_text,
                        char_count=len(page_text)
                    ))
                    full_content_parts.append(page_text)
            else:
                # Single string output
                md_text = md_output if isinstance(md_output, str) else str(md_output)
                md_text = self._clean_markdown(md_text)

                # Try to split by page markers if present
                page_marker_pattern = r'(?:^|\n)(?:---+\s*)?(?:Página|Page)\s+(\d+)\s*(?:---+)?\n'
                page_splits = re.split(page_marker_pattern, md_text)

                if len(page_splits) > 1:
                    # Found page markers
                    current_page = 1
                    for i, part in enumerate(page_splits):
                        if part.strip().isdigit():
                            current_page = int(part)
                        elif part.strip():
                            pages.append(MarkdownPage(
                                page_number=current_page,
                                content=part.strip(),
                                char_count=len(part)
                            ))
                else:
                    # No page markers - treat as single page
                    pages.append(MarkdownPage(
                        page_number=1,
                        content=md_text,
                        char_count=len(md_text)
                    ))

                full_content_parts = [md_text]

            # Build result
            full_markdown = "\n\n---\n\n".join(full_content_parts)
            result = MarkdownDocument(
                full_markdown=full_markdown,
                pages=pages,
                total_pages=total_pages,
                total_chars=len(full_markdown),
                metadata=metadata
            )

            # Cache if key provided
            if cache_key:
                self._cache[cache_key] = result

            doc.close()
            return result

        except Exception as e:
            logger.error(f"Error converting PDF to Markdown: {e}")
            raise

    def convert_pdf_file(self, file_path: str, **kwargs) -> MarkdownDocument:
        """Convert PDF file to Markdown."""
        with open(file_path, "rb") as f:
            return self.convert_pdf_bytes(f.read(), **kwargs)

    def get_page_markdown(
        self,
        pdf_bytes: bytes,
        page_number: int,
        cache_key: Optional[str] = None
    ) -> Optional[str]:
        """
        Get Markdown for a specific page.

        Args:
            pdf_bytes: Raw PDF content
            page_number: 1-indexed page number
            cache_key: Optional cache key

        Returns:
            Markdown content for the page, or None if page doesn't exist
        """
        doc = self.convert_pdf_bytes(pdf_bytes, cache_key=cache_key)

        for page in doc.pages:
            if page.page_number == page_number:
                return page.content

        return None

    def inject_annotations(
        self,
        markdown: str,
        annotations: List[Dict[str, Any]],
        style: str = "highlight"
    ) -> str:
        """
        Inject analysis findings into Markdown as inline annotations.

        Args:
            markdown: Original Markdown content
            annotations: List of findings with 'quote' and metadata
            style: How to style annotations ('highlight', 'inline', 'footnote')

        Returns:
            Markdown with annotations injected
        """
        result = markdown

        for ann in annotations:
            quote = ann.get("quote", "")
            if not quote or len(quote) < 10:
                continue

            # Get annotation type and create appropriate markup
            ann_type = ann.get("type", "info")
            severity = ann.get("severity", "medium")
            title = ann.get("title", "")
            ann_id = ann.get("id", "")

            # Create annotation markup based on style
            if style == "highlight":
                # Use HTML mark tags with data attributes
                if ann_type == "risk":
                    color = "yellow" if severity == "low" else "orange" if severity == "medium" else "red"
                    markup = f'<mark data-type="risk" data-severity="{severity}" data-id="{ann_id}" style="background-color: {color}; cursor: pointer;" title="{title}">{quote}</mark>'
                else:
                    markup = f'<mark data-type="recommendation" data-id="{ann_id}" style="background-color: lightblue; cursor: pointer;" title="{title}">{quote}</mark>'
            elif style == "inline":
                # Add inline annotation marker
                emoji = "⚠️" if ann_type == "risk" else "💡"
                markup = f'**{quote}** [{emoji} {title}]'
            else:  # footnote
                # Add footnote reference
                markup = f'{quote}[^{ann_id}]'

            # Replace quote in text (fuzzy match for whitespace differences)
            quote_pattern = re.escape(quote)
            quote_pattern = quote_pattern.replace(r"\ ", r"\s+")
            result = re.sub(quote_pattern, markup, result, count=1, flags=re.IGNORECASE)

        return result

    def _clean_markdown(self, text: str) -> str:
        """Clean up and normalize Markdown output."""
        if not text:
            return ""

        # Remove excessive whitespace
        text = re.sub(r'\n{4,}', '\n\n\n', text)

        # Fix broken list items
        text = re.sub(r'\n-\s*\n', '\n', text)

        # Normalize heading spacing
        text = re.sub(r'(#{1,6})\s+', r'\1 ', text)

        # Remove empty table rows
        text = re.sub(r'\|\s*\|\s*\|', '', text)

        # Strip leading/trailing whitespace
        text = text.strip()

        return text

    def clear_cache(self, cache_key: Optional[str] = None):
        """Clear cached Markdown documents."""
        if cache_key:
            self._cache.pop(cache_key, None)
        else:
            self._cache.clear()


# Singleton instance
_markdown_service: Optional[PDFMarkdownService] = None


def get_pdf_markdown_service() -> PDFMarkdownService:
    """Get or create the PDF Markdown service singleton."""
    global _markdown_service
    if _markdown_service is None:
        _markdown_service = PDFMarkdownService()
    return _markdown_service
