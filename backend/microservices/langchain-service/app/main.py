"""
LangChain Microservice - FastAPI application
"""
import logging
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from app.services.embedding_service import EmbeddingService
from app.services.vector_service import VectorService
from app.services.llm_service import LLMService
from app.api.recommendations import router as recommendations_router
from app.core.security import validate_service_access

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="LangChain Microservice",
    description="Microservice for LangChain operations including embeddings, vector search, and LLM",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(recommendations_router)

# Pydantic models for API
class EmbeddingRequest(BaseModel):
    texts: List[str]

class EmbeddingResponse(BaseModel):
    embeddings: List[List[float]]

class AddDocumentRequest(BaseModel):
    tenant_id: str
    doc_id: str
    texts: List[str]
    metadatas: List[Dict[str, Any]]

class SearchRequest(BaseModel):
    tenant_id: str
    query: str
    limit: int = 5
    doc_ids: Optional[List[str]] = None

class SearchResponse(BaseModel):
    results: List[Dict[str, Any]]

class LLMRequest(BaseModel):
    query: str
    tenant_id: Optional[str] = None
    doc_ids: Optional[List[str]] = None
    max_tokens: int = 500

class LLMResponse(BaseModel):
    answer: str
    sources: List[Dict[str, Any]]
    context_used: Optional[int] = None

class ChunkRequest(BaseModel):
    text: str

class ChunkResponse(BaseModel):
    chunks: List[Dict[str, Any]]

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "langchain-service"}

@app.post("/embeddings", response_model=EmbeddingResponse)
async def generate_embeddings(
    request: EmbeddingRequest,
    security: dict = Depends(validate_service_access)
):
    """Generate embeddings for texts"""
    try:
        embedding_service = EmbeddingService()
        embeddings = embedding_service.get_embeddings(request.texts)
        return EmbeddingResponse(embeddings=embeddings)
    except Exception as e:
        logger.error(f"Error generating embeddings: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/embedding", response_model=Dict[str, List[float]])
async def generate_single_embedding(
    request: Dict[str, str],
    security: dict = Depends(validate_service_access)
):
    """Generate embedding for single text"""
    try:
        embedding_service = EmbeddingService()
        embedding = embedding_service.get_embedding(request["text"])
        return {"embedding": embedding}
    except Exception as e:
        logger.error(f"Error generating single embedding: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chunk", response_model=ChunkResponse)
async def chunk_text(
    request: ChunkRequest,
    security: dict = Depends(validate_service_access)
):
    """Chunk text into smaller pieces"""
    try:
        embedding_service = EmbeddingService()
        chunks = embedding_service.chunk_text(request.text)
        return ChunkResponse(chunks=chunks)
    except Exception as e:
        logger.error(f"Error chunking text: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/documents/add")
async def add_documents(
    request: AddDocumentRequest,
    security: dict = Depends(validate_service_access)
):
    """Add documents to vector store"""
    try:
        vector_service = VectorService(security["tenant_id"])
        success = vector_service.add_documents(request.texts, request.metadatas)
        return {"success": success}
    except Exception as e:
        logger.error(f"Error adding documents: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/documents/add-single")
async def add_single_document(
    request: Dict[str, Any],
    security: dict = Depends(validate_service_access)
):
    """Add single document to vector store"""
    try:
        vector_service = VectorService(security["tenant_id"])
        success = vector_service.add_document(
            request["doc_id"], 
            request["text"], 
            request.get("metadata", {})
        )
        return {"success": success}
    except Exception as e:
        logger.error(f"Error adding single document: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/search", response_model=SearchResponse)
async def search_similar(
    request: SearchRequest,
    security: dict = Depends(validate_service_access)
):
    """Search for similar documents"""
    try:
        vector_service = VectorService(security["tenant_id"])
        
        if request.doc_ids:
            results = vector_service.search_by_document_ids(
                request.doc_ids, request.query, request.limit
            )
        else:
            results = vector_service.search_similar(request.query, request.limit)
        
        return SearchResponse(results=results)
    except Exception as e:
        logger.error(f"Error searching documents: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/llm/generate", response_model=LLMResponse)
async def generate_llm_response(request: LLMRequest):
    """Generate LLM response with optional RAG"""
    try:
        llm_service = LLMService()
        response = await llm_service.generate_response(
            query=request.query,
            doc_ids=request.doc_ids,
            tenant_id=request.tenant_id,
            max_tokens=request.max_tokens
        )
        
        return LLMResponse(
            answer=response["answer"],
            sources=response["sources"],
            context_used=response.get("context_used")
        )
    except Exception as e:
        logger.error(f"Error generating LLM response: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/llm/suggest-tags")
async def suggest_tags(request: Dict[str, Any]):
    """Suggest tags for text"""
    try:
        llm_service = LLMService()
        tags = await llm_service.suggest_tags(
            request["text"], 
            request.get("num_tags", 5)
        )
        return {"tags": tags}
    except Exception as e:
        logger.error(f"Error suggesting tags: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/llm/extract-metadata")
async def extract_metadata(request: Dict[str, str]):
    """Extract metadata from text"""
    try:
        llm_service = LLMService()
        metadata = await llm_service.extract_metadata(request["text"])
        return {"metadata": metadata}
    except Exception as e:
        logger.error(f"Error extracting metadata: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/llm/summarize")
async def summarize_text(request: Dict[str, Any]):
    """Summarize text"""
    try:
        llm_service = LLMService()
        summary = await llm_service.summarize_text(
            request["text"], 
            request.get("max_length", 200)
        )
        return {"summary": summary}
    except Exception as e:
        logger.error(f"Error summarizing text: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/documents/{tenant_id}/{doc_id}")
async def delete_document(
    tenant_id: str, 
    doc_id: str,
    security: dict = Depends(validate_service_access)
) -> dict:
    """Delete document from vector store"""
    try:
        # Validate tenant_id parameter
        if not tenant_id:
            raise HTTPException(status_code=400, detail="Tenant ID required")
        
        vector_service = VectorService(tenant_id)
        success = vector_service.delete_document(doc_id)
        return {"success": success}
    except Exception as e:
        logger.error(f"Error deleting document: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/collection/{tenant_id}/info")
async def get_collection_info(
    tenant_id: str,
    security: dict = Depends(validate_service_access)
) -> dict:
    """Get collection information"""
    try:
        # Validate tenant_id parameter
        if not tenant_id:
            raise HTTPException(status_code=400, detail="Tenant ID required")
        
        vector_service = VectorService(tenant_id)
        info = vector_service.get_collection_info()
        return info
    except Exception as e:
        logger.error(f"Error getting collection info: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)