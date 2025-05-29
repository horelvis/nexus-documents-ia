// frontend/app/routes/dashboard+/settings.billing.tsx - Versión actualizada
import type { ActionFunctionArgs, LoaderFunctionArgs, MetaFunction } from '@remix-run/node'
import { useFetcher, useLoaderData } from '@remix-run/react'
import { json, redirect } from '@remix-run/node'
import { getAuth } from '@clerk/remix/ssr.server'
import { parseWithZod } from '@conform-to/zod'
import { z } from 'zod'
import { 
  CreditCard, 
  ExternalLink, 
  Calendar,
  CheckCircle,
  XCircle,
  Clock,
  AlertCircle,
  Settings,
  ArrowUpRight,
  Shield,
  Zap,
  Crown
} from 'lucide-react'

import { createStripeApiService } from '#app/services/stripe-api.server'
import { PLANS, PRICING_PLANS, formatPrice, getSavingsPercentage } from '#app/modules/stripe/plans'
import { analyzeSubscriptionStatus, getSubscriptionStatusColor, getSubscriptionStatusMessage } from '#app/utils/stripe'
import { createToastHeaders } from '#app/utils/toast.server'
import { validateCSRF } from '#app/utils/csrf.server'
import { checkHoneypot } from '#app/utils/honeypot.server'
import { useIsPending } from '#app/utils/misc'
import { Button } from '#app/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '#app/components/ui/card'
import { Badge } from '#app/components/ui/badge'
import { Separator } from '#app/components/ui/separator'
import { ROUTE_PATH as ONBOARDING_PLAN_PATH } from '#app/routes/onboarding+/plan'

export const ROUTE_PATH = '/dashboard/settings/billing' as const

export const meta: MetaFunction = () => {
  return [{ title: 'Facturación - Configuración' }]
}

const BillingActionSchema = z.object({
  intent: z.enum(['portal', 'upgrade']),
})

export async function loader({ request }: LoaderFunctionArgs) {
  const { userId } = await getAuth({ request })
  
  if (!userId) {
    return redirect('/auth/sign-in')
  }

  try {
    const stripeService = await createStripeApiService({ request })
    const subscription = await stripeService.getCurrentSubscription()

    return json({
      subscription,
      plans: PRICING_PLANS,
      backendConnected: true,
    })
  } catch (error) {
    console.error('Error loading billing data:', error)
    
    // Fallback data cuando no hay conexión con el backend
    return json({
      subscription: {
        id: 'local_free',
        plan_id: PLANS.FREE,
        interval: 'month' as const,
        status: 'active' as const,
        current_period_start: Date.now() / 1000,
        current_period_end: (Date.now() + 30 * 24 * 60 * 60 * 1000) / 1000,
        cancel_at_period_end: false,
        customer_id: 'local_customer',
      },
      plans: PRICING_PLANS,
      backendConnected: false,
      error: error instanceof Error ? error.message : 'Error desconocido',
    })
  }
}

export async function action({ request }: ActionFunctionArgs) {
  const { userId } = await getAuth({ request })
  
  if (!userId) {
    return redirect('/auth/sign-in')
  }

  const clonedRequest = request.clone()
  const formData = await clonedRequest.formData()
  
  await validateCSRF(formData, clonedRequest.headers)
  checkHoneypot(formData)

  const submission = parseWithZod(formData, { schema: BillingActionSchema })
  
  if (submission.status !== 'success') {
    return json(submission.reply(), { status: 400 })
  }

  const { intent } = submission.value

  try {
    const stripeService = await createStripeApiService({ request })

    switch (intent) {
      case 'portal':
        // Redirigir al Customer Portal de Stripe
        const { portal_url } = await stripeService.createCustomerPortal()
        return redirect(portal_url)

      case 'upgrade':
        // Redirigir a selección de plan
        return redirect(ONBOARDING_PLAN_PATH)

      default:
        return json(
          submission.reply({ formErrors: ['Invalid action'] }),
          { status: 400 }
        )
    }
  } catch (error) {
    console.error('Error processing billing action:', error)
    return json(
      submission.reply({ 
        formErrors: [error instanceof Error ? error.message : 'An error occurred'] 
      }),
      { 
        status: 500,
        headers: await createToastHeaders({
          title: 'Error',
          description: 'No se pudo procesar la acción. Inténtalo de nuevo.',
          type: 'error',
        }),
      }
    )
  }
}

export default function BillingSettings() {
  const { subscription, plans, backendConnected, error } = useLoaderData<typeof loader>()
  const fetcher = useFetcher()
  const isPending = useIsPending()

  const subscriptionStatus = analyzeSubscriptionStatus(subscription)
  const currentPlan = subscription ? plans[subscription.plan_id as keyof typeof plans] : plans.free
  const statusColors = getSubscriptionStatusColor(subscription?.status || 'inactive')
  const statusMessage = getSubscriptionStatusMessage(subscription)

  // Iconos para planes
  const getPlanIcon = (planId: string) => {
    switch (planId) {
      case PLANS.FREE:
        return null
      case PLANS.PRO:
        return <Zap className="h-4 w-4 text-yellow-500" />
      case PLANS.ENTERPRISE:
        return <Crown className="h-4 w-4 text-purple-500" />
      default:
        return null
    }
  }

  if (!backendConnected) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-primary">Facturación</h1>
          <p className="text-muted-foreground">
            Gestiona tu suscripción y métodos de pago
          </p>
        </div>

        <Card className="border-yellow-200 bg-yellow-50 dark:border-yellow-800 dark:bg-yellow-900/20">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-yellow-700 dark:text-yellow-400">
              <AlertCircle className="h-5 w-5" />
              Facturación No Disponible
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-yellow-600 dark:text-yellow-300">
              No se pudo conectar con el sistema de facturación. {error}
            </p>
            <p className="mt-2 text-xs text-yellow-500">
              Tu cuenta de Clerk sigue funcionando normalmente. Solo las funciones de pago están temporalmente no disponibles.
            </p>
            <Button 
              variant="outline" 
              className="mt-4"
              onClick={() => window.location.reload()}
            >
              Reintentar Conexión
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Plan Actual</CardTitle>
            <CardDescription>
              Estado de tu suscripción (modo offline)
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <h3 className="text-xl font-semibold">Plan Gratuito</h3>
                <Badge variant="secondary">Offline</Badge>
              </div>
            </div>
            <p className="mt-2 text-sm text-muted-foreground">
              Cuando se restablezca la conexión, verás tu plan actual y podrás gestionar tu suscripción.
            </p>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-primary">Facturación</h1>
        <p className="text-muted-foreground">
          Gestiona tu suscripción y métodos de pago
        </p>
      </div>

      {/* Current Subscription Status */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CreditCard className="h-5 w-5" />
            Suscripción Actual
          </CardTitle>
          <CardDescription>
            Estado y detalles de tu plan de suscripción
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Plan Info */}
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <div className="flex items-center gap-3">
                {getPlanIcon(currentPlan?.id || PLANS.FREE)}
                <h3 className="text-xl font-semibold">{currentPlan?.name || 'Plan Desconocido'}</h3>
                {currentPlan?.popular && (
                  <Badge variant="default" className="gap-1">
                    <Zap className="h-3 w-3" />
                    Popular
                  </Badge>
                )}
              </div>
              <p className="text-sm text-muted-foreground">
                {currentPlan?.description}
              </p>
            </div>
            
            {subscription && (
              <Badge 
                variant={subscription.status === 'active' ? 'default' : 'destructive'}
                className="gap-1"
              >
                {subscription.status === 'active' && <CheckCircle className="h-3 w-3" />}
                {subscription.status === 'canceled' && <XCircle className="h-3 w-3" />}
                {subscription.status === 'past_due' && <AlertCircle className="h-3 w-3" />}
                {subscription.status === 'unpaid' && <XCircle className="h-3 w-3" />}
                {subscription.status === 'incomplete' && <Clock className="h-3 w-3" />}
                {subscription.status || 'Desconocido'}
              </Badge>
            )}
          </div>

          {/* Status Message */}
          <div className={`rounded-lg border p-3 ${statusColors.bg} ${statusColors.border}`}>
            <p className={`text-sm font-medium ${statusColors.text}`}>
              {statusMessage.message}
            </p>
          </div>

          {/* Billing Details */}
          {subscription && subscriptionStatus.isPaid && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-muted-foreground">Ciclo de facturación:</span>
                <p className="font-medium capitalize">{subscription.interval}al</p>
              </div>
              <div>
                <span className="text-muted-foreground">Próxima facturación:</span>
                <p className="font-medium">
                  {subscriptionStatus.nextBillingDate?.toLocaleDateString('es-ES', {
                    year: 'numeric',
                    month: 'long', 
                    day: 'numeric'
                  })}
                </p>
              </div>
              {subscription.cancel_at_period_end && (
                <div className="md:col-span-2">
                  <span className="text-muted-foreground">Cancelación programada:</span>
                  <p className="font-medium text-orange-600">
                    Se cancelará el {subscriptionStatus.nextBillingDate?.toLocaleDateString('es-ES')}
                  </p>
                </div>
              )}
            </div>
          )}

          <Separator />

          {/* Action Buttons */}
          <div className="flex gap-3">
            {subscriptionStatus.isPaid ? (
              // Usuario con suscripción de pago - ir al portal
              <fetcher.Form method="post" className="flex-1">
                <input type="hidden" name="intent" value="portal" />
                <Button 
                  type="submit" 
                  className="w-full gap-2" 
                  disabled={isPending}
                >
                  <Settings className="h-4 w-4" />
                  {isPending ? 'Conectando...' : 'Gestionar Suscripción'}
                  <ExternalLink className="h-4 w-4" />
                </Button>
              </fetcher.Form>
            ) : (
              // Usuario gratuito - opción de upgrade
              <fetcher.Form method="post" className="flex-1">
                <input type="hidden" name="intent" value="upgrade" />
                <Button 
                  type="submit" 
                  className="w-full gap-2" 
                  disabled={isPending}
                >
                  <ArrowUpRight className="h-4 w-4" />
                  {isPending ? 'Redirigiendo...' : 'Actualizar Plan'}
                </Button>
              </fetcher.Form>
            )}
          </div>
        </CardContent>
      </Card>

      {/* What's included in current plan */}
      <Card>
        <CardHeader>
          <CardTitle>Funciones Incluidas</CardTitle>
          <CardDescription>
            Lo que incluye tu plan {currentPlan?.name}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3">
            {currentPlan?.features.map((feature, index) => (
              <div key={index} className="flex items-center gap-3">
                <CheckCircle className="h-4 w-4 text-green-500 flex-shrink-0" />
                <span className="text-sm">{feature}</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Upgrade Options (only for free users) */}
      {!subscriptionStatus.isPaid && (
        <Card>
          <CardHeader>
            <CardTitle>Planes Disponibles</CardTitle>
            <CardDescription>
              Desbloquea más funciones con un plan premium
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 md:grid-cols-2">
              {Object.values(plans)
                .filter(plan => plan.id !== PLANS.FREE)
                .map(plan => (
                  <div key={plan.id} className="border rounded-lg p-4 space-y-3 hover:shadow-md transition-shadow">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        {getPlanIcon(plan.id)}
                        <h3 className="font-semibold">{plan.name}</h3>
                      </div>
                      {plan.popular && (
                        <Badge variant="default" className="gap-1">
                          <Zap className="h-3 w-3" />
                          Popular
                        </Badge>
                      )}
                    </div>
                    
                    <p className="text-sm text-muted-foreground">
                      {plan.description}
                    </p>
                    
                    <div className="space-y-2">
                      <div className="flex items-baseline gap-2">
                        <span className="text-2xl font-bold">
                          {formatPrice(plan.prices.month.usd)}
                        </span>
                        <span className="text-sm text-muted-foreground">/mes</span>
                      </div>
                      
                      {getSavingsPercentage(plan.id) > 0 && (
                        <p className="text-sm text-green-600 dark:text-green-400">
                          Ahorra {getSavingsPercentage(plan.id)}% pagando anualmente
                        </p>
                      )}
                    </div>

                    <fetcher.Form method="post">
                      <input type="hidden" name="intent" value="upgrade" />
                      <Button variant="outline" className="w-full">
                        Seleccionar {plan.name}
                      </Button>
                    </fetcher.Form>
                  </div>
                ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Customer Portal Info */}
      {subscriptionStatus.isPaid && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Shield className="h-5 w-5" />
              Portal de Cliente Seguro
            </CardTitle>
            <CardDescription>
              Gestiona tu suscripción de forma segura con Stripe
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 text-sm">
              <div className="flex items-start gap-3">
                <CheckCircle className="h-4 w-4 text-green-500 mt-0.5" />
                <div>
                  <p className="font-medium">Actualizar método de pago</p>
                  <p className="text-muted-foreground">Cambia tu tarjeta de crédito o débito</p>
                </div>
              </div>
              
              <div className="flex items-start gap-3">
                <CheckCircle className="h-4 w-4 text-green-500 mt-0.5" />
                <div>
                  <p className="font-medium">Cambiar plan de suscripción</p>
                  <p className="text-muted-foreground">Actualiza o degrada tu plan actual</p>
                </div>
              </div>
              
              <div className="flex items-start gap-3">
                <CheckCircle className="h-4 w-4 text-green-500 mt-0.5" />
                <div>
                  <p className="font-medium">Descargar facturas</p>
                  <p className="text-muted-foreground">Accede a tu historial completo de facturación</p>
                </div>
              </div>
              
              <div className="flex items-start gap-3">
                <CheckCircle className="h-4 w-4 text-green-500 mt-0.5" />
                <div>
                  <p className="font-medium">Cancelar suscripción</p>
                  <p className="text-muted-foreground">Cancela en cualquier momento sin penalizaciones</p>
                </div>
              </div>
            </div>

            <div className="mt-4 p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-md">
              <p className="text-sm text-blue-700 dark:text-blue-300">
                <strong>Nota:</strong> El portal de cliente te redirigirá a Stripe, donde podrás gestionar 
                todos los aspectos de tu suscripción de forma segura. Después de realizar cambios, 
                serás redirigido de vuelta a esta página.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Security Notice */}
      <Card className="border-green-200 bg-green-50 dark:border-green-800 dark:bg-green-900/20">
        <CardContent className="pt-6">
          <div className="flex items-start gap-3">
            <Shield className="h-5 w-5 text-green-600 dark:text-green-400 mt-0.5" />
            <div>
              <h3 className="font-medium text-green-700 dark:text-green-300">
                Pagos Seguros con Stripe
              </h3>
              <p className="text-sm text-green-600 dark:text-green-400 mt-1">
                Todos los pagos son procesados de forma segura por Stripe. 
                Tu información de pago está encriptada y nunca es almacenada en nuestros servidores.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}