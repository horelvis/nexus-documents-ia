'use client'

/**
 * SSO Authentication Context
 *
 * Provides authentication for on-premise deployments using
 * enterprise SSO providers (OIDC, SAML, LDAP).
 *
 * Token flow:
 * 1. Check for existing valid tokens in sessionStorage
 * 2. If not authenticated, redirect to SSO login URL
 * 3. After SSO callback, store tokens and fetch user
 * 4. Auto-refresh tokens before expiry
 */

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useMemo,
  type ReactNode,
} from 'react'
import { useRouter, usePathname, useSearchParams } from 'next/navigation'
import { apiClient } from '@/lib/api-client'
import type {
  AuthState,
  SSOTokens,
  AuthIdentity,
  UnifiedAuthContextType,
} from './types'
import type {
  BackendUser,
  SubscriptionInfo,
  UserPermissions,
  OnboardingStatus,
  LoginResponse,
} from '@/lib/types'

const STORAGE_KEY = 'nexus_sso_tokens'
const TOKEN_REFRESH_MARGIN_MS = 5 * 60 * 1000 // Refresh 5 min before expiry

interface SSOAuthProviderProps {
  children: ReactNode
}

const SSOAuthContext = createContext<UnifiedAuthContextType | undefined>(undefined)

/**
 * Store tokens securely in sessionStorage.
 * Using sessionStorage to clear on tab close for security.
 */
function storeTokens(tokens: SSOTokens): void {
  if (typeof window !== 'undefined') {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(tokens))
  }
}

/**
 * Retrieve stored tokens.
 */
function getStoredTokens(): SSOTokens | null {
  if (typeof window === 'undefined') return null
  const stored = sessionStorage.getItem(STORAGE_KEY)
  if (!stored) return null
  try {
    return JSON.parse(stored) as SSOTokens
  } catch {
    return null
  }
}

/**
 * Clear stored tokens.
 */
function clearStoredTokens(): void {
  if (typeof window !== 'undefined') {
    sessionStorage.removeItem(STORAGE_KEY)
  }
}

/**
 * Check if tokens are expired or about to expire.
 */
function isTokenExpired(tokens: SSOTokens): boolean {
  if (!tokens.expires_at) return false
  const now = Date.now()
  return now >= tokens.expires_at - TOKEN_REFRESH_MARGIN_MS
}

/**
 * Parse JWT payload without verification (for identity extraction).
 */
function parseJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return null
    const payload = JSON.parse(atob(parts[1]))
    return payload
  } catch {
    return null
  }
}

/**
 * Extract identity from SSO tokens.
 */
function extractIdentityFromTokens(tokens: SSOTokens): AuthIdentity | null {
  // Prefer id_token for identity, fallback to access_token
  const tokenToParse = tokens.id_token || tokens.access_token
  const payload = parseJwtPayload(tokenToParse)

  if (!payload) return null

  return {
    external_id: (payload.sub as string) || '',
    email:
      (payload.email as string) ||
      (payload.preferred_username as string) ||
      (payload.upn as string) ||
      '',
    name: payload.name as string | undefined,
    given_name: payload.given_name as string | undefined,
    family_name: payload.family_name as string | undefined,
    picture_url: payload.picture as string | undefined,
    groups: (payload.groups as string[]) || [],
    roles: (payload.roles as string[]) || [],
    provider: 'oidc',
  }
}

export function SSOAuthProvider({ children }: SSOAuthProviderProps) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  // Auth state
  const [authState, setAuthState] = useState<AuthState>({
    isLoaded: false,
    isAuthenticated: false,
    identity: null,
    tokens: null,
    provider: 'oidc',
  })

  // Backend user state
  const [backendUser, setBackendUser] = useState<BackendUser | null>(null)
  const [subscription, setSubscription] = useState<SubscriptionInfo | null>(null)
  const [permissions, setPermissions] = useState<UserPermissions | null>(null)
  const [userLoading, setUserLoading] = useState(true)
  const [userError, setUserError] = useState<string | null>(null)

  // Configure API client with token getter
  useEffect(() => {
    apiClient.setAuthTokenGetter(async () => {
      const tokens = getStoredTokens()
      return tokens?.access_token || null
    })
  }, [])

  // Handle OAuth callback (code exchange)
  const handleOAuthCallback = useCallback(async (code: string, state?: string) => {
    try {
      const response = await fetch('/api/v1/auth/sso/callback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code,
          state,
          redirect_uri: `${window.location.origin}/auth/callback`,
        }),
      })

      if (!response.ok) {
        throw new Error('Failed to exchange authorization code')
      }

      const data = await response.json()
      const tokens: SSOTokens = {
        access_token: data.access_token,
        refresh_token: data.refresh_token,
        id_token: data.id_token,
        expires_at: Date.now() + (data.expires_in || 3600) * 1000,
        token_type: data.token_type || 'Bearer',
      }

      storeTokens(tokens)
      const identity = extractIdentityFromTokens(tokens)

      setAuthState({
        isLoaded: true,
        isAuthenticated: true,
        identity,
        tokens,
        provider: 'oidc',
      })

      // Clear URL params
      router.replace(pathname)
    } catch (err) {
      console.error('[SSOAuth] Callback error:', err)
      setUserError(err instanceof Error ? err.message : 'Authentication failed')
      setAuthState((prev) => ({ ...prev, isLoaded: true }))
    }
  }, [pathname, router])

  // Check for OAuth callback params on mount
  useEffect(() => {
    const code = searchParams.get('code')
    const state = searchParams.get('state')
    const error = searchParams.get('error')

    if (error) {
      setUserError(`SSO Error: ${error}`)
      setAuthState((prev) => ({ ...prev, isLoaded: true }))
      return
    }

    if (code) {
      handleOAuthCallback(code, state || undefined)
      return
    }

    // Check stored tokens
    const tokens = getStoredTokens()
    if (tokens && !isTokenExpired(tokens)) {
      const identity = extractIdentityFromTokens(tokens)
      setAuthState({
        isLoaded: true,
        isAuthenticated: true,
        identity,
        tokens,
        provider: 'oidc',
      })
    } else {
      clearStoredTokens()
      setAuthState({
        isLoaded: true,
        isAuthenticated: false,
        identity: null,
        tokens: null,
        provider: 'oidc',
      })
    }
  }, [searchParams, handleOAuthCallback])

  // Perform backend login after auth
  const performLogin = useCallback(async () => {
    if (!authState.isAuthenticated || !authState.tokens) return

    setUserLoading(true)
    setUserError(null)

    try {
      const response = await apiClient.post<LoginResponse>('/auth/login')

      if (response.error) {
        throw new Error(response.error)
      }

      if (response.data) {
        setBackendUser(response.data.user)
        setSubscription(response.data.subscription)
        setPermissions(response.data.permissions)
      }
    } catch (err) {
      console.error('[SSOAuth] Login failed:', err)
      setUserError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setUserLoading(false)
    }
  }, [authState.isAuthenticated, authState.tokens])

  // Trigger backend login when authenticated
  useEffect(() => {
    if (authState.isLoaded && authState.isAuthenticated && !backendUser) {
      performLogin()
    }
  }, [authState.isLoaded, authState.isAuthenticated, backendUser, performLogin])

  // Token refresh
  const refreshTokens = useCallback(async (): Promise<boolean> => {
    const tokens = getStoredTokens()
    if (!tokens?.refresh_token) return false

    try {
      const response = await fetch('/api/v1/auth/sso/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: tokens.refresh_token }),
      })

      if (!response.ok) return false

      const data = await response.json()
      const newTokens: SSOTokens = {
        access_token: data.access_token,
        refresh_token: data.refresh_token || tokens.refresh_token,
        id_token: data.id_token,
        expires_at: Date.now() + (data.expires_in || 3600) * 1000,
        token_type: data.token_type || 'Bearer',
      }

      storeTokens(newTokens)
      setAuthState((prev) => ({
        ...prev,
        tokens: newTokens,
        identity: extractIdentityFromTokens(newTokens),
      }))

      return true
    } catch (err) {
      console.error('[SSOAuth] Token refresh failed:', err)
      return false
    }
  }, [])

  // Auto-refresh tokens
  useEffect(() => {
    if (!authState.isAuthenticated || !authState.tokens) return

    const checkAndRefresh = async () => {
      if (authState.tokens && isTokenExpired(authState.tokens)) {
        const success = await refreshTokens()
        if (!success) {
          // Token refresh failed, logout
          clearStoredTokens()
          setAuthState({
            isLoaded: true,
            isAuthenticated: false,
            identity: null,
            tokens: null,
            provider: 'oidc',
          })
        }
      }
    }

    const interval = setInterval(checkAndRefresh, 60 * 1000) // Check every minute
    return () => clearInterval(interval)
  }, [authState.isAuthenticated, authState.tokens, refreshTokens])

  // Actions
  const login = useCallback(async () => {
    try {
      const response = await fetch('/api/v1/auth/sso/login-url')
      if (!response.ok) throw new Error('Failed to get login URL')
      const { login_url } = await response.json()
      window.location.href = login_url
    } catch (err) {
      console.error('[SSOAuth] Login redirect failed:', err)
      setUserError('Failed to initiate login')
    }
  }, [])

  const logout = useCallback(async () => {
    try {
      // Call backend logout
      await apiClient.post('/auth/logout')
    } catch (err) {
      console.error('[SSOAuth] Backend logout failed:', err)
    }

    // Clear local state
    clearStoredTokens()
    setBackendUser(null)
    setSubscription(null)
    setPermissions(null)
    setUserError(null)
    setAuthState({
      isLoaded: true,
      isAuthenticated: false,
      identity: null,
      tokens: null,
      provider: 'oidc',
    })

    // Get SSO logout URL if available
    try {
      const response = await fetch('/api/v1/auth/sso/logout-url')
      if (response.ok) {
        const { logout_url } = await response.json()
        if (logout_url) {
          window.location.href = logout_url
          return
        }
      }
    } catch {
      // Ignore, redirect to local sign-in
    }

    router.push('/auth/sign-in')
  }, [router])

  const getAccessToken = useCallback(async (): Promise<string | null> => {
    const tokens = getStoredTokens()
    if (!tokens) return null

    if (isTokenExpired(tokens)) {
      const success = await refreshTokens()
      if (!success) return null
      return getStoredTokens()?.access_token || null
    }

    return tokens.access_token
  }, [refreshTokens])

  // Onboarding
  const onboarding = useMemo<OnboardingStatus>(() => {
    if (userLoading) {
      return {
        needsOnboarding: false,
        isNewUser: false,
        hasCompletedSync: false,
        loading: true,
        error: null,
      }
    }

    if (userError) {
      return {
        needsOnboarding: false,
        isNewUser: false,
        hasCompletedSync: false,
        loading: false,
        error: userError,
      }
    }

    if (backendUser) {
      return {
        needsOnboarding: !backendUser.onboarding_completed,
        isNewUser: false,
        hasCompletedSync: true,
        loading: false,
        error: null,
      }
    }

    return {
      needsOnboarding: false,
      isNewUser: true,
      hasCompletedSync: false,
      loading: false,
      error: null,
    }
  }, [userLoading, userError, backendUser])

  const markOnboardingComplete = useCallback(async (data?: unknown): Promise<boolean> => {
    try {
      const response = await apiClient.post<BackendUser>('/auth/complete-onboarding', data)
      if (response.error) throw new Error(response.error)
      if (response.data) setBackendUser(response.data)
      return true
    } catch (err) {
      console.error('[SSOAuth] Onboarding complete failed:', err)
      return false
    }
  }, [])

  const resetOnboarding = useCallback(async (): Promise<boolean> => {
    try {
      const response = await apiClient.post<BackendUser>('/auth/reset-onboarding')
      if (response.error) throw new Error(response.error)
      if (response.data) setBackendUser(response.data)
      return true
    } catch (err) {
      console.error('[SSOAuth] Onboarding reset failed:', err)
      return false
    }
  }, [])

  const refetchUser = useCallback(async () => {
    await performLogin()
  }, [performLogin])

  // Subscription helpers
  const hasValidTrial = useCallback((): boolean => {
    if (!backendUser?.trial_ends_at) return false
    return new Date(backendUser.trial_ends_at) > new Date()
  }, [backendUser?.trial_ends_at])

  const hasPaidSubscription = useCallback((): boolean => {
    if (!backendUser?.subscription_plan) return false
    return ['basic', 'pro', 'professional', 'enterprise'].includes(
      backendUser.subscription_plan
    )
  }, [backendUser?.subscription_plan])

  const needsPayment = useCallback((): boolean => {
    return !hasValidTrial() && !hasPaidSubscription()
  }, [hasValidTrial, hasPaidSubscription])

  const contextValue = useMemo<UnifiedAuthContextType>(
    () => ({
      authState,
      isLoaded: authState.isLoaded,
      isAuthenticated: authState.isAuthenticated,
      backendUser,
      subscription,
      permissions,
      userLoading,
      userError,
      onboarding,
      login,
      logout,
      refreshTokens,
      getAccessToken,
      markOnboardingComplete,
      resetOnboarding,
      refetchUser,
      hasValidTrial,
      hasPaidSubscription,
      needsPayment,
    }),
    [
      authState,
      backendUser,
      subscription,
      permissions,
      userLoading,
      userError,
      onboarding,
      login,
      logout,
      refreshTokens,
      getAccessToken,
      markOnboardingComplete,
      resetOnboarding,
      refetchUser,
      hasValidTrial,
      hasPaidSubscription,
      needsPayment,
    ]
  )

  return (
    <SSOAuthContext.Provider value={contextValue}>
      {children}
    </SSOAuthContext.Provider>
  )
}

export function useSSOAuth() {
  const context = useContext(SSOAuthContext)
  if (context === undefined) {
    throw new Error('useSSOAuth must be used within an SSOAuthProvider')
  }
  return context
}
