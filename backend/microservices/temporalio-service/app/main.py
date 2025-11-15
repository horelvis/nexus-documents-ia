"""
Temporalio Microservice - Workflow Orchestration with Emma AI Integration
Provides durable workflow execution capabilities using Temporal.io + Emma AI
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import time

from app.core.config import settings
from app.core.security import verify_api_key
from app.core.temporalio_client import temporalio_client
from app.workers.worker_manager import worker_manager

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management"""
    logger.info("🚀 Starting Temporalio Workflow Service...")
    logger.info(f"🔧 Service Port: {settings.service_port}")
    logger.info(f"⏱️ Temporalio Host: {settings.temporalio_host}:{settings.temporalio_port}")
    logger.info(f"📋 Task Queue: {settings.temporalio_task_queue}")
    
    # Initialize Temporalio connection
    try:
        logger.info("🔄 Initializing Temporalio client...")
        await temporalio_client.initialize()
        logger.info("✅ Temporalio client initialized successfully")
        
        # Start workers
        logger.info("🏗️ Starting Temporalio workers...")
        await worker_manager.start()
        logger.info("✅ Temporalio workers started successfully")
        
    except Exception as e:
        logger.error(f"⚠️  Failed to initialize Temporalio: {e}")
        logger.warning("🚀 Starting service anyway for basic endpoint testing")
        # Don't raise - allow service to start for basic testing
    
    yield
    
    # Cleanup
    try:
        logger.info("🔄 Shutting down Temporalio workers...")
        await worker_manager.shutdown()
        await temporalio_client.close()
        logger.info("✅ Temporalio service shutdown complete")
    except Exception as e:
        logger.error(f"❌ Error during shutdown: {e}")


def create_app() -> FastAPI:
    """Create FastAPI application"""
    app = FastAPI(
        title="Temporalio Workflow Service",
        description="Durable workflow orchestration with Emma AI integration",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.debug else settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Add request timing middleware
    @app.middleware("http")
    async def add_process_time_header(request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        return response
    
    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Health check endpoint"""
        try:
            # Check Temporalio connection
            temporalio_status = "healthy" if temporalio_client.is_initialized else "unhealthy"
            
            # Check workers
            worker_status = await worker_manager.health_check()
            
            return {
                "status": "healthy" if temporalio_status == "healthy" and worker_status.get("status") == "healthy" else "unhealthy",
                "service": "temporalio-service",
                "version": "1.0.0",
                "temporalio_service": {
                    "status": temporalio_status,
                    "host": f"{settings.temporalio_host}:{settings.temporalio_port}",
                    "namespace": settings.temporalio_namespace,
                    "task_queue": settings.temporalio_task_queue
                },
                "workers": worker_status
            }
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")
    
    # Include API routers with authentication
    @app.middleware("http")
    async def verify_api_key_middleware(request: Request, call_next):
        from fastapi.responses import JSONResponse
        
        # Skip authentication for health and docs endpoints
        if request.url.path in ["/health", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)
        
        # Verify API key
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401, 
                content={"detail": "Missing or invalid Authorization header"}
            )
        
        api_key = auth_header.split(" ")[1]
        if not verify_api_key(api_key):
            return JSONResponse(
                status_code=401, 
                content={"detail": "Invalid API key"}
            )
        
        return await call_next(request)
    
    # Include API routers
    from app.api.workflow_templates import router as templates_router
    from app.api.workflows import router as workflows_router
    from app.api.workflow_executions import router as executions_router
    
    app.include_router(templates_router, prefix="/workflow-templates", tags=["Workflow Templates"])
    app.include_router(workflows_router, prefix="/workflows", tags=["Workflows"])
    app.include_router(executions_router, prefix="/workflow-executions", tags=["Workflow Executions"])
    
    return app

# Create the app
app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.service_port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )
