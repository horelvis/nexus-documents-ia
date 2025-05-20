# scripts/generate_api_docs.py
import os
import json
import yaml
import datetime
import subprocess
from pathlib import Path

# Configuración
API_URL = "http://localhost:8000"  # URL base para pruebas
OUTPUT_DIR = "docs/api"
OPENAPI_JSON_PATH = f"{OUTPUT_DIR}/openapi.json"
OPENAPI_YAML_PATH = f"{OUTPUT_DIR}/openapi.yaml"
POSTMAN_COLLECTION_PATH = f"{OUTPUT_DIR}/postman_collection.json"
MARKDOWN_DOCS_DIR = f"{OUTPUT_DIR}/endpoints"

def ensure_dir(directory):
    """Asegura que un directorio exista."""
    Path(directory).mkdir(parents=True, exist_ok=True)

def fetch_openapi_spec():
    """Obtiene el esquema OpenAPI de la API en ejecución."""
    import requests
    
    try:
        response = requests.get(f"{API_URL}/api/v1/openapi.json")
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error fetching OpenAPI spec: {response.status_code}")
            return None
    except Exception as e:
        print(f"Error: {str(e)}")
        return None

def generate_openapi_files(spec):
    """Genera archivos OpenAPI JSON y YAML."""
    # Guardar como JSON
    with open(OPENAPI_JSON_PATH, 'w') as f:
        json.dump(spec, f, indent=2)
    
    # Guardar como YAML
    with open(OPENAPI_YAML_PATH, 'w') as f:
        yaml.dump(spec, f, sort_keys=False)
    
    print(f"OpenAPI spec saved to {OPENAPI_JSON_PATH} and {OPENAPI_YAML_PATH}")

def generate_postman_collection(spec):
    """Convierte el esquema OpenAPI en una colección Postman."""
    # Crear colección base
    collection = {
        "info": {
            "name": spec.get("info", {}).get("title", "API Documentation"),
            "description": spec.get("info", {}).get("description", ""),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            "version": spec.get("info", {}).get("version", "1.0.0"),
            "_postman_id": f"postman-{datetime.datetime.now().timestamp()}"
        },
        "item": [],
        "variable": [
            {
                "key": "baseUrl",
                "value": API_URL,
                "type": "string"
            }
        ]
    }
    
    # Organizar por tags
    tag_folders = {}
    
    # Procesar cada ruta y endpoint
    for path, path_item in spec.get("paths", {}).items():
        for method, operation in path_item.items():
            if method in ["get", "post", "put", "delete", "patch"]:
                # Determinar a qué tag pertenece
                tags = operation.get("tags", ["default"])
                tag = tags[0] if tags else "default"
                
                # Crear carpeta para el tag si no existe
                if tag not in tag_folders:
                    tag_folders[tag] = {
                        "name": tag,
                        "description": next((t["description"] for t in spec.get("tags", []) if t["name"] == tag), ""),
                        "item": []
                    }
                
                # Crear ítem Postman para esta operación
                item = {
                    "name": operation.get("summary", path),
                    "description": operation.get("description", ""),
                    "request": {
                        "method": method.upper(),
                        "header": [
                            {
                                "key": "Content-Type",
                                "value": "application/json"
                            }
                        ],
                        "url": {
                            "raw": f"{{{{baseUrl}}}}{path}",
                            "host": ["{{baseUrl}}"],
                            "path": path.strip("/").split("/")
                        }
                    }
                }
                
                # Añadir parámetros de query si existen
                query_params = [param for param in operation.get("parameters", []) if param.get("in") == "query"]
                if query_params:
                    item["request"]["url"]["query"] = []
                    for param in query_params:
                        item["request"]["url"]["query"].append({
                            "key": param["name"],
                            "value": "",
                            "description": param.get("description", ""),
                            "disabled": not param.get("required", False)
                        })
                
                # Añadir body si es POST/PUT/PATCH
                if method in ["post", "put", "patch"] and "requestBody" in operation:
                    content = operation["requestBody"].get("content", {})
                    if "application/json" in content:
                        schema = content["application/json"].get("schema", {})
                        
                        # Intentar generar un ejemplo
                        example = {}
                        if "example" in schema:
                            example = schema["example"]
                        elif "properties" in schema:
                            for prop, details in schema["properties"].items():
                                if "example" in details:
                                    example[prop] = details["example"]
                        
                        item["request"]["body"] = {
                            "mode": "raw",
                            "raw": json.dumps(example, indent=2),
                            "options": {
                                "raw": {
                                    "language": "json"
                                }
                            }
                        }
                
                # Añadir este ítem a la carpeta del tag
                tag_folders[tag]["item"].append(item)
    
    # Añadir todas las carpetas de tags a la colección
    collection["item"] = list(tag_folders.values())
    
    # Guardar como JSON
    with open(POSTMAN_COLLECTION_PATH, 'w') as f:
        json.dump(collection, f, indent=2)
    
    print(f"Postman collection saved to {POSTMAN_COLLECTION_PATH}")

def generate_markdown_docs(spec):
    """Genera documentación en Markdown para cada endpoint."""
    ensure_dir(MARKDOWN_DOCS_DIR)
    
    # Índice de la documentación
    index_content = f"# {spec.get('info', {}).get('title', 'API Documentation')}\n\n"
    index_content += spec.get('info', {}).get('description', '') + "\n\n"
    index_content += "## Endpoints\n\n"
    
    # Organizar por tags
    tag_endpoints = {}
    
    # Procesar cada ruta y endpoint 