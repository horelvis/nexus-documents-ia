#!/bin/bash

# Crear estructura de tests
mkdir -p tests/test_api
mkdir -p tests/test_services
mkdir -p tests/test_utils

# Archivo principal de configuración de tests
touch tests/conftest.py

# Archivos en test_api
touch tests/test_api/{test_auth.py,test_documents.py,test_search.py,test_chat.py,test_admin.py}

# Archivos en test_services
touch tests/test_services/{test_document_service.py,test_llm_service.py,test_embedding_service.py,test_storage_service.py,test_vector_service.py}

# Archivos en test_utils
touch tests/test_utils/test_security.py

echo "Estructura de tests creada correctamente."

