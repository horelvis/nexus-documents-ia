// frontend/app/routes/dashboard+/settings.tsx
import type { MetaFunction, LoaderFunctionArgs } from '@remix-run/node'
import { Link, Outlet, useLocation, useLoaderData } from '@remix-run/react'
import { json } from '@remix-run/node'
import { getAuth } from '@clerk/remix/ssr.server'
import { User, CreditCard, Shield, Bell, Palette, Globe } from 'lucide-react'

import { createApiService } from '#app/utils/backend.server'
import { createStripeApiService } from '#app/services/stripe-api.server'
import { PLANS } from '#app/modules/stripe/plans'
import { cn } from '#app/utils/misc'
import { ROUTE_PATH as BILLING_PATH } from '#app/routes/dashboard+/settings.billing'
import { buttonVariants } from '#app/components/ui/button'
import { Badge } from '#app/components/ui/badge'
import { Separator } from '#app/components/ui/separator'

export const ROUTE_PATH = '/dashboard/settings' as const

export const meta: MetaFunction = () => {
  return [{ title: 'Configuración - Dashboard' }]
}

export async function loader({ request }: LoaderFunctionArgs) {
  const { userId } = await getAuth({ request })
  
  if (!userId) {
    throw new Response('Unauthorized', { status: 401 })
  }

  // Obtener datos mínimos necesarios para configuración
  let backendConnected = false
  let planId = PLANS.FREE
  let isAdmin = false
  let hasCustomDomain = false

  try {
    const [apiService, stripeService] = await Promise.all([
      createApiService({ request }),
      createStripeApiService({ request })
    ])
    
    const [userResult, subscriptionResult] = await Promise.allSettled([
      apiService.getCurrentUser(),
      stripeService.getCurrentSubscription()
    ])

    // Procesar datos del usuario
    if (userResult.status === 'fulfilled' && userResult.value) {
      backendConnected = true
      const user = userResult.value
      isAdmin = user.roles?.some((role: any) => role.name === 'admin') || user.is_superuser || false
      hasCustomDomain = user.custom_domain || false
    }

    // Procesar datos de suscripción
    if (subscriptionResult.status === 'fulfilled' && subscriptionResult.value) {
      planId = subscriptionResult.value.plan_id || PLANS.FREE
    }

  } catch (error) {
    console.error('Error loading settings data:', error)
    // Continuar con datos por defecto - Clerk maneja lo esencial
  }

  return json({
    backendConnected,
    planId,
    isAdmin,
    hasCustomDomain,
    clerkUserId: userId
  })
}

export default function DashboardSettings() {
  const { backendConnected, planId, isAdmin, hasCustomDomain } = useLoaderData<typeof loader>()
  const location = useLocation()
  
  // Configuración de navigation items
  const navigationItems = [
    {
      id: 'general',
      label: 'General',
      href: ROUTE_PATH,
      icon: User,
      description: 'Perfil y configuración básica',
      enabled: true
    },
    {
      id: 'billing',
      label: 'Facturación',
      href: BILLING_PATH,
      icon: CreditCard,
      description: 'Suscripción y métodos de pago',
      enabled: true,
      badge: planId !== PLANS.FREE ? planId : undefined
    },
    {
      id: 'security',
      label: 'Seguridad',
      href: '/dashboard/settings/security',
      icon: Shield,
      description: 'Contraseñas y autenticación',
      enabled: planId !== PLANS.FREE,
      comingSoon: true
    },
    {
      id: 'notifications',
      label: 'Notificaciones',
      href: '/dashboard/settings/notifications',
      icon: Bell,
      description: 'Preferencias de emails y alertas',
      enabled: planId !== PLANS.FREE,
      comingSoon: true
    },
    {
      id: 'appearance',
      label: 'Apariencia',
      href: '/dashboard/settings/appearance',
      icon: Palette,
      description: 'Temas y personalización',
      enabled: true,
      comingSoon: true
    },
    {
      id: 'domain',
      label: 'Dominio Custom',
      href: '/dashboard/settings/domain',
      icon: Globe,
      description: 'Configurar dominio personalizado',
      enabled: planId === PLANS.ENTERPRISE,
      badge: hasCustomDomain ? 'Configurado' : undefined,
      comingSoon: true
    }
  ]

  const currentPath = location.pathname
  const isSettingsIndex = currentPath === ROUTE_PATH
  const isBillingPath = currentPath === BILLING_PATH

  return (
    <div className="flex h-full w-full px-6 py-8">
      <div className="mx-auto flex h-full w-full max-w-screen-xl gap-8">
        {/* Sidebar Navigation */}
        <div className="hidden w-full max-w-64 flex-col gap-1 lg:flex">
          <div className="mb-4">
            <h2 className="text-lg font-semibold text-primary">Configuración</h2>
            <p className="text-sm text-muted-foreground">
              Gestiona tu cuenta y preferencias
            </p>
          </div>

          {/* Estado de conectividad */}
          {!backendConnected && (
            <div className="mb-4 rounded-lg border border-yellow-200 bg-yellow-50 p-3 dark:border-yellow-800 dark:bg-yellow-900/20">
              <p className="text-xs text-yellow-700 dark:text-yellow-300">
                ⚠️ Modo offline - Algunas configuraciones pueden no estar disponibles
              </p>
            </div>
          )}

          <nav className="space-y-1">
            {navigationItems.map((item) => {
              const isActive = currentPath === item.href
              const IconComponent = item.icon

              return (
                <div key={item.id}>
                  {item.enabled ? (
                    <Link
                      to={item.href}
                      prefetch="intent"
                      className={cn(
                        buttonVariants({ variant: 'ghost' }),
                        'h-auto w-full justify-start p-3',
                        isActive && 'bg-accent text-accent-foreground',
                        item.comingSoon && 'opacity-60 cursor-not-allowed'
                      )}
                      onClick={item.comingSoon ? (e) => e.preventDefault() : undefined}
                    >
                      <div className="flex w-full items-center gap-3">
                        <IconComponent className="h-4 w-4 flex-shrink-0" />
                        <div className="flex-1 text-left">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium">{item.label}</span>
                            {item.badge && (
                              <Badge variant="secondary" className="text-xs">
                                {item.badge}
                              </Badge>
                            )}
                            {item.comingSoon && (
                              <Badge variant="outline" className="text-xs">
                                Próximamente
                              </Badge>
                            )}
                          </div>
                          <p className="text-xs text-muted-foreground">
                            {item.description}
                          </p>
                        </div>
                      </div>
                    </Link>
                  ) : (
                    <div
                      className={cn(
                        buttonVariants({ variant: 'ghost' }),
                        'h-auto w-full justify-start p-3 opacity-40 cursor-not-allowed'
                      )}
                    >
                      <div className="flex w-full items-center gap-3">
                        <IconComponent className="h-4 w-4 flex-shrink-0" />
                        <div className="flex-1 text-left">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium">{item.label}</span>
                            <Badge variant="outline" className="text-xs">
                              Pro
                            </Badge>
                          </div>
                          <p className="text-xs text-muted-foreground">
                            {item.description}
                          </p>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </nav>

          <Separator className="my-4" />

          {/* Quick actions */}
          <div className="space-y-2">
            <h3 className="text-sm font-medium text-primary">Acciones rápidas</h3>
            
            {planId === PLANS.FREE && (
              <Link
                to={BILLING_PATH}
                className={cn(
                  buttonVariants({ variant: 'outline' }),
                  'w-full justify-start text-sm'
                )}
              >
                ⭐ Actualizar a Pro
              </Link>
            )}

            {isAdmin && (
              <Link
                to="/admin"
                className={cn(
                  buttonVariants({ variant: 'outline' }),
                  'w-full justify-start text-sm'
                )}
              >
                ⚙️ Panel Admin
              </Link>
            )}
          </div>
        </div>

        {/* Mobile Navigation */}
        <div className="mb-6 flex w-full gap-2 overflow-x-auto lg:hidden">
          <Link
            to={ROUTE_PATH}
            className={cn(
              buttonVariants({ variant: isSettingsIndex ? 'default' : 'outline', size: 'sm' }),
              'whitespace-nowrap'
            )}
          >
            General
          </Link>
          <Link
            to={BILLING_PATH}
            className={cn(
              buttonVariants({ variant: isBillingPath ? 'default' : 'outline', size: 'sm' }),
              'whitespace-nowrap'
            )}
          >
            Facturación
          </Link>
        </div>

        {/* Main Content */}
        <div className="flex-1 space-y-6">
          <Outlet />
        </div>
      </div>
    </div>
  )
}