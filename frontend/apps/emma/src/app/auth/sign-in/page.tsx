'use client'

/**
 * SSO Sign-In Page for Emma On-Premise
 *
 * Redirects to KeyCloak for OIDC authentication.
 * Uses Authorization Code flow with PKCE.
 */

import { useEffect, useState } from 'react'
import { IconBrain, IconLoader2, IconShield, IconCircleCheck } from '@tabler/icons-react'
import { Button } from '@nexus/shared/ui'
import { useAuth } from '@/contexts/auth-context'
import { OIDC_CONFIG } from '@/lib/oidc-config'

export default function SignInPage() {
  const { isLoaded, isAuthenticated, login } = useAuth()
  const [error, setError] = useState<string | null>(null)
  const [isRedirecting, setIsRedirecting] = useState(false)

  useEffect(() => {
    // Check URL for error params (from failed callback)
    const params = new URLSearchParams(window.location.search)
    const errorParam = params.get('error')
    if (errorParam) {
      setError(errorParam === 'callback_failed'
        ? 'No se pudo completar la autenticación. Por favor, intente de nuevo.'
        : errorParam
      )
      return
    }

    // If already authenticated, redirect to emma
    if (isLoaded && isAuthenticated) {
      window.location.href = '/'
      return
    }
  }, [isLoaded, isAuthenticated])

  const handleLogin = async () => {
    setError(null)
    setIsRedirecting(true)
    try {
      await login()
      // login() redirects to KeyCloak, this code won't execute
    } catch (err) {
      console.error('[SignIn] Error:', err)
      setError(err instanceof Error ? err.message : 'Error al iniciar autenticación')
      setIsRedirecting(false)
    }
  }

  return (
    <div className="relative min-h-screen overflow-hidden bg-[#05070d] text-white">
      {/* Background effects */}
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute inset-x-0 top-0 h-40 bg-gradient-to-b from-cyan-500/10 via-transparent to-transparent blur-3xl" />
        <div className="absolute right-8 top-1/3 h-48 w-48 rounded-full bg-purple-500/10 blur-3xl" />
        <div className="absolute left-10 bottom-10 h-40 w-40 rounded-full bg-cyan-500/10 blur-2xl" />
      </div>

      <div className="relative mx-auto flex max-w-5xl flex-col gap-10 px-4 py-12 lg:flex-row lg:items-center min-h-screen">
        {/* Left side - Info */}
        <div className="space-y-6 lg:w-1/2">
          <div className="inline-flex items-center gap-2 rounded-full bg-white/5 px-3 py-1 text-sm text-cyan-100 ring-1 ring-white/10">
            <span className="h-2 w-2 rounded-full bg-emerald-400" />
            Acceso corporativo
          </div>

          <div className="space-y-3">
            <h1 className="text-3xl font-semibold leading-tight md:text-4xl">
              Emma Intelligence
            </h1>
            <p className="text-lg text-slate-300">
              Plataforma de inteligencia empresarial centralizada.
              Accede con tus credenciales corporativas.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {[
              'Acceso empresarial',
              'Single Sign-On',
              'Integración AD/LDAP',
              'Emma IA',
            ].map((item) => (
              <div
                key={item}
                className="flex items-start gap-3 rounded-xl border border-white/10 bg-black/30 px-3 py-2"
              >
                <IconCircleCheck className="mt-0.5 h-4 w-4 text-emerald-400" />
                <span className="text-sm text-slate-200">{item}</span>
              </div>
            ))}
          </div>

          <div className="flex items-center gap-2 text-sm text-slate-300">
            <span className="inline-flex items-center gap-2 rounded-full bg-white/5 px-3 py-1 ring-1 ring-white/10">
              <IconShield className="h-4 w-4 text-cyan-300" />
              Autenticación empresarial
            </span>
          </div>
        </div>

        {/* Right side - Auth Component */}
        <div className="lg:w-1/2">
          <div className="rounded-2xl border border-white/10 bg-[#0c1222]/90 p-8 shadow-2xl shadow-black/40 backdrop-blur">
            <div className="flex flex-col items-center gap-6">
              {/* Logo */}
              <div className="rounded-xl bg-primary/10 p-4">
                <IconBrain className="h-10 w-10 text-cyan-400" />
              </div>

              {error ? (
                <>
                  <div className="text-center">
                    <h2 className="text-xl font-semibold mb-2">
                      Error de Autenticación
                    </h2>
                    <p className="text-sm text-slate-300 mb-4">{error}</p>
                  </div>
                  <Button
                    onClick={handleLogin}
                    disabled={isRedirecting}
                    className="bg-cyan-400 text-slate-900 hover:bg-cyan-300"
                  >
                    {isRedirecting ? (
                      <>
                        <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                        Conectando...
                      </>
                    ) : (
                      'Reintentar'
                    )}
                  </Button>
                </>
              ) : isRedirecting ? (
                <>
                  <IconLoader2 className="h-8 w-8 animate-spin text-cyan-400" />
                  <div className="text-center">
                    <h2 className="text-xl font-semibold mb-2">
                      Conectando con KeyCloak
                    </h2>
                    <p className="text-sm text-slate-300">
                      Redirigiendo al servidor de autenticación...
                    </p>
                  </div>
                </>
              ) : (
                <>
                  <div className="text-center">
                    <h2 className="text-xl font-semibold mb-2">
                      Iniciar Sesión
                    </h2>
                    <p className="text-sm text-slate-300 mb-6">
                      Accede con tus credenciales corporativas
                    </p>
                  </div>
                  <Button
                    onClick={handleLogin}
                    disabled={!isLoaded}
                    className="w-full bg-cyan-400 text-slate-900 hover:bg-cyan-300 font-medium py-3"
                  >
                    {!isLoaded ? (
                      <>
                        <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                        Cargando...
                      </>
                    ) : (
                      <>
                        <IconShield className="mr-2 h-4 w-4" />
                        Continuar con SSO
                      </>
                    )}
                  </Button>
                  <p className="text-xs text-slate-400 text-center mt-4">
                    Serás redirigido a KeyCloak para autenticarte
                  </p>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
