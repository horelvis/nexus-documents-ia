
// frontend/app/modules/stripe/plans.ts
/**
 * Configuración de planes de suscripción
 * Esta configuración debe coincidir con la del backend
 */

export const PLANS = {
  FREE: 'free',
  PRO: 'pro',
  ENTERPRISE: 'enterprise',
} as const

export type Plan = (typeof PLANS)[keyof typeof PLANS]

export const INTERVALS = {
  MONTH: 'month',
  YEAR: 'year',
} as const

export type Interval = (typeof INTERVALS)[keyof typeof INTERVALS]

export const CURRENCIES = {
  DEFAULT: 'usd',
  USD: 'usd',
  EUR: 'eur',
} as const

export type Currency = (typeof CURRENCIES)[keyof typeof CURRENCIES]

/**
 * Configuración de precios para mostrar en el frontend
 * Los precios reales se manejan en el backend
 */
export const PRICING_PLANS = {
  [PLANS.FREE]: {
    id: PLANS.FREE,
    name: 'Free',
    description: 'Perfect for getting started',
    features: [
      'Up to 10 documents',
      'Basic AI chat',
      'Community support',
      '1 GB storage'
    ],
    prices: {
      [INTERVALS.MONTH]: {
        [CURRENCIES.USD]: 0,
        [CURRENCIES.EUR]: 0,
      },
      [INTERVALS.YEAR]: {
        [CURRENCIES.USD]: 0,
        [CURRENCIES.EUR]: 0,
      },
    },
    popular: false,
  },
  [PLANS.PRO]: {
    id: PLANS.PRO,
    name: 'Pro',
    description: 'Best for professionals and small teams',
    features: [
      'Unlimited documents',
      'Advanced AI chat',
      'Priority support',
      '10 GB storage',
      'Advanced search',
      'Custom integrations'
    ],
    prices: {
      [INTERVALS.MONTH]: {
        [CURRENCIES.USD]: 1999, // $19.99
        [CURRENCIES.EUR]: 1999,
      },
      [INTERVALS.YEAR]: {
        [CURRENCIES.USD]: 19999, // $199.99 (save ~17%)
        [CURRENCIES.EUR]: 19999,
      },
    },
    popular: true,
  },
  [PLANS.ENTERPRISE]: {
    id: PLANS.ENTERPRISE,
    name: 'Enterprise',
    description: 'For large organizations with advanced needs',
    features: [
      'Everything in Pro',
      'Unlimited storage',
      'Custom AI models',
      '24/7 phone support',
      'SSO integration',
      'Advanced analytics',
      'Custom branding'
    ],
    prices: {
      [INTERVALS.MONTH]: {
        [CURRENCIES.USD]: 9999, // $99.99
        [CURRENCIES.EUR]: 9999,
      },
      [INTERVALS.YEAR]: {
        [CURRENCIES.USD]: 99999, // $999.99
        [CURRENCIES.EUR]: 99999,
      },
    },
    popular: false,
  },
} satisfies PricingPlan

/**
 * Utilidades para trabajar con planes
 */
export function getPlanDisplayName(planId: string): string {
  const plan = PRICING_PLANS[planId as Plan]
  return plan?.name || 'Unknown Plan'
}

export function getPlanPrice(planId: string, interval: string, currency: string = CURRENCIES.USD): number {
  const plan = PRICING_PLANS[planId as Plan]
  return plan?.prices[interval as Interval]?.[currency as Currency] || 0
}

export function formatPrice(amount: number, currency: string = CURRENCIES.USD): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currency.toUpperCase(),
  }).format(amount / 100)
}

export function calculateYearlySavings(planId: string, currency: string = CURRENCIES.USD): number {
  const monthlyPrice = getPlanPrice(planId, INTERVALS.MONTH, currency)
  const yearlyPrice = getPlanPrice(planId, INTERVALS.YEAR, currency)
  
  const yearlyMonthly = (monthlyPrice * 12)
  return yearlyMonthly - yearlyPrice
}

export function getSavingsPercentage(planId: string, currency: string = CURRENCIES.USD): number {
  const monthlyPrice = getPlanPrice(planId, INTERVALS.MONTH, currency)
  const savings = calculateYearlySavings(planId, currency)
  
  if (monthlyPrice === 0) return 0
  return Math.round((savings / (monthlyPrice * 12)) * 100)
}

// Types
type PriceInterval<I extends Interval = Interval, C extends Currency = Currency> = {
  [interval in I]: {
    [currency in C]: number
  }
}

type PricingPlan<T extends Plan = Plan> = {
  [key in T]: {
    id: string
    name: string
    description: string
    features: string[]
    prices: PriceInterval
    popular: boolean
  }
}