'use client'

import { useEffect, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { SignUp } from '@clerk/nextjs'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { CheckCircle, Loader2, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'

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

export function SignUpWithCheckout() {
  const searchParams = useSearchParams()
  const sessionId = searchParams.get('session_id')
  const email = searchParams.get('email')
  const plan = searchParams.get('plan')
  const invitation = searchParams.get('invitation')
  const tenantId = searchParams.get('tenant')

  const [checkoutData, setCheckoutData] = useState<CheckoutSession | null>(null)
  const [isLoading, setIsLoading] = useState(!!sessionId)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (sessionId) {
      const fetchCheckoutSession = async () => {
        try {
          const response = await fetch(`/api/stripe/checkout-session/${sessionId}`)
          
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
    }
  }, [sessionId])

  const getPlanDisplayName = (planId: string) => {
    const plans: Record<string, { name: string; color: string }> = {
      'free': { name: 'Free Plan', color: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200' },
      'pro': { name: 'Pro Plan', color: 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-200' },
      'enterprise': { name: 'Enterprise Plan', color: 'bg-purple-100 text-purple-800 dark:bg-purple-900/50 dark:text-purple-200' },
    }
    return plans[planId] || { name: planId, color: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200' }
  }

  const formatAmount = (amount: number, currency: string) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: currency.toUpperCase(),
    }).format(amount / 100)
  }

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center space-y-4">
          <Loader2 className="h-8 w-8 animate-spin mx-auto text-blue-600 dark:text-blue-400" />
          <p className="text-muted-foreground">Verificando información de pago...</p>
        </div>
      </div>
    )
  }

  if (error && sessionId) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Card className="max-w-md w-full mx-4 bg-card text-card-foreground border shadow-sm">
          <CardHeader className="text-center">
            <AlertCircle className="h-12 w-12 text-red-500 mx-auto mb-4" />
            <CardTitle className="text-red-600 dark:text-red-400">Error</CardTitle>
            <CardDescription>
              No se pudo verificar tu información de pago. Por favor contacta a soporte.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button 
              onClick={() => window.location.href = '/pricing'} 
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
    <div className="min-h-screen bg-background py-8">
      <div className="max-w-6xl mx-auto px-4">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-start">
          {/* Left side - Plan information */}
          <div className="space-y-6">
            <div className="text-center lg:text-left">
              <h1 className="text-3xl font-bold text-foreground mb-2">
                {invitation ? 'Join Your Team' : 'Completa tu registro'}
              </h1>
              <p className="text-muted-foreground">
                {invitation 
                  ? 'Create your account to join the team and start collaborating.'
                  : checkoutData 
                    ? 'Ya procesamos tu pago. Solo necesitamos algunos datos más para configurar tu cuenta.'
                    : 'Create your account to get started with Nexus.'}
              </p>
            </div>

            {/* Payment confirmation */}
            {checkoutData && (
              <Card className="bg-card text-card-foreground border shadow-sm">
                <CardHeader>
                  <div className="flex items-center space-x-2">
                    <CheckCircle className="h-5 w-5 text-green-600 dark:text-green-400" />
                    <CardTitle className="text-lg text-green-600 dark:text-green-400">Pago Confirmado</CardTitle>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Plan:</span>
                    <Badge className={getPlanDisplayName(checkoutData.plan_id).color}>
                      {getPlanDisplayName(checkoutData.plan_id).name}
                    </Badge>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Monto:</span>
                    <span className="font-semibold">
                      {formatAmount(checkoutData.amount_total, checkoutData.currency)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Email de facturación:</span>
                    <span className="text-sm">{checkoutData.customer_email}</span>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Team invitation info */}
            {invitation && tenantId && (
              <Card className="bg-card text-card-foreground border shadow-sm">
                <CardHeader>
                  <div className="flex items-center space-x-2">
                    <CheckCircle className="h-5 w-5 text-green-600 dark:text-green-400" />
                    <CardTitle className="text-lg">Team Invitation</CardTitle>
                  </div>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground">
                    You're joining an existing team. After registration, you'll have access to all team resources.
                  </p>
                </CardContent>
              </Card>
            )}

            {/* Free plan info */}
            {plan === 'free' && !invitation && (
              <Card className="bg-card text-card-foreground border shadow-sm">
                <CardHeader>
                  <CardTitle className="text-lg">Plan Gratuito</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    <div className="flex items-center space-x-2">
                      <CheckCircle className="h-4 w-4 text-green-600 dark:text-green-400" />
                      <span className="text-sm">Hasta 100 documentos</span>
                    </div>
                    <div className="flex items-center space-x-2">
                      <CheckCircle className="h-4 w-4 text-green-600 dark:text-green-400" />
                      <span className="text-sm">1 GB de almacenamiento</span>
                    </div>
                    <div className="flex items-center space-x-2">
                      <CheckCircle className="h-4 w-4 text-green-600 dark:text-green-400" />
                      <span className="text-sm">Búsqueda básica</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* What's next */}
            <Card className="bg-card text-card-foreground border shadow-sm">
              <CardHeader>
                <CardTitle className="text-lg">¿Qué sigue?</CardTitle>
              </CardHeader>
              <CardContent>
                <ol className="space-y-2 text-sm text-muted-foreground">
                  <li className="flex items-start">
                    <span className="bg-blue-600 dark:bg-blue-500 text-white rounded-full w-5 h-5 flex items-center justify-center text-xs mr-3 mt-0.5 flex-shrink-0">1</span>
                    Completa tu registro en el formulario de la derecha
                  </li>
                  <li className="flex items-start">
                    <span className="bg-blue-600 dark:bg-blue-500 text-white rounded-full w-5 h-5 flex items-center justify-center text-xs mr-3 mt-0.5 flex-shrink-0">2</span>
                    Configura los datos de tu empresa
                  </li>
                  <li className="flex items-start">
                    <span className="bg-blue-600 dark:bg-blue-500 text-white rounded-full w-5 h-5 flex items-center justify-center text-xs mr-3 mt-0.5 flex-shrink-0">3</span>
                    ¡Empieza a usar Nexus inmediatamente!
                  </li>
                </ol>
              </CardContent>
            </Card>
          </div>

          {/* Right side - Clerk SignUp */}
          <div className="flex justify-center">
            <div className="w-full max-w-md">
              <SignUp 
                redirectUrl={invitation && tenantId ? `/${tenantId}/dashboard` : "/onboarding"}
                afterSignUpUrl={invitation && tenantId ? `/${tenantId}/dashboard` : "/onboarding"}
                initialValues={
                  checkoutData?.customer_email || email 
                    ? { emailAddress: checkoutData?.customer_email || email || '' }
                    : undefined
                }
                unsafeMetadata={{
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