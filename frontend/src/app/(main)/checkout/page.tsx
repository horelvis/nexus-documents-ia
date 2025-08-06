'use client'

import { Suspense } from 'react'
import { useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useAuth } from '@clerk/nextjs'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Loader2, AlertCircle } from 'lucide-react'
import { useApiClient } from '@/lib/api-client'
import { getPlan } from '@/lib/stripe-plans'

function CheckoutContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { isLoaded, isSignedIn } = useAuth()
  const apiClient = useApiClient()
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sessionCreated, setSessionCreated] = useState(false)
  
  const planId = searchParams.get('plan')
  const interval = searchParams.get('interval') || 'month'

  const createCheckoutSession = async () => {
    if (!planId || sessionCreated) return

    setIsLoading(true)
    setError(null)
    setSessionCreated(true) // Prevent multiple calls

    try {
      const response = await apiClient.post('/stripe/create-checkout-session', {
        priceId: planId,
        successUrl: `${window.location.origin}/checkout/success`,
        cancelUrl: `${window.location.origin}/pricing`
      })

      if (response.data?.url) {
        window.location.href = response.data.url
      } else {
        throw new Error('No checkout URL received')
      }
    } catch (err: any) {
      console.error('Error creating checkout session:', err)
      setError(err.response?.data?.detail || 'Failed to create checkout session')
      setSessionCreated(false) // Allow retry on error
      setIsLoading(false)
    }
  }

  useEffect(() => {
    if (!isLoaded) return

    if (!isSignedIn) {
      router.push('/sign-in')
      return
    }

    if (planId) {
      createCheckoutSession()
    } else {
      router.push('/pricing')
    }
  }, [isLoaded, isSignedIn, planId])

  const plan = planId ? getPlan(planId) : null

  if (!isLoaded || isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Card className="w-full max-w-md">
          <CardContent className="flex flex-col items-center justify-center py-10">
            <Loader2 className="h-8 w-8 animate-spin mb-4" />
            <p className="text-sm text-muted-foreground">
              {isLoading ? 'Redirecting to checkout...' : 'Loading...'}
            </p>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertCircle className="h-5 w-5 text-destructive" />
              Checkout Error
            </CardTitle>
            <CardDescription>{error}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex gap-2">
              <Button 
                onClick={() => router.push('/pricing')}
                variant="outline"
              >
                Back to Pricing
              </Button>
              <Button 
                onClick={() => {
                  setSessionCreated(false)
                  createCheckoutSession()
                }}
              >
                Try Again
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  return null
}

export default function CheckoutPage() {
  return (
    <Suspense fallback={
      <div className="flex items-center justify-center min-h-screen">
        <Card className="w-full max-w-md">
          <CardContent className="flex flex-col items-center justify-center py-10">
            <Loader2 className="h-8 w-8 animate-spin mb-4" />
            <p className="text-sm text-muted-foreground">Loading checkout...</p>
          </CardContent>
        </Card>
      </div>
    }>
      <CheckoutContent />
    </Suspense>
  )
}