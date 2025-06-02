# Storage Microservice

Microservicio independiente para gestión de almacenamiento en Google Cloud Storage con autenticación basada en API keys y aislamiento por tenant.

## 🏗️ Arquitectura

```
┌─────────────────┐    HTTP API    ┌──────────────────┐    GCS API    ┌─────────────────┐
│   Backend       │ ────────────── │ Storage Service  │ ───────────── │ Google Cloud    │
│   Principal     │                │                  │               │ Storage         │
└─────────────────┘                └──────────────────┘               └─────────────────┘
```

## 🔐 Seguridad

### Autenticación
- **API Key**: Header `X-API-Key` requerido en todas las requests
- **Tenant ID**: Header `X-Tenant-ID` para aislamiento por tenant
- **User ID**: Header `X-User-ID` (opcional) para organización por usuario

### Aislamiento
- **Por Tenant**: Cada tenant tiene buckets separados (`bucket-{tenant_id}`)
- **Por Usuario**: Archivos organizados en paths como `tenant-{id}/user-{id}/filename`
- **Testing**: Buckets de test con sufijo `-test` para pruebas seguras

## 📚 API Endpoints

### Operaciones de Archivos

#### `POST /api/v1/storage/upload`
Sube un archivo al storage.

**Headers:**
```
X-API-Key: your-secret-api-key
X-Tenant-ID: tenant-123
X-User-ID: user-456 (opcional)
```

**Body (form-data):**
```
file: archivo a subir
metadata: {"doc_id": "123", "category": "documents"} (opcional)
```

#### `GET /api/v1/storage/download/{path}`
Descarga un archivo del storage.

#### `DELETE /api/v1/storage/delete/{path}`
Elimina un archivo del storage.

#### `GET /api/v1/storage/info/{path}`
Obtiene información de un archivo.

#### `GET /api/v1/storage/list`
Lista archivos del tenant.

**Query Parameters:**
- `prefix`: Prefijo para filtrar archivos
- `limit`: Límite de archivos (máx 1000)

### URLs Firmadas

#### `POST /api/v1/storage/signed-url/upload`
Genera URL firmada para subir archivo.

**Body:**
```json
{
  "filename": "document.pdf",
  "content_type": "application/pdf",
  "expiration": 3600
}
```

#### `POST /api/v1/storage/signed-url/download/{path}`
Genera URL firmada para descargar archivo.

### Testing

#### `POST /api/v1/storage/cleanup`
Limpia bucket de test (solo en modo testing).

### Health Check

#### `GET /api/v1/storage/health`
Verifica estado del servicio.

## 🚀 Configuración

### Variables de Entorno

```bash
# Seguridad
STORAGE_API_KEY=your-secret-api-key-here

# Google Cloud Storage
GCS_PROJECT_ID=your-project-id
GCS_CREDENTIALS=/path/to/credentials.json
GCS_BUCKET_NAME=nexus-documents

# Configuración
SIGNED_URL_EXPIRATION=3600
MAX_UPLOAD_SIZE=104857600  # 100MB
RATE_LIMIT_PER_MINUTE=10
DEBUG=false
TESTING=false
```

### Docker Compose

```yaml
storage-service:
  build:
    context: ../microservices/storage-service
    dockerfile: Dockerfile
  ports:
    - "8003:8001"
  environment:
    - STORAGE_API_KEY=${STORAGE_API_KEY}
    - GCS_PROJECT_ID=${GCS_PROJECT_ID}
    - GCS_CREDENTIALS=${GCS_CREDENTIALS}
    - GCS_BUCKET_NAME=${GCS_BUCKET_NAME}
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8001/health"]
```

## 🔧 Uso desde Backend Principal

### StorageServiceV2 (Recomendado)

```python
from app.services.storage_service_v2 import StorageServiceV2

# Inicializar servicio
storage = StorageServiceV2(tenant_id="tenant-123", user_id="user-456")

# Subir archivo
success = storage.upload_file(file, "document.pdf", {"type": "document"})

# Descargar archivo
content = storage.download_file("document.pdf")

# Eliminar archivo
success = storage.delete_file("document.pdf")

# Generar URL firmada
url, expires_at = storage.generate_download_signed_url("document.pdf")
```

### StorageClient (Directo)

```python
from app.services.storage_client import StorageClient

# Cliente directo
client = StorageClient(tenant_id="tenant-123", user_id="user-456")

# Operaciones
result = client.upload_file(file, "document.pdf", {"type": "document"})
content = client.download_file("document.pdf")
files = client.list_files(prefix="documents/")
```

## 🧪 Testing

### Tests con Storage Real

```python
def test_real_storage(real_storage_service):
    # Test que usa GCS real con bucket de test
    content = b"Test content"
    file = io.BytesIO(content)
    
    # Upload
    result = real_storage_service.upload_file(file, "test.txt")
    assert result is True
    
    # Download
    downloaded = real_storage_service.download_file("test.txt")
    assert downloaded == content
    
    # El cleanup es automático
```

### Fixtures Disponibles

- `real_storage_service`: Usa GCS real, cleanup de archivos después del test
- `real_storage_service_with_cleanup`: Usa GCS real, elimina bucket completo después del test

## 📦 Deployment

### Desarrollo

```bash
cd microservices/storage-service
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

### Producción

```bash
docker build -t storage-service .
docker run -p 8001:8001 \
  -e STORAGE_API_KEY=your-secret-key \
  -e GCS_PROJECT_ID=your-project \
  -e GCS_CREDENTIALS=/path/to/creds.json \
  storage-service
```

## 🔍 Monitoreo

### Health Check
```bash
curl http://localhost:8001/health
```

### Logs
```bash
docker logs storage-service -f
```

### Métricas
- Rate limiting por IP
- Logs de todas las operaciones
- Health checks automáticos

## 🚨 Seguridad en Producción

1. **Cambiar API Key**: Usar clave secreta fuerte
2. **HTTPS**: Configurar TLS en producción
3. **Firewall**: Restringir acceso solo desde backend principal
4. **Monitoring**: Configurar alertas de seguridad
5. **Backup**: Configurar backup automático de buckets

## 🔄 Migración

Para migrar del `StorageService` original al microservicio:

1. **Mantener compatibilidad**: Usar `StorageServiceV2` que tiene la misma interfaz
2. **Configurar microservicio**: Agregar variables de entorno
3. **Testing gradual**: Probar con `TESTING=true` primero
4. **Switch gradual**: Cambiar servicio por servicio
5. **Cleanup**: Remover `StorageService` original cuando todo funcione

## 📋 TODO

- [ ] Implementar cache de metadatos
- [ ] Agregar métricas de Prometheus
- [ ] Implementar compresión automática
- [ ] Soporte para múltiples clouds (AWS S3, Azure Blob)
- [ ] Interface de administración web