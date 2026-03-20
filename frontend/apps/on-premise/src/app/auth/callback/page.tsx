'use client'

/**
 * OIDC Callback Page for NouxCube AI On-Premise
 *
 * Handles the redirect from KeyCloak after authentication.
 * The actual token exchange is handled by the AuthContext.
 */

import { Suspense, useEffect, useState } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import Image from 'next/image'
import { IconLoader2, IconAlertCircle } from '@tabler/icons-react'
import { Button } from '@/components/ui'
import { useAuth } from '@/contexts/auth-context'

type CallbackStatus = 'processing' | 'error'

export default function AuthCallbackPage() {
  return (
    <Suspense fallback={
      <div className="flex min-h-screen items-center justify-center bg-[#05070d]">
        <IconLoader2 className="h-10 w-10 animate-spin text-cyan-400" />
      </div>
    }>
      <AuthCallbackContent />
    </Suspense>
  )
}

function AuthCallbackContent() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const { isLoaded, isAuthenticated } = useAuth()
  const [status, setStatus] = useState<CallbackStatus>('processing')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const errorParam = searchParams.get('error')
    const errorDescription = searchParams.get('error_description')

    if (errorParam) {
      setStatus('error')
      setError(errorDescription || errorParam)
      return
    }
  }, [searchParams])

  // Redirect immediately when authenticated (no success message)
  useEffect(() => {
    if (isLoaded && isAuthenticated) {
      router.push('/')
    }
  }, [isLoaded, isAuthenticated, router])

  const handleRetry = () => {
    sessionStorage.removeItem('nexus_oidc_state')
    sessionStorage.removeItem('nexus_oidc_verifier')
    window.location.href = '/auth/sign-in'
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#05070d]">
      {/* Background effects */}
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute inset-x-0 top-0 h-[500px] bg-gradient-to-b from-cyan-500/8 via-transparent to-transparent" />
        <div className="absolute right-0 top-1/4 h-[400px] w-[400px] rounded-full bg-cyan-500/5 blur-[100px]" />
        <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNjAiIGhlaWdodD0iNjAiIHZpZXdCb3g9IjAgMCA2MCA2MCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48ZyBmaWxsPSJub25lIiBmaWxsLXJ1bGU9ImV2ZW5vZGQiPjxnIGZpbGw9IiMyMjIiIGZpbGwtb3BhY2l0eT0iMC4wMyI+PGNpcmNsZSBjeD0iMSIgY3k9IjEiIHI9IjEiLz48L2c+PC9nPjwvc3ZnPg==')] opacity-50" />
      </div>

      <div className="relative z-10 mx-4 w-full max-w-md rounded-2xl border border-white/10 bg-gradient-to-b from-white/[0.08] to-white/[0.02] p-8 shadow-2xl shadow-black/50 backdrop-blur-xl">
        <div className="flex flex-col items-center gap-6 text-center text-white">
          {/* Logo */}
          <div className="relative">
            <div className="absolute -inset-4 rounded-full bg-cyan-500/20 blur-xl" />
            <Image
              src="/logo-single.png"
              alt="NouxCube"
              width={64}
              height={64}
              className="relative h-14 w-auto"
            />
          </div>

          {status === 'processing' && (
            <>
              <div className="relative">
                <div className="absolute inset-0 animate-ping rounded-full bg-cyan-400/30" />
                <IconLoader2 className="relative h-10 w-10 animate-spin text-cyan-400" />
              </div>
              <div>
                <h2 className="mb-2 text-xl font-semibold">
                  Procesando autenticación
                </h2>
                <p className="text-sm text-slate-400">
                  Verificando credenciales con KeyCloak...
                </p>
              </div>
            </>
          )}

          {status === 'error' && (
            <>
              <div className="relative">
                <div className="absolute inset-0 rounded-full bg-red-400/20 blur-lg" />
                <IconAlertCircle className="relative h-10 w-10 text-red-400" />
              </div>
              <div>
                <h2 className="mb-2 text-xl font-semibold">
                  Error de autenticación
                </h2>
                <p className="mb-4 text-sm text-slate-400">
                  {error || 'No se pudo completar la autenticación'}
                </p>
                <div className="flex justify-center gap-3">
                  <Button
                    variant="outline"
                    onClick={() => window.location.href = '/auth/sign-in'}
                    className="border-white/10 text-white hover:bg-white/10"
                  >
                    Volver al inicio
                  </Button>
                  <Button
                    onClick={handleRetry}
                    className="bg-gradient-to-r from-cyan-500 to-cyan-400 font-medium text-slate-900 shadow-lg shadow-cyan-500/25 hover:from-cyan-400 hover:to-cyan-300"
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
