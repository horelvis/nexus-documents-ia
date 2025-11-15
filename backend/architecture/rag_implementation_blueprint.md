# Plano de Implementación RAG Basado en Lecciones del Caso Clínico

Documento de referencia para evolucionar la arquitectura RAG de NexusDocs360 tomando como base el artículo “Everyone Builds RAG Backwards” (experiencia real en sector salud) y las recomendaciones internas derivadas.

---

## 1. Resumen Ejecutivo del Artículo

- **Contexto**: Sistema RAG para médicos que debía responder con estudios recientes y precisos. El MVP funcionó con pocos documentos, pero colapsó al escalar (resultados irrelevantes, citas inventadas, información desactualizada).
- **Hallazgo central**: Las guías RAG tradicionales (chunk → embed → vector search) ignoran la comprensión del documento y de la consulta. La arquitectura correcta consta de cinco capas obligatorias.
- **Capas propuestas**:
  1. **Document Intelligence**: Inferir estructura, tipo de sección, entidades y relevancia antes de trocear.
  2. **Query Intelligence**: Expandir abreviaturas, detectar intención, generar variaciones y filtros.
  3. **Multi-stage Retrieval**: Búsqueda filtrada + rerank semántico + fusión contextual por documento.
  4. **Context Assembly**: Construir bloques jerárquicos con metadatos y control estricto del presupuesto de tokens.
  5. **Generation & Validation**: Responder con reglas estrictas y validar cada afirmación contra las fuentes (confidence score).
- **Resultados**: Precisión de recuperación 89 %, latencia media 2.3 s, alucinaciones 4 %, satisfacción 4.7/5 con 340 usuarios activos diarios.
- **Errores evitables**:
  - Optimizar recuperación sin entender las consultas.
  - Tratar todos los documentos por igual (sin ponderar relevancia y frescura).
  - Confiar ciegamente en las citas generadas por el LLM.
- **Monitoreo esencial**: confianza, número de documentos útiles, feedback de usuario, tiempos de respuesta e intenciones con más fallos.

---

## 2. Recomendaciones de Adaptación para NexusDocs360

### 2.1 Document Intelligence
- Extender los pipelines de ingesta (`app/document_processing` y conectores hacia Weaviate, nuestro GAP vectorial) para producir objetos `DocumentSection` con:
  - Tipo de sección (abstract, cláusula legal, KPI financiero, etc.).
  - Puntaje de importancia (ponderado por tipo, densidad de entidades y calidad de la fuente).
  - Entidades extraídas con modelos específicos (Spacy clínico, regulador o financiero, según tenant).
- Guardar metadatos en el payload del vector DB y en Elasticsearch para búsquedas híbridas.

### 2.2 Query Intelligence
- Microservicio ligero que:
  - Expanda abreviaturas y alias por vertical (LGPD, fiscal, healthcare).
  - Clasifique la intención (p.ej. `treatment_lookup`, `compliance_check`, `pricing_analysis`).
  - Genere variaciones semánticas y filtros (intervalos de fechas, tipo de documento, jurisdicción).
  - Devuelva embeddings listos para buscadores densos y filtros para motores híbridos.

### 2.3 Recuperación Multi-etapa
- **Etapa 1**: Búsqueda vectorial filtrada en Qdrant/Weaviate usando cada variación de consulta + filtros.
- **Etapa 2**: Reranking con cross-encoder (puede residir junto al microservicio de orquestación que expone Weaviate/GAP u Ollama).
- **Etapa 3**: Context fusion agrupando por documento, premiando diversidad de secciones relevantes.
- Integrar señales de frescura y calidad (meta-análisis > caso aislado, últimos N meses > histórico).

### 2.4 Ensamblado de Contexto
- Construir bloques con encabezados que incluyan título, autores/empresa, año, tipo de estudio/documento y score de relevancia.
- Limitar tokens por documento (p.ej. 1500) y total (p.ej. 6k) para no saturar el LLM.
- Ordenar secciones según `importance_score` y relevancia combinada del reranker.

### 2.5 Generación + Validación
- Prompt estricto que obligue a citar “Documento N, Sección”.
- Servicio de validación automática:
  - Extrae afirmaciones del output.
  - Verifica cada una con un LLM económico (Claude Haiku, GPT‑4o mini, etc.) contra el contexto usado.
  - Calcula `confidence_score = claims_validadas / claims_totales`.
- Exponer el score y las citas verificadas en la UI para reforzar confianza y facilitar auditorías.

### 2.6 Observabilidad
- Métricas en Prometheus/Grafana:
  - Distribución de intenciones, tiempo total, latencia por etapa, `confidence_score`, número de secciones usadas.
  - Alertas cuando confianza < 0.7 o cuando la recuperación devuelve < N documentos relevantes.
  - Registro estructurado para análisis (query, filtros, doc ids, feedback).

---

## 3. Plan de Implementación Progresivo

1. **Spike de Document Intelligence**
   - Dominio piloto (p.ej. resoluciones LGPD).
   - Medir impacto en precisión de recuperación frente al pipeline actual.
2. **Servicio de Query Intelligence**
   - Diccionarios de abreviaturas/domain ontologies por tenant.
   - API interna que devuelva `intent`, `filters`, `variations`, `embeddings`.
3. **Retrieval multi-etapa**
   - Añadir reranker (sentence-transformers o LLM) y módulo de fusión.
   - Ajustar configuraciones de Qdrant/Weaviate y Elasticsearch para soportar filtros avanzados.
4. **Context Assembler estructurado**
   - Reemplazar el actual formateo en la capa de orquestación (LangGraph + Weaviate/GAP) por bloques jerárquicos con presupuesto de tokens.
5. **Validated Generator**
   - Integrar prompt disciplinado + claim checker.
   - Mostrar `confidence_score` y estado de validación en la respuesta.
6. **Monitoreo y Feedback**
   - Tablero en Grafana con métricas clave.
   - Captura de retroalimentación en la UI (thumbs up/down + comentarios).

---

## 4. Riesgos y Mitigaciones

| Riesgo | Impacto | Mitigación |
| ------ | ------- | ---------- |
| Latencia mayor por nuevas etapas | Respuestas lentas | Optimizar embeddings locales, cachear análisis de query, usar modelos ligeros para validación |
| Costos de LLM/Cross-encoder | Sobrecostos operativos | Seleccionar modelos eficientes, procesar en batch, habilitar fallback a modelos locales |
| Calidad desigual de parsers | Datos mal etiquetados | Tests unitarios para pipelines, validaciones heurísticas (ej. proporción mínima de texto por sección) |
| Falta de confianza en scores | Usuarios ignoran indicador | Documentar cómo se calcula, entrenar usuarios, correlacionar score con feedback real |

---

## 5. Conclusiones

- El fracaso descrito en el artículo coincide con dolores que hemos visto al escalar nuestra plataforma: pérdida de relevancia, citas débiles y falta de señales de confianza.
- Adoptar las cinco capas (inteligencia de documentos, inteligencia de consulta, recuperación multi-etapa, ensamblado estructurado y validación) alinea la arquitectura de NexusDocs360 con las mejores prácticas observadas en producción para dominios altamente regulados.
- El roadmap incremental permite validar cada capa antes de la siguiente, controlando latencia y costos mientras elevamos la precisión y la confianza del usuario final.

> **Próximo paso recomendado**: iniciar un spike de Document/Query Intelligence en un subconjunto de documentos legales para medir mejora de recall/precision y establecer las bases del resto del plan.
