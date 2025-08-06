import { apiClient } from './api-client'

export async function syncUserWithBackend(clerkUserId: string, email: string, fullName: string, plan?: string) {
  try {
    const response = await apiClient.post('/auth/sync-user', {
      clerk_user_id: clerkUserId,
      email: email,
      full_name: fullName || email.split('@')[0], // Fallback to email prefix if no name
      stripe_customer_id: null, // No Stripe customer for free plan
      selected_plan: plan || 'free'
    })

    if (response.error) {
      console.error('Error syncing user:', response.error)
      throw new Error(response.error)
    }

    return response.data
  } catch (error) {
    console.error('Failed to sync user with backend:', error)
    throw error
  }
}