import type { ActionFunctionArgs, LoaderFunctionArgs, MetaFunction } from '@remix-run/node'
import { json, redirect } from '@remix-run/node'
import { Form, useActionData, useLoaderData } from '@remix-run/react'
import { z } from 'zod'
import { getFormProps, getInputProps, useForm } from '@conform-to/react'
import { getZodConstraint, parseWithZod } from '@conform-to/zod'
import { AuthenticityTokenInput } from 'remix-utils/csrf/react'
import { HoneypotInputs } from 'remix-utils/honeypot/react'

import {
  PRICING_PLANS,
  PLANS,
  INTERVALS,
  type PlanId,
  type PlanInterval,
} from '#app/modules/stripe/plans'
import {
  createCustomer,
  createFreeSubscription,
  createSubscriptionCheckout,
} from '#app/modules/stripe/queries.server'
import { validateCSRF } from '#app/utils/csrf.server'
import { checkHoneypot } from '#app/utils/honeypot.server'
import { useIsPending } from '#app/utils/misc'
import { ROUTE_PATH as ONBOARDING_USERNAME_PATH } from '#app/routes/onboarding+/username'
import { ROUTE_PATH as DASHBOARD_PATH } from '#app/routes/dashboard+/_layout'
import { Button } from '#app/components/ui/button'
import { RadioGroup, RadioGroupItem } from '#app/components/ui/radio-group'
import { Label } from '#app/components/ui/label'
import { ERRORS } from '#app/utils/constants/errors'

export const ROUTE_PATH = '/onboarding/plan' as const

const PlanSelectionSchema = z.object({
  planId: z.nativeEnum(PLANS),
  interval: z.nativeEnum(INTERVALS),
})

export const meta: MetaFunction = () => {
  return [{ title: 'Select Plan - Remix SaaS' }]
}

export async function loader({ request }: LoaderFunctionArgs) {
  const user = await requireUser(request)

  if (!user.username) {
    return redirect(ONBOARDING_USERNAME_PATH)
  }

  const subscription = await prisma.subscription.findUnique({
    where: { userId: user.id },
  })

  // If the user has any active subscription (including free), onboarding is considered complete for this page's purpose.
  // The main _layout.tsx loader handles the comprehensive onboarding complete check.
  // This specific loader ensures that if a user lands here and already has an active subscription,
  // they are redirected to the dashboard.
  if (subscription && subscription.status === 'active') {
    return redirect(DASHBOARD_PATH)
  }

  return json({ pricingPlans: PRICING_PLANS })
}

export async function action({ request }: ActionFunctionArgs) {
  const sessionUser = await requireSessionUser(request)
  const clonedRequest = request.clone()
  const formData = await clonedRequest.formData()

  await validateCSRF(formData, clonedRequest.headers)
  checkHoneypot(formData)

  const submission = parseWithZod(formData, { schema: PlanSelectionSchema })
  if (submission.status !== 'success') {
    return json(submission.reply(), { status: submission.status === 'error' ? 400 : 200 })
  }

  const { planId, interval } = submission.value

  let customerId = sessionUser.customerId
  if (!customerId) {
    const customer = await createCustomer({ userId: sessionUser.id })
    if (!customer) {
      // Failed to create customer
      return json(
        submission.reply({
          formErrors: [ERRORS.STRIPE_CUSTOMER_CREATION_FAILED],
        }),
        { status: 500 },
      )
    }
    customerId = customer.id
  }

  if (planId === PLANS.FREE) {
    const success = await createFreeSubscription({ userId: sessionUser.id, request })
    if (!success) {
      // Could be that they already have a subscription, or other error.
      // The loader should ideally prevent this, but as a safeguard:
      return json(
        submission.reply({
          formErrors: [ERRORS.SUBSCRIPTION_CREATION_FAILED_EXISTING],
        }),
        { status: 400 },
      )
    }
    return redirect(DASHBOARD_PATH)
  }

  // For paid plans (e.g., PRO)
  if (planId === PLANS.PRO) {
    const checkoutUrl = await createSubscriptionCheckout({
      userId: sessionUser.id,
      planId: planId as PlanId, // Cast because Zod enum is string
      planInterval: interval as PlanInterval, // Cast because Zod enum is string
      request,
    })

    if (!checkoutUrl) {
      return json(
        submission.reply({
          formErrors: [ERRORS.STRIPE_CHECKOUT_CREATION_FAILED],
        }),
        { status: 500 },
      )
    }
    return redirect(checkoutUrl)
  }

  // Should not happen if schema is correct and plans are well-defined
  return json(submission.reply({ formErrors: [ERRORS.INVALID_PLAN_SELECTED] }), { status: 400 })
}

export default function SelectPlanPage() {
  const { pricingPlans } = useLoaderData<typeof loader>()
  const lastResult = useActionData<typeof action>()
  const isPending = useIsPending()

  const [form, fields] = useForm({
    lastResult,
    constraint: getZodConstraint(PlanSelectionSchema),
    onValidate({ formData }) {
      return parseWithZod(formData, { schema: PlanSelectionSchema })
    },
    defaultValue: {
      planId: PLANS.PRO, // Default to PRO plan
      interval: INTERVALS.MONTH, // Default to monthly
    },
  })

  return (
    <div className="container mx-auto flex h-full flex-col items-center justify-center p-4">
      <div className="mb-8 text-center">
        <h1 className="text-3xl font-bold">Choose Your Plan</h1>
        <p className="text-muted-foreground">Select a plan that best suits your needs.</p>
      </div>

      <Form method="post" className="w-full max-w-lg" {...getFormProps(form)}>
        <AuthenticityTokenInput />
        <HoneypotInputs />

        {form.errors && (
          <div className="mb-4 rounded-md border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
            {form.errors}
          </div>
        )}

        <RadioGroup
          {...getInputProps(fields.planId, { type: 'radio' })}
          className="mb-6 grid grid-cols-1 gap-6 md:grid-cols-2">
          {Object.values(pricingPlans).map((plan) => (
            <Label
              key={plan.id}
              htmlFor={form.id + '-' + plan.id}
              className={`has-[:checked]:border-primary relative flex cursor-pointer flex-col rounded-lg border bg-card p-6 shadow-sm transition-all hover:shadow-md
                ${fields.planId.value === plan.id ? 'border-primary ring-2 ring-primary' : ''}`}>
              <RadioGroupItem
                value={plan.id}
                id={form.id + '-' + plan.id}
                className="sr-only" // Visually hidden, label provides click area
                {...getInputProps(fields.planId, { type: 'radio', value: plan.id })}
              />
              <h2 className="mb-2 text-xl font-semibold text-primary">{plan.name}</h2>
              <p className="mb-4 flex-grow text-sm text-muted-foreground">{plan.description}</p>

              {plan.id !== PLANS.FREE && (
                <RadioGroup
                  {...getInputProps(fields.interval, { type: 'radio' })}
                  className="mt-auto grid grid-cols-2 gap-2">
                  {Object.values(INTERVALS).map((interval) => {
                    const priceInfo = plan.prices[interval]
                    if (!priceInfo) return null
                    return (
                      <Label
                        key={interval}
                        htmlFor={form.id + '-' + plan.id + '-' + interval}
                        className={`has-[:checked]:border-primary has-[:checked]:bg-primary/10 flex items-center justify-center rounded-md border p-3 text-sm
                          ${fields.planId.value === plan.id && fields.interval.value === interval ? 'border-primary ring-1 ring-primary' : ''}
                          ${fields.planId.value !== plan.id ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}>
                        <RadioGroupItem
                          value={interval}
                          id={form.id + '-' + plan.id + '-' + interval}
                          className="sr-only"
                          {...getInputProps(fields.interval, { type: 'radio', value: interval })}
                          disabled={fields.planId.value !== plan.id}
                        />
                        <span className={`capitalize ${
                          fields.planId.value === plan.id && fields.interval.value === interval
                            ? 'font-semibold text-primary'
                            : 'text-muted-foreground'
                        }`}>
                          ${(priceInfo.amount / 100).toFixed(2)}/{interval.slice(0, 2)}
                        </span>
                      </Label>
                    )
                  })}
                </RadioGroup>
              )}

              {plan.id === PLANS.FREE && (
                <div className="mt-auto">
                  <p className="text-lg font-semibold">Free</p>
                  <p className="text-sm text-muted-foreground">Get started with basic features.</p>
                </div>
              )}
            </Label>
          ))}
        </RadioGroup>

        <Button type="submit" className="w-full" size="lg" disabled={isPending}>
          {isPending ? 'Processing...' : 'Continue'}
        </Button>
      </Form>
    </div>
  )
}
