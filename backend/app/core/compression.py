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

    def __init__(self, app: Callable, compression_level: int = 6):
        self.app = app
        self.compression_level = compression_level

    async def __call__(self, scope, receive, send):
        """ASGI middleware implementation"""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Intercept the send callable to compress responses
        original_send = send

        async def compressed_send(message):
            if message["type"] == "http.response.start":
                # Check if client accepts gzip compression
                headers = dict(message.get("headers", []))
                accept_encoding = None

                for key, value in headers.items():
                    if key == b"accept-encoding":
                        accept_encoding = value.decode("utf-8").lower()
                        break

                # Add compression header if client supports it
                if accept_encoding and "gzip" in accept_encoding:
                    message["headers"] = message.get("headers", []) + [
                        [b"content-encoding", b"gzip"]
                    ]

            elif message["type"] == "http.response.body":
                # Compress the response body if it's not empty
                body = message.get("body", b"")
                if body and len(body) > 1024:  # Only compress if body is > 1KB
                    try:
                        compressed_body = gzip.compress(
                            body,
                            compresslevel=self.compression_level
                        )

                        # Only use compressed version if it's actually smaller
                        if len(compressed_body) < len(body):
                            message["body"] = compressed_body
                            # Update Content-Length header to match compressed size
                            message["headers"] = message.get("headers", [])
                            # Remove existing content-length header
                            message["headers"] = [
                                [k, v] for k, v in message["headers"]
                                if k != b"content-length"
                            ]
                            # Add new content-length header
                            message["headers"].append([b"content-length", str(len(compressed_body)).encode("utf-8")])
                            logger.debug(f"Compressed response from {len(body)} to {len(compressed_body)} bytes")
                        else:
                            logger.debug(f"Compression not beneficial, keeping original size: {len(body)} bytes")

                    except Exception as e:
                        logger.warning(f"Compression failed: {str(e)}, sending uncompressed response")

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