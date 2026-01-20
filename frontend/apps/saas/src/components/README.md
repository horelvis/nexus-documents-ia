# Estructura de Componentes

Esta carpeta está organizada siguiendo las mejores prácticas de Next.js y React para mantener una arquitectura escalable y mantenible.

## 📁 Estructura

```
components/
├── auth/            # Componentes de autenticación
│   ├── user-button.tsx
│   ├── auth-guard.tsx
│   └── index.ts
├── landing/         # Componentes de la landing page
│   ├── hero-section.tsx
│   ├── features-section.tsx
│   ├── stats-section.tsx
│   ├── cta-section.tsx
│   ├── landing-header.tsx
│   ├── landing-footer.tsx
│   └── index.ts
├── layout/          # Componentes de layout principal
│   ├── app-sidebar.tsx
│   ├── site-header.tsx
│   └── index.ts
├── navigation/      # Componentes de navegación
│   ├── nav-documents.tsx
│   ├── nav-main.tsx
│   ├── nav-secondary.tsx
│   ├── nav-user.tsx
│   └── index.ts
├── dashboard/       # Componentes específicos del dashboard
│   ├── chart-area-interactive.tsx
│   ├── section-cards.tsx
│   └── index.ts
├── common/         # Componentes reutilizables comunes
│   ├── data-table.tsx
│   └── index.ts
├── providers/      # Providers de contexto/theme
│   ├── theme-provider.tsx
│   └── index.ts
├── ui/            # Componentes UI base (shadcn/ui)
│   ├── button.tsx
│   ├── card.tsx
│   ├── ...
│   └── [otros componentes UI]
├── index.ts       # Exportaciones principales
└── README.md      # Este archivo
```

## 🏗️ Principios de Organización

### **1. Separación por Funcionalidad**
- **auth/**: Componentes de autenticación (login, logout, guards)
- **landing/**: Componentes específicos de la landing page
- **layout/**: Componentes que definen la estructura general de la aplicación
- **navigation/**: Componentes relacionados con la navegación y menús
- **dashboard/**: Componentes específicos de la página dashboard
- **common/**: Componentes reutilizables en múltiples páginas
- **providers/**: Proveedores de contexto, themes, etc.
- **ui/**: Componentes UI básicos (sistema de diseño)

### **2. Archivos de Índice**
Cada directorio tiene un `index.ts` que:
- Exporta todos los componentes del directorio
- Facilita las importaciones
- Mantiene un API limpio

### **3. Nomenclatura Consistente**
- **PascalCase** para nombres de componentes
- **kebab-case** para nombres de archivos
- Descriptivo y específico

## 📝 Cómo Usar

### Importaciones Individuales
```tsx
import { AppSidebar } from '@/components/layout/app-sidebar';
import { DataTable } from '@/components/common/data-table';
```

### Importaciones por Categoría
```tsx
import { AppSidebar, SiteHeader } from '@/components/layout';
import { NavMain, NavUser } from '@/components/navigation';
```

### Importación Global (desde index principal)
```tsx
import { 
  AppSidebar, 
  SiteHeader, 
  NavMain, 
  DataTable 
} from '@/components';
```

## 🔄 Extensión

Para añadir nuevos componentes:

1. **Determina la categoría** correcta basada en su función
2. **Crea el componente** en el directorio apropiado
3. **Exporta** desde el `index.ts` del directorio
4. **Documenta** si añades nuevas categorías

### Ejemplo: Añadir un nuevo componente de autenticación

```bash
# 1. Crear directorio si no existe
mkdir components/auth

# 2. Crear componente
touch components/auth/login-form.tsx

# 3. Crear index
echo "export { LoginForm } from './login-form';" > components/auth/index.ts

# 4. Añadir a index principal
# Editar components/index.ts y añadir:
# export * from './auth';
```

## 🎯 Beneficios

- **Escalabilidad**: Fácil añadir nuevos componentes sin romper la estructura
- **Mantenibilidad**: Componentes organizados por función y responsabilidad
- **Reutilización**: Separación clara entre componentes específicos y reutilizables
- **DX (Developer Experience)**: Importaciones limpias y consistentes
- **Team Collaboration**: Estructura predecible para todos los desarrolladores