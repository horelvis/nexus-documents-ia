'use client'

/**
 * Onboarding Page
 *
 * Shown to new users who haven't connected any data sources yet.
 * Guides them through connector authorization and sync setup.
 */

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { IconBrain, IconLoader2 } from '@tabler/icons-react'
import { useAuth } from '@/contexts/auth-context'
import { ConnectorOnboarding } from '@/components/onboarding/ConnectorOnboarding'

export default function OnboardingPage() {
  const { isLoaded, isAuthenticated, user, completeOnboarding } = useAuth()
  const router = useRouter()

  // Redirect to login if not authenticated
  useEffect(() => {
    if (isLoaded && !isAuthenticated) {
      router.push('/auth/sign-in')
    }
  }, [isLoaded, isAuthenticated, router])

  // Redirect to Emma if already completed onboarding
  useEffect(() => {
    if (isLoaded && user?.onboarding_completed) {
      router.push('/')
    }
  }, [isLoaded, user, router])

  // Loading state
  if (!isLoaded) {
    return (
      <div className="flex items-center justify-center h-screen bg-background">
        <IconLoader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  // Not authenticated
  if (!isAuthenticated) {
    return null
  }

  const handleComplete = async () => {
    await completeOnboarding()
    router.push('/')
  }

  const handleSkip = async () => {
    await completeOnboarding()
    router.push('/')
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="h-14 border-b flex items-center justify-center px-4">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-primary/10">
            <IconBrain className="h-5 w-5 text-primary" />
          </div>
          <span className="font-semibold text-lg">Emma</span>
        </div>
      </header>

      {/* Content */}
      <main className="container max-w-4xl mx-auto py-12 px-4">
        <ConnectorOnboarding onComplete={handleComplete} onSkip={handleSkip} />
      </main>
    </div>
  )
}
