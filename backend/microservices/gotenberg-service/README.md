# Gotenberg Microservice

Microservicio dedicado para la conversión de documentos que incluye Gotenberg como dependencia interna, siguiendo la arquitectura de microservicios del proyecto.

## Arquitectura

```
Frontend/API Principal → Gotenberg Microservice (incluye Gotenberg binary)
```

### Arquitectura Integrada

El microservicio **`gotenberg-service`** (puerto 8005) está basado en la imagen oficial `gotenberg/gotenberg:8` e incluye:
- **Gotenberg oficial** ejecutándose internamente en puerto 3000
- **Python 3 + FastAPI** que provee:
  - Autenticación y autorización multi-tenant
  - Lógica de negocio (tenant isolation, caching, etc.)
  - Gestión de thumbnails e imágenes
  - APIs específicas para nuestro dominio
  - Consistencia con otros microservicios del proyecto

## Endpoints

### Conversión de Documentos
- `POST /convert/office-to-pdf` - Convierte documentos Office (Word, Excel, PowerPoint)
- `POST /convert/html-to-pdf` - Convierte HTML a PDF
- `POST /convert/markdown-to-pdf` - Convierte Markdown a PDF
- `POST /convert/text-to-pdf` - Convierte texto plano a PDF

### Generación de Thumbnails
- `POST /thumbnails/generate-from-pdf` - Genera thumbnails de páginas PDF
- `POST /thumbnails/generate-from-image` - Genera thumbnails de imágenes

### Utilidades
- `GET /formats/supported` - Lista formatos soportados
- `GET /health` - Health check

## Autenticación

Todos los endpoints requieren:
- Header `X-API-Key`: Clave API del microservicio
- Header `X-Tenant-ID`: ID del tenant (opcional, extraído del contexto)
- Header `X-User-ID`: ID del usuario (opcional)

## Configuración

### Variables de Entorno
- `API_KEY`: Clave API para autenticación
- `GOTENBERG_BASE_URL`: URL interna de Gotenberg (http://localhost:3000)
- `THUMBNAIL_WIDTH/HEIGHT`: Dimensiones de thumbnails
- `PDF_CONVERSION_TIMEOUT`: Timeout para conversiones

## Desarrollo

### Modo Desarrollo
```bash
cd backend/docker
./start-dev.sh
```

El microservicio se monta con live reload en el puerto 8005.

### Testing
```bash
cd backend/docker
docker compose -f docker-compose.test.yml up
```

## Formatos Soportados

### Conversión a PDF
- **Office**: `.docx`, `.doc`, `.xlsx`, `.xls`, `.pptx`, `.ppt`
- **OpenDocument**: `.odt`, `.ods`, `.odp`
- **Texto**: `.txt`, `.md`, `.html`, `.htm`, `.rtf`

### Thumbnails
- **PDF**: Cualquier archivo PDF
- **Imágenes**: `.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp`, `.tiff`

## Dependencias

- **Base**: gotenberg/gotenberg:8 (imagen oficial)
- **Python**: FastAPI + Uvicorn
- **HTTP**: httpx (cliente HTTP)
- **Imágenes**: Pillow (procesamiento de imágenes)
- **PDF**: pdf2image (conversión PDF a imagen)
- **Validación**: pydantic

## Logs

El microservicio registra:
- Errores de conversión
- Problemas de conectividad con Gotenberg
- Operaciones de thumbnail
- Health checks