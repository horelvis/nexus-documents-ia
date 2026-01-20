/**
 * Authentication Types
 *
 * Shared types for the unified authentication system
 * that supports both Clerk (SaaS) and SSO (on-premise) modes.
 */

import type { BackendUser, SubscriptionInfo, UserPermissions, OnboardingStatus } from '@/lib/types'

/**
 * Authentication provider types.
 */
export type AuthProviderType = 'clerk' | 'oidc' | 'saml' | 'ldap' | 'none'

/**
 * Tokens from SSO authentication.
 */
export interface SSOTokens {
  access_token: string
  refresh_token?: string
  id_token?: string
  expires_at?: number
  token_type?: string
}

/**
 * User identity from any auth provider.
 */
export interface AuthIdentity {
  external_id: string
  email: string
  name?: string
  given_name?: string
  family_name?: string
  picture_url?: string
  groups?: string[]
  roles?: string[]
  provider: AuthProviderType
}

/**
 * Unified auth state.
 */
export interface AuthState {
  isLoaded: boolean
  isAuthenticated: boolean
  identity: AuthIdentity | null
  tokens: SSOTokens | null
  provider: AuthProviderType
}

/**
 * Unified auth context value.
 * Same interface whether using Clerk or SSO.
 */
export interface UnifiedAuthContextType {
  // Auth state
  authState: AuthState
  isLoaded: boolean
  isAuthenticated: boolean

  // User data (from backend after login)
  backendUser: BackendUser | null
  subscription: SubscriptionInfo | null
  permissions: UserPermissions | null

  // Loading states
  userLoading: boolean
  userError: string | null

  // Onboarding
  onboarding: OnboardingStatus

  // Actions
  login: () => Promise<void>
  logout: () => Promise<void>
  refreshTokens: () => Promise<boolean>
  getAccessToken: () => Promise<string | null>

  // Onboarding actions
  markOnboardingComplete: (data?: unknown) => Promise<boolean>
  resetOnboarding: () => Promise<boolean>
  refetchUser: () => Promise<void>

  // Subscription helpers
  hasValidTrial: () => boolean
  hasPaidSubscription: () => boolean
  needsPayment: () => boolean
}

/**
 * Props for auth guard components.
 */
export interface AuthGuardProps {
  children: React.ReactNode
  fallback?: React.ReactNode
  requireAuth?: boolean
}
