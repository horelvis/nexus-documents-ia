'use client'

import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { SubscriptionStatusBanner } from '@/components/common/subscription-status-banner'
import { useSubscription } from '@/hooks/use-subscription'

interface TestState {
  plan: string
  status: string
  label: string
  description: string
}

const testStates: TestState[] = [
  { 
    label: 'Activa (Pro)', 
    plan: 'pro', 
    status: 'active',
    description: 'Suscripción activa - no debería mostrar banner'
  },
  { 
    label: 'Caducada (Canceled)', 
    plan: 'pro', 
    status: 'canceled',
    description: 'Suscripción cancelada - debería mostrar banner de renovación'
  }, 
  { 
    label: 'Atrasada (Past Due)', 
    plan: 'pro', 
    status: 'past_due',
    description: 'Pago atrasado - debería mostrar banner de renovación'
  },
  { 
    label: 'Gratis', 
    plan: 'free', 
    status: 'active',
    description: 'Plan gratuito - no debería mostrar banner'
  }
]

export function SubscriptionDebugPanel() {
  const [currentTest, setCurrentTest] = useState<TestState | null>(null)
  const [mockEnabled, setMockEnabled] = useState(false)
  const { subscriptionData, loading, error, refetch } = useSubscription()

  // Enable mock mode in localStorage to be picked up by API client
  useEffect(() => {
    if (mockEnabled && currentTest) {
      localStorage.setItem('mock_subscription', JSON.stringify({
        plan_id: currentTest.plan,
        status: currentTest.status
      }))
    } else {
      localStorage.removeItem('mock_subscription')
    }
  }, [mockEnabled, currentTest])

  const enableTest = (state: TestState) => {
    setCurrentTest(state)
    setMockEnabled(true)
    // Force refresh subscription data
    setTimeout(() => refetch(), 100)
  }

  const disableTest = () => {
    setCurrentTest(null)
    setMockEnabled(false)
    localStorage.removeItem('mock_subscription')
    // Force refresh subscription data
    setTimeout(() => refetch(), 100)
  }

  const refreshData = () => {
    refetch()
  }

  return (
    <div className="space-y-4">
      <Card className="border-blue-200 bg-blue-50">
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            🔧 Debug Panel - Estados de Suscripción
            {currentTest && <Badge variant="default">{currentTest.label}</Badge>}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Test Controls */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {testStates.map((state) => (
              <div key={state.label} className="space-y-1">
                <Button
                  variant={currentTest?.label === state.label ? "default" : "outline"}
                  size="sm"
                  onClick={() => enableTest(state)}
                  className="w-full"
                >
                  {state.label}
                </Button>
                <p className="text-xs text-gray-600">{state.description}</p>
              </div>
            ))}
          </div>
          
          <div className="flex gap-2">
            <Button variant="destructive" size="sm" onClick={disableTest}>
              Resetear Estado Real
            </Button>
            <Button variant="secondary" size="sm" onClick={refreshData}>
              Refrescar Datos
            </Button>
          </div>

          {/* Current State Display */}
          <div className="p-3 bg-white rounded border">
            <div className="text-sm space-y-1">
              <div><strong>Estado de Loading:</strong> {loading ? 'Cargando...' : 'Completo'}</div>
              <div><strong>Error:</strong> {error || 'Ninguno'}</div>
              <div><strong>Plan ID:</strong> {subscriptionData?.plan_id || 'N/A'}</div>
              <div><strong>Status:</strong> {subscriptionData?.status || 'N/A'}</div>
              <div><strong>Es Limitado:</strong> {subscriptionData?.subscription_status?.is_limited ? 'Sí' : 'No'}</div>
              <div><strong>Es Activo:</strong> {subscriptionData?.subscription_status?.is_active ? 'Sí' : 'No'}</div>
              {mockEnabled && <div className="text-orange-600"><strong>🧪 Modo Mock Activo</strong></div>}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Live Preview of Subscription Banner */}
      <Card className="border-green-200 bg-green-50">
        <CardHeader>
          <CardTitle className="text-lg">Vista en Vivo - Subscription Banner</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="bg-white p-4 rounded border">
            <SubscriptionStatusBanner compact={false} />
          </div>
          
          <div className="mt-4 bg-white p-4 rounded border">
            <h4 className="font-medium mb-2">Versión Compacta:</h4>
            <SubscriptionStatusBanner compact={true} />
          </div>
        </CardContent>
      </Card>
    </div>
  )
}