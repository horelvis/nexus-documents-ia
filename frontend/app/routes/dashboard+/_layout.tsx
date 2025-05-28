// frontend/app/routes/dashboard+/_layout.tsx
import type { LoaderFunctionArgs, TypedResponse } from '@remix-run/node'
import { Outlet, useLoaderData } from '@remix-run/react'
import { json, redirect } from '@remix-run/node'
import { getAuth } from '@clerk/remix/ssr.server'

import { createApiService } from '#app/utils/backend.server'
import { ROUTE_PATH as ONBOARDING_USERNAME_PATH } from '#app/routes/onboarding+/username'
import { ROUTE_PATH as SIGN_IN_PATH } from '#app/routes/auth+/sign-in.$'
import { Navigation } from '#app/components/navigation'
import { Header } from '#app/components/header'

export const ROUTE_PATH = '/dashboard' as const

export type LoaderData = Exclude<
  Awaited<ReturnType<typeof loader>>,
  Response | TypedResponse<unknown>
>

export const loader = async (args: LoaderFunctionArgs) => {
  const { request } = args
  const { userId, sessionId } = await getAuth(args)

  if (!userId || !sessionId) {
    const params = new URLSearchParams()
    params.set("redirect_url", new URL(request.url).pathname)
    return redirect(`${SIGN_IN_PATH}?${params.toString()}`)
  }

  try {
    // Obtener información del usuario desde el backend
    const apiService = await createApiService(args)
    
    // Obtener usuario actual del backend
    const [backendUserData, backendTenantData] = await Promise.allSettled([
      apiService.getCurrentUser(),
      apiService.getCurrentTenant(),
    ])

    let backendUser = null
    let backendTenant = null
    let backendConnected = false

    if (backendUserData.status === 'fulfilled') {
      backendUser = backendUserData.value
      backendConnected = true
    } else {
      console.error('Error obteniendo usuario del backend:', backendUserData.reason)
    }

    if (backendTenantData.status === 'fulfilled') {
      backendTenant = backendTenantData.value
    }

    // Si no podemos obtener el usuario del backend, pero tenemos userId de Clerk,
    // podemos continuar con funcionalidad limitada
    const user = backendUser || {
      id: userId,
      email: 'usuario@ejemplo.com', // Fallback
      username: null,
      full_name: null,
      clerkUserId: userId,
      roles: [{ name: 'user' }],
      is_active: true,
      tenant_id: null,
    }

    // Verificar onboarding basado en datos del backend o Clerk
    if (backendConnected && backendUser && !backendUser.username) {
      return redirect(ONBOARDING_USERNAME_PATH)
    }

    // Simular suscripción local para compatibilidad con componentes existentes
    const subscription = {
      planId: 'free', // Plan por defecto
      status: 'active',
    }

    return json({
      user,
      subscription,
      backendUser,
      backendTenant,
      backendConnected,
      clerkUserId: userId,
    })

  } catch (error) {
    console.error('Error en dashboard loader:', error)
    
    // En caso de error total, proporcionar datos mínimos para que la app funcione
    return json({
      user: {
        id: userId,
        email: 'usuario@ejemplo.com',
        username: null,
        full_name: null,
        clerkUserId: userId,
        roles: [{ name: 'user' }],
        is_active: true,
        tenant_id: null,
      },
      subscription: {
        planId: 'free',
        status: 'active',
      },
      backendUser: null,
      backendTenant: null,
      backendConnected: false,
      clerkUserId: userId,
      error: error instanceof Error ? error.message : 'Error desconocido',
    })
  }
}

export default function Dashboard() {
  const { user, subscription, backendConnected, error } = useLoaderData<typeof loader>()

  return (
    <div className="flex min-h-[100vh] w-full flex-col bg-secondary dark:bg-black">
      <Navigation user={user} planId={subscription?.planId} />
      <Header />
      
      {/* Indicador de estado del backend */}
      {!backendConnected && (
        <div className="bg-yellow-50 dark:bg-yellow-900/20 border-l-4 border-yellow-400 p-4">
          <div className="flex">
            <div className="ml-3">
              <p className="text-sm text-yellow-700 dark:text-yellow-200">
                <strong>Modo sin conexión:</strong> No se pudo conectar con el backend. 
                Algunas funcionalidades pueden estar limitadas.
                {error && ` Error: ${error}`}
              </p>
            </div>
          </div>
        </div>
      )}
      
      <Outlet />
    </div>
  )
}