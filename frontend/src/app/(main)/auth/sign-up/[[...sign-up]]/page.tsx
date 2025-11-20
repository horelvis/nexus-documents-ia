'use client'

import { useEffect, useState, Suspense } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import { SignUp, useAuth, useUser } from '@clerk/nextjs'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { CheckCircle, Loader2, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { STRIPE_PLANS, type PlanId } from '@/lib/stripe-plans'

function SignUpContent() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const { isSignedIn, isLoaded } = useAuth()
  const { user } = useUser()
  const [processingCheckout, setProcessingCheckout] = useState(false)
  const [checkoutError, setCheckoutError] = useState<string | null>(null)
  
  const rawPlan = (searchParams.get('plan') || '').toLowerCase()
  const planId = (rawPlan in STRIPE_PLANS ? rawPlan : 'free') as PlanId
  const rawInterval = (searchParams.get('interval') || 'month').toLowerCase()
  const interval = rawInterval === 'yearly'
    ? 'year'
    : rawInterval === 'monthly'
      ? 'month'
      : rawInterval
  const invitation = searchParams.get('invitation')
  const tenantId = searchParams.get('tenant')

  const selectedPlan = STRIPE_PLANS[planId]

    useEffect(() => {
      // Si el usuario ya está autenticado y la sesión está cargada, redirigir al dashboard
      if (isLoaded && isSignedIn && user) {
        router.push('/dashboard')
        return
      }

      // Validar que exista un plan o una invitación
      const planParam = searchParams.get('plan')
      if (!planParam && !invitation) {
        router.replace('/pricing')
      }
    }, [isLoaded, isSignedIn, user, router, searchParams, invitation])

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

  

              {/* Selected Plan Info - Now just showing the default/chosen plan */}

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

                          ${selectedPlan.price}/{interval === 'year' ? 'año' : 'mes'}

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

                    <li className="flex items-start">

                      <span className="bg-gray-400 dark:bg-gray-600 text-white rounded-full w-6 h-6 flex items-center justify-center text-xs mr-3 mt-0.5 flex-shrink-0">2</span>

                      <div>

                        <span className="font-medium">Completa el onboarding</span>

                        <p className="text-muted-foreground">Configura tu empresa y preferencias</p>

                      </div>

                    </li>

                    <li className="flex items-start">

                      <span className="bg-gray-400 dark:bg-gray-600 text-white rounded-full w-6 h-6 flex items-center justify-center text-xs mr-3 mt-0.5 flex-shrink-0">3</span>

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

                                  afterSignUpUrl={'/dashboard'}

                                                    unsafeMetadata={{

                                                      invitation_code: invitation || undefined,

                                                      tenant_id: tenantId || undefined,

                                                      selected_plan: planId,

                                                      selected_interval: interval

                                                    }}

                                />

              </div>

            </div>

          </div>

        </div>

      </div>

    )

  }

export default function SignUpPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    }>
      <SignUpContent />
    </Suspense>
  )
}
