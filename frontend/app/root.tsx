// frontend/app/root.tsx - Versión completa actualizada
import type {
  MetaFunction,
  LinksFunction,
  LoaderFunction
} from '@remix-run/node'
import type { Theme } from '#app/utils/hooks/use-theme'
import {
  Links,
  Meta,
  Outlet,
  Scripts,
  ScrollRestoration,
  useLoaderData,
  useRouteError,
  isRouteErrorResponse,
} from '@remix-run/react'
import { useChangeLanguage } from 'remix-i18next/react'
import { AuthenticityTokenProvider } from 'remix-utils/csrf/react'
import { HoneypotProvider } from 'remix-utils/honeypot/react'
import { useNonce } from '#app/utils/hooks/use-nonce'
import { getHints } from '#app/utils/hooks/use-hints'
import { getTheme, useTheme } from '#app/utils/hooks/use-theme'
import { getToastSession } from '#app/utils/toast.server'
import { csrf } from '#app/utils/csrf.server'
import { honeypot } from '#app/utils/honeypot.server'
import { combineHeaders, getDomainUrl } from '#app/utils/misc.server'
import { siteConfig } from '#app/utils/constants/brand'
import { useToast } from '#app/components/toaster'
import { Toaster } from '#app/components/ui/sonner'
import { ClientHintCheck } from '#app/components/misc/client-hints'
import i18nServer, { localeCookie } from '#app/modules/i18n/i18n.server'

// Clerk imports
import { ClerkApp } from '@clerk/remix'
import { rootAuthLoader, getAuth } from '@clerk/remix/ssr.server'

// ✅ Imports para UserContext y servicios API
import { UserContextProvider } from '#app/utils/hooks/use-user-context'
import type { BackendUser } from '#app/utils/hooks/use-user-context'
import { createApiService } from '#app/utils/backend.server'
import { createStripeApiService } from '#app/services/stripe-api.server'
import { PLANS } from '#app/modules/stripe/plans'

import RootCSS from './root.css?url'

export const handle = { i18n: ['translation'] }

export const meta: MetaFunction<typeof loader> = ({ data }) => {
  const title = data?.siteConfig?.siteTitle || siteConfig.siteTitle
  return [
    { title: title },
    { name: 'description', content: siteConfig.siteDescription },
  ]
}

export const links: LinksFunction = () => {
  return [{ rel: 'stylesheet', href: RootCSS }]
}

// ✅ Tipo para el loader data actualizado
export type LoaderData = Awaited<ReturnType<typeof loader>>

// ✅ Loader actualizado con rootAuthLoader de Clerk
export const loader: LoaderFunction = (args) => {
  
  return rootAuthLoader(args, async ({ request }) => {

    const { sessionId, userId , getToken } = request.auth

    const token = await getToken()
   
    console.log("userId", userId); // <- ¿null? 
    console.log("sessionId", sessionId); // <- ¿null? 
    
    
    // ===== Cargar datos básicos de la app (siempre necesarios) =====
    const locale = await i18nServer.getLocale(request)
    const { toast, headers: toastHeaders } = await getToastSession(request)
    const [csrfToken, csrfCookieHeader] = await csrf.commitToken()
    
    // ===== Preparar userData para UserContextProvider =====
    let backendUser: BackendUser | null = null
    let backendConnected = false
    let planId = PLANS.FREE
    let error: string | null = null

    // Solo intentar cargar datos del backend si el usuario está autenticado
    if (userId) {
      try {
        // Crear servicios API
        const [apiService, stripeService] = await Promise.all([
          createApiService(userId, token),
          createStripeApiService(userId, token)
        ])
        
        // Cargar datos del usuario y suscripción en paralelo
        const [userResult, subscriptionResult] = await Promise.allSettled([
          apiService.getCurrentUser(),
          stripeService.getCurrentSubscription()
        ])

        // Procesar datos del usuario del backend
        if (userResult.status === 'fulfilled' && userResult.value) {
          backendUser = userResult.value as BackendUser
          backendConnected = true
        } else {
          console.warn('Could not load backend user:', 
            userResult.status === 'rejected' ? userResult.reason : 'No data')
        }

        // Procesar datos de suscripción
        if (subscriptionResult.status === 'fulfilled' && subscriptionResult.value) {
          planId = subscriptionResult.value.plan_id || PLANS.FREE
        } else {
          console.warn('Could not load subscription:', 
            subscriptionResult.status === 'rejected' ? subscriptionResult.reason : 'No data')
        }

      } catch (err) {
        console.error('Error loading user context data:', err)
        error = err instanceof Error ? err.message : 'Unknown error'
        backendConnected = false
      }
    }

    // ===== Retornar datos para el root =====
    return {
      // Variables de entorno para el cliente
      ENV: { 
        CLERK_PUBLISHABLE_KEY: process.env.CLERK_PUBLISHABLE_KEY 
      },
      
      // Datos básicos de la app
      locale,
      toast,
      csrfToken,
      honeypotProps: honeypot.getInputProps(),
      requestInfo: {
        hints: getHints(request),
        origin: getDomainUrl(request),
        path: new URL(request.url).pathname,
        userPrefs: { theme: getTheme(request) },
      },
      siteConfig: { siteTitle: siteConfig.siteTitle },
      
      // ✅ userData para UserContextProvider
      userData: {
        backendUser,
        backendConnected,
        planId,
        error,
      },
      
      // Headers de respuesta
      responseHeaders: combineHeaders(
        { 'Set-Cookie': await localeCookie.serialize(locale) },
        toastHeaders,
        csrfCookieHeader ? { 'Set-Cookie': csrfCookieHeader } : null,
      ),
    }
  },  {
    signInForceRedirectUrl: '/dashboard',
  }) // loadUser: true carga automáticamente datos de Clerk
}

// Componente Document (sin cambios)
function Document({
  children,
  nonce,
  lang = 'en',
  dir = 'ltr',
  theme = 'dark',
}: {
  children: React.ReactNode
  nonce: string
  lang?: string
  dir?: 'ltr' | 'rtl'
  theme?: Theme
}) {
  return (
    <html
      lang={lang}
      dir={dir}
      className={`${theme} overflow-x-hidden`}
      style={{ colorScheme: theme }}>
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <ClientHintCheck nonce={nonce} />
        <Meta />
        <Links />
      </head>
      <body className="h-auto w-full">
        {children}
        <ScrollRestoration nonce={nonce} />
        <Scripts nonce={nonce} />
        <Toaster closeButton position="bottom-center" theme={theme} />
      </body>
    </html>
  )
}

// ✅ Componente App actualizado con UserContextProvider
export function App() {
  const data = useLoaderData<typeof loader>()
  const nonce = useNonce()
  const theme = useTheme()

  // Actualizar idioma de i18n
  useChangeLanguage(data.locale)

  // Mostrar toast si existe
  useToast(data.toast)

  return (
    <Document nonce={nonce} theme={theme} lang={data.locale ?? 'en'}>
      <AuthenticityTokenProvider token={data.csrfToken}>
        <HoneypotProvider {...data.honeypotProps}>
          {/* ✅ UserContextProvider envuelve todo el contenido */}
          <UserContextProvider userData={data.userData}>
            <Outlet />
          </UserContextProvider>
        </HoneypotProvider>
      </AuthenticityTokenProvider>
    </Document>
  )
}

// ✅ Export default con ClerkApp HOF
export default ClerkApp(App, {
  signInUrl: "/auth/sign-in",
  signUpUrl: "/auth/sign-up", 
  afterSignInUrl: "/dashboard",
  afterSignUpUrl: "/dashboard",
})

// ✅ ErrorBoundary estándar
export function ErrorBoundary() {
  const error = useRouteError()
  let errorTitle = "Error"
  let errorMessage = "An unexpected error occurred."

  if (isRouteErrorResponse(error)) {
    errorTitle = `${error.status} ${error.statusText}`
    errorMessage = error.data?.message || error.data || "Sorry, something went wrong."
  } else if (error instanceof Error) {
    errorMessage = error.message
  }
  
  // Usar estructura HTML simplificada para la página de error
  return (
    <html lang="en">
      <head>
        <title>{errorTitle}</title>
        <Meta />
        <Links />
      </head>
      <body>
        <div style={{ 
          padding: '20px', 
          textAlign: 'center', 
          fontFamily: 'sans-serif',
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          alignItems: 'center'
        }}>
          <h1 style={{ color: '#dc2626' }}>{errorTitle}</h1>
          <p style={{ maxWidth: '600px', margin: '20px 0' }}>{errorMessage}</p>
          <div style={{ marginTop: '30px' }}>
            <a 
              href="/" 
              style={{ 
                padding: '10px 20px',
                backgroundColor: '#3b82f6',
                color: 'white',
                textDecoration: 'none',
                borderRadius: '6px',
                marginRight: '10px'
              }}
            >
              Go to Homepage
            </a>
            <button 
              onClick={() => window.location.reload()}
              style={{ 
                padding: '10px 20px',
                backgroundColor: '#6b7280',
                color: 'white',
                border: 'none',
                borderRadius: '6px',
                cursor: 'pointer'
              }}
            >
              Retry
            </button>
          </div>
        </div>
        <Scripts />
      </body>
    </html>
  )
}