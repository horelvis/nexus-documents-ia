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
    if (plan.id === 'enterprise') {
      // Open contact form or redirect to sales
      window.location.href = 'mailto:sales@nexusdocs360.com?subject=Enterprise%20Plan%20-%20Solicitud%20de%20Información&body=Hola,%0A%0AEstoy%20interesado%20en%20el%20plan%20Enterprise%20de%20NexusDocs360.%0A%0ANombre%20de%20la%20empresa:%20%0ANúmero%20de%20usuarios:%20%0ARequerimientos%20específicos:%20%0A%0AGracias.'
      return
    }

    // For all other plans (free and paid), redirect to signup with plan params.
    const currentHost = window.location.origin;
    const interval = isYearly ? 'yearly' : 'monthly';
    window.location.href = `${currentHost}/auth/sign-up?plan=${plan.id}&interval=${interval}`
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
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 py-16">
        {/* Header */}
        <div className="text-center mb-16">
          <Badge className="mb-4" variant="secondary">
            Pricing
          </Badge>
          <h1 className="text-4xl md:text-6xl font-bold mb-6 bg-gradient-to-r from-purple-500 to-purple-700 bg-clip-text text-transparent">
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
                  ? 'ring-2 ring-purple-600 shadow-lg scale-105' 
                  : 'hover:scale-105'
              }`}
            >
              {plan.popular && (
                <div className="absolute -top-4 left-1/2 transform -translate-x-1/2">
                  <Badge className="bg-gradient-to-r from-purple-500 to-purple-700 text-white px-4 py-1">
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
                    {plan.price === 0 ? 'Free' : plan.price === null ? 'Custom' : formatPrice(plan.price)}
                  </span>
                  {plan.price && plan.price > 0 && (
                    <span className="text-gray-500 dark:text-gray-400 ml-1">
                      /{plan.interval}
                    </span>
                  )}
                  {plan.price === null && (
                    <div className="mt-2">
                      <span className="text-sm text-gray-500">
                        Precios personalizados según tus necesidades
                      </span>
                    </div>
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
                {plan.id === 'pro' ? (
                  // Pro plan with dual buttons
                  <>
                    <div className="grid grid-cols-2 gap-2 w-full">
                      <Button
                        className="w-full"
                        variant="default"
                        size="lg"
                        onClick={() => handlePlanSelection(plan)}
                      >
                        {getPlanIcon(plan.id)}
                        <span className="ml-2">{plan.cta}</span>
                      </Button>
                      <Button
                        className="w-full"
                        variant="outline"
                        size="lg"
                        onClick={() => handlePlanSelection(plans.find(p => p.id === 'free') || plan)}
                      >
                        <Star className="w-4 h-4 mr-2" />
                        Probar gratis
                      </Button>
                    </div>
                    <p className="text-xs text-center text-gray-500 dark:text-gray-400 mt-2">
                      Elige entre pagar o probar 14 días gratis
                    </p>
                    {plan.yearlyPrice && (
                      <Button
                        className="w-full mt-2"
                        variant="ghost"
                        size="sm"
                        onClick={() => handlePlanSelection(plan, true)}
                      >
                        Ahorra {calculateYearlyDiscount(plan.price * 12, plan.yearlyPrice)}% con plan anual
                      </Button>
                    )}
                  </>
                ) : (
                  // Other plans with single button
                  <>
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
                  </>
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
