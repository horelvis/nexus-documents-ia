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
    <div className="min-h-screen bg-background flex items-center justify-center py-8">
      <div className="w-full max-w-md px-4">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-foreground mb-2">
            {invitation ? 'Únete a tu equipo' : 'Crea tu cuenta'}
          </h1>
          <p className="text-muted-foreground">
            {invitation 
              ? 'Crea tu cuenta para unirte al equipo y comenzar a colaborar.'
              : checkoutData 
                ? 'Ya procesamos tu pago. Solo necesitamos algunos datos más.'
                : plan === 'free'
                  ? 'Comienza tu prueba gratis de 14 días'
                  : 'Crea tu cuenta para comenzar con Nexus'}
          </p>
        </div>

        {/* Plan info badge */}
        {plan === 'free' && !invitation && (
          <div className="mb-6 text-center">
            <Badge className="bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-200 px-4 py-2">
              <CheckCircle className="h-4 w-4 mr-2" />
              14 días gratis • Sin tarjeta de crédito
            </Badge>
          </div>
        )}

        {plan === 'pro' && !invitation && (
          <div className="mb-6 text-center">
            <Badge className="bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-200 px-4 py-2">
              Plan Pro • $29/mes
            </Badge>
          </div>
        )}

        {plan === 'enterprise' && !invitation && (
          <div className="mb-6 text-center">
            <Badge className="bg-purple-100 text-purple-800 dark:bg-purple-900/50 dark:text-purple-200 px-4 py-2">
              Plan Enterprise • $99/mes
            </Badge>
          </div>
        )}

        {/* Clerk SignUp Component */}
        <div className="mb-8">
          <SignUp 
            appearance={{
              elements: {
                formButtonPrimary: 
                  'bg-purple-600 hover:bg-purple-700 text-white shadow-sm',
                formButtonSecondary:
                  'bg-gray-200 hover:bg-gray-300 text-gray-900 dark:bg-gray-700 dark:hover:bg-gray-600 dark:text-gray-100',
                socialButtonsBlockButton:
                  'bg-white hover:bg-gray-50 text-gray-900 border border-gray-300 dark:bg-gray-800 dark:hover:bg-gray-700 dark:text-gray-100 dark:border-gray-600',
                socialButtonsBlockButtonText:
                  'text-gray-900 dark:text-gray-100 font-medium',
                formFieldInput:
                  'bg-white dark:bg-gray-800 border-gray-300 dark:border-gray-600',
                footerActionLink:
                  'text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300',
                footerActionText:
                  'text-gray-600 dark:text-gray-400',
                identityPreviewText:
                  'text-gray-900 dark:text-gray-100',
                identityPreviewEditButtonIcon:
                  'text-gray-600 dark:text-gray-400',
                formHeaderTitle:
                  'text-gray-900 dark:text-gray-100',
                formHeaderSubtitle:
                  'text-gray-600 dark:text-gray-400',
                formFieldLabel:
                  'text-gray-700 dark:text-gray-300',
                formFieldSuccessText:
                  'text-green-600 dark:text-green-400',
                formFieldErrorText:
                  'text-red-600 dark:text-red-400',
                phoneInputBox:
                  'bg-white dark:bg-gray-800 border-gray-300 dark:border-gray-600',
                card: 'shadow-sm',
                footer: 'text-gray-600 dark:text-gray-400',
                footerAction: 'text-gray-600 dark:text-gray-400',
                footerPages: 'text-gray-600 dark:text-gray-400',
              },
              variables: {
                colorPrimary: '#2563eb',
                colorTextOnPrimaryBackground: '#ffffff',
                colorBackground: 'transparent',
                colorInputBackground: 'transparent',
                colorInputText: 'inherit',
                borderRadius: '0.5rem',
              }
            }}
            redirectUrl={
              invitation && tenantId 
                ? `/${tenantId}/dashboard` 
                : plan && plan !== 'free'
                  ? `/checkout?plan=${plan}`
                  : plan === 'free'
                    ? '/onboarding-simple'
                    : "/pricing"
            }
            afterSignUpUrl={
              invitation && tenantId 
                ? `/${tenantId}/dashboard` 
                : plan && plan !== 'free'
                  ? `/checkout?plan=${plan}`
                  : plan === 'free'
                    ? '/onboarding-simple'
                    : "/pricing"
            }
            initialValues={
              checkoutData?.customer_email || email 
                ? { emailAddress: checkoutData?.customer_email || email || '' }
                : undefined
            }
            unsafeMetadata={{
              invitation_code: invitation || undefined,
              tenant_id: tenantId || undefined,
              selected_plan: plan || undefined
            }}
          />
        </div>

        {/* Additional info for free trial */}
        {plan === 'free' && !invitation && (
          <div className="text-center space-y-4">
            <p className="text-sm text-muted-foreground">
              Al registrarte obtienes:
            </p>
            <div className="flex flex-wrap justify-center gap-4 text-sm">
              <div className="flex items-center">
                <CheckCircle className="h-4 w-4 text-green-600 dark:text-green-400 mr-1" />
                <span>Documentos ilimitados</span>
              </div>
              <div className="flex items-center">
                <CheckCircle className="h-4 w-4 text-green-600 dark:text-green-400 mr-1" />
                <span>100 GB almacenamiento</span>
              </div>
              <div className="flex items-center">
                <CheckCircle className="h-4 w-4 text-green-600 dark:text-green-400 mr-1" />
                <span>IA avanzada</span>
              </div>
            </div>
          </div>
        )}

        {/* Payment confirmation info */}
        {checkoutData && (
          <div className="text-center mt-6">
            <div className="inline-flex items-center text-green-600 dark:text-green-400 mb-2">
              <CheckCircle className="h-5 w-5 mr-2" />
              <span className="font-semibold">Pago confirmado</span>
            </div>
            <p className="text-sm text-muted-foreground">
              {getPlanDisplayName(checkoutData.plan_id).name} • {formatAmount(checkoutData.amount_total, checkoutData.currency)}
            </p>
          </div>
        )}

        {/* Back to pricing link */}
        <div className="text-center mt-8">
          <Button
            variant="link"
            onClick={() => window.location.href = '/pricing'}
            className="text-sm"
          >
            ← Volver a planes
          </Button>
        </div>
      </div>
    </div>
  )
}