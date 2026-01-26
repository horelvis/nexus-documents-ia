# Análisis Técnico: Recursive Language Models (RLM) para Extensión de Contexto

**Fecha**: Enero 2026
**Prioridad**: Q1 2026 - Evaluación y PoC
**Estado**: Propuesta para evaluación
**Autores**: Equipo de Arquitectura NouxCubeIA

---

## Resumen Ejecutivo

Este documento analiza la viabilidad de integrar **Recursive Language Models (RLM)** en la arquitectura de Emma AI para resolver la limitación de contexto en el procesamiento de documentos largos.

### Decisión Recomendada

| Aspecto | Recomendación |
|---------|---------------|
| **Implementar** | Sí, como PoC en Q1 2026 |
| **Prioridad** | Media-Alta |
| **Esfuerzo estimado** | 4-6 semanas |
| **ROI esperado** | 100x extensión de contexto |

---

## 1. Contexto del Problema

### 1.1 Limitación Actual

Emma AI utiliza un pipeline RAG de 7 capas que actualmente opera con las siguientes restricciones:

| Parámetro | Valor Actual | Impacto |
|-----------|--------------|---------|
| Modelo LLM | Qwen3-8B vía vLLM | 4K-32K tokens nativos |
| Budget de contexto | 12K tokens | ~30 páginas máximo |
| Documentos por query | 12 (hard cap) | Cobertura limitada |
| Estrategia | Truncamiento pre-inferencia | Pérdida de información |

### 1.2 Casos de Uso Afectados

1. **Análisis de contratos largos** (>50 páginas): Truncamiento pierde cláusulas críticas
2. **Due diligence multi-documento**: No puede correlacionar información dispersa
3. **Búsqueda exhaustiva en expedientes**: Cobertura incompleta (~30%)
4. **Comparación de versiones**: Limitado a fragmentos seleccionados

---

## 2. Solución Propuesta: RLM

### 2.1 Referencia Académica

**Paper**: "Recursive Language Models"
**Autores**: Alex L. Zhang, Tim Kraska (MIT), Omar Khattab (Stanford/Databricks)
**Repositorio**: https://github.com/alexzhang13/rlm
**arXiv**: 2512.24601v1

### 2.2 Concepto Fundamental

RLM es un **paradigma de inferencia** (no un modelo nuevo) que permite procesar contextos de longitud "casi infinita" mediante:

```
┌─────────────────────────────────────────────────────────────┐
│                    ENFOQUE TRADICIONAL                       │
│  Input (100K tokens) → [TRUNCAR a 8K] → LLM → Respuesta     │
│                         ↑                                    │
│                    Pérdida de información                    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    ENFOQUE RLM                               │
│  Input (100K tokens) → Entorno REPL (Redis)                 │
│         ↓                                                    │
│  LLM analiza estructura → Descompone en sub-tareas          │
│         ↓                                                    │
│  Sub-llamada 1: LLM(fragmento_1) → resultado_1               │
│  Sub-llamada 2: LLM(fragmento_2) → resultado_2               │
│  ...                                                         │
│  Agregación: LLM(resultados[]) → Respuesta Final            │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 Características Técnicas

| Característica | Valor |
|----------------|-------|
| Extensión de contexto | Hasta 100x el contexto nativo |
| Requiere fine-tuning | No |
| Compatible con vLLM | Sí (OpenAI-compatible API) |
| Licencia | MIT |
| Madurez | Proyecto nuevo (Enero 2025) |

---

## 3. Compatibilidad con NouxCubeIA

### 3.1 Stack Actual

| Componente | Compatibilidad | Notas |
|------------|---------------|-------|
| vLLM + Qwen3 | ✅ Excelente | RLM usa OpenAI-compatible API |
| Microsoft Agent Framework | ✅ Compatible | RLM se integra como patrón de orquestación |
| Redis | ✅ Aprovechable | Para almacenar contexto externo |
| Docker | ✅ Nativo | RLM incluye executor Docker |
| Pipeline RAG 7 capas | ✅ Extensible | RLM como capa 4.5 adicional |

### 3.2 Arquitectura de Integración Propuesta

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     EmmaCoordinator (emma_coordinator.py)                    │
│                                                                              │
│   execute() → detect_orchestration_pattern()                                 │
│                     │                                                        │
│        ┌────────────┼────────────┬─────────────┐                             │
│        ▼            ▼            ▼             ▼                             │
│    HANDOFF     SEQUENTIAL   CONCURRENT    RLM_LONG  ← NUEVO                 │
│   (default)    (A→B→C)      (A|B|C)      (recursivo)                        │
│                                               │                              │
│                                               ▼                              │
│                                    ┌─────────────────────┐                   │
│                                    │  RLMOrchestrator    │                   │
│                                    │  (rlm_orchestrator) │                   │
│                                    └─────────────────────┘                   │
│                                               │                              │
│                                               ▼                              │
│                              Sub-llamadas recursivas vía vLLM                │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Plan de Implementación

### 4.1 Fases

| Fase | Duración | Entregables |
|------|----------|-------------|
| **Fase 1: PoC** | 2-3 semanas | RLM funcionando con documento de prueba |
| **Fase 2: Integración** | 3-4 semanas | Integrado en pipeline Emma |
| **Fase 3: Optimización** | 2-4 semanas | Caching, paralelización, métricas |

### 4.2 Archivos a Modificar/Crear

| Archivo | Acción | Descripción |
|---------|--------|-------------|
| `emma_coordinator.py` | Modificar | Nuevo patrón RLM_LONG |
| `context_assembler.py` | Modificar | Detección de contexto largo |
| `orchestration.py` | Modificar | Routing a RLM |
| `config.py` | Modificar | Settings RLM |
| `rlm_orchestrator.py` | **Crear** | Core RLM logic |
| `rlm_environment.py` | **Crear** | Entorno REPL |

### 4.3 Configuración

```bash
# Variables de entorno
RLM_ENABLED=true
RLM_THRESHOLD_TOKENS=50000      # Activar RLM si contexto > 50K
RLM_MAX_RECURSION_DEPTH=5       # Máxima profundidad de recursión
RLM_CHUNK_SIZE_TOKENS=8000      # Tamaño de chunk por sub-llamada
```

---

## 5. Análisis de Impacto

### 5.1 Métricas Esperadas

| Métrica | RAG Actual | RAG + RLM | Mejora |
|---------|------------|-----------|--------|
| Contexto procesado | 8K tokens | 800K tokens | **+100x** |
| Cobertura (recall) | ~30% | ~95% | **+65pp** |
| Documentos/query | 12 máx | 50+ | **+4x** |
| Latencia p50 | 2s | 8s | +4x |
| Latencia p99 | 5s | 20s | +4x |
| Costo/query | $0.002 | $0.008 | +4x |

### 5.2 Trade-offs

| Beneficio | Costo |
|-----------|-------|
| 100x más contexto | 4x más latencia |
| 95% cobertura vs 30% | 4x más costo por query |
| Análisis completo de documentos largos | Complejidad adicional en pipeline |
| Sin cambio de modelo | Nueva dependencia (rlm package) |

### 5.3 Casos de Uso Beneficiados

| Caso de Uso | Antes | Después |
|-------------|-------|---------|
| Contrato de 150 páginas | Trunca a 30 págs | Analiza completo |
| Due diligence 50 docs | Muestra 12 | Correlaciona todos |
| Búsqueda en expediente | 30% cobertura | 95% cobertura |
| Extracción de cláusulas | Puede perder algunas | Cobertura total |

---

## 6. Riesgos y Mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| Latencia aumentada | Media | Medio | Paralelizar sub-llamadas, cachear resultados |
| Costos de inferencia | Media | Medio | Optimizar profundidad recursiva, caching agresivo |
| Complejidad de debugging | Alta | Bajo | Usar visualizador de trayectorias de RLM |
| Alucinaciones en agregación | Baja | Alto | Mantener validated_generator para verificación |
| Madurez del proyecto RLM | Media | Medio | Paper revisado por pares, código MIT license |

---

## 7. Criterios de Éxito del PoC

### 7.1 Métricas Cuantitativas

- [ ] Procesar documento de >100 páginas sin truncamiento
- [ ] Recall >80% en extracción de cláusulas (vs ~30% actual)
- [ ] Latencia <30s para documentos de 100 páginas
- [ ] Costo <$0.05 por query complejo

### 7.2 Métricas Cualitativas

- [ ] Respuestas más completas en análisis de contratos largos
- [ ] Capacidad de correlacionar información entre múltiples documentos
- [ ] UX aceptable (usuarios toleran latencia por mejor calidad)

---

## 8. Dependencias y Recursos

### 8.1 Dependencias Técnicas

```toml
# Nuevas dependencias
rlm>=0.1.0          # Paquete principal RLM
uv>=0.1.0           # Package manager requerido por RLM
```

### 8.2 Recursos Necesarios

| Recurso | Cantidad | Notas |
|---------|----------|-------|
| Desarrollador Backend | 1 | 4-6 semanas dedicación |
| GPU (vLLM) | Existente | No requiere upgrade |
| Redis | Existente | +100MB RAM para contextos |
| Documentos de prueba | 5-10 | Contratos largos reales |

---

## 9. Timeline Propuesto

```
Q1 2026
├── Semana 1-2: Setup y PoC básico
│   ├── Instalar dependencias RLM
│   ├── Crear rlm_orchestrator.py básico
│   └── Test con documento largo de prueba
│
├── Semana 3-4: Integración con Emma
│   ├── Modificar emma_coordinator.py
│   ├── Añadir patrón RLM_LONG
│   └── Tests de integración
│
├── Semana 5-6: Optimización
│   ├── Caching de sub-resultados
│   ├── Paralelización de sub-llamadas
│   └── Métricas y observabilidad
│
└── Semana 7-8: Validación y documentación
    ├── Benchmarks comparativos
    ├── A/B testing con usuarios piloto
    └── Documentación técnica
```

---

## 10. Decisión y Próximos Pasos

### 10.1 Recomendación

**Proceder con PoC en Q1 2026**

Justificación:
1. ROI potencial significativo (100x contexto)
2. Compatible con stack actual (vLLM, Redis, Agent Framework)
3. No requiere cambio de modelo ni fine-tuning
4. Autores reconocidos (Omar Khattab - DSPy, Tim Kraska - MIT)
5. Alineado con filosofía del proyecto (usar soluciones open source)

### 10.2 Próximos Pasos Inmediatos

1. [ ] Aprobar inicio de PoC
2. [ ] Asignar desarrollador backend
3. [ ] Preparar documentos de prueba (contratos largos)
4. [ ] Definir métricas de éxito detalladas
5. [ ] Crear branch `feature/rlm-integration`

---

## Referencias

1. **Paper**: Zhang, A. L., Kraska, T., & Khattab, O. (2025). Recursive Language Models. arXiv:2512.24601v1
2. **Repositorio**: https://github.com/alexzhang13/rlm
3. **DSPy Framework**: https://github.com/stanfordnlp/dspy (referencia de Omar Khattab)
4. **Microsoft Agent Framework**: Documentación interna NouxCubeIA

---

*Documento generado: Enero 2026*
*Última actualización: 2026-01-12*
*Versión: 1.0*
