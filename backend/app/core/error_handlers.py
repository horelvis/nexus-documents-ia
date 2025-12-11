"""
Global error handlers for the application
"""
import logging
from typing import Any, Dict

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.config import settings

logger = logging.getLogger(__name__)


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle validation errors"""
    logger.error(f"🚫 Validation error on {request.url.path}: {str(exc)}")
    logger.error(f"🔍 Validation errors: {exc.errors()}")

    if settings.DEBUG:
        logger.error(f"🔍 Request method: {request.method}")
        logger.error(f"🔍 Request headers: {dict(request.headers)}")
        # Try to read body, but it may already be consumed for multipart/form-data requests
        try:
            content_type = request.headers.get("content-type", "")
            if "multipart/form-data" in content_type:
                logger.error(f"🔍 Request body: [multipart/form-data - stream already consumed]")
            else:
                body = await request.body()
                logger.error(f"🔍 Request body: {body[:1000] if body else 'N/A'}")
        except RuntimeError as e:
            if "Stream consumed" in str(e):
                logger.error(f"🔍 Request body: [stream already consumed - likely file upload]")
            else:
                logger.error(f"🔍 Request body: [error reading body: {e}]")

    return JSONResponse(
        status_code=422,
        content={
            "detail": exc.errors(),
            "path": str(request.url.path),
            "debug_info": "Validation error - check logs for details" if settings.DEBUG else None
        }
    )


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle all unhandled exceptions"""
    logger.exception(f"💥 Unhandled exception on {request.url.path}: {str(exc)}")

    # In DEBUG mode, show more information
    if settings.DEBUG:
        logger.error(f"🔍 Request method: {request.method}")
        logger.error(f"🔍 Request headers: {dict(request.headers)}")
        logger.error(f"🔍 Exception type: {type(exc)}")
        import traceback
        logger.error(f"📚 Full traceback: {traceback.format_exc()}")

    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "path": str(request.url.path),
            "debug_info": str(exc) if settings.DEBUG else None
        }
    )


def register_error_handlers(app) -> None:
    """Register all error handlers with the FastAPI app"""
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, global_exception_handler)