'use client'

import { createContext, useContext, useState, useEffect } from 'react'
import { useUser } from '@clerk/nextjs'
import { useRouter, usePathname } from 'next/navigation'
import { useApiClient } from '@/lib/api-client'

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
  
  // Onboarding state
  const [onboarding, setOnboarding] = useState<OnboardingStatus>({
    needsOnboarding: false,
    isNewUser: false,
    hasCompletedSync: false,
    loading: true,
    error: null
  })

  // Helper function to get tenant-aware welcome path
  const getWelcomePath = (userData?: BackendUser) => {
    if (userData?.tenant_id) {
      return `/welcome/${userData.tenant_id}`
    }
    // Fallback to extract tenantId from pathname if available
    const tenantMatch = pathname.match(/^\/([^\/]+)\//)
    if (tenantMatch) {
      return `/welcome/${tenantMatch[1]}`
    }
    return '/welcome' // Fallback
  }

  // Helper function to check if current path is welcome or onboarding
  const isWelcomeOrOnboardingPath = () => {
    return pathname.includes('/welcome') || pathname.includes('/onboarding')
  }

  // Sync user with backend
  const syncUserWithBackend = async (stripeData?: {
    sessionId?: string
    customerId?: string
    subscriptionId?: string
    planId?: string
  }): Promise<void> => {
    if (!clerkUser) throw new Error('No user found')

    try {
      const payload = {
        clerk_user_id: clerkUser.id,
        email: clerkUser.emailAddresses[0]?.emailAddress,
        full_name: `${clerkUser.firstName || ''} ${clerkUser.lastName || ''}`.trim(),
        // Include Stripe data if available
        ...(stripeData && {
          stripe_customer_id: stripeData.customerId,
          stripe_session_id: stripeData.sessionId,
          subscription_data: stripeData.subscriptionId ? {
            stripe_subscription_id: stripeData.subscriptionId,
            plan_id: stripeData.planId
          } : undefined
        })
      }

      const response = await apiClient.post('/auth/sync-user', payload)

      if (response.error) {
        throw new Error(response.error)
      }

      setBackendUser(response.data)
      setOnboarding(prev => ({
        ...prev,
        hasCompletedSync: true,
        isNewUser: false
      }))

      return response.data
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : 'Sync failed'
      setOnboarding(prev => ({
        ...prev,
        error: errorMsg
      }))
      throw error
    }
  }

  // Mark onboarding as completed
  const markOnboardingComplete = async (onboardingData?: any): Promise<boolean> => {
    try {
      const payload = onboardingData ? { company_profile: onboardingData } : undefined
      const response = await apiClient.post('/auth/complete-onboarding', payload)
      
      if (response.error) {
        throw new Error(response.error)
      }

      // Update local state
      setBackendUser(prev => prev ? { ...prev, onboarding_completed: true } : null)
      setOnboarding(prev => ({
        ...prev,
        needsOnboarding: false
      }))
      
      return true
    } catch (error) {
      console.error('Error completing onboarding:', error)
      return false
    }
  }

  // Check onboarding status
  const checkOnboardingStatus = async (): Promise<void> => {
    if (!clerkUser) return

    try {
      setOnboarding(prev => ({ ...prev, loading: true, error: null }))
      setUserLoading(true)

      // Check if user exists in our backend
      const response = await apiClient.get('/auth/me')
      
      if (response.error) {
        // User doesn't exist in backend, needs sync
        setBackendUser(null)
        setOnboarding({
          needsOnboarding: true,
          isNewUser: true,
          hasCompletedSync: false,
          loading: false,
          error: null
        })
        
        // Redirect to welcome page for new users
        if (!isWelcomeOrOnboardingPath()) {
          router.push(getWelcomePath())
        }
        return
      }

      // User exists, update state
      const userData: BackendUser = response.data
      setBackendUser(userData)
      
      const hasCompletedOnboarding = userData?.onboarding_completed || false
      setOnboarding({
        needsOnboarding: !hasCompletedOnboarding,
        isNewUser: false,
        hasCompletedSync: true,
        loading: false,
        error: null
      })

      // Redirect to welcome page if needs onboarding and not already there
      if (!hasCompletedOnboarding && !isWelcomeOrOnboardingPath()) {
        router.push(getWelcomePath(userData))
      }

    } catch (error) {
      console.error('Error checking onboarding status:', error)
      
      // If there's an error, assume user needs onboarding
      setBackendUser(null)
      setOnboarding({
        needsOnboarding: true,
        isNewUser: true,
        hasCompletedSync: false,
        loading: false,
        error: error instanceof Error ? error.message : 'Unknown error'
      })

      // Redirect to welcome page for error cases
      if (!isWelcomeOrOnboardingPath()) {
        router.push(getWelcomePath())
      }
    } finally {
      setUserLoading(false)
    }
  }

  // Refetch user data
  const refetchUser = async (): Promise<void> => {
    if (!clerkUser) return
    await checkOnboardingStatus()
  }

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

  const contextValue: UserContextType = {
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
    syncUserWithBackend,
    markOnboardingComplete,
    checkOnboardingStatus,
    refetchUser
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

export function useOnboardingStatus() {
  const { onboarding } = useUserContext()
  return onboarding
}