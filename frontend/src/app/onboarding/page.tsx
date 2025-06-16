'use client'

import { Suspense } from 'react'
import { useUserContext } from '@/contexts/user-context'
import { useRouter } from 'next/navigation'
import { NewUserOnboarding } from '@/components/auth/onboarding'

function OnboardingContent() {
  const { backendUser, isClerkLoaded, isSignedIn } = useUserContext()
  const router = useRouter()

  // Redirect if not authenticated
  if (isClerkLoaded && !isSignedIn) {
    router.push('/auth/sign-in')
    return null
  }

  // If already completed onboarding, redirect to dashboard
  if (backendUser?.onboarding_completed) {
    router.push(`/${backendUser.tenant_id}/dashboard`)
    return null
  }

  const handleComplete = (tenantId?: string) => {
    if (tenantId) {
      router.push(`/${tenantId}/dashboard`)
    } else {
      router.push('/dashboard')
    }
  }

  return <NewUserOnboarding onComplete={handleComplete} />
}

export default function OnboardingPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    }>
      <OnboardingContent />
    </Suspense>
  )
}