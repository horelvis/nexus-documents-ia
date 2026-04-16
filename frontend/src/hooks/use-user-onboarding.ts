'use client'

import { useState, useEffect } from 'react'
import { useUser } from '@clerk/nextjs'
import { useRouter, usePathname } from 'next/navigation'
import { useApiClient } from '@/lib/api-client'

export interface OnboardingStatus {
  needsOnboarding: boolean
  isNewUser: boolean
  hasCompletedSync: boolean
  loading: boolean
  error: string | null
}

export function useUserOnboarding() {
  const { user, isLoaded } = useUser()
  const router = useRouter()
  const pathname = usePathname()
  const apiClient = useApiClient()
  
  const [status, setStatus] = useState<OnboardingStatus>({
    needsOnboarding: false,
    isNewUser: false,
    hasCompletedSync: false,
    loading: true,
    error: null
  })

  useEffect(() => {
    if (!isLoaded || !user) {
      setStatus(prev => ({ ...prev, loading: false }))
      return
    }

    checkOnboardingStatus()
  }, [isLoaded, user])

  const checkOnboardingStatus = async () => {
    if (!user) return

    try {
      setStatus(prev => ({ ...prev, loading: true, error: null }))

      // Check if user exists in our backend
      const response = await apiClient.get('/auth/me')
      
      if (response.error) {
        // User doesn't exist in backend, needs sync
        setStatus({
          needsOnboarding: true,
          isNewUser: true,
          hasCompletedSync: false,
          loading: false,
          error: null
        })
        
        // Redirect to pricing if not already there
        if (pathname !== '/pricing' && !pathname.includes('/onboarding')) {
          router.push('/pricing')
        }
        return
      }

      // User exists, check if they've completed onboarding
      const userData = response.data
      const hasCompletedOnboarding = userData?.onboarding_completed || false

      setStatus({
        needsOnboarding: !hasCompletedOnboarding,
        isNewUser: false,
        hasCompletedSync: true,
        loading: false,
        error: null
      })

      // Redirect to onboarding if needed and not already there
      if (!hasCompletedOnboarding && pathname !== '/pricing' && !pathname.includes('/onboarding')) {
        router.push(`/onboarding`)
      }

    } catch (error) {
      console.error('Error checking onboarding status:', error)
      
      // If there's an error, assume user needs onboarding
      setStatus({
        needsOnboarding: true,
        isNewUser: true,
        hasCompletedSync: false,
        loading: false,
        error: error instanceof Error ? error.message : 'Unknown error'
      })

      // Redirect to pricing
      if (pathname !== '/pricing' && !pathname.includes('/onboarding')) {
        router.push('/pricing')
      }
    }
  }

  const markOnboardingComplete = async () => {
    try {
      // Call backend to mark onboarding as completed
      await apiClient.post('/auth/complete-onboarding')
      
      setStatus(prev => ({
        ...prev,
        needsOnboarding: false
      }))
      
      return true
    } catch (error) {
      console.error('Error completing onboarding:', error)
      return false
    }
  }

  const syncUserWithBackend = async () => {
    if (!user) throw new Error('No user found')

    try {
      const response = await apiClient.post('/auth/sync-user', {
        clerk_user_id: user.id,
        email: user.emailAddresses[0]?.emailAddress,
        full_name: `${user.firstName || ''} ${user.lastName || ''}`.trim()
      })

      if (response.error) {
        throw new Error(response.error)
      }

      setStatus(prev => ({
        ...prev,
        hasCompletedSync: true,
        isNewUser: false
      }))

      return response.data
    } catch (error) {
      setStatus(prev => ({
        ...prev,
        error: error instanceof Error ? error.message : 'Sync failed'
      }))
      throw error
    }
  }

  return {
    ...status,
    checkOnboardingStatus,
    markOnboardingComplete,
    syncUserWithBackend
  }
}