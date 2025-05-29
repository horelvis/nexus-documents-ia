// frontend/app/routes/dashboard+/_index.tsx
import type { LoaderFunctionArgs, MetaFunction } from '@remix-run/node'
import { json, redirect } from '@remix-run/node'
import { useLoaderData, Link } from '@remix-run/react'
import { getAuth } from '@clerk/remix/ssr.server'
import { 
  Plus, 
  Upload, 
  FileText, 
  TrendingUp, 
  Users, 
  Calendar,
  ArrowRight,
  AlertCircle,
  CheckCircle,
  Clock,
  Star,
  Zap,
  Crown,
  Activity,
  BarChart3
} from 'lucide-react'

import { createApiService } from '#app/utils/backend.server'
import { createStripeApiService } from '#app/services/stripe-api.server'
import { PLANS, PRICING_PLANS } from '#app/modules/stripe/plans'
import { cn } from '#app/utils/misc'
import { Button } from '#app/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '#app/components/ui/card'
import { Badge } from '#app/components/ui/badge'
import { Progress } from '#app/components/ui/progress'
import { Separator } from '#app/components/ui/separator'
import { ROUTE_PATH as ONBOARDING_PLAN_PATH } from '#app/routes/onboarding+/plan'
import { ROUTE_PATH as BILLING_PATH } from '#app/routes/dashboard+/settings.billing'

export const ROUTE_PATH = '/dashboard' as const

export const meta: MetaFunction = () => {
  return [{ title: 'Dashboard - Inicio' }]
}

export async function loader(args: LoaderFunctionArgs) {
  const { userId } = await getAuth(args)
  
  if (!userId) {
    return redirect('/auth/sign-in')
  }

  // Variables para tracking de estado y datos
  let backendConnected = false
  let user = null
  let subscription = null
  let documents = []
  let analytics = null
  let recentActivity = []
  let planLimits = null
  let error: string | null = null

  try {
    // Intentar obtener datos del backend
    const [apiService, stripeService] = await Promise.all([
      createApiService(args),
      createStripeApiService(args)
    ])

    const [
      userResult,
      subscriptionResult,
      documentsResult,
      analyticsResult,
      activityResult
    ] = await Promise.allSettled([
      apiService.getCurrentUser(),
      stripeService.getCurrentSubscription(),
      apiService.getDocuments({ limit: 5 }), // Últimos 5 documentos
      apiService.getAnalytics(),
      apiService.getRecentActivity({ limit: 10 })
    ])

    // Procesar resultados
    if (userResult.status === 'fulfilled' && userResult.value) {
      backendConnected = true
      user = userResult.value
    }

    if (subscriptionResult.status === 'fulfilled' && subscriptionResult.value) {
      subscription = subscriptionResult.value
    }

    if (documentsResult.status === 'fulfilled' && documentsResult.value) {
      documents = documentsResult.value.items || []
    }

    if (analyticsResult.status === 'fulfilled' && analyticsResult.value) {
      analytics = analyticsResult.value
    }

    if (activityResult.status === 'fulfilled' && activityResult.value) {
      recentActivity = activityResult.value.items || []
    }

    // Calcular límites según el plan
    const planId = subscription?.plan_id || PLANS.FREE
    planLimits = calculatePlanLimits(planId, analytics)

  } catch (err) {
    console.error('Error loading dashboard data:', err)
    error = err instanceof Error ? err.message : 'Error desconocido'
    backendConnected = false
  }

  return json({
    backendConnected,
    user,
    subscription,
    documents,
    analytics,
    recentActivity,
    planLimits,
    error,
    clerkUserId: userId,
    plans: PRICING_PLANS
  })
}

// Función helper para calcular límites del plan
function calculatePlanLimits(planId: string, analytics: any) {
  const limits = {
    [PLANS.FREE]: {
      documents: 10,
      storage: 1, // GB
      aiRequests: 50,
      collaborators: 1
    },
    [PLANS.PRO]: {
      documents: -1, // Unlimited
      storage: 100, // GB
      aiRequests: -1, // Unlimited
      collaborators: 10
    },
    [PLANS.ENTERPRISE]: {
      documents: -1, // Unlimited
      storage: -1, // Unlimited
      aiRequests: -1, // Unlimited
      collaborators: -1 // Unlimited
    }
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
      used: usage.storageUsed || 0, // En GB
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
    plans
  } = useLoaderData<typeof loader>()
  
  const { user: clerkUser } = useUser()
  
  const planId = subscription?.plan_id || PLANS.FREE
  const currentPlan = plans[planId as keyof typeof plans] || plans.free
  const isFreePlan = planId === PLANS.FREE

  // Función para obtener el saludo según la hora
  const getGreeting = () => {
    const hour = new Date().getHours()
    if (hour < 12) return '¡Buenos días'
    if (hour < 18) return '¡Buenas tardes'
    return '¡Buenas noches'
  }

  // Función para obtener icono del plan
  const getPlanIcon = (plan: string) => {
    switch (plan) {
      case PLANS.FREE:
        return null
      case PLANS.PRO:
        return <Zap className="h-4 w-4 text-yellow-500" />
      case PLANS.ENTERPRISE:
        return <Crown className="h-4 w-4 text-purple-500" />
      default:
        return null
    }
  }

  // Datos de fallback para modo offline
  const displayName = user?.full_name || clerkUser?.fullName || clerkUser?.firstName || 'Usuario'

  return (
    <div className="flex w-full flex-col gap-6 px-6 py-8">
      <div className="mx-auto w-full max-w-screen-xl space-y-6">
        
        {/* Header with greeting */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-primary">
              {getGreeting()}, {displayName}! 👋
            </h1>
            <p className="text-muted-foreground mt-1">
              {backendConnected 
                ? 'Aquí tienes un resumen de tu actividad reciente'
                : 'Modo sin conexión - Funcionalidad limitada'
              }
            </p>
          </div>
          
          <div className="flex items-center gap-3">
            <Badge 
              variant={planId === PLANS.FREE ? 'secondary' : 'default'}
              className="gap-1"
            >
              {getPlanIcon(planId)}
              {currentPlan?.name}
            </Badge>
            
            {!backendConnected && (
              <Badge variant="destructive" className="gap-1">
                <AlertCircle className="h-3 w-3" />
                Offline
              </Badge>
            )}
          </div>
        </div>

        {/* Estado de conectividad */}
        {!backendConnected && (
          <Card className="border-yellow-200 bg-yellow-50 dark:border-yellow-800 dark:bg-yellow-900/20">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-yellow-700 dark:text-yellow-400">
                <AlertCircle className="h-5 w-5" />
                Trabajando en modo offline
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-yellow-600 dark:text-yellow-300">
                No se pudo conectar con el servidor. Tu perfil de Clerk funciona normalmente, 
                pero algunas funciones pueden estar limitadas.
              </p>
              {error && (
                <p className="mt-2 text-xs text-yellow-500">
                  Error técnico: {error}
                </p>
              )}
              <Button 
                variant="outline" 
                size="sm"
                className="mt-3"
                onClick={() => window.location.reload()}
              >
                Intentar reconectar
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Quick Actions */}
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <Card className="hover:shadow-md transition-shadow cursor-pointer">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <Upload className="h-4 w-4 text-blue-500" />
                Subir Documento
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-muted-foreground mb-3">
                Agrega nuevos documentos para analizar
              </p>
              <Button size="sm" className="w-full">
                <Plus className="h-4 w-4 mr-1" />
                Subir
              </Button>
            </CardContent>
          </Card>

          <Card className="hover:shadow-md transition-shadow cursor-pointer">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <FileText className="h-4 w-4 text-green-500" />
                Documentos
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-muted-foreground mb-3">
                Ver y gestionar tus documentos
              </p>
              <Button size="sm" variant="outline" className="w-full">
                <ArrowRight className="h-4 w-4 mr-1" />
                Ver todos
              </Button>
            </CardContent>
          </Card>

          <Card className="hover:shadow-md transition-shadow cursor-pointer">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <BarChart3 className="h-4 w-4 text-purple-500" />
                Análisis
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-muted-foreground mb-3">
                Estadísticas y métricas detalladas
              </p>
              <Button 
                size="sm" 
                variant="outline" 
                className="w-full"
                disabled={!backendConnected}
              >
                <TrendingUp className="h-4 w-4 mr-1" />
                Ver análisis
              </Button>
            </CardContent>
          </Card>

          <Card className="hover:shadow-md transition-shadow cursor-pointer">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <Users className="h-4 w-4 text-orange-500" />
                Colaboración
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-muted-foreground mb-3">
                Invitar colaboradores al proyecto
              </p>
              <Button 
                size="sm" 
                variant="outline" 
                className="w-full"
                disabled={isFreePlan}
              >
                {isFreePlan ? (
                  <>
                    <Star className="h-4 w-4 mr-1" />
                    Pro Feature
                  </>
                ) : (
                  <>
                    <Plus className="h-4 w-4 mr-1" />
                    Invitar
                  </>
                )}
              </Button>
            </CardContent>
          </Card>
        </div>

        <div className="grid gap-6 lg:grid-cols-3">
          
          {/* Main content area - 2 columns */}
          <div className="lg:col-span-2 space-y-6">
            
            {/* Usage Stats (solo si backend conectado) */}
            {backendConnected && planLimits && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Activity className="h-5 w-5" />
                    Uso del Plan
                  </CardTitle>
                  <CardDescription>
                    Tu uso actual del plan {currentPlan?.name}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  
                  {/* Documents usage */}
                  <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span>Documentos</span>
                      <span className="text-muted-foreground">
                        {planLimits.documents.used} 
                        {planLimits.documents.limit === -1 ? '' : ` / ${planLimits.documents.limit}`}
                      </span>
                    </div>
                    {planLimits.documents.limit !== -1 && (
                      <Progress value={planLimits.documents.percentage} className="h-2" />
                    )}
                  </div>

                  {/* Storage usage */}
                  <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span>Almacenamiento</span>
                      <span className="text-muted-foreground">
                        {planLimits.storage.used.toFixed(1)} GB
                        {planLimits.storage.limit === -1 ? '' : ` / ${planLimits.storage.limit} GB`}
                      </span>
                    </div>
                    {planLimits.storage.limit !== -1 && (
                      <Progress value={planLimits.storage.percentage} className="h-2" />
                    )}
                  </div>

                  {/* AI Requests usage */}
                  <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span>Consultas IA (este mes)</span>
                      <span className="text-muted-foreground">
                        {planLimits.aiRequests.used}
                        {planLimits.aiRequests.limit === -1 ? '' : ` / ${planLimits.aiRequests.limit}`}
                      </span>
                    </div>
                    {planLimits.aiRequests.limit !== -1 && (
                      <Progress value={planLimits.aiRequests.percentage} className="h-2" />
                    )}
                  </div>

                  {/* Upgrade CTA si está cerca del límite o es free */}
                  {(isFreePlan || 
                    planLimits.documents.percentage > 80 || 
                    planLimits.storage.percentage > 80 || 
                    planLimits.aiRequests.percentage > 80) && (
                    <div className="pt-4 border-t">
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-sm font-medium">
                            {isFreePlan ? 'Actualiza para más funciones' : 'Cerca del límite'}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {isFreePlan 
                              ? 'Desbloquea uso ilimitado con Pro'
                              : 'Considera actualizar tu plan'
                            }
                          </p>
                        </div>
                        <Button size="sm" asChild>
                          <Link to={BILLING_PATH}>
                            <ArrowRight className="h-4 w-4" />
                          </Link>
                        </Button>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}

            {/* Recent Documents */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <FileText className="h-5 w-5" />
                  Documentos Recientes
                </CardTitle>
                <CardDescription>
                  Tus últimos documentos subidos
                </CardDescription>
              </CardHeader>
              <CardContent>
                {!backendConnected ? (
                  <div className="text-center py-8 text-muted-foreground">
                    <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
                    <p>Los documentos requieren conexión al servidor</p>
                  </div>
                ) : documents.length === 0 ? (
                  <div className="text-center py-8">
                    <FileText className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
                    <h3 className="text-lg font-medium mb-2">No hay documentos</h3>
                    <p className="text-muted-foreground mb-4">
                      Comienza subiendo tu primer documento
                    </p>
                    <Button>
                      <Upload className="h-4 w-4 mr-2" />
                      Subir Documento
                    </Button>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {documents.map((doc: any) => (
                      <div key={doc.id} className="flex items-center gap-3 p-3 rounded-lg border hover:bg-accent transition-colors">
                        <FileText className="h-4 w-4 text-blue-500 flex-shrink-0" />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium truncate">{doc.name || doc.filename}</p>
                          <p className="text-xs text-muted-foreground">
                            {doc.created_at ? new Date(doc.created_at).toLocaleDateString('es-ES') : 'Fecha desconocida'}
                          </p>
                        </div>
                        <Badge variant="outline" className="text-xs">
                          {doc.status || 'Procesado'}
                        </Badge>
                      </div>
                    ))}
                    <Button variant="outline" className="w-full mt-4">
                      Ver todos los documentos
                      <ArrowRight className="h-4 w-4 ml-2" />
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Sidebar - 1 column */}
          <div className="space-y-6">
            
            {/* Plan Info */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  {getPlanIcon(planId)}
                  Plan {currentPlan?.name}
                </CardTitle>
                <CardDescription>
                  {currentPlan?.description}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <p className="text-sm font-medium">Funciones incluidas:</p>
                  <ul className="space-y-1">
                    {currentPlan?.features.slice(0, 3).map((feature, index) => (
                      <li key={index} className="text-xs text-muted-foreground flex items-center gap-2">
                        <CheckCircle className="h-3 w-3 text-green-500 flex-shrink-0" />
                        {feature}
                      </li>
                    ))}
                    {currentPlan?.features.length > 3 && (
                      <li className="text-xs text-muted-foreground">
                        Y {currentPlan.features.length - 3} funciones más...
                      </li>
                    )}
                  </ul>
                </div>

                {isFreePlan && (
                  <div className="pt-4 border-t">
                    <Button className="w-full" asChild>
                      <Link to={ONBOARDING_PLAN_PATH}>
                        <Star className="h-4 w-4 mr-2" />
                        Actualizar a Pro
                      </Link>
                    </Button>
                  </div>
                )}

                <Button variant="outline" className="w-full" asChild>
                  <Link to={BILLING_PATH}>
                    Gestionar Plan
                  </Link>
                </Button>
              </CardContent>
            </Card>

            {/* Recent Activity */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Clock className="h-5 w-5" />
                  Actividad Reciente
                </CardTitle>
              </CardHeader>
              <CardContent>
                {!backendConnected ? (
                  <div className="text-center py-4 text-muted-foreground">
                    <Clock className="h-8 w-8 mx-auto mb-2 opacity-50" />
                    <p className="text-sm">Actividad no disponible offline</p>
                  </div>
                ) : recentActivity.length === 0 ? (
                  <div className="text-center py-4 text-muted-foreground">
                    <Clock className="h-8 w-8 mx-auto mb-2" />
                    <p className="text-sm">No hay actividad reciente</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {recentActivity.slice(0, 5).map((activity: any, index) => (
                      <div key={activity.id || index} className="flex items-start gap-3">
                        <div className="h-2 w-2 rounded-full bg-blue-500 mt-2 flex-shrink-0" />
                        <div className="space-y-1">
                          <p className="text-sm">{activity.description || activity.action}</p>
                          <p className="text-xs text-muted-foreground">
                            {activity.created_at 
                              ? new Date(activity.created_at).toLocaleString('es-ES')
                              : 'Hace un momento'
                            }
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Quick Stats */}
            {backendConnected && analytics && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <BarChart3 className="h-5 w-5" />
                    Estadísticas
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="text-center">
                      <p className="text-2xl font-bold text-primary">
                        {analytics.documentsCount || 0}
                      </p>
                      <p className="text-xs text-muted-foreground">Documentos</p>
                    </div>
                    <div className="text-center">
                      <p className="text-2xl font-bold text-primary">
                        {analytics.aiRequestsThisMonth || 0}
                      </p>
                      <p className="text-xs text-muted-foreground">Consultas IA</p>
                    </div>
                  </div>
                  <Separator />
                  <div className="text-center">
                    <p className="text-lg font-semibold text-primary">
                      {analytics.storageUsed?.toFixed(1) || '0.0'} GB
                    </p>
                    <p className="text-xs text-muted-foreground">Almacenamiento usado</p>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}