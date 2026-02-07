'use client'

import { useEffect, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { IconCheck, IconX, IconLoader2 } from '@tabler/icons-react'

/**
 * OAuth Callback Page
 *
 * Microsoft (and other HTTPS-requiring providers) redirect here after authorization.
 * This page:
 * 1. Extracts code/state/error from URL query params
 * 2. Forwards them to the backend API for token exchange
 * 3. Shows success/error UI
 * 4. Notifies the opener window via postMessage and auto-closes
 */
export default function OAuthCallbackPage() {
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
      if (window.opener) {
        window.opener.postMessage({ type: 'oauth-error', error: errorDescription || error }, '*')
      }
      return
    }

    if (!code || !state) {
      setStatus('error')
      setMessage('Faltan parámetros de autorización (code, state)')
      return
    }

    // Forward to backend callback endpoint (via Next.js rewrite proxy)
    const exchangeCode = async () => {
      try {
        const params = new URLSearchParams({ code, state })
        const response = await fetch(`/api/v1/connectors/oauth/callback?${params}`)
        const html = await response.text()

        if (response.ok) {
          // Extract email from the HTML response if present
          const emailMatch = html.match(/oauth-success.*?email['":\s]*['"]([^'"]+)['"]/)
          const extractedEmail = emailMatch?.[1] || ''

          setStatus('success')
          setEmail(extractedEmail)
          setMessage('Autorización exitosa')

          if (window.opener) {
            window.opener.postMessage({ type: 'oauth-success', email: extractedEmail }, '*')
          }

          setTimeout(() => {
            try { window.close() } catch {}
          }, 1500)
        } else {
          setStatus('error')
          setMessage('Error al intercambiar el código de autorización')
          if (window.opener) {
            window.opener.postMessage({ type: 'oauth-error', error: 'Token exchange failed' }, '*')
          }
        }
      } catch (err: any) {
        setStatus('error')
        setMessage(err.message || 'Error de conexión con el servidor')
      }
    }

    exchangeCode()
  }, [searchParams])

  return (
    <div className="flex items-center justify-center min-h-screen bg-background">
      <div className="bg-card border rounded-xl p-8 shadow-sm text-center max-w-sm">
        {status === 'loading' && (
          <>
            <IconLoader2 className="h-10 w-10 animate-spin text-primary mx-auto mb-4" />
            <p className="text-muted-foreground">Procesando autorización...</p>
          </>
        )}

        {status === 'success' && (
          <>
            <div className="w-12 h-12 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center mx-auto mb-4">
              <IconCheck className="h-6 w-6 text-green-600 dark:text-green-400" />
            </div>
            <h2 className="text-lg font-semibold mb-1">Autorización exitosa</h2>
            {email && <p className="text-sm text-muted-foreground mb-3">{email}</p>}
            <p className="text-xs text-muted-foreground">Esta ventana se cerrará automáticamente...</p>
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
              onClick={() => window.close()}
              className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm hover:opacity-90"
            >
              Cerrar
            </button>
          </>
        )}
      </div>
    </div>
  )
}
