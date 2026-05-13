'use client'

import { Suspense, useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { IconCheck, IconX, IconLoader2 } from '@tabler/icons-react'

/**
 * Channels OAuth Callback Page
 *
 * Receives Google's redirect after a Gmail/Drive channel authorization and:
 * 1. Extracts code/state/error from URL query params
 * 2. Forwards them to the backend with Accept: application/json
 * 3. Renders success/error UI from the JSON response
 *
 * This page must own the visible URL so the backend host:port is never
 * exposed in the browser address bar. Channels OAuth uses full-page
 * navigation (not a popup), so after success this page redirects the user
 * back to /channels with a short success state.
 */
export default function ChannelsOAuthCallbackPage() {
  return (
    <Suspense fallback={
      <div className="flex items-center justify-center min-h-screen bg-background">
        <IconLoader2 className="h-10 w-10 animate-spin text-primary" />
      </div>
    }>
      <ChannelsOAuthCallbackContent />
    </Suspense>
  )
}

function ChannelsOAuthCallbackContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading')
  const [message, setMessage] = useState('')
  const [email, setEmail] = useState('')

  useEffect(() => {
    const code = searchParams.get('code')
    const state = searchParams.get('state')
    const error = searchParams.get('error')
    const errorDescription = searchParams.get('error_description')

    if (error) {
      setStatus('error')
      setMessage(errorDescription || error)
      return
    }

    if (!code || !state) {
      setStatus('error')
      setMessage('Faltan parámetros de autorización (code, state)')
      return
    }

    const exchangeCode = async () => {
      try {
        const params = new URLSearchParams({ code, state })
        const response = await fetch(`/api/v1/channels/oauth/callback?${params}`, {
          headers: { 'Accept': 'application/json' },
        })

        let payload: { ok?: boolean; email?: string; channel_id?: string; error?: string; detail?: string } = {}
        try {
          payload = await response.json()
        } catch {
          payload = { ok: false, error: 'invalid_response' }
        }

        if (response.ok && payload.ok) {
          setStatus('success')
          setEmail(payload.email || '')
          setMessage('Canal autorizado correctamente')

          setTimeout(() => {
            router.push('/emma/channels')
          }, 2000)
        } else {
          setStatus('error')
          setMessage(payload.detail || payload.error || 'Error al intercambiar el código de autorización')
        }
      } catch (err: any) {
        setStatus('error')
        setMessage(err.message || 'Error de conexión con el servidor')
      }
    }

    exchangeCode()
  }, [searchParams, router])

  return (
    <div className="flex items-center justify-center min-h-screen bg-background">
      <div className="bg-card border rounded-xl p-8 shadow-sm text-center max-w-sm">
        {status === 'loading' && (
          <>
            <IconLoader2 className="h-10 w-10 animate-spin text-primary mx-auto mb-4" />
            <p className="text-muted-foreground">Procesando autorización del canal...</p>
          </>
        )}

        {status === 'success' && (
          <>
            <div className="w-12 h-12 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center mx-auto mb-4">
              <IconCheck className="h-6 w-6 text-green-600 dark:text-green-400" />
            </div>
            <h2 className="text-lg font-semibold mb-1">Autorización exitosa</h2>
            {email && <p className="text-sm text-muted-foreground mb-3">{email}</p>}
            <p className="text-xs text-muted-foreground">Redirigiendo a tus canales...</p>
          </>
        )}

        {status === 'error' && (
          <>
            <div className="w-12 h-12 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center mx-auto mb-4">
              <IconX className="h-6 w-6 text-red-600 dark:text-red-400" />
            </div>
            <h2 className="text-lg font-semibold mb-1">Error de autorización</h2>
            <p className="text-sm text-muted-foreground mb-4">{message}</p>
            <button
              onClick={() => router.push('/emma/channels')}
              className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm hover:opacity-90"
            >
              Volver a canales
            </button>
          </>
        )}
      </div>
    </div>
  )
}
