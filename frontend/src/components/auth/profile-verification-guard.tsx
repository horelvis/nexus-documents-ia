'use client'

import { useRouter, usePathname } from 'next/navigation'
import { useEffect } from 'react'
import { useUserContext } from '@/contexts/user-context'
import { TenantNotFound } from '@/components/errors/tenant-not-found'
import { Loader2 } from 'lucide-react'

interface ProfileVerificationGuardProps {
  children: React.ReactNode
  fallback?: React.ReactNode
}

export function ProfileVerificationGuard({ children, fallback }: ProfileVerificationGuardProps) {
  const { isClerkLoaded, isSignedIn, backendUser, userLoading, onboarding, refetchUser } = useUserContext()
  const router = useRouter()
  const pathname = usePathname()
  
  // Lista simple de rutas permitidas sin verificación completa
  const allowedPaths = ['/onboarding', '/pricing', '/plans', '/auth/', '/help', '/checkout']
  const isAllowedPath = allowedPaths.some(path => pathname.includes(path))
  
  useEffect(() => {
    if (!isClerkLoaded || userLoading) return
    
    // No autenticado
    if (!isSignedIn) {
      router.push('/auth/sign-in')
      return
    }
    
    // Subscription redirects are now handled by middleware.ts
    // Only handle onboarding redirects here if needed
    if (!isAllowedPath && backendUser) {
      // Check if user needs onboarding
      // Only redirect to onboarding if:
      // 1. Has not completed onboarding
      // 2. Has an active subscription (including trial)
      const hasActiveSubscription = backendUser.subscription_plan && 
        (backendUser.subscription_plan !== 'free' || backendUser.subscription_status === 'trialing')
      
      if (!backendUser.onboarding_completed && hasActiveSubscription) {
        const tenantId = backendUser.tenant_id || 'temp'
        router.push(`/${tenantId}/onboarding`)
        return
      }
    }
  }, [isClerkLoaded, isSignedIn, backendUser, userLoading, pathname, isAllowedPath])
  
  // Loading
  if (!isClerkLoaded || userLoading) {
    return fallback || (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin" />
      </div>
    )
  }
  
  // No autenticado
  if (!isSignedIn) {
    return null
  }
  
  // Check for invalid tenant ID
  if (onboarding.error === 'INVALID_TENANT') {
    const tenantId = backendUser?.tenant_id || 'default'
    return <TenantNotFound tenantId={tenantId} onRetry={refetchUser} />
  }
  
  // Rutas permitidas o verificación pasada
  return <>{children}</>
}