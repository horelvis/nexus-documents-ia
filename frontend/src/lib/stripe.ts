import { api } from './api';

export interface StripeCheckoutSession {
  url: string;
}

export interface StripeSubscription {
  id: string;
  plan_id: string;
  status: string;
  interval: string;
  current_period_start: number;
  current_period_end: number;
  cancel_at_period_end: boolean;
  customer_id: string;
}

export interface StripeCustomerPortal {
  portal_url: string;
}

export class StripeService {
  /**
   * Create a Stripe checkout session for subscription
   */
  static async createCheckoutSession(priceId: string, successUrl?: string, cancelUrl?: string): Promise<StripeCheckoutSession> {
    try {
      const response = await api.post('/stripe/create-checkout-session', {
        price_id: priceId,
        success_url: successUrl || `${window.location.origin}/dashboard?checkout=success`,
        cancel_url: cancelUrl || `${window.location.origin}/pricing?checkout=cancelled`
      });
      return response.data;
    } catch (error) {
      console.error('Error creating checkout session:', error);
      throw new Error('Failed to create checkout session');
    }
  }

  /**
   * Get current user's subscription details
   */
  static async getCurrentSubscription(): Promise<StripeSubscription> {
    try {
      const response = await api.get('/stripe/subscription');
      return response.data;
    } catch (error) {
      console.error('Error getting subscription:', error);
      throw new Error('Failed to get subscription details');
    }
  }

  /**
   * Create customer portal session for subscription management
   */
  static async createCustomerPortal(returnUrl?: string): Promise<StripeCustomerPortal> {
    try {
      const response = await api.post('/stripe/create-customer-portal', {
        return_url: returnUrl || `${window.location.origin}/dashboard`
      });
      return response.data;
    } catch (error) {
      console.error('Error creating customer portal:', error);
      throw new Error('Failed to create customer portal session');
    }
  }

  /**
   * Sync subscription data from Stripe
   */
  static async syncSubscription(): Promise<void> {
    try {
      await api.post('/stripe/sync-subscription');
    } catch (error) {
      console.error('Error syncing subscription:', error);
      throw new Error('Failed to sync subscription');
    }
  }

  /**
   * Cancel subscription at period end
   */
  static async cancelSubscription(): Promise<void> {
    try {
      await api.post('/stripe/cancel-subscription');
    } catch (error) {
      console.error('Error cancelling subscription:', error);
      throw new Error('Failed to cancel subscription');
    }
  }

  /**
   * Redirect to Stripe checkout
   */
  static redirectToCheckout(checkoutUrl: string): void {
    window.location.href = checkoutUrl;
  }

  /**
   * Redirect to customer portal
   */
  static redirectToCustomerPortal(portalUrl: string): void {
    window.location.href = portalUrl;
  }
}