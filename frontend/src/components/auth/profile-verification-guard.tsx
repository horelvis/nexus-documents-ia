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
  const allowedPaths = ['/onboarding', '/pricing', '/plans', '/auth/', '/help']
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
      // Solo redirigir a onboarding si:
      // 1. No ha completado onboarding
      // 2. Tiene una suscripción activa (no es plan free)
      if (!backendUser.onboarding_completed && backendUser.subscription_plan && backendUser.subscription_plan !== 'free') {
        router.push('/onboarding')
        return
      }
      
      // Si es usuario free sin onboarding completado, está bien
      // El onboarding solo es requerido para usuarios con suscripción pagada
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