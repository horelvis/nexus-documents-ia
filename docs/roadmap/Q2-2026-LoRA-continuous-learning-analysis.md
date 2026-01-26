# Análisis Técnico: LoRA para Aprendizaje Continuo del LLM

**Fecha**: Enero 2026
**Prioridad**: Q2 2026 - Investigación y PoC
**Estado**: Propuesta para evaluación
**Autores**: Equipo de Arquitectura NouxCubeIA

---

## Resumen Ejecutivo

Este documento analiza el uso de **LoRA (Low-Rank Adaptation)** para implementar aprendizaje continuo en Emma AI, permitiendo que el modelo se adapte a dominios específicos de cada tenant sin perder capacidades generales.

### Decisión Recomendada

| Aspecto | Recomendación |
|---------|---------------|
| **Implementar** | Sí, investigación en Q2 2026 |
| **Prioridad** | Media |
| **Esfuerzo estimado** | 6-8 semanas |
| **ROI esperado** | Especialización por dominio/tenant |

---

## 1. Contexto del Problema

### 1.1 Situación Actual

Emma AI utiliza el modelo base **Qwen3-4B** vía vLLM sin ninguna adaptación específica:

| Parámetro | Valor Actual |
|-----------|--------------|
| Modelo | Qwen/Qwen3-4B |
| Fine-tuning | Ninguno |
| Adaptadores | Ninguno |
| Personalización | Solo via prompts |
| VRAM utilizado | ~9GB |

### 1.2 Limitaciones Identificadas

1. **Sin especialización por dominio**: El modelo responde igual para legal, fiscal, laboral
2. **Sin aprendizaje de feedback**: No incorpora correcciones de usuarios
3. **Terminología genérica**: No aprende vocabulario específico del cliente
4. **Respuestas uniformes**: No se adapta al estilo preferido por tenant

### 1.3 Casos de Uso Objetivo

| Caso | Descripción | Beneficio |
|------|-------------|-----------|
| **Dominio legal** | Adaptar a terminología jurídica española | +precisión en contratos |
| **Dominio fiscal** | Especializar en normativa tributaria | +exactitud en consultas |
| **Por tenant** | Cada organización con su adaptador | Personalización total |
| **Feedback loop** | Aprender de correcciones | Mejora continua |

---

## 2. Solución Propuesta: LoRA

### 2.1 ¿Qué es LoRA?

**LoRA (Low-Rank Adaptation)** es una técnica de fine-tuning eficiente que:

1. **Congela** los pesos del modelo base
2. **Inyecta** matrices de bajo rango entrenables en cada capa
3. **Reduce** parámetros entrenables en **10,000x** (de 4B a ~400K)
4. **Mantiene** las capacidades del modelo base

```
┌─────────────────────────────────────────────────────────────┐
│                    ARQUITECTURA LoRA                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   Modelo Base (Qwen3-4B)           Adaptador LoRA           │
│   ┌─────────────────────┐         ┌─────────────────┐       │
│   │ W₀ (congelado)      │    +    │ ΔW = B × A      │       │
│   │ 4B parámetros       │         │ ~400K params    │       │
│   │ 8GB VRAM            │         │ ~2MB archivo    │       │
│   └─────────────────────┘         └─────────────────┘       │
│                                                              │
│   Output = W₀(x) + ΔW(x) = W₀(x) + B(A(x))                 │
│                                                              │
│   Donde:                                                     │
│   - B ∈ R^(d×r), A ∈ R^(r×k)                                │
│   - r = rango (típicamente 4-16)                            │
│   - r ≪ min(d, k) → "bajo rango"                            │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Referencias Académicas

| Paper | Autores | Contribución |
|-------|---------|--------------|
| [LoRA Original](https://arxiv.org/abs/2106.09685) | Hu et al. (Microsoft) | Técnica base |
| [CL-LoRA](https://openaccess.thecvf.com/content/CVPR2025/papers/He_CL-LoRA_Continual_Low-Rank_Adaptation_for_Rehearsal-Free_Class-Incremental_Learning_CVPR_2025_paper.pdf) | He et al. (CVPR 2025) | Aprendizaje continuo |
| [CONEC-LoRA](https://arxiv.org/abs/2510.16077) | Oct 2025 | Domain Incremental Learning |
| [Online-LoRA](https://openaccess.thecvf.com/content/WACV2025/papers/Wei_Online-LoRA_Task-Free_Online_Continual_Learning_via_Low_Rank_Adaptation_WACV_2025_paper.pdf) | Wei et al. (WACV 2025) | Task-free continual learning |

### 2.3 Beneficios Clave

| Beneficio | Valor |
|-----------|-------|
| Reducción de parámetros | 10,000x (4B → 400K) |
| Reducción de VRAM entrenamiento | 3x (12GB → 4GB) |
| Tamaño del adaptador | ~2-35MB vs 8GB modelo |
| Tiempo de entrenamiento | Horas vs días |
| Múltiples adaptadores | Sí, intercambiables en runtime |

---

## 3. Compatibilidad con NouxCubeIA

### 3.1 vLLM Soporte Nativo para LoRA

vLLM soporta nativamente serving de múltiples adaptadores LoRA:

```bash
# Iniciar vLLM con adaptadores LoRA
python -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen3-4B \
    --lora-modules legal-es=/adapters/legal-es \
                   fiscal-es=/adapters/fiscal-es \
                   tenant-abc=/adapters/tenant-abc \
    --max-loras 8 \
    --max-lora-rank 16
```

**Características soportadas** ([vLLM LoRA Docs](https://docs.vllm.ai/en/stable/features/lora/)):

| Característica | Soporte |
|----------------|---------|
| Múltiples adaptadores simultáneos | ✅ Sí |
| Selección por request | ✅ Sí |
| Carga dinámica en runtime | ✅ Sí (con flag) |
| Cache LRU de adaptadores | ✅ Sí |
| Overhead por cambio | ~negligible |

### 3.2 Configuración Actual vs Propuesta

| Aspecto | Actual | Propuesto |
|---------|--------|-----------|
| Modelo | Qwen3-4B | Qwen3-4B (sin cambio) |
| Adaptadores | Ninguno | legal-es, fiscal-es, tenant-* |
| VRAM adicional | 0 | ~100MB por adaptador cargado |
| docker-compose | Sin --lora-modules | Con --lora-modules |

### 3.3 Arquitectura Multi-Tenant con LoRA

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ARQUITECTURA MULTI-TENANT LoRA                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Request (tenant_id: "abc-corp")                                           │
│         │                                                                    │
│         ▼                                                                    │
│   ┌─────────────────────────────────────────────────────────────┐           │
│   │                     EmmaCoordinator                          │           │
│   │                                                              │           │
│   │   1. Detecta tenant_id                                       │           │
│   │   2. Resuelve adaptador: tenant_id → lora_adapter_name       │           │
│   │   3. Añade header: X-LoRA-Adapter: tenant-abc-corp           │           │
│   └────────────────────────────────────┬────────────────────────┘           │
│                                        │                                     │
│                                        ▼                                     │
│   ┌─────────────────────────────────────────────────────────────┐           │
│   │                     vLLM Server                              │           │
│   │                                                              │           │
│   │   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │           │
│   │   │ Qwen3-4B    │  │ LoRA Cache  │  │ Adapter     │         │           │
│   │   │ (base)      │  │ (LRU)       │  │ Storage     │         │           │
│   │   │ 8GB VRAM    │  │ max_loras=8 │  │ /adapters/  │         │           │
│   │   └──────┬──────┘  └──────┬──────┘  └──────┬──────┘         │           │
│   │          │                │                │                 │           │
│   │          └────────────────┴────────────────┘                 │           │
│   │                           │                                  │           │
│   │                           ▼                                  │           │
│   │              Output = Base(x) + LoRA_tenant(x)               │           │
│   └─────────────────────────────────────────────────────────────┘           │
│                                                                              │
│   Adaptadores disponibles:                                                  │
│   /adapters/                                                                 │
│   ├── legal-es/          (dominio legal español)                            │
│   ├── fiscal-es/         (dominio fiscal español)                           │
│   ├── laboral-es/        (dominio laboral español)                          │
│   ├── tenant-abc-corp/   (específico cliente ABC)                           │
│   ├── tenant-xyz-legal/  (específico cliente XYZ)                           │
│   └── base/              (sin adaptador, modelo vanilla)                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Estrategia de Aprendizaje Continuo

### 4.1 Prevención de Catastrophic Forgetting

El principal riesgo del fine-tuning continuo es el **catastrophic forgetting**: el modelo pierde capacidades previas al aprender nuevas.

**Técnicas de mitigación** ([guía práctica](https://blog.ivan.digital/finetuning-qwen3-with-lora-done-right-94d6343e1814)):

| Técnica | Descripción | Implementación |
|---------|-------------|----------------|
| **KL Regularization** | Penaliza divergencia del modelo base | `kl_weight=0.03-0.10` durante SFT |
| **LoRA bajo rango** | Restringe cambios a subespacio pequeño | `r=16, alpha=16` |
| **Replay buffer** | Mezcla datos nuevos con ejemplos base | 10-20% datos generales |
| **Orthogonal constraints** | Minimiza interferencia entre tareas | CL-LoRA approach |

### 4.2 Pipeline de Aprendizaje Continuo

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PIPELINE DE APRENDIZAJE CONTINUO                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   1. RECOLECCIÓN DE FEEDBACK                                                │
│   ┌─────────────────────────────────────────────────────────────┐           │
│   │ Usuario corrige respuesta → Feedback almacenado en DB       │           │
│   │ - Query original                                             │           │
│   │ - Respuesta de Emma                                          │           │
│   │ - Corrección del usuario                                     │           │
│   │ - tenant_id, timestamp                                       │           │
│   └─────────────────────────────────────────────────────────────┘           │
│                           │                                                  │
│                           ▼                                                  │
│   2. CURACIÓN DE DATOS (semanal/mensual)                                    │
│   ┌─────────────────────────────────────────────────────────────┐           │
│   │ - Filtrar feedback de calidad (>N correcciones similares)   │           │
│   │ - Agrupar por dominio (legal, fiscal, laboral)              │           │
│   │ - Agrupar por tenant (si suficientes datos)                 │           │
│   │ - Generar pares (query, respuesta_corregida)                │           │
│   └─────────────────────────────────────────────────────────────┘           │
│                           │                                                  │
│                           ▼                                                  │
│   3. FINE-TUNING LoRA (offline, GPU dedicada)                               │
│   ┌─────────────────────────────────────────────────────────────┐           │
│   │ - Cargar modelo base + adaptador existente                  │           │
│   │ - SFT con KL regularization (previene forgetting)           │           │
│   │ - Opcional: DPO para preferencias                           │           │
│   │ - Validación contra benchmark interno                       │           │
│   └─────────────────────────────────────────────────────────────┘           │
│                           │                                                  │
│                           ▼                                                  │
│   4. VALIDACIÓN Y DESPLIEGUE                                                │
│   ┌─────────────────────────────────────────────────────────────┐           │
│   │ - Test automático: no regresión en tareas base              │           │
│   │ - Test específico: mejora en dominio objetivo               │           │
│   │ - Despliegue gradual (canary 10% → 50% → 100%)              │           │
│   │ - Rollback automático si métricas degradan                  │           │
│   └─────────────────────────────────────────────────────────────┘           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.3 Tipos de Adaptadores Propuestos

| Adaptador | Datos de Entrenamiento | Frecuencia Update | Propósito |
|-----------|------------------------|-------------------|-----------|
| `legal-es` | Corpus jurídico español | Trimestral | Terminología legal |
| `fiscal-es` | Normativa tributaria | Trimestral | Impuestos, IRPF, IVA |
| `laboral-es` | Derecho laboral | Trimestral | Convenios, despidos |
| `gdpr-compliance` | RGPD, LOPDGDD | Semestral | Protección de datos |
| `tenant-{id}` | Feedback del tenant | Mensual | Personalización |

---

## 5. Plan de Implementación

### 5.1 Fase 1: Infraestructura (Semanas 1-2)

```yaml
# docker-compose.yml - Modificaciones
services:
  vllm:
    command:
      - --model=Qwen/Qwen3-4B
      - --enable-lora
      - --max-loras=8
      - --max-lora-rank=16
      - --lora-modules=legal-es=/app/adapters/legal-es
      - --lora-modules=fiscal-es=/app/adapters/fiscal-es
    volumes:
      - ./adapters:/app/adapters:ro
    environment:
      - VLLM_ALLOW_RUNTIME_LORA_UPDATING=true
```

### 5.2 Fase 2: Primer Adaptador (Semanas 3-4)

**Objetivo**: Crear adaptador `legal-es` con corpus jurídico español.

```python
# training/train_lora.py
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, Trainer

# Configuración LoRA recomendada para Qwen3
lora_config = LoraConfig(
    r=16,                    # Rango bajo
    lora_alpha=16,           # Scaling factor
    target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM"
)

# Cargar modelo base
model = AutoModelForCausalLM.from_pretrained("Qwen/Qwen3-4B")
model = get_peft_model(model, lora_config)

# Entrenar con KL regularization
trainer = Trainer(
    model=model,
    train_dataset=legal_dataset,
    # ... config con KL loss
)
trainer.train()

# Guardar solo el adaptador (~2MB)
model.save_pretrained("/adapters/legal-es")
```

### 5.3 Fase 3: Integración con Emma (Semanas 5-6)

```python
# emma_coordinator.py - Modificaciones

class EmmaCoordinator:
    def _resolve_lora_adapter(self, tenant_id: str, query: str) -> Optional[str]:
        """
        Resolver qué adaptador LoRA usar para este request.

        Estrategia:
        1. Si existe adaptador específico del tenant → usarlo
        2. Si query es legal → usar legal-es
        3. Si query es fiscal → usar fiscal-es
        4. Default → sin adaptador (modelo base)
        """
        # Adaptador específico del tenant
        tenant_adapter = f"tenant-{tenant_id}"
        if self._adapter_exists(tenant_adapter):
            return tenant_adapter

        # Detectar dominio de la query
        domain = self._detect_domain(query)
        domain_adapters = {
            "legal": "legal-es",
            "fiscal": "fiscal-es",
            "laboral": "laboral-es",
        }

        return domain_adapters.get(domain)

    async def execute(self, query: str, tenant_id: str, ...):
        # Resolver adaptador
        adapter = self._resolve_lora_adapter(tenant_id, query)

        # Configurar request con adaptador
        if adapter:
            # vLLM selecciona adaptador via model name
            model_name = f"Qwen/Qwen3-4B:{adapter}"
        else:
            model_name = "Qwen/Qwen3-4B"

        # ... resto de ejecución
```

### 5.4 Fase 4: Feedback Loop (Semanas 7-8)

```python
# services/learning/feedback_collector.py

class FeedbackCollector:
    """Recolecta feedback de usuarios para fine-tuning futuro."""

    async def record_correction(
        self,
        tenant_id: str,
        query: str,
        emma_response: str,
        user_correction: str,
        correction_type: str  # "factual", "style", "terminology"
    ) -> None:
        """Almacena corrección para entrenamiento futuro."""
        await self.db.feedback.insert({
            "tenant_id": tenant_id,
            "query": query,
            "original_response": emma_response,
            "corrected_response": user_correction,
            "correction_type": correction_type,
            "timestamp": datetime.utcnow(),
            "used_for_training": False
        })

    async def export_training_data(
        self,
        tenant_id: Optional[str] = None,
        min_corrections: int = 3
    ) -> List[Dict]:
        """Exporta datos curados para fine-tuning."""
        # Agrupar correcciones similares
        # Filtrar por calidad
        # Formatear como pares (query, response)
        ...
```

---

## 6. Requisitos Técnicos

### 6.1 Hardware para Entrenamiento

| Recurso | Mínimo | Recomendado |
|---------|--------|-------------|
| GPU | RTX 3090 (24GB) | A100 (40GB) |
| VRAM para LoRA | 4-8GB | 16GB |
| RAM | 32GB | 64GB |
| Storage | 50GB SSD | 200GB NVMe |

**Nota**: El entrenamiento puede hacerse en instancia cloud temporal (AWS, GCP) para no afectar producción.

### 6.2 Dependencias Nuevas

```toml
# requirements.txt adicionales
peft>=0.7.0           # Parameter-Efficient Fine-Tuning
trl>=0.7.0            # Transformers Reinforcement Learning (DPO)
datasets>=2.14.0      # Dataset management
bitsandbytes>=0.41.0  # QLoRA quantization (opcional)
```

### 6.3 Configuración vLLM para LoRA

```bash
# Variables de entorno
VLLM_ALLOW_RUNTIME_LORA_UPDATING=true
VLLM_MAX_LORAS=8
VLLM_MAX_LORA_RANK=16
VLLM_MAX_CPU_LORAS=16  # Cache en CPU
```

---

## 7. Análisis de Impacto

### 7.1 Métricas Esperadas

| Métrica | Sin LoRA | Con LoRA | Mejora |
|---------|----------|----------|--------|
| Precisión terminología legal | 70% | 90% | **+20pp** |
| Satisfacción usuario (dominio) | 3.5/5 | 4.2/5 | **+0.7** |
| Tiempo respuesta | 2s | 2.1s | +5% (aceptable) |
| VRAM adicional | 0 | 100MB/adapter | Mínimo |
| Storage adaptadores | 0 | ~2MB/adapter | Mínimo |

### 7.2 Trade-offs

| Beneficio | Costo |
|-----------|-------|
| Especialización por dominio | Complejidad de gestión de adaptadores |
| Personalización por tenant | Proceso de entrenamiento periódico |
| Mejora continua con feedback | Necesidad de curación de datos |
| Múltiples "personalidades" | Overhead de selección de adaptador |

### 7.3 Riesgos

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| Catastrophic forgetting | Media | Alto | KL regularization, validación pre-deploy |
| Datos de entrenamiento insuficientes | Media | Medio | Empezar con dominios, no tenants |
| Overfitting a tenant específico | Baja | Medio | Replay buffer con datos generales |
| Complejidad operacional | Media | Medio | Automatizar pipeline de entrenamiento |

---

## 8. Cronograma Q2 2026

```
Q2 2026 (Abril - Junio)
├── Semana 1-2: Infraestructura
│   ├── Configurar vLLM con soporte LoRA
│   ├── Crear estructura /adapters/
│   └── Scripts de carga dinámica
│
├── Semana 3-4: Primer Adaptador (legal-es)
│   ├── Recopilar corpus jurídico español
│   ├── Entrenar adaptador LoRA
│   └── Validar contra benchmark
│
├── Semana 5-6: Integración Emma
│   ├── Modificar EmmaCoordinator
│   ├── Implementar selección de adaptador
│   └── Tests de integración
│
├── Semana 7-8: Feedback Loop
│   ├── Implementar FeedbackCollector
│   ├── UI para correcciones
│   └── Pipeline de curación de datos
│
└── Semana 9-10: Validación y Documentación
    ├── Benchmarks comparativos
    ├── A/B testing con usuarios piloto
    └── Documentación técnica
```

---

## 9. Criterios de Éxito

### 9.1 Métricas Cuantitativas

- [ ] Adaptador `legal-es` mejora precisión terminológica en +15pp
- [ ] Latencia adicional <10% por selección de adaptador
- [ ] VRAM adicional <200MB con 4 adaptadores cargados
- [ ] Pipeline de entrenamiento ejecutable en <4 horas

### 9.2 Métricas Cualitativas

- [ ] Usuarios de dominio legal reportan mejora en respuestas
- [ ] Sistema de feedback funcional y usable
- [ ] Proceso de entrenamiento documentado y reproducible

---

## 10. Dependencias con Otros Proyectos

| Proyecto | Dependencia | Impacto |
|----------|-------------|---------|
| **Q1: RLM Context Extension** | Independiente | Pueden coexistir |
| **Emma Learning System** | Aprovecha FeedbackCollector | Sinergia |
| **Knowledge Extraction** | Datos para entrenamiento | Entrada |

---

## 11. Recursos y Referencias

### 11.1 Papers Clave

1. [LoRA: Low-Rank Adaptation of Large Language Models](https://arxiv.org/abs/2106.09685) - Paper original
2. [CL-LoRA: Continual Low-Rank Adaptation](https://openaccess.thecvf.com/content/CVPR2025/papers/He_CL-LoRA_Continual_Low-Rank_Adaptation_for_Rehearsal-Free_Class-Incremental_Learning_CVPR_2025_paper.pdf) - CVPR 2025
3. [CONEC-LoRA: Domain Incremental Learning](https://arxiv.org/abs/2510.16077) - Octubre 2025
4. [Practical guide: fine-tuning Qwen3 with LoRA](https://blog.ivan.digital/finetuning-qwen3-with-lora-done-right-94d6343e1814) - Guía práctica

### 11.2 Documentación Técnica

- [vLLM LoRA Documentation](https://docs.vllm.ai/en/stable/features/lora/)
- [HuggingFace PEFT Library](https://huggingface.co/docs/peft)
- [Qwen3 Fine-tuning Guide](https://huggingface.co/docs/optimum-neuron/en/training_tutorials/finetune_qwen3)

### 11.3 Herramientas

- [Microsoft LoRA Repository](https://github.com/microsoft/LoRA)
- [HuggingFace TRL](https://github.com/huggingface/trl) - Para DPO
- [LLM Continual Learning Survey](https://github.com/Wang-ML-Lab/llm-continual-learning-survey) - CSUR 2025

---

## 12. Próximos Pasos

### Acciones Inmediatas (Pre-Q2)

1. [ ] Aprobar investigación LoRA para Q2
2. [ ] Identificar corpus de entrenamiento para dominio legal
3. [ ] Reservar instancia GPU para entrenamiento
4. [ ] Definir métricas de benchmark

### Inicio Q2

1. [ ] Crear branch `feature/lora-continuous-learning`
2. [ ] Configurar entorno de entrenamiento
3. [ ] Implementar primer adaptador de dominio

---

*Documento generado: Enero 2026*
*Última actualización: 2026-01-12*
*Versión: 1.0*
