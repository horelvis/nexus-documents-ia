"use client"

import { useRouter, usePathname } from 'next/navigation'
import { useEffect } from 'react'
import { useUserContext } from '@/contexts/user-context'
import { InitialLoader } from '@/components/ui/unified-loader'

import type { AuthGuardProps } from '@/lib/types'

export function AuthGuard({ children, fallback }: AuthGuardProps) {
  const { 
    isClerkLoaded, 
    isSignedIn, 
    onboarding: { needsOnboarding, loading: onboardingLoading },
    userLoading
  } = useUserContext()
  const router = useRouter()
  const pathname = usePathname()

  useEffect(() => {
    if (isClerkLoaded && !isSignedIn) {
      router.push('/auth/sign-in')
    }
  }, [isClerkLoaded, isSignedIn, router])

  if (!isClerkLoaded || userLoading || onboardingLoading) {
    return fallback || <InitialLoader />
  }

  if (!isSignedIn) {
    return fallback || null
  }

  // Let components handle onboarding display - don't block here

  return <>{children}</>
}