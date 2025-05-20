#!/bin/bash

# Crear estructura de directorios
mkdir -p backend/app/api/v1
mkdir -p backend/app/core
mkdir -p backend/app/db/repositories
mkdir -p backend/app/services
mkdir -p backend/app/schemas
mkdir -p backend/tests
mkdir -p backend/docker
mkdir -p backend/migrations/alembic
mkdir -p backend/scripts

# Crear archivos en api/v1
touch backend/app/api/v1/{auth.py,documents.py,search.py,chat.py,admin.py,tenants.py,storage.py}
# Archivo en api
touch backend/app/api/dependencies.py

# Archivos en core
touch backend/app/core/{config.py,security.py,logging.py}

# Archivos en db
touch backend/app/db/{database.py,models.py}
touch backend/app/db/repositories/{documents.py,users.py,tenants.py}

# Archivos en services
touch backend/app/services/{auth_service.py,document_service.py,storage_service.py,embedding_service.py,llm_service.py,vector_service.py}

# Archivos en schemas
touch backend/app/schemas/{auth.py,document.py,user.py,tenant.py}

# Main
touch backend/app/main.py

# Tests
touch backend/tests/{conftest.py,test_auth.py,test_documents.py,test_search.py}

# Docker
touch backend/docker/{Dockerfile,docker-compose.yml,docker-compose.prod.yml}

# Scripts
touch backend/scripts/{init_db.py,seed_data.py}

# Archivos raíz
touch backend/{.env.example,requirements.txt,pyproject.toml,README.md}

echo "Estructura del proyecto creada correctamente."

