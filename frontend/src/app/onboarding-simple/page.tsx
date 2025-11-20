'use client'

import { useEffect, useState, useCallback, Suspense } from 'react'
import { useUser } from '@clerk/nextjs'
import { useRouter, useSearchParams } from 'next/navigation'
import { Loader2, Zap, CheckCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card'
import { useUserContext } from '@/contexts/user-context'

function SimpleOnboardingContent() {
  const { user: clerkUser, isLoaded: isClerkLoaded } = useUser()
  const { syncUserWithBackend, backendUser, userLoading, userError, onboarding, markOnboardingComplete, refetchUser } = useUserContext()
  const router = useRouter()
  const searchParams = useSearchParams()
  const [status, setStatus] = useState<'loading' | 'creating' | 'syncing' | 'selecting_plan' | 'success' | 'error'>('loading')
  const [errorMessage, setErrorMessage] = useState('')

  // This flag controls when the plan selection UI is shown
  const [showPlanSelection, setShowPlanSelection] = useState(false)

  useEffect(() => {
    if (!isClerkLoaded) return

    if (!clerkUser) {
      router.push('/auth/sign-up?plan=free')
      return
    }

    if (userLoading) {
      setStatus('loading')
      return
    }

    // If user is already synced and onboarding is complete, redirect
    if (onboarding.hasCompletedSync && !onboarding.needsOnboarding && backendUser?.tenant_id) {
      router.push(`/${backendUser.tenant_id}/dashboard`)
      return
    }

    // If user needs sync, proceed to sync
    if (!onboarding.hasCompletedSync || onboarding.isNewUser) {
      handleUserSync()
      return
    }

    // If user is synced but needs onboarding (i.e., needs to select a plan)
    if (onboarding.hasCompletedSync && onboarding.needsOnboarding && !showPlanSelection) {
      setStatus('selecting_plan')
      setShowPlanSelection(true)
      return
    }

  }, [isClerkLoaded, clerkUser, userLoading, onboarding, backendUser, router, syncUserWithBackend, showPlanSelection])

  const handleUserSync = async () => {
    if (!clerkUser) return

    setStatus('syncing')

    try {
      const syncedUser = await syncUserWithBackend()

      if (syncedUser) {
        // After sync, if onboarding is still needed, show plan selection
        // The `onboarding` state will be updated by `useUserContext` after `syncUserWithBackend`
        // so the useEffect above will catch the `onboarding.needsOnboarding` state.
        await refetchUser() // Ensure we have the latest onboarding status
        if (onboarding.needsOnboarding) {
           setStatus('selecting_plan')
           setShowPlanSelection(true)
        } else if (syncedUser.tenant_id) {
           // If onboarding is somehow already complete, redirect to dashboard
           router.push(`/${syncedUser.tenant_id}/dashboard`)
        } else {
          // Fallback if tenant_id is missing after sync
          setErrorMessage('Failed to get tenant ID after sync. Please try again.')
          setStatus('error')
        }
      } else {
        throw new Error('Failed to sync user with backend.')
      }
    } catch (error) {
      console.error('Error syncing user:', error)
      setErrorMessage(error instanceof Error ? error.message : 'Unknown error')
      setStatus('error')
    }
  }

  const handleChooseProTrial = useCallback(async () => {
    if (!backendUser) return
    setStatus('creating')
    try {
      const success = await markOnboardingComplete({
        selected_plan: 'pro', // Assuming 'pro' for trial
        onboarding_step: 'plan_selected' // Custom field for tracking
      })
      if (success && backendUser.tenant_id) {
        router.push(`/${backendUser.tenant_id}/dashboard`)
      } else if (success) {
        router.push('/dashboard') // Fallback
      }
      else {
        throw new Error('Failed to activate Pro Trial.')
      }
    } catch (error) {
      console.error('Error activating Pro Trial:', error)
      setErrorMessage(error instanceof Error ? error.message : 'Unknown error')
      setStatus('error')
    }
  }, [backendUser, markOnboardingComplete, router])

  const handleChooseFreePlan = useCallback(async () => {
    if (!backendUser) return
    setStatus('creating')
    try {
      const success = await markOnboardingComplete({
        selected_plan: 'free',
        onboarding_step: 'plan_selected'
      })
      if (success && backendUser.tenant_id) {
        router.push(`/${backendUser.tenant_id}/dashboard`)
      } else if (success) {
        router.push('/dashboard') // Fallback
      }
      else {
        throw new Error('Failed to select Free Plan.')
      }
    } catch (error) {
      console.error('Error selecting Free Plan:', error)
      setErrorMessage(error instanceof Error ? error.message : 'Unknown error')
      setStatus('error')
    }
  }, [backendUser, markOnboardingComplete, router])

  // Auto-select plan if available in metadata or URL params
  useEffect(() => {
    if (status === 'selecting_plan' && showPlanSelection && clerkUser) {
      const unsafeMetadata = clerkUser.unsafeMetadata as any
      const publicMetadata = clerkUser.publicMetadata as any
      
      // Check URL param first, then metadata
      const urlPlan = searchParams.get('plan')
      const selectedPlan = urlPlan || unsafeMetadata?.selected_plan || publicMetadata?.selected_plan

      if (selectedPlan) {
        console.log('Auto-selecting plan:', selectedPlan, 'Source:', urlPlan ? 'URL' : 'Metadata')
        if (selectedPlan === 'pro') {
          handleChooseProTrial()
        } else {
          // Default to free for any other plan or explicit free
          handleChooseFreePlan()
        }
      }
    }
  }, [status, showPlanSelection, clerkUser, searchParams, handleChooseProTrial, handleChooseFreePlan])

  if (status === 'loading' || status === 'syncing' || status === 'creating') {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center space-y-4">
          <Loader2 className="h-8 w-8 animate-spin mx-auto" />
          <p className="text-muted-foreground">
            {status === 'loading' ? 'Cargando...' : status === 'syncing' ? 'Sincronizando tu cuenta...' : 'Aplicando tu plan...'}
          </p>
        </div>
      </div>
    )
  }

  if (status === 'error') {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center space-y-4 max-w-md">
          <h2 className="text-2xl font-bold text-red-600">Error</h2>
          <p className="text-muted-foreground">{errorMessage || userError}</p>
          <Button onClick={handleUserSync}>Reintentar Sincronización</Button>
          <Button variant="outline" onClick={() => router.push('/pricing')}>
            Volver a Pricing
          </Button>
        </div>
      </div>
    )
  }

  if (status === 'selecting_plan' && showPlanSelection) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4 bg-background">
        <Card className="max-w-xl w-full text-center shadow-lg">
          <CardHeader>
            <CardTitle className="text-3xl font-bold">Cómo quieres empezar?</CardTitle>
            <CardDescription className="text-lg text-muted-foreground mt-2">
              Elige tu plan para comenzar con Nexus Documents.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6 md:space-y-0 md:grid md:grid-cols-2 md:gap-6">
            {/* Pro Trial Option */}
            <div className="flex flex-col items-center p-6 border rounded-lg shadow-sm bg-purple-50 dark:bg-purple-950/20">
              <Zap className="h-12 w-12 text-purple-600 mb-4" />
              <h3 className="text-xl font-semibold mb-2">Pro Trial</h3>
              <p className="text-muted-foreground mb-4">14 días gratis, sin tarjeta de crédito.</p>
              <Button onClick={handleChooseProTrial} className="w-full">
                Empezar Prueba Pro
              </Button>
            </div>

            {/* Free Plan Option */}
            <div className="flex flex-col items-center p-6 border rounded-lg shadow-sm bg-gray-50 dark:bg-gray-900/20">
              <CheckCircle className="h-12 w-12 text-green-600 mb-4" />
              <h3 className="text-xl font-semibold mb-2">Plan Gratuito</h3>
              <p className="text-muted-foreground mb-4">Siempre gratis, con funcionalidades básicas.</p>
              <Button onClick={handleChooseFreePlan} variant="outline" className="w-full">
                Continuar con Gratis
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (status === 'success') {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center space-y-4">
          <h2 className="text-2xl font-bold text-green-600">¡Cuenta configurada!</h2>
          <p className="text-muted-foreground">
            Redirigiendo al dashboard...
          </p>
          <Loader2 className="h-6 w-6 animate-spin mx-auto" />
        </div>
      </div>
    )
  }

  return null
}

export default function SimpleOnboardingPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    }>
      <SimpleOnboardingContent />
    </Suspense>
  )
}
