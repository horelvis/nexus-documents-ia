"""
Document Text Service

Extrae texto de PDFs con información de posición para facilitar
la localización de citas en el documento original.

Características:
- Extracción página por página con marcadores [PÁGINA N]
- Chunks con coordenadas (página, bbox) para mapeo directo
- Índice de palabras para búsqueda rápida
- Soporte para búsqueda fuzzy
"""
import fitz  # PyMuPDF
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
import logging
import re
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


@dataclass
class TextBlock:
    """Bloque de texto con información de posición."""
    text: str
    page_number: int  # 1-indexed
    bbox: Tuple[float, float, float, float]  # x0, y0, x1, y1
    block_index: int
    char_start: int  # Posición de inicio en el texto completo
    char_end: int    # Posición de fin en el texto completo


@dataclass
class PageContent:
    """Contenido de una página con sus bloques."""
    page_number: int  # 1-indexed
    text: str
    blocks: List[TextBlock]
    width: float
    height: float


@dataclass
class DocumentContent:
    """Contenido completo del documento con índices."""
    full_text: str                    # Texto completo con marcadores de página
    full_text_raw: str                # Texto sin marcadores
    pages: List[PageContent]
    total_pages: int
    total_chars: int
    word_index: Dict[str, List[int]]  # palabra -> [posiciones en char]


@dataclass
class TextMatch:
    """Resultado de búsqueda de texto."""
    text: str
    page_number: int
    bbox: Tuple[float, float, float, float]
    confidence: float
    match_type: str  # "exact", "fuzzy", "fragment", "keyword"
    char_position: int


class DocumentTextService:
    """
    Servicio para extraer y buscar texto en documentos PDF.

    Proporciona:
    1. Extracción con marcadores de página para contexto del LLM
    2. Índice de posiciones para búsqueda rápida
    3. Búsqueda fuzzy para quotes aproximados
    """

    # Umbral mínimo de similitud para búsqueda fuzzy
    FUZZY_THRESHOLD = 0.75

    # Longitud mínima para búsqueda fuzzy (evitar falsos positivos)
    MIN_FUZZY_LENGTH = 20

    def extract_document_content(
        self,
        pdf_bytes: bytes,
        include_page_markers: bool = True,
        max_chars: int = 0,  # 0 = sin límite
    ) -> DocumentContent:
        """
        Extrae todo el contenido del PDF con información de posición.

        Args:
            pdf_bytes: PDF en bytes
            include_page_markers: Si incluir [PÁGINA N] en el texto
            max_chars: Límite de caracteres (0 = sin límite)

        Returns:
            DocumentContent con texto, páginas y índices
        """
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            logger.error(f"Error abriendo PDF: {e}")
            return DocumentContent(
                full_text="",
                full_text_raw="",
                pages=[],
                total_pages=0,
                total_chars=0,
                word_index={},
            )

        pages = []
        full_text_parts = []
        full_text_raw_parts = []
        char_position = 0
        word_index: Dict[str, List[int]] = {}
        block_counter = 0

        for page_num in range(len(doc)):
            page = doc[page_num]
            page_number = page_num + 1  # 1-indexed

            # Añadir marcador de página
            if include_page_markers:
                marker = f"\n[PÁGINA {page_number}]\n"
                full_text_parts.append(marker)
                char_position += len(marker)

            # Extraer bloques de texto con posiciones
            blocks = []
            page_text_parts = []

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
                        block_text = self._clean_text(block_text)

                        if block_text:
                            char_start = char_position
                            char_end = char_position + len(block_text)

                            text_block = TextBlock(
                                text=block_text,
                                page_number=page_number,
                                bbox=block_bbox,
                                block_index=block_counter,
                                char_start=char_start,
                                char_end=char_end,
                            )
                            blocks.append(text_block)
                            block_counter += 1

                            page_text_parts.append(block_text)
                            full_text_parts.append(block_text + "\n")
                            full_text_raw_parts.append(block_text + "\n")

                            # Indexar palabras
                            self._index_words(block_text, char_position, word_index)

                            char_position += len(block_text) + 1  # +1 por \n

            except Exception as e:
                logger.warning(f"Error extrayendo texto de página {page_number}: {e}")
                # Fallback a extracción simple
                simple_text = page.get_text()
                if simple_text:
                    page_text_parts.append(simple_text)
                    full_text_parts.append(simple_text)
                    full_text_raw_parts.append(simple_text)

            page_content = PageContent(
                page_number=page_number,
                text="\n".join(page_text_parts),
                blocks=blocks,
                width=page.rect.width,
                height=page.rect.height,
            )
            pages.append(page_content)

            # Verificar límite de caracteres
            if max_chars > 0 and char_position >= max_chars:
                logger.info(f"Truncando documento en página {page_number} ({char_position} chars)")
                break

        doc.close()

        full_text = "".join(full_text_parts)
        full_text_raw = "".join(full_text_raw_parts)

        # Truncar si es necesario
        if max_chars > 0 and len(full_text) > max_chars:
            full_text = full_text[:max_chars] + "\n[... DOCUMENTO TRUNCADO ...]"

        logger.info(
            f"Documento extraído: {len(pages)} páginas, "
            f"{len(full_text)} caracteres, {len(word_index)} palabras únicas"
        )

        return DocumentContent(
            full_text=full_text,
            full_text_raw=full_text_raw,
            pages=pages,
            total_pages=len(pages),
            total_chars=len(full_text_raw),
            word_index=word_index,
        )

    def find_text_position(
        self,
        document: DocumentContent,
        search_text: str,
        use_fuzzy: bool = True,
    ) -> Optional[TextMatch]:
        """
        Busca texto en el documento y devuelve su posición.

        Estrategias de búsqueda (en orden):
        1. Búsqueda exacta
        2. Búsqueda de fragmento inicial
        3. Búsqueda fuzzy (Levenshtein)
        4. Búsqueda por palabras clave

        Args:
            document: Documento extraído
            search_text: Texto a buscar
            use_fuzzy: Si usar búsqueda fuzzy

        Returns:
            TextMatch con posición o None si no se encuentra
        """
        search_text = self._clean_text(search_text)

        if len(search_text) < 5:
            return None

        # 1. Búsqueda exacta
        match = self._search_exact(document, search_text)
        if match:
            return match

        # 2. Búsqueda de fragmento (primeras N palabras)
        match = self._search_fragment(document, search_text)
        if match:
            return match

        # 3. Búsqueda fuzzy
        if use_fuzzy and len(search_text) >= self.MIN_FUZZY_LENGTH:
            match = self._search_fuzzy(document, search_text)
            if match:
                return match

        # 4. Búsqueda por palabras clave
        match = self._search_keywords(document, search_text)
        if match:
            return match

        return None

    def find_text_in_pdf(
        self,
        pdf_bytes: bytes,
        search_text: str,
        use_fuzzy: bool = True,
    ) -> Optional[TextMatch]:
        """
        Conveniencia: extrae documento y busca texto en un paso.
        """
        document = self.extract_document_content(pdf_bytes)
        return self.find_text_position(document, search_text, use_fuzzy)

    def _clean_text(self, text: str) -> str:
        """Limpia y normaliza texto para búsqueda."""
        if not text:
            return ""
        # Normalizar espacios
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _index_words(
        self,
        text: str,
        char_offset: int,
        word_index: Dict[str, List[int]]
    ):
        """Añade palabras al índice con sus posiciones."""
        words = re.findall(r'\b\w+\b', text.lower())
        current_pos = 0

        for word in words:
            if len(word) >= 3:  # Solo palabras de 3+ caracteres
                pos_in_text = text.lower().find(word, current_pos)
                if pos_in_text >= 0:
                    absolute_pos = char_offset + pos_in_text
                    if word not in word_index:
                        word_index[word] = []
                    word_index[word].append(absolute_pos)
                    current_pos = pos_in_text + len(word)

    def _search_exact(
        self,
        document: DocumentContent,
        search_text: str
    ) -> Optional[TextMatch]:
        """Búsqueda exacta de texto."""
        search_lower = search_text.lower()

        for page in document.pages:
            for block in page.blocks:
                if search_lower in block.text.lower():
                    return TextMatch(
                        text=search_text,
                        page_number=block.page_number,
                        bbox=block.bbox,
                        confidence=1.0,
                        match_type="exact",
                        char_position=block.char_start,
                    )
        return None

    def _search_fragment(
        self,
        document: DocumentContent,
        search_text: str
    ) -> Optional[TextMatch]:
        """Busca fragmentos iniciales del texto."""
        words = search_text.split()

        # Probar con diferentes longitudes de fragmento
        for word_count in [15, 10, 7, 5]:
            if len(words) >= word_count:
                fragment = " ".join(words[:word_count])
                match = self._search_exact(document, fragment)
                if match:
                    match.match_type = "fragment"
                    match.confidence = 0.8 - (0.05 * (15 - word_count))
                    return match

        return None

    def _search_fuzzy(
        self,
        document: DocumentContent,
        search_text: str
    ) -> Optional[TextMatch]:
        """Búsqueda fuzzy usando similitud de secuencia."""
        search_lower = search_text.lower()
        best_match = None
        best_ratio = 0.0

        for page in document.pages:
            for block in page.blocks:
                block_lower = block.text.lower()

                # Buscar en ventanas deslizantes del tamaño del texto buscado
                window_size = len(search_text)

                for i in range(0, max(1, len(block_lower) - window_size + 1), 10):
                    window = block_lower[i:i + window_size + 20]
                    ratio = SequenceMatcher(None, search_lower, window).ratio()

                    if ratio > best_ratio and ratio >= self.FUZZY_THRESHOLD:
                        best_ratio = ratio
                        best_match = TextMatch(
                            text=block.text[i:i + window_size],
                            page_number=block.page_number,
                            bbox=block.bbox,
                            confidence=ratio,
                            match_type="fuzzy",
                            char_position=block.char_start + i,
                        )

        return best_match

    def _search_keywords(
        self,
        document: DocumentContent,
        search_text: str
    ) -> Optional[TextMatch]:
        """Busca palabras clave largas del texto."""
        words = search_text.split()
        # Filtrar palabras largas y únicas
        keywords = [w.lower() for w in words if len(w) > 6][:5]

        if not keywords:
            return None

        # Buscar palabra por palabra
        for keyword in keywords:
            if keyword in document.word_index:
                positions = document.word_index[keyword]
                if positions:
                    # Encontrar el bloque que contiene esta posición
                    char_pos = positions[0]
                    for page in document.pages:
                        for block in page.blocks:
                            if block.char_start <= char_pos <= block.char_end:
                                return TextMatch(
                                    text=keyword,
                                    page_number=block.page_number,
                                    bbox=block.bbox,
                                    confidence=0.5,
                                    match_type="keyword",
                                    char_position=char_pos,
                                )

        return None

    def get_text_with_context(
        self,
        document: DocumentContent,
        char_position: int,
        context_chars: int = 100
    ) -> str:
        """
        Obtiene texto alrededor de una posición con contexto.

        Útil para debug y para mostrar al usuario.
        """
        start = max(0, char_position - context_chars)
        end = min(len(document.full_text_raw), char_position + context_chars)

        text = document.full_text_raw[start:end]
        return f"...{text}..."

    def find_text_position_cross_block(
        self,
        document: DocumentContent,
        search_text: str,
        max_block_span: int = 3,
        page_hint: Optional[int] = None,
    ) -> Optional[TextMatch]:
        """
        Busca texto que puede cruzar múltiples bloques o páginas.

        Esta función es especialmente útil para citas que atraviesan
        límites de párrafos o columnas en documentos PDF complejos.

        Args:
            document: Documento extraído con bloques
            search_text: Texto a buscar (puede ser largo)
            max_block_span: Máximo de bloques contiguos a unir para búsqueda
            page_hint: Página sugerida donde buscar primero (1-indexed)

        Returns:
            TextMatch con información de posición combinada o None
        """
        search_text = self._clean_text(search_text)

        if len(search_text) < 5:
            return None

        # Recolectar todos los bloques ordenados por posición
        all_blocks: List[TextBlock] = []
        for page in document.pages:
            all_blocks.extend(page.blocks)

        if not all_blocks:
            return None

        # Ordenar por posición de caracteres
        all_blocks.sort(key=lambda b: b.char_start)

        search_lower = search_text.lower()

        # 1. Búsqueda prioritaria en página sugerida
        if page_hint is not None:
            page_blocks = [b for b in all_blocks if b.page_number == page_hint]
            match = self._search_in_block_sequence(
                page_blocks, search_lower, max_block_span
            )
            if match:
                return match

        # 2. Búsqueda en bloques individuales (todo el documento)
        for block in all_blocks:
            if search_lower in block.text.lower():
                return TextMatch(
                    text=search_text,
                    page_number=block.page_number,
                    bbox=block.bbox,
                    confidence=1.0,
                    match_type="exact_block",
                    char_position=block.char_start,
                )

        # 3. Búsqueda cross-block (uniendo bloques adyacentes)
        match = self._search_in_block_sequence(all_blocks, search_lower, max_block_span)
        if match:
            return match

        # 4. Búsqueda fuzzy cross-block
        match = self._search_fuzzy_cross_block(all_blocks, search_lower, max_block_span)
        if match:
            return match

        # 5. Fallback a búsqueda por palabras clave
        return self._search_keywords(document, search_text)

    def _search_in_block_sequence(
        self,
        blocks: List[TextBlock],
        search_lower: str,
        max_span: int
    ) -> Optional[TextMatch]:
        """
        Busca texto en secuencias de bloques contiguos.

        Args:
            blocks: Lista de bloques ordenados
            search_lower: Texto a buscar (lowercase)
            max_span: Máximo de bloques a unir

        Returns:
            TextMatch o None
        """
        if not blocks:
            return None

        # Probar con diferentes tamaños de ventana
        for span in range(2, max_span + 1):
            for i in range(len(blocks) - span + 1):
                window_blocks = blocks[i:i + span]

                # Verificar que los bloques son de páginas cercanas
                page_start = window_blocks[0].page_number
                page_end = window_blocks[-1].page_number
                if page_end - page_start > 1:
                    continue  # Saltar si están en páginas muy separadas

                # Unir textos de los bloques
                combined_text = " ".join(b.text for b in window_blocks)
                combined_lower = self._clean_text(combined_text).lower()

                if search_lower in combined_lower:
                    # Encontrado! Combinar bboxes
                    combined_bbox = self._combine_bboxes(window_blocks)

                    return TextMatch(
                        text=combined_text[:len(search_lower) + 50],
                        page_number=window_blocks[0].page_number,
                        bbox=combined_bbox,
                        confidence=0.9 - (span - 2) * 0.05,
                        match_type=f"cross_block_{span}",
                        char_position=window_blocks[0].char_start,
                    )

        return None

    def _search_fuzzy_cross_block(
        self,
        blocks: List[TextBlock],
        search_lower: str,
        max_span: int
    ) -> Optional[TextMatch]:
        """
        Búsqueda fuzzy en secuencias de bloques.

        Útil cuando hay pequeñas diferencias de OCR/extracción.
        """
        if len(search_lower) < self.MIN_FUZZY_LENGTH:
            return None

        best_match = None
        best_ratio = 0.0

        for span in range(1, max_span + 1):
            for i in range(len(blocks) - span + 1):
                window_blocks = blocks[i:i + span]

                # Verificar páginas cercanas
                page_diff = window_blocks[-1].page_number - window_blocks[0].page_number
                if page_diff > 1:
                    continue

                combined_text = " ".join(b.text for b in window_blocks)
                combined_lower = self._clean_text(combined_text).lower()

                # Comparar con fragmentos del texto combinado
                if len(combined_lower) < len(search_lower) * 0.5:
                    continue

                # Usar SequenceMatcher para encontrar similitud
                ratio = SequenceMatcher(
                    None,
                    search_lower[:min(200, len(search_lower))],
                    combined_lower[:min(250, len(combined_lower))]
                ).ratio()

                if ratio > best_ratio and ratio >= self.FUZZY_THRESHOLD:
                    best_ratio = ratio
                    combined_bbox = self._combine_bboxes(window_blocks)

                    best_match = TextMatch(
                        text=combined_text[:200],
                        page_number=window_blocks[0].page_number,
                        bbox=combined_bbox,
                        confidence=ratio * (1.0 - (span - 1) * 0.05),
                        match_type=f"fuzzy_cross_{span}",
                        char_position=window_blocks[0].char_start,
                    )

        return best_match

    def _combine_bboxes(
        self,
        blocks: List[TextBlock]
    ) -> Tuple[float, float, float, float]:
        """
        Combina bboxes de múltiples bloques en uno que los englobe.

        Para bloques en la misma página, crea un rectángulo envolvente.
        Para bloques en páginas diferentes, usa el bbox del primer bloque.
        """
        if not blocks:
            return (0, 0, 0, 0)

        if len(blocks) == 1:
            return blocks[0].bbox

        # Verificar si todos están en la misma página
        pages = set(b.page_number for b in blocks)

        if len(pages) == 1:
            # Misma página: combinar bboxes
            x0 = min(b.bbox[0] for b in blocks)
            y0 = min(b.bbox[1] for b in blocks)
            x1 = max(b.bbox[2] for b in blocks)
            y1 = max(b.bbox[3] for b in blocks)
            return (x0, y0, x1, y1)
        else:
            # Diferentes páginas: usar el bbox del bloque principal
            # (el que tiene más texto probablemente)
            main_block = max(blocks, key=lambda b: len(b.text))
            return main_block.bbox

    def get_blocks_around_position(
        self,
        document: DocumentContent,
        page_number: int,
        char_position: int,
        context_blocks: int = 2
    ) -> List[TextBlock]:
        """
        Obtiene bloques alrededor de una posición.

        Útil para obtener contexto adicional alrededor de un hallazgo.

        Args:
            document: Documento extraído
            page_number: Número de página (1-indexed)
            char_position: Posición de carácter aproximada
            context_blocks: Número de bloques antes y después

        Returns:
            Lista de bloques alrededor de la posición
        """
        # Obtener bloques de la página
        page_data = None
        for page in document.pages:
            if page.page_number == page_number:
                page_data = page
                break

        if not page_data or not page_data.blocks:
            return []

        # Encontrar el bloque más cercano a la posición
        closest_idx = 0
        min_distance = float('inf')

        for i, block in enumerate(page_data.blocks):
            # Calcular distancia al centro del bloque
            block_center = (block.char_start + block.char_end) // 2
            distance = abs(block_center - char_position)

            if distance < min_distance:
                min_distance = distance
                closest_idx = i

        # Obtener bloques de contexto
        start_idx = max(0, closest_idx - context_blocks)
        end_idx = min(len(page_data.blocks), closest_idx + context_blocks + 1)

        return page_data.blocks[start_idx:end_idx]


# Singleton
document_text_service = DocumentTextService()
