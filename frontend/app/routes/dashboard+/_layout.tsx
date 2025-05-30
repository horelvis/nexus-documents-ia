// frontend/app/routes/dashboard+/_layout.tsx - FIX CLERK TIMEOUT
import type { LoaderFunctionArgs, TypedResponse } from '@remix-run/node'
import { Outlet, useLoaderData } from '@remix-run/react'
import { json, redirect } from '@remix-run/node'
import { getAuth } from '@clerk/remix/ssr.server'
import { timeout, TimeoutError } from '#app/utils/timeout.server'

import { createApiService } from '#app/utils/backend.server'
import { createStripeApiService } from '#app/services/stripe-api.server'
import { PLANS } from '#app/modules/stripe/plans'
import { ROUTE_PATH as ONBOARDING_USERNAME_PATH } from '#app/routes/onboarding+/username'

import { Navigation } from '#app/components/navigation'
import { Header } from '#app/components/header'
import { Sidebar } from '#app/components/sidebar' // Import the new Sidebar component
import { Footer } from '#app/components/footer' // Import the new Footer component

export const ROUTE_PATH = '/dashboard' as const
export const SIGN_IN_PATH = '/auth/sign-in' as const

interface DashboardLayoutData {
  planId: string
  isAdmin: boolean
  backendConnected: boolean
  clerkUserId: string | null
  error: string | null
  needsOnboarding: boolean
  offlineMode: boolean
  layoutLoadTime: number
  clerkTimeout: boolean
}

export type LoaderData = DashboardLayoutData

// ✅ Helper para timeout de Clerk
async function timeoutClerkAuth(args: LoaderFunctionArgs, timeoutMs: number = 2000) {
  try {
    console.time('clerk-auth-timeout')
    
    const clerkOperation = async () => {
      const auth = await getAuth(args)
      return auth.userId
    }

    const userId = await timeout(clerkOperation(), { 
      ms: timeoutMs, 
      signal: args.request.signal 
    })
    
    console.timeEnd('clerk-auth-timeout')
    console.log('✅ Clerk auth completed successfully')
    
    return { userId, error: null, timedOut: false }
    
  } catch (err) {
    console.timeEnd('clerk-auth-timeout')
    
    if (err instanceof TimeoutError) {
      console.error('🔥 CLERK AUTH TIMEOUT after', timeoutMs, 'ms')
      return { userId: null, error: `Clerk timeout ${timeoutMs}ms`, timedOut: true }
    } else {
      console.error('❌ Clerk auth error:', err instanceof Error ? err.message : 'Unknown')
      return { userId: null, error: err instanceof Error ? err.message : 'Clerk error', timedOut: false }
    }
  }
}

export const loader = async (args: LoaderFunctionArgs): Promise<Response> => {
  const startTime = Date.now()
  const { request } = args
  
  console.log('🏗️ Dashboard Layout: Starting with Clerk timeout fix...')
  
  // ✅ STEP 1: Verificar Clerk auth CON TIMEOUT
  const clerkResult = await timeoutClerkAuth(args, 2000) // 2 segundos máximo para Clerk
  
  // Si Clerk falla completamente, redirigir a sign-in
  if (!clerkResult.userId && !clerkResult.timedOut) {
    console.error('❌ Clerk failed completely, redirecting to sign-in')
    return redirect(`${SIGN_IN_PATH}?error=auth_failed`)
  }

  // Si Clerk timeout pero no hay userId, también redirigir
  if (!clerkResult.userId && clerkResult.timedOut) {
    console.error('🔥 Clerk timeout, redirecting to sign-in')
    const params = new URLSearchParams()
    params.set("redirect_url", new URL(request.url).pathname)
    params.set("error", "clerk_timeout")
    return redirect(`${SIGN_IN_PATH}?${params.toString()}`)
  }

  const userId = clerkResult.userId!

  // ✅ STEP 2: Valores por defecto seguros
  let backendConnected = false
  let planId = PLANS.FREE
  let isAdmin = false
  let needsOnboarding = false
  let error: string | null = clerkResult.error
  let offlineMode = clerkResult.timedOut // Si Clerk hizo timeout, modo offline
  const clerkTimeout = clerkResult.timedOut

  // ✅ STEP 3: Backend operations SOLO si Clerk funcionó bien
  if (!clerkTimeout) {
    const BACKEND_TIMEOUT_MS = 1000 // 1 segundo para backend

    try {
      console.time('backend-operations')

      const backendOperation = async () => {
        const [apiService, stripeService] = await Promise.all([
          createApiService(args),
          createStripeApiService(args)
        ])

        const [userResult, subscriptionResult] = await Promise.allSettled([
          apiService.getCurrentUser(),
          stripeService.getCurrentSubscription()
        ])

        return { userResult, subscriptionResult }
      }

      const backendResult = await timeout(backendOperation(), { 
        ms: BACKEND_TIMEOUT_MS, 
        signal: request.signal 
      })

      console.timeEnd('backend-operations')

      // Procesar resultados del backend
      const { userResult, subscriptionResult } = backendResult

      if (userResult.status === 'fulfilled' && userResult.value) {
        const backendUser = userResult.value
        backendConnected = true
        
        if (!backendUser.username || !backendUser.tenant_id) {
          needsOnboarding = true
        }
        
        isAdmin = Boolean(
          backendUser.roles?.some((role: any) => role.name === 'admin') || 
          backendUser.is_superuser
        )
      }

      if (subscriptionResult.status === 'fulfilled' && subscriptionResult.value) {
        planId = subscriptionResult.value.plan_id || PLANS.FREE
      }

    } catch (err) {
      console.timeEnd('backend-operations')
      
      if (err instanceof TimeoutError) {
        console.warn(`⏰ Backend timeout after ${BACKEND_TIMEOUT_MS}ms`)
        error = error ? `${error} + Backend timeout` : `Backend timeout ${BACKEND_TIMEOUT_MS}ms`
      } else {
        console.warn('⚠️ Backend error:', err instanceof Error ? err.message : 'Unknown')
        error = error ? `${error} + Backend error` : (err instanceof Error ? err.message : 'Backend error')
      }
      
      backendConnected = false
      offlineMode = true
    }
  } else {
    console.warn('⚠️ Skipping backend operations due to Clerk timeout')
    offlineMode = true
  }

  const layoutLoadTime = Date.now() - startTime

  // ✅ STEP 4: Solo redirigir a onboarding si TODO funciona bien
  if (needsOnboarding && backendConnected && !offlineMode && !clerkTimeout) {
    console.log('🔄 Layout: Redirecting to onboarding')
    return redirect(ONBOARDING_USERNAME_PATH)
  }

  console.log(`✅ Layout loaded in ${layoutLoadTime}ms - Clerk timeout: ${clerkTimeout}, Backend: ${backendConnected}, Offline: ${offlineMode}`)
  
  return json<DashboardLayoutData>({
    planId,
    isAdmin,
    backendConnected,
    clerkUserId: userId,
    error,
    needsOnboarding,
    offlineMode,
    layoutLoadTime,
    clerkTimeout
  }, {
    headers: {
      'X-Layout-Load-Time': layoutLoadTime.toString(),
      'X-Clerk-Timeout': clerkTimeout.toString(),
      'X-Backend-Connected': backendConnected.toString(),
      'X-Offline-Mode': offlineMode.toString(),
      // ✅ No cache si hay problemas
      ...(clerkTimeout || offlineMode ? {
        'Cache-Control': 'no-cache, no-store, must-revalidate'
      } : {
        'Cache-Control': 'private, max-age=30'
      })
    }
  })
}

export default function Dashboard() {
  const { 
    planId, 
    isAdmin, 
    backendConnected, 
    error, 
    needsOnboarding,
    offlineMode,
    layoutLoadTime,
    clerkTimeout
  } = useLoaderData<LoaderData>()

  return (
    <div className="flex flex-col min-h-screen bg-secondary dark:bg-black">
      {/* Top Navigation Bar */}
      <Navigation 
        planId={planId}
        isAdmin={isAdmin} 
        backendConnected={backendConnected}
      />
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <Sidebar isAdmin={isAdmin} className="h-full" /> {/* Ensure sidebar takes full height of this flex container */}
        
        {/* Main Content Area */}
        <main className="flex-1 flex flex-col overflow-y-auto">
          {/* Page-specific Header (titles) */}
          <Header /> 
          
          {/* Status Banners */}
          {/* ✅ Banner específico para Clerk timeout */}
          {clerkTimeout && (
            <div className="bg-red-50 dark:bg-red-900/20 border-l-4 border-red-500 p-4 mx-6 mt-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center">
                  <div className="flex-shrink-0">
                    <svg className="h-5 w-5 text-red-500" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                    </svg>
                  </div>
                  <div className="ml-3">
                    <p className="text-sm text-red-700 dark:text-red-200">
                      <strong>🔥 Clerk Auth Timeout:</strong> La autenticación tardó más de 2 segundos. 
                      Funcionando con datos cached del usuario.
                    </p>
                  </div>
                </div>
                <div className="flex items-center space-x-3">
                  <span className="text-xs text-red-600 dark:text-red-300">
                    Clerk: 2s timeout
                  </span>
                  <button 
                    onClick={() => window.location.reload()}
                    className="text-red-700 dark:text-red-200 hover:text-red-900 dark:hover:text-red-100 text-sm underline"
                  >
                    Reintentar Auth
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* ✅ Banner de backend offline (solo si Clerk funciona) */}
          {!clerkTimeout && offlineMode && (
            <div className="bg-orange-50 dark:bg-orange-900/20 border-l-4 border-orange-400 p-4 mx-6 mt-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center">
                  <div className="flex-shrink-0">
                    <svg className="h-5 w-5 text-orange-400" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                    </svg>
                  </div>
                  <div className="ml-3">
                    <p className="text-sm text-orange-700 dark:text-orange-200">
                      <strong>Backend Offline:</strong> Backend no responde en 1 segundo. 
                      Auth funcionando, datos limitados.
                    </p>
                  </div>
                </div>
                <div className="flex items-center space-x-3">
                  <span className="text-xs text-orange-600 dark:text-orange-300">
                    Backend: 1s timeout
                  </span>
                  <button 
                    onClick={() => window.location.reload()}
                    className="text-orange-700 dark:text-orange-200 hover:text-orange-900 dark:hover:text-orange-100 text-sm underline"
                  >
                    Reintentar
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* ✅ Banner de éxito cuando todo funciona */}
          {!clerkTimeout && !offlineMode && backendConnected && layoutLoadTime < 1000 && (
            <div className="bg-green-50 dark:bg-green-900/20 border-l-4 border-green-400 p-2 mx-6 mt-4">
              <div className="flex items-center justify-center">
                <div className="flex items-center text-sm text-green-700 dark:text-green-200">
                  <svg className="h-4 w-4 text-green-400 mr-2" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                  </svg>
                  <span>
                    ⚡ Todo funcionando: Cargado en{' '}
                    <span className="font-medium">{layoutLoadTime}ms</span>
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* ✅ Onboarding banner */}
          {needsOnboarding && backendConnected && !offlineMode && !clerkTimeout && (
            <div className="bg-blue-50 dark:bg-blue-900/20 border-l-4 border-blue-400 p-4 mx-6 mt-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center">
                  <div className="ml-3">
                    <p className="text-sm text-blue-700 dark:text-blue-200">
                      <strong>Configuración pendiente:</strong> Completa tu perfil para acceder a todas las funciones.
                    </p>
                  </div>
                </div>
                <div>
                  <a 
                    href={ONBOARDING_USERNAME_PATH}
                    className="text-blue-700 dark:text-blue-200 hover:text-blue-900 dark:hover:text-blue-100 text-sm underline"
                  >
                    Completar ahora
                  </a>
                </div>
              </div>
            </div>
          )}
          
          {/* Page Content */}
          <div className="p-6 flex-1"> {/* Added flex-1 to allow content to grow and push footer if any, or fill space */}
            <Outlet />
          </div>
        </main>
      </div>
      <Footer /> {/* Footer is placed here, outside the flex-1 content div, but inside the main flex-col div */}
    </div>
  )
}