'use client'

/**
 * SSO Sign-In Page for NouxCube AI On-Premise
 *
 * Redirects to KeyCloak for OIDC authentication.
 * Uses Authorization Code flow with PKCE.
 */

import { useEffect, useState } from 'react'
import Image from 'next/image'
import {
  IconLoader2,
  IconShield,
  IconLock,
  IconCpu,
  IconBrain,
  IconScale,
  IconRoute,
  IconPlugConnected,
  IconSearch
} from '@tabler/icons-react'
import { Button } from '@nexus/shared/ui'
import { useAuth } from '@/contexts/auth-context'

export default function SignInPage() {
  const { isLoaded, isAuthenticated, login } = useAuth()
  const [error, setError] = useState<string | null>(null)
  const [isRedirecting, setIsRedirecting] = useState(false)

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const errorParam = params.get('error')
    if (errorParam) {
      setError(errorParam === 'callback_failed'
        ? 'No se pudo completar la autenticación. Por favor, intente de nuevo.'
        : errorParam
      )
      return
    }

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
    } catch (err) {
      console.error('[SignIn] Error:', err)
      setError(err instanceof Error ? err.message : 'Error al iniciar autenticación')
      setIsRedirecting(false)
    }
  }

  const features = [
    { icon: IconCpu, label: 'vLLM + Qwen3', desc: 'GPU local, sin APIs externas' },
    { icon: IconBrain, label: 'Emma AI', desc: '12 agentes especializados' },
    { icon: IconRoute, label: 'SLM Router', desc: 'Query planning con TOON' },
    { icon: IconSearch, label: 'RAG 7 Capas', desc: 'Búsqueda híbrida + reranking' },
    { icon: IconScale, label: 'BOE Legal', desc: '47+ leyes españolas indexadas' },
    { icon: IconPlugConnected, label: 'Conectores', desc: 'Alfresco, SharePoint, DB' },
  ]

  return (
    <div className="relative min-h-screen overflow-hidden bg-[#05070d] text-white">
      {/* Background effects */}
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute inset-x-0 top-0 h-[500px] bg-gradient-to-b from-cyan-500/8 via-transparent to-transparent" />
        <div className="absolute right-0 top-1/4 h-[600px] w-[600px] rounded-full bg-cyan-500/5 blur-[120px]" />
        <div className="absolute -left-20 bottom-0 h-[400px] w-[400px] rounded-full bg-cyan-400/5 blur-[100px]" />
        <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNjAiIGhlaWdodD0iNjAiIHZpZXdCb3g9IjAgMCA2MCA2MCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48ZyBmaWxsPSJub25lIiBmaWxsLXJ1bGU9ImV2ZW5vZGQiPjxnIGZpbGw9IiMyMjIiIGZpbGwtb3BhY2l0eT0iMC4wMyI+PGNpcmNsZSBjeD0iMSIgY3k9IjEiIHI9IjEiLz48L2c+PC9nPjwvc3ZnPg==')] opacity-50" />
      </div>

      <div className="relative mx-auto flex min-h-screen max-w-6xl flex-col items-center justify-center gap-12 px-4 py-12 lg:flex-row lg:gap-20">
        {/* Left side - Branding */}
        <div className="flex flex-col items-center space-y-8 lg:w-1/2 lg:items-start">
          {/* Logo */}
          <Image
            src="/logo-full.png"
            alt="NouxCube AI"
            width={280}
            height={70}
            className="h-auto w-[240px] md:w-[280px]"
            priority
          />

          <div className="space-y-4 text-center lg:text-left">
            <p className="max-w-md text-lg text-slate-300">
              Gestión documental inteligente con IA 100% local. Privacidad total, sin dependencias externas.
            </p>
            <div className="inline-flex items-center gap-2 rounded-full bg-cyan-500/10 px-4 py-2 text-sm text-cyan-300 ring-1 ring-cyan-500/20">
              <span className="h-2 w-2 animate-pulse rounded-full bg-cyan-400" />
              On-Premise · GDPR Ready · Air-Gap Compatible
            </div>
          </div>

          {/* Features */}
          <div className="grid w-full max-w-lg grid-cols-2 gap-3 sm:grid-cols-3">
            {features.map(({ icon: Icon, label, desc }) => (
              <div
                key={label}
                className="flex items-start gap-3 rounded-xl border border-white/5 bg-white/[0.02] px-4 py-3 transition-colors hover:bg-white/[0.04]"
              >
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-cyan-500/10">
                  <Icon className="h-5 w-5 text-cyan-400" />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-white">{label}</p>
                  <p className="text-xs text-slate-400">{desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right side - Auth Card */}
        <div className="w-full max-w-md lg:w-[420px]">
          <div className="rounded-2xl border border-white/10 bg-gradient-to-b from-white/[0.08] to-white/[0.02] p-8 shadow-2xl shadow-black/50 backdrop-blur-xl">
            <div className="flex flex-col items-center gap-6">
              {/* Card Logo */}
              <div className="relative">
                <div className="absolute -inset-4 rounded-full bg-cyan-500/20 blur-xl" />
                <Image
                  src="/logo-single.png"
                  alt="NouxCube"
                  width={80}
                  height={80}
                  className="relative h-16 w-auto"
                />
              </div>

              {error && (
                <div className="w-full rounded-lg border border-red-500/20 bg-red-500/10 p-3 text-center">
                  <p className="text-sm text-red-300">{error}</p>
                </div>
              )}

              <div className="text-center">
                <h2 className="mb-2 text-2xl font-semibold text-white">
                  Bienvenido
                </h2>
                <p className="text-sm text-slate-400">
                  Accede con tus credenciales corporativas
                </p>
              </div>

              <Button
                onClick={handleLogin}
                disabled={!isLoaded || isRedirecting}
                className="h-12 w-full bg-gradient-to-r from-cyan-500 to-cyan-400 font-medium text-slate-900 shadow-lg shadow-cyan-500/25 transition-all hover:from-cyan-400 hover:to-cyan-300 hover:shadow-cyan-500/40 disabled:opacity-50"
              >
                {!isLoaded || isRedirecting ? (
                  <>
                    <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                    {isRedirecting ? 'Conectando...' : 'Cargando...'}
                  </>
                ) : (
                  <>
                    <IconShield className="mr-2 h-5 w-5" />
                    Continuar con SSO
                  </>
                )}
              </Button>

              <div className="flex items-center gap-2 text-xs text-slate-500">
                <IconLock className="h-3 w-3" />
                <span>Conexión segura con KeyCloak</span>
              </div>
            </div>
          </div>

          {/* Footer */}
          <p className="mt-6 text-center text-xs text-slate-600">
            © {new Date().getFullYear()} NouxCube AI. Todos los derechos reservados.
          </p>
        </div>
      </div>
    </div>
  )
}
