# LangGraph Microservice

Microservice for LangGraph-based workflows with state management, checkpointing, and complex graph execution.

## Overview

This service provides LangGraph capabilities to the Nexus Document system, enabling:
- Stateful graph-based workflows
- Complex conditional logic and loops
- Checkpointing and state persistence
- Parallel execution of tasks
- Human-in-the-loop capabilities

## Features

### Available Graphs

1. **Tag Generation Graph** (`tag_generation`)
   - Generates tags from text with confidence scoring
   - Supports multiple tag types (general, technical, business)
   - Includes validation and refinement loops

2. **Document Processing Graph** (`document_processing`)
   - Intelligent document chunking with quality checks
   - Metadata extraction using LLM
   - Adaptive reprocessing for optimal chunk sizes
   - Multi-tenant vector storage

3. **Enhanced RAG Graph** (`rag`)
   - Multiple search strategies (vector, keyword, metadata)
   - Result fusion and reranking
   - Answer generation with quality checks
   - Automatic refinement for better answers

## API Endpoints

### Graph Execution
- `POST /api/v1/graphs/run` - Run a graph to completion
- `POST /api/v1/graphs/stream` - Stream graph execution events
- `GET /api/v1/graphs/state/{run_id}` - Get execution state
- `POST /api/v1/graphs/step` - Execute single step

### Graph Management
- `GET /api/v1/graphs/types` - List available graph types
- `GET /api/v1/graphs/structure/{graph_type}` - Get graph structure

### Checkpointing
- `POST /api/v1/graphs/checkpoint/save` - Save checkpoint
- `POST /api/v1/graphs/checkpoint/{checkpoint_id}/resume` - Resume from checkpoint

## Development

### Running Locally

1. Start the service with Docker Compose:
```bash
cd backend/docker
./start-dev.sh
```

2. The service will be available at `http://localhost:8007`

3. Run tests:
```bash
cd backend/microservices/langgraph-service
python test_langgraph.py
```

### Environment Variables

- `SERVICE_API_KEY` - API key for service authentication
- `OLLAMA_BASE_URL` - Ollama service URL
- `QDRANT_HOST/PORT` - Qdrant vector database connection
- `REDIS_URL` - Redis for distributed state
- `DATABASE_URL` - PostgreSQL connection
- `LANGGRAPH_BACKEND` - Checkpoint backend (sqlite/redis)

### Adding New Graphs

1. Create a new graph class in `app/graphs/`:
```python
from langgraph.graph import StateGraph, END
from typing import TypedDict

class MyState(TypedDict):
    # Define your state structure
    pass

class MyGraph:
    def __init__(self, llm, embeddings, qdrant_client, checkpointer, **kwargs):
        self.graph = self._build_graph()
    
    def _build_graph(self):
        workflow = StateGraph(MyState)
        # Add nodes and edges
        return workflow.compile(checkpointer=self.checkpointer)
```

2. Register in `app/core/langgraph_manager.py`:
```python
from app.graphs.my_graph import MyGraph

# In _register_graphs method:
self.graphs["my_graph"] = MyGraph
```

3. Update schemas if needed in `app/schemas/graph.py`

## Migration from LangChain

This service is part of the migration from LangChain to LangGraph. Key improvements:

1. **State Management**: Graphs maintain state between nodes
2. **Conditional Logic**: Support for complex branching
3. **Loops**: Iterative refinement capabilities
4. **Checkpointing**: Save and resume execution
5. **Debugging**: Better visibility into execution flow

## Example Usage

### Tag Generation
```python
import httpx

headers = {
    "X-API-Key": "your-api-key",
    "X-Tenant-ID": "tenant-123"
}

request = {
    "graph_type": "tag_generation",
    "input_data": {
        "text": "Your document text here...",
        "max_tags": 5,
        "tag_type": "technical"
    },
    "tenant_id": "tenant-123"
}

response = httpx.post(
    "http://localhost:8007/api/v1/graphs/run",
    json=request,
    headers=headers
)
```

### Document Processing
```python
request = {
    "graph_type": "document_processing",
    "input_data": {
        "document_id": "doc-123",
        "content": "Document content...",
        "filename": "document.pdf",
        "tenant_id": "tenant-123"
    },
    "tenant_id": "tenant-123"
}
```

### RAG Query
```python
request = {
    "graph_type": "rag",
    "input_data": {
        "query": "What is LangGraph?",
        "tenant_id": "tenant-123",
        "max_results": 5,
        "include_sources": True
    },
    "tenant_id": "tenant-123"
}
```

## Architecture

```
LangGraph Service
├── API Layer (FastAPI)
├── Graph Manager (Singleton)
├── Graph Implementations
│   ├── Tag Generation
│   ├── Document Processing
│   └── RAG
├── State Management
│   ├── SQLite Checkpointer
│   └── Redis Backend
└── External Services
    ├── Ollama (LLM)
    ├── Qdrant (Vectors)
    └── PostgreSQL (Metadata)
```

## Monitoring

- Health check: `GET /health`
- Logs: Available in Docker logs
- Metrics: Execution time and iterations tracked

## Future Enhancements

1. **Visual Graph Editor**: Future enhancement
2. **Custom Graph Builder**: API for dynamic graph creation
3. **Advanced Checkpointing**: Redis-based distributed checkpoints
4. **Graph Templates**: Pre-built graphs for common workflows
5. **Performance Analytics**: Detailed execution metrics