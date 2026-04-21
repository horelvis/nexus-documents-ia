"""
MCP Google Drive Server Entry Point.

Supports two transport modes:
1. STDIO (default): For subprocess communication
2. HTTP/SSE: For network communication (default in Docker)

Additional endpoints beyond standard MCP:
- /oauth/authorize - Initiate OAuth2 flow
- /oauth/callback  - Handle OAuth2 callback
- /oauth/revoke    - Revoke OAuth tokens
- /oauth/status    - Check OAuth status

Usage:
    # STDIO mode
    python -m app.main

    # HTTP mode
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

    logger.info("Starting MCP Google Drive Server in STDIO mode")

    server = create_server()

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


async def run_http(host: str = "0.0.0.0", port: int = 8000):
    """Run MCP server in HTTP/SSE mode with OAuth endpoints."""
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.requests import Request
    from starlette.responses import JSONResponse, RedirectResponse
    from mcp.server.sse import SseServerTransport
    import uvicorn

    from .services.job_manager import job_manager
    from .services.sync_service import run_sync_job, run_index_pending_job
    from .services.oauth_service import oauth_service

    logger.info(f"Starting MCP Google Drive Server in HTTP mode on {host}:{port}")

    server = create_server()
    sse = SseServerTransport("/messages/")

    # =================================================================
    # MCP SSE endpoints
    # =================================================================

    async def handle_sse(request):
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await server.run(
                streams[0],
                streams[1],
                server.create_initialization_options(),
            )

    async def handle_messages(request):
        await sse.handle_post_message(
            request.scope, request.receive, request._send
        )

    # =================================================================
    # Health & Info
    # =================================================================

    async def health(request):
        return JSONResponse({
            "status": "healthy",
            "service": settings.service_name,
        })

    async def info(request):
        return JSONResponse({
            "name": "mcp-google-drive-server",
            "version": "1.0.0",
            "protocol": "MCP",
            "transport": "HTTP/SSE",
            "oauth_configured": bool(
                settings.google_oauth_client_id
                and settings.google_oauth_client_secret
            ),
            "tools": [
                "gdrive_list_connectors",
                "gdrive_list_files",
                "gdrive_search",
                "gdrive_download",
                "gdrive_get_metadata",
                "gdrive_get_folder_tree",
                "gdrive_create_folder",
                "gdrive_upload",
                "gdrive_move",
                "gdrive_delete",
            ],
        })

    # =================================================================
    # OAuth2 endpoints
    # =================================================================

    async def oauth_authorize(request: Request):
        """GET /oauth/authorize?connector_id=X → Redirect to Google."""
        connector_id = request.query_params.get("connector_id")

        if not connector_id:
            return JSONResponse(
                {"error": "connector_id is required"},
                status_code=400,
            )

        try:
            # If connector already has a google_email, use it as login_hint
            # to skip account selection on reconnect
            login_hint = None
            try:
                from uuid import UUID as _UUID
                from .core.config import load_connector_from_db
                config = await load_connector_from_db(_UUID(connector_id))
                if config and config.google_email:
                    login_hint = config.google_email
            except Exception:
                pass
            auth_url = oauth_service.generate_auth_url(connector_id, login_hint=login_hint)
            return RedirectResponse(url=auth_url)
        except Exception as e:
            logger.error(f"OAuth authorize failed: {e}")
            return JSONResponse(
                {"error": str(e)},
                status_code=500,
            )

    async def oauth_callback(request: Request):
        """GET /oauth/callback?code=X&state=Y → Exchange code, save tokens.

        Returns an HTML page that auto-closes the popup window after authorization.
        """
        from starlette.responses import HTMLResponse

        code = request.query_params.get("code")
        state = request.query_params.get("state")
        error = request.query_params.get("error")

        if error:
            html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Error de Autorización</title>
<style>body{{font-family:system-ui,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;background:#fafafa}}
.card{{background:#fff;border-radius:12px;padding:2rem;box-shadow:0 2px 8px rgba(0,0,0,.1);text-align:center;max-width:400px}}
.error{{color:#dc2626;font-size:1.2rem;margin-bottom:1rem}}
button{{background:#18181b;color:#fff;border:none;padding:.5rem 1.5rem;border-radius:6px;cursor:pointer;font-size:.9rem}}
button:hover{{background:#27272a}}</style></head>
<body><div class="card"><div class="error">✕ Error de autorización</div>
<p style="color:#666;margin-bottom:1.5rem">{error}</p>
<button onclick="window.close()">Cerrar</button></div></body></html>"""
            return HTMLResponse(html, status_code=400)

        if not code or not state:
            html = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Error</title>
<style>body{font-family:system-ui,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;background:#fafafa}
.card{background:#fff;border-radius:12px;padding:2rem;box-shadow:0 2px 8px rgba(0,0,0,.1);text-align:center;max-width:400px}
button{background:#18181b;color:#fff;border:none;padding:.5rem 1.5rem;border-radius:6px;cursor:pointer;font-size:.9rem}
button:hover{background:#27272a}</style></head>
<body><div class="card"><p style="color:#dc2626">Parámetros faltantes (code, state)</p>
<button onclick="window.close()">Cerrar</button></div></body></html>"""
            return HTMLResponse(html, status_code=400)

        try:
            result = await oauth_service.handle_callback(code, state)
            email = result.get("google_email", "")
            html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Autorización Exitosa</title>
<style>body{{font-family:system-ui,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;background:#fafafa}}
.card{{background:#fff;border-radius:12px;padding:2rem;box-shadow:0 2px 8px rgba(0,0,0,.1);text-align:center;max-width:400px}}
.success{{color:#16a34a;font-size:2rem;margin-bottom:.5rem}}</style></head>
<body><div class="card"><div class="success">✓</div>
<h2 style="margin:0 0 .5rem">Autorización exitosa</h2>
<p style="color:#666">{email}</p>
<p style="color:#999;font-size:.85rem">Esta ventana se cerrará automáticamente...</p></div>
<script>
if(window.opener){{window.opener.postMessage({{type:'oauth-success',email:'{email}'}},'*')}}
setTimeout(function(){{try{{window.close()}}catch(e){{}}}},1500)
</script></body></html>"""
            return HTMLResponse(html)
        except Exception as e:
            logger.error(f"OAuth callback failed: {e}")
            html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Error</title>
<style>body{{font-family:system-ui,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;background:#fafafa}}
.card{{background:#fff;border-radius:12px;padding:2rem;box-shadow:0 2px 8px rgba(0,0,0,.1);text-align:center;max-width:400px}}
button{{background:#18181b;color:#fff;border:none;padding:.5rem 1.5rem;border-radius:6px;cursor:pointer;font-size:.9rem}}
button:hover{{background:#27272a}}</style></head>
<body><div class="card"><div style="color:#dc2626;font-size:1.2rem;margin-bottom:1rem">✕ Error</div>
<p style="color:#666;margin-bottom:1.5rem">{str(e)}</p>
<button onclick="window.close()">Cerrar</button></div></body></html>"""
            return HTMLResponse(html, status_code=500)

    async def oauth_revoke(request: Request):
        """POST /oauth/revoke — Revoke OAuth authorization."""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

        connector_id = body.get("connector_id")

        if not connector_id:
            return JSONResponse(
                {"error": "connector_id is required"},
                status_code=400,
            )

        try:
            from uuid import UUID
            success = await oauth_service.revoke_token(UUID(connector_id))
            return JSONResponse({
                "success": success,
                "connector_id": connector_id,
            })
        except Exception as e:
            logger.error(f"OAuth revoke failed: {e}")
            return JSONResponse(
                {"success": False, "error": str(e)},
                status_code=500,
            )

    async def oauth_status(request: Request):
        """GET /oauth/status?connector_id=X → Check OAuth status."""
        connector_id = request.query_params.get("connector_id")

        if not connector_id:
            return JSONResponse(
                {"error": "connector_id is required"},
                status_code=400,
            )

        try:
            from uuid import UUID
            status = await oauth_service.get_oauth_status(UUID(connector_id))
            return JSONResponse(status)
        except Exception as e:
            logger.error(f"OAuth status check failed: {e}")
            return JSONResponse(
                {"error": str(e)},
                status_code=500,
            )

    # =================================================================
    # Folder listing endpoint
    # =================================================================

    async def list_folders(request: Request):
        """GET /folders?connector_id=X&parent_id=root → List Drive folders."""
        connector_id = request.query_params.get("connector_id")
        parent_id = request.query_params.get("parent_id", "root")

        if not connector_id:
            return JSONResponse(
                {"error": "connector_id is required"},
                status_code=400,
            )

        try:
            from uuid import UUID
            from .core.config import get_connector

            config = await get_connector(UUID(connector_id))
            if not config or not config.is_authenticated:
                return JSONResponse(
                    {"error": "Not authorized. Complete OAuth first."},
                    status_code=401,
                )

            access_token = await oauth_service.ensure_fresh_token(config)

            # Direct Drive API call to list only folders
            import httpx as _httpx
            async with _httpx.AsyncClient(
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30.0,
            ) as client:
                query = (
                    f"'{parent_id}' in parents"
                    " and mimeType='application/vnd.google-apps.folder'"
                    " and trashed=false"
                )
                resp = await client.get(
                    "https://www.googleapis.com/drive/v3/files",
                    params={
                        "q": query,
                        "fields": "files(id,name)",
                        "orderBy": "name",
                        "pageSize": 200,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            folders = [
                {"id": f["id"], "name": f["name"]}
                for f in data.get("files", [])
            ]
            return JSONResponse(folders)

        except Exception as e:
            logger.error(f"List folders failed: {e}")
            return JSONResponse(
                {"error": str(e)},
                status_code=500,
            )

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

    # =================================================================
    # Starlette App
    # =================================================================

    app = Starlette(
        debug=settings.debug,
        routes=[
            # Standard MCP endpoints
            Route("/health", health, methods=["GET"]),
            Route("/info", info, methods=["GET"]),
            Route("/sse", handle_sse, methods=["GET"]),
            Route("/messages/", handle_messages, methods=["POST"]),
            # OAuth2 endpoints
            Route("/oauth/authorize", oauth_authorize, methods=["GET"]),
            Route("/oauth/callback", oauth_callback, methods=["GET"]),
            Route("/oauth/revoke", oauth_revoke, methods=["POST"]),
            Route("/oauth/status", oauth_status, methods=["GET"]),
            # Folder listing
            Route("/folders", list_folders, methods=["GET"]),
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
        description="MCP Google Drive Server - Document management for Google Drive"
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

    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()
    use_http = args.http or transport == "http"

    if use_http:
        asyncio.run(run_http(args.host, args.port))
    else:
        asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
