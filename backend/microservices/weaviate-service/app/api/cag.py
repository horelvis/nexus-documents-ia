"""Legacy-compatible CAG endpoints served by the Weaviate/Elysia service."""
import json
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.core.security import verify_api_key
from app.schemas.cag import (
    CAGQueryRequest,
    CAGQueryResponse,
    DocumentAnalysisRequest,
    DocumentAnalysisResponse,
    TaskExecutionRequest,
)
from app.services.cag_adapter import cag_adapter

router = APIRouter(prefix="/api/v1/cag", tags=["CAG"])


@router.post("/query", response_model=CAGQueryResponse)
async def process_query(
    request: CAGQueryRequest, _: bool = Depends(verify_api_key)
) -> CAGQueryResponse:
    try:
        return await cag_adapter.process_query(request)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/query/stream")
async def process_query_stream(
    request: CAGQueryRequest, _: bool = Depends(verify_api_key)
) -> StreamingResponse:
    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            async for chunk in cag_adapter.process_query_stream(request):
                yield f"data: {json.dumps(chunk)}\n\n"
        except Exception as exc:  # pragma: no cover
            yield f"data: {json.dumps({'type': 'error', 'content': str(exc)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.post("/analyze", response_model=DocumentAnalysisResponse)
async def analyze_document(
    request: DocumentAnalysisRequest, _: bool = Depends(verify_api_key)
) -> DocumentAnalysisResponse:
    try:
        return await cag_adapter.analyze_document(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/analyze/stream")
async def analyze_document_stream(
    request: DocumentAnalysisRequest, _: bool = Depends(verify_api_key)
) -> StreamingResponse:
    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            async for chunk in cag_adapter.analyze_document_stream(request):
                yield f"data: {json.dumps(chunk)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'content': str(exc)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.post("/embeddings")
async def generate_embeddings(
    texts: List[str],
    tenant_id: Optional[str] = None,
    _: bool = Depends(verify_api_key),
) -> Dict[str, Any]:
    # tenant_id kept for backwards compatibility/logging purposes
    result = await cag_adapter.generate_embeddings(texts)
    result["tenant_id"] = tenant_id
    return result


@router.post("/execute/stream")
async def execute_task_stream(
    request: TaskExecutionRequest, _: bool = Depends(verify_api_key)
) -> StreamingResponse:
    async def event_stream() -> AsyncGenerator[str, None]:
        async for chunk in cag_adapter.execute_task_stream(request):
            yield f"data: {json.dumps(chunk)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.get("/agents/available")
async def get_available_agents(_: bool = Depends(verify_api_key)) -> Dict[str, Any]:
    return await cag_adapter.get_agents_info()


@router.get("/health")
async def health_check(_: bool = Depends(verify_api_key)) -> Dict[str, Any]:
    return await cag_adapter.health()
