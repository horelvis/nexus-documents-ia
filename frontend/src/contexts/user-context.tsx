'use client'

import { createContext, useContext, useState, useEffect, useMemo, useCallback } from 'react'
import { useUser, useClerk, useAuth } from '@clerk/nextjs'
import { useRouter, usePathname } from 'next/navigation'
import { useApiClient, apiClient as globalApiClient } from '@/lib/api-client'
import { ConnectionError } from '@/components/errors/connection-error'
import { Button } from '@/components/ui/button'
// Authentication flow:
// - Users must register through SignUp flow (creates user via Clerk webhook)
// - Login validates existing users and returns subscription info (POST /auth/login)
// - No JIT provisioning - unregistered users get 401

import type {
  BackendUser,
  OnboardingStatus,
  UserContextType,
  UserProviderProps,
  SubscriptionInfo,
  UserPermissions,
  LoginResponse
} from '@/lib/types'

const UserContext = createContext<UserContextType | undefined>(undefined)

export function UserProvider({ children }: UserProviderProps) {
  const { user: clerkUser, isLoaded: isClerkLoaded, isSignedIn } = useUser()
  const { getToken } = useAuth()
  const { signOut } = useClerk()
  const router = useRouter()
  const pathname = usePathname()
  const apiClient = useApiClient() // This is the local instance
  const [isTokenReady, setIsTokenReady] = useState(false)
  
  // Configure global API client with token getter
  useEffect(() => {
    if (isClerkLoaded) {
      globalApiClient.setAuthTokenGetter(async () => {
        try {
          const token = await getToken()
          return token
        } catch (error) {
          console.error('Failed to get token for global api client:', error)
          return null
        }
      })
      // Mark token as ready after configuring the getter
      setIsTokenReady(true)
    }
  }, [isClerkLoaded, getToken])
  
  // Internal state for sync errors
  const [syncError, setSyncError] = useState<string | null>(null)

  // Track if login has been attempted
  const [hasAttemptedLogin, setHasAttemptedLogin] = useState(false)
  const [isLoggingIn, setIsLoggingIn] = useState(false)

  // Backend user and auth state (from POST /auth/login)
  const [backendUser, setBackendUser] = useState<BackendUser | null>(null)
  const [subscription, setSubscription] = useState<SubscriptionInfo | null>(null)
  const [permissions, setPermissions] = useState<UserPermissions | null>(null)
  const [loginError, setLoginError] = useState<Error | null>(null)

  // Perform login when Clerk is ready
  const performLogin = useCallback(async () => {
    if (!isTokenReady || isLoggingIn || hasAttemptedLogin) return

    setIsLoggingIn(true)
    setLoginError(null)

    try {
      const response = await apiClient.post<LoginResponse>('/auth/login')

      if (response.error) {
        const error = new Error(response.error) as Error & { status?: number }
        error.status = response.status
        throw error
      }

      if (response.data) {
        setBackendUser(response.data.user)
        setSubscription(response.data.subscription)
        setPermissions(response.data.permissions)
      }
    } catch (err: any) {
      console.error('[UserContext] Login failed:', err)
      setLoginError(err)
    } finally {
      setIsLoggingIn(false)
      setHasAttemptedLogin(true)
    }
  }, [apiClient, isTokenReady, isLoggingIn, hasAttemptedLogin])

  // Trigger login when signed in and token ready
  useEffect(() => {
    if (isClerkLoaded && isSignedIn && isTokenReady && !hasAttemptedLogin) {
      performLogin()
    }
  }, [isClerkLoaded, isSignedIn, isTokenReady, hasAttemptedLogin, performLogin])

  // Reset state when user signs out
  useEffect(() => {
    if (isClerkLoaded && !isSignedIn) {
      setBackendUser(null)
      setSubscription(null)
      setPermissions(null)
      setHasAttemptedLogin(false)
      setLoginError(null)
    }
  }, [isClerkLoaded, isSignedIn])

  // Reload user function (for refresh)
  const reloadUser = useCallback(async () => {
    setHasAttemptedLogin(false)
    setLoginError(null)
    await performLogin()
  }, [performLogin])

  // Derived state - loading while Clerk loads, during login, or waiting for backendUser
  const userLoading = !isClerkLoaded || !isTokenReady || (isSignedIn && !backendUser && !loginError && hasAttemptedLogin === false) || isLoggingIn

  // Consolidated error state
  const userError = useMemo(() => {
    if (syncError) return syncError
    if (loginError) {
      const status = (loginError as any).status
      // Don't show error for 401 (user not registered) as we'll redirect
      if (status === 401) return null
      return loginError.message || 'Unknown error'
    }
    return null
  }, [loginError, syncError])

  // Onboarding status derivation
  const onboarding = useMemo<OnboardingStatus>(() => {
    if (userLoading) {
      return {
        needsOnboarding: false,
        isNewUser: false,
        hasCompletedSync: false,
        loading: true,
        error: null
      }
    }
    
    if (userError) {
       return {
        needsOnboarding: false,
        isNewUser: false,
        hasCompletedSync: false,
        loading: false,
        error: userError
      }
    }

    if (backendUser) {
      return {
        needsOnboarding: !backendUser.onboarding_completed,
        isNewUser: false,
        hasCompletedSync: true, // If we have backendUser, sync is done
        loading: false,
        error: null
      }
    }

    // If no backend user and no error (yet), we might be syncing
    return {
      needsOnboarding: false,
      isNewUser: true,
      hasCompletedSync: false,
      loading: false,
      error: null
    }
  }, [userLoading, userError, backendUser])

  // Helper function to get onboarding path
  const getOnboardingPath = useCallback((_userData?: BackendUser) => {
    return '/onboarding'
  }, [])

  // Helper function to check if current path is onboarding
  const isOnboardingPath = useCallback(() => {
    return pathname.includes('/onboarding') || pathname.includes('/onboarding-simple')
  }, [pathname])

  // ... (rest of syncUserWithBackend and other functions)

  // Auto-sync and Redirect Logic
  useEffect(() => {
    // Skip if auth flow, pricing, or error pages
    if (pathname.startsWith('/auth/') || pathname === '/pricing' ||
        pathname === '/tenant-not-found' || pathname === '/user-not-found') return

    // Check for 401 error from login - user exists in Clerk but not registered in backend
    if (isClerkLoaded && isSignedIn && clerkUser && loginError) {
      const status = (loginError as any).status
      if (status === 401) {
        console.log('[UserContext] User not registered in backend (401), redirecting to user-not-found')
        router.push('/user-not-found')
        return
      }
    }

    // If user in Clerk but not in backend (no backendUser after login attempt), redirect to user-not-found
    // Users must register through the proper signup flow first
    if (isClerkLoaded && isSignedIn && clerkUser && !backendUser && !userLoading && !loginError && hasAttemptedLogin) {
       console.log('[UserContext] User in Clerk but not in backend (after login attempt), redirecting to user-not-found')
       router.push('/user-not-found')
       return
    }
  }, [backendUser, router, isClerkLoaded, isSignedIn, userLoading, clerkUser, loginError, pathname, hasAttemptedLogin])


  // Actions
  const markOnboardingComplete = useCallback(async (onboardingData?: any): Promise<boolean> => {
    try {
      const response = await apiClient.post<BackendUser>('/auth/complete-onboarding', onboardingData)
      if (response.error) throw new Error(response.error)

      // Update local state
      if (response.data) {
        setBackendUser(response.data)
      }
      return true
    } catch (error) {
      console.error('Error completing onboarding:', error)
      return false
    }
  }, [apiClient])

  const resetOnboarding = useCallback(async (): Promise<boolean> => {
    try {
      const response = await apiClient.post<BackendUser>('/auth/reset-onboarding')
      if (response.error) throw new Error(response.error)

      // Update local state
      if (response.data) {
        setBackendUser(response.data)
      }
      return true
    } catch (error) {
      console.error('Error resetting onboarding:', error)
      return false
    }
  }, [apiClient])

  // Subscription helpers
  const hasValidTrial = useCallback((): boolean => {
    if (!backendUser?.trial_ends_at) return false
    return new Date(backendUser.trial_ends_at) > new Date()
  }, [backendUser?.trial_ends_at])
  
  const hasPaidSubscription = useCallback((): boolean => {
    if (!backendUser?.subscription_plan) return false
    return ['basic', 'pro', 'professional', 'enterprise'].includes(backendUser.subscription_plan)
  }, [backendUser?.subscription_plan])
  
  const needsPayment = useCallback((): boolean => {
    return !hasValidTrial() && !hasPaidSubscription()
  }, [hasValidTrial, hasPaidSubscription])

  // Handle logout - call backend then Clerk signOut
  const handleLogout = useCallback(async () => {
    try {
      // Call backend logout endpoint for logging
      await apiClient.post('/auth/logout')
    } catch (err) {
      console.error('[UserContext] Backend logout failed:', err)
      // Continue with Clerk signout anyway
    }

    // Clear local state
    setBackendUser(null)
    setSubscription(null)
    setPermissions(null)
    setHasAttemptedLogin(false)
    setLoginError(null)
    setSyncError(null)

    // Clerk signout
    await signOut()

    // Redirect to sign-in
    router.push('/auth/sign-in')
  }, [apiClient, signOut, router])


  const contextValue: UserContextType = useMemo(() => ({
    clerkUser,
    isClerkLoaded,
    isSignedIn: isSignedIn || false,
    backendUser: backendUser || null,
    userLoading,
    userError,
    subscription,
    permissions,
    onboarding,
    markOnboardingComplete,
    resetOnboarding,
    checkOnboardingStatus: async () => { await reloadUser() }, // Adapter for existing calls
    refetchUser: async () => { await reloadUser() },
    handleLogout,
    hasValidTrial,
    hasPaidSubscription,
    needsPayment
  }), [
    clerkUser, isClerkLoaded, isSignedIn, backendUser, userLoading, userError,
    subscription, permissions, onboarding,
    markOnboardingComplete, resetOnboarding, reloadUser, handleLogout,
    hasValidTrial, hasPaidSubscription, needsPayment
  ])

  // Handle connection errors specifically for the UI
  const connectionError = useMemo(() => {
    if (loginError && (loginError.message === 'Failed to fetch' || loginError.name === 'ConnectionError')) {
       return loginError
    }
    return null
  }, [loginError])


  if (connectionError) {
    return <ConnectionError error={connectionError} onRetry={() => reloadUser()} />
  }

  // Show loading screen while authenticating
  if (userLoading && isSignedIn) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-4">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
          <p className="text-muted-foreground text-sm">Authenticating...</p>
        </div>
      </div>
    )
  }

  if (userError && isSignedIn) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4 bg-background">
        <div className="max-w-md w-full text-center space-y-4">
          <h2 className="text-xl font-semibold">Account Error</h2>
          <p className="text-muted-foreground">{userError}</p>
          <div className="flex gap-2 justify-center">
            <Button onClick={() => { setSyncError(null); reloadUser() }}>Try Again</Button>
            <Button variant="outline" onClick={() => signOut()}>Sign Out</Button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <UserContext.Provider value={contextValue}>
      {children}
    </UserContext.Provider>
  )
}

// Hook to use the UserContext
export function useUserContext() {
  const context = useContext(UserContext)
  if (context === undefined) {
    throw new Error('useUserContext must be used within a UserProvider')
  }
  return context
}

// Export individual hooks for convenience
export function useBackendUser() {
  const { backendUser, userLoading, userError } = useUserContext()
  return { backendUser, userLoading, userError }
}

// Re-export useUser from Clerk for convenience
export { useUser } from '@clerk/nextjs'

export function useOnboardingStatus() {
  const { onboarding } = useUserContext()
  return onboarding
}
