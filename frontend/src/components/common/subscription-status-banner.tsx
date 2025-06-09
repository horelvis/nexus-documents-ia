'use client'

import { useState, useEffect } from 'react'
import { useApiClient } from '@/lib/api-client'
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
  const [subscriptionData, setSubscriptionData] = useState<SubscriptionData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchSubscriptionStatus = async () => {
    try {
      setLoading(true)
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
  }, [])

  const handleReactivate = () => {
    if (onReactivate) {
      onReactivate()
    } else {
      // Redirigir a página de planes
      window.location.href = '/pricing'
    }
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
  
  // No mostrar nada si la suscripción está activa y no limitada
  if (subscription_status.is_active && !subscription_status.is_limited && compact) {
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
      <Alert variant={getStatusVariant()} className="mb-4">
        {getStatusIcon()}
        <AlertDescription className="flex items-center justify-between w-full">
          <span>{subscription_status.message}</span>
          {subscription_status.can_reactivate && (
            <Button 
              size="sm" 
              onClick={handleReactivate}
              className="ml-4"
            >
              Reactivar
              <ArrowRight className="h-3 w-3 ml-1" />
            </Button>
          )}
        </AlertDescription>
      </Alert>
    )
  }

  // Vista completa (no compacta)
  return (
    <Card className={`mb-6 ${getStatusColor()}`}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            {getStatusIcon()}
            <CardTitle className="text-lg">
              Estado de Suscripción
            </CardTitle>
            <Badge variant="outline" className="ml-2">
              {subscription_status.plan_type.toUpperCase()}
            </Badge>
          </div>
          {subscription_status.can_reactivate && (
            <Button onClick={handleReactivate}>
              <CreditCard className="h-4 w-4 mr-2" />
              Reactivar Suscripción
            </Button>
          )}
        </div>
      </CardHeader>
      
      <CardContent>
        <CardDescription className="text-base mb-4">
          {subscription_status.message}
        </CardDescription>
        
        {subscription_status.current_period_end && (
          <div className="text-sm text-muted-foreground mb-4">
            Período actual termina: {new Date(subscription_status.current_period_end).toLocaleDateString('es-ES')}
          </div>
        )}
        
        {subscription_status.is_limited && (
          <div className="bg-white/50 rounded-lg p-4 mt-4">
            <h4 className="font-semibold mb-2">Funciones disponibles en modo limitado:</h4>
            <ul className="text-sm space-y-1">
              <li>✅ Ver documentos existentes</li>
              <li>✅ Buscar en documentos existentes</li>
              <li>❌ Subir nuevos documentos</li>
              <li>❌ Usar chat con IA</li>
              <li>❌ Usar agentes especializados</li>
              <li>❌ Exportar documentos</li>
            </ul>
          </div>
        )}
        
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