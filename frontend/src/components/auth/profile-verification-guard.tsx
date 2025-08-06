'use client'

import { useRouter, usePathname } from 'next/navigation'
import { useEffect } from 'react'
import { useUserContext } from '@/contexts/user-context'
import { Loader2 } from 'lucide-react'

interface ProfileVerificationGuardProps {
  children: React.ReactNode
  fallback?: React.ReactNode
}

export function ProfileVerificationGuard({ children, fallback }: ProfileVerificationGuardProps) {
  const { isClerkLoaded, isSignedIn, backendUser, userLoading } = useUserContext()
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
    
    // Si no está en ruta permitida, verificar estado
    if (!isAllowedPath && backendUser) {
      // Check if user needs to complete payment (has no subscription)
      if (!backendUser.subscription_plan && !backendUser.stripe_customer_id) {
        // User registered but hasn't selected a plan or started trial
        router.push('/pricing')
        return
      }
      
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
      
      // If trial expired, redirect to pricing
      if (backendUser.subscription_status === 'trialing' && backendUser.trial_ends_at) {
        const trialEndsAt = new Date(backendUser.trial_ends_at)
        if (trialEndsAt < new Date()) {
          router.push('/pricing')
          return
        }
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
  
  // Rutas permitidas o verificación pasada
  return <>{children}</>
}