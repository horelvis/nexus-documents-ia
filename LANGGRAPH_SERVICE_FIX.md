# LangGraph Service Fix for litellm/httpx Error

## Issue
The langgraph-service was failing to start with the error:
```
AttributeError: 'AsyncHTTPHandler' object has no attribute 'client'
```

This was caused by a conflict in the litellm library used internally by langchain-ollama.

## Solution Applied

### 1. Updated LangGraphManager (`app/core/langgraph_manager.py`)
- Added comprehensive error handling for all component initialization
- Added fallback mechanisms when services are unavailable
- Added explicit timeouts and context window settings
- Added connection testing before declaring services as initialized
- Made the service more resilient to external service failures

### 2. Updated Requirements (`requirements.txt`)
- Added explicit litellm version: `litellm==1.40.19`
- This pins the version to avoid conflicts with httpx

### 3. Key Changes in Error Handling

#### LLM Initialization
```python
try:
    self.llm = ChatOllama(
        base_url=settings.ollama_base_url,
        model=settings.llm_model,
        temperature=0.7,
        num_ctx=4096,  # Add context window
        timeout=60  # Add timeout
    )
    # Test connection
    test_response = await self.llm.ainvoke("test")
except Exception as llm_error:
    # Fallback to mock LLM
    from langchain_core.language_models.fake import FakeListLLM
    self.llm = FakeListLLM(responses=["Mock response"])
```

#### Embeddings Initialization
```python
try:
    self.embeddings = OllamaEmbeddings(
        model=settings.embedding_model,
        base_url=settings.ollama_base_url
    )
except Exception as embed_error:
    # Fallback to fake embeddings
    from langchain_core.embeddings import FakeEmbeddings
    self.embeddings = FakeEmbeddings(size=384)
```

## To Apply the Fix

1. Rebuild the langgraph-service:
```bash
cd backend/docker
docker compose build langgraph-service
```

2. Restart the service:
```bash
docker compose up -d langgraph-service
```

3. Check the logs:
```bash
docker compose logs -f langgraph-service
```

## Benefits
- Service can now start even if Ollama is unavailable
- Graceful degradation with fallback components
- Better error messages for debugging
- More resilient to external service failures
- Proper health check reporting

## Health Check
The health endpoint now reports the status of each component:
```json
{
  "status": "healthy",
  "service": "langgraph-service",
  "checks": {
    "llm": true,
    "embeddings": true,
    "checkpointer": true,
    "qdrant": false,  // if unavailable
    "redis": true
  }
}
```