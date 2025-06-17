# Navigation Loader Implementation

## Overview
Se ha implementado un sistema de indicadores de carga para las transiciones de página en el frontend de Nexus. Esto mejora la experiencia del usuario al proporcionar retroalimentación visual durante la navegación.

## Componentes Implementados

### 1. PageLoaderProvider (`/components/providers/page-loader.tsx`)
- **Función**: Provider principal que maneja el estado global del loader
- **Características**:
  - Detecta cambios de ruta automáticamente
  - Muestra un loader de pantalla completa con animación
  - Incluye texto descriptivo en español
  - Previene flash con un pequeño delay antes de mostrar

### 2. TopLoader (`/components/providers/top-loader.tsx`)
- **Función**: Barra de progreso en la parte superior de la página
- **Características**:
  - Barra de progreso animada con efecto de brillo
  - Se muestra solo durante las transiciones
  - Progreso simulado para mejor UX

### 3. NavLink (`/components/ui/nav-link.tsx`)
- **Función**: Componente Link mejorado que activa el loader
- **Características**:
  - Reemplaza al Link de Next.js
  - Activa el loader automáticamente
  - Ignora navegación a la misma página
  - Maneja enlaces externos correctamente

### 4. useNavigation Hook (`/hooks/use-navigation.ts`)
- **Función**: Hook para navegación programática con loader
- **Características**:
  - `navigate()`: Navegación con loader automático
  - `navigateWithLoader()`: Navegación asíncrona con loader
  - Previene loader en navegación a la misma página

## Archivos Actualizados

### Layout Principal
- `/app/layout.tsx`: Agregados PageLoaderProvider y TopLoader

### Componentes de Navegación
- `/components/navigation/nav-secondary.tsx`: Link → NavLink
- `/components/navigation/nav-main.tsx`: Link → NavLink
- `/components/navigation/nav-documents.tsx`: Link → NavLink
- `/components/navigation/nav-agents.tsx`: router.push → navigate()

## Uso

### Para Enlaces Declarativos
```tsx
import { NavLink } from "@/components/ui/nav-link"

// En lugar de:
<Link href="/documents">Documentos</Link>

// Usar:
<NavLink href="/documents">Documentos</NavLink>
```

### Para Navegación Programática
```tsx
import { useNavigation } from "@/hooks/use-navigation"

function MyComponent() {
  const { navigate } = useNavigation()
  
  const handleClick = () => {
    // Muestra loader automáticamente
    navigate('/documents')
  }
}
```

## Características

1. **Loader de Pantalla Completa**
   - Fondo semi-transparente con blur
   - Spinner animado con efecto de pulso
   - Texto en español: "Cargando página..."

2. **Barra de Progreso Superior**
   - Barra de progreso azul primaria
   - Efecto de brillo
   - Progreso animado

3. **Prevención de Flash**
   - Delay de 100ms antes de mostrar loader
   - Se oculta rápidamente al completar

4. **Integración Automática**
   - Funciona con toda la navegación del sidebar
   - Compatible con Next.js App Router
   - No requiere cambios en las páginas

## Beneficios

- ✅ Mejor experiencia de usuario
- ✅ Feedback visual inmediato
- ✅ Previene clics múltiples
- ✅ Indicador de estado del sistema
- ✅ Totalmente accesible
- ✅ Sin dependencias externas adicionales

## Mantenimiento

Para agregar loader a nuevos componentes:
1. Importar `NavLink` en lugar de `Link`
2. Para navegación programática, usar el hook `useNavigation`
3. El loader se activará automáticamente

El sistema está diseñado para ser transparente y no requerir configuración adicional en las páginas individuales.