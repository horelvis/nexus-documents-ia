'use client'

/**
 * OIDC Authentication Context for Emma On-Premise
 *
 * Manages authentication state using KeyCloak as identity provider.
 * Implements Authorization Code flow with PKCE.
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
import {
  buildAuthorizationUrl,
  exchangeCodeForTokens,
  buildLogoutUrl,
  refreshAccessToken,
} from '@/lib/oidc-config'

const SSO_TOKEN_KEY = 'nexus_sso_tokens'
const OIDC_STATE_KEY = 'nexus_oidc_state'
const OIDC_VERIFIER_KEY = 'nexus_oidc_verifier'

interface SSOTokens {
  access_token: string
  refresh_token?: string
  id_token?: string
  expires_at?: number
}

interface User {
  id: string
  email: string
  full_name?: string
  tenant_id: string
  is_active: boolean
  onboarding_completed: boolean
}

interface AuthContextType {
  isLoaded: boolean
  isAuthenticated: boolean
  user: User | null
  tenantId: string | null
  login: () => Promise<void>
  logout: () => Promise<void>
  refreshUser: () => Promise<void>
  completeOnboarding: () => Promise<boolean>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

function getStoredTokens(): SSOTokens | null {
  if (typeof window === 'undefined') return null
  const stored = sessionStorage.getItem(SSO_TOKEN_KEY)
  if (!stored) return null
  try {
    return JSON.parse(stored)
  } catch {
    return null
  }
}

function storeTokens(tokens: SSOTokens): void {
  if (typeof window !== 'undefined') {
    sessionStorage.setItem(SSO_TOKEN_KEY, JSON.stringify(tokens))
  }
}

function clearTokens(): void {
  if (typeof window !== 'undefined') {
    sessionStorage.removeItem(SSO_TOKEN_KEY)
    sessionStorage.removeItem(OIDC_STATE_KEY)
    sessionStorage.removeItem(OIDC_VERIFIER_KEY)
  }
}

function isTokenExpired(tokens: SSOTokens): boolean {
  if (!tokens.expires_at) return false
  return Date.now() >= tokens.expires_at - 60000 // 1 minute buffer
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  const [isLoaded, setIsLoaded] = useState(false)
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [user, setUser] = useState<User | null>(null)

  // Fetch user from backend using SSO token
  const fetchUser = useCallback(async (accessToken: string) => {
    try {
      // Call backend to validate token and get/create user (JIT provisioning)
      // Backend will validate the token with OIDC provider
      const response = await apiClient.post<User>(
        '/auth/sso/login',
        {}, // Empty body - backend uses Authorization header
        {
          headers: {
            Authorization: `Bearer ${accessToken}`,
          },
        }
      )

      if (response.data) {
        setUser(response.data)
        return response.data
      }

      return null
    } catch (error) {
      console.error('[Auth] Failed to fetch user:', error)
      return null
    }
  }, [])

  // Handle OIDC callback
  const handleCallback = useCallback(async (code: string, returnedState: string) => {
    try {
      // Verify state
      const storedState = sessionStorage.getItem(OIDC_STATE_KEY)
      if (storedState !== returnedState) {
        throw new Error('State mismatch - possible CSRF attack')
      }

      // Get code verifier
      const codeVerifier = sessionStorage.getItem(OIDC_VERIFIER_KEY)
      if (!codeVerifier) {
        throw new Error('Code verifier not found')
      }

      // Exchange code for tokens
      console.log('[Auth] Exchanging code for tokens...')
      const tokenResponse = await exchangeCodeForTokens(code, codeVerifier)

      const tokens: SSOTokens = {
        access_token: tokenResponse.access_token,
        refresh_token: tokenResponse.refresh_token,
        id_token: tokenResponse.id_token,
        expires_at: Date.now() + (tokenResponse.expires_in || 3600) * 1000,
      }

      storeTokens(tokens)
      setIsAuthenticated(true)

      // Clear OIDC state
      sessionStorage.removeItem(OIDC_STATE_KEY)
      sessionStorage.removeItem(OIDC_VERIFIER_KEY)

      // Fetch user info
      console.log('[Auth] Fetching user info...')
      const fetchedUser = await fetchUser(tokens.access_token)

      // Redirect based on onboarding status
      if (fetchedUser && !fetchedUser.onboarding_completed) {
        router.replace('/onboarding')
      } else {
        router.replace('/')
      }
    } catch (error) {
      console.error('[Auth] Callback error:', error)
      clearTokens()
      setIsAuthenticated(false)
      router.push('/auth/sign-in?error=callback_failed')
    }
  }, [router, fetchUser])

  // Try to refresh tokens
  const tryRefreshTokens = useCallback(async (tokens: SSOTokens): Promise<boolean> => {
    if (!tokens.refresh_token) return false

    try {
      const refreshed = await refreshAccessToken(tokens.refresh_token)
      const newTokens: SSOTokens = {
        access_token: refreshed.access_token,
        refresh_token: refreshed.refresh_token || tokens.refresh_token,
        id_token: tokens.id_token,
        expires_at: Date.now() + (refreshed.expires_in || 3600) * 1000,
      }
      storeTokens(newTokens)
      return true
    } catch {
      return false
    }
  }, [])

  // Check auth state on mount
  useEffect(() => {
    async function checkAuth() {
      // Check for OIDC callback
      const code = searchParams.get('code')
      const state = searchParams.get('state')
      const error = searchParams.get('error')

      if (error) {
        console.error('[Auth] OIDC error:', error, searchParams.get('error_description'))
        setIsLoaded(true)
        return
      }

      if (code && state && pathname === '/auth/callback') {
        await handleCallback(code, state)
        setIsLoaded(true)
        return
      }

      // Check stored tokens
      const tokens = getStoredTokens()
      if (tokens) {
        let currentTokens = tokens

        // Check if token is expired locally
        if (isTokenExpired(tokens)) {
          // Try to refresh
          const refreshed = await tryRefreshTokens(tokens)
          if (!refreshed) {
            clearTokens()
            setIsAuthenticated(false)
            setIsLoaded(true)
            return
          }
          // Get the refreshed tokens
          currentTokens = getStoredTokens() || tokens
        }

        // Try to fetch user - if it fails (401), the token might be invalid server-side
        const user = await fetchUser(currentTokens.access_token)
        if (!user) {
          // Token might be invalid server-side, try to refresh
          console.log('[Auth] User fetch failed, attempting token refresh...')
          const refreshed = await tryRefreshTokens(currentTokens)
          if (refreshed) {
            const newTokens = getStoredTokens()
            if (newTokens) {
              const retryUser = await fetchUser(newTokens.access_token)
              if (retryUser) {
                setIsAuthenticated(true)
                setIsLoaded(true)
                return
              }
            }
          }
          // Refresh failed or user still null - clear and redirect
          console.log('[Auth] Token refresh failed, clearing session')
          clearTokens()
          setIsAuthenticated(false)
          setIsLoaded(true)
          return
        }

        setIsAuthenticated(true)
      } else {
        setIsAuthenticated(false)
      }

      setIsLoaded(true)
    }

    checkAuth()
  }, [searchParams, pathname, handleCallback, fetchUser, tryRefreshTokens])

  // Login - redirect to KeyCloak
  const login = useCallback(async () => {
    try {
      const { url, state, codeVerifier } = await buildAuthorizationUrl()

      // Store state and verifier for callback verification
      sessionStorage.setItem(OIDC_STATE_KEY, state)
      sessionStorage.setItem(OIDC_VERIFIER_KEY, codeVerifier)

      // Redirect to KeyCloak
      window.location.href = url
    } catch (error) {
      console.error('[Auth] Login error:', error)
    }
  }, [])

  // Logout
  const logout = useCallback(async () => {
    const tokens = getStoredTokens()

    // Notify backend
    try {
      await apiClient.post('/auth/logout')
    } catch {
      // Ignore errors
    }

    clearTokens()
    setIsAuthenticated(false)
    setUser(null)

    // Redirect to KeyCloak logout
    const logoutUrl = buildLogoutUrl(tokens?.id_token)
    window.location.href = logoutUrl
  }, [])

  // Refresh user data
  const refreshUser = useCallback(async () => {
    const tokens = getStoredTokens()
    if (tokens) {
      await fetchUser(tokens.access_token)
    }
  }, [fetchUser])

  // Mark onboarding as completed in backend
  const completeOnboarding = useCallback(async (): Promise<boolean> => {
    const tokens = getStoredTokens()
    if (!tokens) return false

    try {
      const response = await apiClient.post<User>(
        '/auth/complete-onboarding',
        {},
        {
          headers: {
            Authorization: `Bearer ${tokens.access_token}`,
          },
        }
      )

      if (response.data) {
        setUser(response.data)
        return true
      }

      return false
    } catch (error) {
      console.error('[Auth] Failed to complete onboarding:', error)
      return false
    }
  }, [])

  const contextValue = useMemo<AuthContextType>(
    () => ({
      isLoaded,
      isAuthenticated,
      user,
      tenantId: user?.tenant_id || null,
      login,
      logout,
      refreshUser,
      completeOnboarding,
    }),
    [isLoaded, isAuthenticated, user, login, logout, refreshUser, completeOnboarding]
  )

  return (
    <AuthContext.Provider value={contextValue}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
