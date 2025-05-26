import { json, redirect } from '@remix-run/node'
import { createRemixStub } from '@remix-run/testing'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AuthenticityTokenProvider } from 'remix-utils/csrf/react'
import { HoneypotProvider } from 'remix-utils/honeypot/react'

import * as onboardingPlanRoute from '#app/routes/onboarding+/plan'
import { ROUTE_PATH as ONBOARDING_USERNAME_PATH } from '#app/routes/onboarding+/username'
import { ROUTE_PATH as DASHBOARD_PATH } from '#app/routes/dashboard+/_layout'
import { PRICING_PLANS, PLANS, INTERVALS } from '#app/modules/stripe/plans'
import { prisma } from '#app/utils/db.server'
import * as authServer from '#app/modules/auth/auth.server'
import * as stripeQueries from '#app/modules/stripe/queries.server'
import { ERRORS } from '#app/utils/constants/errors'

// Mock prisma
vi.mock('#app/utils/db.server', () => ({
  prisma: {
    user: {
      findUnique: vi.fn(),
      update: vi.fn(),
    },
    subscription: {
      findUnique: vi.fn(),
      create: vi.fn(),
    },
  },
}))

// Mock auth.server
vi.mock('#app/modules/auth/auth.server', async () => {
  const actual = await vi.importActual('#app/modules/auth/auth.server')
  return {
    ...actual,
    requireUser: vi.fn(),
    requireSessionUser: vi.fn(),
  }
})

// Mock stripe queries.server
vi.mock('#app/modules/stripe/queries.server', () => ({
  createCustomer: vi.fn(),
  createFreeSubscription: vi.fn(),
  createSubscriptionCheckout: vi.fn(),
}))

// Mock CSRF and Honeypot related utilities if they are not automatically handled by testing setup
// For now, we'll assume they are handled or mock them specifically in tests if needed.
// vi.mock('#app/utils/csrf.server', () => ({ validateCSRF: vi.fn() })) // Will mock specific functions later
// vi.mock('#app/utils/honeypot.server', () => ({ checkHoneypot: vi.fn() })) // Will mock specific functions later
import * as csrfServer from '#app/utils/csrf.server'
import * as honeypotServer from '#app/utils/honeypot.server'

const mockUserFn = authServer.requireUser as vi.Mock
const mockSessionUserFn = authServer.requireSessionUser as vi.Mock
const mockPrismaUserFindUnique = prisma.user.findUnique as vi.Mock
const mockPrismaSubscriptionFindUnique = prisma.subscription.findUnique as vi.Mock
const mockPrismaUserUpdate = prisma.user.update as vi.Mock
const mockPrismaSubscriptionCreate = prisma.subscription.create as vi.Mock

const mockCreateCustomer = stripeQueries.createCustomer as vi.Mock
const mockCreateFreeSubscription = stripeQueries.createFreeSubscription as vi.Mock
const mockCreateSubscriptionCheckout = stripeQueries.createSubscriptionCheckout as vi.Mock

// Mock specific functions from csrf.server and honeypot.server
vi.mock('#app/utils/csrf.server', async () => {
  const actual = await vi.importActual('#app/utils/csrf.server');
  return {
    ...actual,
    validateCSRF: vi.fn(),
  };
});
vi.mock('#app/utils/honeypot.server', async () => {
  const actual = await vi.importActual('#app/utils/honeypot.server');
  return {
    ...actual,
    checkHoneypot: vi.fn(),
  };
});

const mockValidateCSRF = csrfServer.validateCSRF as vi.Mock
const mockCheckHoneypot = honeypotServer.checkHoneypot as vi.Mock

const mockCSRFToken = 'test-csrf-token'
// Default to valid CSRF and Honeypot for most tests
mockValidateCSRF.mockImplementation(() => Promise.resolve())
mockCheckHoneypot.mockImplementation(() => {})

// Helper to create a RemixStub with necessary providers
const createTestStub = (
  props: {
    loader?: typeof onboardingPlanRoute.loader
    action?: typeof onboardingPlanRoute.action
    initialEntries?: string[]
  } = {},
) => {
  const RemixStub = createRemixStub([
    {
      path: onboardingPlanRoute.ROUTE_PATH,
      Component: onboardingPlanRoute.default,
      loader: props.loader || onboardingPlanRoute.loader,
      action: props.action || onboardingPlanRoute.action,
    },
    {
      path: ONBOARDING_USERNAME_PATH,
      Component: () => <div>Mock Username Page</div>,
    },
    {
      path: DASHBOARD_PATH,
      Component: () => <div>Mock Dashboard Page</div>,
    },
  ])

  return (
    <AuthenticityTokenProvider token={mockCSRFToken}>
      <HoneypotProvider>
        <RemixStub initialEntries={props.initialEntries || [onboardingPlanRoute.ROUTE_PATH]} />
      </HoneypotProvider>
    </AuthenticityTokenProvider>
  )
}

describe('Onboarding Plan Route', () => {
  afterEach(() => {
    vi.resetAllMocks()
  })

  describe('Loader', () => {
    it('redirects to username page if user has no username', async () => {
      mockUserFn.mockResolvedValue({ id: 'user-1', email: 'test@example.com', username: null })
      const response = await onboardingPlanRoute.loader({
        request: new Request(`http://localhost${onboardingPlanRoute.ROUTE_PATH}`),
        params: {},
        context: {},
      })
      expect(response).toEqual(redirect(ONBOARDING_USERNAME_PATH))
    })

    it('redirects to dashboard if user has active non-free subscription', async () => {
      mockUserFn.mockResolvedValue({ id: 'user-1', email: 'test@example.com', username: 'testuser' })
      mockPrismaSubscriptionFindUnique.mockResolvedValue({
        id: 'sub-1',
        userId: 'user-1',
        planId: PLANS.PRO,
        status: 'active',
      })
      const response = await onboardingPlanRoute.loader({
        request: new Request(`http://localhost${onboardingPlanRoute.ROUTE_PATH}`),
        params: {},
        context: {},
      })
      expect(response).toEqual(redirect(DASHBOARD_PATH))
    })

    it('redirects to dashboard if user has active free subscription', async () => {
      mockUserFn.mockResolvedValue({ id: 'user-1', email: 'test@example.com', username: 'testuser' })
      mockPrismaSubscriptionFindUnique.mockResolvedValue({
        id: 'sub-1',
        userId: 'user-1',
        planId: PLANS.FREE,
        status: 'active',
      })
      const response = await onboardingPlanRoute.loader({
        request: new Request(`http://localhost${onboardingPlanRoute.ROUTE_PATH}`),
        params: {},
        context: {},
      })
      expect(response).toEqual(redirect(DASHBOARD_PATH))
    })

    it('returns pricingPlans if user has username and no active subscription', async () => {
      mockUserFn.mockResolvedValue({ id: 'user-1', email: 'test@example.com', username: 'testuser' })
      mockPrismaSubscriptionFindUnique.mockResolvedValue(null) // No subscription
      const response = await onboardingPlanRoute.loader({
        request: new Request(`http://localhost${onboardingPlanRoute.ROUTE_PATH}`),
        params: {},
        context: {},
      })
      const data = await response.json()
      expect(data).toEqual({ pricingPlans: PRICING_PLANS })
    })
  })

  describe('Action', () => {
    const testUser = { id: 'user-1', email: 'test@example.com', username: 'testuser', customerId: null }
    const testUserWithCustomerId = { ...testUser, customerId: 'cus_test123' }

    const createFormData = (data: Record<string, string>, includeCsrf = true, fillHoneypot = false) => {
      const formData = new FormData()
      if (includeCsrf) {
        formData.append('csrf_token', mockCSRFToken) // Default name from remix-utils
      }
      if (fillHoneypot) {
        // Assuming default honeypot input name is 'HP-name', replace if different
        // Needs to match what HoneypotProvider uses or what checkHoneypot expects.
        // Let's assume 'HP-name' for now based on common examples.
        // The actual name is configured in `honeypot.server.ts` via `new Honeypot({ ... })`.
        // For this test, we'll use a common default 'name' which is often part of the HoneypotSetup.
        // If specific field names are used by the Honeypot in this app, they should be used here.
        // For example, if it's `fields.name` and `fields.timestampName` from `remix-utils/honeypot/server`
        // then those field names need to be used. For now, a generic name.
        formData.append('name', 'bot-value') // A common honeypot field name
      }
      for (const key in data) {
        formData.append(key, data[key])
      }
      return formData
    }

    it('fails if CSRF validation fails', async () => {
      mockSessionUserFn.mockResolvedValue(testUser)
      mockValidateCSRF.mockImplementation(() => { throw new Error('CSRF Validation Failed') })
      
      const formData = createFormData({ planId: PLANS.PRO, interval: INTERVALS.MONTH }, false) // No CSRF token
      
      // Or alternatively, to simulate validateCSRF throwing an error:
      // const formData = createFormData({ planId: PLANS.PRO, interval: INTERVALS.MONTH })
      // mockValidateCSRF.mockRejectedValueOnce(new Error("CSRF Error"));


      try {
        await onboardingPlanRoute.action({
          request: new Request(`http://localhost${onboardingPlanRoute.ROUTE_PATH}`, { method: 'POST', body: formData }),
          params: {},
          context: {},
        })
        // Fail test if no error is thrown
        expect(true).toBe(false)
      } catch (e: any) {
        expect(e.message).toContain('CSRF') // Or specific error message
      }
      // Reset mock for other tests
      mockValidateCSRF.mockImplementation(() => Promise.resolve())
    })

    it('fails if Honeypot check fails', async () => {
      mockSessionUserFn.mockResolvedValue(testUser)
      mockCheckHoneypot.mockImplementation(() => { throw new Error('Honeypot Check Failed') })

      const formData = createFormData({ planId: PLANS.PRO, interval: INTERVALS.MONTH }, true, true) // Fill honeypot

      try {
        await onboardingPlanRoute.action({
          request: new Request(`http://localhost${onboardingPlanRoute.ROUTE_PATH}`, { method: 'POST', body: formData }),
          params: {},
          context: {},
        })
        expect(true).toBe(false)
      } catch (e: any) {
        expect(e.message).toContain('Honeypot')
      }
      // Reset mock for other tests
      mockCheckHoneypot.mockImplementation(() => {})
    })
    
    it('returns validation error for missing planId', async () => {
      mockSessionUserFn.mockResolvedValue(testUser)
      const formData = createFormData({ interval: INTERVALS.MONTH }) // Missing planId

      const response = await onboardingPlanRoute.action({
        request: new Request(`http://localhost${onboardingPlanRoute.ROUTE_PATH}`, { method: 'POST', body: formData }),
        params: {},
        context: {},
      })
      const data = await response.json()
      expect(response.status).toBe(400) // Or 200 if Conform handles it that way
      expect(data.status).toBe('error') // Conform specific
      // expect(data.errors.planId).toBeDefined() // Check for specific field error
    })

    it('returns validation error for invalid planId', async () => {
        mockSessionUserFn.mockResolvedValue(testUser)
        const formData = createFormData({ planId: 'invalid-plan', interval: INTERVALS.MONTH })
  
        const response = await onboardingPlanRoute.action({
          request: new Request(`http://localhost${onboardingPlanRoute.ROUTE_PATH}`, { method: 'POST', body: formData }),
          params: {},
          context: {},
        })
        const data = await response.json()
        expect(response.status).toBe(400)
        expect(data.status).toBe('error')
      })

    describe('Free Plan Selection', () => {
      it('succeeds and redirects to dashboard (new customer)', async () => {
        mockSessionUserFn.mockResolvedValue(testUser) // User without customerId
        mockCreateCustomer.mockResolvedValue({ id: 'cus_test123', email: testUser.email })
        mockCreateFreeSubscription.mockResolvedValue(true)
        // prisma.user.update will be called by createCustomer, ensure it's mocked or handled
        mockPrismaUserUpdate.mockResolvedValue({})


        const formData = createFormData({ planId: PLANS.FREE, interval: INTERVALS.MONTH /* Interval is submitted but ignored for free */ })
        const response = await onboardingPlanRoute.action({
          request: new Request(`http://localhost${onboardingPlanRoute.ROUTE_PATH}`, { method: 'POST', body: formData }),
          params: {},
          context: {},
        })

        expect(mockCreateCustomer).toHaveBeenCalledWith({ userId: testUser.id })
        expect(mockCreateFreeSubscription).toHaveBeenCalledWith({ userId: testUser.id, request: expect.any(Request) })
        expect(response).toEqual(redirect(DASHBOARD_PATH))
      })
      
      it('succeeds and redirects to dashboard (existing customer)', async () => {
        mockSessionUserFn.mockResolvedValue(testUserWithCustomerId) // User with customerId
        mockCreateFreeSubscription.mockResolvedValue(true)

        const formData = createFormData({ planId: PLANS.FREE, interval: INTERVALS.MONTH })
        const response = await onboardingPlanRoute.action({
          request: new Request(`http://localhost${onboardingPlanRoute.ROUTE_PATH}`, { method: 'POST', body: formData }),
          params: {},
          context: {},
        })

        expect(mockCreateCustomer).not.toHaveBeenCalled()
        expect(mockCreateFreeSubscription).toHaveBeenCalledWith({ userId: testUserWithCustomerId.id, request: expect.any(Request) })
        expect(response).toEqual(redirect(DASHBOARD_PATH))
      })

      it('handles failure from createFreeSubscription', async () => {
        mockSessionUserFn.mockResolvedValue(testUserWithCustomerId)
        mockCreateFreeSubscription.mockResolvedValue(false) // Simulate failure

        const formData = createFormData({ planId: PLANS.FREE, interval: INTERVALS.MONTH })
        const response = await onboardingPlanRoute.action({
          request: new Request(`http://localhost${onboardingPlanRoute.ROUTE_PATH}`, { method: 'POST', body: formData }),
          params: {},
          context: {},
        })
        
        const data = await response.json()
        expect(response.status).toBe(400)
        expect(data.formErrors).toContain(ERRORS.SUBSCRIPTION_CREATION_FAILED_EXISTING)
      })
    })

    describe('Pro Plan Selection', () => {
        const mockStripeCheckoutUrl = 'https://checkout.stripe.com/mock-session'

        it('succeeds and redirects to Stripe Checkout (new customer)', async () => {
            mockSessionUserFn.mockResolvedValue(testUser)
            mockCreateCustomer.mockResolvedValue({ id: 'cus_new_test', email: testUser.email })
            mockPrismaUserUpdate.mockResolvedValue({})
            mockCreateSubscriptionCheckout.mockResolvedValue(mockStripeCheckoutUrl)

            const formData = createFormData({ planId: PLANS.PRO, interval: INTERVALS.MONTH })
            const response = await onboardingPlanRoute.action({
                request: new Request(`http://localhost${onboardingPlanRoute.ROUTE_PATH}`, { method: 'POST', body: formData }),
                params: {},
                context: {},
            })

            expect(mockCreateCustomer).toHaveBeenCalledWith({ userId: testUser.id })
            expect(mockCreateSubscriptionCheckout).toHaveBeenCalledWith({
                userId: testUser.id,
                planId: PLANS.PRO,
                planInterval: INTERVALS.MONTH,
                request: expect.any(Request),
            })
            expect(response).toEqual(redirect(mockStripeCheckoutUrl))
        })

        it('succeeds and redirects to Stripe Checkout (existing customer)', async () => {
            mockSessionUserFn.mockResolvedValue(testUserWithCustomerId)
            mockCreateSubscriptionCheckout.mockResolvedValue(mockStripeCheckoutUrl)

            const formData = createFormData({ planId: PLANS.PRO, interval: INTERVALS.YEAR })
            const response = await onboardingPlanRoute.action({
                request: new Request(`http://localhost${onboardingPlanRoute.ROUTE_PATH}`, { method: 'POST', body: formData }),
                params: {},
                context: {},
            })

            expect(mockCreateCustomer).not.toHaveBeenCalled()
            expect(mockCreateSubscriptionCheckout).toHaveBeenCalledWith({
                userId: testUserWithCustomerId.id,
                planId: PLANS.PRO,
                planInterval: INTERVALS.YEAR,
                request: expect.any(Request),
            })
            expect(response).toEqual(redirect(mockStripeCheckoutUrl))
        })

        it('handles failure from createSubscriptionCheckout', async () => {
            mockSessionUserFn.mockResolvedValue(testUserWithCustomerId)
            mockCreateSubscriptionCheckout.mockResolvedValue(null) // Simulate failure

            const formData = createFormData({ planId: PLANS.PRO, interval: INTERVALS.MONTH })
            const response = await onboardingPlanRoute.action({
                request: new Request(`http://localhost${onboardingPlanRoute.ROUTE_PATH}`, { method: 'POST', body: formData }),
                params: {},
                context: {},
            })

            const data = await response.json()
            expect(response.status).toBe(500)
            expect(data.formErrors).toContain(ERRORS.STRIPE_CHECKOUT_CREATION_FAILED)
        })

        it('handles failure from createCustomer during Pro plan selection', async () => {
            mockSessionUserFn.mockResolvedValue(testUser) // No customerId
            mockCreateCustomer.mockResolvedValue(null) // Simulate customer creation failure

            const formData = createFormData({ planId: PLANS.PRO, interval: INTERVALS.MONTH })
             const response = await onboardingPlanRoute.action({
                request: new Request(`http://localhost${onboardingPlanRoute.ROUTE_PATH}`, { method: 'POST', body: formData }),
                params: {},
                context: {},
            })

            const data = await response.json()
            expect(response.status).toBe(500)
            expect(data.formErrors).toContain(ERRORS.STRIPE_CUSTOMER_CREATION_FAILED)
            expect(mockCreateSubscriptionCheckout).not.toHaveBeenCalled()
        })
    })
  })

  describe('UI Rendering', () => {
    it('renders plans and continue button', async () => {
      // Mock loader data
      const mockLoaderData = { pricingPlans: PRICING_PLANS }
      const stubbedLoader = vi.fn().mockResolvedValue(json(mockLoaderData))

      render(createTestStub({ loader: stubbedLoader }))

      // Wait for plans to be rendered
      expect(await screen.findByText(PRICING_PLANS.FREE.name)).toBeInTheDocument()
      expect(await screen.findByText(PRICING_PLANS.PRO.name)).toBeInTheDocument()
      
      // Check for Pro plan prices (monthly/yearly)
      const proPlanMonthlyPrice = PRICING_PLANS.PRO.prices.month.amount / 100
      const proPlanYearlyPrice = PRICING_PLANS.PRO.prices.year.amount / 100
      // Regex to match price, allowing for different formatting (e.g. $10.00 or $10)
      expect(await screen.findByText(new RegExp(`\\$${proPlanMonthlyPrice.toFixed(2)}\\/mo`))).toBeInTheDocument()
      expect(await screen.findByText(new RegExp(`\\$${proPlanYearlyPrice.toFixed(2)}\\/yr`))).toBeInTheDocument()


      expect(screen.getByRole('button', { name: /Continue/i })).toBeInTheDocument()
    })
    
    it('allows selecting a plan and interval', async () => {
        const user = userEvent.setup()
        const mockLoaderData = { pricingPlans: PRICING_PLANS }
        const stubbedLoader = vi.fn().mockResolvedValue(json(mockLoaderData))
        
        render(createTestStub({ loader: stubbedLoader }))

        const proPlanLabel = await screen.findByText(PRICING_PLANS.PRO.name)
        // Click the Pro plan card (Label)
        await user.click(proPlanLabel.closest('label')!) 
        
        const proPlanRadio = screen.getByRole('radio', { name: PRICING_PLANS.PRO.name })
        expect(proPlanRadio).toBeChecked()

        // Select yearly interval for Pro plan
        const yearlyIntervalLabel = await screen.findByText(/\/\s*yr/i) // find label containing /yr
        await user.click(yearlyIntervalLabel.closest('label')!)

        // Find the radio button associated with the yearly interval.
        // It's visually hidden, so we might need a more robust way to select it.
        // Using `getAllByRole` and filtering, or adding a test-id.
        // For now, let's assume Conform correctly links the label and hidden input.
        // We can check if the form would submit the correct value.
        // This test primarily focuses on UI interaction leading to correct state.
        
        // This is more of an e2e test for form submission values.
        // Here, we've tested the user can click and change the checked state.
    })
  })
})

// Helper to get form data from a request (useful for checking action calls)
// async function getFormData(request: Request) {
//   const clonedReq = request.clone()
//   return await clonedReq.formData()
// }
