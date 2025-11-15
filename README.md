# NexusDocs360 - Plataforma de Gestión Documental Potenciada por IA

<div align="center">
  <h3>🧠 Donde la IA Transforma Documentos en Decisiones 🚀</h3>
  <p><strong>Inteligencia Artificial 360° para tu Gestión Documental</strong></p>
</div>

## 📋 Descripción

**NexusDocs360** es la próxima generación en gestión documental empresarial, donde la Inteligencia Artificial no es solo una característica, sino el núcleo que transforma radicalmente cómo las organizaciones interactúan con su información. Nuestra plataforma utiliza IA avanzada para automatizar el 80% de las tareas documentales, permitiendo que los equipos se enfoquen en decisiones estratégicas mientras la IA maneja la complejidad operativa.

### 🌟 Características Principales Potenciadas por IA

- **🧠 Emma AI Assistant**: Asistente inteligente que comprende contexto, extrae insights y genera respuestas personalizadas
- **🖼️ Previews Instantáneos**: Conversión con Gotenberg para visualizar cualquier documento al instante
- **🌐 Búsqueda Web en Tiempo Real**: Acceso a información actualizada con herramientas de búsqueda web integradas
- **🔍 Búsqueda Semántica Avanzada**: Powered by Weaviate para encontrar documentos por significado, no solo palabras
- **💬 Chat Conversacional**: Interactúa con tus documentos usando procesamiento de lenguaje natural
- **📊 Análisis Automático**: Extrae automáticamente datos clave de contratos, facturas y documentos legales
- **🧠 Extracción de Entidades**: Sistema LangExtract que identifica automáticamente personas, organizaciones, fechas, importes y relaciones
- **🎯 Clasificación Inteligente**: Organización automática de documentos con IA de alta precisión
- **🔄 Workflows Adaptativos**: Sistema de decisión inteligente que selecciona las mejores herramientas para cada tarea
- **🌐 Capacidades Multimodales**: Procesa texto, PDFs con firmas digitales y metadatos complejos
- **⚖️ Chain of Thought**: Visualización transparente del proceso de razonamiento de la IA (solo para administradores)

## 🤖 Emma AI: Asistente Inteligente de Nueva Generación

### Emma AI Assistant
**Emma** es nuestro asistente de IA avanzado **construido sobre Elysia Framework**, diseñado para proporcionar respuestas contextuales y ejecutar tareas complejas de forma autónoma.

#### Capacidades Principales de Emma:
- **🧠 Procesamiento Contextual**: Comprende el contexto completo de tus documentos
- **🔍 Búsqueda Inteligente**: Encuentra información relevante usando Elysia Framework con Weaviate vector search
- **🌐 Información en Tiempo Real**: Accede a datos actualizados via búsqueda web
- **🌤️ Consultas Meteorológicas**: Información climática para cualquier ubicación
- **📄 Análisis de Documentos**: Extrae insights de contratos, facturas y reportes
- **🏷️ Extracción de Entidades**: Identifica automáticamente personas, organizaciones, fechas e importes
- **🔄 Comparación de Documentos**: Análisis comparativo inteligente entre documentos
- **⚖️ Chain of Thought**: Transparencia completa del proceso de razonamiento (admin)
- **✨ Respuestas Adaptativas**: Sistema de decisión que selecciona las mejores herramientas

#### Tecnología Subyacente:
- **Elysia Framework**: Sistema de decisión inteligente y orquestación de herramientas (core de Emma AI)
- **Weaviate**: Base de datos vectorial para búsqueda semántica avanzada
- **Ollama Integration**: Modelos locales (gpt-oss:20b) para privacidad y rendimiento
- **LangExtract Integration**: Extracción automática de entidades en upload de documentos
- **Multi-Tool Architecture**: 13+ herramientas especializadas para diferentes tareas

### Casos de Uso con IA
1. **Due Diligence Automático**: Analiza 1000+ documentos en minutos con extracción de entidades
2. **Extracción de Datos**: 99% precisión en facturas, contratos, formularios con LangExtract
3. **Generación de Resúmenes**: Dashboards ejecutivos instantáneos
4. **Detección de Anomalías**: Identifica inconsistencias y riesgos ocultos
5. **Comparación de Contratos**: Análisis diferencial automático entre versiones
6. **Búsqueda por Entidades**: Encuentra documentos por personas, organizaciones o importes
7. **Recomendaciones Proactivas**: Sugiere acciones basadas en patrones

## 🧩 Biblioteca de Plantillas + Workflows Durables

### Plantillas Inteligentes Reutilizables
- **Process Library por tenant**: En la ruta `/{tenantId}/workflows` encontrarás plantillas curadas como Renovación de Contratos u Onboarding con formularios dinámicos y validación en vivo.
- **Catálogo híbrido**: El Core sirve `/api/v1/workflow-templates` (DB multi-tenant); si falla, el sistema usa el catálogo AI (`backend/app/data/ai_workflow_catalog.py`) para mantener operativa la librería.
- **Schemas ricos**: Cada plantilla define pasos, campos condicionales, tags, complejidad y duración estimada, por lo que el frontend se configura automáticamente sin código adicional.
- **Payloads normalizados**: `build_workflow_payload()` agrega defaults y transforma inputs antes de enviar la ejecución a Temporalio, reduciendo errores por datos incompletos.

### Workflows impulsados por Temporalio
- **Motor durable**: Temporalio Server (7233) + Web UI (8233) + microservicio `temporalio-service` (8010) orquestan Emma/Ollama con reintentos automáticos, señales y queries en caliente.
- **Workflows listos**: `ContractRenewalWorkflow` y `EmployeeOnboardingWorkflow` ya están disponibles con seguimiento en tiempo real y opciones de cancelar/consultar desde la UI o API.
- **Monitorización integrada**: Dashboard y pestaña Monitor refrescan los estados cada 30 s/10 s; los endpoints `/temporalio/workflow/{id}/status`, `/temporalio/workflows` y `/workflow-executions` exponen la misma telemetría para automatizaciones.
- **Setup rápido**: `cd backend/docker && ./start-dev.sh` levanta API + Temporalio; health checks en `http://localhost:8010/health` y Web UI en `http://localhost:8233/`.

### Documentación relacionada
- [TEMPORALIO_INTEGRATION.md](TEMPORALIO_INTEGRATION.md): Arquitectura, endpoints, fases del rollout y mejores prácticas de operación.
- [WORKFLOW_UI_TEST_PLAN.md](WORKFLOW_UI_TEST_PLAN.md): Pasos detallados para validar plantillas y workflows desde la UI y las APIs de visibilidad.

## 🏗️ Arquitectura del Sistema

NexusDocs360 está construido con una arquitectura de microservicios moderna y orientada a IA, diseñada para máxima escalabilidad, seguridad y rendimiento.

### 📊 Diagramas de Arquitectura

#### 🎨 **Diagrama Interactivo de Arquitectura**
Para una experiencia visual más detallada, consulta nuestro **[diagrama interactivo de arquitectura](backend/architecture/architecture_diagram.html)** que incluye:
- Vista detallada por capas del sistema
- Flujo de procesamiento de documentos paso a paso
- Conexiones y comunicación entre servicios
- Resumen visual de la arquitectura completa

#### 📈 **Diagrama General del Sistema**

```mermaid
graph TB
    %% Usuarios y Dispositivos
    subgraph "👥 Usuarios"
        User[👤 Usuario Final]
        Admin[👑 Administrador]
        API_Client[🤖 API Client]
    end

    %% Capa de Presentación
    subgraph "🎨 Frontend Layer"
        NextJS[🖥️ Next.js 15<br/>App Router + TypeScript]
        Mobile[📱 Mobile App<br/>React Native]
        AdminUI[⚙️ Admin Dashboard<br/>Shadcn/UI]
    end

    %% API Gateway y Autenticación
    subgraph "🌐 API Gateway"
        Nginx[🔀 Nginx Proxy<br/>SSL + Load Balancer]
        Clerk[🔐 Clerk Auth<br/>OAuth2 + JWT]
        FastAPI[🚀 FastAPI<br/>Main API Gateway]
    end

    %% Servicios de Negocio
    subgraph "⚙️ Business Services"
        DocumentSvc[📄 Document Service<br/>Upload + Processing]
        SearchSvc[🔍 Search Service<br/>Semantic + Hybrid]
        AgentSvc[🤖 Agent Service<br/>AI Conversations]
        SignatureSvc[✍️ Signature Service<br/>Digital Signatures]
        StorageSvc[☁️ Storage Service<br/>GCS Integration]
        AuthSvc[🔒 Auth Service<br/>RBAC + Multi-tenant]
        TeamSvc[👥 Team Service<br/>Collaboration]
        NotificationSvc[📧 Notification Service<br/>Email + Webhooks]
    end

    %% Microservicios de IA
    subgraph "🧠 AI & Workflow Services"
        CAG_Svc[📊 CAG Service<br/>Content Analysis & Agents<br/>Port: 8008]
        LangExtractSvc[🏷️ LangExtract Service<br/>Entity Extraction<br/>Port: 8009]
        TextExtractSvc[📑 TextExtract Service<br/>Deterministic Parsing<br/>Port: 8012]
        WeaviateSvc[🔍 Weaviate Service<br/>Vector Proxy<br/>Port: 8007]
        TemporalioSvc[🔄 Temporalio Service<br/>Durable Workflows<br/>Port: 8010]
        TemplateSvc[🧩 Template Editor Service<br/>Process Library<br/>Port: 8011]
        ElasticSvc[🔎 Elasticsearch Service<br/>Hybrid Search<br/>Port: 8005]
        GotenbergSvc[📄 Gotenberg Service<br/>Document Conversion<br/>Port: 3000 int.]
        OllamaHost[🦙 Ollama Host<br/>Local LLMs<br/>Port: 11434]
    end

    %% Capa de Datos
    subgraph "💾 Data Layer"
        PostgreSQL[(📊 PostgreSQL 15<br/>Main Database<br/>Multi-tenant)]
        Weaviate[(🔍 Weaviate<br/>Vector Database<br/>Semantic Search)]
        Redis[(⚡ Redis<br/>Cache + Sessions)]
        Elasticsearch[(🔎 Elasticsearch<br/>Hybrid Search<br/>Microservice)]
    end

    %% Servicios Externos
    subgraph "🌍 External Services"
        GCS[☁️ Google Cloud Storage<br/>File Storage]
        Stripe[💳 Stripe<br/>Payments]
        SignatureProviders[✍️ Signature Providers<br/>DocuSign, YouSign, etc.]
        EmailSvc[📧 Email Service<br/>SendGrid/Mailgun]
        WebSearch[🌐 Web Search APIs<br/>DuckDuckGo, etc.]
        WeatherAPI[🌤️ Weather APIs<br/>Current conditions]
    end

    %% Conexiones
    User --> NextJS
    Admin --> AdminUI
    API_Client --> Nginx

    NextJS --> Clerk
    AdminUI --> Clerk
    Mobile --> Clerk

    Clerk --> FastAPI
    Nginx --> FastAPI

    FastAPI --> DocumentSvc
    FastAPI --> SearchSvc
    FastAPI --> AgentSvc
    FastAPI --> SignatureSvc
    FastAPI --> StorageSvc
    FastAPI --> AuthSvc
    FastAPI --> TeamSvc
    FastAPI --> NotificationSvc

    DocumentSvc --> LangExtractSvc
    DocumentSvc --> TextExtractSvc
    DocumentSvc --> CAG_Svc
    SearchSvc --> WeaviateSvc
    SearchSvc --> ElasticSvc
    AgentSvc --> CAG_Svc
    AgentSvc --> TemporalioSvc
    TemplateSvc --> TemporalioSvc
    TemporalioSvc --> CAG_Svc
    DocumentSvc --> GotenbergSvc

    LangExtractSvc --> OllamaHost
    CAG_Svc --> OllamaHost

    DocumentSvc --> PostgreSQL
    SearchSvc --> PostgreSQL
    AgentSvc --> PostgreSQL
    AuthSvc --> PostgreSQL
    TeamSvc --> PostgreSQL

    LangExtractSvc --> WeaviateSvc
    CAG_Svc --> WeaviateSvc
    WeaviateSvc --> Weaviate

    DocumentSvc --> Redis
    SearchSvc --> Redis
    AuthSvc --> Redis

    ElasticSvc --> Elasticsearch

    StorageSvc --> GCS
    StorageSvc --> GotenbergSvc
    SignatureSvc --> SignatureProviders
    NotificationSvc --> EmailSvc

    EmmaAI --> WebSearch
    EmmaAI --> WeatherAPI

    FastAPI --> Stripe

    %% Estilos
    classDef frontend fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    classDef api fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef service fill:#e8f5e8,stroke:#1b5e20,stroke-width:2px
    classDef microservice fill:#fff3e0,stroke:#e65100,stroke-width:2px
    classDef database fill:#fce4ec,stroke:#880e4f,stroke-width:2px
    classDef external fill:#efebe9,stroke:#3e2723,stroke-width:2px

    class NextJS,Mobile,AdminUI frontend
    class Nginx,Clerk,FastAPI api
    class DocumentSvc,SearchSvc,AgentSvc,SignatureSvc,StorageSvc,AuthSvc,TeamSvc,NotificationSvc service
    class CAG_Svc,LangExtractSvc,TextExtractSvc,WeaviateSvc,TemporalioSvc,TemplateSvc,ElasticSvc,GotenbergSvc,OllamaHost microservice
    class PostgreSQL,Weaviate,Redis,Elasticsearch database
    class GCS,Stripe,SignatureProviders,EmailSvc,WebSearch,WeatherAPI external
```

### 🏛️ Arquitectura por Capas

#### 🎨 **Capa de Presentación**
- **Next.js 15**: Framework React moderno con App Router
- **Shadcn/UI**: Componentes accesibles y personalizables
- **TypeScript**: Type safety completo en el frontend
- **Tailwind CSS**: Diseño responsive y moderno
- **PWA Support**: Funcionalidad offline y notificaciones

#### 🌐 **Capa de API Gateway**
- **Nginx**: Proxy reverso con SSL automático y load balancing
- **Clerk**: Autenticación OAuth2/JWT multi-proveedor
- **FastAPI**: API principal con documentación automática
- **Rate Limiting**: Protección contra abuso de APIs
- **CORS**: Configuración segura para desarrollo y producción

#### ⚙️ **Servicios de Negocio (Core)**
- **Document Service**: Gestión completa del ciclo de vida de documentos, incluyendo conversión/previews mediante Gotenberg
- **Search Service**: Búsqueda híbrida (semántica + keyword)
- **Agent Service**: Gestión de conversaciones con IA
- **Signature Service**: Integración con proveedores de firma digital
- **Storage Service**: Gestión de archivos en Google Cloud Storage
- **Auth Service**: Autenticación y autorización multi-tenant
- **Team Service**: Colaboración y gestión de equipos
- **Notification Service**: Sistema de notificaciones y webhooks

#### 🧠 **Microservicios de IA y Workflows**
- **CAG Service** (8008): Análisis de contenido, generación de insights y cadenas de agentes
- **LangExtract Service** (8009): Extracción automática de entidades sobre cada upload
- **TextExtract Service** (8012): Parsing determinístico/OCR para documentos complejos
- **Weaviate Service** (8007): Proxy vectorial multi-tenant con guardrails y métricas
- **Temporalio Service** (8010): Ejecución de workflows durables conectados al Process Library
- **Template Editor Service** (8011): Gestión colaborativa de plantillas y formularios AI
- **Elasticsearch Service** (8005): Búsqueda híbrida (keyword + vector) y analytics
- **Gotenberg Service** (3000 int.): Conversión y generación de PDFs a partir de HTML/Office
- **Ollama Host** (11434): Modelos LLM locales (Llama 3.x, GPT-OSS) para baja latencia

#### 💾 **Capa de Datos**
- **PostgreSQL 15**: Base de datos relacional multi-tenant
- **Weaviate**: Base de datos vectorial para búsqueda semántica
- **Redis**: Cache de alto rendimiento y gestión de sesiones
- **Elasticsearch**: Búsqueda híbrida y analytics (microservicio)

#### 🌍 **Servicios Externos**
- **Google Cloud Storage**: Almacenamiento seguro y escalable
- **Stripe**: Procesamiento de pagos y suscripciones
- **Signature Providers**: DocuSign, YouSign, Signaturit
- **Email Services**: SendGrid, Mailgun para notificaciones
- **Web Search APIs**: Información en tiempo real
- **Weather APIs**: Datos meteorológicos contextuales

### 🔄 **Flujo de Datos Principal**

```mermaid
sequenceDiagram
    participant U as 👤 Usuario
    participant F as 🖥️ Frontend
    participant A as 🚀 FastAPI
    participant D as 📄 Document Service
    participant E as 🤖 Emma AI (Elysia)
    participant W as 🔍 Weaviate
    participant P as 📊 PostgreSQL
    participant G as ☁️ GCS

    U->>F: Upload Document
    F->>A: POST /api/v1/documents
    A->>D: Process Document
    D->>G: Store File
    D->>P: Save Metadata
    D->>E: Generate Embeddings
    E->>W: Store Vectors
    D->>A: Document Processed
    A->>F: Success Response

    U->>F: Search Query
    F->>A: GET /api/v1/search
    A->>E: Semantic Search
    E->>W: Vector Search
    W->>E: Similar Documents
    E->>A: Search Results
    A->>F: Results + Metadata
```

### 🛡️ **Características de Seguridad**

- **🔐 Autenticación Multi-Factor**: Clerk con soporte OAuth2
- **👥 Aislamiento Multi-Tenant**: Datos completamente separados
- **🔒 Encriptación End-to-End**: Datos en reposo y tránsito
- **📊 Auditoría Completa**: Logging de todas las operaciones
- **🚫 Rate Limiting**: Protección contra ataques DoS
- **🔑 RBAC**: Control granular de permisos
- **🛡️ CORS**: Configuración segura por entorno

### 📈 **Escalabilidad y Rendimiento**

- **🐳 Docker**: Contenerización completa con hot-reload
- **⚡ Async/Await**: Procesamiento asíncrono en Python
- **🔄 Load Balancing**: Distribución automática de carga
- **📊 Monitoring**: Métricas en tiempo real con Prometheus
- **🚀 CDN**: Optimización de assets estáticos
- **💾 Cache**: Redis para mejorar rendimiento
- **🔍 Vector Search**: Búsqueda semántica de alta velocidad

### 📊 Flujo de Procesamiento de Documentos con IA

```mermaid
sequenceDiagram
    participant U as 👤 Usuario
    participant F as 🖥️ Frontend
    participant A as 🚀 FastAPI
    participant D as 📄 Document Service
    participant LE as 🏷️ LangExtract Service
    participant CAG as 📊 CAG Service
    participant E as 🤖 Emma AI (Elysia)
    participant O as 🦙 Ollama Service
    participant W as 🔍 Weaviate
    participant P as 📊 PostgreSQL
    participant G as ☁️ GCS

    %% Upload y Procesamiento Inicial
    U->>F: 📤 Upload Document
    F->>A: POST /api/v1/documents
    A->>D: 🔄 Process Document

    %% Almacenamiento
    D->>G: 💾 Store File in GCS
    D->>P: 💾 Save Basic Metadata

    %% Extracción de Entidades (Automática)
    D->>LE: 🔍 Extract Entities
    LE->>O: 🤖 Use LLM for Entity Recognition
    O->>LE: 📋 Return Extracted Entities
    LE->>P: 💾 Store Entities in DB

    %% Análisis de Contenido
    D->>CAG: 📊 Analyze Content
    CAG->>O: 🤖 Generate Content Summary
    O->>CAG: 📝 Return Analysis
    CAG->>P: 💾 Store Analysis Results

    %% Generación de Embeddings
    D->>E: 🧮 Generate Embeddings
    E->>O: 🤖 Create Vector Embeddings
    O->>E: 🔢 Return Embeddings
    E->>W: 💾 Store in Weaviate
    E->>P: 🔗 Link Document ID

    %% Respuesta Final
    D->>A: ✅ Document Fully Processed
    A->>F: 🎉 Success + Rich Metadata

    %% Búsqueda Semántica
    U->>F: 🔍 Search Query
    F->>A: GET /api/v1/search
    A->>E: 🔍 Semantic Search
    E->>W: 🔍 Vector Similarity Search
    W->>E: 📄 Return Similar Documents
    E->>P: 📊 Enrich with Metadata
    E->>A: 📋 Search Results
    A->>F: 🎯 Results + Highlights

    %% Chat con Documentos
    U->>F: 💬 Ask Question
    F->>A: POST /api/v1/search/ask
    A->>E: 🤖 Process Question with Context
    E->>W: 🔍 Find Relevant Document Chunks
    E->>O: 🤖 Generate Answer with RAG
    O->>E: 💡 Return Contextual Answer
    E->>A: 💬 Answer + Sources
    A->>F: 🎯 AI Response + Citations
```

### 🔄 **Pipeline de IA Completo**

```mermaid
flowchart TD
    A[📤 Document Upload] --> B[🔍 File Type Detection]
    B --> C[📝 Text Extraction]
    C --> D[🏷️ Entity Recognition]
    D --> E[📊 Content Analysis]
    E --> F[🧮 Embedding Generation]
    F --> G[💾 Vector Storage]
    G --> H[🔍 Search Ready]

    D --> I[💰 Financial Data]
    D --> J[📅 Dates & Deadlines]
    D --> K[👥 People & Organizations]
    D --> L[📋 Contract Terms]

    E --> M[📈 Document Classification]
    E --> N[🎯 Risk Assessment]
    E --> O[📊 Key Metrics Extraction]

    H --> P[🔍 Semantic Search]
    H --> Q[💬 AI Chat]
    H --> R[📊 Analytics]
    H --> S[🔗 Document Relationships]

    classDef input fill:#e3f2fd,stroke:#1976d2,stroke-width:2px
    classDef process fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px
    classDef ai fill:#e8f5e8,stroke:#388e3c,stroke-width:2px
    classDef storage fill:#fff3e0,stroke:#f57c00,stroke-width:2px
    classDef output fill:#fce4ec,stroke:#c2185b,stroke-width:2px

    class A input
    class B,C process
    class D,E,F ai
    class G storage
    class H,P,Q,R,S output
    class I,J,K,L,M,N,O ai
```

### 🔌 **APIs y Puertos del Sistema**

| Servicio | Puerto | Tecnología | Endpoint Principal | Descripción |
|----------|--------|------------|-------------------|-------------|
| **Main API** | `8000` | FastAPI | `/api/v1/` | Pasarela principal y orquestación |
| **CAG Service** | `8008` | FastAPI | `/` | Análisis de contenido y agentes |
| **LangExtract Service** | `8009` | FastAPI | `/` | Extracción automática de entidades |
| **TextExtract Service** | `8012` | FastAPI | `/` | Parsing determinístico/OCR |
| **Weaviate Service** | `8007` | FastAPI | `/` | Proxy vectorial multi-tenant |
| **Storage Service** | `8003` | FastAPI | `/` | Operaciones GCS y signed URLs |
| **Elasticsearch Service** | `8005` | FastAPI | `/` | Búsqueda híbrida + filtros |
| **Temporalio Service** | `8010` | FastAPI | `/` | Workflows durables y signals |
| **Template Editor Service** | `8011` | FastAPI | `/` | Gestión de plantillas y formularios |
| **Temporalio Web UI** | `8233` | Temporal UI | `/` | Monitoreo de workflows |
| **Frontend** | `3000` | Next.js | `/` | Interfaz principal |
| **Gotenberg** | `3000 (interno)` | Gotenberg 8 | `/` | Conversión de documentos a PDF |
| **Ollama Host** | `11434` | Ollama | `/api/generate` | Modelos LLM locales |

### 🐳 **Arquitectura Docker**

### 📚 **Documentación de Arquitectura Adicional**

Para diagramas más detallados y específicos:

- **[Diagrama Interactivo HTML](backend/architecture/architecture_diagram.html)** - Vista completa e interactiva de la arquitectura
- **[Sistema General](backend/architecture/system-overview.md)** - Diagrama general del sistema
- **[Flujo de Datos](backend/architecture/data-flow.md)** - Secuencia de procesamiento de datos
- **[Procesamiento de Documentos](backend/architecture/document-processing.md)** - Pipeline completo de IA
- **[Pipeline de IA](backend/architecture/ai-pipeline.md)** - Arquitectura del procesamiento con IA
- **[Arquitectura Docker](backend/architecture/docker-architecture.md)** - Configuración de contenedores

### 🔄 **Arquitectura Docker**

```mermaid
graph TB
    subgraph "🐳 Docker Network"
        subgraph "Frontend Services"
            NextJS[🖥️ nextjs-app<br/>Port: 3000]
        end

        subgraph "Backend Services"
            API[🚀 api<br/>8000]
            CAG[📊 cag-service<br/>8008]
            LangExtract[🏷️ langextract-service<br/>8009]
            TextExtract[📑 textextract-service<br/>8012]
            Storage[☁️ storage-service<br/>8003]
            WeaviateSvc[🔍 weaviate-service<br/>8007]
            ElasticSvc[🔎 elasticsearch-service<br/>8005]
            TemporalSvc[🔄 temporalio-service<br/>8010]
            TemplateSvc[🧩 template-editor-service<br/>8011]
        end

        subgraph "Infrastructure"
            Postgres[(📊 postgres<br/>5432)]
            Redis[(⚡ redis<br/>6379)]
            Weaviate[(🔍 weaviate core<br/>8080)]
            Elasticsearch[(🧠 elasticsearch<br/>9200)]
            TemporalServer[(⏱️ temporalio-server<br/>7233)]
            TemporalUI[(🖥️ temporalio-ui<br/>8233)]
            Gotenberg[(📄 gotenberg<br/>3000 int.)]
            Ollama[(🦙 genai-ollama<br/>11434)]
        end
    end

    NextJS --> API

    API --> CAG
    API --> LangExtract
    API --> TextExtract
    API --> Storage
    API --> WeaviateSvc
    API --> ElasticSvc
    API --> TemporalSvc
    API --> TemplateSvc

    CAG --> WeaviateSvc
    LangExtract --> WeaviateSvc
    CAG --> Ollama
    LangExtract --> Ollama
    TextExtract --> Gotenberg

    WeaviateSvc --> Weaviate
    ElasticSvc --> Elasticsearch
    Storage --> Gotenberg
    TemporalSvc --> TemporalServer
    TemporalSvc --> TemporalUI
    TemplateSvc --> TemporalSvc

    API --> Postgres
    API --> Redis

    classDef frontend fill:#e1f5fe,stroke:#01579b
    classDef backend fill:#f3e5f5,stroke:#4a148c
    classDef infra fill:#efebe9,stroke:#3e2723

    class NextJS frontend
    class API,CAG,LangExtract,TextExtract,Storage,WeaviateSvc,ElasticSvc,TemporalSvc,TemplateSvc backend
    class Postgres,Redis,Weaviate,Elasticsearch,TemporalServer,TemporalUI,Gotenberg,Ollama infra
```

## 🚀 Inicio Rápido

### Prerrequisitos
- Docker y Docker Compose
- Node.js 18+ (para desarrollo frontend)
- Python 3.9+ (para desarrollo backend)
- Cuenta en Google Cloud (para almacenamiento)

### Instalación

1. **Clonar el repositorio**:
```bash
git clone https://github.com/your-org/nexusdocs360.git
cd nexusdocs360
```

2. **Configurar variables de entorno**:
```bash
cp .env.example .env
# Editar .env con tu configuración
```

3. **Iniciar servicios con Docker**:
```bash
# Backend + Servicios
cd backend/docker
./start-dev.sh

# Frontend (en otra terminal)
cd frontend
npm install
npm run dev
```

4. **Acceder a la aplicación**:
- Frontend: http://localhost:3000
- API Docs: http://localhost:8000/docs
- Administración: http://localhost:3000/admin

## 🔧 Desarrollo

### Estructura del Proyecto
```
nexusdocs360/
├── backend/
│   ├── app/               # Aplicación principal FastAPI
│   ├── microservices/     # Microservicios especializados
│   ├── docker/            # Configuración Docker
│   └── tests/             # Tests automatizados
├── frontend/
│   ├── app/               # Next.js App Router
│   ├── components/        # Componentes React
│   └── lib/               # Utilidades y servicios
├── nginx/                 # Configuración proxy reverso
└── deployment/           # Scripts de despliegue
```

### Comandos Útiles

```bash
# Backend
cd backend/docker && ./start-dev.sh     # Iniciar desarrollo
cd backend/tests && ./run_tests.sh      # Ejecutar tests

# Frontend
cd frontend && npm run dev               # Iniciar desarrollo
cd frontend && npm run build             # Build producción
cd frontend && npm run lint              # Linting

# Base de datos
cd backend && python scripts/alembic_safe_migrate.py  # Migraciones seguras
cd backend && python -m scripts.init_db               # Inicializar DB

# 🆕 Extracción de Entidades
cd backend && python scripts/migrate_extract_entities_langextract.py --dry-run  # Migrar documentos existentes
```

## 📦 Despliegue

### Google Cloud Platform (Recomendado)

```bash
# Configuración rápida
./deploy-to-gcp.sh

# O paso a paso
cd deployment/gcp
cp .env.prod .env
./setup-secrets.sh
./deploy-infrastructure.sh
gcloud builds submit --config=cloudbuild.yaml
```

Consulta [DEPLOYMENT.md](DEPLOYMENT.md) para guía completa de despliegue.

## 📚 Documentación Adicional

- **[LANGEXTRACT_INTEGRATION.md](LANGEXTRACT_INTEGRATION.md)**: Guía completa de extracción automática de entidades
- **[EMMA_ARCHITECTURE.md](EMMA_ARCHITECTURE.md)**: Arquitectura técnica de Emma AI y Chain of Thought
- **[CLAUDE.md](CLAUDE.md)**: Guía para desarrollo con Claude Code
- **[TEMPORALIO_INTEGRATION.md](TEMPORALIO_INTEGRATION.md)**: Integración de Temporalio (workflows durables)
- **[WORKFLOW_UI_TEST_PLAN.md](WORKFLOW_UI_TEST_PLAN.md)**: Guía paso a paso para probar workflows desde la UI

## 🔐 Seguridad

- Autenticación multi-factor con Clerk
- Encriptación en reposo y tránsito
- Auditoría completa de acciones
- Cumplimiento GDPR/HIPAA ready
- Aislamiento total multi-tenant

## 🆕 Últimas Mejoras y Características

### 🧠 Extracción Automática de Entidades (NUEVO)
**Integración completa de LangExtract en el flujo de upload**:
- ✅ **Automático**: Cada documento extrae entidades al subir
- ✅ **Múltiples tipos**: Contratos, facturas, reportes, documentos generales  
- ✅ **Entidades detectadas**: Personas, organizaciones, fechas, importes, términos legales
- ✅ **API de búsqueda**: Búsqueda por entidades extraídas
- ✅ **Migración**: Script para extraer entidades de documentos existentes

### ⚖️ Chain of Thought Visualization (NUEVO)
**Para administradores del sistema**:
- ✅ **Transparencia total**: Visualiza el proceso de razonamiento de Emma AI
- ✅ **Decision Tree**: Árbol de decisiones con contexto global
- ✅ **Tool Selection**: Ve qué herramientas considera y selecciona
- ✅ **Reasoning Steps**: Pasos detallados del análisis
- ✅ **Performance Metrics**: Tiempo de ejecución y confianza

### 🔄 Comparación de Documentos (NUEVO)
**Emma AI puede comparar documentos**:
- ✅ **Análisis de contenido**: Similitudes y diferencias
- ✅ **Comparación estructural**: Formato y organización
- ✅ **Metadatos**: Fechas, autores, versiones
- ✅ **Recomendaciones**: Acciones sugeridas basadas en diferencias

## 📊 Características Empresariales

- **Gestión de Equipos**: Roles y permisos granulares
- **Integraciones**: API REST, Webhooks, SDK
- **Personalización**: Campos personalizados, workflows
- **Escalabilidad**: Arquitectura cloud-native
- **Soporte 24/7**: SLA empresarial disponible

## 🤝 Contribuir

Las contribuciones son bienvenidas. Por favor:

1. Fork el proyecto
2. Crea tu feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add AmazingFeature'`)
4. Push al branch (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

## 📄 Licencia

Este proyecto está licenciado bajo [MIT License](LICENSE).

## 🆘 Soporte

- 📧 Email: support@nexusdocs360.com
- 📚 Documentación: [docs.nexusdocs360.com](https://docs.nexusdocs360.com)
- 💬 Discord: [NexusDocs360 Community](https://discord.gg/nexusdocs360)
- 🐛 Issues: [GitHub Issues](https://github.com/your-org/nexusdocs360/issues)

---

<div align="center">
  <h3>🧠 NexusDocs360 - Donde la Inteligencia Artificial Transforma Cada Documento en Ventaja Competitiva 🚀</h3>
  <p><strong>El Futuro de la Gestión Documental es Inteligente</strong></p>
  <p>Potenciado por IA de Vanguardia | Hecho con ❤️ y 🤖 por el equipo de NexusDocs360</p>
</div>
