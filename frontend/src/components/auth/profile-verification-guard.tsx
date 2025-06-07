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
  hasSubscription: boolean
  subscriptionStatus?: string
  planName?: string
  hasCompletedOnboarding: boolean
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
    onboarding
  } = useUserContext()
  const router = useRouter()
  const pathname = usePathname()
  const apiClient = useApiClient()
  
  // Early return for welcome paths to prevent infinite redirects
  if (pathname.includes('/welcome')) {
    return <>{children}</>
  }
  
  const [profileStatus, setProfileStatus] = useState<ProfileVerificationStatus>({
    hasSubscription: false,
    hasCompletedOnboarding: false,
    isVerified: false,
    loading: true
  })

  // Check if we're on allowed paths that don't need full verification
  const isAllowedPath = () => {
    const allowedPaths = [
      '/onboarding',
      '/welcome',
      '/billing',
      '/auth/',
      '/help'
    ]
    console.log('Checking allowed path:', pathname, allowedPaths.some(path => pathname.includes(path)))
    return allowedPaths.some(path => pathname.includes(path))
  }

  // Check subscription status
  const checkSubscriptionStatus = async (): Promise<boolean> => {
    try {
      const response = await apiClient.get('/auth/me')
      if (response.error) return false
      
      const user = response.data
      const subscription = user.subscription
      
      if (!subscription) {
        setProfileStatus(prev => ({
          ...prev,
          hasSubscription: false,
          subscriptionStatus: 'none',
          planName: 'No Plan'
        }))
        return false
      }
      
      const isActive = subscription.status === 'active'
      setProfileStatus(prev => ({
        ...prev,
        hasSubscription: isActive,
        subscriptionStatus: subscription.status,
        planName: subscription.plan?.name || 'Unknown Plan'
      }))
      
      return isActive
    } catch (error) {
      console.error('Error checking subscription:', error)
      return false
    }
  }

  // Perform full profile verification
  const verifyProfile = async () => {
    if (!backendUser || userLoading || onboarding.loading) {
      return
    }

    setProfileStatus(prev => ({ ...prev, loading: true }))
    
    try {
      // Check subscription
      const hasValidSubscription = await checkSubscriptionStatus()
      
      // Check onboarding
      const hasCompletedOnboarding = backendUser.onboarding_completed || false
      
      const isFullyVerified = hasValidSubscription && hasCompletedOnboarding
      
      setProfileStatus(prev => ({
        ...prev,
        hasCompletedOnboarding,
        isVerified: isFullyVerified,
        loading: false
      }))
      
      // Redirect if profile is incomplete and not on allowed paths
      if (!isFullyVerified && !isAllowedPath()) {
        if (!hasCompletedOnboarding) {
          const tenantId = backendUser.tenant_id
          router.push(`/welcome/${tenantId}`)
        } else if (!hasValidSubscription) {
          const tenantId = backendUser.tenant_id
          router.push(`/${tenantId}/billing`)
        }
      }
      
    } catch (error) {
      console.error('Error verifying profile:', error)
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
              Completar Configuración de Perfil
            </h1>
            <p className="text-lg text-gray-600">
              Completa los siguientes pasos para acceder a todas las funcionalidades
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
              {/* Onboarding Status */}
              <div className="flex items-center justify-between p-4 border rounded-lg">
                <div className="flex items-center space-x-3">
                  {profileStatus.hasCompletedOnboarding ? (
                    <CheckCircle className="h-5 w-5 text-green-600" />
                  ) : (
                    <AlertCircle className="h-5 w-5 text-orange-600" />
                  )}
                  <div>
                    <p className="font-medium">Proceso de Bienvenida</p>
                    <p className="text-sm text-muted-foreground">
                      Configuración inicial de tu cuenta
                    </p>
                  </div>
                </div>
                <Badge 
                  variant={profileStatus.hasCompletedOnboarding ? "default" : "secondary"}
                  className={profileStatus.hasCompletedOnboarding ? "bg-green-100 text-green-800" : "bg-orange-100 text-orange-800"}
                >
                  {profileStatus.hasCompletedOnboarding ? "Completado" : "Pendiente"}
                </Badge>
              </div>

              {/* Subscription Status */}
              <div className="flex items-center justify-between p-4 border rounded-lg">
                <div className="flex items-center space-x-3">
                  {profileStatus.hasSubscription ? (
                    <CheckCircle className="h-5 w-5 text-green-600" />
                  ) : (
                    <AlertCircle className="h-5 w-5 text-red-600" />
                  )}
                  <div>
                    <p className="font-medium">Plan de Suscripción</p>
                    <p className="text-sm text-muted-foreground">
                      {profileStatus.planName} - {profileStatus.subscriptionStatus || 'No activo'}
                    </p>
                  </div>
                </div>
                <Badge 
                  variant={profileStatus.hasSubscription ? "default" : "destructive"}
                  className={profileStatus.hasSubscription ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800"}
                >
                  {profileStatus.hasSubscription ? "Activo" : "Inactivo"}
                </Badge>
              </div>

              {/* Progress Bar */}
              <div className="mt-6">
                <div className="flex items-center justify-between text-sm text-gray-600 mb-2">
                  <span>Progreso de Configuración</span>
                  <span>
                    {(profileStatus.hasCompletedOnboarding ? 1 : 0) + (profileStatus.hasSubscription ? 1 : 0)} de 2 completados
                  </span>
                </div>
                <Progress 
                  value={((profileStatus.hasCompletedOnboarding ? 1 : 0) + (profileStatus.hasSubscription ? 1 : 0)) * 50} 
                  className="w-full" 
                />
              </div>
            </CardContent>
          </Card>

          {/* Action Buttons */}
          <div className="flex flex-col space-y-3">
            {!profileStatus.hasCompletedOnboarding && (
              <Button 
                onClick={() => {
                  const tenantId = backendUser?.tenant_id
                  router.push(`/welcome/${tenantId}`)
                }}
                className="w-full"
                size="lg"
              >
                <User className="h-4 w-4 mr-2" />
                Completar Proceso de Bienvenida
                <ArrowRight className="h-4 w-4 ml-2" />
              </Button>
            )}
            
            {!profileStatus.hasSubscription && (
              <Button 
                onClick={() => {
                  const tenantId = backendUser?.tenant_id
                  router.push(`/${tenantId}/billing`)
                }}
                variant={profileStatus.hasCompletedOnboarding ? "default" : "outline"}
                className="w-full"
                size="lg"
              >
                <CreditCard className="h-4 w-4 mr-2" />
                Configurar Plan de Suscripción
                <ArrowRight className="h-4 w-4 ml-2" />
              </Button>
            )}
          </div>

          {/* Help Section */}
          <div className="mt-8 text-center">
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
          </div>
        </div>
      </div>
    )
  }

  // Profile is fully verified
  return <>{children}</>
}