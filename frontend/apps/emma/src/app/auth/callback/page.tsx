'use client'

/**
 * OIDC Callback Page for Emma On-Premise
 *
 * Handles the redirect from KeyCloak after authentication.
 * The actual token exchange is handled by the AuthContext.
 */

import { useEffect, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { Loader2, CheckCircle, AlertCircle, Brain } from 'lucide-react'
import { Button } from '@nexus/shared/ui'
import { useAuth } from '@/contexts/auth-context'

type CallbackStatus = 'processing' | 'success' | 'error'

export default function AuthCallbackPage() {
  const searchParams = useSearchParams()
  const { isLoaded, isAuthenticated } = useAuth()
  const [status, setStatus] = useState<CallbackStatus>('processing')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    // Check for error from SSO provider
    const errorParam = searchParams.get('error')
    const errorDescription = searchParams.get('error_description')

    if (errorParam) {
      setStatus('error')
      setError(errorDescription || errorParam)
      return
    }

    // The AuthContext handles the actual callback processing
    // We just show the loading state until it's done
  }, [searchParams])

  // Update status based on auth state
  useEffect(() => {
    if (isLoaded && isAuthenticated) {
      setStatus('success')
    }
  }, [isLoaded, isAuthenticated])

  const handleRetry = () => {
    // Clear any stored state and redirect to sign-in
    sessionStorage.removeItem('nexus_oidc_state')
    sessionStorage.removeItem('nexus_oidc_verifier')
    window.location.href = '/auth/sign-in'
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#05070d]">
      {/* Background effects */}
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute inset-x-0 top-0 h-40 bg-gradient-to-b from-cyan-500/10 via-transparent to-transparent blur-3xl" />
        <div className="absolute right-8 top-1/3 h-48 w-48 rounded-full bg-purple-500/10 blur-3xl" />
      </div>

      <div className="relative z-10 rounded-2xl border border-white/10 bg-[#0c1222]/90 p-8 shadow-2xl shadow-black/40 backdrop-blur max-w-md w-full mx-4">
        <div className="flex flex-col items-center gap-6 text-center text-white">
          {/* Logo */}
          <div className="rounded-xl bg-primary/10 p-3">
            <Brain className="h-8 w-8 text-cyan-400" />
          </div>

          {status === 'processing' && (
            <>
              <Loader2 className="h-10 w-10 animate-spin text-cyan-400" />
              <div>
                <h2 className="text-xl font-semibold mb-2">
                  Procesando autenticación
                </h2>
                <p className="text-sm text-slate-300">
                  Verificando credenciales con KeyCloak...
                </p>
              </div>
            </>
          )}

          {status === 'success' && (
            <>
              <CheckCircle className="h-10 w-10 text-emerald-400" />
              <div>
                <h2 className="text-xl font-semibold mb-2">
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
                <h2 className="text-xl font-semibold mb-2">
                  Error de autenticación
                </h2>
                <p className="text-sm text-slate-300 mb-4">
                  {error || 'No se pudo completar la autenticación'}
                </p>
                <div className="flex gap-3 justify-center">
                  <Button
                    variant="outline"
                    onClick={() => window.location.href = '/auth/sign-in'}
                    className="border-white/10 text-white hover:bg-white/10"
                  >
                    Volver al inicio
                  </Button>
                  <Button
                    onClick={handleRetry}
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
