// frontend/app/routes/dashboard+/checkout.tsx
import type { LoaderFunctionArgs, MetaFunction } from '@remix-run/node'
import { useLoaderData, Link } from '@remix-run/react'
import { json, redirect } from '@remix-run/node'
import { getAuth } from '@clerk/remix/ssr.server'
import { CheckCircle, CreditCard, Receipt, ArrowRight } from 'lucide-react'

import { createStripeApiService } from '#app/services/stripe-api.server'
import { PLANS } from '#app/modules/stripe/plans'
import { Button } from '#app/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '#app/components/ui/card'
import { Badge } from '#app/components/ui/badge'
import { ROUTE_PATH as DASHBOARD_PATH } from '#app/routes/dashboard+/_layout'
import { ROUTE_PATH as BILLING_PATH } from '#app/routes/dashboard+/settings.billing'

export const ROUTE_PATH = '/dashboard/checkout' as const

export const meta: MetaFunction = () => {
  return [{ title: 'Checkout Success - Dashboard' }]
}

export async function loader({ request }: LoaderFunctionArgs) {
  const { userId } = await getAuth({ request })
  
  if (!userId) {
    return redirect('/auth/sign-in')
  }

  const url = new URL(request.url)
  const sessionId = url.searchParams.get('session_id')
  
  try {
    const stripeService = await createStripeApiService({ request })
    
    // Sincronizar el estado de la suscripción después del checkout
    const subscription = await stripeService.syncSubscriptionStatus()
    
    return json({
      subscription,
      sessionId,
      backendConnected: true,
    })
  } catch (error) {
    console.error('Error syncing subscription after checkout:', error)
    
    // Fallback: redirigir a billing para que el usuario pueda ver su estado
    return redirect(BILLING_PATH)
  }
}

export default function CheckoutSuccess() {
  const { subscription, sessionId } = useLoaderData<typeof loader>()

  const isPro = subscription?.plan_id === PLANS.PRO
  const isEnterprise = subscription?.plan_id === PLANS.ENTERPRISE

  return (
    <div className="flex h-full w-full px-6 py-8">
      <div className="mx-auto flex h-full w-full max-w-2xl items-center justify-center">
        <Card className="w-full">
          <CardHeader className="text-center space-y-4">
            <div className="mx-auto w-16 h-16 bg-green-100 dark:bg-green-900/20 rounded-full flex items-center justify-center">
              <CheckCircle className="h-8 w-8 text-green-600 dark:text-green-400" />
            </div>
            
            <div className="space-y-2">
              <CardTitle className="text-2xl">¡Pago Exitoso!</CardTitle>
              <p className="text-muted-foreground">
                Tu suscripción ha sido activada correctamente
              </p>
            </div>
          </CardHeader>

          <CardContent className="space-y-6">
            {/* Subscription Details */}
            {subscription && (
              <div className="bg-muted/50 rounded-lg p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="font-medium">Estado:</span>
                  <Badge variant="default" className="gap-1">
                    <CheckCircle className="h-3 w-3" />
                    Activo
                  </Badge>
                </div>
                
                <div className="flex items-center justify-between">
                  <span className="font-medium">Próxima facturación:</span>
                  <span>
                    {new Date(subscription.current_period_end * 1000).toLocaleDateString()}
                  </span>
                </div>
              </div>
            )}

            {/* What's Next */}
            <div className="space-y-4">
              <h3 className="font-medium text-lg">¿Qué sigue?</h3>
              
              <div className="grid gap-3">
                <div className="flex items-start gap-3 p-3 border rounded-lg">
                  <div className="w-8 h-8 bg-blue-100 dark:bg-blue-900/20 rounded-full flex items-center justify-center flex-shrink-0">
                    <span className="text-blue-600 dark:text-blue-400 font-semibold text-sm">1</span>
                  </div>
                  <div className="space-y-1">
                    <p className="font-medium">Explora las nuevas funciones</p>
                    <p className="text-sm text-muted-foreground">
                      Ahora tienes acceso a todas las funciones avanzadas de tu plan
                    </p>
                  </div>
                </div>
                
                <div className="flex items-start gap-3 p-3 border rounded-lg">
                  <div className="w-8 h-8 bg-blue-100 dark:bg-blue-900/20 rounded-full flex items-center justify-center flex-shrink-0">
                    <span className="text-blue-600 dark:text-blue-400 font-semibold text-sm">2</span>
                  </div>
                  <div className="space-y-1">
                    <p className="font-medium">Configura tu cuenta</p>
                    <p className="text-sm text-muted-foreground">
                      Personaliza tu perfil y configuraciones para aprovechar al máximo la plataforma
                    </p>
                  </div>
                </div>
                
                <div className="flex items-start gap-3 p-3 border rounded-lg">
                  <div className="w-8 h-8 bg-blue-100 dark:bg-blue-900/20 rounded-full flex items-center justify-center flex-shrink-0">
                    <span className="text-blue-600 dark:text-blue-400 font-semibold text-sm">3</span>
                  </div>
                  <div className="space-y-1">
                    <p className="font-medium">Gestiona tu facturación</p>
                    <p className="text-sm text-muted-foreground">
                      Revisa tus facturas y gestiona tu suscripción desde la configuración
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* Session Info (para debugging) */}
            {sessionId && (
              <div className="text-xs text-muted-foreground text-center space-y-1">
                <p>ID de sesión: {sessionId}</p>
                <p>Tu suscripción ha sido confirmada exitosamente</p>
              </div>
            )}

            {/* Action Buttons */}
            <div className="flex flex-col sm:flex-row gap-3">
              <Button asChild className="flex-1">
                <Link to={DASHBOARD_PATH}>
                  <ArrowRight className="h-4 w-4 mr-2" />
                  Ir al Dashboard
                </Link>
              </Button>
              
              <Button variant="outline" asChild className="flex-1">
                <Link to={BILLING_PATH}>
                  <Receipt className="h-4 w-4 mr-2" />
                  Ver Facturación
                </Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}