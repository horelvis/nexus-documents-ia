# Arquitectura Docker

> Solo la API, frontend y servicios de proxy exponen puertos al host. El resto de microservicios escucha en su puerto interno dentro de `backend-network` y se comunica por DNS (`http://servicio:puerto`).

```mermaid
graph TB
    subgraph "Frontend"
        NextJS[🖥️ Next.js App<br/>Host Port: 3001]
    end

    subgraph "Backend Services"
        API[🚀 api<br/>Host Port: 8000]
        EmmaSvc[🤖 emma-agent-service<br/>Internal: 8009]
        WeaviateSvc[🔎 weaviate-service<br/>Internal: 8000]
        IntelligenceSvc[📄 intelligence-docs-service<br/>Internal: 8000, Host: 8012]
        KnowledgeTreeSvc[🌳 knowledge-tree-service<br/>Internal: 8011]
        BackgroundWorker[⚙️ background-worker<br/>Internal: 8100]
        StorageSvc[☁️ storage-service<br/>Internal: 8010]
        PresentationSvc[📊 presentation-service<br/>Internal: 8000]
    end

    subgraph "GPU Services"
        SGLang[🧠 sglang<br/>Host Port: 8001<br/>Qwen3.5-9B FP8]
        GLMOCR[👁️ glm-ocr<br/>Internal: 8000<br/>GLM-OCR 0.9B]
    end

    subgraph "Infrastructure"
        Postgres[(📊 postgres<br/>Port: 5432)]
        Redis[(⚡ redis<br/>Port: 6379)]
        WeaviateCore[(🔍 weaviate<br/>Port: 8080)]
        FalkorDB[(🕸️ falkordb<br/>Port: 6380)]
        Langfuse[(📈 langfuse<br/>Host: 3002)]
        Keycloak[(🔐 keycloak<br/>Port: 8080)]
    end

    NextJS --> API
    API --> EmmaSvc
    API --> WeaviateSvc
    API --> StorageSvc

    EmmaSvc --> SGLang
    EmmaSvc --> WeaviateSvc
    EmmaSvc --> KnowledgeTreeSvc
    EmmaSvc --> Langfuse
    EmmaSvc --> Postgres
    EmmaSvc --> Redis

    WeaviateSvc --> WeaviateCore
    WeaviateSvc --> IntelligenceSvc
    WeaviateSvc --> KnowledgeTreeSvc

    IntelligenceSvc --> SGLang
    IntelligenceSvc --> GLMOCR

    KnowledgeTreeSvc --> FalkorDB

    API --> Postgres
    API --> Redis
    API --> Keycloak

    classDef frontend fill:#e1f5fe,stroke:#01579b
    classDef backend fill:#f3e5f5,stroke:#4a148c
    classDef gpu fill:#fff3e0,stroke:#e65100
    classDef infra fill:#efebe9,stroke:#3e2723

    class NextJS frontend
    class API,EmmaSvc,WeaviateSvc,IntelligenceSvc,KnowledgeTreeSvc,BackgroundWorker,StorageSvc,PresentationSvc backend
    class SGLang,GLMOCR gpu
    class Postgres,Redis,WeaviateCore,FalkorDB,Langfuse,Keycloak infra
```

## Servicios GPU (RTX 4090 24GB)

| Servicio | VRAM | Modelo | Función |
|----------|------|--------|---------|
| `sglang` | ~14 GB | Qwen3.5-9B FP8 | LLM inference (chat + planner) |
| `intelligence-docs-service` | ~2.7 GB | BGE-M3 | Embeddings 1024 dims |
| `glm-ocr` | ~2 GB | GLM-OCR 0.9B | OCR para documentos escaneados |
| **Total** | **~19 GB** | | Deja ~5 GB para KV cache |

## Flujo de Datos Principal

```
Document Upload → API → weaviate-service (indexing pipeline)
    → intelligence-docs-service (text extraction: Docling/GLM-OCR)
    → intelligence-docs-service (embeddings: BGE-M3)
    → intelligence-docs-service (entity extraction: LangExtract)
    → Weaviate (vector store)
    → FalkorDB (knowledge graph)

User Query → API → emma-agent-service (LangGraph ReAct agent)
    → SGLang (LLM inference)
    → weaviate-service (SmartSearch: Weaviate + FalkorDB + PublicKnowledge)
    → Response with citations
```
