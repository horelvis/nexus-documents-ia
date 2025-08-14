'use client'

import React, { useEffect, useState } from 'react'
import { Check, Star, Zap, Crown, CheckCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { getAllPlans, formatPrice, calculateYearlyDiscount, type Plan } from '@/lib/stripe-plans'
import { useRouter, useParams } from 'next/navigation'
import { useApiClient } from '@/lib/api-client'
import { Loader2 } from 'lucide-react'
import { useUserContext } from '@/contexts/user-context'

export default function TenantPlansPage() {
  const plans = getAllPlans()
  const router = useRouter()
  const params = useParams()
  const apiClient = useApiClient()
  const { backendUser } = useUserContext()
  const [loadingPlan, setLoadingPlan] = useState<string | null>(null)
  const [currentSubscription, setCurrentSubscription] = useState<any>(null)
  const [isLoading, setIsLoading] = useState(true)

  // Check current subscription status - Single call optimization
  useEffect(() => {
    const checkSubscription = async () => {
      try {
        // Check if we already have subscription info from user context
        if (backendUser?.subscription_plan && backendUser?.subscription_status) {
          setCurrentSubscription({
            plan_id: backendUser.subscription_plan,
            status: backendUser.subscription_status
          })
          setIsLoading(false)
          return
        }

        // Only make API call if we don't have subscription info
        const response = await apiClient.get('/stripe/subscription')
        if (!response.error && response.data) {
          setCurrentSubscription(response.data)
        }
      } catch (error) {
        console.error('Error checking subscription:', error)
      } finally {
        setIsLoading(false)
      }
    }

    checkSubscription()
  }, [apiClient, backendUser])

  const handlePlanSelection = async (plan: Plan, isYearly: boolean = false) => {
    setLoadingPlan(plan.id)
    
    try {
      if (plan.id === 'free') {
        // Free plan - no checkout needed
        router.push('/dashboard')
        return
      }

      if (plan.id === 'enterprise') {
        // Open contact form or redirect to sales
        window.location.href = 'mailto:sales@nexusdocs360.com?subject=Enterprise%20Plan%20-%20Solicitud%20de%20Información'
        return
      }

      // For paid plans, create checkout session
      const interval = isYearly ? 'year' : 'month'
      const response = await apiClient.post('/stripe/create-checkout-session', {
        planId: plan.id,
        interval,
        success_url: `${window.location.origin}/checkout/success?session_id={CHECKOUT_SESSION_ID}`,
        cancel_url: window.location.pathname
      })

      if (response.error) {
        throw new Error(response.error)
      }

      // Redirect to Stripe Checkout
      if (response.data?.url) {
        window.location.href = response.data.url
      }
    } catch (error) {
      console.error('Error creating checkout session:', error)
    } finally {
      setLoadingPlan(null)
    }
  }

  const getPlanIcon = (planId: string) => {
    switch (planId) {
      case 'enterprise':
        return <Crown className="w-4 h-4" />
      case 'pro':
        return <Zap className="w-4 h-4" />
      default:
        return <Star className="w-4 h-4" />
    }
  }

  // Show loading state while checking subscription
  if (isLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center space-y-4">
          <Loader2 className="h-8 w-8 animate-spin mx-auto text-purple-600" />
          <p className="text-muted-foreground">Verificando tu suscripción...</p>
        </div>
      </div>
    )
  }

  // Redirect automatically to dashboard if user already has an active subscription  
  useEffect(() => {
    if (!isLoading && currentSubscription && currentSubscription.plan_id !== 'free' && currentSubscription.status === 'active') {
      // User has active subscription, redirect to dashboard immediately
      router.replace(`/${params.tenantId}/dashboard`)
    }
  }, [isLoading, currentSubscription, params.tenantId, router])

  // Show loading during redirect
  if (currentSubscription && currentSubscription.plan_id !== 'free' && currentSubscription.status === 'active') {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center space-y-4">
          <Loader2 className="h-8 w-8 animate-spin mx-auto text-purple-600" />
          <p className="text-muted-foreground">Redirigiendo al dashboard...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 py-16">
        {/* Header */}
        <div className="text-center mb-16">
          <Badge className="mb-4" variant="secondary">
            Planes y Precios
          </Badge>
          <h1 className="text-4xl md:text-6xl font-bold mb-6 bg-gradient-to-r from-purple-500 to-purple-700 bg-clip-text text-transparent">
            Actualiza tu Plan
          </h1>
          <p className="text-xl text-gray-600 dark:text-gray-300 max-w-3xl mx-auto">
            Elige el plan perfecto para tu equipo. Sin contratos, cancela cuando quieras.
          </p>
        </div>

        {/* Pricing Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 max-w-7xl mx-auto">
          {plans.map((plan) => (
            <Card 
              key={plan.id} 
              className={`relative transition-all duration-300 hover:shadow-xl ${
                plan.popular 
                  ? 'ring-2 ring-purple-600 shadow-lg scale-105' 
                  : 'hover:scale-105'
              }`}
            >
              {plan.popular && (
                <div className="absolute -top-4 left-1/2 transform -translate-x-1/2">
                  <Badge className="bg-gradient-to-r from-purple-500 to-purple-700 text-white px-4 py-1">
                    <Star className="w-4 h-4 mr-1" />
                    Más Popular
                  </Badge>
                </div>
              )}

              <CardHeader className="text-center">
                <div className="flex items-center justify-center mb-2">
                  {getPlanIcon(plan.id)}
                  <CardTitle className="text-2xl font-bold ml-2">{plan.name}</CardTitle>
                </div>
                <CardDescription className="text-gray-600 dark:text-gray-300">
                  {plan.description}
                </CardDescription>
                <div className="pt-4">
                  <span className="text-5xl font-bold">
                    {plan.price === 0 ? 'Gratis' : plan.price === null ? 'Personalizado' : formatPrice(plan.price)}
                  </span>
                  {plan.price && plan.price > 0 && (
                    <span className="text-gray-500 dark:text-gray-400 ml-1">
                      /mes
                    </span>
                  )}
                  {plan.yearlyPrice && (
                    <div className="mt-2">
                      <span className="text-sm text-gray-500">
                        o {formatPrice(plan.yearlyPrice)}/año
                      </span>
                      <Badge variant="secondary" className="ml-2 text-xs">
                        Ahorra {calculateYearlyDiscount(plan.price * 12, plan.yearlyPrice)}%
                      </Badge>
                    </div>
                  )}
                </div>
              </CardHeader>

              <CardContent>
                <ul className="space-y-3">
                  {plan.features.map((feature, index) => (
                    <li key={index} className="flex items-start">
                      <Check className="w-5 h-5 text-green-500 mr-3 mt-0.5 flex-shrink-0" />
                      <span className="text-gray-600 dark:text-gray-300">{feature}</span>
                    </li>
                  ))}
                </ul>
              </CardContent>

              <CardFooter className="flex flex-col space-y-2">
                <Button
                  className="w-full"
                  variant={plan.popular ? 'default' : 'outline'}
                  size="lg"
                  onClick={() => handlePlanSelection(plan)}
                  disabled={loadingPlan === plan.id}
                >
                  {loadingPlan === plan.id ? (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  ) : (
                    getPlanIcon(plan.id)
                  )}
                  <span className="ml-2">{plan.cta}</span>
                </Button>
                {plan.yearlyPrice && plan.price > 0 && (
                  <Button
                    className="w-full"
                    variant="ghost"
                    size="sm"
                    onClick={() => handlePlanSelection(plan, true)}
                    disabled={loadingPlan === plan.id}
                  >
                    Elegir Plan Anual (Ahorra {calculateYearlyDiscount(plan.price * 12, plan.yearlyPrice)}%)
                  </Button>
                )}
              </CardFooter>
            </Card>
          ))}
        </div>

        {/* FAQ or Additional Info */}
        <div className="text-center mt-16">
          <p className="text-gray-600 dark:text-gray-300 mb-4">
            ¿Necesitas una solución personalizada? ¿Tienes preguntas?
          </p>
          <Button 
            variant="outline" 
            size="lg"
            onClick={() => window.location.href = 'mailto:sales@nexusdocs360.com'}
          >
            Contacta a Nuestro Equipo
          </Button>
        </div>
      </div>
    </div>
  )
}