"""
Enhanced OCR Service

Provides high-quality OCR for scanned PDFs and images when Apache Tika
produces low-quality results.

Uses:
- EasyOCR (primary): GPU-accelerated, multilingual, better handwriting support
- Tesseract (fallback): CPU-based, more languages, fallback for edge cases

This service is triggered when document_intelligence detects:
- Quality < 60%
- OCR errors
- Garbled text
- Very low text-to-page ratio (scanned PDFs)
"""

import asyncio
import io
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# Lazy imports for GPU efficiency
_easyocr_reader = None
_tesseract_available = None


class OCREngine(str, Enum):
    """OCR engine used for extraction"""
    EASYOCR = "easyocr"
    TESSERACT = "tesseract"
    HYBRID = "hybrid"  # EasyOCR + Tesseract post-processing


@dataclass
class OCRResult:
    """Result of OCR extraction"""
    text: str
    confidence: float  # 0.0 - 1.0
    engine: OCREngine
    languages: List[str]
    page_count: int
    processing_time_ms: float
    warnings: List[str] = field(default_factory=list)
    page_confidences: List[float] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return bool(self.text.strip()) and self.confidence > 0.3


def _get_easyocr_reader(languages: List[str]):
    """Get or create EasyOCR reader (lazy initialization)"""
    global _easyocr_reader

    if _easyocr_reader is None:
        try:
            import easyocr
            # GPU if available, CPU fallback
            _easyocr_reader = easyocr.Reader(
                languages,
                gpu=True,  # Will fall back to CPU if no GPU
                verbose=False,
            )
            logger.info(f"EasyOCR initialized with languages: {languages}")
        except Exception as e:
            logger.error(f"Failed to initialize EasyOCR: {e}")
            raise

    return _easyocr_reader


def _is_tesseract_available() -> bool:
    """Check if Tesseract is available"""
    global _tesseract_available

    if _tesseract_available is None:
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            _tesseract_available = True
        except Exception:
            _tesseract_available = False

    return _tesseract_available


def _convert_pdf_to_images(pdf_bytes: bytes, dpi: int = 300) -> List[Image.Image]:
    """Convert PDF pages to PIL Images"""
    try:
        from pdf2image import convert_from_bytes

        images = convert_from_bytes(
            pdf_bytes,
            dpi=dpi,
            fmt='RGB',
            thread_count=4,
        )
        return images
    except Exception as e:
        logger.error(f"Failed to convert PDF to images: {e}")
        raise


def _preprocess_image(image: Image.Image) -> Image.Image:
    """
    Preprocess image for better OCR results.

    Applies:
    - Grayscale conversion
    - Contrast enhancement
    - Noise reduction (for scanned documents)
    """
    import numpy as np
    from PIL import ImageEnhance, ImageFilter

    # Convert to grayscale if RGB
    if image.mode == 'RGB':
        image = image.convert('L')

    # Enhance contrast
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(1.5)

    # Slight sharpening
    image = image.filter(ImageFilter.SHARPEN)

    # Convert back to RGB for EasyOCR
    return image.convert('RGB')


class OCRService:
    """
    Enhanced OCR service for scanned documents.

    Usage:
        ocr_service = OCRService()

        # From PDF bytes
        result = await ocr_service.extract_from_pdf(pdf_bytes)

        # From image bytes
        result = await ocr_service.extract_from_image(image_bytes)

        # Check quality
        if result.confidence > 0.6:
            print(result.text)
    """

    # Language mapping for EasyOCR
    LANGUAGE_MAP = {
        "es": "es",
        "en": "en",
        "ca": "ca",  # Catalan
        "pt": "pt",
        "fr": "fr",
        "de": "de",
        "it": "it",
    }

    def __init__(
        self,
        default_languages: List[str] = None,
        dpi: int = 300,
        preprocess: bool = True,
        min_confidence: float = 0.3,
    ):
        """
        Initialize OCR service.

        Args:
            default_languages: Default OCR languages (e.g., ["es", "en"])
            dpi: DPI for PDF to image conversion
            preprocess: Whether to preprocess images for better OCR
            min_confidence: Minimum confidence threshold
        """
        self.default_languages = default_languages or ["es", "en"]
        self.dpi = dpi
        self.preprocess = preprocess
        self.min_confidence = min_confidence
        self._reader = None

    async def extract_from_pdf(
        self,
        pdf_bytes: bytes,
        languages: Optional[List[str]] = None,
        use_hybrid: bool = False,
    ) -> OCRResult:
        """
        Extract text from PDF using OCR.

        Args:
            pdf_bytes: PDF file content
            languages: OCR languages (defaults to instance default)
            use_hybrid: Use both EasyOCR and Tesseract for best results

        Returns:
            OCRResult with extracted text and confidence
        """
        start_time = time.time()
        warnings = []

        langs = languages or self.default_languages

        try:
            # Convert PDF to images
            images = await asyncio.to_thread(
                _convert_pdf_to_images, pdf_bytes, self.dpi
            )

            if not images:
                return OCRResult(
                    text="",
                    confidence=0.0,
                    engine=OCREngine.EASYOCR,
                    languages=langs,
                    page_count=0,
                    processing_time_ms=(time.time() - start_time) * 1000,
                    warnings=["No pages could be converted from PDF"],
                )

            # Process each page
            page_texts = []
            page_confidences = []

            for i, image in enumerate(images):
                # Preprocess if enabled
                if self.preprocess:
                    image = await asyncio.to_thread(_preprocess_image, image)

                # Extract text from page
                if use_hybrid and _is_tesseract_available():
                    page_text, page_conf = await self._extract_hybrid(image, langs)
                    engine = OCREngine.HYBRID
                else:
                    page_text, page_conf = await self._extract_easyocr(image, langs)
                    engine = OCREngine.EASYOCR

                page_texts.append(page_text)
                page_confidences.append(page_conf)

                logger.debug(f"Page {i+1}/{len(images)}: {len(page_text)} chars, confidence={page_conf:.2f}")

            # Combine pages
            full_text = "\n\n".join(page_texts)
            avg_confidence = sum(page_confidences) / len(page_confidences) if page_confidences else 0.0

            processing_time = (time.time() - start_time) * 1000

            logger.info(
                f"OCR completed: {len(full_text)} chars, {len(images)} pages, "
                f"confidence={avg_confidence:.2f}, time={processing_time:.0f}ms"
            )

            return OCRResult(
                text=full_text,
                confidence=avg_confidence,
                engine=engine,
                languages=langs,
                page_count=len(images),
                processing_time_ms=processing_time,
                warnings=warnings,
                page_confidences=page_confidences,
            )

        except Exception as e:
            logger.error(f"OCR extraction failed: {e}")
            return OCRResult(
                text="",
                confidence=0.0,
                engine=OCREngine.EASYOCR,
                languages=langs,
                page_count=0,
                processing_time_ms=(time.time() - start_time) * 1000,
                warnings=[f"OCR extraction failed: {str(e)}"],
            )

    async def extract_from_image(
        self,
        image_bytes: bytes,
        languages: Optional[List[str]] = None,
    ) -> OCRResult:
        """
        Extract text from a single image.

        Args:
            image_bytes: Image file content (PNG, JPEG, etc.)
            languages: OCR languages

        Returns:
            OCRResult with extracted text
        """
        start_time = time.time()
        langs = languages or self.default_languages

        try:
            # Load image
            image = Image.open(io.BytesIO(image_bytes))

            if self.preprocess:
                image = await asyncio.to_thread(_preprocess_image, image)

            # Extract text
            text, confidence = await self._extract_easyocr(image, langs)

            return OCRResult(
                text=text,
                confidence=confidence,
                engine=OCREngine.EASYOCR,
                languages=langs,
                page_count=1,
                processing_time_ms=(time.time() - start_time) * 1000,
                page_confidences=[confidence],
            )

        except Exception as e:
            logger.error(f"Image OCR failed: {e}")
            return OCRResult(
                text="",
                confidence=0.0,
                engine=OCREngine.EASYOCR,
                languages=langs,
                page_count=1,
                processing_time_ms=(time.time() - start_time) * 1000,
                warnings=[f"Image OCR failed: {str(e)}"],
            )

    async def _extract_easyocr(
        self,
        image: Image.Image,
        languages: List[str],
    ) -> Tuple[str, float]:
        """Extract text using EasyOCR"""
        try:
            # Map languages to EasyOCR format
            easyocr_langs = [
                self.LANGUAGE_MAP.get(lang, lang)
                for lang in languages
            ]

            reader = _get_easyocr_reader(easyocr_langs)

            # Convert PIL to numpy array
            image_np = np.array(image)

            # Run OCR
            results = await asyncio.to_thread(
                reader.readtext,
                image_np,
                detail=1,  # Get confidence scores
                paragraph=True,  # Group into paragraphs
            )

            if not results:
                return "", 0.0

            # Extract text and calculate confidence
            texts = []
            confidences = []

            for result in results:
                if len(result) >= 2:
                    bbox, text = result[0], result[1]
                    conf = result[2] if len(result) > 2 else 0.8
                    texts.append(text)
                    confidences.append(conf)

            full_text = "\n".join(texts)
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

            return full_text, avg_confidence

        except Exception as e:
            logger.error(f"EasyOCR extraction failed: {e}")

            # Fallback to Tesseract if available
            if _is_tesseract_available():
                logger.info("Falling back to Tesseract OCR")
                return await self._extract_tesseract(image, languages)

            raise

    async def _extract_tesseract(
        self,
        image: Image.Image,
        languages: List[str],
    ) -> Tuple[str, float]:
        """Extract text using Tesseract (fallback)"""
        try:
            import pytesseract

            # Map to Tesseract language codes
            tess_langs = "+".join(languages)

            # Get text with confidence data
            data = await asyncio.to_thread(
                pytesseract.image_to_data,
                image,
                lang=tess_langs,
                output_type=pytesseract.Output.DICT,
            )

            # Extract text and confidence
            texts = []
            confidences = []

            for i, conf in enumerate(data['conf']):
                if conf > 0:  # Valid confidence
                    text = data['text'][i]
                    if text.strip():
                        texts.append(text)
                        confidences.append(conf / 100.0)  # Normalize to 0-1

            full_text = " ".join(texts)
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

            return full_text, avg_confidence

        except Exception as e:
            logger.error(f"Tesseract extraction failed: {e}")
            return "", 0.0

    async def _extract_hybrid(
        self,
        image: Image.Image,
        languages: List[str],
    ) -> Tuple[str, float]:
        """
        Hybrid extraction: EasyOCR primary + Tesseract for validation.

        Uses EasyOCR for main extraction, then validates with Tesseract
        for characters that EasyOCR might struggle with (numbers, special chars).
        """
        # Get EasyOCR result
        easyocr_text, easyocr_conf = await self._extract_easyocr(image, languages)

        # Get Tesseract result
        if _is_tesseract_available():
            tess_text, tess_conf = await self._extract_tesseract(image, languages)

            # Use EasyOCR text but boost confidence if Tesseract agrees
            if self._texts_similar(easyocr_text, tess_text):
                return easyocr_text, min(1.0, (easyocr_conf + tess_conf) / 2 + 0.1)

            # If very different, use the one with higher confidence
            if tess_conf > easyocr_conf + 0.2:
                return tess_text, tess_conf

        return easyocr_text, easyocr_conf

    def _texts_similar(self, text1: str, text2: str, threshold: float = 0.7) -> bool:
        """Check if two texts are similar (simple ratio)"""
        if not text1 or not text2:
            return False

        # Simple character overlap ratio
        set1 = set(text1.lower())
        set2 = set(text2.lower())

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        return (intersection / union) >= threshold if union > 0 else False


# Global instance with default settings
ocr_service = OCRService()
