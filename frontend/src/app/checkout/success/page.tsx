'use client'

import { useEffect, useState } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import { CheckCircle, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { UnifiedLoader } from '@/components/ui/unified-loader'

// Skip static generation for this page since it uses useSearchParams
export const dynamic = 'force-dynamic'

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

export default function CheckoutSuccessPage() {
  const searchParams = useSearchParams()
  const router = useRouter()
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
      // Redirect to sign-up with session data
      // The backend will create the user with the subscription when they sign up
      router.push(`/auth/sign-up?session_id=${checkoutData.session_id}&plan=${checkoutData.plan_id}`)
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
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800">
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
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800 flex items-center justify-center">
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
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800 flex items-center justify-center">
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
                <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Monto</p>
                <p className="text-lg font-semibold">
                  {formatAmount(checkoutData.amount_total, checkoutData.currency)}
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
              <ol className="text-left space-y-2 text-sm text-gray-600 dark:text-gray-300">
                <li className="flex items-start">
                  <span className="bg-blue-600 text-white rounded-full w-5 h-5 flex items-center justify-center text-xs mr-3 mt-0.5">1</span>
                  Completa tu registro con los datos de tu empresa
                </li>
                <li className="flex items-start">
                  <span className="bg-blue-600 text-white rounded-full w-5 h-5 flex items-center justify-center text-xs mr-3 mt-0.5">2</span>
                  Configura tu workspace y agrega tu equipo
                </li>
                <li className="flex items-start">
                  <span className="bg-blue-600 text-white rounded-full w-5 h-5 flex items-center justify-center text-xs mr-3 mt-0.5">3</span>
                  ¡Empieza a usar todas las funcionalidades premium!
                </li>
              </ol>
            </div>
          </CardContent>
        </Card>

        {/* CTA Button */}
        <div className="text-center">
          <Button 
            onClick={handleContinueToSignup}
            size="lg"
            className="bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 text-white px-8 py-3"
          >
            Completar Registro
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