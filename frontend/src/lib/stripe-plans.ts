// Configuración de planes de Nexus
export const STRIPE_PLANS = {
  free: {
    id: 'free',
    name: 'Free',
    description: 'Perfecto para comenzar',
    price: 0,
    currency: 'USD',
    interval: 'forever',
    features: [
      'Hasta 100 documentos',
      '1 GB de almacenamiento',
      'Búsqueda básica',
      'Soporte estándar',
      '1 usuario',
    ],
    limitations: [
      'Sin funciones de IA',
      'Sin firma digital',
      'Sin API access',
    ],
    cta: 'Empezar Gratis',
    popular: false,
    // Free plan handled locally, no Stripe integration
    backend: false
  },
  pro: {
    id: 'pro',
    name: 'Pro',
    description: 'Ideal para equipos en crecimiento',
    price: 29,
    currency: 'USD',
    interval: 'month',
    yearlyPrice: 290, // $24.17/month billed yearly
    features: [
      'Documentos ilimitados',
      '100 GB de almacenamiento',
      'Búsqueda con IA avanzada',
      'Análisis inteligente de documentos',
      'Firma digital integrada',
      'Hasta 10 usuarios',
      'Soporte prioritario',
      'Acceso a API',
      'Integraciones avanzadas',
    ],
    cta: 'Probar Pro',
    popular: true,
    // Stripe data is handled by backend
    backend: true
  },
  enterprise: {
    id: 'enterprise',
    name: 'Enterprise',
    description: 'Para organizaciones grandes',
    price: 99,
    currency: 'USD',
    interval: 'month',
    yearlyPrice: 990, // $82.50/month billed yearly
    features: [
      'Todo en Pro, además:',
      '1 TB de almacenamiento',
      'Agentes de IA avanzados',
      'Integraciones personalizadas',
      'Opciones de marca blanca',
      'Usuarios ilimitados',
      'Soporte dedicado 24/7',
      'SLA garantizado',
      'Flujos de trabajo personalizados',
      'Análisis avanzados',
      'Auditoría completa',
    ],
    cta: 'Contactar Ventas',
    popular: false,
    // Stripe data is handled by backend
    backend: true
  }
} as const

export type PlanId = keyof typeof STRIPE_PLANS
export type Plan = typeof STRIPE_PLANS[PlanId]

export const getPlan = (planId: PlanId): Plan => {
  return STRIPE_PLANS[planId]
}

export const getAllPlans = (): Plan[] => {
  return Object.values(STRIPE_PLANS)
}

export const getPaidPlans = (): Plan[] => {
  return Object.values(STRIPE_PLANS).filter(plan => plan.id !== 'free')
}

export const formatPrice = (price: number, currency: string = 'USD'): string => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
  }).format(price)
}

export const calculateYearlyDiscount = (monthlyPrice: number, yearlyPrice: number): number => {
  const yearlyEquivalent = monthlyPrice * 12
  const discount = ((yearlyEquivalent - yearlyPrice) / yearlyEquivalent) * 100
  return Math.round(discount)
}

// Helper functions for paid plans
export const isPaidPlan = (planId: PlanId): boolean => {
  return planId !== 'free'
}

// Feature flags por plan
export const PLAN_FEATURES = {
  free: {
    maxDocuments: 100,
    maxStorageGB: 1,
    maxUsers: 1,
    hasAI: false,
    hasSignatures: false,
    hasAPI: false,
    hasAdvancedIntegrations: false,
    hasPrioritySupport: false,
  },
  pro: {
    maxDocuments: -1, // unlimited
    maxStorageGB: 100,
    maxUsers: 10,
    hasAI: true,
    hasSignatures: true,
    hasAPI: true,
    hasAdvancedIntegrations: true,
    hasPrioritySupport: true,
  },
  enterprise: {
    maxDocuments: -1, // unlimited
    maxStorageGB: 1000,
    maxUsers: -1, // unlimited
    hasAI: true,
    hasSignatures: true,
    hasAPI: true,
    hasAdvancedIntegrations: true,
    hasPrioritySupport: true,
    hasCustomIntegrations: true,
    hasWhiteLabel: true,
    hasSLA: true,
    hasDedicatedSupport: true,
  }
} as const

export type PlanFeatures = typeof PLAN_FEATURES[PlanId]

export const getPlanFeatures = (planId: PlanId): PlanFeatures => {
  return PLAN_FEATURES[planId]
}

export const canUserAccess = (userPlan: PlanId, requiredFeature: keyof PlanFeatures): boolean => {
  const features = getPlanFeatures(userPlan)
  return !!features[requiredFeature]
}