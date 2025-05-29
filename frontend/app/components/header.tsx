// frontend/app/components/header.tsx
import { useLocation } from '@remix-run/react'
import { SignedIn, SignedOut, useUser } from '@clerk/remix'
import { ROUTE_PATH as DASHBOARD_PATH } from '#app/routes/dashboard+/_layout'
import { ROUTE_PATH as BILLING_PATH } from '#app/routes/dashboard+/settings.billing'
import { ROUTE_PATH as SETTINGS_PATH } from '#app/routes/dashboard+/settings'
import { ROUTE_PATH as ADMIN_PATH } from '#app/routes/admin+/_layout'

export function Header() {
  const { user } = useUser()
  const location = useLocation()
  
  // Lista de rutas permitidas para mostrar el header
  const allowedLocations = [DASHBOARD_PATH, BILLING_PATH, SETTINGS_PATH, ADMIN_PATH]

  // Función para obtener el título de la página
  const headerTitle = () => {
    if (location.pathname === DASHBOARD_PATH) return 'Dashboard'
    if (location.pathname === BILLING_PATH) return 'Facturación'
    if (location.pathname === SETTINGS_PATH) return 'Configuración'
    if (location.pathname === ADMIN_PATH) return 'Administración'
    return 'Aplicación'
  }

  // Función para obtener la descripción de la página
  const headerDescription = () => {
    if (location.pathname === DASHBOARD_PATH)
      return 'Gestiona tus documentos y revisa tu actividad.'
    if (location.pathname === SETTINGS_PATH) 
      return 'Configura tu cuenta y preferencias.'
    if (location.pathname === BILLING_PATH)
      return 'Gestiona tu suscripción y facturación.'
    if (location.pathname === ADMIN_PATH) 
      return 'Panel de administración del sistema.'
    return 'Bienvenido a tu aplicación.'
  }

  // Solo mostrar header en rutas permitidas y para usuarios autenticados
  if (!allowedLocations.includes(location.pathname as (typeof allowedLocations)[number])) {
    return null
  }

  return (
    <SignedIn>
      <header className="z-10 flex w-full flex-col border-b border-border bg-card px-6">
        <div className="mx-auto flex w-full max-w-screen-xl items-center justify-between py-8 md:py-12">
          <div className="flex flex-col items-start gap-2">
            <h1 className="text-2xl md:text-3xl font-medium text-primary/80">
              {headerTitle()}
            </h1>
            <p className="text-sm md:text-base font-normal text-primary/60">
              {headerDescription()}
            </p>
          </div>

          {/* Información del usuario usando Clerk */}
          <div className="flex items-center gap-4">
            {user && (
              <div className="hidden md:flex flex-col items-end">
                <span className="text-sm font-medium text-primary/80">
                  {user.fullName || user.firstName || 'Usuario'}
                </span>
                <span className="text-xs text-primary/60">
                  {user.emailAddresses[0]?.emailAddress}
                </span>
              </div>
            )}
          </div>
        </div>
      </header>
    </SignedIn>
  )
}