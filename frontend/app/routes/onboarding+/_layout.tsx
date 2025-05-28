// frontend/app/routes/onboarding+/_layout.tsx
import type { LoaderFunctionArgs } from '@remix-run/node'
import { Outlet } from '@remix-run/react'
import { redirect, json } from '@remix-run/node'
import { getAuth } from '@clerk/remix/ssr.server'

import { createApiService } from '#app/utils/backend.server'
import { getDomainPathname } from '#app/utils/misc.server'
import { ROUTE_PATH as DASHBOARD_PATH } from '#app/routes/dashboard+/_layout'
import { ROUTE_PATH as ONBOARDING_USERNAME_PATH } from '#app/routes/onboarding+/username'
import { ROUTE_PATH as ONBOARDING_PLAN_PATH } from '#app/routes/onboarding+/plan'
import { Logo } from '#app/components/logo'

export const ROUTE_PATH = '/onboarding' as const

export async function loader(args : LoaderFunctionArgs) {
  const { request } = args
  const { userId } = await getAuth(args)
  
  if (!userId) {
    return redirect('/auth/sign-in')
  }

  const pathname = getDomainPathname(request)

  try {
    // Intentar obtener información del usuario desde el backend
    const apiService = await createApiService(args)
    const backendUser = await apiService.getCurrentUser()

    // Verificar si el onboarding está completo
    const onboardingComplete = backendUser && backendUser.username && backendUser.tenantId

    if (onboardingComplete) {
      // Onboarding completo, redirigir al dashboard
      if (
        pathname === ROUTE_PATH ||
        pathname === ONBOARDING_USERNAME_PATH ||
        pathname === ONBOARDING_PLAN_PATH
      ) {
        return redirect(DASHBOARD_PATH)
      }
    } else {
      // Onboarding no completo, determinar siguiente paso
      if (pathname === ROUTE_PATH) {
        if (!backendUser?.username) {
          return redirect(ONBOARDING_USERNAME_PATH)
        }
        return redirect(ONBOARDING_PLAN_PATH)
      }

      if (pathname === ONBOARDING_USERNAME_PATH) {
        if (backendUser?.username) {
          return redirect(ONBOARDING_PLAN_PATH)
        }
        // Usuario está en la página correcta
      }

      if (pathname === ONBOARDING_PLAN_PATH) {
        if (!backendUser?.username) {
          return redirect(ONBOARDING_USERNAME_PATH)
        }
        // Usuario está en la página correcta
      }
    }

    return json({ backendConnected: true, user: backendUser })

  } catch (error) {
    console.error('Error en onboarding loader:', error)
    
    // Si hay error con el backend, permitir continuar con datos mínimos
    // pero redirigir apropiadamente basado en la ruta actual
    if (pathname === ROUTE_PATH) {
      return redirect(ONBOARDING_USERNAME_PATH)
    }

    return json({ 
      backendConnected: false, 
      user: null,
      error: error instanceof Error ? error.message : 'Error desconocido'
    })
  }
}

export default function Onboarding() {
  return (
    <div className="relative flex h-screen w-full bg-card">
      <div className="absolute left-1/2 top-8 mx-auto -translate-x-1/2 transform justify-center">
        <Logo />
      </div>
      <div className="z-10 h-screen w-screen">
        <Outlet />
      </div>
      <div className="base-grid fixed h-screen w-screen opacity-40" />
      <div className="fixed bottom-0 h-screen w-screen bg-gradient-to-t from-[hsl(var(--card))] to-transparent" />
    </div>
  )
}