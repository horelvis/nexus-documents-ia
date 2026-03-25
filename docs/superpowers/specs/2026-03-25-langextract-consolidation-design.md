# Consolidacion de LangExtract en intelligence-docs-service

**Fecha**: 2026-03-25
**Estado**: Propuesta
**Autor**: Equipo de arquitectura

## 1. Contexto y Problema

Actualmente la extraccion de entidades esta fragmentada en 3 capas independientes:

1. **`intelligence-docs-service/providers/entities/regex_spanish.py`** — Regex para DNI/NIE/CIF con validacion de checksum. Sin LLM, siempre disponible.

2. **`intelligence-docs-service/providers/entities/sglang_ner.py`** — NER via SGLang (OpenAI-compatible). Extrae PERSON, ORGANIZATION, DATE, AMOUNT, LOCATION. Trunca a 4000 chars.

3. **`langextract-service/` (microservicio standalone, puerto 8000)** — Usa la libreria `langextract` (v1.1.1) con configuraciones few-shot para extraccion estructurada. Soporta deteccion de tipo de documento, extraccion de documentos de identidad (doctr OCR), y entidades con source grounding (indices de caracter). Configurado para Ollama/Gemini/OpenAI como backend LLM.

Ademas, **`weaviate-service/app/services/rag/langextract_client.py`** es un cliente HTTP que llama al langextract-service y **duplica** la extraccion regex de DNI/NIE/CIF.

### Problemas

- **Duplicacion**: DNI/NIE/CIF regex existe en 3 sitios (regex_spanish.py, langextract_client.py, y dentro de langextract-service).
- **Redundancia LLM**: `sglang_ner.py` extrae PERSON, ORG, DATE, AMOUNT, LOCATION con un prompt generico. LangExtract extrae las mismas entidades y mas (atributos, source grounding, few-shot por tipo de documento). Tener dos capas LLM para el mismo trabajo es innecesario.
- **Microservicio innecesario**: langextract-service es un wrapper HTTP fino sobre la libreria `langextract`. No necesita ser un servicio separado.
- **Complejidad operativa**: Un servicio Docker mas que mantener, con su propio healthcheck, dependencias y configuracion.
- **Desaprovechamiento de SGLang**: El langextract-service esta configurado para Ollama pero on-premise ya tenemos SGLang con Qwen3.5-9B.
- **Perdida de source grounding**: La Entity dataclass de intelligence-docs no tiene `start_pos`/`end_pos`, perdiendo informacion valiosa de langextract.
- **Inconsistencia en clasificacion**: Hay dos clasificadores independientes: uno heuristico en intelligence-docs y otro LLM-based en langextract-service.

## 2. Solucion Propuesta

Consolidar toda la logica de `langextract-service` dentro de `intelligence-docs-service` como un nuevo `EntityProvider` llamado `LangExtractProvider`. Eliminar el microservicio standalone y `sglang_ner.py` (redundante — LangExtract cubre todas sus entidades y mas).

### 2.1 Arquitectura Objetivo

```
intelligence-docs-service (puerto 8000)
  providers/entities/
    langextract_provider.py  (NUEVO — extractor principal, reemplaza sglang_ner + langextract-service)
  providers/guardrails/
    spanish_id_validator.py  (REFACTORIZADO desde regex_spanish.py — guardrail post-extraccion)
  providers/extraction/
    ... (docling, glm-ocr, tika — sin cambios)
  pipeline/
    processor.py           (EXTENDIDO — paso de validacion post-entidades)
    classifier.py          (EXTENDIDO — clasificacion LLM via langextract)
  services/
    id_document_service.py (MOVIDO desde langextract-service)
  configs/
    few_shot_configs.py    (NUEVO — configs extraidos de extractor.py)
```

**Pipeline de entidades**: `langextract (extraccion) -> spanish_id_validator (guardrail)`.

- LangExtract es el **unico extractor**: PERSON, ORG, DATE, AMOUNT, DNI, NIE, CIF, etc.
- `spanish_id_validator` es un **guardrail post-extraccion** que:
  1. Valida checksums de DNI/NIE extraidos por LangExtract (descarta alucinaciones)
  2. Hace scan regex del texto para encontrar DNI/NIE/CIF que LangExtract pudo omitir
  3. Enriquece entidades validadas con `confidence=0.95` (checksum verificado)
- Si SGLang esta caido, el guardrail sigue escaneando el texto con regex como fallback.

### 2.2 Eliminacion de providers obsoletos

Se eliminan 3 providers:
- `sglang_ner.py` — LangExtract cubre todas sus entidades con mayor precision (few-shot, source grounding, multi-pass)
- `vllm_ner.py` — shim de backward-compatibility que apuntaba a sglang_ner
- `regex_spanish.py` como EntityProvider — se refactoriza a guardrail (ver 2.4)

### 2.3 LangExtractProvider

Nuevo `EntityProvider` unico que:

- Importa `langextract` directamente (sin HTTP).
- Usa SGLang como backend LLM via `model_url` (OpenAI-compatible endpoint).
- Mantiene todas las configuraciones few-shot: contract, invoice, report, nomina, modelo_111, modelo_190, modelo_303, certificado, comunicacion_itss, general.
- Convierte las extracciones de langextract (`Extraction` con `extraction_class`, `extraction_text`, `attributes`, `source_indices`) a `Entity` enriquecidas.
- Es el **unico extractor** de entidades en el pipeline.

### 2.4 Spanish ID Validator (Guardrail)

`regex_spanish.py` se refactoriza de `EntityProvider` a guardrail post-extraccion:

```python
class SpanishIdValidator:
    """Guardrail post-extraccion para IDs espanoles."""

    def validate_and_enrich(self, entities: list[Entity], text: str) -> list[Entity]:
        """
        1. Validar checksums de DNI/NIE extraidos por LangExtract
           - Si checksum invalido: bajar confidence a 0.3, marcar en attributes
           - Si checksum valido: subir confidence a 0.95
        2. Scan regex del texto para encontrar DNI/NIE/CIF omitidos
           - Agregar como entidades nuevas con provider="regex_guardrail"
        3. Retornar lista enriquecida
        """
```

**Beneficios del patron guardrail**:
- Detecta alucinaciones del LLM (DNI con checksum invalido)
- Captura IDs que el LLM pudo omitir (safety net)
- Funciona sin LLM (si SGLang cae, el guardrail sigue escaneando)
- Enriquece con confidence verificada (0.95 para checksum valido vs 0.8 generico)

### 2.5 Extension del Dataclass Entity

```python
@dataclass
class Entity:
    type: str
    value: str
    provider: str
    confidence: float = 1.0
    start_pos: Optional[int] = None  # NUEVO
    end_pos: Optional[int] = None    # NUEVO
    attributes: dict[str, Any] = field(default_factory=dict)  # NUEVO
```

Los campos nuevos son opcionales. Solo `langextract_provider` los rellena. El guardrail los lee para validar.

### 2.6 Clasificacion Mejorada

El clasificador actual (`classifier.py`) es puramente heuristico. La funcion `detect_document_type()` del langextract-service es LLM-based y mas precisa. Plan:

- Extender `classifier.py` con una etapa LLM opcional usando langextract.
- Cadena: heuristica filename -> heuristica contenido -> LLM langextract (si disponible).
- El resultado se usa para seleccionar la configuracion few-shot apropiada en `LangExtractProvider`.

### 2.7 Servicio de Documentos de Identidad

`id_document_service.py` se mueve a `intelligence-docs-service/app/services/`. Requiere dependencias adicionales (`python-doctr[torch]`, `pillow`, `mrz`). Las APIs (`/identity/extract`, `/identity/health`) se mueven a un nuevo router en intelligence-docs.

### 2.8 Cliente intelligence_client

El `intelligence_client.py` en weaviate-service ya llama a intelligence-docs-service para entidades via `/entities`. La consolidacion enriquece el response — no requiere cambios en el cliente salvo extender el formato de respuesta para incluir `start_pos`, `end_pos`, y `attributes`.

## 3. Impacto en Indexing Pipeline

Actualmente el pipeline de indexing en weaviate-service tiene dos flujos de entidades:

1. **Stage 4.5**: `intelligence_client.extract_entities()` -> llama a intelligence-docs-service `/entities`
2. **Stage 5**: Knowledge extraction usa las entidades del paso anterior.

Tras la consolidacion:
- El flujo no cambia. `intelligence_client.extract_entities()` sigue llamando a `/entities` de intelligence-docs-service.
- La respuesta es mas rica (incluye entidades de langextract con few-shot).
- Se elimina `langextract_client.py` (ya no se necesita).

## 4. Configuracion

Nuevas variables de entorno en intelligence-docs-service:

| Variable | Default | Descripcion |
|----------|---------|-------------|
| `LANGEXTRACT_ENABLED` | `true` | Activar provider langextract |
| `LANGEXTRACT_EXTRACTION_PASSES` | `2` | Pasadas de extraccion |
| `LANGEXTRACT_MAX_CHAR_BUFFER` | `10000` | Max chars por chunk |
| `LANGEXTRACT_CONFIDENCE_THRESHOLD` | `0.7` | Umbral minimo de confianza |
| `ID_DOCUMENT_ENABLED` | `true` | Activar servicio de documentos de identidad |

Se reutilizan las variables existentes `SGLANG_BASE_URL` y `SGLANG_MODEL` para el backend LLM.

## 5. Dependencias

Nuevas en `intelligence-docs-service/requirements.txt`:

```
langextract[openai]==1.1.1
pillow>=10.0.0
mrz>=0.6.2
```

**Nota**: `python-doctr[torch]` es pesada (~500MB+ con modelos). Se mantiene como dependencia opcional con lazy import (como ya hace langextract-service). Solo se carga si se usa `/identity/extract`.

## 6. Eliminaciones

- **Eliminar**: `backend/microservices/langextract-service/` (directorio completo)
- **Eliminar**: `backend/microservices/intelligence-docs-service/app/providers/entities/sglang_ner.py` (redundante con LangExtract)
- **Eliminar**: `backend/microservices/intelligence-docs-service/app/providers/entities/vllm_ner.py` (shim de backward-compat que apuntaba a sglang_ner)
- **Refactorizar**: `regex_spanish.py` de EntityProvider a guardrail (`providers/guardrails/spanish_id_validator.py`)
- **Eliminar**: `backend/microservices/weaviate-service/app/services/rag/langextract_client.py`
- **Eliminar**: Seccion `langextract-service` en `docker-compose.onpremise.yml`
- **Eliminar**: Seccion `langextract-service` en `docker-compose.yml.saas`
- **Eliminar**: Referencia `LANGEXTRACT_SERVICE_URL` en todos los compose y .env
- **Eliminar**: Dependencia `langextract-service: condition: service_healthy` en weaviate-service

## 7. Riesgos y Mitigaciones

| Riesgo | Impacto | Mitigacion |
|--------|---------|------------|
| langextract lib incompatible con SGLang | Alto — extraccion falla | La lib usa `model_url` (Ollama-compatible). SGLang expone `/chat/completions` que Ollama tambien usa. Probar con provider "ollama" apuntando a SGLang. |
| python-doctr aumenta imagen Docker | Medio — mayor tamano | Lazy imports (ya implementados en langextract-service). Solo se carga si se usa `/identity/extract`. |
| Regresion en indexing pipeline | Alto | No cambiar la interfaz de `intelligence_client.extract_entities()`. Agregar entidades langextract como complemento a las existentes. |
| Timeout por pasadas multiples de langextract | Medio | Configurar `LANGEXTRACT_EXTRACTION_PASSES=1` por defecto en pipeline de indexing. Usar 2 solo para extraccion dedicada. |
| Few-shot configs desincronizados | Bajo | Extraer a modulo separado (`few_shot_configs.py`), facil de mantener. |
