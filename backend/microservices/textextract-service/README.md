# Text Extraction Microservice

Microservice responsable de extraer texto plano y metadatos básicos de documentos usando la librería [`unstructured`](https://github.com/Unstructured-IO/unstructured).

## Endpoints

| Método | Ruta                                   | Descripción                                   |
|--------|----------------------------------------|-----------------------------------------------|
| GET    | `/health`                               | Comprobación de estado                        |
| POST   | `/api/v1/text-extraction/extract`       | Extrae texto a partir de un archivo           |

### POST `/api/v1/text-extraction/extract`

Request (multipart/form-data):

```
file: (UploadFile) Documento a procesar
strategy: (opcional) `auto`, `fast`, `hi_res` (defecto: `auto`)
```

Headers necesarios:

- `X-API-Key`
- `X-Tenant-ID`
- `X-User-ID` (opcional)

Response:

```json
{
  "success": true,
  "text": "...",
  "characters": 1234,
  "language": "es",
  "metadata": {
    "file_extension": ".pdf",
    "strategy": "auto",
    "num_elements": 45
  }
}
```

## Desarrollo local

```bash
docker compose up textextract-service
```

## Variables de entorno

- `MICROSERVICES_API_KEY` (obligatoria)
- `TEXT_EXTRACTION_SERVICE_PORT` (opcional, por defecto 8000)
- `ALLOWED_EXTENSIONS` (lista separada por comas)
- `MAX_FILE_SIZE_MB` (límite de tamaño)
