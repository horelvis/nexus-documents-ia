'use client'

import { useRouter } from 'next/navigation'
import { UserOnboarding } from '@/components/auth/user-onboarding'

export default function OnboardingPage() {
  const router = useRouter()

  const handleOnboardingComplete = () => {
    // Redirect to dashboard after onboarding
    router.push('/dashboard')
  }

  return (
    <UserOnboarding onComplete={handleOnboardingComplete} />
  )
}