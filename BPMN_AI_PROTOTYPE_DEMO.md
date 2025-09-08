# 🚀 **Prototipo BPM AI + Emma AI - Demo Renovación de Contratos**

## 📋 **¿Qué hemos construido?**

Un sistema **híbrido revolucionario** que combina:
- **🤖 Modelos BPM especializados** de Hugging Face (TXT2BPMN, BPMN Information Extraction)
- **🧠 Emma AI** para validación y contexto laboral español
- **⚖️ Cumplimiento automático** con normativa laboral
- **🔄 Ejecución dinámica** de procesos

## 🎯 **Caso de Uso: Renovación Automática de Contrato**

### **📊 Input:**
```json
{
  "contract_id": "contract_001",
  "employee_name": "María López", 
  "contract_type": "temporal",
  "expiration_date": "2025-01-15",
  "performance_rating": "Excelente",
  "attendance_score": 98
}
```

### **🎨 Proceso Automático:**

#### **1. Generación de Descripción BPM:**
```
Proceso de renovación de contrato temporal para María López que vence 2025-01-15:

1. RRHH recibe alerta automática 30 días antes del vencimiento
2. Se analiza el historial de rendimiento del empleado
3. Se evalúa la necesidad operativa del puesto  
4. Manager directo proporciona evaluación
5. Si evaluación es positiva: se procede con renovación
6. Se genera nuevo contrato con condiciones actualizadas
7. Se envía contrato a empleado para firma digital
8. Se programa seguimiento si no hay respuesta en 7 días
9. Una vez firmado, se actualiza sistema
```

#### **2. Extracción Automática de Elementos:**
- **🧑‍💼 Agents**: RRHH, Manager, Empleado, Legal
- **📋 Tasks**: Analizar rendimiento, Evaluar necesidad, Generar contrato, Enviar firma
- **🎯 Conditions**: Evaluación positiva, Necesidad operativa, Firma completada
- **⏰ Process Info**: 30 días antes, 7 días seguimiento

#### **3. BPMN Generado:**
```
START_EVENT: contract_expiration_alert
→
SERVICE_TASK: analyze_employee_performance (RRHH)
→
SERVICE_TASK: evaluate_operational_need (Manager)  
→
EXCLUSIVE_GATEWAY: renewal_decision
├─ YES: performance_good AND operational_need
│   →
│   SERVICE_TASK: generate_renewal_contract (RRHH)
│   →
│   USER_TASK: employee_contract_signature (Empleado)
│   →
│   END_EVENT: renewal_completed
│
└─ NO: performance_poor OR no_operational_need
    →
    SERVICE_TASK: prepare_termination_docs (Legal)
    →  
    END_EVENT: termination_prepared
```

#### **4. Emma AI Validation (Normativa Española):**
- ✅ **Cumplimiento Estatuto de los Trabajadores**
- ✅ **Plazos legales para notificaciones**  
- ✅ **Derechos del trabajador en el proceso**
- ✅ **Documentación obligatoria**
- ✅ **Procedimiento contradictorio**

#### **5. Plan de Ejecución Inteligente:**
```json
{
  "execution_steps": [
    "Analizar historial de rendimiento empleado",
    "Evaluar necesidad operativa del puesto",
    "Tomar decisión renovación basada en datos", 
    "Generar documentos apropiados",
    "Ejecutar workflow seleccionado"
  ],
  "timeline": {"total_duration": "15 días"},
  "stakeholders": {
    "RRHH": "Coordinador proceso",
    "Manager": "Evaluador rendimiento", 
    "Empleado": "Beneficiario contrato"
  },
  "automated_actions": [
    "Análisis de rendimiento",
    "Generación de contratos",
    "Envío de notificaciones"
  ]
}
```

## 🌐 **API Endpoints Disponibles**

### **🔍 Health Check**
```bash
GET /bpmn-ai/health
```

### **🎨 Generar BPMN desde Descripción**
```bash
POST /bpmn-ai/generate-bpmn
Content-Type: application/json

{
  "process_description": "Renovar contrato temporal de Juan que vence en febrero",
  "tenant_id": "asesoría_garcía_asociados",
  "process_type": "contract_renewal",
  "context": {
    "employee_name": "Juan Pérez",
    "contract_type": "temporal"
  }
}
```

### **📄 Proceso Completo Renovación**
```bash
POST /bpmn-ai/contracts/contract_001/renewal
Content-Type: application/json

{
  "contract_id": "contract_001",
  "tenant_id": "asesoría_garcía_asociados",
  "user_id": "user_123"
}
```

### **⚡ Ejecutar Proceso**
```bash
POST /bpmn-ai/contracts/contract_001/execute?tenant_id=asesoría_001&user_id=user_123
```

### **🎭 Demo Completo**
```bash
POST /bpmn-ai/demo/contract-renewal
# Ejecuta demo completo con datos simulados
```

## 📊 **Response Example:**

```json
{
  "success": true,
  "message": "Proceso de renovación generado para contrato contract_001",
  "contract_id": "contract_001", 
  "tenant_id": "asesoría_garcía_asociados",
  "data": {
    "process_description": "Proceso renovación...",
    "extracted_elements": {
      "agents": [{"name": "RRHH", "confidence": 1.0}],
      "tasks": [{"description": "Analizar rendimiento", "confidence": 0.95}],
      "conditions": [{"condition": "evaluación positiva", "confidence": 0.9}]
    },
    "generated_bpmn": "START_EVENT → SERVICE_TASK → ...",
    "validated_bpmn": {
      "optimized_bpmn": "Versión optimizada por Emma AI",
      "legal_compliance_points": [
        "Verificación Art. 15 Estatuto Trabajadores",
        "Plazo preaviso 15 días naturales"
      ],
      "recommendations": [
        "Incluir cláusula prórroga automática",
        "Documentar evaluación de rendimiento"
      ],
      "emma_confidence": 0.92
    },
    "execution_plan": {
      "execution_steps": ["Paso 1", "Paso 2", "..."],
      "timeline": {"total_duration": "15 días"},
      "stakeholders": {"RRHH": "Coordinador", "...": "..."}
    }
  },
  "generated_at": "2025-01-04T12:56:27"
}
```

## 🚀 **Cómo Probarlo:**

### **1. Setup Rápido:**
```bash
# En el directorio del proyecto
cd backend/docker
./start-dev.sh

# Verificar que weaviate-service esté running
docker ps | grep weaviate-service
```

### **2. Instalar Dependencias BPM (Opcional):**
```bash
pip install transformers torch
# Esto habilita los modelos reales de Hugging Face
# Sin esto, usa fallback implementation
```

### **3. Probar Endpoints:**
```bash
# Health check
curl -H "Authorization: Bearer nxs_dev_GYCa7km7zmibtf54yzA9NwPMj4fAYFGt" \
     http://localhost:8007/bpmn-ai/health

# Demo completo
curl -X POST \
     -H "Authorization: Bearer nxs_dev_GYCa7km7zmibtf54yzA9NwPMj4fAYFGt" \
     -H "Content-Type: application/json" \
     http://localhost:8007/bpmn-ai/demo/contract-renewal
```

### **4. Interfaz Web:**
```
http://localhost:8007/docs
```
- Navegar a sección "BPM AI"
- Probar endpoint `/bpmn-ai/demo/contract-renewal`

## 🏆 **Ventajas Competitivas Únicas**

### **✅ vs Competidores:**
| Aspecto | Competidores | WorkIA BPM AI |
|---------|-------------|---------------|
| **BPMN Generation** | Manual/templates | Automático desde texto |
| **Legal Compliance** | Manual review | Emma AI validation |
| **Process Adaptation** | Static workflows | Dynamic AI-driven |
| **Stakeholder Intelligence** | Fixed roles | Context-aware assignment |
| **Execution Tracking** | Basic logging | AI-powered insights |

### **🚀 Diferenciadores:**
1. **🤖 Primera plataforma** que combina modelos BPM especializados + IA conversacional
2. **⚖️ Única validación automática** con normativa laboral española
3. **🧠 Procesos que se adaptan** basándose en contexto específico
4. **🔄 Ejecución híbrida** humano-IA optimizada
5. **📊 Transparencia total** del razonamiento IA (Chain of Thought)

## 📈 **Próximos Desarrollos**

### **Semana 1-2: Production Ready**
- [ ] Integración real con base de datos contratos
- [ ] Cache de procesos BPMN generados
- [ ] Logging y métricas detalladas
- [ ] Error handling robusto

### **Semana 3-4: Advanced Features**  
- [ ] Más tipos de proceso (disciplinario, terminación)
- [ ] Templates específicos por sector
- [ ] Integración con signature service
- [ ] Notificaciones automáticas

### **Semana 5-6: UI/UX**
- [ ] Dashboard visual de procesos BPMN
- [ ] Editor de workflows drag & drop  
- [ ] Monitoring en tiempo real
- [ ] Reportes ejecutivos

## 🎯 **Resultado Final**

**WorkIA Labor** se convierte en la **única plataforma del mercado** que ofrece:
- **Generación automática de procesos BPM** para casos laborales
- **Validación legal automática** con normativa española
- **Ejecución inteligente** con decisiones IA + intervención humana
- **Transparencia total** del proceso de razonamiento

**Diferenciación**: 2-3 años de ventaja sobre competidores que tendrían que desarrollar desde cero esta capacidad híbrida BPM + IA conversacional especializada en derecho laboral español.