# Arquitectura Docker

> Desde esta iteración solo la API (y las UIs públicas) exponen puertos al host. El resto de microservicios escucha en su puerto interno dentro de `backend-network` y se comunica por DNS (`http://servicio:puerto`).

```mermaid
graph TB
    subgraph "Frontend"
        NextJS[🖥️ Next.js App<br/>Host Port: 3000]
    end

    subgraph "Backend Services"
        API[🚀 api<br/>Host Port: 8000]
        WeaviateSvc[🤖 weaviate-service + Elysia<br/>Internal: 8000]
        LangExtractSvc[🏷️ langextract-service<br/>Internal: 8000]
        TextExtractSvc[📑 textextract-service<br/>Internal: 8000]
        TemplateSvc[🧩 template-editor-service<br/>Internal: 8000]
        TemporalSvc[🔄 temporalio-service<br/>Internal: 8000]
        StorageSvc[☁️ storage-service<br/>Internal: 8000]
        ElasticSvc[🔎 elasticsearch-service<br/>Internal: 8000]
        GotenbergSvc[📄 gotenberg<br/>Internal: 3000]
    end

    subgraph "Infrastructure"
        Postgres[(📊 postgres<br/>Internal: 5432)]
        Redis[(⚡ redis<br/>Internal: 6379)]
        WeaviateCore[(🔍 weaviate core<br/>Internal: 8080)]
        ElasticsearchCore[(🧭 elasticsearch core<br/>Internal: 9200)]
        Ollama[(🦙 genai-ollama<br/>Internal: 11434)]
    end

    NextJS --> API
    API --> WeaviateSvc
    API --> LangExtractSvc
    API --> TextExtractSvc
    API --> TemplateSvc
    API --> TemporalSvc
    API --> StorageSvc
    API --> ElasticSvc
    API --> GotenbergSvc

    WeaviateSvc --> WeaviateCore
    LangExtractSvc --> Ollama
    TextExtractSvc --> GotenbergSvc
    TemporalSvc --> WeaviateSvc
    StorageSvc --> Postgres
    API --> Postgres
    API --> Redis
    ElasticSvc --> ElasticsearchCore

    classDef frontend fill:#e1f5fe,stroke:#01579b
    classDef backend fill:#f3e5f5,stroke:#4a148c
    classDef infra fill:#efebe9,stroke:#3e2723

    class NextJS frontend
    class API,WeaviateSvc,LangExtractSvc,TextExtractSvc,TemplateSvc,TemporalSvc,StorageSvc,ElasticSvc,GotenbergSvc backend
    class Postgres,Redis,WeaviateCore,ElasticsearchCore,Ollama infra
```
