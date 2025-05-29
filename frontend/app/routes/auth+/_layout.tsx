// frontend/app/routes/admin+/_layout.tsx
import type { MetaFunction, LoaderFunctionArgs, TypedResponse } from '@remix-run/node'
import { Outlet, useLoaderData } from '@remix-run/react'
import { json, redirect } from '@remix-run/node'
import { getAuth } from '@clerk/remix/ssr.server'

import { createApiService } from '#app/utils/backend.server'
import { createStripeApiService } from '#app/services/stripe-api.server'
import { PLANS } from '#app/modules/stripe/plans'
import { siteConfig } from '#app/utils/constants/brand'
import { Navigation } from '#app/components/navigation'
import { Header } from '#app/components/header'

export const ROUTE_PATH = '/admin' as const
export const SIGN_IN_PATH = '/auth/sign-in' as const

export const meta: MetaFunction = () => {
  return [{ title: `${siteConfig.siteTitle} - Admin` }]
}

export type LoaderData = Exclude<
  Awaited<ReturnType<typeof loader>>,
  Response | TypedResponse<unknown>
>

export async function loader(args: LoaderFunctionArgs) {
  const { request } = args
  const { userId } = await getAuth(args)

  if (!userId) {
    const params = new URLSearchParams()
    params.set("redirect_url", new URL(request.url).pathname)
    return redirect(`${SIGN_IN_PATH}?${params.toString()}`)
  }

  // Variables de estado
  let backendConnected = false
  let isAdmin = false
  let planId = PLANS.FREE
  let error: string | null = null

  try {
    // Verificar permisos de admin y obtener datos
    const [apiService, stripeService] = await Promise.all([
      createApiService(args),
      createStripeApiService(args)
    ])
    
    const [userResult, subscriptionResult] = await Promise.allSettled([
      apiService.getCurrentUser(),
      stripeService.getCurrentSubscription()
    ])

    // Verificar usuario y permisos
    if (userResult.status === 'fulfilled' && userResult.value) {
      const user = userResult.value
      backendConnected = true
      
      // Verificar permisos de administrador
      isAdmin = user.roles?.some((role: any) => role.name === 'admin') || 
                user.is_superuser || 
                false

      if (!isAdmin) {
        throw new Response('Acceso denegado. Se requieren permisos de administrador.', { 
          status: 403,
          statusText: 'Forbidden' 
        })
      }
    } else {
      // Sin conexión al backend - verificar si podemos usar datos de Clerk como fallback
      console.warn('No se pudo verificar permisos de admin en el backend')
      
      // Fallback: verificar en metadatos de Clerk si están configurados
      // (esto requeriría configuración previa en Clerk)
      throw new Response('No se pudo verificar permisos de administrador', { 
        status: 503,
        statusText: 'Service Unavailable' 
      })
    }

    // Obtener plan (los admins típicamente tienen acceso completo)
    if (subscriptionResult.status === 'fulfilled' && subscriptionResult.value) {
      planId = subscriptionResult.value.plan_id || PLANS.PRO // Default Pro para admins
    } else {
      planId = PLANS.PRO // Admins tienen acceso completo
    }

  } catch (err) {
    // Manejar errores específicos
    if (err instanceof Response) {
      throw err // Re-lanzar respuestas HTTP específicas
    }
    
    console.error('Error en admin loader:', err)
    error = err instanceof Error ? err.message : 'Error interno del servidor'
    
    // Para admins, requerir conexión al backend
    throw new Response('Error interno del servidor. Admin requiere conexión al backend.', { 
      status: 500 
    })
  }

  return json({
    planId,
    isAdmin: true, // Si llegamos aquí, definitivamente es admin
    backendConnected,
    clerkUserId: userId,
    error
  })
}

export default function Admin() {
  const { 
    planId, 
    isAdmin, 
    backendConnected, 
    error 
  } = useLoaderData<typeof loader>()

  return (
    <div className="flex min-h-[100vh] w-full flex-col bg-secondary dark:bg-black">
      {/* Navigation para administradores */}
      <Navigation 
        planId={planId}
        isAdmin={isAdmin}
        backendConnected={backendConnected}
      />
      
      {/* Header para panel de admin */}
      <Header />

      {/* Banner informativo para administradores */}
      <div className="bg-blue-50 dark:bg-blue-900/20 border-l-4 border-blue-400 p-4">
        <div className="flex">
          <div className="ml-3">
            <p className="text-sm text-blue-700 dark:text-blue-200">
              <strong>Panel de Administración:</strong> Tienes acceso completo al sistema. 
              Usa estas herramientas responsablemente.
            </p>
          </div>
        </div>
      </div>

      {/* Estado de conexión específico para admin */}
      {!backendConnected && (
        <div className="bg-red-50 dark:bg-red-900/20 border-l-4 border-red-400 p-4">
          <div className="flex">
            <div className="ml-3">
              <p className="text-sm text-red-700 dark:text-red-200">
                <strong>Error crítico:</strong> Panel de administración requiere conexión al backend.
                {error && ` Detalles: ${error}`}
              </p>
            </div>
          </div>
        </div>
      )}
      
      <Outlet />
    </div>
  )
}