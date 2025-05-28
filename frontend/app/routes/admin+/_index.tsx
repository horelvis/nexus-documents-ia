// frontend/app/routes/admin+/_index.tsx
import type { LoaderFunctionArgs } from '@remix-run/node'
import { useLoaderData } from '@remix-run/react'
import { json } from '@remix-run/node'
import { Users, FileText, Building, Activity, TrendingUp, Database, AlertCircle, CheckCircle } from 'lucide-react'
import { getAuth } from '@clerk/remix/ssr.server'

import { createApiClient } from '#app/utils/backend.server'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '#app/components/ui/card'
import { Badge } from '#app/components/ui/badge'

export async function loader({ request }: LoaderFunctionArgs) {
  const { userId } = await getAuth({ request })
  
  if (!userId) {
    throw new Response('Unauthorized', { status: 401 })
  }

  let systemStats = null
  let activityStats = null
  let backendConnected = false
  let error = null
  let isAdmin = false

  try {
    const apiClient = await createApiClient({ request })
    
    // Primero verificar si el usuario es admin obteniendo su información
    const currentUser = await apiClient.getCurrentUser()
    
    // Verificar si es admin (esto depende de cómo estructures los roles en tu backend)
    isAdmin = currentUser?.is_superuser || 
              currentUser?.roles?.some((role: any) => role.name === 'admin') ||
              false

    if (!isAdmin) {
      throw new Response('Forbidden', { status: 403 })
    }

    // Obtener estadísticas del sistema
    const [statsData, activityData] = await Promise.allSettled([
      apiClient.getSystemStats(),
      apiClient.getDocumentActivityStats(30),
    ])

    if (statsData.status === 'fulfilled') {
      systemStats = statsData.value
      backendConnected = true
    } else {
      console.error('Error obteniendo estadísticas:', statsData.reason)
    }

    if (activityData.status === 'fulfilled') {
      activityStats = activityData.value
    } else {
      console.error('Error obteniendo actividad:', activityData.reason)
    }

  } catch (err) {
    console.error('Error en admin loader:', err)
    error = err instanceof Error ? err.message : 'Error desconocido'
    
    // Si es un error de permisos, lanzarlo
    if (err instanceof Response && (err.status === 401 || err.status === 403)) {
      throw err
    }
  }

  return json({
    systemStats,
    activityStats,
    backendConnected,
    error,
    isAdmin,
  })
}

export default function AdminIndex() {
  const { systemStats, activityStats, backendConnected, error, isAdmin } = useLoaderData<typeof loader>()

  if (!isAdmin) {
    return (
      <div className="flex w-full flex-col gap-2 p-6 py-2">
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
          <h2 className="text-xl font-medium text-red-700 dark:text-red-400">
            Acceso Denegado
          </h2>
          <p className="text-sm font-normal text-red-600 dark:text-red-300">
            No tienes permisos de administrador para acceder a esta sección.
          </p>
        </div>
      </div>
    )
  }

  if (!backendConnected) {
    return (
      <div className="flex w-full flex-col gap-2 p-6 py-2">
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
          <h2 className="text-xl font-medium text-red-700 dark:text-red-400">
            Error de Conexión con Backend
          </h2>
          <p className="text-sm font-normal text-red-600 dark:text-red-300">
            No se pudo conectar con el backend para obtener las estadísticas. {error}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex w-full flex-col gap-6 p-6 py-2">
      {/* Header */}
      <div>
        <h2 className="text-3xl font-bold text-primary">Panel de Administración</h2>
        <p className="text-muted-foreground">
          Supervisa el sistema y gestiona usuarios y recursos
        </p>
      </div>

      {/* Estado de conexión */}
      <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4">
        <div className="flex items-center space-x-2">
          <div className="w-3 h-3 bg-green-500 rounded-full"></div>
          <span className="text-sm font-medium text-green-700 dark:text-green-300">
            Conectado al Backend
          </span>
          <Badge variant="secondary">API Activa</Badge>
        </div>
      </div>

      {/* Estadísticas principales */}
      {systemStats && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Total Usuarios</CardTitle>
              <Users className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{systemStats.users?.total || 0}</div>
              <p className="text-xs text-muted-foreground">
                {systemStats.users?.active || 0} activos
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Organizaciones</CardTitle>
              <Building className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{systemStats.tenants?.total || 0}</div>
              <p className="text-xs text-muted-foreground">
                {systemStats.tenants?.active || 0} activas
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Documentos</CardTitle>
              <FileText className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{systemStats.documents?.total || 0}</div>
              <p className="text-xs text-muted-foreground">
                {systemStats.documents?.indexed || 0} indexados
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Almacenamiento</CardTitle>
              <Database className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {systemStats.storage?.total_mb ? `${systemStats.storage.total_mb} MB` : '0 MB'}
              </div>
              <p className="text-xs text-muted-foreground">
                Espacio utilizado
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Estado de documentos */}
      {systemStats?.documents && (
        <Card>
          <CardHeader>
            <CardTitle>Estado de Documentos</CardTitle>
            <CardDescription>
              Distribución de documentos por estado de procesamiento
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="text-center p-4 border rounded-lg">
                <div className="text-2xl font-bold text-green-600">
                  {systemStats.documents.indexed}
                </div>
                <p className="text-sm text-muted-foreground">Indexados</p>
              </div>
              <div className="text-center p-4 border rounded-lg">
                <div className="text-2xl font-bold text-yellow-600">
                  {(systemStats.documents.total - systemStats.documents.indexed - (systemStats.documents.error || 0))}
                </div>
                <p className="text-sm text-muted-foreground">En Proceso</p>
              </div>
              <div className="text-center p-4 border rounded-lg">
                <div className="text-2xl font-bold text-red-600">
                  {systemStats.documents.error || 0}
                </div>
                <p className="text-sm text-muted-foreground">Con Error</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Tipos de documentos */}
      {systemStats?.documents?.by_type && (
        <Card>
          <CardHeader>
            <CardTitle>Documentos por Tipo</CardTitle>
            <CardDescription>
              Distribución de documentos según su formato
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {Object.entries(systemStats.documents.by_type).map(([type, count]) => (
                <div key={type} className="text-center p-3 border rounded-lg">
                  <Badge variant="secondary" className="mb-2">
                    {type.toUpperCase()}
                  </Badge>
                  <div className="text-xl font-bold">{count as number}</div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Estadísticas de actividad */}
      {activityStats && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Actividad General (30 días)</CardTitle>
              <CardDescription>
                Métricas de uso del sistema
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="flex justify-between items-center">
                  <span className="text-sm text-muted-foreground">Usuarios activos</span>
                  <span className="font-bold">{activityStats.general?.active_users || 0}</span>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Formatos Populares</CardTitle>
              <CardDescription>
                Tipos de documentos más consultados
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {activityStats.top_formats?.slice(0, 5).map((format: any, index: number) => (
                  <div key={index} className="flex justify-between items-center">
                    <Badge variant="outline">{format.format?.toUpperCase()}</Badge>
                    <span className="font-medium">{format.count} vistas</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Usuarios más activos */}
      {activityStats?.top_users && (
        <Card>
          <CardHeader>
            <CardTitle>Usuarios Más Activos</CardTitle>
            <CardDescription>
              Usuarios con mayor actividad en los últimos 30 días
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {activityStats.top_users.slice(0, 5).map((user: any, index: number) => (
                <div key={index} className="flex items-center justify-between p-3 border rounded-lg">
                  <div>
                    <div className="font-medium">{user.name || user.email}</div>
                    <div className="text-sm text-muted-foreground">{user.email}</div>
                  </div>
                  <Badge variant="secondary">
                    {user.view_count} vistas
                  </Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Documentos más consultados */}
      {activityStats?.top_queried_docs && (
        <Card>
          <CardHeader>
            <CardTitle>Documentos Más Consultados por IA</CardTitle>
            <CardDescription>
              Documentos más utilizados en consultas de IA
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {activityStats.top_queried_docs.slice(0, 5).map((doc: any, index: number) => (
                <div key={index} className="flex items-center justify-between p-3 border rounded-lg">
                  <div className="flex-1">
                    <div className="font-medium">{doc.title}</div>
                    <div className="text-sm text-muted-foreground">ID: {doc.id}</div>
                  </div>
                  <Badge variant="secondary">
                    {doc.query_count} consultas
                  </Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Acciones rápidas */}
      <Card>
        <CardHeader>
          <CardTitle>Acciones de Administración</CardTitle>
          <CardDescription>
            Funciones administrativas disponibles via API
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <button 
              className="p-4 border rounded-lg hover:bg-muted/50 transition-colors text-left"
              onClick={() => window.open(`${window.location.origin}/admin/users`, '_blank')}
            >
              <Users className="h-6 w-6 mb-2 text-blue-500" />
              <div className="font-medium">Gestionar Usuarios</div>
              <div className="text-sm text-muted-foreground">Administrar usuarios via API</div>
            </button>
            
            <button 
              className="p-4 border rounded-lg hover:bg-muted/50 transition-colors text-left"
              onClick={() => window.open(`${window.location.origin}/admin/tenants`, '_blank')}
            >
              <Building className="h-6 w-6 mb-2 text-green-500" />
              <div className="font-medium">Gestionar Organizaciones</div>
              <div className="text-sm text-muted-foreground">Administrar tenants del sistema</div>
            </button>
            
            <button 
              className="p-4 border rounded-lg hover:bg-muted/50 transition-colors text-left"
              onClick={() => window.open(`${window.location.origin}/admin/documents`, '_blank')}
            >
              <FileText className="h-6 w-6 mb-2 text-purple-500" />
              <div className="font-medium">Ver Documentos</div>
              <div className="text-sm text-muted-foreground">Supervisar todos los documentos</div>
            </button>
          </div>
        </CardContent>
      </Card>

      {/* Estado del sistema */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center">
            <TrendingUp className="h-5 w-5 mr-2 text-green-500" />
            Estado del Sistema
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="flex items-center space-x-2">
              <div className="w-3 h-3 bg-green-500 rounded-full"></div>
              <span className="text-sm">Backend API</span>
              <Badge variant="secondary">Conectado</Badge>
            </div>
            
            <div className="flex items-center space-x-2">
              <div className="w-3 h-3 bg-green-500 rounded-full"></div>
              <span className="text-sm">Base de Datos</span>
              <Badge variant="secondary">Activa</Badge>
            </div>
            
            <div className="flex items-center space-x-2">
              <div className="w-3 h-3 bg-green-500 rounded-full"></div>
              <span className="text-sm">Procesamiento IA</span>
              <Badge variant="secondary">Disponible</Badge>
            </div>
          </div>

          <div className="mt-4 p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-md">
            <p className="text-sm text-blue-700 dark:text-blue-300">
              <strong>Nota:</strong> Todos los datos se obtienen desde el backend via API REST. 
              No hay dependencias de Prisma en el frontend.
            </p>
          </div>

          {/* Información adicional del sistema */}
          <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-md">
              <div className="flex items-center space-x-2">
                <CheckCircle className="h-4 w-4 text-green-600" />
                <span className="text-sm font-medium text-green-700 dark:text-green-300">
                  Autenticación Clerk
                </span>
              </div>
              <p className="text-xs text-green-600 dark:text-green-400 mt-1">
                JWT tokens validados correctamente
              </p>
            </div>
            
            <div className="p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-md">
              <div className="flex items-center space-x-2">
                <CheckCircle className="h-4 w-4 text-green-600" />
                <span className="text-sm font-medium text-green-700 dark:text-green-300">
                  Comunicación API
                </span>
              </div>
              <p className="text-xs text-green-600 dark:text-green-400 mt-1">
                Frontend ↔ Backend sincronizado
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Resumen de la arquitectura */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center">
            <Activity className="h-5 w-5 mr-2 text-blue-500" />
            Arquitectura del Sistema
          </CardTitle>
          <CardDescription>
            Información sobre la arquitectura actual sin Prisma
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div className="flex items-center justify-between p-3 border rounded-lg bg-muted/20">
              <div>
                <div className="font-medium">Frontend (Remix)</div>
                <div className="text-sm text-muted-foreground">UI + Clerk Auth + API Client</div>
              </div>
              <Badge variant="default">Activo</Badge>
            </div>
            
            <div className="flex items-center justify-center">
              <div className="text-center">
                <div className="text-2xl">↕️</div>
                <div className="text-xs text-muted-foreground">API REST</div>
              </div>
            </div>
            
            <div className="flex items-center justify-between p-3 border rounded-lg bg-muted/20">
              <div>
                <div className="font-medium">Backend (FastAPI)</div>
                <div className="text-sm text-muted-foreground">Business Logic + SQLAlchemy + AI</div>
              </div>
              <Badge variant="default">Conectado</Badge>
            </div>
            
            <div className="flex items-center justify-center">
              <div className="text-center">
                <div className="text-2xl">↕️</div>
                <div className="text-xs text-muted-foreground">SQL</div>
              </div>
            </div>
            
            <div className="flex items-center justify-between p-3 border rounded-lg bg-muted/20">
              <div>
                <div className="font-medium">Base de Datos</div>
                <div className="text-sm text-muted-foreground">PostgreSQL + Vector Store</div>
              </div>
              <Badge variant="default">Operacional</Badge>
            </div>
          </div>
          
          <div className="mt-4 p-3 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-md">
            <div className="flex items-center space-x-2">
              <AlertCircle className="h-4 w-4 text-yellow-600" />
              <span className="text-sm font-medium text-yellow-700 dark:text-yellow-300">
                Migración Completada
              </span>
            </div>
            <p className="text-xs text-yellow-600 dark:text-yellow-400 mt-1">
              Frontend migrado de Prisma a API REST. Todos los datos provienen del backend.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}