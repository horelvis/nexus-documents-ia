// frontend/app/components/navigation.tsx
import { Link, useLocation } from '@remix-run/react'
import { 
  SignedIn, 
  SignedOut, 
  UserButton, 
  useUser,
  SignInButton 
} from '@clerk/remix'
import {
  Slash,
  Star,
  AlertCircle
} from 'lucide-react'
import { PLANS } from '#app/modules/stripe/plans'
import { useRequestInfo } from '#app/utils/hooks/use-request-info'
import { cn } from '#app/utils/misc'
import { ROUTE_PATH as ADMIN_PATH } from '#app/routes/admin+/_layout'
import { ROUTE_PATH as DASHBOARD_PATH } from '#app/routes/dashboard+/_layout'
import { ROUTE_PATH as DASHBOARD_SETTINGS_PATH } from '#app/routes/dashboard+/settings'
import { ROUTE_PATH as DASHBOARD_SETTINGS_BILLING_PATH } from '#app/routes/dashboard+/settings.billing'
import { ThemeSwitcher } from '#app/components/misc/theme-switcher'
import { LanguageSwitcher } from '#app/components/misc/language-switcher'
import { Button, buttonVariants } from '#app/components/ui/button'
import { Badge } from '#app/components/ui/badge'
import { Logo } from '#app/components/logo'

type NavigationProps = {
  planId?: string
  backendConnected?: boolean
  isAdmin?: boolean
}

export function Navigation({ 
  planId = PLANS.FREE, 
  backendConnected = true,
  isAdmin = false 
}: NavigationProps) {
  const { user } = useUser() // Solo para verificar roles si es necesario
  const requestInfo = useRequestInfo()
  const location = useLocation()

  // Estados de navegación
  const isAdminPath = location.pathname === ADMIN_PATH
  const isDashboardPath = location.pathname === DASHBOARD_PATH
  const isSettingsPath = location.pathname === DASHBOARD_SETTINGS_PATH
  const isBillingPath = location.pathname === DASHBOARD_SETTINGS_BILLING_PATH

  // Función para obtener el nombre del plan
  const getPlanDisplayName = (plan: string) => {
    switch (plan) {
      case PLANS.FREE:
        return 'Free'
      case PLANS.PRO:
        return 'Pro'
      case PLANS.ENTERPRISE:
        return 'Enterprise'
      default:
        return 'Free'
    }
  }

  return (
    <nav className="sticky top-0 z-50 flex w-full flex-col border-b border-border bg-card px-6">
      <div className="mx-auto flex w-full max-w-screen-xl items-center justify-between py-3">
        {/* Logo */}
        <div className="flex h-10 items-center gap-2">
          <Link
            to={DASHBOARD_PATH}
            prefetch="intent"
            className="flex h-10 items-center gap-1"
          >
            <Logo />
          </Link>
          
          {/* Separador visual solo cuando hay usuario */}
          <SignedIn>
            <Slash className="h-6 w-6 -rotate-12 stroke-[1.5px] text-primary/10" />
            
            {/* Indicadores de estado */}
            <div className="flex items-center gap-2">
              {/* Badge del plan */}
              <Badge 
                variant={planId === PLANS.FREE ? 'secondary' : 'default'}
                className="text-xs"
              >
                {getPlanDisplayName(planId)}
              </Badge>

              {/* Indicador de backend offline */}
              {!backendConnected && (
                <Badge variant="destructive" className="text-xs gap-1">
                  <AlertCircle className="h-3 w-3" />
                  Offline
                </Badge>
              )}
            </div>
          </SignedIn>
        </div>

        {/* Acciones del usuario */}
        <div className="flex h-10 items-center gap-3">
          {/* Enlace a documentación */}
          <a
            href="https://github.com/dev-xo/remix-saas/tree/main/docs#welcome-to-%EF%B8%8F-remix-saas-documentation"
            target="_blank"
            rel="noreferrer"
            className={cn(
              buttonVariants({ variant: 'link', size: 'sm' }),
              'group flex gap-3 px-0 text-primary/80 hover:text-primary hover:no-underline',
            )}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-6 w-6 text-primary/80 transition group-hover:text-primary"
              viewBox="0 0 24 24"
              fill="currentColor"
            >
              <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
            </svg>
            <span className="hidden select-none items-center gap-1 rounded-full bg-green-500/5 px-2 py-1.5 pr-2.5 text-xs font-semibold tracking-tight text-green-600 ring-1 ring-inset ring-green-600/20 backdrop-blur-sm transition-all duration-300 group-hover:brightness-110 dark:bg-yellow-800/40 dark:text-yellow-100 dark:ring-yellow-200/50 md:flex">
              <Star
                className="h-3 w-3 text-green-600 dark:text-yellow-100"
                fill="currentColor"
              />
              +1.4K Documentación
            </span>
          </a>

          {/* Configuración de tema y idioma para usuarios no autenticados */}
          <SignedOut>
            <div className="flex items-center gap-2">
              <ThemeSwitcher userPreference={requestInfo.userPrefs.theme} />
              <LanguageSwitcher />
              <SignInButton mode="modal">
                <Button size="sm">Iniciar Sesión</Button>
              </SignInButton>
            </div>
          </SignedOut>

          {/* UserButton de Clerk para usuarios autenticados */}
          <SignedIn>
            <UserButton 
              afterSignOutUrl="/"
              appearance={{
                elements: {
                  avatarBox: "w-8 h-8",
                  userButtonPopoverCard: "bg-card border border-border",
                  userButtonPopoverActions: "bg-card",
                  userButtonPopoverActionButton: "text-primary/80 hover:text-primary hover:bg-accent",
                  userButtonPopoverActionButtonText: "text-sm",
                  userButtonPopoverFooter: "hidden", // Ocultar footer por defecto
                },
              }}
            >
              {/* Elementos personalizados del menú */}
              <UserButton.MenuItems>
                {/* Enlace a configuración personalizada */}
                <UserButton.Link 
                  label="Configuración"
                  labelIcon={<ThemeSwitcher userPreference={requestInfo.userPrefs.theme} triggerClass="w-4 h-4" />}
                  href={DASHBOARD_SETTINGS_PATH}
                />
                
                {/* Enlace a facturación */}
                <UserButton.Link 
                  label="Facturación"
                  labelIcon="💳"
                  href={DASHBOARD_SETTINGS_BILLING_PATH}
                />

                {/* Configuración de idioma */}
                <UserButton.Action 
                  label="Idioma"
                  labelIcon={<LanguageSwitcher />}
                  onClick={() => {}} // LanguageSwitcher maneja el click
                />
              </UserButton.MenuItems>
            </UserButton>
          </SignedIn>
        </div>
      </div>

      {/* Navegación de tabs - Solo para usuarios autenticados */}
      <SignedIn>
        <div className="mx-auto flex w-full max-w-screen-xl items-center gap-3">
          {/* Tab Admin (solo si es admin) */}
          {isAdmin && (
            <div
              className={`flex h-12 items-center border-b-2 ${
                isAdminPath ? 'border-primary' : 'border-transparent'
              }`}
            >
              <Link
                to={ADMIN_PATH}
                prefetch="intent"
                className={cn(
                  `${buttonVariants({ variant: 'ghost', size: 'sm' })} text-primary/80`,
                )}
              >
                Admin
              </Link>
            </div>
          )}

          {/* Tab Dashboard */}
          <div
            className={`flex h-12 items-center border-b-2 ${
              isDashboardPath ? 'border-primary' : 'border-transparent'
            }`}
          >
            <Link
              to={DASHBOARD_PATH}
              prefetch="intent"
              className={cn(
                `${buttonVariants({ variant: 'ghost', size: 'sm' })} text-primary/80`,
              )}
            >
              Dashboard
            </Link>
          </div>

          {/* Tab Configuración */}
          <div
            className={`flex h-12 items-center border-b-2 ${
              isSettingsPath ? 'border-primary' : 'border-transparent'
            }`}
          >
            <Link
              to={DASHBOARD_SETTINGS_PATH}
              prefetch="intent"
              className={cn(
                `${buttonVariants({ variant: 'ghost', size: 'sm' })} text-primary/80`,
              )}
            >
              Configuración
            </Link>
          </div>

          {/* Tab Facturación */}
          <div
            className={`flex h-12 items-center border-b-2 ${
              isBillingPath ? 'border-primary' : 'border-transparent'
            }`}
          >
            <Link
              to={DASHBOARD_SETTINGS_BILLING_PATH}
              prefetch="intent"
              className={cn(
                `${buttonVariants({ variant: 'ghost', size: 'sm' })} text-primary/80`,
              )}
            >
              Facturación
            </Link>
          </div>
        </div>
      </SignedIn>
    </nav>
  )
}