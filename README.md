# Aplicación Fullstack Inteligente (Proyecto Demo)

Esta es una aplicación fullstack de demostración que incluye un backend en Python/FastAPI y un frontend en Remix/TypeScript. El backend está diseñado para la gestión y búsqueda inteligente de documentos, utilizando tecnologías como Qdrant para búsqueda vectorial y potencialmente servicios LLM.

## Estructura del Proyecto

El repositorio está organizado de la siguiente manera:

-   `/backend`: Contiene la aplicación API desarrollada con FastAPI, la lógica de negocio y los servicios de procesamiento de documentos.
-   `/frontend`: Contiene la interfaz de usuario desarrollada con Remix (React/TypeScript).
-   `/docs`: Documentación adicional y guías (si aplica).
-   `init_structure.sh`: Script para la creación inicial de la estructura de directorios y archivos del proyecto (usar solo para desarrollo inicial).

## Prerrequisitos

Antes de comenzar, asegúrate de tener instalados los siguientes programas:

-   **Docker y Docker Compose:** Para ejecutar la aplicación en un entorno contenerizado.
-   **Node.js:** (Versión LTS recomendada) Para la gestión de dependencias y ejecución del frontend. Se puede usar `npm` o `yarn`.
-   **Python:** (Versión 3.8+ recomendada) Para el desarrollo y ejecución del backend.

## Configuración Inicial

1.  **Clonar el Repositorio:**
    ```bash
    git clone <URL_DEL_REPOSITORIO>
    cd <NOMBRE_DEL_DIRECTORIO_DEL_PROYECTO>
    ```

2.  **Configurar Variables de Entorno:**
    *   **Backend:** Revisa `backend/.env.example` y crea un archivo `.env` en el directorio `backend/` con tu configuración local si es necesario.
    *   **Frontend:** Revisa si existe un `.env.example` en `frontend/` y configura las variables necesarias.

3.  **Script de Inicialización (Opcional):**
    *   El script `init_structure.sh` se utiliza únicamente para generar la estructura de carpetas y archivos inicial. **No es necesario para ejecutar el proyecto si la estructura ya existe y no inicia servicios.**
    ```bash
    # ./init_structure.sh # Descomentar y ejecutar si existe y es necesario para crear la estructura base
    ```

4.  **Instalar Dependencias:**
    *   **Backend:**
        ```bash
        # Opción 1: Si se gestiona con pip directamente
        pip install -r backend/requirements.txt

        # Opción 2: Si se construye con Docker, las dependencias se instalan en la imagen.
        ```
    *   **Frontend:**
        ```bash
        cd frontend
        npm install # o yarn install
        cd ..
        ```

## Cómo Ejecutar la Aplicación

Se recomienda ejecutar la aplicación utilizando Docker Compose si existe una configuración a nivel raíz que orqueste todos los servicios.

**Opción 1: Usando Docker Compose (Recomendado para el Backend y servicios dependientes)**

1.  **Levantar los Servicios del Backend (desde el directorio `backend/docker/`):**
    ```bash
    cd backend/docker
    docker compose up --build -d
    ```
    Esto iniciará el backend API, PostgreSQL, Redis y Qdrant.

2.  **Levantar el Frontend (en un terminal separado, desde el directorio `frontend/`):**
    ```bash
    cd frontend
    npm run dev # o yarn dev
    ```

3.  **Acceder a la Aplicación:**
    *   Frontend: `http://localhost:3000` (o el puerto configurado para Remix)
    *   Backend API: `http://localhost:8000/api/v1/docs` (o el puerto y prefijo configurado para FastAPI)

**Opción 2: Ejecución Manual (para desarrollo local)**

*   **Backend:**
    1.  Asegúrate de que los servicios de base de datos (PostgreSQL, Redis, Qdrant) estén en ejecución y accesibles.
    2.  Navega al directorio del backend: `cd backend`
    3.  Inicia el servidor FastAPI/Uvicorn:
        ```bash
        uvicorn app.main:app --reload --port 8000
        ```

*   **Frontend:**
    1.  Navega al directorio del frontend: `cd frontend`
    2.  Inicia el servidor de desarrollo de Remix:
        ```bash
        npm run dev
        ```

## Cómo Ejecutar las Pruebas

*   **Backend:**
    Las pruebas del backend se ejecutan utilizando `pytest` en un entorno Docker.
    ```bash
    cd backend/tests
    ./run_tests.sh
    ```
    Para más detalles, consulta el archivo `backend/tests/README.md`.

*   **Frontend:**
    Las pruebas del frontend se ejecutan con Vitest (u otra herramienta configurada).
    ```bash
    cd frontend
    npm test # o el comando configurado en package.json (ej. yarn test, npm run vitest)
    ```

## Tecnologías Principales

*   **Backend:** Python, FastAPI, SQLAlchemy, PostgreSQL, Redis, Qdrant, Docker.
*   **Frontend:** Remix, React, TypeScript, Tailwind CSS, Vitest, Docker.

---

Este README proporciona una guía básica. Revisa la documentación específica en los subdirectorios `/backend` y `/frontend` para obtener información más detallada.
```
