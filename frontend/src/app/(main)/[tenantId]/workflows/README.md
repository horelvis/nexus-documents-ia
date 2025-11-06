# Workflows con TemporalIO - Documentación Frontend

## 📋 Resumen

La interfaz de workflows de NexusDocs360 ahora está completamente integrada con **TemporalIO**, proporcionando una experiencia moderna y robusta para la gestión de procesos automatizados.

## 🏗️ Arquitectura de Componentes

### Componentes Principales

#### 1. **WorkflowDashboard** (`/components/workflows/WorkflowDashboard.tsx`)
- **Función**: Muestra lista de workflows activos con estado en tiempo real
- **Características**:
  - Lista paginada de workflows
  - Estados visuales (running, completed, failed, cancelled)
  - Acciones rápidas (cancelar, ver detalles)
  - Estadísticas resumidas
  - Auto-refresh cada 30 segundos

#### 2. **WorkflowForm** (`/components/workflows/WorkflowForm.tsx`)
- **Función**: Formulario para iniciar nuevos workflows
- **Características**:
  - Selección de tipo de workflow
  - Campos dinámicos basados en el tipo
  - Validación en tiempo real
  - Preview de datos antes de envío

#### 3. **WorkflowTemplates** (`/components/workflows/WorkflowTemplates.tsx`)
- **Función**: Catálogo de plantillas predefinidas
- **Características**:
  - Templates para Contract Renewal y Employee Onboarding
  - Información detallada de cada template
  - Inicio rápido con datos de demo
  - Estadísticas de uso

#### 4. **WorkflowMonitor** (`/components/workflows/WorkflowMonitor.tsx`)
- **Función**: Monitoreo en tiempo real del sistema
- **Características**:
  - Estado de conexión con TemporalIO
  - Health checks de servicios
  - Lista de workflows activos
  - Métricas de performance
  - Auto-refresh cada 10 segundos

#### 5. **WorkflowStatus** (`/components/workflows/WorkflowStatus.tsx`)
- **Función**: Vista detallada de un workflow específico
- **Características**:
  - Log de ejecución completo
  - Estado detallado con timestamps
  - Resultados y errores
  - Queries en tiempo real

### Hook Principal

#### **useWorkflows** (`/hooks/useWorkflows.ts`)
```typescript
const {
  workflows,           // Lista de workflows
  templates,           // Plantillas disponibles
  stats,              // Estadísticas del sistema
  isLoading,          // Estado de carga
  error,              // Errores
  refreshWorkflows,   // Refrescar lista
  startWorkflow,      // Iniciar workflow
  getWorkflowStatus,  // Obtener estado
  cancelWorkflow,     // Cancelar workflow
  queryWorkflow       // Query workflow
} = useWorkflows(tenantId);
```

## 🚀 Flujo de Uso

### 1. **Acceso a Workflows**
```
Navegar a: /{tenantId}/workflows
```

### 2. **Ver Dashboard**
- Lista de workflows activos
- Estadísticas generales
- Estado del sistema

### 3. **Iniciar Workflow**
```typescript
// Opción 1: Usar formulario
<WorkflowForm onSubmit={handleStartWorkflow} />

// Opción 2: Usar template
<WorkflowTemplates onStartWorkflow={handleStartWorkflow} />
```

### 4. **Monitorear Progreso**
```typescript
// Ver estado en tiempo real
<WorkflowMonitor onWorkflowUpdate={handleUpdate} />

// Ver detalles específicos
<WorkflowStatus workflowId={workflowId} />
```

## 📡 API Integration

### Endpoints Utilizados

#### **Core API** (`/api/v1/temporalio`)
```http
GET  /health                    # Health check
POST /contract-renewal         # Iniciar renovación
POST /employee-onboarding      # Iniciar onboarding
GET  /workflow/{id}/status     # Estado del workflow
POST /workflow/{id}/cancel     # Cancelar workflow
POST /workflow/{id}/query      # Query workflow
GET  /workflows                # Lista de workflows
```

### Manejo de Errores

```typescript
try {
  await startWorkflow("contract_renewal", inputData);
  toast({ title: "Éxito", description: "Workflow iniciado" });
} catch (error) {
  toast({
    title: "Error",
    description: error.message,
    variant: "destructive"
  });
}
```

## 🎨 UI/UX Features

### Estados Visuales
- **🟢 Verde**: Completado exitosamente
- **🔵 Azul**: En ejecución
- **🔴 Rojo**: Error o fallido
- **⚪ Gris**: Cancelado

### Loading States
- Skeleton loaders para listas
- Spinners para acciones
- Progress bars para workflows activos

### Responsive Design
- Mobile-first approach
- Grid layouts adaptativos
- Componentes colapsables

## 🔧 Configuración

### Variables de Entorno
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
# Opcional: configuración de polling
NEXT_PUBLIC_WORKFLOW_POLL_INTERVAL=10000
```

### Dependencias Requeridas
```json
{
  "lucide-react": "^0.292.0",
  "@radix-ui/react-dialog": "^1.0.5",
  "@radix-ui/react-tabs": "^1.0.4",
  "@radix-ui/react-progress": "^1.0.3"
}
```

## 🧪 Testing

### Component Testing
```typescript
import { render, screen } from "@testing-library/react";
import { WorkflowDashboard } from "./WorkflowDashboard";

test("renders workflow list", () => {
  render(<WorkflowDashboard workflows={[]} isLoading={false} />);
  expect(screen.getByText("Workflows Activos")).toBeInTheDocument();
});
```

### Hook Testing
```typescript
import { renderHook } from "@testing-library/react";
import { useWorkflows } from "./useWorkflows";

test("initializes with empty state", () => {
  const { result } = renderHook(() => useWorkflows("test-tenant"));
  expect(result.current.workflows).toEqual([]);
});
```

## 🚨 Troubleshooting

### Problemas Comunes

#### **1. Workflows no se cargan**
```typescript
// Verificar conexión con API
console.log("API URL:", process.env.NEXT_PUBLIC_API_URL);

// Verificar tenantId
console.log("Tenant ID:", tenantId);
```

#### **2. Errores de autenticación**
```typescript
// Verificar que el usuario esté autenticado
const { user } = useUser();
if (!user) return <div>No autorizado</div>;
```

#### **3. Estado no se actualiza**
```typescript
// Forzar refresh manual
await refreshWorkflows();

// Verificar intervalos de polling
useEffect(() => {
  const interval = setInterval(refreshWorkflows, 30000);
  return () => clearInterval(interval);
}, [refreshWorkflows]);
```

## 📈 Métricas y Analytics

### KPIs Monitoreados
- **Total Workflows**: Número total de workflows
- **Activos**: Workflows en ejecución
- **Completados**: Workflows finalizados exitosamente
- **Fallidos**: Workflows con errores
- **Tiempo Promedio**: Duración promedio de ejecución

### Health Checks
- **API Core**: Estado del backend principal
- **TemporalIO Service**: Estado del microservicio
- **Workers**: Estado de los workers de TemporalIO
- **Conectividad**: Estado de la conexión en tiempo real

## 🔮 Próximas Funcionalidades

### Planificadas
- [ ] Notificaciones push para workflow events
- [ ] Dashboard personalizado por usuario
- [ ] Exportación de logs de ejecución
- [ ] Templates personalizables
- [ ] Integración con calendario

### Futuras
- [ ] Workflows colaborativos
- [ ] A/B testing de workflows
- [ ] Machine learning para optimización
- [ ] Integración con herramientas externas

## 📞 Soporte

Para soporte técnico:
1. Revisar logs de consola del navegador
2. Verificar estado de servicios en `/health`
3. Consultar documentación de TemporalIO
4. Reportar issues en el repositorio

---

**🎉 La interfaz de workflows está lista para producción con TemporalIO!**