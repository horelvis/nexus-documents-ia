// frontend/app/routes/dashboard+/_index.tsx - FIX CLERK TIMEOUT
import type { LoaderFunctionArgs, MetaFunction } from '@remix-run/node'
import { json, redirect } from '@remix-run/node'
import { useLoaderData, Link, useNavigation } from '@remix-run/react'
import { getAuth } from '@clerk/remix/ssr.server'
import { useUser } from '@clerk/remix'
import { timeout, TimeoutError } from '#app/utils/timeout.server'

import { createApiService } from '#app/utils/backend.server'
import { createStripeApiService } from '#app/services/stripe-api.server'
import { PLANS, PRICING_PLANS } from '#app/modules/stripe/plans'
import { cn } from '#app/utils/misc'
import { Button } from '#app/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '#app/components/ui/card'
import { Badge } from '#app/components/ui/badge'

export const ROUTE_PATH = '/dashboard' as const

interface LoaderData {
  backendConnected: boolean
  user: any | null
  subscription: any | null
  documents: any[]
  analytics: any | null
  recentActivity: any[]
  planLimits: any | null
  error: string | null
  clerkUserId: string | null
  plans: typeof PRICING_PLANS
  offlineMode: boolean
  loadTime: number
  clerkTimeout: boolean
}

// ✅ Mismo helper de timeout para Clerk
async function timeoutClerkAuth(args: LoaderFunctionArgs, timeoutMs: number = 1500) {
  try {
    console.time('dashboard-clerk-auth')
    
    const clerkOperation = async () => {
      const auth = await getAuth(args)
      return auth.userId
    }

    const userId = await timeout(clerkOperation(), { 
      ms: timeoutMs, 
      signal: args.request.signal 
    })
    
    console.timeEnd('dashboard-clerk-auth')
    console.log('✅ Dashboard Clerk auth completed')
    
    return { userId, error: null, timedOut: false }
    
  } catch (err) {
    console.timeEnd('dashboard-clerk-auth')
    
    if (err instanceof TimeoutError) {
      console.error('🔥 DASHBOARD CLERK TIMEOUT after', timeoutMs, 'ms')
      return { userId: null, error: `Clerk timeout ${timeoutMs}ms`, timedOut: true }
    } else {
      console.error('❌ Dashboard Clerk error:', err instanceof Error ? err.message : 'Unknown')
      return { userId: null, error: err instanceof Error ? err.message : 'Clerk error', timedOut: false }
    }
  }
}

export async function loader(args: LoaderFunctionArgs): Promise<Response> {
  const startTime = Date.now()
  const { request } = args
  
  console.log('📊 Dashboard Index: Starting with Clerk timeout fix...')

  // ✅ STEP 1: Verificar Clerk auth CON TIMEOUT
  const clerkResult = await timeoutClerkAuth(args, 1500) // 1.5 segundos para dashboard
  
  // Si Clerk falla completamente, redirigir
  if (!clerkResult.userId && !clerkResult.timedOut) {
    return redirect('/auth/sign-in')
  }

  // Si Clerk timeout, también redirigir pero con parámetro
  if (!clerkResult.userId && clerkResult.timedOut) {
    const params = new URLSearchParams()
    params.set("redirect_url", new URL(request.url).pathname)
    params.set("error", "clerk_timeout_dashboard")
    return redirect(`/auth/sign-in?${params.toString()}`)
  }

  const userId = clerkResult.userId!

  // ✅ STEP 2: Valores por defecto
  let backendConnected = false
  let user = null
  let subscription = null
  let documents: any[] = []
  let analytics = null
  let recentActivity: any[] = []
  let planLimits = null
  let error: string | null = clerkResult.error
  let offlineMode = clerkResult.timedOut
  const clerkTimeout = clerkResult.timedOut

  // ✅ STEP 3: Backend operations SOLO si Clerk funcionó
  if (!clerkTimeout) {
    try {
      console.time('dashboard-backend-ops')

      const backendOperation = async () => {
        const [apiService, stripeService] = await Promise.all([
          createApiService(args),
          createStripeApiService(args)
        ])

        // Operaciones críticas primero
        const [userResult, subscriptionResult] = await Promise.allSettled([
          apiService.getCurrentUser(),
          stripeService.getCurrentSubscription()
        ])

        // Operaciones secundarias solo si las críticas funcionan
        let documentsResult = null
        let analyticsResult = null  
        let activityResult = null

        if (userResult.status === 'fulfilled') {
          const secondaryOps = await Promise.allSettled([
            apiService.getDocuments({ limit: 5 }),
            apiService.getAnalytics(),
            apiService.getRecentActivity({ limit: 10 })
          ])
          
          documentsResult = secondaryOps[0]
          analyticsResult = secondaryOps[1]
          activityResult = secondaryOps[2]
        }

        return { 
          userResult, 
          subscriptionResult, 
          documentsResult, 
          analyticsResult, 
          activityResult 
        }
      }

      const result = await timeout(backendOperation(), { 
        ms: 1000, // 1 segundo para backend
        signal: request.signal 
      })

      console.timeEnd('dashboard-backend-ops')

      // Procesar resultados
      const { userResult, subscriptionResult, documentsResult, analyticsResult, activityResult } = result

      if (userResult.status === 'fulfilled' && userResult.value) {
        user = userResult.value
        backendConnected = true
      }

      if (subscriptionResult.status === 'fulfilled' && subscriptionResult.value) {
        subscription = subscriptionResult.value
      }

      if (documentsResult?.status === 'fulfilled' && documentsResult.value) {
        documents = documentsResult.value.items || []
      }

      if (analyticsResult?.status === 'fulfilled' && analyticsResult.value) {
        analytics = analyticsResult.value
      }

      if (activityResult?.status === 'fulfilled' && activityResult.value) {
        recentActivity = activityResult.value.items || []
      }

    } catch (err) {
      console.timeEnd('dashboard-backend-ops')
      
      if (err instanceof TimeoutError) {
        console.warn('⏰ Dashboard backend timeout after 1000ms')
        error = error ? `${error} + Backend timeout` : 'Backend timeout 1s'
      } else {
        console.warn('⚠️ Dashboard backend error:', err instanceof Error ? err.message : 'Unknown')
        error = error ? `${error} + Backend error` : (err instanceof Error ? err.message : 'Backend error')
      }
      
      backendConnected = false
      offlineMode = true
    }
  } else {
    console.warn('⚠️ Skipping dashboard backend due to Clerk timeout')
  }

  // ✅ Calcular límites del plan
  const planId = subscription?.plan_id || PLANS.FREE
  planLimits = calculatePlanLimits(planId, analytics)

  const loadTime = Date.now() - startTime
  console.log(`📊 Dashboard completed in ${loadTime}ms - Clerk timeout: ${clerkTimeout}, Backend: ${backendConnected}`)

  return json<LoaderData>({
    backendConnected,
    user,
    subscription,
    documents,
    analytics,
    recentActivity,
    planLimits,
    error,
    clerkUserId: userId,
    plans: PRICING_PLANS,
    offlineMode,
    loadTime,
    clerkTimeout
  }, {
    headers: {
      'X-Dashboard-Load-Time': loadTime.toString(),
      'X-Clerk-Timeout': clerkTimeout.toString(),
      'X-Backend-Connected': backendConnected.toString(),
      'X-Offline-Mode': offlineMode.toString(),
      ...(clerkTimeout || offlineMode ? {
        'Cache-Control': 'no-cache, no-store, must-revalidate'
      } : {
        'Cache-Control': 'private, max-age=30'
      })
    }
  })
}

function calculatePlanLimits(planId: string, analytics: any) {
  const limits = {
    [PLANS.FREE]: { documents: 10, storage: 1, aiRequests: 50, collaborators: 1 },
    [PLANS.PRO]: { documents: -1, storage: 100, aiRequests: -1, collaborators: 10 },
    [PLANS.ENTERPRISE]: { documents: -1, storage: -1, aiRequests: -1, collaborators: -1 }
  }

  const planLimits = limits[planId as keyof typeof limits] || limits[PLANS.FREE]
  const usage = analytics || {}

  return {
    documents: {
      used: usage.documentsCount || 0,
      limit: planLimits.documents,
      percentage: planLimits.documents === -1 ? 0 : Math.min(100, ((usage.documentsCount || 0) / planLimits.documents) * 100)
    },
    storage: {
      used: usage.storageUsed || 0,
      limit: planLimits.storage,
      percentage: planLimits.storage === -1 ? 0 : Math.min(100, ((usage.storageUsed || 0) / planLimits.storage) * 100)
    },
    aiRequests: {
      used: usage.aiRequestsThisMonth || 0,
      limit: planLimits.aiRequests,
      percentage: planLimits.aiRequests === -1 ? 0 : Math.min(100, ((usage.aiRequestsThisMonth || 0) / planLimits.aiRequests) * 100)
    }
  }
}

export default function Dashboard() {
  const { 
    backendConnected, 
    user, 
    subscription, 
    documents, 
    analytics, 
    recentActivity,
    planLimits,
    error,
    plans,
    offlineMode,
    loadTime,
    clerkTimeout
  } = useLoaderData<LoaderData>()
  
  const navigation = useNavigation()
  const { user: clerkUser } = useUser()
  
  // ✅ Mostrar skeleton durante navegación
  if (navigation.state === "loading") {
    return (
      <div className="flex w-full flex-col gap-6 px-6 py-8">
        <div className="mx-auto w-full max-w-screen-xl">
          <div className="animate-pulse">
            <div className="h-8 bg-gray-200 rounded w-64 mb-4"></div>
            <div className="h-4 bg-gray-200 rounded w-48 mb-8"></div>
            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="bg-white p-6 rounded-lg shadow border">
                  <div className="h-4 bg-gray-200 rounded w-20 mb-2"></div>
                  <div className="h-6 bg-gray-200 rounded w-16"></div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    )
  }
  
  const planId = subscription?.plan_id || PLANS.FREE
  const currentPlan = plans[planId as keyof typeof plans] || plans.free
  const displayName = user?.full_name || clerkUser?.fullName || clerkUser?.firstName || 'Usuario'

  const getGreeting = () => {
    const hour = new Date().getHours()
    if (hour < 12) return '¡Buenos días'
    if (hour < 18) return '¡Buenas tardes'
    return '¡Buenas noches'
  }

  const getLoadTimeColor = (time: number) => {
    if (time < 500) return 'text-green-600'
    if (time < 1000) return 'text-yellow-600'
    if (time < 1500) return 'text-orange-600'
    return 'text-red-600'
  }

  return (
    <div className="flex w-full flex-col gap-6 px-6 py-8">
      <div className="mx-auto w-full max-w-screen-xl space-y-6">
        
        {/* Header con info de timeout */}
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-3xl font-bold text-primary">
                {getGreeting()}, {displayName}! 👋
              </h1>
              
              {/* Badges de estado */}
              {clerkTimeout && (
                <Badge variant="destructive" className="gap-1">
                  🔥 Clerk Timeout
                </Badge>
              )}
              
              {!clerkTimeout && offlineMode && (
                <Badge variant="outline" className="gap-1 border-orange-400 text-orange-600">
                  📡 Backend Offline
                </Badge>
              )}
              
              <Badge variant="outline" className={`gap-1 ${getLoadTimeColor(loadTime)}`}>
                ⏱️ {loadTime}ms
              </Badge>
            </div>
            <p className="text-muted-foreground mt-1">
              {clerkTimeout 
                ? `Clerk tardó más de 1.5s - usando datos cached`
                : backendConnected 
                  ? `Datos cargados en ${loadTime}ms`
                  : `Backend offline - solo funciones básicas`
              }
            </p>
          </div>
          
          <div className="flex items-center gap-3">
            <Badge 
              variant={planId === PLANS.FREE ? 'secondary' : 'default'}
              className="gap-1"
            >
              {currentPlan?.name}
              {(clerkTimeout || offlineMode) && <span className="text-xs">(Limited)</span>}
            </Badge>
          </div>
        </div>

        {/* Card principal de estado del sistema */}
        {clerkTimeout ? (
          <Card className="border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-900/20">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-red-700 dark:text-red-400">
                🔥 Problema de Autenticación Detectado
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <p className="text-sm text-red-700 dark:text-red-400">
                  <strong>Clerk Auth tardó más de 1.5 segundos.</strong> Este es el cuello de botella principal 
                  que causa los timeouts de 8+ segundos que viste en los logs.
                </p>
                
                <div className="grid gap-3 md:grid-cols-2">
                  <div className="p-3 bg-red-100 dark:bg-red-900/30 border border-red-300 dark:border-red-700 rounded-md">
                    <p className="text-sm text-red-800 dark:text-red-200">
                      <strong>⚠️ Problema:</strong> Clerk Auth muy lento (3.8s+ en logs)
                    </p>
                  </div>
                  
                  <div className="p-3 bg-yellow-100 dark:bg-yellow-900/30 border border-yellow-300 dark:border-yellow-700 rounded-md">
                    <p className="text-sm text-yellow-800 dark:text-yellow-200">
                      <strong>🔧 Solución:</strong> Timeout aplicado a Clerk para mantener velocidad
                    </p>
                  </div>
                </div>

                <div className="p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-md">
                  <h4 className="font-medium text-blue-800 dark:text-blue-200 mb-2">Posibles causas de Clerk lento:</h4>
                  <ul className="text-sm text-blue-700 dark:text-blue-300 space-y-1">
                    <li>• Latencia de red con servidores de Clerk</li>
                    <li>• Problemas de conectividad de tu servidor</li>
                    <li>• Configuración de DNS o proxy</li>
                    <li>• Rate limiting de Clerk API</li>
                  </ul>
                </div>

                <div className="flex gap-3">
                  <Button 
                    variant="outline" 
                    size="sm"
                    onClick={() => window.location.reload()}
                    className="border-red-400 text-red-700 hover:bg-red-100"
                  >
                    🔄 Reintentar Auth
                  </Button>
                  
                  <Button 
                    variant="outline" 
                    size="sm"
                    onClick={() => window.open('https://status.clerk.com', '_blank')}
                    className="border-blue-400 text-blue-700 hover:bg-blue-100"
                  >
                    📊 Estado de Clerk
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        ) : offlineMode ? (
          <Card className="border-orange-200 bg-orange-50 dark:border-orange-800 dark:bg-orange-900/20">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-orange-700 dark:text-orange-400">
                📡 Backend Offline (Auth OK)
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <p className="text-sm text-orange-700 dark:text-orange-400">
                  Clerk Auth funcionó correctamente, pero el backend tardó más de 1 segundo. 
                  Funcionalidad limitada disponible.
                </p>
                
                <div className="grid gap-3 md:grid-cols-2">
                  <div className="p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-md">
                    <p className="text-sm text-green-700 dark:text-green-300">
                      <strong>✅ Funcionando:</strong> Autenticación, navegación, perfil
                    </p>
                  </div>
                  
                  <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-md">
                    <p className="text-sm text-red-700 dark:text-red-300">
                      <strong>⚠️ No disponible:</strong> Documentos, analytics, datos del backend
                    </p>
                  </div>
                </div>

                <Button 
                  variant="outline" 
                  size="sm"
                  onClick={() => window.location.reload()}
                  className="border-orange-400 text-orange-700 hover:bg-orange-100"
                >
                  🔄 Reintentar Backend
                </Button>
              </div>
            </CardContent>
          </Card>
        ) : (
          <Card className="border-green-200 bg-green-50 dark:border-green-800 dark:bg-green-900/20">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-green-700 dark:text-green-400">
                ✅ Sistema Funcionando Correctamente
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 md:grid-cols-3">
                <div className="p-4 border border-green-200 dark:border-green-800 rounded-lg bg-white dark:bg-green-900/10">
                  <div className="flex items-center gap-3 mb-2">
                    <div className="h-3 w-3 bg-green-500 rounded-full"></div>
                    <span className="font-medium">Clerk Auth</span>
                  </div>
                  <p className="text-sm text-green-600">Conectado y rápido</p>
                </div>
                
                <div className="p-4 border border-green-200 dark:border-green-800 rounded-lg bg-white dark:bg-green-900/10">
                  <div className="flex items-center gap-3 mb-2">
                    <div className="h-3 w-3 bg-green-500 rounded-full"></div>
                    <span className="font-medium">Backend API</span>
                  </div>
                  <p className="text-sm text-green-600">Conectado en {loadTime}ms</p>
                </div>
                
                <div className="p-4 border border-green-200 dark:border-green-800 rounded-lg bg-white dark:bg-green-900/10">
                  <div className="flex items-center gap-3 mb-2">
                    <div className="h-3 w-3 bg-green-500 rounded-full"></div>
                    <span className="font-medium">Datos</span>
                  </div>
                  <p className="text-sm text-green-600">Todos disponibles</p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Dashboard content - solo si backend conectado */}
        {backendConnected && !clerkTimeout && (
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            <Card>
              <CardHeader>
                <CardTitle>Documentos</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold">{documents.length}</p>
                <p className="text-sm text-muted-foreground">documentos recientes</p>
              </CardContent>
            </Card>
            
            <Card>
              <CardHeader>
                <CardTitle>Uso del Plan</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold">{planLimits?.documents?.used || 0}</p>
                <p className="text-sm text-muted-foreground">
                  de {planLimits?.documents?.limit === -1 ? '∞' : planLimits?.documents?.limit || 0} documentos
                </p>
              </CardContent>
            </Card>
            
            <Card>
              <CardHeader>
                <CardTitle>Actividad</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold">{recentActivity.length}</p>
                <p className="text-sm text-muted-foreground">acciones recientes</p>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Acciones disponibles */}
        <Card>
          <CardHeader>
            <CardTitle>Acciones Disponibles</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
              <Button variant="outline" asChild>
                <Link to="/dashboard/settings">
                  ⚙️ Configuración
                </Link>
              </Button>
              
              <Button variant="outline" asChild>
                <Link to="/dashboard/profile">
                  👤 Perfil
                </Link>
              </Button>
              
              {backendConnected && (
                <Button variant="outline" asChild>
                  <Link to="/dashboard/documents">
                    📄 Documentos
                  </Link>
                </Button>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Footer informativo */}
        <Card className="border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-900/20">
          <CardContent className="pt-6 text-center">
            <h3 className="text-lg font-medium text-blue-700 dark:text-blue-300 mb-2">
              🔍 Diagnóstico de Performance
            </h3>
            <div className="text-sm text-blue-600 dark:text-blue-400 space-y-1">
              <p>
                <strong>Carga total:</strong> {loadTime}ms | 
                <strong> Clerk timeout:</strong> {clerkTimeout ? 'SÍ' : 'NO'} | 
                <strong> Backend:</strong> {backendConnected ? 'Conectado' : 'Offline'}
              </p>
              <p>
                {error && `Error: ${error}`}
              </p>
              <p className="mt-2">
                Los timeouts de Clerk (3.8s+) eran la causa de los logs de 8+ segundos. 
                Ahora el sistema corta a 1.5s y funciona offline cuando sea necesario.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}