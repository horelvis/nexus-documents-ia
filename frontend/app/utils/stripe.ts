// frontend/app/utils/stripe.ts
import { PLANS, INTERVALS, type Plan, type Interval } from '#app/modules/stripe/plans'

/**
 * Utilidades para trabajar con Stripe en el frontend
 */

export interface SubscriptionStatus {
  isActive: boolean
  isPaid: boolean
  isCanceled: boolean
  isPastDue: boolean
  planName: string
  interval?: string
  nextBillingDate?: Date
  cancelAtPeriodEnd?: boolean
}

/**
 * Analiza el estado de una suscripción y devuelve información útil
 */
export function analyzeSubscriptionStatus(subscription: any): SubscriptionStatus {
  if (!subscription) {
    return {
      isActive: false,
      isPaid: false,
      isCanceled: true,
      isPastDue: false,
      planName: 'No subscription',
    }
  }

  const isActive = subscription.status === 'active'
  const isPaid = subscription.plan_id !== PLANS.FREE
  const isCanceled = subscription.status === 'canceled'
  const isPastDue = subscription.status === 'past_due'
  const planName = getPlanDisplayName(subscription.plan_id)
  
  return {
    isActive,
    isPaid,
    isCanceled,
    isPastDue,
    planName,
    interval: subscription.interval,
    nextBillingDate: subscription.current_period_end 
      ? new Date(subscription.current_period_end * 1000)
      : undefined,
    cancelAtPeriodEnd: subscription.cancel_at_period_end,
  }
}

/**
 * Obtiene el nombre de display para un plan
 */
export function getPlanDisplayName(planId: string): string {
  switch (planId) {
    case PLANS.FREE:
      return 'Free'
    case PLANS.PRO:
      return 'Pro'
    case PLANS.ENTERPRISE:
      return 'Enterprise'
    default:
      return 'Unknown Plan'
  }
}

/**
 * Obtiene el color para mostrar según el estado de la suscripción
 */
export function getSubscriptionStatusColor(status: string): {
  bg: string
  text: string
  border: string
} {
  switch (status) {
    case 'active':
      return {
        bg: 'bg-green-50 dark:bg-green-900/20',
        text: 'text-green-700 dark:text-green-300',
        border: 'border-green-200 dark:border-green-800',
      }
    case 'past_due':
    case 'unpaid':
      return {
        bg: 'bg-red-50 dark:bg-red-900/20',
        text: 'text-red-700 dark:text-red-300',
        border: 'border-red-200 dark:border-red-800',
      }
    case 'canceled':
      return {
        bg: 'bg-gray-50 dark:bg-gray-900/20',
        text: 'text-gray-700 dark:text-gray-300',
        border: 'border-gray-200 dark:border-gray-800',
      }
    default:
      return {
        bg: 'bg-yellow-50 dark:bg-yellow-900/20',
        text: 'text-yellow-700 dark:text-yellow-300',
        border: 'border-yellow-200 dark:border-yellow-800',
      }
  }
}

/**
 * Verifica si un usuario puede acceder a una funcionalidad específica
 */
export function canAccessFeature(
  subscription: any,
  feature: 'unlimited_documents' | 'advanced_ai' | 'priority_support' | 'custom_integrations' | 'sso'
): boolean {
  if (!subscription || subscription.status !== 'active') {
    return false
  }

  const planId = subscription.plan_id

  // Features por plan
  const featureMatrix = {
    [PLANS.FREE]: [],
    [PLANS.PRO]: [
      'unlimited_documents',
      'advanced_ai',
      'priority_support',
      'custom_integrations'
    ],
    [PLANS.ENTERPRISE]: [
      'unlimited_documents',
      'advanced_ai',
      'priority_support',
      'custom_integrations',
      'sso'
    ],
  }

  return featureMatrix[planId as Plan]?.includes(feature) || false
}

/**
 * Obtiene los límites para un plan específico
 */
export function getPlanLimits(planId: string): {
  documents: number | 'unlimited'
  storage: string
  aiRequests: number | 'unlimited'
  integrations: number | 'unlimited'
} {
  switch (planId) {
    case PLANS.FREE:
      return {
        documents: 10,
        storage: '1 GB',
        aiRequests: 50,
        integrations: 0,
      }
    case PLANS.PRO:
      return {
        documents: 'unlimited',
        storage: '10 GB',
        aiRequests: 'unlimited',
        integrations: 5,
      }
    case PLANS.ENTERPRISE:
      return {
        documents: 'unlimited',
        storage: 'unlimited',
        aiRequests: 'unlimited',
        integrations: 'unlimited',
      }
    default:
      return {
        documents: 0,
        storage: '0 GB',
        aiRequests: 0,
        integrations: 0,
      }
  }
}

/**
 * Formatea una fecha de facturación
 */
export function formatBillingDate(timestamp: number, locale = 'es-ES'): string {
  return new Date(timestamp * 1000).toLocaleDateString(locale, {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
}

/**
 * Calcula días restantes hasta la próxima facturación
 */
export function getDaysUntilNextBilling(currentPeriodEnd: number): number {
  const now = new Date().getTime()
  const endDate = currentPeriodEnd * 1000
  const diffTime = endDate - now
  return Math.ceil(diffTime / (1000 * 60 * 60 * 24))
}

/**
 * Verifica si una suscripción está por vencer (próximos 7 días)
 */
export function isSubscriptionExpiringSoon(subscription: any): boolean {
  if (!subscription || subscription.plan_id === PLANS.FREE) {
    return false
  }

  const daysRemaining = getDaysUntilNextBilling(subscription.current_period_end)
  return daysRemaining <= 7 && daysRemaining > 0
}

/**
 * Genera un mensaje de estado para la suscripción
 */
export function getSubscriptionStatusMessage(subscription: any): {
  message: string
  type: 'success' | 'warning' | 'error' | 'info'
} {
  if (!subscription) {
    return {
      message: 'No hay suscripción activa',
      type: 'info',
    }
  }

  const status = subscription.status
  const planName = getPlanDisplayName(subscription.plan_id)

  switch (status) {
    case 'active':
      if (subscription.cancel_at_period_end) {
        const endDate = formatBillingDate(subscription.current_period_end)
        return {
          message: `Tu suscripción ${planName} se cancelará el ${endDate}`,
          type: 'warning',
        }
      }
      
      if (isSubscriptionExpiringSoon(subscription)) {
        const days = getDaysUntilNextBilling(subscription.current_period_end)
        return {
          message: `Tu suscripción ${planName} se renueva en ${days} días`,
          type: 'info',
        }
      }

      return {
        message: `Suscripción ${planName} activa`,
        type: 'success',
      }

    case 'past_due':
      return {
        message: `Tu suscripción ${planName} tiene pagos pendientes`,
        type: 'error',
      }

    case 'canceled':
      return {
        message: `Tu suscripción ${planName} ha sido cancelada`,
        type: 'error',
      }

    case 'unpaid':
      return {
        message: `Tu suscripción ${planName} no se pudo procesar`,
        type: 'error',
      }

    default:
      return {
        message: `Estado de suscripción: ${status}`,
        type: 'info',
      }
  }
}

/**
 * Helpers para URLs de Stripe
 */
export const stripeUrls = {
  portal: '/dashboard/settings/billing',
  upgrade: '/onboarding/plan',
  success: '/dashboard/checkout',
  cancel: '/dashboard/settings/billing',
} as const

/**
 * Manejo de errores específicos de Stripe
 */
export function handleStripeError(error: any): {
  userMessage: string
  shouldRetry: boolean
  technical: string
} {
  const message = error?.message || 'Error desconocido'

  // Errores comunes de Stripe
  if (message.includes('card_declined')) {
    return {
      userMessage: 'Tu tarjeta fue rechazada. Por favor, verifica los datos o usa otra tarjeta.',
      shouldRetry: true,
      technical: message,
    }
  }

  if (message.includes('insufficient_funds')) {
    return {
      userMessage: 'Fondos insuficientes en tu tarjeta.',
      shouldRetry: true,
      technical: message,
    }
  }

  if (message.includes('expired_card')) {
    return {
      userMessage: 'Tu tarjeta ha expirado. Por favor, actualiza la información de pago.',
      shouldRetry: true,
      technical: message,
    }
  }

  if (message.includes('processing_error')) {
    return {
      userMessage: 'Error procesando el pago. Por favor, intenta de nuevo.',
      shouldRetry: true,
      technical: message,
    }
  }

  if (message.includes('rate_limit')) {
    return {
      userMessage: 'Demasiadas solicitudes. Por favor, espera un momento antes de intentar de nuevo.',
      shouldRetry: true,
      technical: message,
    }
  }

  // Error genérico
  return {
    userMessage: 'Ocurrió un error con el procesamiento del pago. Por favor, contacta soporte si el problema persiste.',
    shouldRetry: false,
    technical: message,
  }
}

/**
 * Valida datos de facturación
 */
export function validateBillingData(data: {
  planId?: string
  interval?: string
}): { isValid: boolean; errors: string[] } {
  const errors: string[] = []

  if (!data.planId) {
    errors.push('Plan ID es requerido')
  } else if (!Object.values(PLANS).includes(data.planId as Plan)) {
    errors.push('Plan ID inválido')
  }

  if (!data.interval) {
    errors.push('Intervalo de facturación es requerido')
  } else if (!Object.values(INTERVALS).includes(data.interval as Interval)) {
    errors.push('Intervalo de facturación inválido')
  }

  return {
    isValid: errors.length === 0,
    errors,
  }
}