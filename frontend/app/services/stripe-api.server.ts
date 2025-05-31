// frontend/app/services/stripe-api.server.ts
import type { LoaderFunctionArgs } from '@remix-run/node'
import { ApiService } from '#app/services/api.server'

export interface StripeApiService {
  createCheckoutSession(planId: string, interval: string): Promise<{ checkout_url: string }>
  createCustomerPortal(): Promise<{ portal_url: string }>
  getCurrentSubscription(): Promise<SubscriptionData | null>
  cancelSubscription(): Promise<{ success: boolean }>
  updateSubscription(planId: string, interval: string): Promise<{ success: boolean }>
  getInvoiceHistory(): Promise<InvoiceData[]>
}

export interface SubscriptionData {
  id: string
  plan_id: string
  interval: 'month' | 'year'
  status: 'active' | 'canceled' | 'past_due' | 'unpaid'
  current_period_start: number
  current_period_end: number
  cancel_at_period_end: boolean
  customer_id: string
}

export interface InvoiceData {
  id: string
  amount_paid: number
  currency: string
  status: string
  created: number
  invoice_pdf?: string
}

export class StripeApiServiceImpl extends ApiService implements StripeApiService {
  async createCheckoutSession(planId: string, interval: string): Promise<{ checkout_url: string }> {
    return this.makeRequest('/stripe/create-checkout-session', {
      method: 'POST',
      body: JSON.stringify({
        plan_id: planId,
        interval: interval,
      }),
    })
  }

  async createCustomerPortal(): Promise<{ portal_url: string }> {
    return this.makeRequest('/stripe/create-customer-portal', {
      method: 'POST',
    })
  }

  async getCurrentSubscription(): Promise<SubscriptionData | null> {
    try {
      return await this.makeRequest('/stripe/subscription')
    } catch (error) {
      // Si no hay suscripción, el backend puede devolver 404
      if (error instanceof Error && error.message.includes('404')) {
        return null
      }
      throw error
    }
  }

  async cancelSubscription(): Promise<{ success: boolean }> {
    return this.makeRequest('/stripe/subscription/cancel', {
      method: 'POST',
    })
  }

  async updateSubscription(planId: string, interval: string): Promise<{ success: boolean }> {
    return this.makeRequest('/stripe/subscription', {
      method: 'PUT',
      body: JSON.stringify({
        plan_id: planId,
        interval: interval,
      }),
    })
  }

  async getInvoiceHistory(): Promise<InvoiceData[]> {
    return this.makeRequest('/stripe/invoices')
  }

  // Métodos específicos para el manejo de webhooks (si necesitas verificar estados)
  async syncSubscriptionStatus(): Promise<SubscriptionData | null> {
    return this.makeRequest('/stripe/subscription/sync', {
      method: 'POST',
    })
  }
}

/**
 * Factory function para crear el servicio de Stripe API
 */
export async function createStripeApiService(userId: string, token: string): Promise<StripeApiServiceImpl> {

  const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL || 'http://localhost:8000'
  
  return new StripeApiServiceImpl({
    baseUrl: BACKEND_BASE_URL,
    getToken: async () => {
      try {
        return token
      } catch (error) {
        console.error('Error obteniendo token de Clerk:', error)
        return null
      }
    },
  })
}