"""
MCP Alfresco Server Entry Point.

Supports two transport modes:
1. STDIO (default): For subprocess communication
   - Run: python -m app.main

2. HTTP/SSE: For network communication
   - Run: python -m app.main --http
   - Or set: MCP_TRANSPORT=http

Usage:
    # STDIO mode (for MCP clients using subprocess)
    python -m app.main

    # HTTP mode (for network access)
    python -m app.main --http --port 8000

    # Or via environment
    MCP_TRANSPORT=http PORT=8000 python -m app.main
"""

import argparse
import asyncio
import logging
import os
import sys

from .server import create_server
from .core.config import settings, get_instances

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


async def run_stdio():
    """Run MCP server in STDIO mode."""
    from mcp.server.stdio import stdio_server

    logger.info("Starting MCP Alfresco Server in STDIO mode")

    server = create_server()

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


async def run_http(host: str = "0.0.0.0", port: int = 8000):
    """
    Run MCP server in HTTP/SSE mode.

    Uses Starlette for HTTP server with SSE transport.
    """
    from starlette.applications import Starlette
    from starlette.routing import Route, Mount
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from mcp.server.sse import SseServerTransport
    import uvicorn

    from .services.job_manager import job_manager
    from .services.sync_service import run_sync_job, run_index_pending_job

    logger.info(f"Starting MCP Alfresco Server in HTTP mode on {host}:{port}")

    server = create_server()
    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        """Handle SSE connections."""
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await server.run(
                streams[0],
                streams[1],
                server.create_initialization_options(),
            )

    async def handle_messages(request):
        """Handle SSE message endpoint."""
        await sse.handle_post_message(
            request.scope, request.receive, request._send
        )

    async def health(request):
        """Health check endpoint."""
        instances = get_instances()
        return JSONResponse({
            "status": "healthy",
            "service": settings.service_name,
            "instances": list(instances.keys()),
        })

    async def info(request):
        """Server info endpoint."""
        instances = get_instances()
        return JSONResponse({
            "name": "mcp-alfresco-server",
            "version": "1.0.0",
            "protocol": "MCP",
            "transport": "HTTP/SSE",
            "instances": [
                {
                    "name": inst.name,
                    "url": inst.url,
                    "default_site": inst.default_site_id,
                }
                for inst in instances.values()
            ],
            "tools": [
                "alfresco_search",
                "alfresco_download",
                "alfresco_upload",
                "alfresco_list",
                "alfresco_get_metadata",
                "alfresco_get_versions",
                "alfresco_move",
                "alfresco_copy",
                "alfresco_delete",
                "alfresco_update_metadata",
                "alfresco_create_folder",
                "alfresco_get_sites",
            ],
        })

    # =================================================================
    # Sync & Indexing HTTP endpoints
    # =================================================================

    async def handle_sync(request: Request):
        """POST /sync — Start a sync job."""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

        connector_id = body.get("connector_id")
        if not connector_id:
            return JSONResponse({"error": "connector_id is required"}, status_code=400)

        full_sync = body.get("full_sync", False)
        batch_size = body.get("batch_size", 10)

        job_id = await job_manager.start_job(
            job_type="sync",
            coro_func=run_sync_job,
            params={
                "connector_id": connector_id,
                "full_sync": full_sync,
                "batch_size": batch_size,
            },
        )

        return JSONResponse({
            "job_id": job_id,
            "status": "started",
            "message": "Sync job started",
        })

    async def handle_index_pending(request: Request):
        """POST /index-pending — Start an indexing job."""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

        connector_id = body.get("connector_id")
        if not connector_id:
            return JSONResponse({"error": "connector_id is required"}, status_code=400)

        batch_size = body.get("batch_size", 10)
        max_documents = body.get("max_documents")

        job_id = await job_manager.start_job(
            job_type="index-pending",
            coro_func=run_index_pending_job,
            params={
                "connector_id": connector_id,
                "batch_size": batch_size,
                "max_documents": max_documents,
            },
        )

        return JSONResponse({
            "job_id": job_id,
            "status": "started",
            "message": "Indexing job started",
        })

    async def handle_get_job(request: Request):
        """GET /jobs/{job_id} — Get job status."""
        job_id = request.path_params["job_id"]
        job = job_manager.get_job(job_id)
        if not job:
            return JSONResponse({"error": "Job not found"}, status_code=404)

        return JSONResponse({
            "job_id": job.job_id,
            "job_type": job.job_type,
            "status": job.status.value,
            "progress": job.progress,
            "result": job.result,
            "error": job.error,
            "started_at": job.started_at.isoformat(),
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        })

    async def handle_list_jobs(request: Request):
        """GET /jobs — List all jobs."""
        job_type = request.query_params.get("type")
        jobs = job_manager.list_jobs(job_type=job_type)
        return JSONResponse({
            "jobs": [
                {
                    "job_id": j.job_id,
                    "job_type": j.job_type,
                    "status": j.status.value,
                    "progress": j.progress,
                    "started_at": j.started_at.isoformat(),
                    "completed_at": j.completed_at.isoformat() if j.completed_at else None,
                }
                for j in jobs
            ]
        })

    app = Starlette(
        debug=settings.debug,
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/info", info, methods=["GET"]),
            Route("/sse", handle_sse, methods=["GET"]),
            Route("/messages/", handle_messages, methods=["POST"]),
            # Sync & Indexing endpoints
            Route("/sync", handle_sync, methods=["POST"]),
            Route("/index-pending", handle_index_pending, methods=["POST"]),
            Route("/jobs/{job_id}", handle_get_job, methods=["GET"]),
            Route("/jobs", handle_list_jobs, methods=["GET"]),
        ],
    )

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="debug" if settings.debug else "info",
    )
    server_uvicorn = uvicorn.Server(config)
    await server_uvicorn.serve()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="MCP Alfresco Server - Document management for Alfresco 7.x"
    )
    parser.add_argument(
        "--http",
        action="store_true",
        help="Run in HTTP/SSE mode instead of STDIO",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("HOST", "0.0.0.0"),
        help="HTTP host (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PORT", "8000")),
        help="HTTP port (default: 8000)",
    )

    args = parser.parse_args()

    # Check environment for transport mode
    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()
    use_http = args.http or transport == "http"

    # Log configuration
    instances = get_instances()
    if instances:
        logger.info(f"Configured Alfresco instances: {list(instances.keys())}")
    else:
        logger.warning("No Alfresco instances configured!")

    # Run server
    if use_http:
        asyncio.run(run_http(args.host, args.port))
    else:
        asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
