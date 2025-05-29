// frontend/app/routes/dashboard+/_layout.tsx
import type { LoaderFunctionArgs, TypedResponse } from '@remix-run/node'
import { Outlet, useLoaderData } from '@remix-run/react'
import { json, redirect } from '@remix-run/node'
import { getAuth } from '@clerk/remix/ssr.server'

import { createApiService } from '#app/utils/backend.server'
import { createStripeApiService } from '#app/services/stripe-api.server'
import { PLANS } from '#app/modules/stripe/plans'
import { ROUTE_PATH as ONBOARDING_USERNAME_PATH } from '#app/routes/onboarding+/username'

import { Navigation } from '#app/components/navigation'
import { Header } from '#app/components/header'

export const ROUTE_PATH = '/dashboard' as const
export const SIGN_IN_PATH = '/auth/sign-in' as const


export type LoaderData = Exclude<
  Awaited<ReturnType<typeof loader>>,
  Response | TypedResponse<unknown>
>

export const loader = async (args: LoaderFunctionArgs) => {
  const { request } = args
  const { userId } = await getAuth(args)

  if (!userId) {
    const params = new URLSearchParams()
    params.set("redirect_url", new URL(request.url).pathname)
    return redirect(`${SIGN_IN_PATH}?${params.toString()}`)
  }

  // Variables para tracking de estado
  let backendConnected = false
  let planId = PLANS.FREE
  let isAdmin = false
  let needsOnboarding = false
  let error: string | null = null

  try {
    // Intentar conectar con el backend para datos adicionales
    const apiService = await createApiService(args)
    
    const [userResult, stripeResult] = await Promise.allSettled([
      apiService.getCurrentUser(),
      createStripeApiService(args).then(service => service.getCurrentSubscription())
    ])

    // Procesar resultado del usuario del backend
    if (userResult.status === 'fulfilled' && userResult.value) {
      const backendUser = userResult.value
      backendConnected = true
      
      // Verificar si necesita completar onboarding
      if (!backendUser.username) {
        needsOnboarding = true
      }
      
      // Verificar permisos de admin
      isAdmin = backendUser.roles?.some((role: any) => role.name === 'admin') || 
                backendUser.is_superuser || 
                false
    } else {
      console.warn('No se pudo obtener usuario del backend:', userResult.status === 'rejected' ? userResult.reason : 'Sin datos')
    }

    // Procesar resultado de suscripción
    if (stripeResult.status === 'fulfilled' && stripeResult.value) {
      planId = stripeResult.value.plan_id || PLANS.FREE
    } else {
      console.warn('No se pudo obtener suscripción:', stripeResult.status === 'rejected' ? stripeResult.reason : 'Sin datos')
    }

  } catch (err) {
    console.error('Error general en dashboard loader:', err)
    error = err instanceof Error ? err.message : 'Error desconocido'
    backendConnected = false
  }

  // Redireccionar a onboarding si es necesario
  if (needsOnboarding && backendConnected) {
    return redirect(ONBOARDING_USERNAME_PATH)
  }

  return json({
    planId,
    isAdmin,
    backendConnected,
    clerkUserId: userId,
    error,
    needsOnboarding
  })
}

export default function Dashboard() {
  const { 
    planId, 
    isAdmin, 
    backendConnected, 
    error, 
    needsOnboarding 
  } = useLoaderData<typeof loader>()

  return (
    <div className="flex min-h-[100vh] w-full flex-col bg-secondary dark:bg-black">
      {/* Navigation usando solo componentes Clerk + datos mínimos de negocio */}
      <Navigation 
        planId={planId}
        isAdmin={isAdmin}
        backendConnected={backendConnected}
      />
      
      {/* Header simplificado - Clerk maneja datos de usuario */}
      <Header />
      
      {/* Indicadores de estado */}
      {!backendConnected && (
        <div className="bg-yellow-50 dark:bg-yellow-900/20 border-l-4 border-yellow-400 p-4">
          <div className="flex">
            <div className="ml-3">
              <p className="text-sm text-yellow-700 dark:text-yellow-200">
                <strong>Modo sin conexión:</strong> Algunas funcionalidades pueden estar limitadas. 
                La aplicación funciona con los componentes de Clerk.
                {error && ` Error técnico: ${error}`}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Banner de onboarding pendiente */}
      {needsOnboarding && backendConnected && (
        <div className="bg-blue-50 dark:bg-blue-900/20 border-l-4 border-blue-400 p-4">
          <div className="flex">
            <div className="ml-3">
              <p className="text-sm text-blue-700 dark:text-blue-200">
                <strong>Configuración pendiente:</strong> Completa tu perfil para acceder a todas las funciones.
              </p>
            </div>
          </div>
        </div>
      )}
      
      <Outlet />
    </div>
  )
}