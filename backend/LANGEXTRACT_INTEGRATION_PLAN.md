# Plan de Integración de LangExtract en NexusDocs360

## 🎯 Objetivos de la Integración

1. **Mejorar extracción de texto**: Reemplazar PyPDF2 con LangExtract para mejor precisión
2. **Extracción estructurada**: Obtener entidades, relaciones y metadatos automáticamente
3. **Mejor clasificación de documentos**: Usar LangExtract para detectar tipo de documento con mayor precisión
4. **Resúmenes inteligentes**: Generar resúmenes más contextuales y precisos
5. **Trazabilidad**: Mapear cada dato extraído a su ubicación en el documento original

## 📦 Instalación y Configuración

```bash
# Instalar LangExtract
pip install langextract

# Dependencias principales:
# - google-genai>=0.1.0
# - pydantic>=1.8.0
# - pandas>=1.3.0
# - numpy>=1.20.0
```

## 🔧 Puntos de Integración

### 1. **Servicio de Extracción de Documentos** (`async_document_service.py`)

**Actual:**
```python
def _extract_text_sync(self, contents: bytes, file_ext: str) -> Optional[str]:
    if file_ext == "pdf":
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(contents))
        # Extracción básica
```

**Con LangExtract:**
```python
import langextract as lx

async def _extract_with_langextract(self, contents: bytes, file_ext: str) -> Dict[str, Any]:
    # Definir prompt para extracción
    prompt = """
    Extract the following information:
    - Document type (contract, invoice, report, etc.)
    - Key parties/entities involved
    - Important dates and deadlines
    - Financial amounts if any
    - Main obligations or actions
    - Summary of document purpose
    """
    
    # Ejemplos para guiar el modelo
    examples = [
        lx.data.ExampleData(
            text="CONTRACT between Company A and Company B dated January 1, 2025",
            extractions=[
                lx.data.Extraction(
                    extraction_class="document_type",
                    extraction_text="CONTRACT",
                    attributes={"confidence": "high"}
                ),
                lx.data.Extraction(
                    extraction_class="party",
                    extraction_text="Company A",
                    attributes={"role": "first_party"}
                ),
                lx.data.Extraction(
                    extraction_class="party", 
                    extraction_text="Company B",
                    attributes={"role": "second_party"}
                ),
                lx.data.Extraction(
                    extraction_class="date",
                    extraction_text="January 1, 2025",
                    attributes={"type": "contract_date"}
                )
            ]
        )
    ]
    
    # Extraer con LangExtract
    result = lx.extract(
        text_or_documents=text,
        prompt_description=prompt,
        examples=examples,
        model="gemini-1.5-flash",  # O usar Ollama local
        extraction_passes=2,  # Múltiples pasadas para mejor recall
        max_char_buffer=10000  # Tamaño de chunk
    )
    
    return {
        "text": result.source_text,
        "extractions": result.extractions,
        "entities": self._group_extractions(result.extractions),
        "summary": self._generate_summary_from_extractions(result.extractions)
    }
```

### 2. **CAG Service** (`cag_service.py`)

**Integración con LangExtract para mejor análisis:**

```python
async def analyze_document_with_langextract(
    self,
    document_content: str,
    document_id: str,
    analysis_type: str = "comprehensive"
) -> Dict[str, Any]:
    
    # Usar LangExtract para extracción estructurada
    extraction_result = await self._extract_with_langextract(
        document_content, 
        analysis_type
    )
    
    # Enriquecer con CAG para análisis profundo
    enhanced_analysis = await self._enhance_with_cag(
        extraction_result,
        document_content
    )
    
    return {
        "document_type": extraction_result.get("document_type"),
        "confidence": extraction_result.get("confidence"),
        "entities": extraction_result.get("entities"),
        "relationships": extraction_result.get("relationships"),
        "key_points": extraction_result.get("key_points"),
        "summary": enhanced_analysis.get("summary"),
        "compliance_check": enhanced_analysis.get("compliance"),
        "risk_assessment": enhanced_analysis.get("risks")
    }
```

### 3. **Agent Router Service** (`agent_router_service.py`)

**Mejorar routing con extracciones precisas:**

```python
async def _analyze_with_langextract(
    self, 
    content: str, 
    filename: str
) -> Dict[str, Any]:
    
    # Extraer información estructurada
    result = await lx.extract(
        text_or_documents=content,
        prompt_description=self.ROUTING_PROMPT,
        examples=self.ROUTING_EXAMPLES,
        model="gemini-1.5-flash"
    )
    
    # Determinar tipo de documento basado en extracciones
    doc_type = self._determine_type_from_extractions(result.extractions)
    
    # Calcular confianza basada en cantidad y calidad de extracciones
    confidence = self._calculate_confidence(result.extractions)
    
    return {
        "document_type": doc_type,
        "confidence": confidence,
        "key_entities": result.entities,
        "requires_signature": self._check_signature_requirement(result),
        "compliance_needed": self._check_compliance_requirement(result)
    }
```

### 4. **Nuevo Servicio: LangExtract Service**

Crear un microservicio dedicado para LangExtract:

```python
# backend/microservices/langextract-service/app/main.py

from fastapi import FastAPI
import langextract as lx
from typing import Dict, Any, List

app = FastAPI(title="LangExtract Service")

class LangExtractService:
    def __init__(self):
        self.extraction_configs = {
            "contract": self._get_contract_config(),
            "invoice": self._get_invoice_config(),
            "report": self._get_report_config(),
            "general": self._get_general_config()
        }
    
    async def extract_structured_data(
        self,
        text: str,
        document_type: str = "general"
    ) -> Dict[str, Any]:
        
        config = self.extraction_configs.get(
            document_type, 
            self.extraction_configs["general"]
        )
        
        result = await lx.extract(
            text_or_documents=text,
            prompt_description=config["prompt"],
            examples=config["examples"],
            model=config["model"],
            extraction_passes=config.get("passes", 2),
            max_char_buffer=config.get("buffer_size", 10000)
        )
        
        # Generar visualización HTML
        html_viz = lx.visualize(result)
        
        return {
            "extractions": result.extractions,
            "entities": self._group_by_class(result.extractions),
            "visualization_html": html_viz,
            "source_mapping": result.source_spans
        }
    
    def _get_contract_config(self) -> Dict:
        return {
            "prompt": """
            Extract from contracts:
            - Parties involved with their roles
            - Contract terms and conditions
            - Payment terms and amounts
            - Important dates and deadlines
            - Obligations and deliverables
            - Termination clauses
            - Legal jurisdiction
            """,
            "examples": [...],  # Contract-specific examples
            "model": "gemini-1.5-flash",
            "passes": 3,
            "buffer_size": 15000
        }
```

## 🚀 Plan de Implementación

### Fase 1: Setup y Testing (1-2 días)
1. Instalar LangExtract en entorno de desarrollo
2. Configurar API keys para Gemini
3. Crear scripts de prueba con documentos de ejemplo
4. Validar extracción con diferentes tipos de documentos

### Fase 2: Integración Básica (2-3 días)
1. Integrar LangExtract en `async_document_service.py`
2. Reemplazar extracción de texto actual
3. Actualizar proceso de generación de resúmenes
4. Testing con documentos existentes

### Fase 3: Microservicio Dedicado (3-4 días)
1. Crear `langextract-service` en microservicios
2. Implementar API endpoints para extracción
3. Integrar con docker-compose
4. Conectar con servicios existentes

### Fase 4: Mejoras Avanzadas (2-3 días)
1. Implementar visualización HTML de extracciones
2. Mejorar routing de agentes con datos estructurados
3. Añadir extracción de relaciones entre entidades
4. Optimizar para documentos largos

### Fase 5: Optimización y Producción (2-3 días)
1. Configurar caché para extracciones
2. Implementar procesamiento por lotes
3. Añadir métricas y monitoreo
4. Documentación y pruebas finales

## 📊 Beneficios Esperados

1. **Mayor Precisión**: 
   - Extracción estructurada con grounding preciso
   - Mejor detección de tipo de documento
   - Reducción de errores en clasificación

2. **Más Información Extraída**:
   - Entidades y sus atributos
   - Relaciones entre entidades
   - Fechas, montos, obligaciones específicas

3. **Mejor UX**:
   - Visualización HTML interactiva
   - Trazabilidad de cada extracción
   - Resúmenes más contextuales

4. **Escalabilidad**:
   - Procesamiento paralelo de documentos largos
   - Chunking inteligente
   - Múltiples pasadas para mejor recall

## 🔧 Configuración Docker

```yaml
# docker-compose.yml addition
langextract-service:
  build: ./microservices/langextract-service
  ports:
    - "8009:8009"
  environment:
    - GEMINI_API_KEY=${GEMINI_API_KEY}
    - OLLAMA_HOST=http://ollama:11434
  depends_on:
    - ollama
  volumes:
    - ./microservices/langextract-service:/app
```

## 📝 Ejemplo de Uso

```python
# Ejemplo de uso en el flujo actual
async def process_document_with_langextract(document_id: str):
    # 1. Obtener documento
    doc = await get_document(document_id)
    
    # 2. Extraer con LangExtract
    extraction_result = await langextract_service.extract(
        text=doc.content,
        document_type="auto"  # Auto-detectar
    )
    
    # 3. Guardar extracciones estructuradas
    await save_extractions(document_id, extraction_result)
    
    # 4. Actualizar routing basado en extracciones
    routing = await update_routing_with_extractions(
        document_id, 
        extraction_result
    )
    
    # 5. Generar visualización
    viz_url = await generate_visualization(extraction_result)
    
    return {
        "document_id": document_id,
        "type": extraction_result["document_type"],
        "entities": extraction_result["entities"],
        "visualization": viz_url,
        "routing": routing
    }
```

## 🎯 KPIs para Medir Éxito

1. **Precisión de clasificación**: >95% (actual: ~85%)
2. **Entidades extraídas por documento**: >10 (actual: 0)
3. **Tiempo de procesamiento**: <5s por documento
4. **Recall de información clave**: >90%
5. **Satisfacción del usuario**: Medida por feedback

## 📚 Recursos

- [GitHub LangExtract](https://github.com/google/langextract)
- [Documentación Oficial](https://langextract.io/)
- [Paper de investigación](https://arxiv.org/abs/langextract)
- [Ejemplos de uso](https://github.com/google/langextract/tree/main/examples)