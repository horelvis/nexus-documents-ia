#!/usr/bin/env python3
"""
Minimal FastAPI app for debugging Cloud Run deployment issues
"""

import os
import logging
from fastapi import FastAPI
from fastapi.responses import JSONResponse

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create minimal FastAPI app
app = FastAPI(
    title="Minimal Backend Debug",
    version="0.1.0"
)

@app.get("/")
async def root():
    return {"message": "Minimal backend is running", "status": "ok"}

@app.get("/health")
async def health():
    return {"status": "healthy", "version": "0.1.0"}

@app.get("/debug")
async def debug():
    return {
        "environment": dict(os.environ),
        "port": os.getenv("PORT", "8000"),
        "status": "debug_mode_active"
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)