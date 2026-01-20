'use client'

/**
 * Universal Sign-In Page
 *
 * Supports both authentication modes:
 * - SaaS mode: Shows Clerk SignIn component
 * - On-premise mode: Redirects to SSO provider or shows SSO login UI
 */

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { SignIn } from '@clerk/nextjs'
import { Button } from '@/components/ui/button'
import { CheckCircle, Loader2, LogIn, Shield, Brain } from 'lucide-react'
import {
  useFeature,
  Feature,
  useDeploymentMode,
  DeploymentMode,
} from '@/lib/features'

/**
 * SSO Login Component
 *
 * For on-premise deployments using OIDC/SAML/LDAP.
 * Automatically redirects to SSO provider on mount.
 */
function SSOSignIn() {
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [providerInfo, setProviderInfo] = useState<string | null>(null)

  useEffect(() => {
    async function initiateSSO() {
      try {
        // Get login URL from backend
        const response = await fetch('/api/v1/auth/sso/login-url')
        if (!response.ok) {
          throw new Error('Failed to get SSO login URL')
        }

        const data = await response.json()
        setProviderInfo(data.provider)

        // Redirect to SSO provider
        if (data.login_url) {
          window.location.href = data.login_url
        } else {
          throw new Error('No login URL returned')
        }
      } catch (err) {
        console.error('[SSOSignIn] Error:', err)
        setError(err instanceof Error ? err.message : 'SSO login failed')
        setIsLoading(false)
      }
    }

    initiateSSO()
  }, [])

  if (error) {
    return (
      <div className="flex flex-col items-center gap-4 p-6">
        <div className="rounded-full bg-red-500/10 p-3">
          <Shield className="h-8 w-8 text-red-400" />
        </div>
        <h2 className="text-lg font-semibold text-white">Error de Autenticación</h2>
        <p className="text-center text-sm text-slate-300">{error}</p>
        <Button
          onClick={() => window.location.reload()}
          className="bg-cyan-400 text-slate-900 hover:bg-cyan-300"
        >
          Reintentar
        </Button>
      </div>
    )
  }

  return (
    <div className="flex flex-col items-center gap-4 p-6">
      <div className="rounded-full bg-cyan-500/10 p-3">
        <Loader2 className="h-8 w-8 animate-spin text-cyan-400" />
      </div>
      <h2 className="text-lg font-semibold text-white">Conectando con SSO</h2>
      <p className="text-center text-sm text-slate-300">
        Redirigiendo al servidor de autenticación...
        {providerInfo && <span className="block mt-1 text-xs">({providerInfo})</span>}
      </p>
    </div>
  )
}

/**
 * Clerk Sign-In Component
 *
 * For SaaS deployments using Clerk authentication.
 */
function ClerkSignIn() {
  return (
    <SignIn
      appearance={{
        variables: {
          colorPrimary: '#22d3ee',
          colorText: '#e5e7eb',
          colorBackground: '#0c1222',
          colorInputBackground: '#0b1220',
          colorInputText: '#e5e7eb',
          colorDanger: '#f87171',
          borderRadius: '12px',
          fontFamily: 'Inter, system-ui, -apple-system, sans-serif',
        },
        elements: {
          rootBox: 'w-full flex justify-center',
          card: 'bg-transparent shadow-none border-0 p-0 max-w-md',
          headerTitle: 'text-white text-2xl font-semibold',
          headerSubtitle: 'text-slate-300',
          socialButtonsBlockButton:
            'bg-white/5 border-white/10 text-white hover:bg-white/10',
          formButtonPrimary:
            'bg-cyan-400 hover:bg-cyan-300 text-slate-900 font-semibold',
          formButtonPrimary__disabled: 'bg-cyan-400/60',
          formFieldInput:
            'bg-[#0b1220] border border-white/10 text-white focus:border-cyan-400 focus:ring-0',
          formFieldLabel: 'text-slate-200',
          footerActionText: 'text-slate-300',
          footerActionLink: 'text-cyan-200 hover:text-white',
        },
      }}
      signUpUrl="/auth/sign-up"
    />
  )
}

export default function SignInPage() {
  const deploymentMode = useDeploymentMode()
  const useClerk = useFeature(Feature.CLERK_AUTH)
  const [isHydrated, setIsHydrated] = useState(false)

  // Wait for hydration
  useEffect(() => {
    setIsHydrated(true)
  }, [])

  // Determine auth mode
  const isClerkMode = deploymentMode === DeploymentMode.SAAS && useClerk
  const isSSOMode = !isClerkMode

  // Features to display based on mode
  const features = isSSOMode
    ? ['Acceso empresarial', 'Single Sign-On', 'Integración AD/LDAP', 'Emma IA']
    : ['Dashboard en vivo', 'Búsqueda con IA', 'Firmas digitales', 'Soporte prioritario']

  return (
    <div className="relative min-h-screen overflow-hidden bg-[#05070d] text-white">
      {/* Background effects */}
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute inset-x-0 top-0 h-40 bg-gradient-to-b from-cyan-500/10 via-transparent to-transparent blur-3xl" />
        <div className="absolute right-8 top-1/3 h-48 w-48 rounded-full bg-purple-500/10 blur-3xl" />
        <div className="absolute left-10 bottom-10 h-40 w-40 rounded-full bg-cyan-500/10 blur-2xl" />
      </div>

      <div className="relative mx-auto flex max-w-5xl flex-col gap-10 px-4 py-12 lg:flex-row lg:items-center">
        {/* Left side - Info */}
        <div className="space-y-6 lg:w-1/2">
          <div className="inline-flex items-center gap-2 rounded-full bg-white/5 px-3 py-1 text-sm text-cyan-100 ring-1 ring-white/10">
            <span className="h-2 w-2 rounded-full bg-emerald-400" />
            {isSSOMode ? 'Acceso corporativo' : 'Acceso seguro'}
          </div>

          <div className="space-y-3">
            <h1 className="text-3xl font-semibold leading-tight md:text-4xl">
              {isSSOMode ? 'Emma Intelligence' : 'Bienvenido de vuelta'}
            </h1>
            <p className="text-lg text-slate-300">
              {isSSOMode
                ? 'Plataforma de inteligencia empresarial centralizada. Accede con tus credenciales corporativas.'
                : 'Ingresa para continuar donde lo dejaste y seguir colaborando con tu equipo.'}
            </p>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {features.map((item) => (
              <div
                key={item}
                className="flex items-start gap-3 rounded-xl border border-white/10 bg-black/30 px-3 py-2"
              >
                <CheckCircle className="mt-0.5 h-4 w-4 text-emerald-400" />
                <span className="text-sm text-slate-200">{item}</span>
              </div>
            ))}
          </div>

          <div className="flex flex-col gap-3 text-sm text-slate-300 sm:flex-row sm:items-center">
            <span className="inline-flex items-center gap-2 rounded-full bg-white/5 px-3 py-1 ring-1 ring-white/10">
              {isSSOMode ? (
                <>
                  <Shield className="h-4 w-4 text-cyan-300" />
                  Autenticación empresarial
                </>
              ) : (
                <>
                  <Loader2 className="h-4 w-4 animate-spin text-cyan-300" />
                  Sesión protegida con Clerk
                </>
              )}
            </span>
            {!isSSOMode && (
              <Link href="/auth/sign-up" className="text-cyan-200 hover:text-white">
                ¿No tienes cuenta? Regístrate
              </Link>
            )}
          </div>
        </div>

        {/* Right side - Auth Component */}
        <div className="lg:w-1/2">
          <div className="rounded-2xl border border-white/10 bg-[#0c1222]/90 p-6 shadow-2xl shadow-black/40 backdrop-blur">
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                {isSSOMode && (
                  <div className="rounded-lg bg-primary/10 p-2">
                    <Brain className="h-6 w-6 text-cyan-400" />
                  </div>
                )}
                <div>
                  <p className="text-sm text-slate-300">
                    {isSSOMode ? 'Emma Intelligence' : 'Accede a tu espacio'}
                  </p>
                  <p className="text-lg font-semibold">Inicia sesión</p>
                </div>
              </div>
              <div className="rounded-full bg-white/5 px-3 py-1 text-xs text-slate-200">
                {isSSOMode ? 'SSO Corporativo' : 'Soporta SSO y correo'}
              </div>
            </div>

            <div className="flex justify-center">
              {!isHydrated ? (
                <div className="flex items-center gap-2 py-8">
                  <Loader2 className="h-5 w-5 animate-spin text-cyan-400" />
                  <span className="text-sm text-slate-300">Cargando...</span>
                </div>
              ) : isSSOMode ? (
                <SSOSignIn />
              ) : (
                <ClerkSignIn />
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
