"""
Document Structure Models for Hierarchical RAG

Defines the data structures for representing document hierarchy:
- NodoEstructura: A node in the document tree (chapter, section, paragraph, etc.)
- ArbolDocumento: The complete document tree with metadata

This hierarchical representation enables:
1. Bottom-up summary generation (leaves → root)
2. Structure-aware chunking respecting section boundaries
3. Hierarchical retrieval (summary → section → paragraph)

Reference: "Hierarchical Indexing for Long Context RAG"
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime


class NivelJerarquico(str, Enum):
    """
    Hierarchical levels in a document structure.

    Ordered from highest (document) to lowest (list item):
    DOCUMENTO > TITULO > CAPITULO > SECCION > SUBSECCION > CLAUSULA > PARRAFO > LISTA
    """
    DOCUMENTO = "documento"      # Root level - entire document
    TITULO = "titulo"            # Title/Part - e.g., "TÍTULO I - Disposiciones Generales"
    CAPITULO = "capitulo"        # Chapter - e.g., "Capítulo 1 - Objeto del Contrato"
    SECCION = "seccion"          # Section - e.g., "Sección 1.1 - Definiciones"
    SUBSECCION = "subseccion"    # Subsection - e.g., "1.1.1 - Términos Legales"
    CLAUSULA = "clausula"        # Clause - e.g., "Cláusula Primera"
    PARRAFO = "parrafo"          # Paragraph - text block
    LISTA = "lista"              # List item - bullet points, numbered items

    @classmethod
    def get_depth(cls, nivel: "NivelJerarquico") -> int:
        """Return the depth of a hierarchical level (0=highest)."""
        depths = {
            cls.DOCUMENTO: 0,
            cls.TITULO: 1,
            cls.CAPITULO: 2,
            cls.SECCION: 3,
            cls.SUBSECCION: 4,
            cls.CLAUSULA: 5,
            cls.PARRAFO: 6,
            cls.LISTA: 7,
        }
        return depths.get(nivel, 7)

    @classmethod
    def is_structural(cls, nivel: "NivelJerarquico") -> bool:
        """Check if level is structural (not content-level)."""
        return nivel in {cls.DOCUMENTO, cls.TITULO, cls.CAPITULO, cls.SECCION, cls.SUBSECCION}


@dataclass
class NodoEstructura:
    """
    A node in the document structure tree.

    Represents a structural element (chapter, section, paragraph, etc.)
    with its content, children, and generated summary.

    Attributes:
        id: Unique identifier for this node
        nivel: Hierarchical level (TITULO, CAPITULO, SECCION, etc.)
        titulo: Title/heading of this node (e.g., "Capítulo 1 - Objeto")
        contenido: Raw text content of this node (without children)
        hijos: Child nodes in the hierarchy
        resumen: Generated summary (populated bottom-up)
        char_start: Character offset where this node starts in original text
        char_end: Character offset where this node ends
        page_start: Page number where this node starts (if available)
        page_end: Page number where this node ends (if available)
        metadata: Additional node-specific metadata
    """
    id: str
    nivel: NivelJerarquico
    titulo: str
    contenido: str
    hijos: List["NodoEstructura"] = field(default_factory=list)
    resumen: Optional[str] = None
    char_start: int = 0
    char_end: int = 0
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def depth(self) -> int:
        """Return the hierarchical depth of this node."""
        return NivelJerarquico.get_depth(self.nivel)

    @property
    def is_leaf(self) -> bool:
        """Check if this node has no children (is a leaf node)."""
        return len(self.hijos) == 0

    @property
    def total_content_length(self) -> int:
        """Calculate total content length including children."""
        own_length = len(self.contenido)
        children_length = sum(hijo.total_content_length for hijo in self.hijos)
        return own_length + children_length

    @property
    def descendant_count(self) -> int:
        """Count total number of descendants."""
        count = len(self.hijos)
        for hijo in self.hijos:
            count += hijo.descendant_count
        return count

    def get_all_content(self) -> str:
        """
        Get all content from this node and its descendants.

        Returns concatenated content in document order.
        """
        parts = [self.contenido] if self.contenido else []
        for hijo in self.hijos:
            parts.append(hijo.get_all_content())
        return "\n\n".join(parts)

    def get_leaves(self) -> List["NodoEstructura"]:
        """Get all leaf nodes under this node."""
        if self.is_leaf:
            return [self]

        leaves = []
        for hijo in self.hijos:
            leaves.extend(hijo.get_leaves())
        return leaves

    def find_by_id(self, node_id: str) -> Optional["NodoEstructura"]:
        """Find a node by its ID in the subtree."""
        if self.id == node_id:
            return self

        for hijo in self.hijos:
            found = hijo.find_by_id(node_id)
            if found:
                return found
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert node to dictionary representation."""
        return {
            "id": self.id,
            "nivel": self.nivel.value,
            "titulo": self.titulo,
            "contenido_length": len(self.contenido),
            "resumen": self.resumen,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "hijos_count": len(self.hijos),
            "hijos": [hijo.to_dict() for hijo in self.hijos],
            "metadata": self.metadata,
        }


@dataclass
class ArbolDocumento:
    """
    Complete document structure tree.

    Contains the root node of the document hierarchy along with
    document-level metadata for processing and retrieval.

    Attributes:
        document_id: PostgreSQL document UUID
        tenant_id: Tenant identifier for multi-tenancy
        raiz: Root node (NivelJerarquico.DOCUMENTO)
        total_nodos: Total number of nodes in the tree
        profundidad_maxima: Maximum depth of the tree
        document_type: Detected document type (legal, markdown, numbered)
        parsing_time_ms: Time taken to parse the document
        created_at: When the tree was created
        metadata: Additional tree-level metadata
    """
    document_id: str
    tenant_id: str
    raiz: NodoEstructura
    total_nodos: int = 0
    profundidad_maxima: int = 0
    document_type: str = "general"
    parsing_time_ms: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Calculate tree statistics after initialization."""
        if self.total_nodos == 0:
            self.total_nodos = self._count_nodes(self.raiz)
        if self.profundidad_maxima == 0:
            self.profundidad_maxima = self._calculate_max_depth(self.raiz)

    def _count_nodes(self, node: NodoEstructura) -> int:
        """Count total nodes in subtree."""
        count = 1
        for hijo in node.hijos:
            count += self._count_nodes(hijo)
        return count

    def _calculate_max_depth(self, node: NodoEstructura, current_depth: int = 0) -> int:
        """Calculate maximum depth of subtree."""
        if node.is_leaf:
            return current_depth

        max_child_depth = current_depth
        for hijo in node.hijos:
            child_depth = self._calculate_max_depth(hijo, current_depth + 1)
            max_child_depth = max(max_child_depth, child_depth)
        return max_child_depth

    def get_nodes_at_level(self, nivel: NivelJerarquico) -> List[NodoEstructura]:
        """Get all nodes at a specific hierarchical level."""
        return self._collect_nodes_at_level(self.raiz, nivel)

    def _collect_nodes_at_level(
        self,
        node: NodoEstructura,
        target_nivel: NivelJerarquico
    ) -> List[NodoEstructura]:
        """Recursively collect nodes at target level."""
        nodes = []
        if node.nivel == target_nivel:
            nodes.append(node)

        for hijo in node.hijos:
            nodes.extend(self._collect_nodes_at_level(hijo, target_nivel))
        return nodes

    def get_all_leaves(self) -> List[NodoEstructura]:
        """Get all leaf nodes in the document."""
        return self.raiz.get_leaves()

    def get_summaries_for_level(self, nivel: NivelJerarquico) -> List[Dict[str, str]]:
        """
        Get all summaries for nodes at a specific level.

        Returns list of {id, titulo, resumen} dictionaries.
        """
        nodes = self.get_nodes_at_level(nivel)
        return [
            {
                "id": node.id,
                "titulo": node.titulo,
                "resumen": node.resumen or "",
            }
            for node in nodes
            if node.resumen
        ]

    def to_dict(self) -> Dict[str, Any]:
        """Convert tree to dictionary representation."""
        return {
            "document_id": self.document_id,
            "tenant_id": self.tenant_id,
            "total_nodos": self.total_nodos,
            "profundidad_maxima": self.profundidad_maxima,
            "document_type": self.document_type,
            "parsing_time_ms": self.parsing_time_ms,
            "created_at": self.created_at.isoformat(),
            "raiz": self.raiz.to_dict(),
            "metadata": self.metadata,
        }

    @classmethod
    def create_simple(
        cls,
        document_id: str,
        tenant_id: str,
        title: str,
        content: str,
    ) -> "ArbolDocumento":
        """
        Create a simple single-node tree for documents without structure.

        Used as fallback when structure parsing fails or for simple documents.
        """
        import uuid

        root = NodoEstructura(
            id=str(uuid.uuid4()),
            nivel=NivelJerarquico.DOCUMENTO,
            titulo=title,
            contenido=content,
            char_start=0,
            char_end=len(content),
        )

        return cls(
            document_id=document_id,
            tenant_id=tenant_id,
            raiz=root,
            document_type="simple",
        )
