'use client'

import { Suspense, useEffect, useState } from 'react'
import { useUserContext } from '@/contexts/user-context'
import { useRouter, useSearchParams } from 'next/navigation'
import { NewUserOnboarding } from '@/components/auth/onboarding'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { CheckCircle, Loader2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'

function OnboardingContent() {
  const { backendUser, isClerkLoaded, isSignedIn } = useUserContext()
  const router = useRouter()
  const searchParams = useSearchParams()
  const sessionId = searchParams.get('session_id')
  
  const [isVerifyingPayment, setIsVerifyingPayment] = useState(!!sessionId)
  const [paymentVerified, setPaymentVerified] = useState(false)
  const [subscriptionPlan, setSubscriptionPlan] = useState<string | null>(null)

  useEffect(() => {
    // Verify Stripe payment if session_id is present
    if (sessionId) {
      verifyStripePayment(sessionId)
    }
  }, [sessionId])

  // Redirect if not authenticated
  useEffect(() => {
    if (isClerkLoaded && !isSignedIn) {
      router.push('/auth/sign-in')
    }
  }, [isClerkLoaded, isSignedIn, router])

  // If already completed onboarding, redirect to dashboard
  useEffect(() => {
    if (backendUser?.onboarding_completed) {
      router.push(`/${backendUser.tenant_id}/dashboard`)
    }
  }, [backendUser, router])

  const verifyStripePayment = async (sessionId: string) => {
    try {
      const response = await fetch(`/api/stripe/verify-session/${sessionId}`)
      
      if (response.ok) {
        const data = await response.json()
        setPaymentVerified(true)
        setSubscriptionPlan(data.plan)
        
        // Update user subscription in backend
        await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/stripe/webhook`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            type: 'checkout.session.completed',
            data: {
              object: data
            }
          }),
        })
      }
    } catch (error) {
      console.error('Error verifying payment:', error)
    } finally {
      setIsVerifyingPayment(false)
    }
  }

  const handleComplete = (tenantId?: string) => {
    if (tenantId) {
      router.push(`/${tenantId}/dashboard`)
    } else {
      router.push('/dashboard')
    }
  }

  // Show loading while verifying payment
  if (isVerifyingPayment) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Card className="max-w-md w-full mx-4">
          <CardHeader className="text-center">
            <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4 text-blue-600" />
            <CardTitle>Verificando tu suscripción</CardTitle>
            <CardDescription>
              Estamos confirmando tu pago con Stripe...
            </CardDescription>
          </CardHeader>
        </Card>
      </div>
    )
  }

  // Show payment confirmation before onboarding
  if (paymentVerified && !backendUser?.onboarding_completed) {
    return (
      <div className="min-h-screen bg-background">
        <div className="max-w-4xl mx-auto px-4 py-8">
          {/* Payment Success Card */}
          <Card className="mb-8 bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800">
            <CardHeader>
              <div className="flex items-center space-x-2">
                <CheckCircle className="h-6 w-6 text-green-600 dark:text-green-400" />
                <CardTitle className="text-green-800 dark:text-green-200">
                  ¡Pago confirmado!
                </CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-between">
                <span>Tu suscripción está activa:</span>
                <Badge variant="default" className="bg-green-600">
                  Plan {subscriptionPlan}
                </Badge>
              </div>
            </CardContent>
          </Card>

          {/* Onboarding Component */}
          <NewUserOnboarding onComplete={handleComplete} />
        </div>
      </div>
    )
  }

  // Default onboarding for free plan or already verified users
  return <NewUserOnboarding onComplete={handleComplete} />
}

export default function OnboardingPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    }>
      <OnboardingContent />
    </Suspense>
  )
}