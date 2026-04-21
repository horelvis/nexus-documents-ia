"""
Storage Service — REST API for file storage via MinIO (S3-compatible).

Replaces mcp-storage-server. No MCP protocol — pure REST for
service-to-service file operations.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.services.minio_service import minio_storage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting Storage Service on port {settings.service_port}...")
    await minio_storage.initialize()
    yield
    logger.info("Shutting down Storage Service...")


app = FastAPI(title="Storage Service", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "storage-service", "version": "1.0.0"}


@app.post("/files/{path:path}")
async def upload_file(path: str, request: Request):
    """Upload file bytes to MinIO."""
    content = await request.body()
    if not content:
        raise HTTPException(400, "Empty body")

    object_name = path
    content_type = request.headers.get("content-type", "application/octet-stream")

    result = await minio_storage.upload(object_name, content, content_type)
    return JSONResponse(result)


@app.get("/files/{path:path}")
async def download_file(path: str):
    """Download file bytes from MinIO."""
    object_name = path
    content = await minio_storage.download(object_name)
    if content is None:
        raise HTTPException(404, "File not found")
    return Response(content=content, media_type="application/octet-stream")


@app.delete("/files/{path:path}")
async def delete_file(path: str):
    """Delete file from MinIO."""
    object_name = path
    success = await minio_storage.delete(object_name)
    if not success:
        raise HTTPException(404, "File not found")
    return {"deleted": True}


@app.head("/files/{path:path}")
async def file_exists(path: str):
    """Check if file exists in MinIO."""
    object_name = path
    exists = await minio_storage.exists(object_name)
    if not exists:
        raise HTTPException(404)
    return Response(status_code=200)
