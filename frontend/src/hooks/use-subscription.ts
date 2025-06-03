"use client";

import { useState, useEffect } from 'react';
import { StripeService, StripeSubscription } from '@/lib/stripe';
import { toast } from 'sonner';

export function useSubscription() {
  const [subscription, setSubscription] = useState<StripeSubscription | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSubscription = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await StripeService.getCurrentSubscription();
      setSubscription(data);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to fetch subscription';
      setError(errorMessage);
      console.error('Error fetching subscription:', err);
    } finally {
      setLoading(false);
    }
  };

  const createCheckoutSession = async (priceId: string) => {
    try {
      setLoading(true);
      const session = await StripeService.createCheckoutSession(priceId);
      StripeService.redirectToCheckout(session.url);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to create checkout session';
      setError(errorMessage);
      toast.error(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const openCustomerPortal = async () => {
    try {
      setLoading(true);
      const portal = await StripeService.createCustomerPortal();
      StripeService.redirectToCustomerPortal(portal.portal_url);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to open customer portal';
      setError(errorMessage);
      toast.error(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const syncSubscription = async () => {
    try {
      await StripeService.syncSubscription();
      await fetchSubscription(); // Refresh subscription data
      toast.success('Subscription synced successfully');
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to sync subscription';
      setError(errorMessage);
      toast.error(errorMessage);
    }
  };

  const cancelSubscription = async () => {
    try {
      await StripeService.cancelSubscription();
      await fetchSubscription(); // Refresh subscription data
      toast.success('Subscription cancelled successfully');
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to cancel subscription';
      setError(errorMessage);
      toast.error(errorMessage);
    }
  };

  useEffect(() => {
    fetchSubscription();
  }, []);

  return {
    subscription,
    loading,
    error,
    createCheckoutSession,
    openCustomerPortal,
    syncSubscription,
    cancelSubscription,
    refetch: fetchSubscription,
  };
}