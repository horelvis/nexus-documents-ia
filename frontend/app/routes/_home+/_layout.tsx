// frontend/app/routes/_home+/_layout.tsx
import type { LoaderFunctionArgs } from '@remix-run/node'
import { Outlet, useLoaderData } from '@remix-run/react'
import { json } from '@remix-run/node'
import { getAuth } from '@clerk/remix/ssr.server'

import { createApiService } from '#app/utils/backend.server'
import { PLANS } from '#app/modules/stripe/plans'
import { Navigation } from '#app/components/navigation'

export const ROUTE_PATH = '/' as const

export async function loader(args: LoaderFunctionArgs) {
  const { request } = args
  const { userId } = await getAuth(args)

  // Para páginas públicas, no requerimos autenticación
  // pero podemos obtener datos si el usuario está logueado
  
  let backendConnected = true
  let isAdmin = false
  
  // Si hay usuario logueado, intentar obtener información adicional
  if (userId) {
    try {
      const apiService = await createApiService(args)
      const user = await apiService.getCurrentUser()
      
      if (user) {
        isAdmin = user.roles?.some((role: any) => role.name === 'admin') || 
                  user.is_superuser || 
                  false
      }
    } catch (error) {
      console.warn('Error obteniendo datos de usuario en home:', error)
      backendConnected = false
    }
  }

  return json({
    userId: userId || 'anonymous',
    planId: PLANS.FREE, // Default para páginas públicas
    isAdmin,
    backendConnected,
    isAuthenticated: !!userId
  })
}

export default function Home() {
  const { planId, isAdmin, backendConnected, isAuthenticated } = useLoaderData<typeof loader>()

  return (
    <div className="flex min-h-[100vh] w-full flex-col">
      {/* Navigation para páginas públicas - funciona para usuarios autenticados y no autenticados */}
      <Navigation 
        planId={isAuthenticated ? planId : PLANS.FREE}
        isAdmin={isAuthenticated ? isAdmin : false}
        backendConnected={backendConnected}
      />
      
      {/* Sin Header para páginas públicas - mantener diseño limpio */}
      
      {/* Indicador sutil de estado offline (solo para usuarios autenticados) */}
      {isAuthenticated && !backendConnected && (
        <div className="bg-yellow-50 dark:bg-yellow-900/20 border-b border-yellow-200 dark:border-yellow-800 px-6 py-2">
          <div className="mx-auto max-w-screen-xl">
            <p className="text-xs text-yellow-700 dark:text-yellow-200 text-center">
              Modo sin conexión - Funcionalidad limitada
            </p>
          </div>
        </div>
      )}
      
      <Outlet />
    </div>
  )
}