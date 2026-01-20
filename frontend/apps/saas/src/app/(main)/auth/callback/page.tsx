'use client'

/**
 * OAuth Callback Page
 *
 * Handles the redirect from SSO providers after authentication.
 * Exchanges the authorization code for tokens and stores them.
 */

import { useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Loader2, CheckCircle, AlertCircle, Brain } from 'lucide-react'
import { Button } from '@/components/ui/button'

type CallbackStatus = 'processing' | 'success' | 'error'

interface TokenResponse {
  access_token: string
  refresh_token?: string
  id_token?: string
  token_type: string
  expires_in: number
}

export default function AuthCallbackPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [status, setStatus] = useState<CallbackStatus>('processing')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function handleCallback() {
      // Check for error from SSO provider
      const errorParam = searchParams.get('error')
      const errorDescription = searchParams.get('error_description')

      if (errorParam) {
        setStatus('error')
        setError(errorDescription || errorParam)
        return
      }

      // Get authorization code
      const code = searchParams.get('code')
      const state = searchParams.get('state')

      if (!code) {
        setStatus('error')
        setError('No authorization code received')
        return
      }

      try {
        // Exchange code for tokens
        const response = await fetch('/api/v1/auth/sso/callback', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            code,
            state,
            redirect_uri: `${window.location.origin}/auth/callback`,
          }),
        })

        if (!response.ok) {
          const data = await response.json().catch(() => ({}))
          throw new Error(data.detail || 'Token exchange failed')
        }

        const tokens: TokenResponse = await response.json()

        // Store tokens in sessionStorage
        const tokenData = {
          access_token: tokens.access_token,
          refresh_token: tokens.refresh_token,
          id_token: tokens.id_token,
          token_type: tokens.token_type || 'Bearer',
          expires_at: Date.now() + (tokens.expires_in || 3600) * 1000,
        }

        sessionStorage.setItem('nexus_sso_tokens', JSON.stringify(tokenData))

        // Success - redirect to app
        setStatus('success')

        // Extract tenant from state or use default
        // State format could be: "tenant_id:random_string" or just "random_string"
        let targetUrl = '/'
        if (state && state.includes(':')) {
          const [tenantId] = state.split(':')
          targetUrl = `/${tenantId}/emma`
        }

        // Small delay to show success message
        setTimeout(() => {
          router.push(targetUrl)
        }, 1000)

      } catch (err) {
        console.error('[AuthCallback] Error:', err)
        setStatus('error')
        setError(err instanceof Error ? err.message : 'Authentication failed')
      }
    }

    handleCallback()
  }, [searchParams, router])

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#05070d]">
      {/* Background effects */}
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute inset-x-0 top-0 h-40 bg-gradient-to-b from-cyan-500/10 via-transparent to-transparent blur-3xl" />
        <div className="absolute right-8 top-1/3 h-48 w-48 rounded-full bg-purple-500/10 blur-3xl" />
      </div>

      <div className="relative z-10 rounded-2xl border border-white/10 bg-[#0c1222]/90 p-8 shadow-2xl shadow-black/40 backdrop-blur max-w-md w-full mx-4">
        <div className="flex flex-col items-center gap-6 text-center">
          {/* Logo */}
          <div className="rounded-xl bg-primary/10 p-3">
            <Brain className="h-8 w-8 text-cyan-400" />
          </div>

          {status === 'processing' && (
            <>
              <Loader2 className="h-10 w-10 animate-spin text-cyan-400" />
              <div>
                <h2 className="text-xl font-semibold text-white mb-2">
                  Procesando autenticación
                </h2>
                <p className="text-sm text-slate-300">
                  Verificando credenciales...
                </p>
              </div>
            </>
          )}

          {status === 'success' && (
            <>
              <CheckCircle className="h-10 w-10 text-emerald-400" />
              <div>
                <h2 className="text-xl font-semibold text-white mb-2">
                  ¡Autenticación exitosa!
                </h2>
                <p className="text-sm text-slate-300">
                  Redirigiendo a Emma...
                </p>
              </div>
            </>
          )}

          {status === 'error' && (
            <>
              <AlertCircle className="h-10 w-10 text-red-400" />
              <div>
                <h2 className="text-xl font-semibold text-white mb-2">
                  Error de autenticación
                </h2>
                <p className="text-sm text-slate-300 mb-4">
                  {error || 'No se pudo completar la autenticación'}
                </p>
                <div className="flex gap-3 justify-center">
                  <Button
                    variant="outline"
                    onClick={() => router.push('/auth/sign-in')}
                    className="border-white/10 text-white hover:bg-white/10"
                  >
                    Volver al inicio
                  </Button>
                  <Button
                    onClick={() => window.location.reload()}
                    className="bg-cyan-400 text-slate-900 hover:bg-cyan-300"
                  >
                    Reintentar
                  </Button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
