"""
Knowledge Tree Service — TrustGraph

Triple store for TrustGraph knowledge graph on FalkorDB.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.services.falkordb_client import falkordb_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    await falkordb_client.initialize()
    await falkordb_client.bootstrap_schema()
    yield
    await falkordb_client.close()


app = FastAPI(
    title="Knowledge Tree Service — TrustGraph",
    description="Triple store for TrustGraph knowledge graph on FalkorDB",
    version="2.0.0",
    lifespan=lifespan,
)

from app.api.triples import router as triples_router
from app.api.extract import router as extract_router
from app.api.reports import router as reports_router
from app.api.traces import router as traces_router

app.include_router(triples_router)
app.include_router(extract_router)
app.include_router(reports_router)
app.include_router(traces_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "knowledge-tree-service", "version": "2.0.0"}
