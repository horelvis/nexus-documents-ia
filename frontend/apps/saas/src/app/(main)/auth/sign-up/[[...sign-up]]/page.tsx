'use client'

import { useEffect, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { SignUp, useAuth, useUser } from '@clerk/nextjs'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { STRIPE_PLANS, type PlanId } from '@/lib/stripe-plans'
import { CheckCircle, Loader2 } from 'lucide-react'

function SignUpContent() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const { isSignedIn, isLoaded } = useAuth()
  const { user } = useUser()

  const rawPlan = (searchParams.get('plan') || '').toLowerCase()
  const planId = (rawPlan in STRIPE_PLANS ? rawPlan : 'free') as PlanId
  const rawInterval = (searchParams.get('interval') || 'month').toLowerCase()
  const interval =
    rawInterval === 'yearly'
      ? 'year'
      : rawInterval === 'monthly'
        ? 'month'
        : rawInterval
  const invitation = searchParams.get('invitation')
  const tenantId = searchParams.get('tenant')

  const selectedPlan = STRIPE_PLANS[planId]

  useEffect(() => {
    if (isLoaded && isSignedIn && user) {
      router.push('/dashboard')
      return
    }

    const planParam = searchParams.get('plan')
    if (!planParam && !invitation) {
      router.replace('/pricing')
    }
  }, [isLoaded, isSignedIn, user, router, searchParams, invitation])

  const getPlanBadgeColor = (currentPlanId: string) => {
    switch (currentPlanId) {
      case 'pro':
        return 'bg-cyan-500/20 text-cyan-100 border border-cyan-500/30'
      case 'enterprise':
        return 'bg-purple-500/20 text-purple-100 border border-purple-500/30'
      default:
        return 'bg-white/5 text-white border border-white/10'
    }
  }

  const shortFeatures = selectedPlan.features.slice(0, 4)
  const displayPrice =
    selectedPlan.price && selectedPlan.price > 0
      ? `$${selectedPlan.price}/${interval === 'year' ? 'año' : 'mes'}`
      : selectedPlan.customPricing
        ? 'Hablemos'
        : 'Incluido'

  return (
    <div className="relative min-h-screen overflow-hidden bg-[#05070d] text-white">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute inset-x-0 top-0 h-48 bg-gradient-to-b from-cyan-500/10 via-transparent to-transparent blur-3xl" />
        <div className="absolute left-12 top-1/3 h-48 w-48 rounded-full bg-purple-500/10 blur-3xl" />
        <div className="absolute right-10 bottom-10 h-40 w-40 rounded-full bg-cyan-500/10 blur-2xl" />
      </div>

      <div className="relative mx-auto flex max-w-6xl flex-col gap-10 px-4 py-12 lg:flex-row lg:items-start">
        <div className="space-y-6 lg:w-1/2">
          <div className="inline-flex items-center gap-2 rounded-full bg-white/5 px-3 py-1 text-sm text-cyan-100 ring-1 ring-white/10">
            <span className="h-2 w-2 rounded-full bg-emerald-400" />
            {invitation ? 'Acceso por invitación' : 'Plan seleccionado'}
          </div>

          <div className="space-y-3">
            <h1 className="text-3xl font-semibold leading-tight md:text-4xl">
              {invitation ? 'Únete al equipo y colabora en segundos' : 'Crea tu cuenta en Nexus'}
            </h1>
            <p className="text-lg text-slate-300">
              {invitation
                ? 'Confirma tu información y tendrás todo listo para trabajar con tu equipo.'
                : 'Regístrate y empieza a centralizar tus documentos con IA desde el primer día.'}
            </p>
          </div>

          <Card className="border-white/10 bg-white/5 shadow-2xl shadow-black/40 backdrop-blur">
            <CardHeader className="flex flex-row items-start justify-between gap-3">
              <div>
                <p className="text-sm uppercase tracking-wide text-slate-400">Plan</p>
                <div className="mt-1 flex items-center gap-3">
                  <Badge className={getPlanBadgeColor(selectedPlan.id)}>{selectedPlan.name}</Badge>
                  <span className="text-sm text-slate-300">{selectedPlan.description}</span>
                </div>
              </div>
              <div className="text-right">
                <p className="text-xs uppercase text-slate-400">Precio</p>
                <p className="text-xl font-semibold">{displayPrice}</p>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {shortFeatures.map((feature, index) => (
                  <div
                    key={index}
                    className="flex items-start gap-3 rounded-xl border border-white/10 bg-black/30 px-3 py-2"
                  >
                    <CheckCircle className="mt-0.5 h-4 w-4 text-emerald-400" />
                    <span className="text-sm text-slate-200">{feature}</span>
                  </div>
                ))}
              </div>
              <div className="flex items-center justify-between rounded-xl bg-black/40 px-4 py-3 text-sm text-slate-300 ring-1 ring-white/10">
                <div className="flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin text-cyan-300" />
                  <span>Configuraremos tu espacio tras el registro.</span>
                </div>
                <Button
                  variant="ghost"
                  className="h-8 px-3 text-sm text-cyan-200 hover:text-white"
                  onClick={() => router.push('/pricing')}
                >
                  Cambiar plan
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="lg:w-1/2">
          <div className="rounded-2xl border border-white/10 bg-[#0c1222]/90 p-6 shadow-2xl shadow-black/40 backdrop-blur">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <p className="text-sm text-slate-300">Paso 1 de 2</p>
                <p className="text-lg font-semibold">Crea tu cuenta</p>
              </div>
              <div className="rounded-full bg-white/5 px-3 py-1 text-xs text-slate-200">
                Sin tarjeta requerida
              </div>
            </div>
            <div className="flex justify-center">
              <SignUp
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
                unsafeMetadata={{
                  invitation_code: invitation || undefined,
                  tenant_id: tenantId || undefined,
                  selected_plan: planId,
                  selected_interval: interval,
                }}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function SignUpPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      }
    >
      <SignUpContent />
    </Suspense>
  )
}
