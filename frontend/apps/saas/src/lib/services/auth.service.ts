import { useMemo } from 'react'
import { useApiClient } from '../api-client'
import type { BackendUser } from '../types'

/**
 * Subscription information from Stripe
 */
export interface SubscriptionInfo {
  plan: string                        // trial, basic, pro, enterprise
  status: string                      // active, trialing, past_due, canceled
  can_use_agents: boolean
  can_use_advanced_features: boolean
  limits: Record<string, number>      // { documents: 500, storage_mb: 10240 }
  needs_upgrade: boolean              // True if trial expired without paid plan
  trial_days_remaining: number | null
  current_period_end: string | null
  subscription_id: string | null
  cancel_at_period_end: boolean
}

/**
 * User permissions based on subscription and roles
 */
export interface UserPermissions {
  is_admin: boolean
  is_team_member: boolean
  can_upload_documents: boolean
  can_use_agents: boolean
  can_invite_members: boolean
  can_access_api: boolean
  can_export: boolean
}

/**
 * Response from POST /auth/login
 */
export interface LoginResponse {
  user: BackendUser
  subscription: SubscriptionInfo
  permissions: UserPermissions
  tenant_id: string
}

/**
 * Response from POST /auth/logout
 */
export interface LogoutResponse {
  success: boolean
  message: string
}

/**
 * Auth service for Clerk + Stripe authentication flow
 */
export class AuthService {
  constructor(private apiClient: ReturnType<typeof useApiClient>) {}

  /**
   * Login - validates existing user and returns subscription info.
   * Returns 401 if user doesn't exist (must register first via SignUp).
   */
  async login() {
    return this.apiClient.post<LoginResponse>('/auth/login')
  }

  /**
   * Logout - logs the event (Clerk handles session invalidation).
   */
  async logout() {
    return this.apiClient.post<LogoutResponse>('/auth/logout')
  }

  /**
   * Get current user data (use for refresh, not initial login).
   */
  async getMe() {
    return this.apiClient.get<BackendUser>('/auth/me')
  }

  /**
   * Complete onboarding for the current user.
   */
  async completeOnboarding() {
    return this.apiClient.post<BackendUser>('/auth/complete-onboarding')
  }
}

/**
 * Hook to use the auth service
 */
export function useAuthService() {
  const apiClient = useApiClient()
  return useMemo(() => new AuthService(apiClient), [apiClient])
}
