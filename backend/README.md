# Sistema de Gestión Documental con Búsqueda Semántica

Este proyecto implementa una API REST para un sistema de gestión documental con búsqueda semántica basada en embeddings, permitiendo la carga, procesamiento, indexación y consulta inteligente de documentos.

## Características

- **Autenticación y autorización** con JWT
- **Multi-tenant**: Aislamiento de datos por organización
- **Procesamiento de documentos**: PDF, DOCX, TXT, CSV, Excel, Markdown
- **Búsqueda semántica**: Encuentra documentos relacionados semánticamente
- **Integración LLM**: Resúmenes, sugerencia de etiquetas, respuestas a preguntas
- **Almacenamiento en la nube**: Google Cloud Storage
- **Base de datos vectorial**: Qdrant para embeddings
- **Arquitectura modular**: Servicios independientes y adaptables

## Tecnologías

- **Backend**: FastAPI (Python)
- **Base de datos relacional**: PostgreSQL
- **Cache**: Redis
- **Base de datos vectorial**: Qdrant
- **Almacenamiento**: Google Cloud Storage
- **Modelos de lenguaje**: Ollama
- **Docker**: Contenedores para todos los componentes

## Estructura del Proyecto

```
backend/
│
├── app/                    # Código fuente principal
│   ├── api/                # Endpoints de la API
│   │   ├── dependencies.py # Dependencias compartidas
│   │   └── v1/             # Endpoints versión 1
│   │
│   ├── core/               # Configuración central
│   │   ├── config.py       # Configuración de la aplicación
│   │   ├── security.py     # Funcionalidades de seguridad
│   │   └── logging.py      # Configuración de logs
│   │
│   ├── db/                 # Capa de base de datos
│   │   ├── database.py     # Configuración de la base de datos
│   │   └── models.py       # Modelos SQLAlchemy
│   │
│   ├── schemas/            # Modelos Pydantic
│   │   ├── auth.py         # Esquemas de autenticación
│   │   ├── document.py     # Esquemas de documentos
│   │   └── user.py         # Esquemas de usuarios
│   │
│   ├── services/           # Lógica de negocio
│   │   ├── auth_service.py         # Servicio de autenticación
│   │   ├── document_service.py     # Servicio de documentos
│   │   ├── embedding_service.py    # Servicio de embeddings
│   │   ├── llm_service.py          # Servicio de LLM
│   │   ├── search_service.py       # Servicio de búsqueda
│   │   ├── storage_service.py      # Servicio de almacenamiento
│   │   └── vector_service.py       # Servicio de base vectorial
│   │
│   └── main.py            # Punto de entrada de la aplicación
│
├── docker/                # Configuración de Docker
│   ├── Dockerfile         # Configuración para la imagen
│   └── docker-compose.yml # Configuración de servicios
│
├── scripts/               # Scripts de utilidad
│   ├── init_db.py         # Inicialización de la base de datos
│   └── seed_data.py       # Datos de prueba
│
├── tests/                 # Tests automatizados
│   ├── conftest.py        # Configuración de pruebas
│   ├── test_api/          # Pruebas de la API
│   └── test_services/     # Pruebas de servicios
│
├── .env.example           # Ejemplo de variables de entorno
└── requirements.txt       # Dependencias del proyecto
```

## Requisitos

- Python 3.9+
- Docker y Docker Compose
- Cuenta de Google Cloud (para GCS en producción)

## Configuración

1. Clona el repositorio:
   ```bash
   git clone https://github.com/tu-usuario/doc-management-system.git
   cd doc-management-system/backend
   ```

2. Copia el archivo de ejemplo de variables de entorno:
   ```bash
   cp .env.example .env
   ```

3. Edita el archivo `.env` con tu configuración:
   ```
   # API
   API_V1_STR=/api/v1
   SECRET_KEY=super-secret-key-change-this-in-production
   ACCESS_TOKEN_EXPIRE_MINUTES=10080  # 7 días
   SERVER_NAME=Document Management API
   SERVER_HOST=https://api.example.com
   BACKEND_CORS_ORIGINS=["http://localhost:3000", "http://localhost:8000", "https://app.example.com"]
   
   # PostgreSQL
   POSTGRES_SERVER=db
   POSTGRES_USER=postgres
   POSTGRES_PASSWORD=password
   POSTGRES_DB=doc_management
   
   # Resto de configuraciones...
   ```

## Uso con Docker

1. Inicia los servicios con Docker Compose:
   ```bash
   docker-compose -f docker/docker-compose.yml up -d
   ```

2. Inicializa la base de datos:
   ```bash
   docker-compose -f docker/docker-compose.yml exec api python -m scripts.init_db
   ```

3. La API estará disponible en: `http://localhost:8000`
   - Documentación OpenAPI: `http://localhost:8000/docs`

## Desarrollo Local

1. Crea y activa un entorno virtual:
   ```bash
   python -m venv venv
   source venv/bin/activate  # En Windows: venv\Scripts\activate
   ```

2. Instala dependencias:
   ```bash
   pip install -r requirements.txt
   ```

3. Inicializa la base de datos:
   ```bash
   python -m scripts.init_db
   ```

4. Ejecuta el servidor de desarrollo:
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

## Tests

Ejecuta los tests con pytest:
```bash
chmod +x tests/run_tests.sh  # Asegura permisos de ejecución
./tests/run_tests.sh
```

## Endpoints Principales

### Autenticación

- **POST** `/api/v1/auth/login/access-token` - Obtener token JWT
- **POST** `/api/v1/auth/register` - Registrar nuevo usuario
- **GET** `/api/v1/auth/me` - Obtener usuario actual

### Documentos

- **GET** `/api/v1/documents/` - Listar documentos
- **POST** `/api/v1/documents/` - Subir nuevo documento
- **GET** `/api/v1/documents/{doc_id}` - Obtener documento
- **DELETE** `/api/v1/documents/{doc_id}` - Eliminar documento
- **GET** `/api/v1/documents/{doc_id}/summary` - Generar resumen
- **GET** `/api/v1/documents/{doc_id}/download-url` - Obtener URL de descarga

### Búsqueda

- **GET** `/api/v1/search/` - Búsqueda semántica
- **POST** `/api/v1/search/ask` - Responder preguntas sobre documentos

### Administración

- **GET** `/api/v1/admin/users` - Listar usuarios
- **POST** `/api/v1/admin/users` - Crear usuario
- **GET** `/api/v1/admin/stats` - Estadísticas del sistema
- **POST** `/api/v1/admin/init-ollama-model` - Inicializar modelo LLM

### Tenants

- **GET** `/api/v1/tenants/` - Listar tenants (admin)
- **POST** `/api/v1/tenants/` - Crear tenant (admin)
- **GET** `/api/v1/tenants/current` - Obtener tenant actual

## Implementación en Producción

Para implementar en producción, utiliza el archivo `docker-compose.prod.yml`:

```bash
docker-compose -f docker/docker-compose.prod.yml up -d
```

Este archivo incluye:
- Replicación de servicios
- Configuración de red segura
- Proxy Nginx para HTTPS

## Escalabilidad

El sistema está diseñado para escalar horizontalmente:

1. Los servicios no mantienen estado (stateless)
2. El almacenamiento en GCS permite escala ilimitada
3. Qdrant puede escalar en cluster
4. La arquitectura multi-tenant permite segmentar datos

## Contribuciones

Las contribuciones son bienvenidas. Por favor, sigue estos pasos:

1. Fork el repositorio
2. Crea una rama para tu característica (`git checkout -b feature/caracteristica-increible`)
3. Realiza tus cambios y ejecuta pruebas
4. Haz commit de tus cambios (`git commit -m 'Añade característica increíble'`)
5. Push a la rama (`git push origin feature/caracteristica-increible`)
6. Abre un Pull Request

## Licencia

Este proyecto está licenciado bajo la licencia MIT - consulta el archivo `LICENSE` para más detalles.
