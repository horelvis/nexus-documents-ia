"use client"

import { useRouter } from 'next/navigation'
import { useAuth } from '@clerk/nextjs'
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { IconCheck, IconStar, IconCrown, IconBolt } from "@tabler/icons-react"
import { getAllPlans, formatPrice, type Plan } from '@/lib/stripe-plans'

export function PricingSection() {
  const router = useRouter()
  const { isSignedIn } = useAuth()
  const plans = getAllPlans()

  const handlePlanSelection = (plan: Plan) => {
    if (plan.id === 'free') {
      // Free plan: go to signup if not signed in, dashboard if signed in
      if (isSignedIn) {
        router.push('/dashboard')
      } else {
        router.push('/auth/sign-up?plan=free')
      }
    } else {
      // Paid plans: go to signup to start onboarding flow with plan selection
      if (isSignedIn) {
        router.push('/dashboard')
      } else {
        router.push('/auth/sign-up')
      }
    }
  }

  const getPlanIcon = (planId: string) => {
    switch (planId) {
      case 'enterprise':
        return <IconCrown className="w-5 h-5" />
      case 'pro':
        return <IconBolt className="w-5 h-5" />
      default:
        return <IconStar className="w-5 h-5" />
    }
  }

  return (
    <section className="py-24 bg-gray-50">
      <div className="container mx-auto px-4">
        {/* Header */}
        <div className="text-center mb-16">
          <Badge className="mb-4" variant="secondary">
            Planes y Precios
          </Badge>
          <h2 className="text-3xl md:text-4xl font-bold mb-6">
            Elige el plan perfecto para ti
          </h2>
          <p className="text-xl text-gray-600 max-w-3xl mx-auto">
            Desde startups hasta empresas. Empieza gratis y escala según crezca tu negocio.
          </p>
        </div>

        {/* Pricing Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 max-w-6xl mx-auto">
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
                    <IconStar className="w-4 h-4 mr-1" />
                    Más Popular
                  </Badge>
                </div>
              )}

              <CardHeader className="text-center">
                <div className="flex items-center justify-center mb-2">
                  {getPlanIcon(plan.id)}
                  <CardTitle className="text-xl font-bold ml-2">{plan.name}</CardTitle>
                </div>
                <CardDescription className="text-gray-600">
                  {plan.description}
                </CardDescription>
                <div className="pt-4">
                  <span className="text-4xl font-bold">
                    {plan.price === 0 ? 'Gratis' : formatPrice(plan.price)}
                  </span>
                  {plan.price > 0 && (
                    <span className="text-gray-500 ml-1">
                      /{plan.interval}
                    </span>
                  )}
                </div>
              </CardHeader>

              <CardContent>
                <ul className="space-y-3">
                  {plan.features.slice(0, 4).map((feature, index) => (
                    <li key={index} className="flex items-start">
                      <IconCheck className="w-5 h-5 text-green-500 mr-3 mt-0.5 flex-shrink-0" />
                      <span className="text-gray-600">{feature}</span>
                    </li>
                  ))}
                  {plan.features.length > 4 && (
                    <li className="text-sm text-gray-500 text-center pt-2">
                      +{plan.features.length - 4} características más
                    </li>
                  )}
                </ul>
              </CardContent>

              <CardFooter>
                <Button
                  className="w-full"
                  variant={plan.popular ? 'default' : 'outline'}
                  size="lg"
                  onClick={() => handlePlanSelection(plan)}
                >
                  {getPlanIcon(plan.id)}
                  <span className="ml-2">{plan.cta}</span>
                </Button>
              </CardFooter>
            </Card>
          ))}
        </div>

        {/* Bottom CTA */}
        <div className="text-center mt-12">
          <p className="text-gray-600 mb-4">
            ¿Necesitas una solución personalizada?
          </p>
          <Button 
            variant="outline" 
            size="lg"
            onClick={() => router.push('/pricing')}
          >
            Ver Todos los Planes
          </Button>
        </div>
      </div>
    </section>
  )
}