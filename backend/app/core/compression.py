"""
Response compression middleware for improved performance
"""
import gzip
import logging
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse, HTMLResponse, PlainTextResponse

logger = logging.getLogger(__name__)


class CompressionMiddleware:
    """Middleware for compressing HTTP responses"""

    def __init__(self, app: Callable, compression_level: int = 6, min_size: int = 1024):
        self.app = app
        self.compression_level = compression_level
        self.min_size = min_size

    async def __call__(self, scope, receive, send):
        """ASGI middleware implementation"""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_headers = dict(scope.get("headers") or [])
        accepts_gzip = False
        for key, value in request_headers.items():
            if key == b"accept-encoding" and b"gzip" in value.lower():
                accepts_gzip = True
                break

        # Skip compression for streaming/document endpoints explicitly
        request_path = scope.get("path", "") or ""
        if not accepts_gzip or "/stream" in request_path:
            await self.app(scope, receive, send)
            return

        original_send = send
        response_start_message = None
        response_headers = []
        headers_sent = False
        can_compress = True

        async def compressed_send(message):
            nonlocal response_start_message, response_headers, headers_sent, can_compress

            if message["type"] == "http.response.start":
                response_start_message = message.copy()
                response_headers = list(message.get("headers", []))

                # Inspect content type to skip non-compressible responses (PDF, binaries, SSE, etc.)
                content_type = ""
                for key, value in response_headers:
                    if key == b"content-type":
                        content_type = value.decode("latin-1").lower()
                        break

                nonlocal_can_compress = can_compress
                if any(
                    media in content_type
                    for media in [
                        "application/pdf",
                        "application/zip",
                        "application/gzip",
                        "application/octet-stream",
                        "image/",
                        "audio/",
                        "video/",
                        "text/event-stream",
                    ]
                ):
                    nonlocal_can_compress = False

                can_compress = nonlocal_can_compress
                return

            if message["type"] == "http.response.body":
                body = message.get("body", b"")
                more_body = message.get("more_body", False)

                # If the response is streaming (multiple body chunks), skip compression
                if more_body:
                    can_compress = False

                if not headers_sent:
                    start_message = response_start_message or {"type": "http.response.start", "headers": []}
                    adjusted_headers = response_headers

                    compressed_body = body
                    did_compress = False

                    if (
                        can_compress
                        and body
                        and not more_body
                        and len(body) >= self.min_size
                    ):
                        try:
                            candidate = gzip.compress(body, compresslevel=self.compression_level)
                            if len(candidate) < len(body):
                                compressed_body = candidate
                                did_compress = True
                            else:
                                can_compress = False
                        except Exception as e:
                            logger.warning(f"Compression failed: {str(e)}, sending uncompressed response")
                            can_compress = False

                    if did_compress:
                        adjusted_headers = [
                            [k, v]
                            for k, v in response_headers
                            if k not in (b"content-length", b"content-encoding")
                        ]
                        adjusted_headers.append([b"content-encoding", b"gzip"])
                        adjusted_headers.append([b"content-length", str(len(compressed_body)).encode("utf-8")])
                        message["body"] = compressed_body
                    else:
                        # If compression not applied, ensure original body is used
                        message["body"] = body

                    start_message["headers"] = adjusted_headers
                    response_start_message = None
                    await original_send(start_message)
                    headers_sent = True

                    if did_compress:
                        await original_send(message)
                        return

                # For subsequent body messages or when compression is not applied
                await original_send(message)
            else:
                await original_send(message)

        await self.app(scope, receive, compressed_send)


def should_compress_response(response: Response, min_size: int = 1024) -> bool:
    """
    Determine if a response should be compressed based on various factors.
    """
    # Don't compress small responses
    if hasattr(response, 'body') and len(response.body) < min_size:
        return False

    # Don't compress already compressed content
    content_type = response.headers.get("content-type", "").lower()
    compressed_types = [
        "image/", "video/", "audio/", "application/zip",
        "application/gzip", "application/x-compressed"
    ]

    for compressed_type in compressed_types:
        if compressed_type in content_type:
            return False

    # Don't compress streaming responses
    if hasattr(response, 'media_type') and "stream" in response.media_type:
        return False

    return True


def compress_response_data(data: bytes, compression_level: int = 6) -> bytes:
    """
    Compress response data using gzip.
    """
    try:
        compressed = gzip.compress(data, compresslevel=compression_level)

        # Only return compressed data if it's actually smaller
        if len(compressed) < len(data):
            return compressed
        else:
            logger.debug("Compression not beneficial, returning original data")
            return data

    except Exception as e:
        logger.warning(f"Compression failed: {str(e)}")
        return data


class CompressedJSONResponse(JSONResponse):
    """JSON response with automatic gzip compression"""

    def __init__(self, content, status_code: int = 200, headers=None, compression_level: int = 6):
        super().__init__(content, status_code, headers)

        # Compress the JSON content
        json_bytes = self.body
        if len(json_bytes) > 1024:  # Only compress larger responses
            compressed = compress_response_data(json_bytes, compression_level)
            if len(compressed) < len(json_bytes):
                self.body = compressed
                self.headers["content-encoding"] = "gzip"
                self.headers["content-length"] = str(len(compressed))
                logger.debug(f"Compressed JSON response from {len(json_bytes)} to {len(compressed)} bytes")


class CompressedHTMLResponse(HTMLResponse):
    """HTML response with automatic gzip compression"""

    def __init__(self, content, status_code: int = 200, headers=None, compression_level: int = 6):
        super().__init__(content, status_code, headers)

        # Compress the HTML content
        html_bytes = self.body
        if len(html_bytes) > 512:  # Compress even smaller HTML
            compressed = compress_response_data(html_bytes, compression_level)
            if len(compressed) < len(html_bytes):
                self.body = compressed
                self.headers["content-encoding"] = "gzip"
                self.headers["content-length"] = str(len(compressed))
                logger.debug(f"Compressed HTML response from {len(html_bytes)} to {len(compressed)} bytes")


class CompressedTextResponse(PlainTextResponse):
    """Text response with automatic gzip compression"""

    def __init__(self, content, status_code: int = 200, headers=None, compression_level: int = 6):
        super().__init__(content, status_code, headers)

        # Compress the text content
        text_bytes = self.body
        if len(text_bytes) > 1024:
            compressed = compress_response_data(text_bytes, compression_level)
            if len(compressed) < len(text_bytes):
                self.body = compressed
                self.headers["content-encoding"] = "gzip"
                self.headers["content-length"] = str(len(compressed))
                logger.debug(f"Compressed text response from {len(text_bytes)} to {len(compressed)} bytes")


def get_compressed_response(response_class, content, **kwargs):
    """
    Factory function to get appropriate compressed response based on content type.
    """
    compression_level = kwargs.pop('compression_level', 6)

    if response_class == JSONResponse:
        return CompressedJSONResponse(content, compression_level=compression_level, **kwargs)
    elif response_class == HTMLResponse:
        return CompressedHTMLResponse(content, compression_level=compression_level, **kwargs)
    elif response_class == PlainTextResponse:
        return CompressedTextResponse(content, compression_level=compression_level, **kwargs)
    else:
        # For other response types, return as-is
        return response_class(content, **kwargs)


# Compression utilities
def get_optimal_compression_level(content_size: int) -> int:
    """
    Get optimal compression level based on content size.
    Larger content benefits from higher compression levels.
    """
    if content_size < 1024:  # < 1KB
        return 1  # Fast compression
    elif content_size < 10240:  # < 10KB
        return 4  # Balanced
    elif content_size < 102400:  # < 100KB
        return 6  # Default
    else:  # > 100KB
        return 9  # Maximum compression


def estimate_compression_ratio(content_type: str) -> float:
    """
    Estimate compression ratio based on content type.
    """
    ratios = {
        "application/json": 0.3,  # JSON compresses very well
        "text/html": 0.4,         # HTML compresses well
        "text/plain": 0.5,        # Plain text compresses moderately
        "text/css": 0.6,          # CSS compresses moderately
        "application/javascript": 0.4,  # JS compresses well
        "text/xml": 0.5,          # XML compresses moderately
    }

    for content_pattern, ratio in ratios.items():
        if content_pattern in content_type:
            return ratio

    return 0.7  # Default ratio for unknown types
