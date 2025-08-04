'use client'

import { useEffect, useState } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import { SignUp, useAuth, useUser } from '@clerk/nextjs'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { CheckCircle, Loader2, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { getAllPlans } from '@/lib/stripe-plans'

export default function SignUpPage() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const { isSignedIn, isLoaded } = useAuth()
  const { user } = useUser()
  const [processingCheckout, setProcessingCheckout] = useState(false)
  const [checkoutError, setCheckoutError] = useState<string | null>(null)
  
  const plan = searchParams.get('plan') || 'free'
  const interval = searchParams.get('interval') || 'monthly'
  const invitation = searchParams.get('invitation')
  const tenantId = searchParams.get('tenant')

  const plans = getAllPlans()
  const selectedPlan = plans.find(p => p.id === plan) || plans.find(p => p.id === 'free')!

  useEffect(() => {
    // Si el usuario ya está autenticado y la sesión está cargada, redirigir según el flujo
    if (isLoaded && isSignedIn && user) {
      handlePostSignUp()
    }
  }, [isLoaded, isSignedIn, user])

  const handlePostSignUp = async () => {
    // Para planes de pago, crear sesión de Stripe
    if (plan !== 'free' && plan !== 'enterprise') {
      setProcessingCheckout(true)
      setCheckoutError(null)
      
      // Esperar un momento para asegurar que la sesión de Clerk esté sincronizada
      await new Promise(resolve => setTimeout(resolve, 1000))
      
      try {
        // Include user email if available
        const userEmail = user?.emailAddresses?.[0]?.emailAddress
        
        const response = await fetch('/api/stripe/create-checkout-session', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            plan,
            interval,
            userEmail,
            successUrl: `${window.location.origin}/onboarding?session_id={CHECKOUT_SESSION_ID}`,
            cancelUrl: `${window.location.origin}/pricing`,
          }),
        })

        if (response.ok) {
          const { url } = await response.json()
          window.location.href = url
        } else {
          const errorData = await response.json().catch(() => null)
          console.error('Failed to create checkout session:', errorData)
          
          if (response.status === 401) {
            // Si falla por autenticación, intentar de nuevo después de un delay
            setTimeout(() => handlePostSignUp(), 2000)
          } else {
            setCheckoutError('No se pudo crear la sesión de pago. Por favor, continúa con el plan gratuito.')
            setProcessingCheckout(false)
            // Redirigir a onboarding después de 3 segundos
            setTimeout(() => router.push('/onboarding?plan=free'), 3000)
          }
        }
      } catch (error) {
        console.error('Error creating checkout session:', error)
        setCheckoutError('Error al procesar el pago. Continuando con plan gratuito.')
        setProcessingCheckout(false)
        setTimeout(() => router.push('/onboarding?plan=free'), 3000)
      }
    } else {
      // Para plan gratuito o invitación, ir directo a onboarding
      if (invitation && tenantId) {
        router.push(`/${tenantId}/dashboard`)
      } else {
        router.push('/onboarding')
      }
    }
  }

  // Mostrar estado de procesamiento
  if (processingCheckout) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Card className="max-w-md w-full mx-4">
          <CardHeader className="text-center">
            <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4 text-blue-600" />
            <CardTitle>Preparando tu suscripción</CardTitle>
            <CardDescription>
              Estamos configurando tu plan {selectedPlan.name}. Serás redirigido a Stripe en un momento...
            </CardDescription>
          </CardHeader>
        </Card>
      </div>
    )
  }

  // Mostrar error si ocurrió
  if (checkoutError) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Card className="max-w-md w-full mx-4">
          <CardHeader className="text-center">
            <AlertCircle className="h-8 w-8 text-yellow-600 mx-auto mb-4" />
            <CardTitle>Aviso</CardTitle>
            <CardDescription>{checkoutError}</CardDescription>
          </CardHeader>
        </Card>
      </div>
    )
  }

  const getPlanBadgeColor = (planId: string) => {
    switch (planId) {
      case 'pro':
        return 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-200'
      case 'enterprise':
        return 'bg-purple-100 text-purple-800 dark:bg-purple-900/50 dark:text-purple-200'
      default:
        return 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200'
    }
  }

  return (
    <div className="min-h-screen bg-background py-8">
      <div className="max-w-6xl mx-auto px-4">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-start">
          {/* Left side - Plan information */}
          <div className="space-y-6">
            <div className="text-center lg:text-left">
              <h1 className="text-3xl font-bold text-foreground mb-2">
                {invitation ? 'Únete a tu equipo' : 'Crea tu cuenta'}
              </h1>
              <p className="text-muted-foreground">
                {invitation 
                  ? 'Crea tu cuenta para unirte al equipo y comenzar a colaborar.'
                  : 'Regístrate para comenzar a usar Nexus Documents.'}
              </p>
            </div>

            {/* Selected Plan Info */}
            <Card className="bg-card text-card-foreground border shadow-sm">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-lg">Plan seleccionado</CardTitle>
                  <Badge className={getPlanBadgeColor(selectedPlan.id)}>
                    {selectedPlan.name}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  {selectedPlan.features.map((feature, index) => (
                    <div key={index} className="flex items-center space-x-2">
                      <CheckCircle className="h-4 w-4 text-green-600 dark:text-green-400 flex-shrink-0" />
                      <span className="text-sm">{feature}</span>
                    </div>
                  ))}
                </div>
                {selectedPlan.price > 0 && (
                  <div className="pt-4 border-t">
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Precio:</span>
                      <span className="font-semibold">
                        ${selectedPlan.price}/{interval === 'yearly' ? 'año' : 'mes'}
                      </span>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* What's next */}
            <Card className="bg-card text-card-foreground border shadow-sm">
              <CardHeader>
                <CardTitle className="text-lg">Proceso de registro</CardTitle>
              </CardHeader>
              <CardContent>
                <ol className="space-y-3 text-sm">
                  <li className="flex items-start">
                    <span className="bg-blue-600 dark:bg-blue-500 text-white rounded-full w-6 h-6 flex items-center justify-center text-xs mr-3 mt-0.5 flex-shrink-0">1</span>
                    <div>
                      <span className="font-medium">Crea tu cuenta</span>
                      <p className="text-muted-foreground">Regístrate con email o redes sociales</p>
                    </div>
                  </li>
                  {plan !== 'free' && (
                    <li className="flex items-start">
                      <span className="bg-gray-400 dark:bg-gray-600 text-white rounded-full w-6 h-6 flex items-center justify-center text-xs mr-3 mt-0.5 flex-shrink-0">2</span>
                      <div>
                        <span className="font-medium">Configura tu suscripción</span>
                        <p className="text-muted-foreground">Proceso de pago seguro con Stripe</p>
                      </div>
                    </li>
                  )}
                  <li className="flex items-start">
                    <span className="bg-gray-400 dark:bg-gray-600 text-white rounded-full w-6 h-6 flex items-center justify-center text-xs mr-3 mt-0.5 flex-shrink-0">
                      {plan !== 'free' ? '3' : '2'}
                    </span>
                    <div>
                      <span className="font-medium">Completa el onboarding</span>
                      <p className="text-muted-foreground">Configura tu empresa y preferencias</p>
                    </div>
                  </li>
                  <li className="flex items-start">
                    <span className="bg-gray-400 dark:bg-gray-600 text-white rounded-full w-6 h-6 flex items-center justify-center text-xs mr-3 mt-0.5 flex-shrink-0">
                      {plan !== 'free' ? '4' : '3'}
                    </span>
                    <div>
                      <span className="font-medium">¡Comienza a usar Nexus!</span>
                      <p className="text-muted-foreground">Accede a tu dashboard</p>
                    </div>
                  </li>
                </ol>
              </CardContent>
            </Card>

            {/* Change plan option */}
            <div className="text-center lg:text-left">
              <Button
                variant="outline"
                onClick={() => router.push('/pricing')}
                className="w-full lg:w-auto"
              >
                Cambiar plan
              </Button>
            </div>
          </div>

          {/* Right side - Clerk SignUp */}
          <div className="flex justify-center">
            <div className="w-full max-w-md">
              <SignUp 
                appearance={{
                  elements: {
                    rootBox: "w-full",
                    card: "shadow-none p-0",
                  }
                }}
                afterSignUpUrl={`/post-signup?plan=${plan}&interval=${interval}`}
                unsafeMetadata={{
                  plan: plan,
                  interval: interval,
                  invitation_code: invitation || undefined,
                  tenant_id: tenantId || undefined
                }}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}