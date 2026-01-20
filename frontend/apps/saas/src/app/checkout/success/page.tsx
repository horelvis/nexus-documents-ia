'use client'

import { useEffect, useState, Suspense } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import { useAuth } from '@clerk/nextjs'
import { CheckCircle, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { UnifiedLoader } from '@/components/ui/unified-loader'

interface CheckoutSession {
  session_id: string
  customer_id: string
  customer_email: string
  subscription_id: string
  plan_id: string
  payment_status: string
  amount_total: number
  currency: string
}

function CheckoutSuccessContent() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const { isSignedIn, isLoaded } = useAuth()
  const sessionId = searchParams.get('session_id')
  
  const [checkoutData, setCheckoutData] = useState<CheckoutSession | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!sessionId) {
      setError('No session ID provided')
      setIsLoading(false)
      return
    }

    const fetchCheckoutSession = async () => {
      try {
        const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
        const response = await fetch(`${API_BASE}/api/v1/stripe/checkout-session/${sessionId}`)
        
        if (!response.ok) {
          throw new Error('Failed to fetch checkout session')
        }

        const data = await response.json()
        setCheckoutData(data)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error')
      } finally {
        setIsLoading(false)
      }
    }

    fetchCheckoutSession()
  }, [sessionId])

  const handleContinueToSignup = () => {
    if (checkoutData) {
      // Always check isLoaded before making decisions based on isSignedIn
      if (!isLoaded) {
        // Clerk not ready, wait a bit and retry
        setTimeout(handleContinueToSignup, 500)
        return
      }

      // Check if user is already signed in
      if (isSignedIn) {
        // User is already authenticated, go to onboarding or dashboard
        // The onboarding will detect if it's already complete and redirect to dashboard
        router.push('/onboarding-simple?plan=' + checkoutData.plan_id)
      } else {
        // User needs to sign up with the session data
        router.push(`/auth/sign-up?session_id=${checkoutData.session_id}&plan=${checkoutData.plan_id}`)
      }
    }
  }

  const formatAmount = (amount: number, currency: string) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: currency.toUpperCase(),
    }).format(amount / 100)
  }

  const getPlanDisplayName = (planId: string) => {
    const plans: Record<string, string> = {
      'pro': 'Pro Plan',
      'enterprise': 'Enterprise Plan',
    }
    return plans[planId] || planId
  }

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <UnifiedLoader 
          variant="initial"
          size="lg"
          text="Verificando tu pago..."
          showLogo={true}
        />
      </div>
    )
  }

  if (error || !checkoutData) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Card className="max-w-md w-full mx-4">
          <CardHeader className="text-center">
            <AlertCircle className="h-12 w-12 text-red-500 mx-auto mb-4" />
            <CardTitle className="text-red-600">Error</CardTitle>
            <CardDescription>
              {error || 'No se pudo verificar tu pago. Por favor contacta a soporte.'}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button 
              onClick={() => router.push('/pricing')} 
              className="w-full"
              variant="outline"
            >
              Volver a Pricing
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="max-w-2xl w-full mx-4 space-y-8">
        {/* Success Message */}
        <Card className="text-center">
          <CardHeader>
            <div className="w-20 h-20 bg-green-100 dark:bg-green-900 rounded-full flex items-center justify-center mx-auto mb-4">
              <CheckCircle className="h-12 w-12 text-green-600 dark:text-green-400" />
            </div>
            <CardTitle className="text-3xl text-green-600 dark:text-green-400 mb-2">
              ¡Pago Exitoso!
            </CardTitle>
            <CardDescription className="text-lg">
              Tu suscripción ha sido activada correctamente
            </CardDescription>
          </CardHeader>
          
          <CardContent className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-left">
              <div className="space-y-2">
                <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Plan</p>
                <Badge variant="secondary" className="text-sm">
                  {getPlanDisplayName(checkoutData.plan_id)}
                </Badge>
              </div>
              
              <div className="space-y-2">
                <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
                  {checkoutData.amount_total === 0 ? 'Precio del Plan' : 'Monto'}
                </p>
                <p className="text-lg font-semibold">
                  {formatAmount(checkoutData.amount_total, checkoutData.currency)}
                  {checkoutData.amount_total === 0 && (
                    <span className="text-sm font-normal text-green-600 dark:text-green-400 ml-2">
                      (14 días gratis)
                    </span>
                  )}
                </p>
              </div>
              
              <div className="space-y-2">
                <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Email</p>
                <p className="text-sm text-gray-700 dark:text-gray-300">
                  {checkoutData.customer_email}
                </p>
              </div>
              
              <div className="space-y-2">
                <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Estado</p>
                <Badge variant="default" className="bg-green-600">
                  Pagado
                </Badge>
              </div>
            </div>

            <div className="pt-6 border-t border-gray-200 dark:border-gray-700">
              <h3 className="text-lg font-semibold mb-3">¿Qué sigue?</h3>
              {checkoutData.amount_total === 0 && (
                <div className="bg-green-50 dark:bg-green-900/20 p-3 rounded-lg mb-4">
                  <p className="text-sm text-green-700 dark:text-green-300">
                    🎉 <strong>¡Tienes 14 días gratis!</strong> Tu primer cargo será el {new Date(Date.now() + 14 * 24 * 60 * 60 * 1000).toLocaleDateString('es-ES')}
                  </p>
                </div>
              )}
              <ol className="text-left space-y-2 text-sm text-gray-600 dark:text-gray-300">
                {isSignedIn ? (
                  <>
                    <li className="flex items-start">
                      <span className="bg-purple-600 text-white rounded-full w-5 h-5 flex items-center justify-center text-xs mr-3 mt-0.5">1</span>
                      Tu suscripción está activa y lista
                    </li>
                    <li className="flex items-start">
                      <span className="bg-purple-600 text-white rounded-full w-5 h-5 flex items-center justify-center text-xs mr-3 mt-0.5">2</span>
                      Accede a todas las funcionalidades premium
                    </li>
                    <li className="flex items-start">
                      <span className="bg-purple-600 text-white rounded-full w-5 h-5 flex items-center justify-center text-xs mr-3 mt-0.5">3</span>
                      ¡Comienza a trabajar con tus documentos!
                    </li>
                  </>
                ) : (
                  <>
                    <li className="flex items-start">
                      <span className="bg-purple-600 text-white rounded-full w-5 h-5 flex items-center justify-center text-xs mr-3 mt-0.5">1</span>
                      Completa tu registro con los datos de tu empresa
                    </li>
                    <li className="flex items-start">
                      <span className="bg-purple-600 text-white rounded-full w-5 h-5 flex items-center justify-center text-xs mr-3 mt-0.5">2</span>
                      Configura tu workspace y agrega tu equipo
                    </li>
                    <li className="flex items-start">
                      <span className="bg-purple-600 text-white rounded-full w-5 h-5 flex items-center justify-center text-xs mr-3 mt-0.5">3</span>
                      ¡Empieza a usar todas las funcionalidades premium!
                    </li>
                  </>
                )}
              </ol>
            </div>
          </CardContent>
        </Card>

        {/* CTA Button */}
        <div className="text-center">
          <Button 
            onClick={handleContinueToSignup}
            size="lg"
            className="bg-gradient-to-r from-purple-500 to-purple-700 hover:from-purple-600 hover:to-purple-800 text-white px-8 py-3"
          >
            {isSignedIn ? 'Ir al Dashboard' : 'Completar Registro'}
          </Button>
        </div>

        {/* Help Text */}
        <div className="text-center text-sm text-gray-500 dark:text-gray-400">
          <p>¿Necesitas ayuda? <a href="mailto:support@nexus.com" className="text-blue-600 hover:underline">Contacta a soporte</a></p>
        </div>
      </div>
    </div>
  )
}

// Force dynamic rendering to avoid static generation issues with useSearchParams
export const dynamic = 'force-dynamic'

export default function CheckoutSuccessPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center">
        <UnifiedLoader 
          variant="initial"
          size="lg"
          text="Cargando..."
          showLogo={true}
        />
      </div>
    }>
      <CheckoutSuccessContent />
    </Suspense>
  )
}