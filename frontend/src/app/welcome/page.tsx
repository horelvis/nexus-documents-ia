'use client'

import { ModernOnboarding } from "@/components/auth"
import { ExpressOnboarding } from "@/components/auth/express-onboarding"
import { useRouter, useSearchParams } from "next/navigation"
import { Suspense, useEffect, useState } from "react"

interface CheckoutData {
  plan_id: string
  customer_email: string
  amount_total: number
  currency: string
}

function WelcomeContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  
  const [checkoutData, setCheckoutData] = useState<CheckoutData | null>(null)
  const [isLoadingCheckout, setIsLoadingCheckout] = useState(false)
  
  // Check if user comes from Stripe checkout
  const sessionId = searchParams.get('session_id')
  const fromCheckout = !!sessionId
  
  useEffect(() => {
    if (sessionId) {
      const fetchCheckoutData = async () => {
        try {
          setIsLoadingCheckout(true)
          const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
          const response = await fetch(`${API_BASE}/api/v1/stripe/checkout-session/${sessionId}`)
          
          if (response.ok) {
            const data = await response.json()
            setCheckoutData({
              plan_id: data.plan_id,
              customer_email: data.customer_email,
              amount_total: data.amount_total,
              currency: data.currency,
            })
          }
        } catch (error) {
          console.error('Error fetching checkout data:', error)
        } finally {
          setIsLoadingCheckout(false)
        }
      }

      fetchCheckoutData()
    }
  }, [sessionId])
  
  const handleOnboardingComplete = (tenantId?: string) => {
    // Default tenant or use provided one
    const finalTenantId = tenantId || 'default'
    router.push(`/${finalTenantId}/dashboard`)
  }

  // Show loading while fetching checkout data
  if (isLoadingCheckout) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800 flex items-center justify-center">
        <div className="text-center space-y-4">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="text-lg font-medium text-gray-600 dark:text-gray-300">
            Verificando tu información...
          </p>
        </div>
      </div>
    )
  }

  // Use ExpressOnboarding for paid users
  if (fromCheckout && checkoutData) {
    return <ExpressOnboarding checkoutData={checkoutData} onComplete={handleOnboardingComplete} />
  }

  // Use regular onboarding for free users
  return <ModernOnboarding onComplete={handleOnboardingComplete} />
}

export default function WelcomePage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    }>
      <WelcomeContent />
    </Suspense>
  )
}