'use client'

import { useRouter, usePathname } from 'next/navigation'
import { useEffect, useState } from 'react'
import { useUserContext } from '@/contexts/user-context'
import { useApiClient } from '@/lib/api-client'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { 
  CheckCircle, 
  AlertCircle, 
  CreditCard, 
  User, 
  Building,
  Loader2,
  ArrowRight
} from 'lucide-react'

interface ProfileVerificationStatus {
  hasCompletedNewOnboarding: boolean
  selectedPlan?: string
  hasValidPlan: boolean
  isVerified: boolean
  loading: boolean
}

interface ProfileVerificationGuardProps {
  children: React.ReactNode
  fallback?: React.ReactNode
}

export function ProfileVerificationGuard({ children, fallback }: ProfileVerificationGuardProps) {
  const { 
    isClerkLoaded, 
    isSignedIn, 
    backendUser,
    userLoading,
    onboarding,
    resetOnboarding
  } = useUserContext()
  const router = useRouter()
  const pathname = usePathname()
  const apiClient = useApiClient()
  
  // Early return for welcome paths to prevent infinite redirects
  if (pathname.includes('/welcome')) {
    return <>{children}</>
  }
  
  const [profileStatus, setProfileStatus] = useState<ProfileVerificationStatus>({
    hasCompletedNewOnboarding: false,
    hasValidPlan: false,
    isVerified: false,
    loading: true
  })

  // Check if we're on allowed paths that don't need full verification
  const isAllowedPath = () => {
    const allowedPaths = [
      '/onboarding',
      '/welcome',
      '/billing',
      '/pricing',  // Public pricing page
      '/plans',    // Authenticated plans page
      '/auth/',
      '/help'
    ]
    console.log('Checking allowed path:', pathname, allowedPaths.some(path => pathname.includes(path)))
    return allowedPaths.some(path => pathname.includes(path))
  }

  // Check if user has completed the new onboarding flow
  const checkNewOnboardingStatus = async (): Promise<boolean> => {
    try {
      const response = await apiClient.get('/auth/me')
      if (response.error) return false
      
      const user = response.data
      
      console.log('🔍 [PROFILE_GUARD] User data from /auth/me:', user)
      console.log('🔍 [PROFILE_GUARD] onboarding_completed:', user.onboarding_completed)
      console.log('🔍 [PROFILE_GUARD] subscription:', user.subscription)
      
      // Check if user has completed onboarding
      const hasCompletedOnboarding = user.onboarding_completed || false
      
      // Check subscription status to determine plan
      const subscription = user.subscription
      let planType = 'free'
      let hasActiveSubscription = false
      
      if (subscription && subscription.status === 'active') {
        planType = subscription.plan?.name || 'premium'
        hasActiveSubscription = true
      }
      
      // For access control:
      // - User must have completed onboarding (basic info)
      // - User must have an active paid subscription to access most areas
      const hasCompletedBasicOnboarding = hasCompletedOnboarding
      const hasFullAccess = hasActiveSubscription // Only paid users get full access
      
      console.log('🔍 [PROFILE_GUARD] hasCompletedBasicOnboarding:', hasCompletedBasicOnboarding)
      console.log('🔍 [PROFILE_GUARD] hasActiveSubscription:', hasActiveSubscription)
      console.log('🔍 [PROFILE_GUARD] hasFullAccess:', hasFullAccess)
      console.log('🔍 [PROFILE_GUARD] planType:', planType)
      
      setProfileStatus(prev => ({
        ...prev,
        hasCompletedNewOnboarding: hasCompletedBasicOnboarding,
        selectedPlan: planType,
        hasValidPlan: hasActiveSubscription
      }))
      
      return { hasCompletedBasicOnboarding, hasFullAccess }
    } catch (error) {
      console.log('Error checking new onboarding status:', error)
      return { hasCompletedBasicOnboarding: false, hasFullAccess: false }
    }
  }

  // Perform full profile verification
  const verifyProfile = async () => {
    if (!backendUser || userLoading || onboarding.loading) {
      return
    }

    setProfileStatus(prev => ({ ...prev, loading: true }))
    
    try {
      // Check if user completed the new onboarding flow
      const result = await checkNewOnboardingStatus()
      const { hasCompletedBasicOnboarding, hasFullAccess } = result
      
      // User has full access only with active subscription
      const isFullyVerified = hasFullAccess
      
      setProfileStatus(prev => ({
        ...prev,
        isVerified: isFullyVerified,
        loading: false
      }))
      
      // Redirect logic based on user status
      console.log('🔍 [PROFILE_GUARD] Basic onboarding complete:', hasCompletedBasicOnboarding)
      console.log('🔍 [PROFILE_GUARD] Has full access (paid):', hasFullAccess)
      console.log('🔍 [PROFILE_GUARD] Current path:', pathname)
      console.log('🔍 [PROFILE_GUARD] Is allowed path:', isAllowedPath())
      
      const tenantId = backendUser.tenant_id
      
      if (!hasCompletedBasicOnboarding && !isAllowedPath()) {
        // User hasn't completed basic onboarding - go to pricing first
        console.log('💳 [PROFILE_GUARD] Redirecting to pricing (no onboarding):', `/pricing`)
        router.push(`/pricing`)
      } else if (hasCompletedBasicOnboarding && !hasFullAccess && !isAllowedPath()) {
        // User completed onboarding but has no active subscription - go to plans page
        console.log('💳 [PROFILE_GUARD] Redirecting to plans (no subscription):', `/plans/${tenantId}`)
        router.push(`/plans/${tenantId}`)
      } else if (hasFullAccess) {
        console.log('✅ [PROFILE_GUARD] User has full access (paid), allowing access to:', pathname)
      } else {
        console.log('➡️ [PROFILE_GUARD] On allowed path, allowing access')
      }
      
    } catch (error) {
      console.log('Error verifying profile:', error)
      setProfileStatus(prev => ({ ...prev, loading: false }))
    }
  }

  useEffect(() => {
    if (isClerkLoaded && isSignedIn && backendUser && !userLoading && !onboarding.loading) {
      verifyProfile()
    }
  }, [isClerkLoaded, isSignedIn, backendUser, userLoading, onboarding.loading])

  // Loading state
  if (!isClerkLoaded || userLoading || onboarding.loading || profileStatus.loading) {
    return fallback || (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-center space-y-4">
          <Loader2 className="h-8 w-8 animate-spin mx-auto" />
          <p className="text-muted-foreground">Verificando perfil...</p>
        </div>
      </div>
    )
  }

  // Not signed in
  if (!isSignedIn) {
    return fallback || null
  }

  // Allow access to specific paths
  if (isAllowedPath()) {
    return <>{children}</>
  }

  // Profile verification failed - show verification screen
  if (!profileStatus.isVerified) {
    return (
      <div className="min-h-screen bg-gray-50 py-8">
        <div className="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8">
          {/* Header */}
          <div className="text-center mb-8">
            <h1 className="text-3xl font-bold text-gray-900 mb-2">
              {profileStatus.hasCompletedNewOnboarding && !profileStatus.hasValidPlan
                ? 'Selecciona un Plan para Continuar'
                : 'Selecciona un Plan para Comenzar'}
            </h1>
            <p className="text-lg text-gray-600">
              {profileStatus.hasCompletedNewOnboarding && !profileStatus.hasValidPlan
                ? 'Para acceder al sistema, necesitas seleccionar un plan de pago'
                : 'Para comenzar a usar Nexus, primero necesitas seleccionar un plan'}
            </p>
          </div>

          {/* Verification Status */}
          <Card className="mb-6">
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Building className="h-5 w-5" />
                <span>Estado de Verificación</span>
              </CardTitle>
              <CardDescription>
                Revisa el estado de tu perfil y los pasos pendientes
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* New Onboarding Status */}
              <div className="flex items-center justify-between p-4 border rounded-lg">
                <div className="flex items-center space-x-3">
                  {profileStatus.hasCompletedNewOnboarding ? (
                    <CheckCircle className="h-5 w-5 text-green-600" />
                  ) : (
                    <AlertCircle className="h-5 w-5 text-orange-600" />
                  )}
                  <div>
                    <p className="font-medium">Configuración de Cuenta</p>
                    <p className="text-sm text-muted-foreground">
                      Datos personales, empresa y selección de plan
                    </p>
                  </div>
                </div>
                <Badge 
                  variant={profileStatus.hasCompletedNewOnboarding ? "default" : "secondary"}
                  className={profileStatus.hasCompletedNewOnboarding ? "bg-green-100 text-green-800" : "bg-orange-100 text-orange-800"}
                >
                  {profileStatus.hasCompletedNewOnboarding ? "Completado" : "Pendiente"}
                </Badge>
              </div>

              {/* Selected Plan Status */}
              <div className="flex items-center justify-between p-4 border rounded-lg">
                <div className="flex items-center space-x-3">
                  {profileStatus.selectedPlan ? (
                    <CheckCircle className="h-5 w-5 text-green-600" />
                  ) : (
                    <AlertCircle className="h-5 w-5 text-orange-600" />
                  )}
                  <div>
                    <p className="font-medium">Plan Seleccionado</p>
                    <p className="text-sm text-muted-foreground">
                      {profileStatus.selectedPlan ? `Plan ${profileStatus.selectedPlan}` : 'Sin plan seleccionado'}
                    </p>
                  </div>
                </div>
                <Badge 
                  variant={profileStatus.selectedPlan ? "default" : "secondary"}
                  className={profileStatus.selectedPlan ? "bg-green-100 text-green-800" : "bg-orange-100 text-orange-800"}
                >
                  {profileStatus.selectedPlan ? "Configurado" : "Pendiente"}
                </Badge>
              </div>

              {/* Progress Bar */}
              <div className="mt-6">
                <div className="flex items-center justify-between text-sm text-gray-600 mb-2">
                  <span>Progreso de Configuración</span>
                  <span>
                    {profileStatus.hasCompletedNewOnboarding ? '1' : '0'} de 1 completado
                  </span>
                </div>
                <Progress 
                  value={profileStatus.hasCompletedNewOnboarding ? 100 : 0} 
                  className="w-full" 
                />
              </div>
            </CardContent>
          </Card>

          {/* Action Buttons */}
          <div className="flex flex-col space-y-3">
            {!profileStatus.hasCompletedNewOnboarding && (
              <Button 
                onClick={() => {
                  router.push('/pricing')
                }}
                className="w-full"
                size="lg"
              >
                <CreditCard className="h-4 w-4 mr-2" />
                Ver Planes y Precios
                <ArrowRight className="h-4 w-4 ml-2" />
              </Button>
            )}
            
            {profileStatus.hasCompletedNewOnboarding && !profileStatus.hasValidPlan && (
              <Button 
                onClick={() => {
                  const tenantId = backendUser?.tenant_id
                  router.push(`/plans/${tenantId}`)
                }}
                className="w-full"
                size="lg"
              >
                <CreditCard className="h-4 w-4 mr-2" />
                Ver Planes y Precios
                <ArrowRight className="h-4 w-4 ml-2" />
              </Button>
            )}
          </div>

          {/* Help Section */}
          <div className="mt-8 text-center space-y-4">
            <p className="text-sm text-muted-foreground mb-2">
              ¿Necesitas ayuda con la configuración?
            </p>
            <Button 
              variant="ghost" 
              onClick={() => {
                const tenantId = backendUser?.tenant_id
                router.push(`/${tenantId}/help`)
              }}
            >
              Contactar Soporte
            </Button>
            
            {/* Development tools */}
            <div className="pt-4 border-t space-y-3">
              <p className="text-xs text-muted-foreground">
                🚧 Herramientas de Desarrollo:
              </p>
              
              <div className="flex flex-col space-y-2">
                <Button 
                  variant="outline" 
                  size="sm"
                  onClick={async () => {
                    const success = await resetOnboarding()
                    if (success) {
                      // Redirect to welcome page after reset
                      const tenantId = backendUser?.tenant_id
                      router.push(`/welcome/${tenantId}`)
                    }
                  }}
                >
                  🔄 Resetear Onboarding
                </Button>
                
                <Button 
                  variant="destructive" 
                  size="sm"
                  onClick={async () => {
                    if (!confirm('⚠️ PELIGRO: Esto eliminará tu usuario completamente de la base de datos. ¿Estás seguro?')) {
                      return
                    }
                    
                    try {
                      const response = await apiClient.delete('/auth/dev/delete-user')
                      if (!response.error) {
                        alert('✅ Usuario eliminado. Serás redirigido al login.')
                        // Redirect to sign out and then to home
                        window.location.href = '/auth/sign-in'
                      } else {
                        alert(`❌ Error: ${response.error}`)
                      }
                    } catch (error) {
                      alert(`❌ Error eliminando usuario: ${error.message}`)
                    }
                  }}
                >
                  🗑️ Eliminar Usuario Completamente
                </Button>
                
                <p className="text-xs text-red-500">
                  ⚠️ El botón rojo elimina TODO: usuario, documentos, suscripciones, etc.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // Profile is fully verified
  return <>{children}</>
}