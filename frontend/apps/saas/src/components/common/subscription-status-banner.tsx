'use client'

import { useState, useEffect } from 'react'
import { useApiClient } from '@/lib/api-client'
import { useUserContext } from '@/contexts/user-context'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { 
  AlertTriangle, 
  CheckCircle, 
  CreditCard, 
  Clock, 
  XCircle,
  ArrowRight,
  RefreshCw
} from 'lucide-react'

interface SubscriptionStatus {
  plan_type: string
  status: string
  is_active: boolean
  is_limited: boolean
  current_period_end: string | null
  can_reactivate: boolean
  permissions: Record<string, any>
  message: string
}

interface SubscriptionData {
  id: string
  plan_id: string
  status: string
  current_period_end: number
  subscription_status: SubscriptionStatus
}

interface SubscriptionStatusBannerProps {
  /** Si está en modo compacto, solo muestra un banner pequeño */
  compact?: boolean
  /** Callback cuando el usuario hace clic en "Reactivar suscripción" */
  onReactivate?: () => void
}

export function SubscriptionStatusBanner({ 
  compact = false, 
  onReactivate 
}: SubscriptionStatusBannerProps) {
  const apiClient = useApiClient()
  const { backendUser } = useUserContext()
  const [subscriptionData, setSubscriptionData] = useState<SubscriptionData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchSubscriptionStatus = async () => {
    try {
      setLoading(true)
      
      // Check if we already have subscription info from user context
      if (backendUser?.subscription_plan && backendUser?.subscription_status) {
        const contextSubscription = {
          id: 'from_context',
          plan_id: backendUser.subscription_plan,
          status: backendUser.subscription_status,
          current_period_end: 0,
          subscription_status: {
            plan_type: backendUser.subscription_plan,
            status: backendUser.subscription_status,
            is_active: backendUser.subscription_status === 'active',
            is_limited: backendUser.subscription_status !== 'active',
            current_period_end: null,
            can_reactivate: backendUser.subscription_status === 'canceled' || backendUser.subscription_status === 'past_due',
            permissions: {},
            message: ''
          }
        }
        setSubscriptionData(contextSubscription)
        setError(null)
        setLoading(false)
        return
      }
      
      // Only make API call if we don't have subscription info
      const response = await apiClient.get('/stripe/subscription')
      
      if (response.error) {
        setError(response.error)
        return
      }
      
      setSubscriptionData(response.data)
      setError(null)
    } catch (err) {
      setError('Error cargando estado de suscripción')
      console.error('Error fetching subscription:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchSubscriptionStatus()
  }, [backendUser])

  const handleReactivate = () => {
    if (onReactivate) {
      onReactivate()
    } else {
      // Redirigir a página de planes para renovar o iniciar nueva suscripción
      window.location.href = '/pricing'
    }
  }

  const handleNewSubscription = () => {
    // Ir a planes para iniciar nueva suscripción
    window.location.href = '/pricing?new=true'
  }

  if (loading) {
    return compact ? (
      <Alert>
        <RefreshCw className="h-4 w-4 animate-spin" />
        <AlertDescription>Cargando estado de suscripción...</AlertDescription>
      </Alert>
    ) : null
  }

  if (error || !subscriptionData) {
    return compact ? (
      <Alert variant="destructive">
        <XCircle className="h-4 w-4" />
        <AlertDescription>Error cargando suscripción</AlertDescription>
      </Alert>
    ) : null
  }

  const { subscription_status } = subscriptionData
  
  // Solo mostrar si la suscripción ha caducado (is_limited = true significa caducada)
  // No mostrar para estados activos o de procesamiento
  if (subscription_status.is_active && !subscription_status.is_limited) {
    return null
  }
  
  // Solo mostrar si realmente ha caducado, no para estados temporales
  const hasExpired = subscription_status.is_limited || 
    subscription_status.status === 'canceled' || 
    subscription_status.status === 'past_due'
  
  if (!hasExpired) {
    return null
  }

  const getStatusIcon = () => {
    if (subscription_status.is_limited) {
      return <AlertTriangle className="h-4 w-4" />
    }
    if (subscription_status.status === 'canceled') {
      return <Clock className="h-4 w-4" />
    }
    if (subscription_status.status === 'past_due') {
      return <CreditCard className="h-4 w-4" />
    }
    return <CheckCircle className="h-4 w-4" />
  }

  const getStatusVariant = () => {
    if (subscription_status.is_limited) {
      return 'destructive' as const
    }
    if (subscription_status.status === 'canceled' || subscription_status.status === 'past_due') {
      return 'default' as const
    }
    return 'default' as const
  }

  const getStatusColor = () => {
    if (subscription_status.is_limited) {
      return 'bg-red-100 text-red-800 border-red-200'
    }
    if (subscription_status.status === 'canceled') {
      return 'bg-yellow-100 text-yellow-800 border-yellow-200'
    }
    if (subscription_status.status === 'past_due') {
      return 'bg-orange-100 text-orange-800 border-orange-200'
    }
    return 'bg-green-100 text-green-800 border-green-200'
  }

  if (compact) {
    return (
      <Alert variant="destructive" className="mb-4">
        <AlertTriangle className="h-4 w-4" />
        <AlertDescription className="flex items-center justify-between w-full">
          <span>Tu suscripción ha caducado. Renueva tu plan para continuar.</span>
          <div className="flex gap-2 ml-4">
            {subscription_status.can_reactivate && (
              <Button 
                size="sm" 
                onClick={handleReactivate}
                variant="outline"
              >
                Renovar
              </Button>
            )}
            <Button 
              size="sm" 
              onClick={handleNewSubscription}
            >
              Nueva suscripción
              <ArrowRight className="h-3 w-3 ml-1" />
            </Button>
          </div>
        </AlertDescription>
      </Alert>
    )
  }

  // Vista completa (no compacta)
  return (
    <Card className="mb-6 bg-red-50 border-red-200">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <AlertTriangle className="h-5 w-5 text-red-600" />
            <CardTitle className="text-lg text-red-800">
              Suscripción Caducada
            </CardTitle>
            <Badge variant="destructive" className="ml-2">
              {subscription_status.plan_type.toUpperCase()}
            </Badge>
          </div>
          <div className="flex gap-2">
            {subscription_status.can_reactivate && (
              <Button onClick={handleReactivate} variant="outline">
                <CreditCard className="h-4 w-4 mr-2" />
                Renovar Plan
              </Button>
            )}
            <Button onClick={handleNewSubscription}>
              <CreditCard className="h-4 w-4 mr-2" />
              Nueva Suscripción
            </Button>
          </div>
        </div>
      </CardHeader>
      
      <CardContent>
        <CardDescription className="text-base mb-4 text-red-700">
          Tu suscripción ha caducado y necesitas renovarla para continuar usando todas las funcionalidades. 
          Puedes renovar tu plan actual o iniciar una nueva suscripción.
        </CardDescription>
        
        {subscription_status.current_period_end && (
          <div className="text-sm text-red-600 mb-4">
            Caducó el: {new Date(subscription_status.current_period_end).toLocaleDateString('es-ES')}
          </div>
        )}
        
        <div className="bg-white rounded-lg p-4 mt-4 border-l-4 border-red-500">
          <h4 className="font-semibold mb-3 text-red-800">Acceso Limitado - Renueva para restaurar:</h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-sm">
            <div className="text-green-700">✅ Ver documentos existentes</div>
            <div className="text-red-700">❌ Subir nuevos documentos</div>
            <div className="text-green-700">✅ Buscar documentos</div>
            <div className="text-red-700">❌ Chat con IA</div>
            <div className="text-green-700">✅ Descargar documentos</div>
            <div className="text-red-700">❌ Agentes especializados</div>
            <div className="text-red-700">❌ Exportar documentos</div>
            <div className="text-red-700">❌ Acceso API</div>
          </div>
        </div>
        
        {!subscription_status.is_limited && subscription_status.permissions && (
          <div className="bg-white/50 rounded-lg p-4 mt-4">
            <h4 className="font-semibold mb-2">Tu plan incluye:</h4>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div>
                📄 Documentos: {
                  subscription_status.permissions.max_documents === -1 
                    ? 'Ilimitados' 
                    : subscription_status.permissions.max_documents
                }
              </div>
              <div>
                📤 Subidas/mes: {
                  subscription_status.permissions.max_monthly_uploads === -1 
                    ? 'Ilimitadas' 
                    : subscription_status.permissions.max_monthly_uploads
                }
              </div>
              <div>
                💬 Chat con IA: {subscription_status.permissions.can_use_chat ? '✅' : '❌'}
              </div>
              <div>
                🤖 Agentes: {subscription_status.permissions.can_use_agents ? '✅' : '❌'}
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export default SubscriptionStatusBanner