"""GLM-OCR extraction provider — VLM-based document understanding.

Uses GLM-OCR (0.9B params) via OpenAI-compatible API (SGLang/Ollama)
for scanned PDFs, images, and low-quality documents. Outputs Markdown.
"""
import base64
import logging
import mimetypes
from typing import Optional

import httpx
from langdetect import detect

from app.providers.base import ExtractionProvider, ExtractionResult

logger = logging.getLogger(__name__)

# Formats GLM-OCR handles well (image-based understanding)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".gif", ".webp"}
PDF_EXTENSION = ".pdf"


class GlmOcrProvider(ExtractionProvider):
    """Extract text from images/scanned PDFs via GLM-OCR VLM.

    GLM-OCR is served as an OpenAI-compatible vision model endpoint.
    It accepts images and returns structured text/markdown.
    """

    name = "glm-ocr"

    def __init__(self, base_url: str, model: str = "zai-org/GLM-OCR", timeout: int = 120):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    async def extract(self, file_bytes: bytes, filename: str, **options) -> ExtractionResult:
        ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""

        # For PDFs, we need to convert pages to images first
        # For now, send as base64 image to the vision endpoint
        if ext == PDF_EXTENSION:
            return await self._extract_pdf(file_bytes, filename)
        else:
            return await self._extract_image(file_bytes, filename, ext)

    async def _extract_image(self, file_bytes: bytes, filename: str, ext: str = "") -> ExtractionResult:
        """Extract text from a single image via GLM-OCR vision API."""
        mime = mimetypes.guess_type(filename)[0] or "image/png"
        b64 = base64.b64encode(file_bytes).decode("utf-8")
        data_url = f"data:{mime};base64,{b64}"

        text = await self._call_vision_api(data_url, "Text Recognition:")

        language = ""
        if text and len(text) > 20:
            try:
                language = detect(text)
            except Exception:
                pass

        return ExtractionResult(
            text=text,
            language=language,
            metadata={
                "extraction_provider": "glm-ocr",
                "characters": len(text),
                "model": self._model,
            },
        )

    async def _extract_pdf(self, file_bytes: bytes, filename: str) -> ExtractionResult:
        """Extract text from PDF by sending pages as images.

        For multi-page PDFs, uses pdf2image to render pages then OCRs each.
        Falls back to sending the raw PDF bytes if pdf2image is not available.
        """
        pages_text = []

        try:
            from pdf2image import convert_from_bytes
            images = convert_from_bytes(file_bytes, dpi=150, fmt="png")

            for i, img in enumerate(images):
                import io
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                data_url = f"data:image/png;base64,{b64}"

                page_text = await self._call_vision_api(data_url, "Text Recognition:")
                if page_text:
                    pages_text.append(f"<!-- Page {i+1} -->\n{page_text}")

        except ImportError:
            logger.warning("pdf2image not installed, sending PDF as single image")
            # Fallback: send first page hint
            b64 = base64.b64encode(file_bytes).decode("utf-8")
            data_url = f"data:application/pdf;base64,{b64}"
            text = await self._call_vision_api(data_url, "Text Recognition:")
            pages_text = [text] if text else []

        full_text = "\n\n".join(pages_text)
        language = ""
        if full_text and len(full_text) > 20:
            try:
                language = detect(full_text)
            except Exception:
                pass

        return ExtractionResult(
            text=full_text,
            language=language,
            metadata={
                "extraction_provider": "glm-ocr",
                "characters": len(full_text),
                "pages": len(pages_text),
                "model": self._model,
            },
        )

    async def _call_vision_api(self, image_data_url: str, prompt: str) -> str:
        """Call OpenAI-compatible vision chat/completions endpoint."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    json={
                        "model": self._model,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "image_url", "image_url": {"url": image_data_url}},
                                    {"type": "text", "text": prompt},
                                ],
                            }
                        ],
                        "max_tokens": 8192,
                        "temperature": 0.1,
                    },
                )
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.warning(f"GLM-OCR API call failed: {e}")
            return ""

    async def extract_from_url(self, url: str, filename: str, **options) -> ExtractionResult:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return await self.extract(resp.content, filename, **options)

    async def is_available(self) -> bool:
        if not self._model:
            return False
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self._base_url}/models")
                return resp.status_code == 200
        except Exception:
            return False
