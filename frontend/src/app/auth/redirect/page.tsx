"use client"

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useUser } from '@clerk/nextjs'
import { useUserContext } from '@/contexts/user-context'
import { InitialLoader } from '@/components/ui/unified-loader'

export default function AuthRedirectPage() {
  const router = useRouter()
  const { user: clerkUser, isLoaded: isClerkLoaded } = useUser()
  const { backendUser, userLoading, checkOnboardingStatus } = useUserContext()

  useEffect(() => {
    const handleRedirect = async () => {
      // Wait for Clerk to load
      if (!isClerkLoaded) return

      // If no Clerk user, redirect to sign-in
      if (!clerkUser) {
        router.push('/auth/sign-in')
        return
      }

      // Wait for backend user data to load
      if (userLoading) return

      try {
        // If we don't have backend user data yet, try to fetch it
        if (!backendUser) {
          console.log('[auth/redirect] No backendUser yet, checking status…')
          await checkOnboardingStatus()
          return // Wait for the next effect run
        }
        console.log('[auth/redirect] backendUser snapshot', {
          tenantId: backendUser.tenant_id,
          onboardingCompleted: backendUser.onboarding_completed,
          subscriptionPlan: backendUser.subscription_plan,
          subscriptionStatus: backendUser.subscription_status,
          trialEndsAt: backendUser.trial_ends_at
        })

        // Check for invalid tenant ID
        const isInvalidTenantId = !backendUser.tenant_id ||
          backendUser.tenant_id === 'default' ||
          backendUser.tenant_id === '00000000-0000-0000-0000-000000000000' ||
          backendUser.tenant_id === 'undefined' ||
          backendUser.tenant_id === 'null'

        if (isInvalidTenantId) {
          console.error('Invalid tenant ID detected:', backendUser.tenant_id)
          // Redirect to a page that handles tenant creation/setup
          router.push('/tenant-not-found')
          return
        }

        // Check if user needs onboarding
        const hasCompletedOnboarding = backendUser?.onboarding_completed || false
        const hasValidTrial = backendUser?.trial_ends_at && new Date(backendUser.trial_ends_at) > new Date()
        const hasPaidSubscription = backendUser?.subscription_plan &&
          ['basic', 'pro', 'professional', 'enterprise'].includes(backendUser.subscription_plan)

        const hasValidPlan = hasPaidSubscription || hasValidTrial
        const needsOnboarding = !hasCompletedOnboarding && hasValidPlan

        if (needsOnboarding) {
          console.log('[auth/redirect] Needs onboarding, redirecting', { tenantId: backendUser.tenant_id })
          // Redirect to onboarding
          router.push(`/${backendUser.tenant_id}/onboarding`)
          return
        }

        // Check subscription status
        const hasActiveStatus = backendUser?.subscription_status &&
          ['active', 'trialing'].includes(backendUser.subscription_status)

        if (!hasValidTrial && !hasPaidSubscription && !hasActiveStatus) {
          console.log('[auth/redirect] No valid subscription or trial, sending to plans')
          // No valid subscription, redirect to plans
          router.push(`/${backendUser.tenant_id}/plans`)
          return
        }

        console.log('[auth/redirect] All good, going to dashboard')
        // Everything is good, redirect to dashboard
        router.push(`/${backendUser.tenant_id}/dashboard`)

      } catch (error) {
        console.error('Error during auth redirect:', error)
        // On error, redirect to a safe fallback
        router.push('/auth/sign-in')
      }
    }

    handleRedirect()
  }, [isClerkLoaded, clerkUser, backendUser, userLoading, router, checkOnboardingStatus])

  // Show loading while processing
  return <InitialLoader />
}
