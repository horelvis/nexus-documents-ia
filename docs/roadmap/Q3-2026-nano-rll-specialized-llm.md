# Análisis Técnico: nano-rll - LLM Especializado en Gestión Documental

**Fecha**: Enero 2026
**Prioridad**: Q3 2026 - Desarrollo en paralelo con LoRA
**Estado**: Propuesta para evaluación
**Autores**: Equipo de Arquitectura NouxCubeIA

---

## Resumen Ejecutivo

Este documento propone el desarrollo de **nano-rll** (nano Records & Legal Language model), un LLM entrenado desde cero especializado en gestión documental y derecho español, utilizando el pipeline de entrenamiento de **nanochat** de Karpathy.

### Decisión Recomendada

| Aspecto | Recomendación |
|---------|---------------|
| **Implementar** | Sí, desarrollo en Q3 2026 |
| **Prioridad** | Media-Alta |
| **Esfuerzo estimado** | 10 semanas |
| **Costo estimado** | $300 (PoC) - $3,000 (Producción) |
| **ROI esperado** | Especialización profunda sin pérdida conversacional |

---

## 1. Contexto del Problema

### 1.1 Diferencia Clave vs LoRA (Q2 2026)

| Aspecto | LoRA (Q2 2026) | nano-rll (Q3 2026) |
|---------|----------------|---------------------|
| **Enfoque** | Adaptar modelo genérico | Entrenar desde cero |
| **Capacidad conversacional** | Riesgo de pérdida | Mantiene (SFT incluido) |
| **Especialización** | Superficie (capas adaptadoras) | Profunda (todo el modelo) |
| **Costo** | ~$200 | ~$3,000 |
| **Tiempo** | 8 semanas | 10 semanas |
| **Dependencia externa** | Modelo base Qwen3 | Modelo propio |

### 1.2 Justificación

nano-rll ofrece especialización profunda SIN perder capacidad conversacional porque el pipeline incluye las 4 fases: **Pretraining → Midtraining → SFT → RL**.

### 1.3 Casos de Uso Objetivo

| Caso | Descripción | Beneficio |
|------|-------------|-----------|
| **Análisis de contratos** | Extracción de cláusulas con citas exactas | Citación precisa de artículos |
| **Compliance RGPD** | Verificación normativa automática | Detección de incumplimientos |
| **NER Legal** | Extracción de entidades jurídicas | Precisión en datos estructurados |
| **Consultas laborales** | Interpretación de convenios y ET | Respuestas especializadas |

---

## 2. Arquitectura nano-rll

### 2.1 Configuraciones de Modelo

| Config | Parámetros | Capas | Context | VRAM | Uso |
|--------|------------|-------|---------|------|-----|
| **nano-rll-560M** | 560M | 20 | 4K | ~4GB | PoC |
| **nano-rll-1.1B** | 1.1B | 26 | 8K | ~8GB | Dev |
| **nano-rll-2.2B** | 2.2B | 34 | 16K | ~16GB | Producción |

### 2.2 Pipeline de Entrenamiento (nanochat style)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PIPELINE DE ENTRENAMIENTO nano-rll                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   FASE 1: PRETRAINING (20B tokens)                                          │
│   ┌─────────────────────────────────────────────────────────────┐           │
│   │ 50% General: FineWeb-ES, Wikipedia ES                       │           │
│   │ 50% Legal: BOE (2000-2024), EUR-Lex, MultiEURLEX           │           │
│   └─────────────────────────────────────────────────────────────┘           │
│                           │                                                  │
│                           ▼                                                  │
│   FASE 2: MIDTRAINING (1B tokens)                                           │
│   ┌─────────────────────────────────────────────────────────────┐           │
│   │ SmolTalk-ES (conversacional)                                │           │
│   │ Legal QA Pairs (sintético)                                  │           │
│   │ Document Analysis (sintético)                               │           │
│   └─────────────────────────────────────────────────────────────┘           │
│                           │                                                  │
│                           ▼                                                  │
│   FASE 3: SFT (30K ejemplos)                                                │
│   ┌─────────────────────────────────────────────────────────────┐           │
│   │ Contract Analysis                                           │           │
│   │ Legal NER (MAPA dataset)                                    │           │
│   │ Compliance Check                                            │           │
│   │ Identity Emma + tono profesional                            │           │
│   └─────────────────────────────────────────────────────────────┘           │
│                           │                                                  │
│                           ▼                                                  │
│   FASE 4: RL                                                                │
│   ┌─────────────────────────────────────────────────────────────┐           │
│   │ Reward: Citación correcta de artículos                      │           │
│   │ Reward: JSON válido                                         │           │
│   │ Penalización: Alucinaciones legales                         │           │
│   └─────────────────────────────────────────────────────────────┘           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Fuentes de Datos

### 3.1 Datos Públicos

| Fuente | Tipo | Tokens Est. | Acceso |
|--------|------|-------------|--------|
| **BOE API** | Legislación española | ~3B | `boe.es/datosabiertos/api` |
| **EUR-Lex** | Derecho EU | ~2B | Data dump disponible |
| **MultiEURLEX** | Corpus legal multilingüe | 65K docs | HuggingFace |
| **FineWeb-ES** | Web general español | ~10B | HuggingFace |
| **Wikipedia ES** | Enciclopedia | ~2B | Dumps disponibles |

### 3.2 Datos Sintéticos (GPT-4/Claude)

```yaml
# Prompts para generación de datos sintéticos
contract_analysis:
  - Análisis de contratos con citas exactas a Código Civil
  - Extracción de cláusulas y riesgos
  - Referencias a artículos específicos

legal_qa:
  - Pares pregunta-respuesta sobre ET, LGSS
  - Consultas sobre RGPD, LOPDGDD
  - Interpretación de convenios colectivos

compliance_check:
  - Verificación de cumplimiento normativo
  - Detección de cláusulas abusivas
  - Análisis de protección de datos
```

### 3.3 Infusión de Identidad Emma (nanochat methodology)

Basado en la [discusión #139 de nanochat](https://github.com/karpathy/nanochat/discussions/139), se implementará una metodología específica para codificar la identidad y comportamiento de Emma en el modelo.

#### Proceso de Generación

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PIPELINE DE INFUSIÓN DE IDENTIDAD                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   1. DEFINICIÓN DE IDENTIDAD (prompt en lenguaje natural)                   │
│   ┌─────────────────────────────────────────────────────────────┐           │
│   │ "Emma es una asistente de gestión documental especializada  │           │
│   │  en derecho español. Responde de forma profesional, cita    │           │
│   │  artículos exactos, y nunca inventa información legal."     │           │
│   └─────────────────────────────────────────────────────────────┘           │
│                           │                                                  │
│                           ▼                                                  │
│   2. GENERACIÓN SINTÉTICA (gen_synthetic_data.py)                           │
│   ┌─────────────────────────────────────────────────────────────┐           │
│   │ - 1000+ conversaciones multi-turno                          │           │
│   │ - Generadas via API (GPT-4/Claude) en minutos               │           │
│   │ - Formato: pares Usuario-Asistente en jsonl                 │           │
│   └─────────────────────────────────────────────────────────────┘           │
│                           │                                                  │
│                           ▼                                                  │
│   3. INTEGRACIÓN EN PIPELINE                                                │
│   ┌─────────────────────────────────────────────────────────────┐           │
│   │ - Midtraining: mezcla con datos conversacionales            │           │
│   │ - SFT: CustomJSON task desde archivo identity.jsonl         │           │
│   │ - Resultado: modelo "sabe" que es Emma                      │           │
│   └─────────────────────────────────────────────────────────────┘           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Script de Generación

```python
# training/data/gen_emma_identity.py
# Basado en nanochat dev/gen_synthetic_data.py

EMMA_IDENTITY_PROMPT = """
Eres Emma, asistente de gestión documental de NouxCubeIA.

IDENTIDAD:
- Nombre: Emma
- Rol: Asistente especializada en gestión documental y derecho español
- Creador: NouxCubeIA
- Tono: Profesional, preciso, servicial

COMPORTAMIENTO:
- Siempre citas artículos exactos (ej: "Art. 1254 del Código Civil")
- Nunca inventas información legal
- Si no sabes algo, lo admites claramente
- Respondes en español formal

Genera una conversación multi-turno donde el usuario pregunta sobre
documentos legales y Emma responde de forma profesional.
"""

# Genera 1000 conversaciones en ~5 minutos via API
conversations = generate_synthetic_conversations(
    prompt=EMMA_IDENTITY_PROMPT,
    n_conversations=1000,
    api="openrouter",  # o "openai", "anthropic"
    model="gpt-4o"
)

# Exporta a jsonl para CustomJSON task
save_to_jsonl(conversations, "data/emma_identity.jsonl")
```

#### Técnica de Diversidad: Persona Sampling

Para mejorar la diversidad semántica de las conversaciones generadas (basado en comentario de @Murgio en la discusión):

```python
# Muestreo de personas para mayor diversidad
LEGAL_PERSONAS = [
    "Abogado laboralista con 20 años de experiencia",
    "Directora de RRHH de una PYME",
    "Autónomo con dudas sobre facturación",
    "Empresario preocupado por RGPD",
    "Estudiante de derecho preparando oposiciones",
    "Gestor administrativo de una asesoría",
    "Responsable de compliance de multinacional",
    "Propietario de inmueble con conflicto de arrendamiento"
]

# Genera conversaciones desde múltiples perspectivas
for persona in LEGAL_PERSONAS:
    prompt = f"El usuario es: {persona}\n{EMMA_IDENTITY_PROMPT}"
    conversations.extend(generate_synthetic_conversations(prompt, n=125))

# Resultado: 1000 conversaciones con alta diversidad (1-Self-BLEU > 0.85)
```

#### Datasets de Identidad Resultantes

| Dataset | Ejemplos | Integración | Propósito |
|---------|----------|-------------|-----------|
| `emma_identity.jsonl` | 1,000 | Midtraining + SFT | Identidad base |
| `emma_legal_qa.jsonl` | 2,000 | SFT | Conocimiento legal |
| `emma_document_analysis.jsonl` | 1,000 | SFT | Análisis documental |
| `emma_compliance.jsonl` | 500 | SFT | Verificación normativa |

**Costo estimado de generación**: ~$15-20 (1000 conversaciones via GPT-4o)

---

## 4. Estimación de Costos

### 4.1 PoC (560M) - ~$300

| Fase | Tiempo | GPUs | Costo |
|------|--------|------|-------|
| Pretraining (5B tokens) | 8h | 8xH100 | $200 |
| Midtraining | 1h | 8xH100 | $25 |
| SFT | 1h | 8xH100 | $25 |
| RL | 2h | 8xH100 | $50 |
| **Total** | **12h** | | **$300** |

### 4.2 Producción (2.2B) - ~$3,000

| Fase | Tiempo | GPUs | Costo |
|------|--------|------|-------|
| Pretraining (40B tokens) | 100h | 8xH100 | $2,400 |
| Midtraining | 5h | 8xH100 | $120 |
| SFT | 3h | 8xH100 | $75 |
| RL | 10h | 8xH100 | $240 |
| Evaluation | 5h | 8xH100 | $120 |
| **Total** | **123h** | | **$2,955** |

### 4.3 Proveedores Recomendados

| Proveedor | Costo/hora (8xH100) | Disponibilidad |
|-----------|---------------------|----------------|
| Lambda Labs | $24/h | Bajo demanda |
| RunPod | $16-20/h | Spot instances |
| AWS p5.48xlarge | $32/h | Reserved |

---

## 5. Estructura de Directorios

```
training/                           # NUEVO directorio
├── nano_rll/
│   ├── gpt.py                     # Arquitectura del modelo
│   ├── tokenizer.py               # BPE con tokens legales
│   ├── dataset.py                 # Data loading
│   └── engine.py                  # Inferencia con KV cache
├── scripts/
│   ├── base_train.py              # Fase 1: Pretraining
│   ├── mid_train.py               # Fase 2: Midtraining
│   ├── chat_sft.py                # Fase 3: SFT
│   ├── chat_rl.py                 # Fase 4: RL
│   └── export_vllm.py             # Export para vLLM
├── data/
│   ├── downloaders/
│   │   ├── boe_downloader.py      # Script BOE API
│   │   └── eurlex_downloader.py   # Script EUR-Lex
│   └── prompts/
│       └── synthetic_data.yaml    # Prompts para datos sintéticos
├── configs/
│   ├── nano_rll_560m.yaml         # Config PoC
│   └── nano_rll_2b.yaml           # Config producción
└── docker/
    └── Dockerfile.training        # Container de entrenamiento
```

---

## 6. Integración con Emma

### 6.1 Arquitectura de Routing

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ARQUITECTURA DUAL-MODEL ROUTING                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Request                                                                    │
│         │                                                                    │
│         ▼                                                                    │
│   ┌─────────────────────────────────────────────────────────────┐           │
│   │                     ModelRouter                              │           │
│   │                                                              │           │
│   │   legal_keywords = ["contrato", "cláusula", "artículo",     │           │
│   │                     "ley", "rgpd", "convenio"]              │           │
│   │                                                              │           │
│   │   if any(kw in query.lower() for kw in legal_keywords):     │           │
│   │       return "nano-rll-2b"    ────────────────────┐         │           │
│   │   else:                                           │         │           │
│   │       return "Qwen/Qwen3-4B"  ─────┐              │         │           │
│   └────────────────────────────────────│──────────────│─────────┘           │
│                                        │              │                      │
│                                        ▼              ▼                      │
│   ┌─────────────────────────┐   ┌─────────────────────────┐                 │
│   │      vLLM General       │   │      vLLM Legal         │                 │
│   │      Qwen/Qwen3-4B      │   │      nano-rll-2b        │                 │
│   │      Port 8000          │   │      Port 8001          │                 │
│   └─────────────────────────┘   └─────────────────────────┘                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Archivos a Modificar

| Archivo | Acción | Descripción |
|---------|--------|-------------|
| `weaviate-service/app/agents/model_client.py` | Modificar | Agregar routing a nano-rll |
| `weaviate-service/app/agents/config.py` | Modificar | Config nano-rll |
| `backend/docker/docker-compose.yml` | Modificar | Agregar servicio vllm-legal |

### 6.3 Configuración docker-compose

```yaml
# docker-compose.yml - Nuevo servicio
services:
  vllm-legal:
    image: vllm/vllm-openai:v0.9.0
    runtime: nvidia
    command:
      - "--model=/models/nano-rll-2b"
      - "--max-model-len=16384"
      - "--port=8000"
    volumes:
      - nano_rll_models:/models
    environment:
      - NVIDIA_VISIBLE_DEVICES=1  # Segunda GPU
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

volumes:
  nano_rll_models:
```

---

## 7. Métricas de Evaluación

### 7.1 Benchmarks Cuantitativos

| Benchmark | Tipo | Target | Baseline |
|-----------|------|--------|----------|
| MultiEURLEX-ES | Clasificación | F1 > 0.80 | Qwen3: 0.65 |
| Legal NER (MAPA) | Extracción entidades | F1 > 0.85 | Qwen3: 0.70 |
| Citation Accuracy | Factual | Precision > 0.90 | Qwen3: 0.60 |
| Conversation Quality | Human eval | 4/5 | Qwen3: 4/5 |

### 7.2 Métricas de Éxito

- [ ] nano-rll-2b supera Qwen3 en benchmarks legales por +15pp
- [ ] Mantiene capacidad conversacional (>3.8/5 en human eval)
- [ ] Latencia comparable a Qwen3 (<2.5s por respuesta)
- [ ] Citación correcta de artículos en >90% de respuestas legales

---

## 8. Cronograma Q3 2026

```
Q3 2026 (Julio - Septiembre)
│
├── Semanas 1-2: Preparación
│   ├── Setup Lambda Labs / RunPod
│   ├── Descargar BOE, EUR-Lex, FineWeb-ES
│   ├── Entrenar tokenizer con vocabulario legal
│   └── Configurar pipeline de datos
│
├── Semanas 3-4: PoC (560M)
│   ├── Pretraining 5B tokens
│   ├── Midtraining + SFT
│   ├── Validación inicial
│   └── Comparación con Qwen3 en subset
│
├── Semanas 5-8: Producción (2.2B)
│   ├── Pretraining 40B tokens
│   ├── Midtraining con datos conversacionales
│   ├── SFT con identidad Emma
│   ├── RL con rewards de citación
│   └── Benchmarks completos
│
└── Semanas 9-10: Integración
    ├── Export a formato vLLM
    ├── Modificar model_client.py
    ├── Implementar routing
    ├── A/B testing con usuarios piloto
    └── Documentación técnica
```

---

## 9. Análisis de Riesgos

### 9.1 Riesgos Identificados

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| Pérdida capacidad conversacional | Media | Alto | 50% datos generales en pretraining |
| Datos insuficientes | Media | Alto | Sintéticos + EUR-Lex como backup |
| Costos excedidos | Baja | Medio | Empezar con PoC 560M |
| Alucinaciones legales | Alta | Alto | RL con reward de citaciones |
| No supera LoRA | Media | Medio | Mantener LoRA como fallback |

### 9.2 Plan de Contingencia

1. **Si PoC no mejora sobre Qwen3**: Cancelar y enfocar en LoRA (Q2)
2. **Si costos exceden presupuesto**: Usar configuración 1.1B en lugar de 2.2B
3. **Si tiempo excede 10 semanas**: Priorizar SFT sobre RL para MVP

---

## 10. Dependencias con Otros Proyectos

| Proyecto | Relación | Impacto |
|----------|----------|---------|
| **Q1: RLM Context Extension** | Independiente | Pueden coexistir |
| **Q2: LoRA Continuous Learning** | Paralelo/Alternativa | Comparten infraestructura |
| **Emma Learning System** | Sinergia | Comparte datos de feedback |
| **Knowledge Extraction** | Entrada | Datos para entrenamiento |

---

## 11. Estrategia de Ejecución Recomendada

### 11.1 Ejecución Paralela con LoRA

```
         Q2 2026                    Q3 2026                    Q4 2026
            │                          │                          │
    ┌───────┴───────┐          ┌───────┴───────┐          ┌───────┴───────┐
    │               │          │               │          │               │
    │   LoRA        │          │   nano-rll    │          │  Evaluación   │
    │   (bajo       │ ───────► │   (paralelo)  │ ───────► │  y Migración  │
    │   riesgo)     │          │               │          │               │
    │               │          │               │          │               │
    └───────────────┘          └───────────────┘          └───────────────┘
            │                          │                          │
            ▼                          ▼                          ▼
    Adaptadores de           Modelo especializado        Si nano-rll > LoRA:
    dominio funcionales      entrenado                   migrar a nano-rll
```

### 11.2 Criterios de Decisión Q4

| Métrica | Umbral para migrar a nano-rll |
|---------|-------------------------------|
| Benchmark legal | nano-rll > LoRA en +10pp |
| Capacidad conversacional | nano-rll >= LoRA |
| Latencia | nano-rll <= LoRA + 20% |
| Costo operativo | Comparable |

---

## 12. Verificación Post-Implementación

### 12.1 Post-Entrenamiento

```bash
# Evaluar en MultiEURLEX
python training/scripts/eval_legal.py --checkpoint /models/nano-rll-2b

# Comparar con Qwen3
python training/scripts/compare_models.py --baseline Qwen/Qwen3-4B

# Verificar capacidad conversacional
python training/scripts/eval_conversation.py --checkpoint /models/nano-rll-2b
```

### 12.2 Post-Integración

```bash
# Test de routing
curl -X POST http://localhost:8007/api/emma/query \
  -d '{"query": "Analiza las cláusulas de penalización", "tenant_id": "test"}'

# Verificar modelo usado en logs
docker logs weaviate-service | grep "Using model"

# A/B test
python scripts/ab_test.py --variant nano-rll --control qwen3 --queries legal_queries.json
```

---

## 13. Recursos y Referencias

### 13.1 Repositorios Clave

- [nanochat (Karpathy)](https://github.com/karpathy/nanochat) - Pipeline de entrenamiento
- [nanochat Discussion #139: Identity Infusion](https://github.com/karpathy/nanochat/discussions/139) - Metodología de inyección de identidad via datos sintéticos
- [nanoGPT (Karpathy)](https://github.com/karpathy/nanoGPT) - Arquitectura base
- [MultiEURLEX](https://huggingface.co/datasets/multi_eurlex) - Benchmark legal

### 13.2 Datasets

- [BOE Datos Abiertos](https://www.boe.es/datosabiertos/) - Legislación española
- [EUR-Lex](https://eur-lex.europa.eu/homepage.html) - Derecho europeo
- [FineWeb](https://huggingface.co/datasets/HuggingFaceFW/fineweb) - Corpus web

### 13.3 Papers Relevantes

- [Scaling Laws for Neural Language Models](https://arxiv.org/abs/2001.08361) - Chinchilla
- [Training Compute-Optimal LLMs](https://arxiv.org/abs/2203.15556) - Hoffman et al.

---

## 14. Próximos Pasos

### Acciones Inmediatas (Pre-Q3)

1. [ ] Aprobar presupuesto para entrenamiento (~$3,000)
2. [ ] Evaluar resultados de LoRA (Q2) como baseline
3. [ ] Configurar acceso a BOE API y EUR-Lex
4. [ ] Reservar instancias GPU en Lambda Labs

### Inicio Q3

1. [ ] Crear branch `feature/nano-rll-training`
2. [ ] Descargar y procesar corpus legal
3. [ ] Entrenar tokenizer especializado
4. [ ] Iniciar PoC con modelo 560M

---

*Documento generado: Enero 2026*
*Última actualización: 2026-01-14*
*Versión: 1.0*
