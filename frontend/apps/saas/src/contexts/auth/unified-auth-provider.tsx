'use client'

/**
 * Unified Authentication Provider
 *
 * Automatically selects the appropriate auth provider based on deployment mode:
 * - SaaS mode: Uses Clerk authentication
 * - On-premise mode: Uses SSO (OIDC/SAML/LDAP)
 *
 * Provides a unified interface regardless of the underlying auth system.
 */

import { createContext, useContext, useMemo, type ReactNode } from 'react'
import { useFeature, Feature, DeploymentMode, useDeploymentMode } from '@/lib/features'
import { SSOAuthProvider, useSSOAuth } from './sso-auth-context'
import { UserProvider, useUserContext } from '@/contexts/user-context'
import type { UnifiedAuthContextType, AuthState } from './types'
import type { OnboardingStatus } from '@/lib/types'

const UnifiedAuthContext = createContext<UnifiedAuthContextType | undefined>(undefined)

interface UnifiedAuthProviderProps {
  children: ReactNode
}

/**
 * Adapter that converts Clerk's UserContext to UnifiedAuthContextType
 */
function ClerkAuthAdapter({ children }: { children: ReactNode }) {
  const {
    clerkUser,
    isClerkLoaded,
    isSignedIn,
    backendUser,
    userLoading,
    userError,
    subscription,
    permissions,
    onboarding,
    markOnboardingComplete,
    resetOnboarding,
    refetchUser,
    handleLogout,
    hasValidTrial,
    hasPaidSubscription,
    needsPayment,
  } = useUserContext()

  const authState = useMemo<AuthState>(
    () => ({
      isLoaded: isClerkLoaded,
      isAuthenticated: isSignedIn || false,
      identity: clerkUser
        ? {
            external_id: clerkUser.id,
            email: clerkUser.primaryEmailAddress?.emailAddress || '',
            name: clerkUser.fullName || undefined,
            given_name: clerkUser.firstName || undefined,
            family_name: clerkUser.lastName || undefined,
            picture_url: clerkUser.imageUrl || undefined,
            groups: [],
            roles: [],
            provider: 'clerk' as const,
          }
        : null,
      tokens: null, // Clerk manages tokens internally
      provider: 'clerk' as const,
    }),
    [isClerkLoaded, isSignedIn, clerkUser]
  )

  const contextValue = useMemo<UnifiedAuthContextType>(
    () => ({
      authState,
      isLoaded: isClerkLoaded,
      isAuthenticated: isSignedIn || false,
      backendUser,
      subscription,
      permissions,
      userLoading,
      userError,
      onboarding,
      login: async () => {
        // Clerk handles login via SignIn component
        window.location.href = '/auth/sign-in'
      },
      logout: handleLogout,
      refreshTokens: async () => true, // Clerk handles this automatically
      getAccessToken: async () => null, // Clerk manages tokens internally
      markOnboardingComplete,
      resetOnboarding,
      refetchUser,
      hasValidTrial,
      hasPaidSubscription,
      needsPayment,
    }),
    [
      authState,
      isClerkLoaded,
      isSignedIn,
      backendUser,
      subscription,
      permissions,
      userLoading,
      userError,
      onboarding,
      handleLogout,
      markOnboardingComplete,
      resetOnboarding,
      refetchUser,
      hasValidTrial,
      hasPaidSubscription,
      needsPayment,
    ]
  )

  return (
    <UnifiedAuthContext.Provider value={contextValue}>
      {children}
    </UnifiedAuthContext.Provider>
  )
}

/**
 * Adapter that provides SSO context as UnifiedAuthContextType
 */
function SSOAuthAdapter({ children }: { children: ReactNode }) {
  const ssoAuth = useSSOAuth()

  return (
    <UnifiedAuthContext.Provider value={ssoAuth}>
      {children}
    </UnifiedAuthContext.Provider>
  )
}

/**
 * Provider selector based on deployment mode.
 * This component must be rendered after features are loaded.
 */
function AuthProviderSelector({ children }: { children: ReactNode }) {
  const deploymentMode = useDeploymentMode()
  const useClerk = useFeature(Feature.CLERK_AUTH)

  // In SaaS mode with Clerk enabled, use Clerk
  if (deploymentMode === DeploymentMode.SAAS && useClerk) {
    return (
      <UserProvider>
        <ClerkAuthAdapter>{children}</ClerkAuthAdapter>
      </UserProvider>
    )
  }

  // In on-premise mode or when Clerk is disabled, use SSO
  return (
    <SSOAuthProvider>
      <SSOAuthAdapter>{children}</SSOAuthAdapter>
    </SSOAuthProvider>
  )
}

/**
 * Unified Auth Provider
 *
 * Wraps the app and provides consistent auth interface regardless
 * of whether Clerk or SSO is being used.
 *
 * Usage:
 *   <UnifiedAuthProvider>
 *     <App />
 *   </UnifiedAuthProvider>
 */
export function UnifiedAuthProvider({ children }: UnifiedAuthProviderProps) {
  return <AuthProviderSelector>{children}</AuthProviderSelector>
}

/**
 * Hook to access unified auth context.
 *
 * Works the same whether using Clerk or SSO.
 */
export function useUnifiedAuth(): UnifiedAuthContextType {
  const context = useContext(UnifiedAuthContext)
  if (context === undefined) {
    throw new Error('useUnifiedAuth must be used within a UnifiedAuthProvider')
  }
  return context
}

/**
 * Convenience hooks
 */
export function useAuth() {
  return useUnifiedAuth()
}

export function useAuthState() {
  const { authState } = useUnifiedAuth()
  return authState
}

export function useIsAuthenticated() {
  const { isAuthenticated } = useUnifiedAuth()
  return isAuthenticated
}
