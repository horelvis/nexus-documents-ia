'use client'

import React from 'react'
import { Check, Star, Zap, Crown } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { getAllPlans, formatPrice, calculateYearlyDiscount, isPaidPlan, type Plan } from '@/lib/stripe-plans'

export default function PricingPage() {
  const plans = getAllPlans()

  const handlePlanSelection = async (plan: Plan, isYearly: boolean = false) => {
    if (plan.id === 'free') {
      // Redirect directly to signup for free plan
      window.location.href = '/auth/sign-up?plan=free'
      return
    }

    if (plan.id === 'enterprise') {
      // Open contact form or redirect to sales
      window.location.href = 'mailto:sales@nexus.com?subject=Enterprise%20Plan%20Inquiry'
      return
    }

    // For paid plans, create Stripe checkout session
    try {
      const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      const response = await fetch(`${API_BASE}/api/v1/stripe/create-checkout-session`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          planId: plan.id,
          interval: isYearly ? 'year' : 'month',
        }),
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const { url } = await response.json()
      
      if (url) {
        window.location.href = url
      }
    } catch (error) {
      console.error('Error creating checkout session:', error)
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

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800">
      <div className="container mx-auto px-4 py-16">
        {/* Header */}
        <div className="text-center mb-16">
          <Badge className="mb-4" variant="secondary">
            Pricing
          </Badge>
          <h1 className="text-4xl md:text-6xl font-bold mb-6 bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
            Choose Your Plan
          </h1>
          <p className="text-xl text-gray-600 dark:text-gray-300 max-w-3xl mx-auto">
            Start free and scale as you grow. No hidden fees, no lock-in contracts.
          </p>
        </div>

        {/* Pricing Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 max-w-7xl mx-auto">
          {plans.map((plan) => (
            <Card 
              key={plan.id} 
              className={`relative transition-all duration-300 hover:shadow-xl ${
                plan.popular 
                  ? 'ring-2 ring-blue-500 shadow-lg scale-105' 
                  : 'hover:scale-105'
              }`}
            >
              {plan.popular && (
                <div className="absolute -top-4 left-1/2 transform -translate-x-1/2">
                  <Badge className="bg-gradient-to-r from-blue-600 to-purple-600 text-white px-4 py-1">
                    <Star className="w-4 h-4 mr-1" />
                    Most Popular
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
                    {plan.price === 0 ? 'Free' : formatPrice(plan.price)}
                  </span>
                  {plan.price > 0 && (
                    <span className="text-gray-500 dark:text-gray-400 ml-1">
                      /{plan.interval}
                    </span>
                  )}
                  {plan.yearlyPrice && (
                    <div className="mt-2">
                      <span className="text-sm text-gray-500">
                        or {formatPrice(plan.yearlyPrice)}/year
                      </span>
                      <Badge variant="secondary" className="ml-2 text-xs">
                        Save {calculateYearlyDiscount(plan.price * 12, plan.yearlyPrice)}%
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
                >
                  {getPlanIcon(plan.id)}
                  <span className="ml-2">{plan.cta}</span>
                </Button>
                {plan.yearlyPrice && plan.price > 0 && (
                  <Button
                    className="w-full"
                    variant="ghost"
                    size="sm"
                    onClick={() => handlePlanSelection(plan, true)}
                  >
                    Choose Yearly (Save {calculateYearlyDiscount(plan.price * 12, plan.yearlyPrice)}%)
                  </Button>
                )}
              </CardFooter>
            </Card>
          ))}
        </div>

        {/* FAQ or Additional Info */}
        <div className="text-center mt-16">
          <p className="text-gray-600 dark:text-gray-300 mb-4">
            Need a custom solution? Have questions?
          </p>
          <Button variant="outline" size="lg">
            Contact Our Sales Team
          </Button>
        </div>
      </div>
    </div>
  )
}