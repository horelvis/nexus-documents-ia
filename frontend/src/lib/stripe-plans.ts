// Configuración de planes de Nexus
export const STRIPE_PLANS = {
  free: {
    id: 'free',
    name: 'Starter',
    description: 'Prueba gratis por 14 días',
    price: 0,
    currency: 'USD',
    interval: 'trial',
    trialDays: 14,
    features: [
      '14 días de prueba gratis',
      'Todas las funciones Pro incluidas',
      'Documentos ilimitados durante el trial',
      '100 GB de almacenamiento',
      'IA y análisis avanzados',
      'Firma digital integrada',
      'Sin tarjeta de crédito requerida',
    ],
    limitations: [
      'Después del trial: $29/mes plan Basic',
      'O actualiza a Pro para más funciones',
    ],
    cta: 'Comenzar Prueba Gratis',
    popular: false,
    // Free trial handled by Stripe with trial period
    backend: true
  },
  basic: {
    id: 'basic',
    name: 'Basic',
    description: 'Para uso personal',
    price: 29,
    currency: 'USD',
    interval: 'month',
    features: [
      'Hasta 500 documentos',
      '10 GB de almacenamiento',
      'Búsqueda con IA básica',
      'Análisis de documentos',
      '1 usuario',
      'Soporte por email',
    ],
    cta: 'Comenzar con Basic',
    popular: false,
    // Stripe data is handled by backend
    backend: true
  },
  pro: {
    id: 'pro',
    name: 'Pro',
    description: 'Ideal para equipos en crecimiento',
    price: 60,
    currency: 'USD',
    interval: 'month',
    yearlyPrice: 600, // $50/month billed yearly
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
    cta: 'Elegir Pro',
    popular: true,
    // Stripe data is handled by backend
    backend: true
  },
  enterprise: {
    id: 'enterprise',
    name: 'Enterprise',
    description: 'Para organizaciones grandes',
    price: null, // Custom pricing
    currency: 'USD',
    interval: 'custom',
    customPricing: true,
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
    // No Stripe integration - handled by sales team
    backend: false
  }
} as const

export type PlanId = keyof typeof STRIPE_PLANS
export type Plan = typeof STRIPE_PLANS[PlanId]

export const getPlan = (planId: PlanId): Plan => {
  return STRIPE_PLANS[planId]
}

export const getAllPlans = (): Plan[] => {
  // Return plans in specific order: Basic, Pro, Enterprise (excluding free/starter)
  const planOrder = ['basic', 'pro', 'enterprise']
  return planOrder.map(id => STRIPE_PLANS[id as PlanId]).filter(Boolean)
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
    // Durante el trial: características Pro
    // Después del trial: características básicas
    maxDocuments: 100, // unlimited during trial
    maxStorageGB: 1, // 100GB during trial
    maxUsers: 1, // 10 during trial
    hasAI: false, // true during trial
    hasSignatures: false, // true during trial
    hasAPI: false, // true during trial
    hasAdvancedIntegrations: false, // true during trial
    hasPrioritySupport: false, // true during trial
    isTrialPlan: true,
    trialDays: 14,
  },
  basic: {
    maxDocuments: 500,
    maxStorageGB: 10,
    maxUsers: 1,
    hasAI: true, // Basic AI features
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