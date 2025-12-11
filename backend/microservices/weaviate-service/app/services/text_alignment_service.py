"""
Text Alignment Service

Reconcilia el texto extraído por Apache Tika (alta calidad) con las
coordenadas de PyMuPDF para crear bloques alineados con posiciones exactas.

El problema:
- Tika extrae texto de alta calidad (mejor OCR, manejo de tablas, columnas)
- PyMuPDF extrae bloques con coordenadas (bbox) precisas
- El texto puede diferir ligeramente entre ambos

La solución:
1. Extraer bloques de PyMuPDF con sus bboxes
2. Usar "anclas" (frases únicas) para alinear con texto Tika
3. Interpolar posiciones entre anclas
4. Resultado: AlignedBlocks con texto Tika + coords PyMuPDF
"""
import fitz  # PyMuPDF
import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from difflib import SequenceMatcher
import hashlib

logger = logging.getLogger(__name__)


@dataclass
class AlignedBlock:
    """Bloque de texto alineado con coordenadas."""
    text: str                    # Texto (de Tika o PyMuPDF)
    page_number: int             # 1-indexed
    bbox: Tuple[float, float, float, float]  # x0, y0, x1, y1 de PyMuPDF
    char_start: int              # Posición inicio en texto completo
    char_end: int                # Posición fin en texto completo
    confidence: float = 1.0      # Confianza del alineamiento (1.0 = exacto)
    block_id: str = ""           # ID único del bloque


@dataclass
class PyMuPDFBlock:
    """Bloque extraído de PyMuPDF."""
    text: str
    page_number: int  # 1-indexed
    bbox: Tuple[float, float, float, float]
    block_index: int


@dataclass
class AlignmentResult:
    """Resultado completo del alineamiento."""
    aligned_blocks: List[AlignedBlock]
    full_text: str                # Texto completo (Tika o concatenado)
    total_pages: int
    total_chars: int
    alignment_quality: float      # 0-1, indica qué tan bien se alinearon
    warnings: List[str] = field(default_factory=list)


class TextAlignmentService:
    """
    Servicio para alinear texto de Tika con coordenadas de PyMuPDF.

    Estrategias de alineamiento:
    1. Anclas exactas: Frases únicas que aparecen en ambos textos
    2. Alineamiento fuzzy: Para bloques sin ancla exacta
    3. Interpolación: Estimar posiciones entre anclas conocidas
    """

    # Configuración
    ANCHOR_MIN_LENGTH = 20        # Longitud mínima de ancla
    ANCHOR_MAX_LENGTH = 100       # Longitud máxima de ancla
    FUZZY_THRESHOLD = 0.85        # Umbral para matching fuzzy
    MAX_ANCHORS_PER_PAGE = 5      # Máximo de anclas por página

    def align_text_with_coordinates(
        self,
        pdf_bytes: bytes,
        tika_text: Optional[str] = None,
        use_tika_text: bool = True,
    ) -> AlignmentResult:
        """
        Alinea el texto con coordenadas del PDF.

        Args:
            pdf_bytes: PDF en bytes
            tika_text: Texto extraído por Tika (opcional)
            use_tika_text: Si usar texto Tika como fuente primaria

        Returns:
            AlignmentResult con bloques alineados
        """
        # 1. Extraer bloques de PyMuPDF con coordenadas
        pymupdf_blocks = self._extract_pymupdf_blocks(pdf_bytes)

        if not pymupdf_blocks:
            logger.warning("No se extrajeron bloques de PyMuPDF")
            return AlignmentResult(
                aligned_blocks=[],
                full_text=tika_text or "",
                total_pages=0,
                total_chars=0,
                alignment_quality=0.0,
                warnings=["No se pudieron extraer bloques del PDF"]
            )

        # 2. Si no hay texto Tika, usar PyMuPDF directamente
        if not tika_text or not use_tika_text:
            return self._create_aligned_from_pymupdf(pymupdf_blocks)

        # 3. Alinear texto Tika con bloques PyMuPDF
        return self._align_tika_with_pymupdf(tika_text, pymupdf_blocks)

    def _extract_pymupdf_blocks(self, pdf_bytes: bytes) -> List[PyMuPDFBlock]:
        """Extrae bloques de texto con coordenadas usando PyMuPDF."""
        blocks = []

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            logger.error(f"Error abriendo PDF: {e}")
            return []

        block_index = 0

        for page_num in range(len(doc)):
            page = doc[page_num]
            page_number = page_num + 1  # 1-indexed

            try:
                text_dict = page.get_text("dict")

                for block in text_dict.get("blocks", []):
                    if block.get("type") != 0:  # Solo bloques de texto
                        continue

                    block_text_parts = []
                    block_bbox = block.get("bbox", (0, 0, 0, 0))

                    for line in block.get("lines", []):
                        line_text = ""
                        for span in line.get("spans", []):
                            line_text += span.get("text", "")
                        if line_text.strip():
                            block_text_parts.append(line_text)

                    if block_text_parts:
                        block_text = " ".join(block_text_parts)
                        block_text = self._normalize_text(block_text)

                        if block_text:
                            blocks.append(PyMuPDFBlock(
                                text=block_text,
                                page_number=page_number,
                                bbox=tuple(block_bbox),
                                block_index=block_index,
                            ))
                            block_index += 1

            except Exception as e:
                logger.warning(f"Error extrayendo página {page_number}: {e}")

        doc.close()
        logger.info(f"Extraídos {len(blocks)} bloques de PyMuPDF")
        return blocks

    def _create_aligned_from_pymupdf(
        self,
        pymupdf_blocks: List[PyMuPDFBlock]
    ) -> AlignmentResult:
        """Crea resultado de alineamiento solo con bloques PyMuPDF."""
        aligned_blocks = []
        full_text_parts = []
        char_position = 0
        max_page = 0

        for block in pymupdf_blocks:
            block_text = block.text
            char_start = char_position
            char_end = char_position + len(block_text)

            aligned = AlignedBlock(
                text=block_text,
                page_number=block.page_number,
                bbox=block.bbox,
                char_start=char_start,
                char_end=char_end,
                confidence=1.0,
                block_id=self._generate_block_id(block_text, block.page_number),
            )
            aligned_blocks.append(aligned)

            full_text_parts.append(block_text)
            char_position = char_end + 1  # +1 para separador
            max_page = max(max_page, block.page_number)

        full_text = "\n".join(full_text_parts)

        return AlignmentResult(
            aligned_blocks=aligned_blocks,
            full_text=full_text,
            total_pages=max_page,
            total_chars=len(full_text),
            alignment_quality=1.0,
        )

    def _align_tika_with_pymupdf(
        self,
        tika_text: str,
        pymupdf_blocks: List[PyMuPDFBlock]
    ) -> AlignmentResult:
        """
        Alinea texto de Tika con bloques PyMuPDF usando anclas.

        Proceso:
        1. Encontrar anclas (frases únicas en ambos textos)
        2. Para cada bloque PyMuPDF, buscar su posición en texto Tika
        3. Crear AlignedBlocks con texto y coordenadas
        """
        tika_text_normalized = self._normalize_text(tika_text)
        tika_lower = tika_text_normalized.lower()

        aligned_blocks = []
        warnings = []
        successful_alignments = 0
        total_blocks = len(pymupdf_blocks)

        # Procesar bloques y encontrar posiciones en texto Tika
        char_position = 0

        for block in pymupdf_blocks:
            block_text = block.text
            block_lower = block_text.lower()

            # Estrategia 1: Búsqueda exacta
            position = self._find_exact_position(block_lower, tika_lower, char_position)
            confidence = 1.0

            if position is None:
                # Estrategia 2: Búsqueda fuzzy con fragmentos
                position, confidence = self._find_fuzzy_position(
                    block_lower, tika_lower, char_position
                )

            if position is not None:
                # Usar el texto del bloque (o del Tika si es diferente)
                text_to_use = block_text
                char_start = position
                char_end = position + len(block_text)

                aligned = AlignedBlock(
                    text=text_to_use,
                    page_number=block.page_number,
                    bbox=block.bbox,
                    char_start=char_start,
                    char_end=char_end,
                    confidence=confidence,
                    block_id=self._generate_block_id(text_to_use, block.page_number),
                )
                aligned_blocks.append(aligned)

                # Avanzar posición para siguiente búsqueda
                char_position = char_end
                successful_alignments += 1
            else:
                # No se pudo alinear - usar estimación basada en posición
                estimated_pos = char_position

                aligned = AlignedBlock(
                    text=block_text,
                    page_number=block.page_number,
                    bbox=block.bbox,
                    char_start=estimated_pos,
                    char_end=estimated_pos + len(block_text),
                    confidence=0.3,  # Baja confianza
                    block_id=self._generate_block_id(block_text, block.page_number),
                )
                aligned_blocks.append(aligned)

                char_position = estimated_pos + len(block_text) + 1
                warnings.append(
                    f"Bloque en página {block.page_number} no alineado exactamente"
                )

        # Calcular calidad del alineamiento
        alignment_quality = successful_alignments / total_blocks if total_blocks > 0 else 0.0

        # Determinar número total de páginas
        max_page = max((b.page_number for b in aligned_blocks), default=0)

        logger.info(
            f"Alineamiento completado: {successful_alignments}/{total_blocks} bloques "
            f"({alignment_quality:.1%} calidad)"
        )

        return AlignmentResult(
            aligned_blocks=aligned_blocks,
            full_text=tika_text,
            total_pages=max_page,
            total_chars=len(tika_text),
            alignment_quality=alignment_quality,
            warnings=warnings,
        )

    def _find_exact_position(
        self,
        search_text: str,
        full_text: str,
        start_from: int = 0
    ) -> Optional[int]:
        """Busca posición exacta del texto."""
        # Buscar desde la posición actual
        position = full_text.find(search_text, start_from)
        if position >= 0:
            return position

        # Si no se encuentra, probar con fragmentos iniciales
        words = search_text.split()
        for word_count in [20, 15, 10, 7, 5]:
            if len(words) >= word_count:
                fragment = " ".join(words[:word_count])
                position = full_text.find(fragment, start_from)
                if position >= 0:
                    return position

        return None

    def _find_fuzzy_position(
        self,
        search_text: str,
        full_text: str,
        start_from: int = 0
    ) -> Tuple[Optional[int], float]:
        """
        Busca posición usando matching fuzzy.

        Returns:
            Tupla (posición, confianza) o (None, 0.0)
        """
        if len(search_text) < 20:
            return None, 0.0

        # Tomar fragmento inicial del texto a buscar
        search_fragment = search_text[:min(100, len(search_text))]

        best_position = None
        best_ratio = 0.0

        # Buscar en ventanas deslizantes
        window_size = len(search_fragment)
        search_area = full_text[start_from:start_from + 5000]  # Limitar área de búsqueda

        for i in range(0, max(1, len(search_area) - window_size), 20):
            window = search_area[i:i + window_size + 20]
            ratio = SequenceMatcher(None, search_fragment, window).ratio()

            if ratio > best_ratio and ratio >= self.FUZZY_THRESHOLD:
                best_ratio = ratio
                best_position = start_from + i

        if best_position is not None:
            return best_position, best_ratio

        return None, 0.0

    def _normalize_text(self, text: str) -> str:
        """Normaliza texto para comparación."""
        if not text:
            return ""
        # Normalizar espacios
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _generate_block_id(self, text: str, page_number: int) -> str:
        """Genera ID único para un bloque."""
        content = f"{page_number}:{text[:50]}"
        return hashlib.md5(content.encode()).hexdigest()[:12]

    def find_text_in_aligned_blocks(
        self,
        search_text: str,
        aligned_blocks: List[AlignedBlock],
        max_block_span: int = 3,
    ) -> Optional[Tuple[AlignedBlock, AlignedBlock, float]]:
        """
        Busca texto en bloques alineados, permitiendo cruzar bloques.

        Args:
            search_text: Texto a buscar
            aligned_blocks: Lista de bloques alineados
            max_block_span: Máximo de bloques contiguos a unir

        Returns:
            Tupla (bloque_inicio, bloque_fin, confianza) o None
        """
        search_lower = search_text.lower().strip()
        search_normalized = self._normalize_text(search_lower)

        if len(search_normalized) < 5:
            return None

        # Ordenar bloques por posición
        sorted_blocks = sorted(aligned_blocks, key=lambda b: b.char_start)

        # 1. Búsqueda en bloques individuales
        for block in sorted_blocks:
            block_lower = block.text.lower()
            if search_normalized in block_lower:
                return (block, block, 1.0)

        # 2. Búsqueda en bloques unidos (cross-block)
        for span in range(2, max_block_span + 1):
            for i in range(len(sorted_blocks) - span + 1):
                # Unir bloques contiguos
                combined_blocks = sorted_blocks[i:i + span]

                # Verificar que son de páginas cercanas
                page_diff = combined_blocks[-1].page_number - combined_blocks[0].page_number
                if page_diff > 1:
                    continue  # Saltar si están muy separados

                combined_text = " ".join(b.text for b in combined_blocks).lower()
                combined_normalized = self._normalize_text(combined_text)

                if search_normalized in combined_normalized:
                    return (
                        combined_blocks[0],
                        combined_blocks[-1],
                        0.9 - (span - 2) * 0.1  # Menor confianza para más bloques
                    )

        # 3. Búsqueda fuzzy en bloques individuales
        for block in sorted_blocks:
            block_lower = block.text.lower()
            ratio = SequenceMatcher(None, search_normalized, block_lower).ratio()
            if ratio >= 0.75:
                return (block, block, ratio)

        return None

    def get_bbox_for_text_range(
        self,
        start_block: AlignedBlock,
        end_block: AlignedBlock,
    ) -> Tuple[float, float, float, float]:
        """
        Combina bboxes de múltiples bloques.

        Returns:
            Bbox combinado (x0, y0, x1, y1)
        """
        if start_block == end_block:
            return start_block.bbox

        # Combinar bboxes
        x0 = min(start_block.bbox[0], end_block.bbox[0])
        y0 = min(start_block.bbox[1], end_block.bbox[1])
        x1 = max(start_block.bbox[2], end_block.bbox[2])
        y1 = max(start_block.bbox[3], end_block.bbox[3])

        return (x0, y0, x1, y1)


# Singleton
text_alignment_service = TextAlignmentService()
