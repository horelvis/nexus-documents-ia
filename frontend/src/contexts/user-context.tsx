'use client'

import { createContext, useContext, useState, useEffect, useMemo, useCallback } from 'react'
import { useUser, useClerk, useAuth } from '@clerk/nextjs'
import { useRouter, usePathname } from 'next/navigation'
import useSWR, { useSWRConfig } from 'swr'
import { useApiClient, apiClient as globalApiClient } from '@/lib/api-client'
import { fetcher } from '@/lib/fetcher'
import { ConnectionError } from '@/components/errors/connection-error'
import { Button } from '@/components/ui/button'
import { syncUserWithBackend } from '@/lib/sync-user'

import type { BackendUser, OnboardingStatus, UserContextType, UserProviderProps } from '@/lib/types'

const UserContext = createContext<UserContextType | undefined>(undefined)

export function UserProvider({ children }: UserProviderProps) {
  const { user: clerkUser, isLoaded: isClerkLoaded, isSignedIn } = useUser()
  const { getToken } = useAuth()
  const { signOut } = useClerk()
  const router = useRouter()
  const pathname = usePathname()
  const apiClient = useApiClient() // This is the local instance
  const { mutate } = useSWRConfig()
  const [isTokenReady, setIsTokenReady] = useState(false)
  
  // Configure global API client with token getter for SWR fetcher
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
  
  // Internal state for sync errors that SWR doesn't catch (like failed sync after 404)
  const [syncError, setSyncError] = useState<string | null>(null)
  
  // SWR for fetching backend user
  const { data: backendUser, error: swrError, isLoading: swrLoading, mutate: reloadUser } = useSWR<BackendUser>(
    isClerkLoaded && isSignedIn && isTokenReady ? '/auth/me' : null,
    fetcher,
    {
      shouldRetryOnError: false,
      revalidateOnFocus: true,
      onError: (err) => {
        // We'll handle 403/404 specifically in a useEffect
        console.log('SWR Error:', err)
      }
    }
  )

  // Derived state
  const userLoading = !isClerkLoaded || (isSignedIn && swrLoading && !backendUser && !swrError)
  
  // Consolidated error state
  const userError = useMemo(() => {
    if (syncError) return syncError
    if (swrError) {
      const status = (swrError as any).status
      // Don't show error for 403/404 as we'll try to sync
      if (status === 403 || status === 404) return null
      return swrError.message || 'Unknown error'
    }
    return null
  }, [swrError, syncError])

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

  // Helper function to get tenant-aware onboarding path
  const getOnboardingPath = useCallback((userData?: BackendUser) => {
    if (userData?.tenant_id) {
      return `/${userData.tenant_id}/onboarding`
    }
    // Fallback to extract tenantId from pathname if available
    const tenantMatch = pathname.match(/^\/([^\/]+)\//)
    if (tenantMatch) {
      return `/${tenantMatch[1]}/onboarding`
    }
    return '/onboarding' // Fallback
  }, [pathname])

  // Helper function to check if current path is onboarding
  const isOnboardingPath = useCallback(() => {
    return pathname.includes('/onboarding') || pathname.includes('/onboarding-simple')
  }, [pathname])

  // ... (rest of syncUserWithBackend and other functions)

  // Auto-sync and Redirect Logic
  useEffect(() => {
    // Skip if auth flow or pricing
    if (pathname.startsWith('/auth/') || pathname === '/pricing') return

    // Auto-sync for new users (Direct Flow)
    // If we have a clerk user but no backend user (and no loading/error), it means the user needs to be synced/created
    if (isClerkLoaded && isSignedIn && clerkUser && !backendUser && !userLoading && !userError) {
       const unsafeMetadata = clerkUser.unsafeMetadata as any
       const selectedPlan = unsafeMetadata?.selected_plan || 'free'
       
       console.log('[UserContext] Auto-syncing new user...')
       syncUserWithBackend(
          clerkUser.id, 
          clerkUser.primaryEmailAddress?.emailAddress || '', 
          clerkUser.fullName || '',
          selectedPlan
       ).then(async (syncedUser) => {
          if (syncedUser && !syncedUser.onboarding_completed) {
             console.log('[UserContext] Auto-completing onboarding...')
             await apiClient.post('/auth/complete-onboarding', {
                selected_plan: selectedPlan
             })
          }
          reloadUser()
       }).catch(err => {
          console.error('[UserContext] Auto-sync failed', err)
       })
    }
    
    // Redirect to onboarding is DISABLED for direct flow
    /*
    if (backendUser && !backendUser.onboarding_completed && !isOnboardingPath()) {
       // Check for invalid/default tenant ID
       const isInvalidTenantId = !backendUser.tenant_id || 
       backendUser.tenant_id === 'default' || 
       backendUser.tenant_id === '00000000-0000-0000-0000-000000000000' ||
       backendUser.tenant_id === 'undefined' ||
       backendUser.tenant_id === 'null'
     
      if (isInvalidTenantId) {
         setSyncError('INVALID_TENANT')
      } else {
         console.log('[UserContext] Redirecting to onboarding')
         router.push(getOnboardingPath(backendUser))
      }
    }
    */
  }, [backendUser, isOnboardingPath, getOnboardingPath, router, isClerkLoaded, isSignedIn, userLoading, userError, clerkUser, apiClient, reloadUser])


  // Actions
  const markOnboardingComplete = useCallback(async (onboardingData?: any): Promise<boolean> => {
    try {
      const response = await apiClient.post('/auth/complete-onboarding', onboardingData)
      if (response.error) throw new Error(response.error)

      // Update SWR cache
      mutate('/auth/me', response.data, false) 
      return true
    } catch (error) {
      console.error('Error completing onboarding:', error)
      return false
    }
  }, [apiClient, mutate])

  const resetOnboarding = useCallback(async (): Promise<boolean> => {
    try {
      const response = await apiClient.post('/auth/reset-onboarding')
      if (response.error) throw new Error(response.error)
      
      mutate('/auth/me', response.data, false)
      return true
    } catch (error) {
      console.error('Error resetting onboarding:', error)
      return false
    }
  }, [apiClient, mutate])

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


  const contextValue: UserContextType = useMemo(() => ({
    clerkUser,
    isClerkLoaded,
    isSignedIn: isSignedIn || false,
    backendUser: backendUser || null,
    userLoading,
    userError,
    onboarding,
    markOnboardingComplete,
    resetOnboarding,
    checkOnboardingStatus: async () => { await reloadUser() }, // Adapter for existing calls
    refetchUser: async () => { await reloadUser() },
    hasValidTrial,
    hasPaidSubscription,
    needsPayment
  }), [
    clerkUser, isClerkLoaded, isSignedIn, backendUser, userLoading, userError, onboarding,
    markOnboardingComplete, resetOnboarding, reloadUser, hasValidTrial, hasPaidSubscription, needsPayment
  ])

  // Handle connection errors specifically for the UI
  const connectionError = useMemo(() => {
    if (swrError && (swrError.message === 'Failed to fetch' || swrError.name === 'ConnectionError')) {
       return swrError
    }
    return null
  }, [swrError])


  if (connectionError) {
    return <ConnectionError error={connectionError} onRetry={() => reloadUser()} />
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
