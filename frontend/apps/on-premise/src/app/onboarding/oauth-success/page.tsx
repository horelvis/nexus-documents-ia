'use client'

/**
 * OAuth Success Page
 *
 * Shown after user successfully authorizes a connector.
 * Redirects back to onboarding to continue the flow.
 */

import { Suspense, useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { IconCheck, IconLoader2 } from '@tabler/icons-react'
import { Button } from '@nexus/shared/ui'

export default function OAuthSuccessPage() {
  return (
    <Suspense fallback={
      <div className="flex items-center justify-center min-h-screen bg-background">
        <IconLoader2 className="h-10 w-10 animate-spin text-primary" />
      </div>
    }>
      <OAuthSuccessContent />
    </Suspense>
  )
}

function OAuthSuccessContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [countdown, setCountdown] = useState(3)

  const connectorId = searchParams.get('connector_id')

  useEffect(() => {
    // Auto-redirect after countdown
    const timer = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          clearInterval(timer)
          router.push('/onboarding')
          return 0
        }
        return prev - 1
      })
    }, 1000)

    return () => clearInterval(timer)
  }, [router])

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-background">
      <div className="text-center space-y-6 max-w-md mx-auto px-4">
        {/* Success icon */}
        <div className="w-20 h-20 mx-auto rounded-full bg-green-100 flex items-center justify-center">
          <IconCheck className="h-10 w-10 text-green-600" />
        </div>

        {/* Message */}
        <div className="space-y-2">
          <h1 className="text-2xl font-bold">¡Conexión exitosa!</h1>
          <p className="text-muted-foreground">
            Tu cuenta ha sido autorizada correctamente.
            Ahora puedes activar la sincronización de documentos.
          </p>
        </div>

        {/* Countdown */}
        <div className="flex items-center justify-center gap-2 text-muted-foreground">
          <IconLoader2 className="h-4 w-4 animate-spin" />
          <span>Redirigiendo en {countdown}...</span>
        </div>

        {/* Manual redirect */}
        <Button onClick={() => router.push('/onboarding')} variant="outline">
          Continuar ahora
        </Button>
      </div>
    </div>
  )
}
