'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { useUserContext } from '@/contexts/user-context'
import { SubscriptionStatusBanner } from '@/components/common/subscription-status-banner'

interface TestState {
  plan: string
  status: string
  label: string
}

const mockSubscriptionStates: TestState[] = [
  { label: 'Activa (Pro)', plan: 'pro', status: 'active' },
  { label: 'Caducada (Canceled)', plan: 'pro', status: 'canceled' }, 
  { label: 'Atrasada (Past Due)', plan: 'pro', status: 'past_due' },
  { label: 'Gratis', plan: 'free', status: 'active' },
  { label: 'Incompleta', plan: 'pro', status: 'incomplete' }
]

export function SubscriptionTestPanel() {
  const { backendUser } = useUserContext()
  const [testingState, setTestingState] = useState<TestState | null>(null)

  // Temporarily override the user context values for testing
  const getTestUser = () => {
    if (!testingState || !backendUser) return backendUser
    
    return {
      ...backendUser,
      subscription_plan: testingState.plan,
      subscription_status: testingState.status
    }
  }

  const applyTestState = (state: TestState) => {
    setTestingState(state)
  }

  const resetToOriginal = () => {
    setTestingState(null)
  }

  // Override the useUserContext temporarily for components below
  const testUser = getTestUser()

  return (
    <div>
      <Card className="m-4 border-yellow-200 bg-yellow-50">
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            🧪 Panel de Testing - Estados de Suscripción
            {testingState && <Badge variant="secondary">Testing: {testingState.label}</Badge>}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2 mb-4">
            {mockSubscriptionStates.map((state) => (
              <Button
                key={state.label}
                variant="outline"
                size="sm"
                onClick={() => applyTestState(state)}
                className={testingState?.label === state.label ? 'bg-blue-100' : ''}
              >
                {state.label}
              </Button>
            ))}
          </div>
          
          <div className="flex gap-2 mb-4">
            <Button variant="destructive" size="sm" onClick={resetToOriginal}>
              Resetear Estado Original
            </Button>
          </div>

          <div className="p-3 bg-gray-100 rounded text-sm">
            <strong>Estado actual:</strong><br />
            Plan: {testUser?.subscription_plan || 'N/A'}<br />
            Status: {testUser?.subscription_status || 'N/A'}
            {testingState && (
              <>
                <br />
                <em className="text-orange-600">⚠️ Modo Testing Activo</em>
              </>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Test the subscription banner with the current test state */}
      {testingState && (
        <div className="m-4">
          <h3 className="text-lg font-semibold mb-2">Vista Previa del Banner:</h3>
          {/* Note: This won't work perfectly because SubscriptionStatusBanner uses its own useUserContext */}
          <SubscriptionStatusBanner compact={false} />
        </div>
      )}
    </div>
  )
}
