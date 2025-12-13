'use client'

import Link from 'next/link'
import { SignIn } from '@clerk/nextjs'
import { Button } from '@/components/ui/button'
import { CheckCircle, Loader2 } from 'lucide-react'

export default function Page() {
  return (
    <div className="relative min-h-screen overflow-hidden bg-[#05070d] text-white">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute inset-x-0 top-0 h-40 bg-gradient-to-b from-cyan-500/10 via-transparent to-transparent blur-3xl" />
        <div className="absolute right-8 top-1/3 h-48 w-48 rounded-full bg-purple-500/10 blur-3xl" />
        <div className="absolute left-10 bottom-10 h-40 w-40 rounded-full bg-cyan-500/10 blur-2xl" />
      </div>

      <div className="relative mx-auto flex max-w-5xl flex-col gap-10 px-4 py-12 lg:flex-row lg:items-center">
        <div className="space-y-6 lg:w-1/2">
          <div className="inline-flex items-center gap-2 rounded-full bg-white/5 px-3 py-1 text-sm text-cyan-100 ring-1 ring-white/10">
            <span className="h-2 w-2 rounded-full bg-emerald-400" />
            Acceso seguro
          </div>
          <div className="space-y-3">
            <h1 className="text-3xl font-semibold leading-tight md:text-4xl">Bienvenido de vuelta</h1>
            <p className="text-lg text-slate-300">
              Ingresa para continuar donde lo dejaste y seguir colaborando con tu equipo.
            </p>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {['Dashboard en vivo', 'Búsqueda con IA', 'Firmas digitales', 'Soporte prioritario'].map((item) => (
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
              <Loader2 className="h-4 w-4 animate-spin text-cyan-300" />
              Sesión protegida con Clerk
            </span>
            <Link href="/auth/sign-up" className="text-cyan-200 hover:text-white">
              ¿No tienes cuenta? Regístrate
            </Link>
          </div>
        </div>

        <div className="lg:w-1/2">
          <div className="rounded-2xl border border-white/10 bg-[#0c1222]/90 p-6 shadow-2xl shadow-black/40 backdrop-blur">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <p className="text-sm text-slate-300">Accede a tu espacio</p>
                <p className="text-lg font-semibold">Inicia sesión</p>
              </div>
              <div className="rounded-full bg-white/5 px-3 py-1 text-xs text-slate-200">
                Soporta SSO y correo
              </div>
            </div>
            <div className="flex justify-center">
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
                    socialButtonsBlockButton: 'bg-white/5 border-white/10 text-white hover:bg-white/10',
                    formButtonPrimary: 'bg-cyan-400 hover:bg-cyan-300 text-slate-900 font-semibold',
                    formButtonPrimary__disabled: 'bg-cyan-400/60',
                    formFieldInput: 'bg-[#0b1220] border border-white/10 text-white focus:border-cyan-400 focus:ring-0',
                    formFieldLabel: 'text-slate-200',
                    footerActionText: 'text-slate-300',
                    footerActionLink: 'text-cyan-200 hover:text-white',
                  },
                }}
                signUpUrl="/auth/sign-up"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
