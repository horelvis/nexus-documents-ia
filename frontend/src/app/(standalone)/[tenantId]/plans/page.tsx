'use client'

import { useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useAuth } from '@clerk/nextjs'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { 
  Check,
  X,
  Loader2,
  Crown,
  Zap,
  Star
} from 'lucide-react'
import { useUserContext } from '@/contexts/user-context'
import { useNotifications } from '@/contexts/app-state-context'

const PLANS = [
  {
    id: 'free',
    name: 'Plan Gratuito',
    description: 'Perfecto para empezar',
    price: '$0',
    priceId: null,
    gradient: 'from-gray-600 to-gray-700',
    features: [
      { name: 'Hasta 10 documentos', included: true },
      { name: '5 cargas mensuales', included: true },
      { name: 'Búsqueda básica', included: true },
      { name: 'Chat con documentos', included: true },
      { name: 'Agentes AI', included: false, highlight: true },
      { name: 'Exportar documentos', included: false },
      { name: 'API Access', included: false },
      { name: 'Soporte prioritario', included: false }
    ],
    icon: Star,
    current: true
  },
  {
    id: 'pro',
    name: 'Plan Profesional',
    description: 'Para profesionales y equipos pequeños',
    price: '$29',
    priceId: 'price_professional',
    popular: true,
    gradient: 'from-blue-600 to-purple-600',
    features: [
      { name: 'Hasta 500 documentos', included: true },
      { name: '100 cargas mensuales', included: true },
      { name: 'Búsqueda avanzada', included: true },
      { name: 'Chat con documentos', included: true },
      { name: 'Agentes AI', included: true },
      { name: 'Exportar documentos', included: true },
      { name: 'API Access', included: false },
      { name: 'Soporte por email', included: true }
    ],
    icon: Zap
  },
  {
    id: 'enterprise',
    name: 'Plan Empresarial',
    description: 'Para empresas con necesidades avanzadas',
    price: 'Personalizado',
    priceId: 'price_enterprise',
    gradient: 'from-purple-600 to-pink-600',
    features: [
      { name: 'Documentos ilimitados', included: true },
      { name: 'Cargas ilimitadas', included: true },
      { name: 'Búsqueda avanzada', included: true },
      { name: 'Chat con documentos', included: true },
      { name: 'Agentes AI ilimitados', included: true },
      { name: 'Exportar documentos', included: true },
      { name: 'API Access completo', included: true },
      { name: 'Soporte prioritario 24/7', included: true }
    ],
    icon: Crown
  }
]

export default function PlansPage() {
  const params = useParams()
  const router = useRouter()
  const { getToken } = useAuth()
  const { backendUser } = useUserContext()
  const { addNotification } = useNotifications()
  
  const [isLoading, setIsLoading] = useState<string | null>(null)
  
  // Get current plan from backend user (now stored directly on user)
  const currentPlan = backendUser?.subscription_plan || 'free'

  const handleSelectPlan = async (plan: typeof PLANS[0]) => {
    if (plan.id === currentPlan) {
      addNotification({
        type: 'info',
        title: 'Plan actual',
        message: 'Ya estás en este plan'
      })
      return
    }

    if (!plan.priceId) {
      addNotification({
        type: 'info',
        title: 'Plan gratuito',
        message: 'Ya estás en el plan gratuito'
      })
      return
    }

    // Handle enterprise plan - redirect to contact form
    if (plan.id === 'enterprise') {
      window.location.href = 'mailto:sales@nexusdocument.com?subject=Enterprise Plan Inquiry'
      return
    }

    try {
      setIsLoading(plan.id)
      const token = await getToken()
      const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      
      const response = await fetch(`${API_BASE}/api/v1/stripe/create-checkout-session`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          planId: plan.id === 'professional' ? 'pro' : plan.id,
          interval: 'month',
          email: backendUser?.email,
          success_url: `${window.location.origin}/${params.tenantId}/dashboard?upgraded=true&sync=true`,
          cancel_url: window.location.href
        })
      })

      if (response.ok) {
        const { url } = await response.json()
        window.location.href = url
      } else {
        throw new Error('Failed to create checkout session')
      }
    } catch (error) {
      console.error('Error creating checkout:', error)
      addNotification({
        type: 'error',
        title: 'Error',
        message: 'No se pudo procesar la actualización del plan'
      })
    } finally {
      setIsLoading(null)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-50 to-white dark:from-gray-900 dark:to-black">
      {/* Simple header with logo and back button */}
      <div className="w-full border-b bg-white/50 dark:bg-gray-900/50 backdrop-blur-sm">
        <div className="container max-w-6xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => router.push(`/${params.tenantId}/dashboard`)}
                className="gap-2"
              >
                ← Volver al dashboard
              </Button>
              <h2 className="text-xl font-semibold">Nexus Document</h2>
            </div>
          </div>
        </div>
      </div>

      <div className="container max-w-6xl mx-auto px-4 py-12">
        <div className="mb-12 text-center">
          <h1 className="text-4xl font-bold mb-4 bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
            Elige el plan perfecto para ti
          </h1>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            Desbloquea todo el potencial de la gestión inteligente de documentos con agentes AI avanzados
          </p>
        </div>

        <div className="grid gap-6 md:grid-cols-3">
        {PLANS.map((plan) => {
          const isCurrent = plan.id === currentPlan
          const Icon = plan.icon
          
          return (
            <Card 
              key={plan.id} 
              className={`relative transition-all hover:scale-105 ${plan.popular ? 'border-blue-600 shadow-lg scale-105' : ''} ${isCurrent ? 'border-green-600' : ''}`}
            >
              {plan.popular && (
                <Badge className="absolute -top-3 left-1/2 -translate-x-1/2 bg-blue-600">
                  Más popular
                </Badge>
              )}
              {isCurrent && (
                <Badge className="absolute -top-3 right-4 bg-green-600">
                  Plan actual
                </Badge>
              )}
              
              <CardHeader>
                <div className={`inline-flex p-3 rounded-full bg-gradient-to-r ${plan.gradient} mb-4`}>
                  <Icon className="h-6 w-6 text-white" />
                </div>
                <CardTitle className="text-2xl">
                  {plan.name}
                </CardTitle>
                <CardDescription>{plan.description}</CardDescription>
                <div className="mt-4">
                  <span className="text-4xl font-bold">{plan.price}</span>
                  {plan.price !== 'Personalizado' && <span className="text-muted-foreground text-lg">/mes</span>}
                </div>
              </CardHeader>
              
              <CardContent>
                <ul className="space-y-2">
                  {plan.features.map((feature, idx) => (
                    <li key={idx} className="flex items-center gap-2">
                      {feature.included ? (
                        <Check className="h-4 w-4 text-green-600 flex-shrink-0" />
                      ) : (
                        <X className="h-4 w-4 text-gray-400 flex-shrink-0" />
                      )}
                      <span className={`${
                        feature.included ? '' : 'text-muted-foreground'
                      } ${
                        feature.highlight && !feature.included ? 'font-semibold text-orange-600' : ''
                      }`}>
                        {feature.name}
                      </span>
                    </li>
                  ))}
                </ul>
              </CardContent>
              
              <CardFooter>
                <Button 
                  className="w-full" 
                  variant={isCurrent ? 'outline' : plan.popular ? 'default' : 'secondary'}
                  disabled={isCurrent || isLoading === plan.id}
                  onClick={() => handleSelectPlan(plan)}
                >
                  {isLoading === plan.id && (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  )}
                  {isCurrent ? 'Plan actual' : plan.id === 'enterprise' ? 'Contactar ventas' : 'Seleccionar plan'}
                </Button>
              </CardFooter>
            </Card>
          )
        })}
        </div>

        <div className="mt-12 text-center">
          <div className="max-w-2xl mx-auto space-y-4">
            <div className="flex items-center justify-center gap-8 text-sm text-muted-foreground">
              <div className="flex items-center gap-2">
                <Check className="h-4 w-4 text-green-600" />
                <span>Almacenamiento seguro</span>
              </div>
              <div className="flex items-center gap-2">
                <Check className="h-4 w-4 text-green-600" />
                <span>Cifrado de documentos</span>
              </div>
              <div className="flex items-center gap-2">
                <Check className="h-4 w-4 text-green-600" />
                <span>Cancela en cualquier momento</span>
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              ¿Tienes preguntas? Contáctanos en support@nexusdocument.com
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}