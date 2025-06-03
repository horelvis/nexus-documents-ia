# Nexus Document Backend - Frontend Integration Setup

Esta guía te ayudará a configurar la integración entre la aplicación Next.js y el backend con Clerk para autenticación.

## 🚀 Configuración Rápida

### 1. Instalar Dependencias

```bash
cd frontend
npm install
# o
yarn install
```

### 2. Configurar Variables de Entorno

Copia el archivo de ejemplo y configura las variables:

```bash
cp .env.local.example .env.local
```

Edita `.env.local` con tus valores:

```env
# Clerk Authentication (Obtener de https://clerk.com)
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
CLERK_SECRET_KEY=sk_test_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Clerk URLs
NEXT_PUBLIC_CLERK_SIGN_IN_URL=/auth/login
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/auth/register
NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL=/dashboard
NEXT_PUBLIC_CLERK_AFTER_SIGN_UP_URL=/dashboard

# Backend API
NEXT_PUBLIC_API_URL=http://localhost:8000
INTERNAL_API_URL=http://localhost:8000

# Webhooks
CLERK_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxxxxxxxxxxxxx

# App Configuration
NEXT_PUBLIC_APP_NAME="Nexus Document Backend"
NEXT_PUBLIC_APP_URL=http://localhost:3000
```

### 3. Configurar Clerk

1. **Crear cuenta en Clerk**: Ve a [clerk.com](https://clerk.com) y crea una cuenta
2. **Crear aplicación**: Crea una nueva aplicación en el dashboard
3. **Obtener keys**: Copia las keys desde el dashboard de Clerk
4. **Configurar URLs de redirect**:
   - Sign-in URL: `/auth/login`
   - Sign-up URL: `/auth/register`
   - After sign-in: `/dashboard`
   - After sign-up: `/dashboard`

### 4. Configurar Webhooks de Clerk

1. En el dashboard de Clerk, ve a **Webhooks**
2. Crea un nuevo webhook con la URL: `http://localhost:3000/api/webhooks/clerk`
3. Selecciona los eventos:
   - `user.created`
   - `user.updated`
   - `user.deleted`
4. Copia el secret del webhook y agrégalo a `.env.local`

### 5. Ejecutar la Aplicación

```bash
npm run dev
```

La aplicación estará disponible en `http://localhost:3000`

## 📋 Estructura del Proyecto

```
frontend/
├── src/
│   ├── app/                    # App Router de Next.js
│   │   ├── auth/              # Páginas de autenticación
│   │   ├── dashboard/         # Dashboard principal
│   │   └── api/               # API routes
│   ├── components/            # Componentes reutilizables
│   │   ├── auth/             # Componentes de autenticación
│   │   └── ui/               # Componentes UI
│   ├── hooks/                # Custom hooks
│   ├── lib/                  # Utilidades y configuración
│   └── middleware.ts         # Middleware de autenticación
```

## 🔗 Características Implementadas

### ✅ **Autenticación con Clerk**
- **Login/Register**: Páginas completas con componentes de Clerk
- **Middleware**: Protección automática de rutas
- **User Navigation**: Dropdown con perfil y logout
- **Webhooks**: Sincronización automática con backend

### ✅ **Cliente API**
- **Axios Client**: Configurado con interceptors
- **Autenticación automática**: Headers de autorización automáticos
- **Error handling**: Manejo de errores 401/403
- **Types**: TypeScript para todas las respuestas

### ✅ **Hooks de React**
- **useCurrentUser**: Gestión del usuario actual
- **useDocuments**: CRUD de documentos
- **useDocument**: Gestión de documento individual
- **useSearch**: Búsqueda de documentos
- **useChat**: Chat con documentos

### ✅ **Dashboard**
- **Stats Cards**: Métricas de documentos
- **Upload Dialog**: Subida de archivos
- **Document Grid**: Lista de documentos recientes
- **Quick Actions**: Acciones rápidas

## 🔧 API Endpoints Disponibles

### Autenticación
```typescript
api.auth.syncUser(userData)      // Sincronizar usuario
api.auth.getCurrentUser()        // Obtener usuario actual
```

### Documentos
```typescript
api.documents.list(params)       // Listar documentos
api.documents.get(id)           // Obtener documento
api.documents.upload(file, meta) // Subir documento
api.documents.delete(id)        // Eliminar documento
api.documents.generateSummary(id) // Generar resumen
```

### Búsqueda
```typescript
api.search.documents(query)     // Buscar documentos
api.search.ask(question)        // Hacer pregunta
```

### Chat
```typescript
api.chat.send(message)          // Enviar mensaje
api.chat.getSessions()          // Obtener sesiones
```

## 🎨 Componentes UI

### Componentes Base
- `Button`, `Input`, `Label`
- `Card`, `Badge`, `Avatar`
- `Dialog`, `DropdownMenu`
- `Toaster` (notificaciones)

### Componentes de Autenticación
- `UserNav`: Navegación del usuario
- `SignIn`/`SignUp`: Componentes de Clerk

## 🔄 Flujo de Autenticación

1. **Usuario accede**: Middleware verifica autenticación
2. **Redirect a login**: Si no autenticado → `/auth/login`
3. **Clerk authentication**: Usuario se autentica con Clerk
4. **Webhook sync**: Clerk envía webhook → sincroniza con backend
5. **Dashboard access**: Usuario accede al dashboard

## 🚨 Troubleshooting

### Error: "Clerk keys not found"
- Verifica que las variables de entorno estén configuradas
- Reinicia el servidor de desarrollo

### Error: "API connection failed"
- Verifica que el backend esté ejecutándose en puerto 8000
- Revisa las URLs en `.env.local`

### Error: "Webhook not working"
- Verifica el secret del webhook
- Usa ngrok para testing local: `ngrok http 3000`

### Error: "User not syncing"
- Revisa los logs del webhook en Clerk dashboard
- Verifica que el backend esté recibiendo las requests

## 🔄 Próximos Pasos

1. **Implementar más páginas**:
   - Página de documentos completa
   - Página de búsqueda
   - Chat interface

2. **Mejorar UI/UX**:
   - Loading states
   - Error boundaries
   - Responsive design

3. **Features avanzadas**:
   - File preview
   - Drag & drop upload
   - Real-time notifications

## 📚 Recursos

- [Clerk Documentation](https://clerk.com/docs)
- [Next.js App Router](https://nextjs.org/docs/app)
- [Tailwind CSS](https://tailwindcss.com)
- [Radix UI](https://radix-ui.com)

## 🤝 Contribuir

1. Fork el proyecto
2. Crea una branch (`git checkout -b feature/nueva-feature`)
3. Commit cambios (`git commit -am 'Add nueva feature'`)
4. Push a la branch (`git push origin feature/nueva-feature`)
5. Abre un Pull Request