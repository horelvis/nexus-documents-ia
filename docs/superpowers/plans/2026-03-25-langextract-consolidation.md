# Plan de Implementacion: Consolidacion LangExtract

**Spec**: `docs/superpowers/specs/2026-03-25-langextract-consolidation-design.md`
**Fecha**: 2026-03-25

## Fase 1: Preparacion (sin cambios funcionales)

### 1.1 Extender Entity dataclass
**Archivo**: `backend/microservices/intelligence-docs-service/app/providers/base.py`

Agregar campos opcionales a `Entity`:

```python
@dataclass
class Entity:
    type: str
    value: str
    provider: str
    confidence: float = 1.0
    start_pos: Optional[int] = None
    end_pos: Optional[int] = None
    attributes: dict[str, Any] = field(default_factory=dict)
```

### 1.2 Extender EntityResponse en schemas
**Archivo**: `backend/microservices/intelligence-docs-service/app/schemas/models.py`

Agregar `start_pos`, `end_pos`, `attributes` a `EntityResponse`.

### 1.3 Actualizar processor.py para pasar nuevos campos
**Archivo**: `backend/microservices/intelligence-docs-service/app/pipeline/processor.py`

Mapear `start_pos`, `end_pos`, `attributes` de `Entity` a `EntityResponse`.

### 1.4 Agregar dependencias
**Archivo**: `backend/microservices/intelligence-docs-service/requirements.txt`

```
langextract[openai]==1.1.1
pillow>=10.0.0
mrz>=0.6.2
```

**Nota**: NO agregar `python-doctr[torch]` a requirements.txt directamente. Mantenerlo como dependencia opcional con lazy import, ya que es muy pesada. Solo se instala si se necesita extraccion de documentos de identidad.

## Fase 2: Crear LangExtractProvider

### 2.1 Extraer configuraciones few-shot
**Crear**: `backend/microservices/intelligence-docs-service/app/providers/entities/few_shot_configs.py`

Mover las 9+ configuraciones few-shot desde `langextract-service/app/services/extractor.py`:
- contract, invoice, report, nomina, modelo_111, modelo_190, modelo_303, certificado, comunicacion_itss, general

Cada config es un dict con `prompt` (str) y `examples` (list de `lx.data.ExampleData`).

### 2.2 Implementar LangExtractProvider
**Crear**: `backend/microservices/intelligence-docs-service/app/providers/entities/langextract_provider.py`

Estructura:

```python
import langextract as lx
from app.providers.base import EntityProvider, Entity
from app.providers.entities.few_shot_configs import EXTRACTION_CONFIGS

class LangExtractProvider(EntityProvider):
    name = "langextract"

    def __init__(self, sglang_base_url, sglang_model,
                 extraction_passes=1, max_char_buffer=10000, timeout=120):
        ...

    async def extract_entities(self, text, language="es",
                                document_type="general") -> list[Entity]:
        # 1. Seleccionar config few-shot segun document_type
        # 2. Ejecutar lx.extract() via asyncio.to_thread (blocking call)
        # 3. Convertir extractions a Entity con source grounding
        ...

    def _map_class_to_type(self, extraction_class: str) -> str:
        """Mapear clases langextract a tipos Entity estandar."""
        ...

    async def is_available(self) -> bool:
        # Verificar conectividad con SGLang
        ...
```

**Nota**: `lx.extract()` es sincrono y puede tardar 5-30s. Se ejecuta en `asyncio.to_thread()`.

### 2.3 Agregar configuracion
**Archivo**: `backend/microservices/intelligence-docs-service/app/core/config.py`

```python
langextract_enabled: bool = True
langextract_extraction_passes: int = 1
langextract_max_char_buffer: int = 10000
langextract_confidence_threshold: float = 0.7
id_document_enabled: bool = True
```

### 2.4 Registrar provider en main.py
**Archivo**: `backend/microservices/intelligence-docs-service/app/main.py`

Cambiar la cadena de providers de `"regex,sglang"` a `"regex,langextract"`.

Eliminar el bloque de registro de `sglang` provider (ya no se usa).

### 2.5 Extender /entities endpoint con document_type
**Archivo**: `backend/microservices/intelligence-docs-service/app/schemas/models.py`

Agregar `document_type: str = "general"` a `EntitiesRequest`.

**Archivo**: `backend/microservices/intelligence-docs-service/app/pipeline/processor.py`

Pasar el `document_type` detectado al step de entity extraction.

## Fase 3: Mover Servicio de Documentos de Identidad

### 3.1 Mover id_document_service.py
**Mover**: `langextract-service/app/services/id_document_service.py`
**A**: `intelligence-docs-service/app/services/id_document_service.py`

Sin cambios en el codigo — solo ajustar imports si es necesario.

### 3.2 Crear router de identidad
**Crear**: `intelligence-docs-service/app/api/identity.py`

Mover los endpoints:
- `GET /identity/health`
- `POST /identity/extract`

### 3.3 Registrar router en main.py
**Archivo**: `intelligence-docs-service/app/main.py`

```python
from app.api.identity import router as identity_router
app.include_router(identity_router)
```

## Fase 4: Extender Clasificador

### 4.1 Clasificacion LLM opcional
**Archivo**: `backend/microservices/intelligence-docs-service/app/pipeline/classifier.py`

Agregar Stage 3 (LLM classification via langextract) despues de las heuristicas:

```python
# Stage 3: LLM classification via langextract (si disponible)
if langextract_available and confidence < 0.7:
    # Usar detect_document_type() portado de extractor.py
    ...
```

Mover la logica de `detect_document_type()` desde `extractor.py` a un metodo reutilizable.

## Fase 5: Refactorizar providers obsoletos

### 5.0a Eliminar providers NER obsoletos
**Eliminar**: `backend/microservices/intelligence-docs-service/app/providers/entities/sglang_ner.py`
**Eliminar**: `backend/microservices/intelligence-docs-service/app/providers/entities/vllm_ner.py`

Verificar que no hay imports restantes:
```bash
grep -r "sglang_ner\|SglangNer\|vllm_ner\|VllmNer" backend/microservices/intelligence-docs-service/
```

### 5.0b Refactorizar regex_spanish.py a guardrail
**Crear**: `backend/microservices/intelligence-docs-service/app/providers/guardrails/spanish_id_validator.py`
**Eliminar**: `backend/microservices/intelligence-docs-service/app/providers/entities/regex_spanish.py`

Reutilizar la logica de validacion de checksums (DNI mod 23, NIE prefix map) pero con nuevo rol:

```python
class SpanishIdValidator:
    """Guardrail post-extraccion para IDs espanoles."""

    def validate_and_enrich(self, entities: list[Entity], text: str) -> list[Entity]:
        """
        1. Validar checksums de DNI/NIE extraidos por LangExtract
           - Checksum valido: confidence = 0.95
           - Checksum invalido: confidence = 0.3, attributes["checksum_valid"] = False
        2. Scan regex del texto para encontrar DNI/NIE/CIF que LangExtract omitio
           - Agregar como entidades con provider="regex_guardrail", confidence=0.95
        3. Retornar lista enriquecida y validada
        """
```

**Integrar en processor.py**: Ejecutar `validate_and_enrich()` despues del paso de entity extraction, antes de devolver la respuesta.

Verificar que no hay imports restantes del provider original:
```bash
grep -r "regex_spanish\|RegexSpanish" backend/microservices/intelligence-docs-service/
```

### 5.1 Actualizar intelligence_client.py
**Archivo**: `backend/microservices/weaviate-service/app/clients/intelligence_client.py`

Enviar `document_type` en el request body de `extract_entities()`. Extender respuesta para incluir `start_pos`, `end_pos`, `attributes`.

### 5.2 Eliminar langextract_client.py
**Eliminar**: `backend/microservices/weaviate-service/app/services/rag/langextract_client.py`

Verificar que no hay imports restantes:
```bash
grep -r "langextract_client" backend/microservices/weaviate-service/
```

### 5.3 Actualizar docker-compose.onpremise.yml
**Archivo**: `backend/docker/docker-compose.onpremise.yml`

- Eliminar seccion `langextract-service:`
- Eliminar `langextract-service: condition: service_healthy` de `weaviate-service.depends_on`
- Eliminar `LANGEXTRACT_SERVICE_URL=http://langextract-service:8000` de `weaviate-service.environment`
- Agregar a `intelligence-docs-service.environment`:
  ```yaml
  - ENTITY_PROVIDERS=langextract
  ```

### 5.4 Actualizar docker-compose.yml.saas (si aplica)
Mismas eliminaciones que en onpremise.

## Fase 6: Eliminar langextract-service

### 6.1 Eliminar directorio completo
**Eliminar**: `backend/microservices/langextract-service/`

### 6.2 Limpiar referencias
```bash
grep -r "langextract-service" backend/
grep -r "LANGEXTRACT_SERVICE" backend/
```

Eliminar cualquier referencia restante en .env, .env.example, README, etc.

## Secuencia de Implementacion

```
Fase 1 (Preparacion)          <- Sin cambios funcionales, backward compatible
   |
Fase 2 (LangExtractProvider)  <- Nuevo provider, se suma a los existentes
   |
Fase 3 (ID Documents)         <- Mover servicio de identidad
   |
Fase 4 (Clasificador)         <- Mejora clasificacion, opcional
   |
Fase 5 (Clientes + Compose)   <- Actualizar integraciones, quitar langextract-service de compose
   |
Fase 6 (Limpieza)             <- Eliminar langextract-service
```

**Punto de corte seguro**: Despues de Fase 2 se puede deployar. Langextract-service sigue corriendo pero es redundante. Fases 5-6 se hacen juntas en un commit.

## Archivos a Crear

| Archivo | Descripcion |
|---------|-------------|
| `intelligence-docs-service/app/providers/entities/langextract_provider.py` | Nuevo EntityProvider (unico extractor) |
| `intelligence-docs-service/app/providers/entities/few_shot_configs.py` | Configs few-shot extraidas |
| `intelligence-docs-service/app/providers/guardrails/spanish_id_validator.py` | Guardrail validador de DNI/NIE/CIF |
| `intelligence-docs-service/app/services/id_document_service.py` | Movido desde langextract-service |
| `intelligence-docs-service/app/api/identity.py` | Router para documentos de identidad |

## Archivos a Modificar

| Archivo | Cambio |
|---------|--------|
| `intelligence-docs-service/app/providers/base.py` | Agregar start_pos, end_pos, attributes a Entity. Eliminar EntityProvider de regex |
| `intelligence-docs-service/app/schemas/models.py` | Agregar campos a EntityResponse y EntitiesRequest |
| `intelligence-docs-service/app/pipeline/processor.py` | Mapear nuevos campos Entity -> EntityResponse + integrar guardrail post-extraccion |
| `intelligence-docs-service/app/pipeline/classifier.py` | Agregar Stage 3 LLM classification |
| `intelligence-docs-service/app/core/config.py` | Agregar settings de langextract |
| `intelligence-docs-service/app/main.py` | Registrar LangExtractProvider + identity router |
| `intelligence-docs-service/requirements.txt` | Agregar langextract[openai], pillow, mrz |
| `weaviate-service/app/clients/intelligence_client.py` | Agregar document_type y campos extendidos |
| `docker-compose.onpremise.yml` | Eliminar langextract-service, actualizar deps |

## Archivos a Eliminar

| Archivo | Razon |
|---------|-------|
| `langextract-service/` (directorio completo) | Consolidado en intelligence-docs-service |
| `intelligence-docs-service/app/providers/entities/sglang_ner.py` | Redundante — LangExtract cubre todas sus entidades |
| `intelligence-docs-service/app/providers/entities/vllm_ner.py` | Shim de backward-compat hacia sglang_ner |
| `intelligence-docs-service/app/providers/entities/regex_spanish.py` | Refactorizado a guardrail (`providers/guardrails/`) |
| `weaviate-service/app/services/rag/langextract_client.py` | Reemplazado por intelligence_client |

## Verificacion

Checklist post-implementacion:

- [ ] `curl http://intelligence-docs-service:8000/health` muestra `langextract` en providers.entities
- [ ] `POST /entities` con texto de contrato devuelve entidades con `provider=langextract`
- [ ] `POST /entities` con texto corto sigue devolviendo entidades regex (sin LLM)
- [ ] `POST /identity/extract` con imagen DNI funciona
- [ ] Pipeline de indexing en weaviate-service extrae entidades normalmente
- [ ] `docker compose up` arranca sin langextract-service
- [ ] No quedan referencias a `langextract-service` ni `LANGEXTRACT_SERVICE_URL` en el codigo
