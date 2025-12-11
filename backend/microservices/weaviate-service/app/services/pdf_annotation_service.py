"""
PDF Annotation Service v2.0

Añade anotaciones (highlights) directamente al PDF basándose
en el análisis de Emma. Usa PyMuPDF para manipulación nativa de PDF.

Características:
- Uso de Optional Content Groups (OCG/Layers) para organizar anotaciones
- Cada tipo de anotación en su propia capa (Riesgos, Recomendaciones, Cambios Sugeridos)
- Sistema anti-solapamiento para etiquetas
- Tooltips amplios y legibles con mejor contraste
- Highlights interactivos también toggleables por capa
- Soporte para "Cambios Sugeridos" con texto tachado y propuesta
- Annotations vinculadas a OCG con Annot.set_oc()

Referencias:
- https://pymupdf.readthedocs.io/en/latest/recipes-optional-content.html
- https://pymupdf.readthedocs.io/en/latest/annot.html (set_oc, get_oc)
- https://artifex.com/blog/optional-content-discovering-the-pdf-layers-pymupdf-python
"""
import fitz  # PyMuPDF
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
import logging
import re

logger = logging.getLogger(__name__)

# Constantes para tamaños - MEJORADAS v3.0 para legibilidad
LABEL_FONTSIZE = 8  # Tamaño compacto para margen
LABEL_PADDING = 3   # Padding interno reducido
BORDER_WIDTH = 0  # Sin borde para menos ruido visual
UNDERLINE_WIDTH = 2.0  # Grosor del subrayado
RECT_PADDING = 2    # Padding mínimo alrededor del texto
LABEL_MARGIN_TOP = 2  # Espacio entre etiqueta y rect
MIN_LABEL_SPACING = 14  # Espacio mínimo entre etiquetas
LEFT_MARGIN_WIDTH = 50  # Ancho del área de margen izquierdo para etiquetas
MARGIN_ANNOTATION_WIDTH = 200  # Ancho para anotaciones en margen derecho (fallback)


@dataclass
class AnnotationLocation:
    """Ubicación de una anotación en el PDF."""
    page_number: int  # 0-indexed
    rect: Tuple[float, float, float, float]  # x0, y0, x1, y1
    text_found: str
    confidence: float


@dataclass
class PositionData:
    """
    Datos de posición pre-calculados (de Weaviate o TextAlignmentService).

    Cuando están disponibles, permiten localización directa sin búsqueda.
    """
    page_start: int         # 1-indexed
    page_end: int           # 1-indexed
    char_start: int
    char_end: int
    bbox_start: Tuple[float, float, float, float]  # x0, y0, x1, y1
    bbox_end: Tuple[float, float, float, float]    # x0, y0, x1, y1


@dataclass
class AnnotationResult:
    """Resultado de añadir anotaciones al PDF."""
    pdf_bytes: bytes
    annotations: List[Dict[str, Any]]
    pages_annotated: int
    total_annotations: int
    failed_annotations: int


class PDFAnnotationService:
    """
    Servicio para añadir anotaciones a PDFs.

    Proceso:
    1. Extraer texto con posiciones de cada página
    2. Buscar fragmentos del análisis en el texto
    3. Añadir highlights visibles con etiquetas de color

    Usa la Shape API de PyMuPDF para crear:
    - Rectángulos de fondo semi-transparentes
    - Etiquetas con texto legible
    - Bordes de color para delimitar áreas
    """

    # Colores v3.0 - ALTA DISTINCIÓN VISUAL con subrayado
    # Diseño: subrayado de color saturado + etiqueta compacta en margen izquierdo
    # Sin fondo de highlight para no obstruir la lectura del documento
    COLORS = {
        "risk_high": {
            "fill": None,                    # Sin relleno de fondo
            "stroke": (0.8, 0.0, 0.0),       # Rojo puro para subrayado
            "text": (0.6, 0.0, 0.0),         # Rojo texto
            "label_bg": (0.85, 0.1, 0.1),    # Rojo intenso para etiqueta
            "label_text": (1.0, 1.0, 1.0),   # Blanco
            "underline": (0.85, 0.1, 0.1),   # Rojo para subrayado
            "sidebar": (0.85, 0.1, 0.1),     # Línea lateral
        },
        "risk_medium": {
            "fill": None,                    # Sin relleno
            "stroke": (0.95, 0.5, 0.0),      # Naranja intenso
            "text": (0.7, 0.35, 0.0),        # Naranja texto
            "label_bg": (0.95, 0.5, 0.0),    # Naranja para etiqueta
            "label_text": (1.0, 1.0, 1.0),   # Blanco
            "underline": (0.95, 0.5, 0.0),   # Naranja para subrayado
            "sidebar": (0.95, 0.5, 0.0),     # Línea lateral
        },
        "risk_low": {
            "fill": None,                    # Sin relleno
            "stroke": (0.75, 0.65, 0.0),     # Amarillo oscuro
            "text": (0.5, 0.45, 0.0),        # Amarillo texto
            "label_bg": (0.75, 0.65, 0.0),   # Amarillo oscuro para etiqueta
            "label_text": (1.0, 1.0, 1.0),   # Blanco
            "underline": (0.75, 0.65, 0.0),  # Amarillo para subrayado
            "sidebar": (0.75, 0.65, 0.0),    # Línea lateral
        },
        "recommendation": {
            "fill": None,                    # Sin relleno
            "stroke": (0.1, 0.4, 0.8),       # Azul intenso
            "text": (0.0, 0.3, 0.6),         # Azul texto
            "label_bg": (0.1, 0.45, 0.85),   # Azul para etiqueta
            "label_text": (1.0, 1.0, 1.0),   # Blanco
            "underline": (0.1, 0.45, 0.85),  # Azul para subrayado
            "sidebar": (0.1, 0.45, 0.85),    # Línea lateral
        },
        "suggested_change": {
            "fill": None,                    # Sin relleno
            "stroke": (0.0, 0.6, 0.3),       # Verde
            "text": (0.0, 0.5, 0.2),         # Verde texto
            "label_bg": (0.1, 0.65, 0.3),    # Verde para etiqueta
            "label_text": (1.0, 1.0, 1.0),   # Blanco
            "underline": (0.1, 0.65, 0.3),   # Verde para subrayado
            "sidebar": (0.1, 0.65, 0.3),     # Línea lateral
            "strikethrough": (0.7, 0.0, 0.0),  # Rojo para tachado
        },
        "info": {
            "fill": None,                    # Sin relleno
            "stroke": (0.4, 0.4, 0.4),       # Gris
            "text": (0.3, 0.3, 0.3),         # Gris texto
            "label_bg": (0.5, 0.5, 0.5),     # Gris para etiqueta
            "label_text": (1.0, 1.0, 1.0),   # Blanco
            "underline": (0.5, 0.5, 0.5),    # Gris para subrayado
            "sidebar": (0.5, 0.5, 0.5),      # Línea lateral
        },
    }

    # Etiquetas compactas para margen izquierdo (v3.0)
    LABELS = {
        "risk_high": "ALTO",
        "risk_medium": "MEDIO",
        "risk_low": "BAJO",
        "recommendation": "REC",
        "suggested_change": "EDIT",
        "info": "INFO",
    }

    # Nombres de capas OCG para el PDF
    LAYER_NAMES = {
        "risk_high": "Riesgos Altos",
        "risk_medium": "Riesgos Medios",
        "risk_low": "Riesgos Bajos",
        "recommendation": "Recomendaciones",
        "suggested_change": "Cambios Sugeridos",
        "info": "Información",
    }

    def annotate_pdf(
        self,
        pdf_bytes: bytes,
        analysis_items: List[Dict[str, Any]]
    ) -> AnnotationResult:
        """
        Añade anotaciones al PDF basándose en el análisis.

        Usa Optional Content Groups (OCG/Layers) para organizar las anotaciones
        por tipo, permitiendo al usuario mostrar/ocultar categorías específicas.

        Args:
            pdf_bytes: PDF original en bytes
            analysis_items: Lista de riesgos/recomendaciones con campos:
                - type: "risk" | "recommendation"
                - severity: "high" | "medium" | "low" (para risks)
                - title: Título del hallazgo
                - description: Descripción completa
                - quote: Cita textual del documento (para buscar)

        Returns:
            AnnotationResult con PDF anotado y metadata
        """
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            logger.error(f"Error abriendo PDF: {e}")
            return AnnotationResult(
                pdf_bytes=pdf_bytes,
                annotations=[],
                pages_annotated=0,
                total_annotations=0,
                failed_annotations=len(analysis_items),
            )

        # Crear capas OCG para cada tipo de anotación
        ocg_layers = self._create_ocg_layers(doc)

        annotations_added = []
        pages_with_annotations = set()
        failed_count = 0

        # Tracking de posiciones de etiquetas por página para evitar solapamiento
        page_label_positions: Dict[int, Set[Tuple[int, int]]] = {}

        for idx, item in enumerate(analysis_items):
            # Determinar qué texto buscar
            search_text = item.get("quote") or item.get("clause") or ""

            # Si no hay quote, usar fragmento de descripción
            if not search_text or len(search_text) < 10:
                description = item.get("description", "")
                # Extraer primera oración significativa
                search_text = self._extract_searchable_text(description)

            if not search_text or len(search_text) < 5:
                logger.warning(f"Item {idx} sin texto buscable: {item.get('title', 'Sin título')}")
                failed_count += 1
                continue

            # Obtener page_hint si está disponible (del DocumentTextService)
            page_hint = item.get("page_hint")

            # LOG: Información de entrada para depuración
            logger.info(
                f"📍 Item {idx}: page_hint={page_hint}, "
                f"page_start={item.get('page_start')}, "
                f"title='{item.get('title', '')[:40]}...', "
                f"quote='{search_text[:50]}...'"
            )

            # Extraer position_data si está disponible (de Weaviate o TextAlignmentService)
            position_data = None
            if item.get("page_start") and item.get("bbox_start_x0") is not None:
                try:
                    position_data = PositionData(
                        page_start=item.get("page_start", 1),
                        page_end=item.get("page_end", item.get("page_start", 1)),
                        char_start=item.get("char_start", 0),
                        char_end=item.get("char_end", 0),
                        bbox_start=(
                            item.get("bbox_start_x0", 0),
                            item.get("bbox_start_y0", 0),
                            item.get("bbox_start_x1", 0),
                            item.get("bbox_start_y1", 0),
                        ),
                        bbox_end=(
                            item.get("bbox_end_x0", 0),
                            item.get("bbox_end_y0", 0),
                            item.get("bbox_end_x1", 0),
                            item.get("bbox_end_y1", 0),
                        ),
                    )
                    # Usar page_start como page_hint si no hay otro
                    if page_hint is None:
                        page_hint = position_data.page_start
                except Exception as e:
                    logger.warning(f"Error extrayendo position_data: {e}")

            # Buscar el texto en el PDF, usando position_data si está disponible
            location = self._find_text_location(
                doc, search_text, page_hint=page_hint, position_data=position_data
            )

            if location:
                # LOG: Ubicación encontrada
                logger.info(
                    f"✅ Item {idx} localizado: página {location.page_number + 1} "
                    f"(esperado: {page_hint or 'N/A'}), "
                    f"confianza={location.confidence:.2f}, "
                    f"rect=({location.rect[0]:.0f},{location.rect[1]:.0f},{location.rect[2]:.0f},{location.rect[3]:.0f})"
                )

                # Verificar discrepancia de página
                if page_hint and location.page_number + 1 != page_hint:
                    logger.warning(
                        f"⚠️ DISCREPANCIA: Item {idx} esperado en página {page_hint}, "
                        f"encontrado en página {location.page_number + 1}"
                    )

                # Obtener la capa OCG correspondiente
                color_key = self._get_color_key(item)
                ocg_xref = ocg_layers.get(color_key, 0)

                # Obtener/crear set de posiciones para esta página
                page_num = location.page_number
                if page_num not in page_label_positions:
                    page_label_positions[page_num] = set()

                # Añadir anotación con capa y tracking anti-solapamiento
                self._add_layered_annotation(
                    doc, location, item, ocg_xref,
                    used_positions=page_label_positions[page_num]
                )

                pages_with_annotations.add(location.page_number)
                annotations_added.append({
                    "id": item.get("id", f"annot_{idx}"),
                    "type": item.get("type", "risk"),
                    "severity": item.get("severity"),
                    "title": item.get("title", ""),
                    "description": item.get("description", ""),
                    "page_number": location.page_number + 1,  # 1-indexed para UI
                    "rect": {
                        "x0": location.rect[0],
                        "y0": location.rect[1],
                        "x1": location.rect[2],
                        "y1": location.rect[3],
                    },
                    "text_found": location.text_found,
                    "confidence": location.confidence,
                    "layer": self.LAYER_NAMES.get(color_key, "Otros"),
                })
            else:
                logger.warning(f"No se encontró texto para: {item.get('title', 'Sin título')[:50]}")
                failed_count += 1

        # Guardar PDF modificado
        try:
            pdf_output = doc.tobytes(
                garbage=4,  # Limpieza agresiva
                deflate=True,  # Comprimir
            )
        except Exception as e:
            logger.error(f"Error guardando PDF: {e}")
            pdf_output = pdf_bytes
        finally:
            doc.close()

        logger.info(
            f"PDF anotado: {len(annotations_added)} anotaciones en {len(pages_with_annotations)} páginas, "
            f"{failed_count} fallidas, {len(ocg_layers)} capas creadas"
        )

        return AnnotationResult(
            pdf_bytes=pdf_output,
            annotations=annotations_added,
            pages_annotated=len(pages_with_annotations),
            total_annotations=len(annotations_added),
            failed_annotations=failed_count,
        )

    def _create_ocg_layers(self, doc: fitz.Document) -> Dict[str, int]:
        """
        Crea capas OCG (Optional Content Groups) para cada tipo de anotación.

        Returns:
            Diccionario con color_key -> ocg_xref
        """
        ocg_layers = {}

        for color_key, layer_name in self.LAYER_NAMES.items():
            try:
                # Crear OCG con el nombre descriptivo
                ocg_xref = doc.add_ocg(
                    layer_name,
                    on=True,  # Visible por defecto
                    intent="View",
                    usage="Artwork",
                )
                ocg_layers[color_key] = ocg_xref
                logger.debug(f"Capa OCG creada: {layer_name} (xref={ocg_xref})")
            except Exception as e:
                logger.warning(f"Error creando capa {layer_name}: {e}")
                ocg_layers[color_key] = 0  # Sin capa

        return ocg_layers

    def _extract_searchable_text(self, text: str) -> str:
        """Extrae texto buscable de una descripción."""
        if not text:
            return ""

        # Limpiar el texto
        text = text.strip()

        # Buscar texto entre comillas (probable cita)
        quotes = re.findall(r'["\']([^"\']{10,})["\']', text)
        if quotes:
            return quotes[0]

        # Tomar primera oración significativa
        sentences = re.split(r'[.!?]', text)
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) >= 20:
                return sentence[:150]  # Limitar longitud

        return text[:100] if len(text) >= 10 else ""

    def _find_text_location(
        self,
        doc: fitz.Document,
        search_text: str,
        page_hint: Optional[int] = None,
        position_data: Optional[PositionData] = None,
    ) -> Optional[AnnotationLocation]:
        """
        Busca texto en el PDF y devuelve su ubicación.

        Args:
            doc: Documento PDF
            search_text: Texto a buscar
            page_hint: Número de página sugerido (1-indexed) para priorizar búsqueda
            position_data: Datos de posición pre-calculados (de Weaviate)

        Estrategias de búsqueda (en orden):
        0. Usar position_data directamente si está disponible
        1. Búsqueda en página sugerida (si se proporciona page_hint)
        2. Búsqueda exacta en todo el documento
        3. Búsqueda por primeras palabras (fragmentos)
        4. Búsqueda por palabras clave largas
        """
        # === Estrategia 0: Usar posición pre-calculada ===
        if position_data is not None:
            location = self._use_position_data(doc, position_data, search_text)
            if location:
                logger.debug(
                    f"Usando posición pre-calculada: página {location.page_number + 1}, "
                    f"confianza {location.confidence:.2f}"
                )
                return location
            else:
                # position_data no funcionó, intentar con page_hint derivado
                if page_hint is None:
                    page_hint = position_data.page_start

        search_text_clean = self._normalize_text(search_text)

        if len(search_text_clean) < 5:
            return None

        # Estrategia 1: Buscar primero en la página sugerida
        if page_hint is not None and 1 <= page_hint <= len(doc):
            page_idx = page_hint - 1  # Convertir a 0-indexed
            location = self._search_in_page(doc, page_idx, search_text_clean)
            if location:
                logger.debug(f"Texto encontrado en página sugerida {page_hint}")
                return location

        # Estrategia 2: Búsqueda exacta en todo el documento
        location = self._search_exact(doc, search_text_clean)
        if location:
            return location

        # Estrategia 3: Buscar primeras N palabras
        words = search_text_clean.split()
        for word_count in [15, 10, 7, 5]:
            if len(words) >= word_count:
                fragment = " ".join(words[:word_count])

                # Primero en página sugerida
                if page_hint is not None and 1 <= page_hint <= len(doc):
                    location = self._search_in_page(doc, page_hint - 1, fragment)
                    if location:
                        location.confidence = 0.85
                        return location

                # Luego en todo el documento
                location = self._search_exact(doc, fragment)
                if location:
                    location.confidence = 0.8
                    return location

        # Estrategia 4: Buscar palabras clave individuales (más largas)
        key_words = [w for w in words if len(w) > 6][:5]

        # Primero en página sugerida
        if page_hint is not None and 1 <= page_hint <= len(doc):
            page = doc[page_hint - 1]
            for word in key_words:
                rects = page.search_for(word, quads=False)
                if rects and len(rects) > 0:
                    return AnnotationLocation(
                        page_number=page_hint - 1,
                        rect=tuple(rects[0]),
                        text_found=word,
                        confidence=0.6,
                    )

        # Luego en todo el documento
        for word in key_words:
            for page_num, page in enumerate(doc):
                rects = page.search_for(word, quads=False)
                if rects and len(rects) > 0:
                    return AnnotationLocation(
                        page_number=page_num,
                        rect=tuple(rects[0]),
                        text_found=word,
                        confidence=0.5,
                    )

        return None

    def _use_position_data(
        self,
        doc: fitz.Document,
        position_data: PositionData,
        search_text: str,
    ) -> Optional[AnnotationLocation]:
        """
        Usa datos de posición pre-calculados para localizar texto.

        Si los bbox son válidos, los usa directamente.
        Si no, verifica que el texto está en la página indicada.

        Args:
            doc: Documento PDF
            position_data: Datos de posición
            search_text: Texto para verificación

        Returns:
            AnnotationLocation si se puede usar position_data, None si no
        """
        page_idx = position_data.page_start - 1  # Convertir a 0-indexed

        # Verificar que la página existe
        if page_idx < 0 or page_idx >= len(doc):
            logger.warning(
                f"Página {position_data.page_start} fuera de rango (documento tiene {len(doc)} páginas)"
            )
            return None

        bbox = position_data.bbox_start

        # Si bbox tiene valores válidos (no ceros), usarlo directamente
        if bbox[2] > bbox[0] and bbox[3] > bbox[1]:  # x1 > x0 y y1 > y0
            # Verificar que el bbox está dentro de la página
            page = doc[page_idx]
            page_rect = page.rect

            # Ajustar bbox si está fuera de límites
            adjusted_bbox = (
                max(0, min(bbox[0], page_rect.width)),
                max(0, min(bbox[1], page_rect.height)),
                max(0, min(bbox[2], page_rect.width)),
                max(0, min(bbox[3], page_rect.height)),
            )

            # Si el bbox ajustado tiene área significativa, usarlo
            width = adjusted_bbox[2] - adjusted_bbox[0]
            height = adjusted_bbox[3] - adjusted_bbox[1]

            if width > 10 and height > 5:  # Mínimo 10x5 pixels
                return AnnotationLocation(
                    page_number=page_idx,
                    rect=adjusted_bbox,
                    text_found=search_text[:100],  # Truncar para el log
                    confidence=0.95,  # Alta confianza en datos pre-calculados
                )

        # Si bbox no es válido, intentar buscar en la página indicada
        search_clean = self._normalize_text(search_text)
        if len(search_clean) >= 5:
            location = self._search_in_page(doc, page_idx, search_clean)
            if location:
                location.confidence = 0.9  # Confianza alta porque usamos page_hint de position_data
                return location

        return None

    def _search_in_page(
        self,
        doc: fitz.Document,
        page_num: int,
        text: str
    ) -> Optional[AnnotationLocation]:
        """Busca texto en una página específica."""
        if page_num < 0 or page_num >= len(doc):
            return None

        page = doc[page_num]
        rects = page.search_for(text, quads=False)

        if rects and len(rects) > 0:
            combined_rect = self._combine_rects(rects)
            return AnnotationLocation(
                page_number=page_num,
                rect=combined_rect,
                text_found=text,
                confidence=1.0,
            )
        return None

    def _search_exact(
        self,
        doc: fitz.Document,
        text: str
    ) -> Optional[AnnotationLocation]:
        """Búsqueda exacta de texto en el documento."""
        for page_num, page in enumerate(doc):
            rects = page.search_for(text, quads=False)
            if rects and len(rects) > 0:
                combined_rect = self._combine_rects(rects)
                return AnnotationLocation(
                    page_number=page_num,
                    rect=combined_rect,
                    text_found=text,
                    confidence=1.0,
                )
        return None

    def _normalize_text(self, text: str) -> str:
        """Normaliza texto para búsqueda."""
        if not text:
            return ""
        # Eliminar saltos de línea extra y espacios múltiples
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _combine_rects(self, rects: List) -> Tuple[float, float, float, float]:
        """Combina múltiples rectángulos en uno que los englobe."""
        if not rects:
            return (0, 0, 0, 0)

        x0 = min(r.x0 for r in rects)
        y0 = min(r.y0 for r in rects)
        x1 = max(r.x1 for r in rects)
        y1 = max(r.y1 for r in rects)

        return (x0, y0, x1, y1)

    def _get_color_key(self, item: Dict) -> str:
        """Obtiene la clave de color según tipo y severidad."""
        item_type = item.get("type", "risk")
        severity = item.get("severity", "medium")

        if item_type == "recommendation":
            return "recommendation"

        if item_type == "suggested_change" or item_type == "change":
            return "suggested_change"

        if item_type == "info":
            return "info"

        color_key = f"risk_{severity}"
        return color_key if color_key in self.COLORS else "risk_medium"

    def _get_colors(self, item: Dict) -> Dict[str, Tuple[float, float, float]]:
        """Obtiene el diccionario de colores según tipo y severidad."""
        color_key = self._get_color_key(item)
        return self.COLORS.get(color_key, self.COLORS["risk_medium"])

    def _calculate_label_position_left_margin(
        self,
        page: fitz.Page,
        text_rect: fitz.Rect,
        label_height: float,
        used_positions: Set[Tuple[int, int]],
    ) -> Tuple[float, float]:
        """
        Calcula posición para etiqueta en el MARGEN IZQUIERDO (v3.0).

        Las etiquetas se colocan en el margen izquierdo de la página,
        alineadas verticalmente con el texto anotado.

        Args:
            page: Página del PDF
            text_rect: Rectángulo del texto anotado
            label_height: Alto de la etiqueta
            used_positions: Set de posiciones ya usadas (grid 10x10)

        Returns:
            (x, y) posición de la etiqueta
        """
        # Posición X: siempre en el margen izquierdo (5px desde el borde)
        label_x0 = 5

        # Posición Y: alineada con el centro vertical del texto
        label_y0 = text_rect.y0 + (text_rect.height - label_height) / 2

        # Asegurar que está dentro de la página
        label_y0 = max(5, min(label_y0, page.rect.height - label_height - 5))

        # Verificar solapamiento con otras etiquetas
        grid_y = int(label_y0 / MIN_LABEL_SPACING)
        grid_key = (0, grid_y)  # X siempre es 0 (margen izquierdo)

        if grid_key in used_positions:
            # Desplazar verticalmente para evitar solapamiento
            for offset in range(1, 10):
                # Intentar arriba
                new_y = label_y0 - offset * MIN_LABEL_SPACING
                if new_y >= 5:
                    new_grid = (0, int(new_y / MIN_LABEL_SPACING))
                    if new_grid not in used_positions:
                        used_positions.add(new_grid)
                        return (label_x0, new_y)

                # Intentar abajo
                new_y = label_y0 + offset * MIN_LABEL_SPACING
                if new_y + label_height <= page.rect.height - 5:
                    new_grid = (0, int(new_y / MIN_LABEL_SPACING))
                    if new_grid not in used_positions:
                        used_positions.add(new_grid)
                        return (label_x0, new_y)

        used_positions.add(grid_key)
        return (label_x0, label_y0)

    def _add_layered_annotation(
        self,
        doc: fitz.Document,
        location: AnnotationLocation,
        item: Dict,
        ocg_xref: int,
        used_positions: Optional[Set[Tuple[int, int]]] = None,
    ):
        """
        Añade anotaciones al PDF (diseño simplificado).

        DISEÑO v4.0 - Minimalista:
        - SUBRAYADO de color debajo del texto
        - ETIQUETA compacta en el margen izquierdo (ALTO, MEDIO, BAJO, REC)
        - Sin líneas conectoras ni barras laterales
        - Los detalles se muestran en el sidebar del frontend

        Args:
            doc: Documento PDF
            location: Ubicación del texto encontrado
            item: Datos del hallazgo (título, descripción, etc.)
            ocg_xref: xref de la capa OCG (0 = sin capa)
            used_positions: Set compartido para tracking de posiciones usadas
        """
        if used_positions is None:
            used_positions = set()

        page = doc[location.page_number]
        rect = fitz.Rect(location.rect)

        # Log detallado de página para depuración
        logger.debug(
            f"Anotando en página {location.page_number + 1} (0-idx: {location.page_number}): "
            f"rect=({rect.x0:.1f}, {rect.y0:.1f}, {rect.x1:.1f}, {rect.y1:.1f}), "
            f"item={item.get('title', 'Sin título')[:40]}"
        )

        # Obtener colores
        colors = self._get_colors(item)
        color_key = self._get_color_key(item)

        try:
            # === 1. SUBRAYADO del texto (en lugar de highlight de fondo) ===
            # IMPORTANTE: rect.y1 es la parte inferior del rect, añadimos margen
            # para asegurar que el subrayado esté DEBAJO del texto, no atravesándolo
            underline_y = rect.y1 + 2  # 2px debajo del texto para margen seguro
            page.draw_line(
                fitz.Point(rect.x0, underline_y),
                fitz.Point(rect.x1, underline_y),
                color=colors.get("underline", colors["stroke"]),
                width=UNDERLINE_WIDTH,
                stroke_opacity=0.85,
                oc=ocg_xref,
            )

            # === 2. ETIQUETA en margen izquierdo ===
            label_text = self.LABELS.get(color_key, "INFO")
            label_height = LABEL_FONTSIZE + LABEL_PADDING * 2

            # Calcular ancho basado en el texto
            label_width = len(label_text) * (LABEL_FONTSIZE * 0.6) + LABEL_PADDING * 2
            label_width = max(label_width, 35)  # Mínimo 35px

            # Posición en margen izquierdo con anti-solapamiento
            label_x0, label_y0 = self._calculate_label_position_left_margin(
                page, rect, label_height, used_positions
            )

            label_rect = fitz.Rect(
                label_x0,
                label_y0,
                label_x0 + label_width,
                label_y0 + label_height
            )

            # Fondo de la etiqueta (compacto, sin bordes redondeados)
            page.draw_rect(
                label_rect,
                color=colors["label_bg"],
                fill=colors["label_bg"],
                width=0,
                fill_opacity=0.95,
                overlay=True,
                oc=ocg_xref,
            )

            # Texto de la etiqueta (centrado)
            text_x = label_rect.x0 + LABEL_PADDING
            text_y = label_rect.y0 + LABEL_FONTSIZE + (LABEL_PADDING / 2)
            page.insert_text(
                fitz.Point(text_x, text_y),
                label_text,
                fontsize=LABEL_FONTSIZE,
                fontname="helv",
                color=colors["label_text"],
                overlay=True,
                oc=ocg_xref,
            )

            # Solo subrayado + etiqueta (simplificado)

        except Exception as e:
            logger.warning(f"Error añadiendo anotación v3.0: {e}")
            import traceback
            traceback.print_exc()
            # Fallback a highlight simple
            self._add_simple_highlight(page, rect, colors, item)

    def _add_simple_highlight(
        self,
        page: fitz.Page,
        rect: fitz.Rect,
        colors: Dict,
        item: Dict
    ):
        """
        Fallback: añade un subrayado simple sin capas OCG.

        IMPORTANTE: NO usar highlight_annot con opacity porque oscurece el texto.
        En su lugar, dibujar solo un subrayado y una pequeña nota.
        """
        try:
            # Solo dibujar un subrayado debajo del texto (no highlight)
            underline_y = rect.y1 + 2  # 2px debajo para margen seguro
            page.draw_line(
                fitz.Point(rect.x0, underline_y),
                fitz.Point(rect.x1, underline_y),
                color=colors.get("stroke", (1, 0, 0)),
                width=UNDERLINE_WIDTH,
                stroke_opacity=0.8,
            )

            # Solo subrayado (simplificado)

        except Exception as e:
            logger.error(f"Error en fallback de highlight: {e}")

    def extract_text_with_positions(
        self,
        pdf_bytes: bytes
    ) -> List[Dict[str, Any]]:
        """
        Extrae todo el texto del PDF con posiciones.
        Útil para debugging o para mostrar en frontend.

        Returns:
            Lista de páginas con sus bloques de texto
        """
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            logger.error(f"Error abriendo PDF: {e}")
            return []

        pages_data = []

        for page_num, page in enumerate(doc):
            page_data = {
                "page_number": page_num + 1,  # 1-indexed
                "width": page.rect.width,
                "height": page.rect.height,
                "blocks": [],
            }

            try:
                blocks = page.get_text("dict")["blocks"]

                for block in blocks:
                    if block.get("type") == 0:  # Text block
                        for line in block.get("lines", []):
                            line_text = ""
                            line_bbox = None

                            for span in line.get("spans", []):
                                line_text += span.get("text", "")
                                if line_bbox is None:
                                    line_bbox = span.get("bbox")
                                else:
                                    # Expandir bbox
                                    sb = span.get("bbox")
                                    if sb:
                                        line_bbox = (
                                            min(line_bbox[0], sb[0]),
                                            min(line_bbox[1], sb[1]),
                                            max(line_bbox[2], sb[2]),
                                            max(line_bbox[3], sb[3]),
                                        )

                            if line_text.strip():
                                page_data["blocks"].append({
                                    "text": line_text,
                                    "bbox": line_bbox,
                                })
            except Exception as e:
                logger.warning(f"Error extrayendo texto de página {page_num}: {e}")

            pages_data.append(page_data)

        doc.close()
        return pages_data


    def get_ocg_info(self, pdf_bytes: bytes) -> Dict[str, Any]:
        """
        Método de debug: Lista todas las capas OCG en un PDF.

        Útil para verificar que las capas se crearon correctamente.

        Returns:
            Dict con información de capas OCG
        """
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            logger.error(f"Error abriendo PDF: {e}")
            return {"error": str(e), "layers": []}

        try:
            # Obtener todas las OCGs
            ocgs = doc.get_ocgs()

            layers_info = []
            for xref, info in ocgs.items():
                layers_info.append({
                    "xref": xref,
                    "name": info.get("name", "Sin nombre"),
                    "on": info.get("on", True),
                    "intent": info.get("intent", "View"),
                    "usage": info.get("usage", ""),
                })

            # Obtener configuración de capas UI
            ui_configs = []
            try:
                for config in doc.layer_ui_configs():
                    ui_configs.append(config)
            except Exception:
                pass

            return {
                "total_layers": len(layers_info),
                "layers": layers_info,
                "ui_configs": ui_configs,
                "has_optional_content": len(layers_info) > 0,
            }

        finally:
            doc.close()

    def add_suggested_change(
        self,
        pdf_bytes: bytes,
        page_number: int,
        original_text: str,
        suggested_text: str,
        reason: str = "",
    ) -> AnnotationResult:
        """
        Añade una sugerencia de cambio específica al PDF.

        Crea una anotación con:
        - Texto original tachado
        - Texto sugerido visible
        - Tooltip con la razón del cambio

        Args:
            pdf_bytes: PDF original
            page_number: Número de página (1-indexed)
            original_text: Texto a tachar
            suggested_text: Texto de reemplazo sugerido
            reason: Razón del cambio sugerido

        Returns:
            AnnotationResult con el PDF modificado
        """
        analysis_item = {
            "type": "suggested_change",
            "title": f"Cambio sugerido",
            "description": reason or f"Reemplazar '{original_text[:30]}...' con '{suggested_text[:30]}...'",
            "quote": original_text,
            "suggested_text": suggested_text,
            "page_hint": page_number,
        }

        return self.annotate_pdf(pdf_bytes, [analysis_item])


# Singleton
pdf_annotation_service = PDFAnnotationService()
