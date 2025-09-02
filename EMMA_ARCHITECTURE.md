# 🤖 Emma AI: Arquitectura y Documentación Técnica

## 📋 Introducción

**Emma** es el asistente de IA inteligente de NexusDocs360, construido sobre el framework **Elysia** para proporcionar respuestas contextuales, ejecutar tareas complejas y acceder a información en tiempo real.

## 🏗️ Arquitectura General

```mermaid
graph TB
    User[👤 Usuario] --> Frontend[🖥️ Next.js Frontend]
    Frontend --> API[🔧 FastAPI Principal]
    API --> Emma[🤖 Emma AI Service]
    
    Emma --> Elysia[🧠 Elysia Framework]
    Emma --> Weaviate[📊 Weaviate Vector DB]
    Emma --> Ollama[🦙 Ollama LLMs]
    
    Elysia --> Tools[🛠️ 12+ Specialized Tools]
    Tools --> WebSearch[🌐 Web Search]
    Tools --> Weather[🌤️ Weather API]
    Tools --> Contract[📄 Contract Analysis]
    Tools --> Finance[💰 Financial Analysis]
    Tools --> Signatures[✍️ Digital Signatures]
    
    Weaviate --> PostgreSQL[🗃️ PostgreSQL]
    Emma --> GCS[☁️ Google Cloud Storage]
```

## 🔧 Componentes Principales

### 1. Emma AI Service (Weaviate-Service)
**Puerto**: 8007  
**Ubicación**: `/backend/microservices/weaviate-service/`

#### Responsabilidades:
- Orquestación del framework Elysia
- Gestión de la base de datos vectorial Weaviate
- Coordinación de herramientas especializadas
- Procesamiento de queries conversacionales

#### Archivos Clave:
- `app/services/elysia_service.py` - Core de Emma AI
- `app/services/elysia_tools.py` - Registro de herramientas
- `app/services/weaviate_service.py` - Gestión vectorial
- `app/api/elysia.py` - Endpoints REST

### 2. Elysia Framework Integration

#### Sistema de Decisión Inteligente:
```python
# Herramientas registradas automáticamente con @tool
@tool
async def search_web(query: str, location: str = "Spain") -> str:
    """Search the web for current information"""
    
@tool  
async def get_weather_info(location: str) -> str:
    """Get current weather information"""
```

#### Flujo de Decisión:
1. **Análisis de Query**: Emma analiza la intención del usuario
2. **Selección de Herramientas**: Elysia decide qué herramientas usar
3. **Ejecución**: Las herramientas se ejecutan en paralelo/secuencia
4. **Síntesis**: Emma combina resultados en respuesta coherente

### 3. Weaviate Vector Database

#### Configuración Multi-Tenant:
- **Colecciones**: `Nexus_{tenant_id}_documents`
- **Esquema**: Incluye `document_id` para enlace con PostgreSQL
- **Embeddings**: Modelo `nomic-embed-text` via Ollama

#### Propiedades del Schema:
```python
{
    "id": "document_id",  # PostgreSQL document ID
    "title": "Document title",
    "content": "Full text content", 
    "tenant_id": "Organization ID",
    "document_type": "Category/type",
    "tags": ["metadata", "tags"]
}
```

### 4. Herramientas Especializadas (12+ Tools)

#### Análisis de Documentos:
- **Document Analyzer**: Estructura y metadatos
- **Contract Extractor**: Partes, fechas, términos
- **Financial Analyzer**: KPIs y métricas
- **Compliance Checker**: Verificación regulatoria

#### Información Externa:
- **Web Search**: DuckDuckGo API para información actualizada
- **Weather Info**: wttr.in API para datos meteorológicos

#### Procesamiento:
- **Smart Summarizer**: Resúmenes contextuales
- **Entity Linker**: Relaciones entre documentos
- **Risk Assessor**: Evaluación de riesgos
- **Multi-Language Processor**: Traducción y procesamiento

## 🔄 Flujos de Trabajo

### Chat Conversacional
1. **Input**: Usuario envía query via frontend
2. **Routing**: API principal → Emma AI Service  
3. **Context Search**: Weaviate busca documentos relevantes
4. **Decision Tree**: Elysia analiza y selecciona herramientas
5. **Tool Execution**: Ejecuta herramientas necesarias
6. **Response Synthesis**: Emma combina resultados
7. **Output**: Respuesta contextual al usuario

### Indexación de Documentos
1. **Upload**: Usuario sube documento via frontend
2. **Storage**: Archivo → Google Cloud Storage
3. **Processing**: Extracción de texto y metadatos
4. **Embedding**: Generación de vector embeddings
5. **Indexing**: Almacenamiento en Weaviate con document_id
6. **Linking**: Enlace con registro PostgreSQL

## 🛠️ Configuración y Desarrollo

### Variables de Entorno
```bash
# Weaviate Configuration
WEAVIATE_URL=http://weaviate:8080
ELYSIA_LOCAL_WEAVIATE=true
ELYSIA_DISABLE_WCD=true

# Ollama Integration  
OLLAMA_BASE_URL=http://genai-ollama:11434
MODEL_NAME=gpt-oss:20b

# API Security
MICROSERVICES_API_KEY=nxs_dev_GYCa7km7zmibtf54yzA9NwPMj4fAYFGt
```

### Desarrollo Local
```bash
# Iniciar Emma AI Service
cd backend/docker
./start-dev.sh

# Verificar herramientas disponibles
curl -H "Authorization: Bearer nxs_dev_GYCa7km7zmibtf54yzA9NwPMj4fAYFGt" \
     http://localhost:8007/elysia/tools
```

### Endpoints Principales
- `GET /elysia/tools` - Lista herramientas disponibles
- `POST /elysia/query` - Procesa query conversacional  
- `GET /elysia/health` - Estado del servicio
- `POST /weaviate/collections/{name}/documents` - Indexa documento

## 🔍 Monitoreo y Debugging

### Logs Importantes
```bash
# Emma AI Service logs
docker logs docker-weaviate-service-1 --tail 50

# Verificar herramientas registradas
grep "Available tools" docker logs
```

### Métricas Clave
- **Herramientas Registradas**: 12+ tools (contract analysis, web search, weather, etc.)
- **Tiempo de Respuesta**: < 60 segundos para queries complejas
- **Precisión**: Puntuaciones de confianza en respuestas
- **Cobertura**: Multi-tenant con colecciones isoladas

## 🚀 Roadmap y Mejoras Futuras

### Próximas Características:
- **Herramientas de Búsqueda Web**: Arreglar implementación actual
- **Más Modelos LLM**: Integración con modelos adicionales
- **Análisis Avanzado**: Herramientas especializadas por industria
- **APIs Externas**: Integración con más servicios web
- **Optimización**: Cache inteligente y paralelización

### Mejoras Técnicas:
- **Performance**: Optimización de embeddings y búsqueda
- **Escalabilidad**: Balanceadores de carga y clustering
- **Observabilidad**: Métricas detalladas y tracing
- **Seguridad**: Validación adicional de herramientas externas

---

**Emma AI** representa la evolución natural de la gestión documental, donde la inteligencia artificial no es solo una herramienta, sino un compañero inteligente que comprende, procesa y actúa sobre la información de manera autónoma y contextual.