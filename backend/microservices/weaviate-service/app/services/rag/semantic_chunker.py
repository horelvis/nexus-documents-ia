"""
Semantic Chunking for RAG Pipeline

Intelligent document chunking that:
- Detects document structure (headers, sections, clauses)
- Preserves semantic boundaries
- Handles different document types appropriately
- Creates chunks with overlap only when necessary

Key insight from production: "Context boundaries matter more than chunk size"
This improved retrieval accuracy by 34%.

Reference: "My production system crashed at 2 AM" - Layer 1: Intelligent Document Processing
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple, TYPE_CHECKING
from dataclasses import dataclass, field
from enum import Enum

if TYPE_CHECKING:
    from app.services.text_alignment_service import AlignedBlock

logger = logging.getLogger(__name__)


class DocumentType(str, Enum):
    """Document type classification for chunking strategy"""
    LEGAL_CONTRACT = "legal_contract"
    LEGAL_BRIEF = "legal_brief"
    TECHNICAL_MANUAL = "technical_manual"
    MEDICAL_RECORD = "medical_record"
    FINANCIAL_REPORT = "financial_report"
    GENERAL = "general"


@dataclass
class Section:
    """A detected section in a document"""
    title: str
    content: str
    level: int  # Header level (1-6)
    start_pos: int
    end_pos: int
    section_type: str = "body"  # header, clause, paragraph, list, etc.

    @property
    def length(self) -> int:
        return len(self.content)


@dataclass
class DocumentChunk:
    """A chunk ready for embedding"""
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    section_title: Optional[str] = None
    chunk_index: int = 0
    total_chunks: int = 1
    token_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "metadata": self.metadata,
            "section_title": self.section_title,
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "token_count": self.token_count,
        }


@dataclass
class PositionedChunk:
    """
    Chunk con información completa de posición para localización en PDF.

    Esta clase extiende DocumentChunk con:
    - Posiciones exactas en el texto completo (char_start, char_end)
    - Páginas de inicio y fin
    - Coordenadas bbox para anotaciones
    """
    content: str
    page_start: int               # 1-indexed
    page_end: int                 # 1-indexed
    char_start: int               # Posición inicio en texto completo
    char_end: int                 # Posición fin en texto completo
    bbox_start: Tuple[float, float, float, float] = (0, 0, 0, 0)  # x0, y0, x1, y1
    bbox_end: Tuple[float, float, float, float] = (0, 0, 0, 0)    # x0, y0, x1, y1
    metadata: Dict[str, Any] = field(default_factory=dict)
    section_title: Optional[str] = None
    chunk_index: int = 0
    total_chunks: int = 1
    token_count: int = 0
    confidence: float = 1.0       # Confianza del alineamiento

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "bbox_start_x0": self.bbox_start[0],
            "bbox_start_y0": self.bbox_start[1],
            "bbox_start_x1": self.bbox_start[2],
            "bbox_start_y1": self.bbox_start[3],
            "bbox_end_x0": self.bbox_end[0],
            "bbox_end_y0": self.bbox_end[1],
            "bbox_end_x1": self.bbox_end[2],
            "bbox_end_y1": self.bbox_end[3],
            "metadata": self.metadata,
            "section_title": self.section_title,
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "token_count": self.token_count,
            "confidence": self.confidence,
        }

    def to_weaviate_properties(self) -> Dict[str, Any]:
        """Propiedades para indexar en Weaviate."""
        return {
            "page_start": self.page_start,
            "page_end": self.page_end,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "bbox_start_x0": self.bbox_start[0],
            "bbox_start_y0": self.bbox_start[1],
            "bbox_start_x1": self.bbox_start[2],
            "bbox_start_y1": self.bbox_start[3],
            "bbox_end_x0": self.bbox_end[0],
            "bbox_end_y0": self.bbox_end[1],
            "bbox_end_x1": self.bbox_end[2],
            "bbox_end_y1": self.bbox_end[3],
        }


class SemanticChunker:
    """
    Intelligent document chunker that respects semantic boundaries.

    Different from naive chunking:
    - Legal briefs get chunked differently than technical manuals
    - Contracts preserve clause boundaries
    - Medical records maintain context across sections

    Configuration:
        chunk_size: Target chunk size in tokens (default: 512)
        max_chunk_size: Maximum chunk size (default: 1024)
        overlap: Overlap size for split sections (default: 100)
    """

    # Section detection patterns
    SECTION_PATTERNS = {
        # Markdown headers
        "markdown": r'^(#{1,6})\s+(.+)$',
        # Numbered sections (1., 1.1., 1.1.1., etc.)
        "numbered": r'^(\d+(?:\.\d+)*)\.\s+(.+)$',
        # Legal clauses (CLÁUSULA, ARTÍCULO, SECCIÓN)
        "legal_es": r'^(CL[ÁA]USULA|ART[ÍI]CULO|SECCI[ÓO]N)\s+(\w+)[:\.\s]',
        # Legal clauses (English)
        "legal_en": r'^(CLAUSE|ARTICLE|SECTION)\s+(\w+)[:\.\s]',
        # Roman numerals
        "roman": r'^([IVXLCDM]+)\.\s+(.+)$',
        # Lettered sections (A., B., etc.)
        "lettered": r'^([A-Z])\.\s+(.+)$',
    }

    # Paragraph break patterns
    PARAGRAPH_BREAK = r'\n{2,}'

    # Atomic section indicators (sections that shouldn't be split)
    ATOMIC_INDICATORS = [
        r'^\s*WHEREAS',
        r'^\s*NOW,?\s+THEREFORE',
        r'^\s*IN\s+WITNESS\s+WHEREOF',
        r'^\s*CONSIDERANDO',
        r'^\s*POR\s+TANTO',
        r'^\s*EN\s+FE\s+DE\s+LO\s+CUAL',
    ]

    def __init__(
        self,
        chunk_size: int = 512,
        max_chunk_size: int = 1024,
        overlap: int = 100,
    ):
        self.chunk_size = chunk_size
        self.max_chunk_size = max_chunk_size
        self.overlap = overlap

    def chunk_document(
        self,
        text: str,
        metadata: Dict[str, Any],
        document_type: Optional[DocumentType] = None,
    ) -> List[DocumentChunk]:
        """
        Chunk a document respecting semantic boundaries.

        Args:
            text: Full document text
            metadata: Document metadata to include in chunks
            document_type: Optional document type for strategy selection

        Returns:
            List of DocumentChunk ready for embedding
        """
        if not text or not text.strip():
            return []

        # Detect document type if not provided
        if document_type is None:
            document_type = self._detect_document_type(text)

        logger.debug(f"Chunking document type: {document_type}")

        # Step 1: Detect sections
        sections = self._detect_sections(text, document_type)
        logger.debug(f"Detected {len(sections)} sections")

        # Step 2: Process each section
        chunks: List[DocumentChunk] = []
        chunk_index = 0

        for section in sections:
            if self._is_atomic_section(section):
                # Keep atomic sections whole (even if large)
                chunk = DocumentChunk(
                    content=section.content.strip(),
                    metadata={**metadata, "section_type": section.section_type},
                    section_title=section.title,
                    chunk_index=chunk_index,
                    token_count=self._estimate_tokens(section.content),
                )
                chunks.append(chunk)
                chunk_index += 1
            elif section.length <= self.max_chunk_size * 4:  # Roughly token estimate
                # Small enough section, keep whole
                chunk = DocumentChunk(
                    content=section.content.strip(),
                    metadata={**metadata, "section_type": section.section_type},
                    section_title=section.title,
                    chunk_index=chunk_index,
                    token_count=self._estimate_tokens(section.content),
                )
                chunks.append(chunk)
                chunk_index += 1
            else:
                # Large section, split with overlap
                sub_chunks = self._split_with_overlap(
                    section.content,
                    section.title,
                    metadata,
                )
                for i, sub_chunk in enumerate(sub_chunks):
                    sub_chunk.chunk_index = chunk_index
                    sub_chunk.metadata["sub_chunk_index"] = i
                    sub_chunk.metadata["section_type"] = section.section_type
                    chunks.append(sub_chunk)
                    chunk_index += 1

        # Update total chunks count
        for chunk in chunks:
            chunk.total_chunks = len(chunks)

        logger.info(f"Created {len(chunks)} chunks from document")
        return chunks

    def _detect_document_type(self, text: str) -> DocumentType:
        """Detect document type from content"""
        text_lower = text.lower()

        # Legal contract indicators
        contract_patterns = [
            r'contrato\s+de', r'las\s+partes', r'cláusula',
            r'contract', r'agreement', r'parties', r'clause',
            r'whereas', r'hereinafter', r'witnesseth',
        ]
        if any(re.search(p, text_lower) for p in contract_patterns):
            return DocumentType.LEGAL_CONTRACT

        # Legal brief indicators
        brief_patterns = [
            r'tribunal', r'demanda', r'sentencia', r'recurso',
            r'court', r'plaintiff', r'defendant', r'motion',
        ]
        if any(re.search(p, text_lower) for p in brief_patterns):
            return DocumentType.LEGAL_BRIEF

        # Technical manual indicators
        tech_patterns = [
            r'installation', r'configuration', r'api\s+reference',
            r'instalación', r'configuración', r'manual\s+técnico',
        ]
        if any(re.search(p, text_lower) for p in tech_patterns):
            return DocumentType.TECHNICAL_MANUAL

        # Financial report indicators
        finance_patterns = [
            r'balance\s+sheet', r'income\s+statement', r'cash\s+flow',
            r'balance\s+general', r'estado\s+de\s+resultados',
        ]
        if any(re.search(p, text_lower) for p in finance_patterns):
            return DocumentType.FINANCIAL_REPORT

        return DocumentType.GENERAL

    def _detect_sections(
        self,
        text: str,
        document_type: DocumentType,
    ) -> List[Section]:
        """Detect sections in document based on structure"""
        sections: List[Section] = []

        # Choose patterns based on document type
        if document_type in [DocumentType.LEGAL_CONTRACT, DocumentType.LEGAL_BRIEF]:
            patterns = ['legal_es', 'legal_en', 'numbered', 'roman']
        elif document_type == DocumentType.TECHNICAL_MANUAL:
            patterns = ['markdown', 'numbered']
        else:
            patterns = ['markdown', 'numbered', 'lettered']

        # Find all section headers
        section_markers: List[Tuple[int, str, int]] = []  # (position, title, level)

        for pattern_name in patterns:
            pattern = self.SECTION_PATTERNS.get(pattern_name)
            if not pattern:
                continue

            for match in re.finditer(pattern, text, re.MULTILINE | re.IGNORECASE):
                pos = match.start()
                title = match.group(0).strip()
                # Determine level from pattern type
                level = self._get_level_from_match(pattern_name, match)
                section_markers.append((pos, title, level))

        # Sort by position
        section_markers.sort(key=lambda x: x[0])

        # If no sections found, treat paragraphs as sections
        if not section_markers:
            return self._split_by_paragraphs(text)

        # Create sections from markers
        for i, (pos, title, level) in enumerate(section_markers):
            # End position is start of next section or end of text
            if i + 1 < len(section_markers):
                end_pos = section_markers[i + 1][0]
            else:
                end_pos = len(text)

            content = text[pos:end_pos].strip()

            sections.append(Section(
                title=title,
                content=content,
                level=level,
                start_pos=pos,
                end_pos=end_pos,
                section_type="header",
            ))

        # Handle text before first section
        if section_markers and section_markers[0][0] > 0:
            preamble = text[:section_markers[0][0]].strip()
            if preamble:
                sections.insert(0, Section(
                    title="Preamble",
                    content=preamble,
                    level=0,
                    start_pos=0,
                    end_pos=section_markers[0][0],
                    section_type="preamble",
                ))

        return sections

    def _split_by_paragraphs(self, text: str) -> List[Section]:
        """Split text by paragraphs when no sections detected"""
        paragraphs = re.split(self.PARAGRAPH_BREAK, text)
        sections = []
        pos = 0

        for i, para in enumerate(paragraphs):
            para = para.strip()
            if para:
                sections.append(Section(
                    title=f"Paragraph {i + 1}",
                    content=para,
                    level=1,
                    start_pos=pos,
                    end_pos=pos + len(para),
                    section_type="paragraph",
                ))
            pos += len(para) + 2  # Account for \n\n

        return sections

    def _get_level_from_match(self, pattern_name: str, match: re.Match) -> int:
        """Determine section level from pattern match"""
        if pattern_name == "markdown":
            # Count # symbols
            return len(match.group(1))
        elif pattern_name == "numbered":
            # Count dots in number
            return match.group(1).count('.') + 1
        elif pattern_name in ["legal_es", "legal_en"]:
            return 1
        elif pattern_name == "roman":
            return 2
        elif pattern_name == "lettered":
            return 3
        return 1

    def _is_atomic_section(self, section: Section) -> bool:
        """Check if section should be kept whole (not split)"""
        # Check against atomic indicators
        for pattern in self.ATOMIC_INDICATORS:
            if re.search(pattern, section.content, re.IGNORECASE):
                return True

        # Short sections are atomic
        if section.length < self.chunk_size * 2:
            return True

        # Signature blocks are atomic
        if section.section_type == "signature" or "firma" in section.title.lower():
            return True

        return False

    def _split_with_overlap(
        self,
        text: str,
        section_title: str,
        metadata: Dict[str, Any],
    ) -> List[DocumentChunk]:
        """Split large section into chunks with overlap"""
        chunks = []

        # Try to split at sentence boundaries first
        sentences = self._split_into_sentences(text)

        current_chunk = ""
        current_tokens = 0

        for sentence in sentences:
            sentence_tokens = self._estimate_tokens(sentence)

            if current_tokens + sentence_tokens <= self.chunk_size:
                current_chunk += sentence + " "
                current_tokens += sentence_tokens
            else:
                # Save current chunk
                if current_chunk.strip():
                    chunks.append(DocumentChunk(
                        content=current_chunk.strip(),
                        metadata=metadata,
                        section_title=section_title,
                        token_count=current_tokens,
                    ))

                # Start new chunk with overlap
                overlap_text = self._get_overlap_text(current_chunk, self.overlap)
                current_chunk = overlap_text + sentence + " "
                current_tokens = self._estimate_tokens(current_chunk)

        # Don't forget last chunk
        if current_chunk.strip():
            chunks.append(DocumentChunk(
                content=current_chunk.strip(),
                metadata=metadata,
                section_title=section_title,
                token_count=self._estimate_tokens(current_chunk),
            ))

        return chunks

    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences"""
        # Simple sentence splitting (could be improved with NLP)
        sentence_endings = r'(?<=[.!?])\s+'
        sentences = re.split(sentence_endings, text)
        return [s.strip() for s in sentences if s.strip()]

    def _get_overlap_text(self, text: str, target_tokens: int) -> str:
        """Get overlap text from end of chunk"""
        words = text.split()
        # Rough estimation: 1 word ≈ 1.3 tokens
        target_words = int(target_tokens / 1.3)

        if len(words) <= target_words:
            return text

        overlap_words = words[-target_words:]
        return " ".join(overlap_words) + " "

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation (1 word ≈ 1.3 tokens)"""
        if not text:
            return 0
        return int(len(text.split()) * 1.3)

    def chunk_document_with_positions(
        self,
        aligned_blocks: List["AlignedBlock"],
        metadata: Dict[str, Any],
        document_type: Optional[DocumentType] = None,
    ) -> List[PositionedChunk]:
        """
        Chunk documento usando bloques alineados con posiciones.

        A diferencia de chunk_document(), este método:
        - Preserva información de página y coordenadas
        - Agrupa bloques adyacentes respetando tamaño de chunk
        - Mantiene trazabilidad completa para anotaciones PDF

        Args:
            aligned_blocks: Lista de AlignedBlock del TextAlignmentService
            metadata: Metadatos del documento
            document_type: Tipo de documento para estrategia de chunking

        Returns:
            Lista de PositionedChunk con coordenadas
        """
        if not aligned_blocks:
            return []

        # Combinar texto para detectar tipo
        full_text = " ".join(b.text for b in aligned_blocks)

        if document_type is None:
            document_type = self._detect_document_type(full_text)

        logger.debug(f"Chunking con posiciones, tipo: {document_type}")

        chunks: List[PositionedChunk] = []
        current_blocks: List["AlignedBlock"] = []
        current_tokens = 0

        for block in aligned_blocks:
            block_tokens = self._estimate_tokens(block.text)

            # Si añadir este bloque excede el tamaño, guardar chunk actual
            if current_blocks and current_tokens + block_tokens > self.chunk_size:
                chunk = self._create_positioned_chunk(
                    current_blocks, metadata, len(chunks)
                )
                chunks.append(chunk)

                # Iniciar nuevo chunk con overlap de bloques
                overlap_blocks = self._get_overlap_blocks(current_blocks)
                current_blocks = overlap_blocks + [block]
                current_tokens = sum(self._estimate_tokens(b.text) for b in current_blocks)
            else:
                current_blocks.append(block)
                current_tokens += block_tokens

        # No olvidar el último chunk
        if current_blocks:
            chunk = self._create_positioned_chunk(
                current_blocks, metadata, len(chunks)
            )
            chunks.append(chunk)

        # Actualizar total_chunks
        for i, chunk in enumerate(chunks):
            chunk.total_chunks = len(chunks)

        logger.info(
            f"Creados {len(chunks)} chunks posicionados de {len(aligned_blocks)} bloques"
        )
        return chunks

    def _create_positioned_chunk(
        self,
        blocks: List["AlignedBlock"],
        metadata: Dict[str, Any],
        chunk_index: int,
    ) -> PositionedChunk:
        """Crea un PositionedChunk desde una lista de bloques."""
        if not blocks:
            return PositionedChunk(
                content="",
                page_start=1,
                page_end=1,
                char_start=0,
                char_end=0,
                metadata=metadata,
                chunk_index=chunk_index,
            )

        # Combinar textos
        content = " ".join(b.text for b in blocks)

        # Calcular posiciones extremas
        first_block = blocks[0]
        last_block = blocks[-1]

        # Calcular confianza promedio
        avg_confidence = sum(b.confidence for b in blocks) / len(blocks)

        return PositionedChunk(
            content=content,
            page_start=first_block.page_number,
            page_end=last_block.page_number,
            char_start=first_block.char_start,
            char_end=last_block.char_end,
            bbox_start=first_block.bbox,
            bbox_end=last_block.bbox,
            metadata=metadata,
            section_title=None,  # Se podría detectar de los bloques
            chunk_index=chunk_index,
            token_count=self._estimate_tokens(content),
            confidence=avg_confidence,
        )

    def _get_overlap_blocks(
        self,
        blocks: List["AlignedBlock"],
    ) -> List["AlignedBlock"]:
        """
        Obtiene bloques de overlap para el siguiente chunk.

        Incluye los últimos N bloques que sumen aproximadamente
        `self.overlap` tokens.
        """
        if not blocks:
            return []

        overlap_blocks = []
        overlap_tokens = 0

        # Iterar desde el final
        for block in reversed(blocks):
            block_tokens = self._estimate_tokens(block.text)
            if overlap_tokens + block_tokens <= self.overlap * 1.5:
                overlap_blocks.insert(0, block)
                overlap_tokens += block_tokens
            else:
                break

            # Máximo 2 bloques de overlap
            if len(overlap_blocks) >= 2:
                break

        return overlap_blocks


# Global instance with default settings
semantic_chunker = SemanticChunker(
    chunk_size=512,
    max_chunk_size=1024,
    overlap=100,
)
