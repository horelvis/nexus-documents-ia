"use client"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { 
  IconAlertCircle,
  IconCrown,
  IconCheck,
  IconX
} from "@tabler/icons-react"
import { useRouter } from "next/navigation"

interface SubscriptionErrorDialogProps {
  isOpen: boolean
  onClose: () => void
  errorDetail: {
    message: string
    subscription_status?: {
      plan_type: string
      status: string
      permissions: {
        max_documents: number
        max_monthly_uploads: number
        can_use_agents: boolean
        can_export_documents: boolean
        can_use_api: boolean
        max_file_size_mb: number
        [key: string]: any
      }
      message: string
    }
    action_required?: string
  }
}

export function SubscriptionErrorDialog({
  isOpen,
  onClose,
  errorDetail,
}: SubscriptionErrorDialogProps) {
  const router = useRouter()

  const handleUpgrade = () => {
    onClose()
    setTimeout(() => {
      router.push(`/plans`)
    }, 100)
  }

  const handleRenewSubscription = () => {
    onClose()
    setTimeout(() => {
      router.push('/pricing')
    }, 100)
  }

  // Determinar si la suscripción ha caducado
  const hasExpired = errorDetail.subscription_status?.is_limited || 
    errorDetail.subscription_status?.status === 'canceled' || 
    errorDetail.subscription_status?.status === 'past_due'

  const getPlanDisplayName = (planType: string) => {
    const planNames: Record<string, string> = {
      'free': 'Plan Gratuito',
      'professional': 'Plan Profesional',
      'enterprise': 'Plan Empresarial'
    }
    return planNames[planType] || planType
  }

  const getPermissionDisplay = (key: string, value: any) => {
    const labels: Record<string, string> = {
      'max_documents': 'Documentos máximos',
      'max_monthly_uploads': 'Cargas mensuales',
      'can_use_agents': 'Agentes AI',
      'can_export_documents': 'Exportar documentos',
      'can_use_api': 'Acceso API',
      'max_file_size_mb': 'Tamaño máximo de archivo'
    }
    
    const label = labels[key] || key
    
    if (typeof value === 'boolean') {
      return {
        label,
        value: value ? (
          <IconCheck className="h-4 w-4 text-green-600" />
        ) : (
          <IconX className="h-4 w-4 text-red-600" />
        )
      }
    }
    
    if (key === 'max_file_size_mb') {
      return { label, value: `${value} MB` }
    }
    
    return { label, value: value.toString() }
  }

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <IconAlertCircle className="h-5 w-5 text-red-600" />
            {hasExpired ? 'Suscripción Caducada' : 'Función no disponible'}
          </DialogTitle>
          <DialogDescription>
            {hasExpired 
              ? 'Tu suscripción ha caducado. Renueva tu plan o inicia una nueva suscripción para continuar.'
              : errorDetail.message
            }
          </DialogDescription>
        </DialogHeader>

        {errorDetail.subscription_status && (
          <div className="space-y-4">
            <Alert>
              <IconCrown className="h-4 w-4" />
              <AlertTitle>Tu plan actual</AlertTitle>
              <AlertDescription className="mt-2">
                <div className="flex items-center gap-2 mb-3">
                  <Badge variant="secondary">
                    {getPlanDisplayName(errorDetail.subscription_status.plan_type)}
                  </Badge>
                  <Badge 
                    variant={errorDetail.subscription_status.status === 'active' ? 'default' : 'destructive'}
                  >
                    {errorDetail.subscription_status.status === 'active' ? 'Activo' : 'Inactivo'}
                  </Badge>
                </div>
                
                <div className="space-y-2">
                  <p className="text-sm font-medium mb-2">Límites de tu plan:</p>
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    {Object.entries(errorDetail.subscription_status.permissions)
                      .filter(([key]) => ['max_documents', 'max_monthly_uploads', 'can_use_agents', 'can_export_documents', 'max_file_size_mb'].includes(key))
                      .map(([key, value]) => {
                        const display = getPermissionDisplay(key, value)
                        return (
                          <div key={key} className="flex items-center justify-between py-1">
                            <span className="text-muted-foreground">{display.label}:</span>
                            <span className="font-medium">{display.value}</span>
                          </div>
                        )
                      })}
                  </div>
                </div>
              </AlertDescription>
            </Alert>

            {errorDetail.action_required === 'upgrade_plan' && (
              <Alert className="border-gray-800 bg-black text-white">
                <IconCrown className="h-4 w-4 text-yellow-400" />
                <AlertTitle className="text-white">Actualiza tu plan</AlertTitle>
                <AlertDescription className="text-gray-200">
                  Mejora a un plan superior para acceder a todas las funciones avanzadas,
                  incluyendo agentes AI, exportación de documentos y mucho más.
                </AlertDescription>
              </Alert>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cerrar
          </Button>
          {hasExpired ? (
            <div className="flex gap-2">
              <Button onClick={handleRenewSubscription} variant="outline" className="gap-2">
                <IconCrown className="h-4 w-4" />
                Renovar Plan
              </Button>
              <Button onClick={handleRenewSubscription} className="gap-2">
                <IconCrown className="h-4 w-4" />
                Nueva Suscripción
              </Button>
            </div>
          ) : errorDetail.action_required === 'upgrade_plan' && (
            <Button onClick={handleUpgrade} className="gap-2">
              <IconCrown className="h-4 w-4" />
              Ver planes
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}