# Pruebas del Backend

Este directorio contiene las pruebas unitarias y de integración para el backend de la aplicación.

## Cómo Ejecutar las Pruebas

Para ejecutar la suite completa de pruebas, utiliza el script `run_tests.sh` desde el directorio `backend/tests/`:

```bash
./run_tests.sh
```

**Requisitos:**
*   Docker y Docker Compose deben estar instalados y en ejecución.
*   Debes estar en el directorio `backend/tests/` para ejecutar el script.

**Qué Hace el Script:**
1.  **Construye (o reconstruye) las imágenes de Docker** necesarias para el entorno de prueba (definidas en `backend/docker/docker-compose.test.yml`).
2.  **Levanta los servicios dependientes** (base de datos PostgreSQL, Redis, Qdrant) en contenedores Docker. La base de datos se ejecuta en memoria (`tmpfs`) para mayor velocidad y se reinicia en cada ejecución.
3.  **Ejecuta `pytest`** dentro de un contenedor (`test-api`) que tiene acceso a los servicios anteriores.
    *   La configuración de `pytest` se encuentra en `backend/pyproject.toml`.
    *   Los logs de `pytest` (incluyendo los de la aplicación a nivel INFO) se mostrarán en la consola con un formato detallado.
4.  **Genera un informe de cobertura de código** en formato HTML.
5.  **Muestra una lista de las 10 pruebas más lentas.**
6.  **Limpia los contenedores y volúmenes** de prueba al finalizar.

## Informes y Salida

*   **Informe de Cobertura:** Después de una ejecución exitosa, encontrarás el informe de cobertura en `backend/tests/coverage_report/index.html`. El script fallará si la cobertura es inferior al 70%.
*   **Pruebas Lentas:** La lista de las 10 pruebas más lentas se mostrará en la salida de la consola al final de la ejecución de `pytest` (visible en `/tmp/test_output.log` y resumido en la salida del script).
*   **Logs Detallados:** Los logs de `pytest` y de la aplicación (configurados en `backend/pyproject.toml` y `backend/app/core/logging.py` respectivamente) proporcionarán información detallada durante la ejecución. La salida completa de `pytest` se guarda en `/tmp/test_output.log` dentro del contenedor `test-api` durante la ejecución del script.

## Configuración de la Base de Datos de Prueba

El archivo `backend/tests/conftest.py` está configurado para:
*   Crear el esquema de la base de datos una vez por sesión de prueba.
*   Ejecutar cada función de prueba dentro de una transacción de base de datos que se revierte al finalizar la prueba. Esto asegura el aislamiento de los datos entre pruebas sin el costo de recrear el esquema completo cada vez.
```
