"""
Document Structure Parser

Parses raw text into a hierarchical tree structure based on document patterns:
- legal_es: Spanish legal documents (TÍTULO, CAPÍTULO, SECCIÓN, CLÁUSULA)
- markdown: Markdown-style headings (#, ##, ###)
- numbered: Numbered sections (1., 1.1., 1.1.1.)

The parser detects the document type automatically and applies the appropriate
parsing strategy to build the document tree.

Usage:
    from app.services.rag.structure_parser import structure_parser

    tree = await structure_parser.parse(
        text="TÍTULO I. Disposiciones Generales...",
        document_id="doc-123",
        tenant_id="tenant-abc",
        document_type="auto"  # or "legal_es", "markdown", "numbered"
    )
"""

import logging
import re
import time
import uuid
from typing import List, Dict, Any, Optional, Tuple, Pattern
from dataclasses import dataclass

from .document_structure import (
    NodoEstructura,
    ArbolDocumento,
    NivelJerarquico,
)
from ...core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class HeadingMatch:
    """A matched heading in the document."""
    text: str           # Full matched text
    titulo: str         # Extracted title
    nivel: NivelJerarquico
    char_start: int
    char_end: int
    pattern_name: str   # Which pattern matched


class StructureParser:
    """
    Parses document text into hierarchical structure tree.

    Supports multiple document formats:
    - Spanish legal documents (TÍTULO, CAPÍTULO, ARTÍCULO, etc.)
    - Markdown headings (#, ##, ###, etc.)
    - Numbered sections (1., 1.1., 1.1.1., etc.)

    The parser automatically detects the format or can be explicitly specified.
    """

    def __init__(self):
        self._max_depth = settings.rag_max_tree_depth if hasattr(settings, 'rag_max_tree_depth') else 6

        # Pattern definitions for different document types
        # Each pattern maps regex → (NivelJerarquico, priority)
        self._patterns: Dict[str, Dict[str, Tuple[Pattern, NivelJerarquico, int]]] = {
            "legal_es": self._build_legal_es_patterns(),
            "markdown": self._build_markdown_patterns(),
            "numbered": self._build_numbered_patterns(),
        }

    def _build_legal_es_patterns(self) -> Dict[str, Tuple[Pattern, NivelJerarquico, int]]:
        """
        Build patterns for Spanish legal documents.

        Matches structures like:
        - TÍTULO I. Disposiciones Generales
        - TÍTULO PRIMERO - Del Objeto
        - Capítulo 1 - Definiciones
        - Sección 1.1 - Términos
        - Artículo 5. Obligaciones
        - Cláusula Primera.- Partes
        """
        return {
            "titulo_romano": (
                re.compile(
                    r'^[\s]*(?:TÍTULO|TITULO)\s+([IVXLCDM]+(?:\s*[.-])?\s*.{0,100}?)(?:\n|$)',
                    re.MULTILINE | re.IGNORECASE
                ),
                NivelJerarquico.TITULO,
                1
            ),
            "titulo_ordinal": (
                re.compile(
                    r'^[\s]*(?:TÍTULO|TITULO)\s+(?:PRIMER[OA]?|SEGUND[OA]|TERCER[OA]|CUART[OA]|QUINT[OA]|SEXT[OA]|SÉPTIM[OA]|OCTAV[OA]|NOVEN[OA]|DÉCIM[OA])[\s.-]+(.{0,100}?)(?:\n|$)',
                    re.MULTILINE | re.IGNORECASE
                ),
                NivelJerarquico.TITULO,
                2
            ),
            "capitulo": (
                re.compile(
                    r'^[\s]*(?:CAPÍTULO|CAPITULO|Cap\.?)\s*(\d+|[IVXLCDM]+)[\s.:,-]+(.{0,100}?)(?:\n|$)',
                    re.MULTILINE | re.IGNORECASE
                ),
                NivelJerarquico.CAPITULO,
                3
            ),
            "seccion": (
                re.compile(
                    r'^[\s]*(?:SECCIÓN|SECCION|Secc?\.?)\s*(\d+(?:\.\d+)?)[\s.:,-]+(.{0,100}?)(?:\n|$)',
                    re.MULTILINE | re.IGNORECASE
                ),
                NivelJerarquico.SECCION,
                4
            ),
            "articulo": (
                re.compile(
                    r'^[\s]*(?:ARTÍCULO|ARTICULO|Art\.?)\s*(\d+)[\s.:,-]+(.{0,100}?)(?:\n|$)',
                    re.MULTILINE | re.IGNORECASE
                ),
                NivelJerarquico.CLAUSULA,
                5
            ),
            "clausula": (
                re.compile(
                    r'^[\s]*(?:CLÁUSULA|CLAUSULA)\s+(?:(\d+)|(?:PRIMER[OA]?|SEGUND[OA]|TERCER[OA]|CUART[OA]|QUINT[OA]|SEXT[OA]|SÉPTIM[OA]|OCTAV[OA]|NOVEN[OA]|DÉCIM[OA]))[\s.:,-]+(.{0,100}?)(?:\n|$)',
                    re.MULTILINE | re.IGNORECASE
                ),
                NivelJerarquico.CLAUSULA,
                5
            ),
            "disposicion": (
                re.compile(
                    r'^[\s]*(?:DISPOSICIÓN|DISPOSICION)\s+(?:ADICIONAL|TRANSITORIA|FINAL|DEROGATORIA)\s*(.{0,100}?)(?:\n|$)',
                    re.MULTILINE | re.IGNORECASE
                ),
                NivelJerarquico.SECCION,
                4
            ),
        }

    def _build_markdown_patterns(self) -> Dict[str, Tuple[Pattern, NivelJerarquico, int]]:
        """
        Build patterns for Markdown documents.

        Matches:
        - # Heading 1 → TITULO
        - ## Heading 2 → CAPITULO
        - ### Heading 3 → SECCION
        - #### Heading 4 → SUBSECCION
        - ##### Heading 5+ → CLAUSULA
        """
        return {
            "h1": (
                re.compile(r'^#\s+(.+?)(?:\n|$)', re.MULTILINE),
                NivelJerarquico.TITULO,
                1
            ),
            "h2": (
                re.compile(r'^##\s+(.+?)(?:\n|$)', re.MULTILINE),
                NivelJerarquico.CAPITULO,
                2
            ),
            "h3": (
                re.compile(r'^###\s+(.+?)(?:\n|$)', re.MULTILINE),
                NivelJerarquico.SECCION,
                3
            ),
            "h4": (
                re.compile(r'^####\s+(.+?)(?:\n|$)', re.MULTILINE),
                NivelJerarquico.SUBSECCION,
                4
            ),
            "h5": (
                re.compile(r'^#####\s+(.+?)(?:\n|$)', re.MULTILINE),
                NivelJerarquico.CLAUSULA,
                5
            ),
            "h6": (
                re.compile(r'^######\s+(.+?)(?:\n|$)', re.MULTILINE),
                NivelJerarquico.CLAUSULA,
                6
            ),
        }

    def _build_numbered_patterns(self) -> Dict[str, Tuple[Pattern, NivelJerarquico, int]]:
        """
        Build patterns for numbered sections.

        Matches:
        - 1. Section → CAPITULO
        - 1.1 Subsection → SECCION
        - 1.1.1 Sub-subsection → SUBSECCION
        - 1.1.1.1 → CLAUSULA
        """
        return {
            "level1": (
                re.compile(r'^(\d+)\.\s+(.+?)(?:\n|$)', re.MULTILINE),
                NivelJerarquico.CAPITULO,
                1
            ),
            "level2": (
                re.compile(r'^(\d+\.\d+)[\s.]+(.+?)(?:\n|$)', re.MULTILINE),
                NivelJerarquico.SECCION,
                2
            ),
            "level3": (
                re.compile(r'^(\d+\.\d+\.\d+)[\s.]+(.+?)(?:\n|$)', re.MULTILINE),
                NivelJerarquico.SUBSECCION,
                3
            ),
            "level4": (
                re.compile(r'^(\d+\.\d+\.\d+\.\d+)[\s.]+(.+?)(?:\n|$)', re.MULTILINE),
                NivelJerarquico.CLAUSULA,
                4
            ),
        }

    async def parse(
        self,
        text: str,
        document_id: str,
        tenant_id: str,
        document_type: str = "auto",
        title: Optional[str] = None,
    ) -> ArbolDocumento:
        """
        Parse document text into hierarchical structure.

        Args:
            text: Raw document text
            document_id: Document identifier
            tenant_id: Tenant identifier
            document_type: Type of document ("auto", "legal_es", "markdown", "numbered")
            title: Optional document title (used as root node title)

        Returns:
            ArbolDocumento with parsed hierarchical structure
        """
        start_time = time.time()

        # Auto-detect document type if needed
        if document_type == "auto":
            document_type = self._detect_document_type(text)
            logger.info(f"[{document_id}] Auto-detected document type: {document_type}")

        # Get patterns for this document type
        patterns = self._patterns.get(document_type, self._patterns["numbered"])

        # Find all headings
        headings = self._find_all_headings(text, patterns)
        logger.info(f"[{document_id}] Found {len(headings)} structural headings")

        # Build tree from headings
        if headings:
            root = self._build_tree_from_headings(
                text=text,
                headings=headings,
                title=title or "Documento",
                document_id=document_id,
            )
        else:
            # No structure found - create simple single-node tree
            logger.warning(f"[{document_id}] No structure detected, creating simple tree")
            root = NodoEstructura(
                id=str(uuid.uuid4()),
                nivel=NivelJerarquico.DOCUMENTO,
                titulo=title or "Documento",
                contenido=text,
                char_start=0,
                char_end=len(text),
            )

        parsing_time = (time.time() - start_time) * 1000

        tree = ArbolDocumento(
            document_id=document_id,
            tenant_id=tenant_id,
            raiz=root,
            document_type=document_type,
            parsing_time_ms=parsing_time,
        )

        logger.info(
            f"[{document_id}] Structure parsing complete: "
            f"{tree.total_nodos} nodes, max depth {tree.profundidad_maxima}, "
            f"{parsing_time:.1f}ms"
        )

        return tree

    def _detect_document_type(self, text: str) -> str:
        """
        Auto-detect document type based on content patterns.

        Analyzes the first portion of the document to find characteristic patterns.
        """
        # Sample the first 5000 characters for detection
        sample = text[:5000].upper()

        # Score each document type
        scores = {
            "legal_es": 0,
            "markdown": 0,
            "numbered": 0,
        }

        # Legal Spanish patterns
        legal_indicators = [
            "TÍTULO", "TITULO", "CAPÍTULO", "CAPITULO",
            "ARTÍCULO", "ARTICULO", "CLÁUSULA", "CLAUSULA",
            "SECCIÓN", "SECCION", "DISPOSICIÓN", "DISPOSICION",
        ]
        for indicator in legal_indicators:
            scores["legal_es"] += sample.count(indicator)

        # Markdown patterns (check original text, not uppercased)
        markdown_pattern = re.compile(r'^#{1,6}\s+', re.MULTILINE)
        scores["markdown"] = len(markdown_pattern.findall(text[:5000]))

        # Numbered patterns
        numbered_pattern = re.compile(r'^\d+\.(?:\d+\.)*\s+', re.MULTILINE)
        scores["numbered"] = len(numbered_pattern.findall(text[:5000]))

        # Return type with highest score (default to numbered)
        best_type = max(scores, key=scores.get)
        if scores[best_type] == 0:
            return "numbered"  # Default fallback

        return best_type

    def _find_all_headings(
        self,
        text: str,
        patterns: Dict[str, Tuple[Pattern, NivelJerarquico, int]],
    ) -> List[HeadingMatch]:
        """
        Find all heading matches in text using given patterns.

        Returns sorted list of HeadingMatch objects.
        """
        headings = []

        for pattern_name, (pattern, nivel, priority) in patterns.items():
            for match in pattern.finditer(text):
                # Extract title from match groups
                groups = match.groups()
                if len(groups) >= 2:
                    # Pattern has number/identifier and title
                    titulo = f"{groups[0]} - {groups[1]}".strip()
                elif len(groups) == 1:
                    titulo = groups[0].strip()
                else:
                    titulo = match.group().strip()

                # Clean up title
                titulo = re.sub(r'\s+', ' ', titulo)
                titulo = titulo.strip('.-: ')

                if len(titulo) > 200:
                    titulo = titulo[:200] + "..."

                heading = HeadingMatch(
                    text=match.group(),
                    titulo=titulo,
                    nivel=nivel,
                    char_start=match.start(),
                    char_end=match.end(),
                    pattern_name=pattern_name,
                )
                headings.append(heading)

        # Sort by position in document
        headings.sort(key=lambda h: h.char_start)

        # Remove overlapping matches (keep higher priority/earlier)
        filtered = []
        last_end = -1
        for heading in headings:
            if heading.char_start >= last_end:
                filtered.append(heading)
                last_end = heading.char_end

        return filtered

    def _build_tree_from_headings(
        self,
        text: str,
        headings: List[HeadingMatch],
        title: str,
        document_id: str,
    ) -> NodoEstructura:
        """
        Build document tree from list of headings.

        Creates parent-child relationships based on hierarchical levels.
        """
        # Create root node
        root = NodoEstructura(
            id=str(uuid.uuid4()),
            nivel=NivelJerarquico.DOCUMENTO,
            titulo=title,
            contenido="",  # Root has no direct content
            char_start=0,
            char_end=len(text),
        )

        # Track current path in tree (stack of parent nodes)
        # This allows us to find the correct parent for each new node
        node_stack: List[NodoEstructura] = [root]

        for i, heading in enumerate(headings):
            # Calculate content for this heading (until next heading or end)
            content_start = heading.char_end
            if i + 1 < len(headings):
                content_end = headings[i + 1].char_start
            else:
                content_end = len(text)

            content = text[content_start:content_end].strip()

            # Create node for this heading
            node = NodoEstructura(
                id=str(uuid.uuid4()),
                nivel=heading.nivel,
                titulo=heading.titulo,
                contenido=content,
                char_start=heading.char_start,
                char_end=content_end,
                metadata={"pattern": heading.pattern_name},
            )

            # Find correct parent (pop stack until we find a higher-level node)
            node_depth = NivelJerarquico.get_depth(heading.nivel)

            while len(node_stack) > 1:
                parent = node_stack[-1]
                parent_depth = NivelJerarquico.get_depth(parent.nivel)

                if parent_depth < node_depth:
                    # Found a valid parent
                    break
                # Pop this level and try again
                node_stack.pop()

            # Add as child to current parent
            parent = node_stack[-1]
            parent.hijos.append(node)

            # Push this node onto stack (it might be parent of following nodes)
            node_stack.append(node)

            # Respect max depth
            if len(node_stack) > self._max_depth:
                node_stack = node_stack[:self._max_depth]

        # Add any leading content (before first heading) to root
        if headings and headings[0].char_start > 0:
            leading_content = text[:headings[0].char_start].strip()
            if leading_content:
                root.contenido = leading_content

        return root

    def parse_to_flat_sections(
        self,
        text: str,
        document_type: str = "auto",
    ) -> List[Dict[str, Any]]:
        """
        Parse document into flat list of sections (for simple use cases).

        Returns list of {titulo, contenido, nivel, char_start, char_end}.
        This is useful when you don't need the full tree structure.
        """
        # Auto-detect document type if needed
        if document_type == "auto":
            document_type = self._detect_document_type(text)

        patterns = self._patterns.get(document_type, self._patterns["numbered"])
        headings = self._find_all_headings(text, patterns)

        sections = []

        for i, heading in enumerate(headings):
            content_start = heading.char_end
            if i + 1 < len(headings):
                content_end = headings[i + 1].char_start
            else:
                content_end = len(text)

            content = text[content_start:content_end].strip()

            sections.append({
                "titulo": heading.titulo,
                "contenido": content,
                "nivel": heading.nivel.value,
                "char_start": heading.char_start,
                "char_end": content_end,
            })

        return sections


# Global singleton instance
structure_parser = StructureParser()
