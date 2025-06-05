# Langroid Microservice

## Descripción

Microservicio avanzado para la gestión de agentes de IA utilizando el framework Langroid. Este servicio proporciona capacidades mejoradas para workflows de agentes multi-step, herramientas especializadas y procesamiento avanzado de documentos.

## Características Principales

### 🤖 Agentes Especializados
- **Digital Signature Agent**: Gestión avanzada de flujos de firma digital
- **Document Analyzer**: Análisis semántico profundo de documentos
- **RAG Assistant**: Asistente con capacidades de búsqueda y recuperación
- **Generic Agent**: Agente configurable para tareas generales

### 🔧 Herramientas Avanzadas
- Creación y gestión de solicitudes de firma
- Monitoreo de estado de firmas
- Búsqueda semántica de documentos
- Análisis de contenido con IA
- Workflows multi-step personalizables

### 🔒 Seguridad
- Control de acceso basado en roles (Admin/Superuser requerido para gestión de agentes)
- Verificación de permisos por tenant
- Validación de contexto de usuario
- Aislamiento de datos por tenant

## Arquitectura

```
┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│   Main Backend     │────│ Langroid Service   │────│     Langroid        │
│   (Agent API)      │    │   (Microservice)   │    │    Framework        │
└─────────────────────┘    └─────────────────────┘    └─────────────────────┘
                                      │
                           ┌──────────┼──────────┐
                           │          │          │
                    ┌─────────┐ ┌─────────┐ ┌─────────┐
                    │ Qdrant  │ │ Ollama  │ │ Backend │
                    │ Vector  │ │  LLM    │ │   DB    │
                    │   DB    │ │ Service │ │         │
                    └─────────┘ └─────────┘ └─────────┘
```

## Configuración

### Variables de Entorno

```bash
# Configuración del servicio
SERVICE_NAME=langroid-service
SERVICE_PORT=8002
LOG_LEVEL=INFO

# Seguridad
SECRET_KEY=your-secret-key
REQUIRE_TENANT_AUTH=true

# Modelos LLM - ACTUALIZADO PARA OLLAMA
OPENAI_API_KEY=your-openai-key  # Opcional
ANTHROPIC_API_KEY=your-anthropic-key  # Opcional
DEFAULT_LLM_MODEL=llama3.1:8b
DEFAULT_EMBEDDING_MODEL=nomic-embed-text

# Base de datos vectorial
QDRANT_HOST=qdrant
QDRANT_PORT=6333
QDRANT_COLLECTION_PREFIX=nexus_langroid

# Ollama (Configuración principal)
OLLAMA_BASE_URL=http://ollama-service:11434

# Configuración de agentes
MAX_CONVERSATION_LENGTH=50
DEFAULT_AGENT_TIMEOUT=300
MAX_CHUNK_SIZE=500
CHUNK_OVERLAP=50
```

## API Endpoints

### Gestión de Agentes

#### Crear Agente
```http
POST /agents/create
Content-Type: application/json
X-Tenant-ID: {tenant_id}
X-User-ID: {user_id}

{
  "agent_type": "digital_signature",
  "tenant_id": "tenant-uuid",
  "user_id": "user-uuid",
  "configuration": {
    "use_langroid": true,
    "custom_settings": {}
  }
}
```

#### Eliminar Agente
```http
DELETE /agents/{agent_id}?tenant_id={tenant_id}
X-Tenant-ID: {tenant_id}
X-User-ID: {user_id}
```

#### Listar Agentes
```http
GET /agents/list?tenant_id={tenant_id}
X-Tenant-ID: {tenant_id}
X-User-ID: {user_id}
```

### Interacción con Agentes

#### Chat con Agente (Streaming)
```http
POST /agents/{agent_id}/chat?tenant_id={tenant_id}
Content-Type: application/json
X-Tenant-ID: {tenant_id}
X-User-ID: {user_id}

{
  "message": "Crea una solicitud de firma para el contrato de servicios",
  "conversation_id": "optional-conversation-id",
  "context": {
    "document_id": "doc-123"
  }
}
```

#### Ejecutar Tarea Específica (Streaming)
```http
POST /agents/{agent_id}/execute?tenant_id={tenant_id}
Content-Type: application/json
X-Tenant-ID: {tenant_id}
X-User-ID: {user_id}

{
  "task_type": "create_signature_request",
  "parameters": {
    "title": "Contrato de Servicios",
    "document_name": "contrato.pdf",
    "signers": [
      {
        "name": "Juan Pérez",
        "email": "juan@example.com"
      }
    ]
  },
  "context": {}
}
```

### Endpoints Especializados

#### Crear Solicitud de Firma
```http
POST /signature-agent/create-request?tenant_id={tenant_id}&user_id={user_id}
Content-Type: application/json

{
  "title": "Contrato de Servicios",
  "document_name": "contrato.pdf",
  "signers": [
    {
      "name": "Juan Pérez",
      "email": "juan@example.com"
    }
  ],
  "message": "Por favor, firma este documento",
  "signature_type": "sequential"
}
```

#### Consultar Estado de Firma
```http
GET /signature-agent/status/{request_id}?tenant_id={tenant_id}&user_id={user_id}
```

#### Analizar Documento
```http
POST /document/analyze
Content-Type: application/json

{
  "document_content": "Contenido del documento...",
  "analysis_type": "summary",
  "tenant_id": "tenant-uuid",
  "user_id": "user-uuid"
}
```

## Respuestas de Streaming

Todos los endpoints de interacción devuelven respuestas en formato Server-Sent Events (SSE):

```javascript
data: {"type": "message", "content": "Procesando tu solicitud...", "metadata": {...}}
data: {"type": "tool_call", "content": "Ejecutando: create_signature_request", "metadata": {...}}
data: {"type": "task_result", "content": "✅ Solicitud creada", "metadata": {"result": {...}}}
```

### Tipos de Eventos

- `message`: Mensaje de texto del agente
- `tool_call`: Ejecución de herramienta
- `task_progress`: Progreso de tarea
- `task_result`: Resultado de tarea
- `error`: Error en procesamiento
- `execution_started`: Inicio de ejecución
- `execution_completed`: Finalización de ejecución

## Integración con Backend Principal

### Cliente Langroid

El backend principal incluye un cliente para comunicarse con este microservicio:

```python
from app.services.langroid_client import LangroidClient

async with LangroidClient() as client:
    # Crear agente
    agent_id = await client.create_agent(
        agent_type="digital_signature",
        tenant_id=tenant_id,
        user_id=user_id,
        configuration={"use_langroid": True}
    )
    
    # Ejecutar tarea con streaming
    async for response in client.execute_agent_task(
        agent_id=agent_id,
        tenant_id=tenant_id,
        user_id=user_id,
        task_type="create_signature_request",
        parameters=params
    ):
        print(response)
```

### Ejecución Híbrida

El servicio de ejecución de agentes puede usar tanto el método legacy como Langroid:

```python
# Configuración en el agente para usar Langroid
agent_config = {
    "use_langroid": True,  # Forzar uso de Langroid
    "fallback_to_legacy": True  # Usar legacy si Langroid falla
}

# El sistema decide automáticamente basado en:
# - Tipo de agente
# - Tipo de tarea  
# - Configuración del agente
```

## Seguridad y Permisos

### Control de Acceso

1. **Gestión de Agentes**: Solo admins y superusers pueden crear/eliminar agentes
2. **Ejecución de Agentes**: Usuarios regulares pueden ejecutar agentes según permisos
3. **Contexto de Tenant**: Todos los datos están aislados por tenant
4. **Validación de Usuario**: Se verifica acceso antes de cada operación

### Headers Requeridos

```http
X-Tenant-ID: {tenant_uuid}
X-User-ID: {user_uuid}
```

## Desarrollo

### Ejecutar Localmente

```bash
# Instalar dependencias
cd backend/microservices/langroid-service
pip install -r requirements.txt

# Configurar variables de entorno
export QDRANT_HOST=localhost
export OLLAMA_BASE_URL=http://localhost:11434

# Ejecutar
python -m uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload
```

### Docker

```bash
# Construir imagen
docker build -t langroid-service .

# Ejecutar contenedor
docker run -p 8002:8002 \
  -e QDRANT_HOST=host.docker.internal \
  -e OLLAMA_BASE_URL=http://host.docker.internal:11434 \
  langroid-service
```

### Docker Compose

El servicio está integrado en el docker-compose.yml principal:

```bash
docker-compose up langroid-service
```

## Monitoreo

### Health Check

```http
GET /health
```

### Estado Detallado

```http
GET /status
```

Respuesta incluye:
- Estado del servicio
- Número de agentes activos
- Tipos de agentes soportados
- Configuración de modelos

## Casos de Uso

### 1. Flujo de Firma Digital Avanzado

```python
# Crear agente de firma
agent_id = await create_signature_agent()

# Ejecutar workflow completo
async for event in execute_signature_workflow(
    agent_id,
    documents=["contract.pdf", "nda.pdf"],
    signers=[...],
    workflow_type="parallel_with_dependencies"
):
    handle_event(event)
```

### 2. Análisis Semántico de Documentos

```python
# Crear agente analizador
agent_id = await create_document_analyzer()

# Análisis multi-documento
async for event in analyze_document_collection(
    agent_id,
    documents=document_collection,
    analysis_types=["summary", "sentiment", "entities"]
):
    process_analysis(event)
```

### 3. Asistente RAG Personalizado

```python
# Crear asistente RAG
agent_id = await create_rag_assistant(
    knowledge_base="tenant_documents",
    specialization="legal_documents"
)

# Chat con contexto
async for response in chat_with_rag(
    agent_id,
    "¿Qué cláusulas de confidencialidad tenemos en nuestros contratos?"
):
    display_response(response)
```

## Troubleshooting

### Problemas Comunes

1. **Agente no responde**: Verificar estado de Qdrant y Ollama
2. **Error de permisos**: Validar headers X-Tenant-ID y X-User-ID
3. **Timeout en ejecución**: Ajustar DEFAULT_AGENT_TIMEOUT
4. **Memoria insuficiente**: Optimizar MAX_CHUNK_SIZE y CHUNK_OVERLAP

### Logs

```bash
# Ver logs del servicio
docker-compose logs langroid-service

# Logs en tiempo real
docker-compose logs -f langroid-service
```

## Contribución

1. Seguir convenciones de código existentes
2. Añadir tests para nuevas funcionalidades
3. Documentar nuevos endpoints
4. Validar seguridad y permisos

## Licencia

Propietario - Nexus Document Backend