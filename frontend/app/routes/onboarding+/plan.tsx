// frontend/app/routes/onboarding+/plan.tsx
import type { ActionFunctionArgs, LoaderFunctionArgs, MetaFunction } from '@remix-run/node'
import { json, redirect } from '@remix-run/node'
import { Form, useActionData, useLoaderData } from '@remix-run/react'
import { z } from 'zod'
import { getFormProps, getInputProps, useForm } from '@conform-to/react'
import { getZodConstraint, parseWithZod } from '@conform-to/zod'
import { AuthenticityTokenInput } from 'remix-utils/csrf/react'
import { HoneypotInputs } from 'remix-utils/honeypot/react'
import { getAuth } from '@clerk/remix/ssr.server'
import { CheckCircle, Star, Zap, AlertCircle } from 'lucide-react'

import { createStripeApiService } from '#app/services/stripe-api.server'
import { createApiService } from '#app/utils/backend.server'
import {
  PRICING_PLANS,
  PLANS,
  INTERVALS,
  formatPrice,
  getSavingsPercentage,
} from '#app/modules/stripe/plans'
import { validateCSRF } from '#app/utils/csrf.server'
import { checkHoneypot } from '#app/utils/honeypot.server'
import { useIsPending } from '#app/utils/misc'
import { ROUTE_PATH as ONBOARDING_USERNAME_PATH } from '#app/routes/onboarding+/username'
import { ROUTE_PATH as DASHBOARD_PATH } from '#app/routes/dashboard+/_layout'
import { Button } from '#app/components/ui/button'
import { RadioGroup, RadioGroupItem } from '#app/components/ui/radio-group'
import { Label } from '#app/components/ui/label'
import { Badge } from '#app/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '#app/components/ui/card'

export const ROUTE_PATH = '/onboarding/plan' as const

const PlanSelectionSchema = z.object({
  planId: z.nativeEnum(PLANS),
  interval: z.nativeEnum(INTERVALS).default(INTERVALS.MONTH),
})

export const meta: MetaFunction = () => {
  return [{ title: 'Seleccionar Plan - Remix SaaS' }]
}

export async function loader({ request }: LoaderFunctionArgs) {
  const { userId } = await getAuth({ request })
  
  if (!userId) {
    return redirect('/auth/sign-in')
  }

  try {
    // Verificar si el usuario tiene username configurado
    const apiService = await createApiService({ request })
    const user = await apiService.getCurrentUser()

    if (!user?.username) {
      return redirect(ONBOARDING_USERNAME_PATH)
    }

    // Verificar si ya tiene una suscripción activa (evitar duplicados)
    try {
      const stripeService = await createStripeApiService({ request })
      const subscription = await stripeService.getCurrentSubscription()

      if (subscription && subscription.status === 'active' && subscription.plan_id !== PLANS.FREE) {
        // Ya tiene suscripción de pago, ir al dashboard
        return redirect(DASHBOARD_PATH)
      }
    } catch (stripeError) {
      // Si no puede verificar Stripe, continuar (puede ser usuario nuevo sin customer)
      console.log('Could not verify Stripe subscription, continuing with onboarding')
    }

    return json({ 
      pricingPlans: PRICING_PLANS,
      backendConnected: true,
      user 
    })
  } catch (error) {
    console.error('Error en onboarding plan loader:', error)
    
    // Permitir continuar aunque el backend no esté disponible
    return json({ 
      pricingPlans: PRICING_PLANS,
      backendConnected: false,
      user: null,
      error: error instanceof Error ? error.message : 'Error desconocido'
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

  const submission = parseWithZod(formData, { schema: PlanSelectionSchema })
  if (submission.status !== 'success') {
    return json(submission.reply(), { status: submission.status === 'error' ? 400 : 200 })
  }

  const { planId, interval } = submission.value

  try {
    if (planId === PLANS.FREE) {
      // Para el plan gratuito, simplemente completar el onboarding
      // No necesitamos crear nada en Stripe para usuarios gratuitos
      return redirect(DASHBOARD_PATH)
    }

    // Para planes de pago, crear sesión de checkout con Stripe
    const stripeService = await createStripeApiService({ request })
    const { checkout_url } = await stripeService.createCheckoutSession(planId, interval)
    
    return redirect(checkout_url)

  } catch (error) {
    console.error('Error procesando selección de plan:', error)
    
    return json(
      submission.reply({
        formErrors: [
          error instanceof Error ? error.message : 'Error procesando la suscripción'
        ],
      }),
      { status: 500 }
    )
  }
}

export default function SelectPlanPage() {
  const { pricingPlans, backendConnected, error } = useLoaderData<typeof loader>()
  const lastResult = useActionData<typeof action>()
  const isPending = useIsPending()

  const [form, fields] = useForm({
    lastResult,
    constraint: getZodConstraint(PlanSelectionSchema),
    onValidate({ formData }) {
      return parseWithZod(formData, { schema: PlanSelectionSchema })
    },
    defaultValue: {
      planId: PLANS.PRO, // Pre-seleccionar Pro como recomendado
      interval: INTERVALS.MONTH,
    },
  })

  if (!backendConnected) {
    return (
      <div className="container mx-auto flex h-full flex-col items-center justify-center p-4">
        <div className="max-w-md text-center space-y-4">
          <AlertCircle className="h-12 w-12 text-yellow-500 mx-auto" />
          <h1 className="text-2xl font-bold">Selección de Plan</h1>
          <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
            <p className="text-sm text-yellow-700 dark:text-yellow-300">
              No se pudo conectar con el sistema de facturación. Puedes continuar con el plan gratuito 
              y actualizar más tarde desde la configuración.
            </p>
            {error && (
              <p className="text-xs text-yellow-600 dark:text-yellow-400 mt-2">
                Error técnico: {error}
              </p>
            )}
          </div>
          <Button asChild className="w-full">
            <a href={DASHBOARD_PATH}>Continuar con Plan Gratuito</a>
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="container mx-auto flex h-full flex-col items-center justify-center p-4">
      <div className="w-full max-w-6xl space-y-8">
        {/* Header */}
        <div className="text-center space-y-4">
          <h1 className="text-3xl font-bold">Elige tu Plan</h1>
          <p className="text-muted-foreground text-lg">
            Selecciona el plan que mejor se adapte a tus necesidades
          </p>
        </div>

        <Form method="post" {...getFormProps(form)}>
          <AuthenticityTokenInput />
          <HoneypotInputs />

          {form.errors && (
            <div className="mb-6 rounded-md border border-destructive bg-destructive/10 p-4 text-sm text-destructive">
              <ul className="list-disc list-inside space-y-1">
                {form.errors.map((error, index) => (
                  <li key={index}>{error}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Plan Selection */}
          <div className="grid gap-6 lg:grid-cols-3 mb-8">
            {Object.values(pricingPlans).map((plan) => {
              const isSelected = fields.planId.value === plan.id
              const isPro = plan.id === PLANS.PRO
              
              return (
                <Card 
                  key={plan.id} 
                  className={`relative cursor-pointer transition-all hover:shadow-lg ${
                    isSelected 
                      ? 'ring-2 ring-primary border-primary shadow-lg' 
                      : 'hover:border-primary/50'
                  } ${plan.popular ? 'border-primary/30' : ''}`}
                >
                  {plan.popular && (
                    <div className="absolute -top-3 left-1/2 transform -translate-x-1/2">
                      <Badge className="bg-primary text-primary-foreground px-3">
                        <Star className="h-3 w-3 mr-1" />
                        Más Popular
                      </Badge>
                    </div>
                  )}

                  <Label 
                    htmlFor={`plan-${plan.id}`}
                    className="block cursor-pointer h-full"
                  >
                    <input
                      type="radio"
                      id={`plan-${plan.id}`}
                      {...getInputProps(fields.planId, { type: 'radio', value: plan.id })}
                      className="sr-only"
                    />
                    
                    <CardHeader className="text-center pb-4">
                      <CardTitle className="text-xl flex items-center justify-center gap-2">
                        {plan.name}
                        {isPro && <Zap className="h-5 w-5 text-yellow-500" />}
                      </CardTitle>
                      <CardDescription>{plan.description}</CardDescription>
                      
                      {plan.id === PLANS.FREE ? (
                        <div className="text-3xl font-bold text-green-600">Gratis</div>
                      ) : (
                        <div className="space-y-2">
                          <div className="text-3xl font-bold">
                            {formatPrice(plan.prices.month.usd)}
                            <span className="text-base font-normal text-muted-foreground">/mes</span>
                          </div>
                          {getSavingsPercentage(plan.id) > 0 && (
                            <div className="text-sm text-green-600 dark:text-green-400">
                              o {formatPrice(plan.prices.year.usd / 12)}/mes anualmente
                              <br />
                              <Badge variant="secondary" className="mt-1">
                                Ahorra {getSavingsPercentage(plan.id)}%
                              </Badge>
                            </div>
                          )}
                        </div>
                      )}
                    </CardHeader>

                    <CardContent className="space-y-4">
                      <ul className="space-y-3">
                        {plan.features.map((feature, index) => (
                          <li key={index} className="flex items-start gap-2">
                            <CheckCircle className="h-4 w-4 text-green-500 mt-0.5 flex-shrink-0" />
                            <span className="text-sm">{feature}</span>
                          </li>
                        ))}
                      </ul>

                      {isSelected && (
                        <div className="pt-2 border-t border-border">
                          <Badge variant="default" className="w-full justify-center">
                            Seleccionado
                          </Badge>
                        </div>
                      )}
                    </CardContent>
                  </Label>
                </Card>
              )
            })}
          </div>

          {/* Billing Interval Selection (only for paid plans) */}
          {fields.planId.value && fields.planId.value !== PLANS.FREE && (
            <div className="mb-8">
              <h3 className="text-lg font-medium mb-4 text-center">
                Frecuencia de Facturación
              </h3>
              <RadioGroup 
                value={fields.interval.value}
                name={fields.interval.name}
                className="grid grid-cols-2 gap-4 max-w-md mx-auto"
              >
                <Label 
                  htmlFor="interval-monthly"
                  className={`flex items-center justify-center rounded-lg border p-4 cursor-pointer transition-all ${
                    fields.interval.value === INTERVALS.MONTH 
                      ? 'border-primary bg-primary/5 ring-1 ring-primary' 
                      : 'hover:bg-muted/50'
                  }`}
                >
                  <RadioGroupItem 
                    value={INTERVALS.MONTH} 
                    id="interval-monthly"
                    className="sr-only"
                  />
                  <input
                    type="radio"
                    {...getInputProps(fields.interval, { type: 'radio', value: INTERVALS.MONTH })}
                    className="sr-only"
                  />
                  <div className="text-center">
                    <div className="font-medium">Mensual</div>
                    <div className="text-sm text-muted-foreground">
                      Facturación mensual
                    </div>
                  </div>
                </Label>

                <Label 
                  htmlFor="interval-yearly"
                  className={`flex items-center justify-center rounded-lg border p-4 cursor-pointer transition-all ${
                    fields.interval.value === INTERVALS.YEAR 
                      ? 'border-primary bg-primary/5 ring-1 ring-primary' 
                      : 'hover:bg-muted/50'
                  }`}
                >
                  <RadioGroupItem 
                    value={INTERVALS.YEAR} 
                    id="interval-yearly"
                    className="sr-only"
                  />
                  <input
                    type="radio"
                    {...getInputProps(fields.interval, { type: 'radio', value: INTERVALS.YEAR })}
                    className="sr-only"
                  />
                  <div className="text-center">
                    <div className="font-medium">Anual</div>
                    <div className="text-sm text-green-600 dark:text-green-400">
                      Ahorra {getSavingsPercentage(fields.planId.value || PLANS.PRO)}%
                    </div>
                  </div>
                </Label>
              </RadioGroup>
            </div>
          )}

          {/* Submit Button */}
          <div className="text-center">
            <Button 
              type="submit" 
              size="lg" 
              disabled={isPending}
              className="min-w-48"
            >
              {isPending ? (
                'Procesando...'
              ) : fields.planId.value === PLANS.FREE ? (
                'Comenzar Gratis'
              ) : (
                `Continuar con ${pricingPlans[fields.planId.value as keyof typeof pricingPlans]?.name || 'Plan Seleccionado'}`
              )}
            </Button>
          </div>
        </Form>

        {/* Footer */}
        <div className="text-center text-sm text-muted-foreground space-y-2">
          <p>🔒 Pagos seguros procesados por Stripe</p>
          <p>Puedes cambiar o cancelar tu plan en cualquier momento</p>
          <p>Plan gratuito sin limitaciones de tiempo</p>
        </div>
      </div>
    </div>
  )
}