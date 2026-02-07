"""
SSE Proxy Helper — eliminates duplicate streaming boilerplate.

All three SSE streaming endpoints (query/stream, verified/generate/stream,
predictive/analyze/stream) share the same httpx → SSE → StreamingResponse
pattern. This module extracts that pattern into a single function.
"""

import asyncio
import logging
from typing import AsyncGenerator

import httpx
from fastapi.responses import StreamingResponse

from app.core.config import settings

logger = logging.getLogger(__name__)


async def proxy_sse_stream(
    target_url: str,
    body: dict,
    timeout: float = 300.0,
    log_prefix: str = "SSE",
) -> StreamingResponse:
    """Proxy an SSE stream from Emma Agent Service to the client.

    Args:
        target_url: Full URL of the upstream SSE endpoint.
        body: JSON body to POST to the upstream endpoint.
        timeout: Total request timeout in seconds.
        log_prefix: Prefix for log messages (e.g. "Emma stream", "Verified stream").

    Returns:
        FastAPI StreamingResponse with proper SSE headers.
    """

    async def _stream() -> AsyncGenerator[bytes, None]:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=10.0),
            http2=False,
        ) as client:
            try:
                async with client.stream(
                    "POST",
                    target_url,
                    json=body,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "text/event-stream",
                        "X-API-Key": settings.MICROSERVICES_API_KEY or "",
                    },
                ) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        logger.error(f"❌ {log_prefix} error: {response.status_code} - {error_text}")
                        yield f"event: error\ndata: {{\"error\": \"Service error: {response.status_code}\"}}\n\n".encode()
                        return

                    async for line in response.aiter_lines():
                        if line:
                            yield (line + "\n").encode()
                        else:
                            yield b"\n"
                        await asyncio.sleep(0)

            except httpx.TimeoutException:
                logger.error(f"⏱️ {log_prefix} timeout after {timeout}s")
                yield f"event: error\ndata: {{\"error\": \"Service timeout\"}}\n\n".encode()
            except Exception as e:
                logger.error(f"❌ {log_prefix} proxy error: {e}")
                yield f"event: error\ndata: {{\"error\": \"{str(e)}\"}}\n\n".encode()

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
