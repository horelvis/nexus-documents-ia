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
  const markOnboardingComplete = async (onboardingData?: any): Promise<boolean> => {
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
  }

  // Reset onboarding (for development/testing)
  const resetOnboarding = async (): Promise<boolean> => {
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
  }

  // Check user status in backend
  const checkOnboardingStatus = async (): Promise<void> => {
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
      setBackendUser(userData)
      
      // Check if user needs onboarding (only after first payment)
      const hasCompletedOnboarding = userData?.onboarding_completed || false
      setOnboarding({
        needsOnboarding: !hasCompletedOnboarding && userData?.subscription_plan !== 'free',
        isNewUser: false,
        hasCompletedSync: true,
        loading: false,
        error: null
      })

      // Redirect to onboarding only if:
      // 1. User has not completed onboarding
      // 2. User has a paid subscription (just came from checkout)
      // 3. Not already on onboarding page
      if (!hasCompletedOnboarding && userData?.subscription_plan !== 'free' && !isOnboardingPath()) {
        router.push(getOnboardingPath(userData))
      }

    } catch (error: any) {
      console.error('Error checking user status:', error)
      
      // Check if it's a connection error
      const isConnectionError = 
        error?.name === 'ConnectionError' ||
        error?.message?.includes('Unable to connect') ||
        error?.message?.includes('Failed to fetch')
      
      // For connection errors, silently fail without setting error state
      // The ConnectionProvider will handle showing the error page
      if (isConnectionError) {
        setBackendUser(null)
        setOnboarding({
          needsOnboarding: false,
          isNewUser: false,
          hasCompletedSync: false,
          loading: false,
          error: null // Don't set error for connection issues
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
    markOnboardingComplete,
    resetOnboarding,
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