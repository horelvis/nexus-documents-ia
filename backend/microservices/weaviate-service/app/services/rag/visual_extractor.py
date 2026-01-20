"""
Visual Content Extractor

Extracts visual elements from PDF documents for multimodal embedding:
- Embedded images (photos, diagrams, charts)
- Tables rendered as images (preserves visual layout)
- Flowcharts and architecture diagrams
- Page thumbnails for layout understanding

Uses PyMuPDF (fitz) for high-quality PDF rendering.

Usage:
    from app.services.rag.visual_extractor import visual_extractor

    # Extract all visual content from a PDF
    visuals = await visual_extractor.extract_visuals(
        pdf_bytes=pdf_content,
        document_id="doc-123",
        extract_tables=True,
        extract_images=True,
        extract_diagrams=True,
        page_thumbnails=False,
    )

    # Each visual has: image_bytes, content_type, page_number, bbox, caption
"""

import asyncio
import io
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple, Dict, Any

from app.core.config import settings
from app.services.multimodal_embedding_service import ContentType, VisualContent

logger = logging.getLogger(__name__)


class TableDetectionMethod(str, Enum):
    """Method used to detect tables"""
    RULED = "ruled"  # Lines/borders detected
    STRUCTURE = "structure"  # Cell structure detected
    REGEX = "regex"  # Text pattern detected


@dataclass
class ExtractedVisual:
    """A visual element extracted from a document"""
    content_type: ContentType
    image_bytes: bytes
    page_number: int
    bbox: Tuple[float, float, float, float]  # (x0, y0, x1, y1) in PDF coordinates
    caption: Optional[str] = None
    width: int = 0
    height: int = 0
    detection_method: Optional[str] = None
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_visual_content(self) -> VisualContent:
        """Convert to VisualContent for embedding"""
        return VisualContent(
            content_type=self.content_type,
            image_bytes=self.image_bytes,
            caption=self.caption,
            page_number=self.page_number,
            bbox=self.bbox,
            metadata={
                "width": self.width,
                "height": self.height,
                "detection_method": self.detection_method,
                "confidence": self.confidence,
                **self.metadata,
            },
        )


@dataclass
class VisualExtractionResult:
    """Result of visual content extraction"""
    document_id: str
    visuals: List[ExtractedVisual] = field(default_factory=list)
    page_count: int = 0
    images_count: int = 0
    tables_count: int = 0
    diagrams_count: int = 0
    thumbnails_count: int = 0
    processing_time_ms: float = 0.0
    success: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class VisualContentExtractor:
    """
    Extract visual content from PDF documents.

    Capabilities:
    - Extract embedded images with deduplication
    - Detect and render tables as images (preserves visual layout)
    - Detect flowcharts/diagrams based on shape analysis
    - Generate page thumbnails for layout context

    All images are rendered at configurable DPI and resized to max dimensions.
    """

    def __init__(
        self,
        render_dpi: int = None,
        max_image_size: int = None,
        image_format: str = None,
        min_image_area: int = 5000,  # Min pixels² to keep (filters tiny images)
        min_table_rows: int = 2,
        min_table_cols: int = 2,
    ):
        self.render_dpi = render_dpi or settings.multimodal_render_dpi
        self.max_image_size = max_image_size or settings.multimodal_max_image_size
        self.image_format = image_format or settings.multimodal_image_format
        self.min_image_area = min_image_area
        self.min_table_rows = min_table_rows
        self.min_table_cols = min_table_cols

    async def extract_visuals(
        self,
        pdf_bytes: bytes,
        document_id: str,
        extract_tables: bool = None,
        extract_images: bool = None,
        extract_diagrams: bool = None,
        page_thumbnails: bool = None,
    ) -> VisualExtractionResult:
        """
        Extract all visual content from a PDF document.

        Args:
            pdf_bytes: PDF file content
            document_id: Document identifier for logging
            extract_tables: Extract tables as images (default from config)
            extract_images: Extract embedded images (default from config)
            extract_diagrams: Detect and extract diagrams (default from config)
            page_thumbnails: Generate page thumbnails (default from config)

        Returns:
            VisualExtractionResult with extracted visuals
        """
        import time
        start_time = time.time()

        # Use config defaults if not specified
        extract_tables = extract_tables if extract_tables is not None else settings.multimodal_extract_tables
        extract_images = extract_images if extract_images is not None else settings.multimodal_extract_images
        extract_diagrams = extract_diagrams if extract_diagrams is not None else settings.multimodal_extract_diagrams
        page_thumbnails = page_thumbnails if page_thumbnails is not None else settings.multimodal_page_thumbnails

        result = VisualExtractionResult(document_id=document_id)

        try:
            import fitz  # PyMuPDF

            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            result.page_count = len(doc)

            logger.info(
                f"[{document_id}] Extracting visuals from {result.page_count} pages "
                f"(tables={extract_tables}, images={extract_images}, "
                f"diagrams={extract_diagrams}, thumbnails={page_thumbnails})"
            )

            # Track seen image hashes to avoid duplicates
            seen_image_hashes = set()

            for page_num in range(len(doc)):
                page = doc[page_num]

                # Extract embedded images
                if extract_images:
                    images = await self._extract_images(
                        page, page_num, seen_image_hashes, document_id
                    )
                    result.visuals.extend(images)
                    result.images_count += len(images)

                # Detect and render tables
                if extract_tables:
                    tables = await self._extract_tables(page, page_num, document_id)
                    result.visuals.extend(tables)
                    result.tables_count += len(tables)

                # Detect diagrams/flowcharts
                if extract_diagrams:
                    diagrams = await self._extract_diagrams(page, page_num, document_id)
                    result.visuals.extend(diagrams)
                    result.diagrams_count += len(diagrams)

                # Generate page thumbnail
                if page_thumbnails:
                    thumbnail = await self._generate_thumbnail(page, page_num, document_id)
                    if thumbnail:
                        result.visuals.append(thumbnail)
                        result.thumbnails_count += 1

            doc.close()

            result.processing_time_ms = (time.time() - start_time) * 1000

            logger.info(
                f"[{document_id}] Extracted {len(result.visuals)} visuals: "
                f"{result.images_count} images, {result.tables_count} tables, "
                f"{result.diagrams_count} diagrams, {result.thumbnails_count} thumbnails "
                f"({result.processing_time_ms:.0f}ms)"
            )

        except Exception as e:
            logger.error(f"[{document_id}] Visual extraction failed: {e}")
            result.success = False
            result.errors.append(str(e))
            result.processing_time_ms = (time.time() - start_time) * 1000

        return result

    async def _extract_images(
        self,
        page,
        page_num: int,
        seen_hashes: set,
        document_id: str,
    ) -> List[ExtractedVisual]:
        """Extract embedded images from a page"""
        import fitz
        import hashlib

        extracted = []

        try:
            image_list = page.get_images(full=True)

            for img_index, img_info in enumerate(image_list):
                xref = img_info[0]

                try:
                    # Extract image
                    base_image = page.parent.extract_image(xref)
                    if not base_image:
                        continue

                    image_bytes = base_image["image"]

                    # Check for duplicates
                    img_hash = hashlib.md5(image_bytes).hexdigest()
                    if img_hash in seen_hashes:
                        continue
                    seen_hashes.add(img_hash)

                    # Get image dimensions
                    width = base_image.get("width", 0)
                    height = base_image.get("height", 0)

                    # Filter tiny images (icons, bullets, etc.)
                    if width * height < self.min_image_area:
                        continue

                    # Get bounding box on page
                    bbox = self._get_image_bbox(page, xref)

                    # Resize if needed
                    processed_bytes = await self._process_image(
                        image_bytes, base_image.get("ext", "png")
                    )

                    if processed_bytes:
                        extracted.append(ExtractedVisual(
                            content_type=ContentType.IMAGE,
                            image_bytes=processed_bytes,
                            page_number=page_num,
                            bbox=bbox,
                            width=width,
                            height=height,
                            detection_method="embedded",
                            metadata={
                                "xref": xref,
                                "original_format": base_image.get("ext", "unknown"),
                            },
                        ))

                except Exception as e:
                    logger.debug(f"[{document_id}] Failed to extract image {xref}: {e}")

        except Exception as e:
            logger.warning(f"[{document_id}] Image extraction error on page {page_num}: {e}")

        return extracted

    async def _extract_tables(
        self,
        page,
        page_num: int,
        document_id: str,
    ) -> List[ExtractedVisual]:
        """Detect and render tables as images"""
        import fitz

        extracted = []

        try:
            # Method 1: Use PyMuPDF's table detection (fitz >= 1.23)
            if hasattr(page, "find_tables"):
                tables = page.find_tables()

                for table_idx, table in enumerate(tables):
                    try:
                        bbox = table.bbox

                        # Filter small tables
                        if table.row_count < self.min_table_rows:
                            continue
                        if table.col_count < self.min_table_cols:
                            continue

                        # Render table region as image
                        table_image = await self._render_region(
                            page, bbox, document_id
                        )

                        if table_image:
                            # Generate caption from table headers if possible
                            caption = self._extract_table_caption(table)

                            extracted.append(ExtractedVisual(
                                content_type=ContentType.TABLE_IMAGE,
                                image_bytes=table_image,
                                page_number=page_num,
                                bbox=bbox,
                                caption=caption,
                                detection_method=TableDetectionMethod.STRUCTURE.value,
                                metadata={
                                    "rows": table.row_count,
                                    "cols": table.col_count,
                                    "table_index": table_idx,
                                },
                            ))

                    except Exception as e:
                        logger.debug(f"[{document_id}] Table render error: {e}")

            else:
                # Fallback: Detect tables via line analysis
                tables = await self._detect_tables_by_lines(page)

                for bbox in tables:
                    table_image = await self._render_region(page, bbox, document_id)
                    if table_image:
                        extracted.append(ExtractedVisual(
                            content_type=ContentType.TABLE_IMAGE,
                            image_bytes=table_image,
                            page_number=page_num,
                            bbox=bbox,
                            detection_method=TableDetectionMethod.RULED.value,
                        ))

        except Exception as e:
            logger.warning(f"[{document_id}] Table detection error on page {page_num}: {e}")

        return extracted

    async def _extract_diagrams(
        self,
        page,
        page_num: int,
        document_id: str,
    ) -> List[ExtractedVisual]:
        """Detect and extract diagrams/flowcharts"""
        import fitz

        extracted = []

        try:
            # Get all drawings on the page
            drawings = page.get_drawings()

            if not drawings:
                return extracted

            # Cluster nearby shapes into potential diagrams
            diagram_regions = self._cluster_drawings(drawings, page)

            for region_idx, bbox in enumerate(diagram_regions):
                # Skip small regions
                width = bbox[2] - bbox[0]
                height = bbox[3] - bbox[1]
                if width * height < self.min_image_area:
                    continue

                # Render the region
                diagram_image = await self._render_region(page, bbox, document_id)

                if diagram_image:
                    extracted.append(ExtractedVisual(
                        content_type=ContentType.DIAGRAM,
                        image_bytes=diagram_image,
                        page_number=page_num,
                        bbox=bbox,
                        detection_method="shapes",
                        metadata={
                            "shape_count": len([d for d in drawings if self._rect_contains(bbox, d["rect"])]),
                            "region_index": region_idx,
                        },
                    ))

        except Exception as e:
            logger.warning(f"[{document_id}] Diagram detection error on page {page_num}: {e}")

        return extracted

    async def _generate_thumbnail(
        self,
        page,
        page_num: int,
        document_id: str,
    ) -> Optional[ExtractedVisual]:
        """Generate a page thumbnail"""
        try:
            # Render at lower DPI for thumbnails
            thumbnail_dpi = min(72, self.render_dpi)
            mat = page.parent.__class__.Matrix(thumbnail_dpi / 72, thumbnail_dpi / 72)

            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes(output=self.image_format)

            return ExtractedVisual(
                content_type=ContentType.PAGE_THUMBNAIL,
                image_bytes=img_bytes,
                page_number=page_num,
                bbox=(0, 0, page.rect.width, page.rect.height),
                width=pix.width,
                height=pix.height,
                detection_method="full_page",
            )

        except Exception as e:
            logger.debug(f"[{document_id}] Thumbnail generation failed: {e}")
            return None

    async def _render_region(
        self,
        page,
        bbox: Tuple[float, float, float, float],
        document_id: str,
    ) -> Optional[bytes]:
        """Render a specific region of a page as an image"""
        import fitz

        try:
            # Create clip rectangle
            clip = fitz.Rect(bbox)

            # Calculate zoom based on DPI
            zoom = self.render_dpi / 72
            mat = fitz.Matrix(zoom, zoom)

            # Render with clipping
            pix = page.get_pixmap(matrix=mat, clip=clip)

            # Resize if too large
            if pix.width > self.max_image_size or pix.height > self.max_image_size:
                scale = min(
                    self.max_image_size / pix.width,
                    self.max_image_size / pix.height
                )
                new_width = int(pix.width * scale)
                new_height = int(pix.height * scale)

                # PyMuPDF doesn't have resize, use PIL
                from PIL import Image
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

                buf = io.BytesIO()
                img.save(buf, format=self.image_format.upper())
                return buf.getvalue()

            return pix.tobytes(output=self.image_format)

        except Exception as e:
            logger.debug(f"[{document_id}] Region render failed: {e}")
            return None

    async def _process_image(
        self,
        image_bytes: bytes,
        original_format: str,
    ) -> Optional[bytes]:
        """Process and resize an image if needed"""
        try:
            from PIL import Image

            img = Image.open(io.BytesIO(image_bytes))

            # Convert CMYK to RGB if needed
            if img.mode == "CMYK":
                img = img.convert("RGB")
            elif img.mode == "P":
                img = img.convert("RGBA")

            # Resize if too large
            if img.width > self.max_image_size or img.height > self.max_image_size:
                scale = min(
                    self.max_image_size / img.width,
                    self.max_image_size / img.height
                )
                new_size = (int(img.width * scale), int(img.height * scale))
                img = img.resize(new_size, Image.Resampling.LANCZOS)

            # Convert to target format
            buf = io.BytesIO()
            if img.mode == "RGBA" and self.image_format.lower() == "jpeg":
                # JPEG doesn't support alpha
                img = img.convert("RGB")
            img.save(buf, format=self.image_format.upper())
            return buf.getvalue()

        except Exception as e:
            logger.debug(f"Image processing failed: {e}")
            return None

    def _get_image_bbox(self, page, xref: int) -> Tuple[float, float, float, float]:
        """Get the bounding box of an image on a page"""
        try:
            # Search for image placement
            for item in page.get_images(full=True):
                if item[0] == xref:
                    # Get image rect from page content
                    for img_rect in page.get_image_rects(xref):
                        return tuple(img_rect)

            # Fallback: return page bounds
            return (0, 0, page.rect.width, page.rect.height)

        except Exception:
            return (0, 0, page.rect.width, page.rect.height)

    def _extract_table_caption(self, table) -> Optional[str]:
        """Extract caption/header from table"""
        try:
            if hasattr(table, "header") and table.header:
                headers = [str(cell) for row in table.header.cells for cell in row if cell]
                if headers:
                    return f"Table: {' | '.join(headers[:5])}"  # First 5 headers
            return None
        except Exception:
            return None

    async def _detect_tables_by_lines(self, page) -> List[Tuple[float, float, float, float]]:
        """Detect tables by analyzing horizontal/vertical lines"""
        import fitz

        tables = []

        try:
            # Get all paths (lines, rectangles)
            paths = page.get_drawings()

            # Find horizontal lines
            h_lines = []
            v_lines = []

            for path in paths:
                rect = path.get("rect", fitz.Rect())
                if rect.width > rect.height * 10:  # Horizontal
                    h_lines.append(rect)
                elif rect.height > rect.width * 10:  # Vertical
                    v_lines.append(rect)

            # If enough lines, look for grid patterns
            if len(h_lines) >= 2 and len(v_lines) >= 2:
                # Simple clustering: find bounding box of line groups
                all_lines = h_lines + v_lines
                if all_lines:
                    x0 = min(r.x0 for r in all_lines)
                    y0 = min(r.y0 for r in all_lines)
                    x1 = max(r.x1 for r in all_lines)
                    y1 = max(r.y1 for r in all_lines)

                    # Add some padding
                    padding = 5
                    tables.append((x0 - padding, y0 - padding, x1 + padding, y1 + padding))

        except Exception as e:
            logger.debug(f"Line-based table detection failed: {e}")

        return tables

    def _cluster_drawings(
        self,
        drawings: list,
        page,
        distance_threshold: float = 50,
    ) -> List[Tuple[float, float, float, float]]:
        """Cluster nearby drawings into diagram regions"""
        import fitz

        if not drawings:
            return []

        # Get bounding boxes of all drawings
        rects = []
        for d in drawings:
            rect = d.get("rect")
            if rect:
                rects.append(fitz.Rect(rect))

        if not rects:
            return []

        # Simple clustering: merge overlapping/nearby rectangles
        clusters = []
        used = set()

        for i, rect1 in enumerate(rects):
            if i in used:
                continue

            # Start new cluster
            cluster_rect = fitz.Rect(rect1)
            used.add(i)

            # Find all nearby rectangles
            changed = True
            while changed:
                changed = False
                expanded = cluster_rect + (-distance_threshold, -distance_threshold,
                                            distance_threshold, distance_threshold)

                for j, rect2 in enumerate(rects):
                    if j in used:
                        continue

                    if expanded.intersects(rect2):
                        cluster_rect = cluster_rect | rect2
                        used.add(j)
                        changed = True

            # Only keep significant clusters (not tiny shapes)
            if cluster_rect.width > 100 and cluster_rect.height > 100:
                clusters.append(tuple(cluster_rect))

        return clusters

    def _rect_contains(
        self,
        outer: Tuple[float, float, float, float],
        inner,
    ) -> bool:
        """Check if outer bbox contains inner rect"""
        try:
            import fitz
            outer_rect = fitz.Rect(outer)
            inner_rect = fitz.Rect(inner) if not isinstance(inner, fitz.Rect) else inner
            return outer_rect.contains(inner_rect)
        except Exception:
            return False


# Global singleton instance
visual_extractor = VisualContentExtractor()
