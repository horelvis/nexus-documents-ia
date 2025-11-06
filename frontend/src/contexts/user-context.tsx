'use client'

import { createContext, useContext, useState, useEffect, useMemo, useCallback } from 'react'
import { useUser } from '@clerk/nextjs'
import { useRouter, usePathname } from 'next/navigation'
import { useApiClient } from '@/lib/api-client'
import { ConnectionError } from '@/components/errors/connection-error'

import type { BackendUser, OnboardingStatus, UserContextType, UserProviderProps } from '@/lib/types'

const UserContext = createContext<UserContextType | undefined>(undefined)

export function UserProvider({ children }: UserProviderProps) {
  const { user: clerkUser, isLoaded: isClerkLoaded, isSignedIn } = useUser()
  const router = useRouter()
  const pathname = usePathname()
  const apiClient = useApiClient()
  
  // Backend user state
  const [backendUser, setBackendUser] = useState<BackendUser | null>(null)
  const [userLoading, setUserLoading] = useState(true)
  const [userError] = useState<string | null>(null)
  const [initialLoadComplete, setInitialLoadComplete] = useState(false)
  const [connectionError, setConnectionError] = useState<Error | null>(null)
  
  // Onboarding state
  const [onboarding, setOnboarding] = useState<OnboardingStatus>({
    needsOnboarding: false,
    isNewUser: false,
    hasCompletedSync: false,
    loading: true,
    error: null
  })

  // Helper function to get tenant-aware onboarding path
  const getOnboardingPath = (userData?: BackendUser) => {
    if (userData?.tenant_id) {
      return `/${userData.tenant_id}/onboarding`
    }
    // Fallback to extract tenantId from pathname if available
    const tenantMatch = pathname.match(/^\/([^\/]+)\//)
    if (tenantMatch) {
      return `/${tenantMatch[1]}/onboarding`
    }
    return '/onboarding' // Fallback
  }

  // Helper function to check if current path is onboarding
  const isOnboardingPath = () => {
    return pathname.includes('/onboarding')
  }

  // Note: syncUserWithBackend removed - users are created automatically by backend
  // when they sign up through Clerk after completing checkout

  // Mark onboarding as completed
  const markOnboardingComplete = useCallback(async (onboardingData?: any): Promise<boolean> => {
    try {
      // Send the onboarding data directly as the request body
      const response = await apiClient.post('/auth/complete-onboarding', onboardingData)
      
      if (response.error) {
        throw new Error(response.error)
      }

      // Update local state with the returned user data
      const updatedUser: BackendUser = response.data
      setBackendUser(updatedUser)
      setOnboarding(prev => ({
        ...prev,
        needsOnboarding: false
      }))
      
      return true
    } catch (error) {
      console.error('Error completing onboarding:', error)
      return false
    }
  }, [apiClient])

  // Reset onboarding (for development/testing)
  const resetOnboarding = useCallback(async (): Promise<boolean> => {
    try {
      const response = await apiClient.post('/auth/reset-onboarding')
      
      if (response.error) {
        throw new Error(response.error)
      }

      // Update local state
      const updatedUser: BackendUser = response.data
      setBackendUser(updatedUser)
      setOnboarding(prev => ({
        ...prev,
        needsOnboarding: true
      }))
      
      return true
    } catch (error) {
      console.error('Error resetting onboarding:', error)
      return false
    }
  }, [apiClient])

  // Check user status in backend
  const checkOnboardingStatus = useCallback(async (): Promise<void> => {
    if (!clerkUser) return

    try {
      setOnboarding(prev => ({ ...prev, loading: true, error: null }))
      setUserLoading(true)

      // Check if user exists in our backend
      const response = await apiClient.get('/auth/me')
      
      if (response.error) {
        // User doesn't exist in backend yet - this is normal for new users
        // They will be created when they complete checkout
        setBackendUser(null)
        setOnboarding({
          needsOnboarding: false,
          isNewUser: true,
          hasCompletedSync: false,
          loading: false,
          error: null
        })
        return
      }

      // User exists, update state
      const userData: BackendUser = response.data
      
      // Check for invalid/default tenant ID
      const isInvalidTenantId = !userData.tenant_id || 
        userData.tenant_id === 'default' || 
        userData.tenant_id === '00000000-0000-0000-0000-000000000000' ||
        userData.tenant_id === 'undefined' ||
        userData.tenant_id === 'null'
      
      if (isInvalidTenantId) {
        console.error('Invalid tenant ID detected:', userData.tenant_id)
        setOnboarding({
          needsOnboarding: false,
          isNewUser: false,
          hasCompletedSync: false,
          loading: false,
          error: 'INVALID_TENANT'
        })
        setUserLoading(false)
        return
      }
      
      setBackendUser(userData)
      
      // Check if user needs onboarding (only after first payment or trial start)
      const hasCompletedOnboarding = userData?.onboarding_completed || false
      const needsOnboarding = !hasCompletedOnboarding && 
        (userData?.subscription_plan !== 'free' || userData?.subscription_status === 'trialing')
      
      setOnboarding({
        needsOnboarding,
        isNewUser: false,
        hasCompletedSync: true,
        loading: false,
        error: null
      })

      // Subscription redirects are now handled by middleware.ts
      // Only handle onboarding redirects here
      
      // Check if user has valid subscription or trial for onboarding purposes
      const hasValidTrial = userData?.trial_ends_at && new Date(userData.trial_ends_at) > new Date()
      const hasPaidSubscription = userData?.subscription_plan && 
        ['basic', 'pro', 'professional', 'enterprise'].includes(userData.subscription_plan)
      
      // If user has paid plan (including valid trial) but hasn't completed onboarding
      const hasValidPlan = hasPaidSubscription || hasValidTrial
      
      if (!hasCompletedOnboarding && hasValidPlan && !isOnboardingPath()) {
        router.push(getOnboardingPath(userData))
      }

    } catch (error: any) {
      console.error('Error checking user status:', error)
      
      // Check if it's a connection error
      const isConnectionError = 
        error?.name === 'ConnectionError' ||
        error?.message?.includes('Unable to connect') ||
        error?.message?.includes('Failed to fetch')
      
      // For connection errors, show ConnectionError overlay
      if (isConnectionError) {
        setConnectionError(error)
        setBackendUser(null)
        setOnboarding({
          needsOnboarding: false,
          isNewUser: false,
          hasCompletedSync: false,
          loading: false,
          error: null
        })
      } else {
        // For other errors, set the error state
        setBackendUser(null)
        setOnboarding({
          needsOnboarding: false,
          isNewUser: false,
          hasCompletedSync: false,
          loading: false,
          error: error instanceof Error ? error.message : 'Unknown error'
        })
      }
    } finally {
      setUserLoading(false)
    }
  }, [clerkUser, apiClient, pathname, router])

  // Helper functions for subscription status
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

  // Refetch user data
  const refetchUser = useCallback(async (): Promise<void> => {
    if (!clerkUser) return
    await checkOnboardingStatus()
  }, [clerkUser, checkOnboardingStatus])

  // Initialize user data when Clerk user is loaded
  useEffect(() => {
    if (!isClerkLoaded) {
      setUserLoading(true)
      setOnboarding(prev => ({ ...prev, loading: true }))
      return
    }

    if (!clerkUser) {
      setUserLoading(false)
      setBackendUser(null)
      setOnboarding(prev => ({ ...prev, loading: false }))
      return
    }

    // User is loaded, check backend status
    checkOnboardingStatus()
  }, [isClerkLoaded, clerkUser])

  const contextValue: UserContextType = useMemo(() => ({
    // Clerk data
    clerkUser,
    isClerkLoaded,
    isSignedIn: isSignedIn || false,
    
    // Backend data
    backendUser,
    userLoading,
    userError,
    
    // Onboarding
    onboarding,
    
    // Actions
    markOnboardingComplete,
    resetOnboarding,
    checkOnboardingStatus,
    refetchUser,
    
    // Subscription helpers
    hasValidTrial,
    hasPaidSubscription,
    needsPayment
  }), [
    clerkUser,
    isClerkLoaded,
    isSignedIn,
    backendUser,
    userLoading,
    userError,
    onboarding,
    markOnboardingComplete,
    resetOnboarding,
    checkOnboardingStatus,
    refetchUser,
    hasValidTrial,
    hasPaidSubscription,
    needsPayment
  ])

  if (connectionError) {
    const handleRetry = async () => {
      setConnectionError(null)
      await checkOnboardingStatus()
    }
    return <ConnectionError error={connectionError} onRetry={handleRetry} />
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
