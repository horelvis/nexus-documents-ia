"use client"

import { useRouter, usePathname } from 'next/navigation'
import { useEffect } from 'react'
import { useUserContext } from '@/contexts/user-context'

interface AuthGuardProps {
  children: React.ReactNode
  fallback?: React.ReactNode
}

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
    return fallback || (
      <div className="flex min-h-screen items-center justify-center">
        <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-gray-900"></div>
      </div>
    )
  }

  if (!isSignedIn) {
    return fallback || null
  }

  // Let components handle onboarding display - don't block here

  return <>{children}</>
}